"""Dựng đồ thị từ đoạn văn HotpotQA (DECISIONS D4–D6, D12).

Các chế độ:
  build_graph(example)        extract-v1: mỗi câu hỏi một đồ thị (bản thử baseline-v1/v2; giữ để tái lập)
  build_shared_graph(corpus)  MỘT đồ thị chung cho cả kho đoạn văn; prompt không có danh sách tiêu đề,
                              tên thực thể được liên kết với tiêu đề bằng code (TitleLinker)
      per_call=1  extract-v2        : mỗi đoạn một lần gọi
      per_call>1  extract-v3-batch  : gộp nhiều đoạn (≤ batch_tokens token văn bản) mỗi lần gọi, kết quả tách theo
                                      từng đoạn; đoạn bị bỏ sót được gọi lại riêng (D13)
      workers>1   gọi song song; kết quả luôn được ghép vào đồ thị theo thứ tự kho → đồ thị không phụ thuộc thời gian chạy

LLM trả bộ ba + số câu nguồn; code kiểm tra:
  - quan hệ phải thuộc 96 PID, nếu không → bỏ, ghi log;
  - số câu phải hợp lệ, nếu không → bỏ;
  - tên đầu/đuôi có xuất hiện trong câu được trích không → nếu không, gắn cờ provenance_suspect.
"""
from __future__ import annotations

import random
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from .common import ENTITY_TYPES, norm, relation_list_text, strip_paren
from .graph import KG
from .llm import parse_json

PROMPT_VERSION = "extract-v1"
SHARED_PROMPT_VERSION = "extract-v2"
BATCH_PROMPT_VERSION = "extract-v3-batch"

_RULES = """Return JSON: {"triples": [{"head": str, "head_type": str, "relation": str, "tail": str, "tail_type": str, "sentences": [int]}]}

Rules:
- relation MUST be one of the relation ids listed below (e.g. "P57"). If no listed relation fits, do not output the triple.
- head_type / tail_type: one of PER, ORG, LOC, TIME, NUM, MISC.
- sentences: indices of the sentence(s) in THIS paragraph that state the fact.
- {naming}
  Replace pronouns and descriptions ("she", "the film", "the band") with the entity they refer to (usually this paragraph's title).
  Otherwise copy the name as it appears in the text.
- Only extract facts explicitly stated in the paragraph. Do not use outside knowledge.

Relations:
{relations}"""

SYSTEM = "You extract a knowledge graph from one Wikipedia paragraph.\n\n" + _RULES.replace(
    "{naming}", "Entity names: if an entity is the subject of one of the PARAGRAPH TITLES given, write the title exactly as given.")
SYSTEM_SHARED = "You extract a knowledge graph from one Wikipedia paragraph.\n\n" + _RULES.replace(
    "{naming}", "Entity names: for the subject of this paragraph, write the PARAGRAPH TITLE exactly as given.")

USER = """PARAGRAPH TITLES (all paragraphs of this question):
{titles}

PARAGRAPH TITLE: {title}
SENTENCES:
{sentences}"""

USER_SHARED = """PARAGRAPH TITLE: {title}
SENTENCES:
{sentences}"""

SYSTEM_BATCH = ("You extract a knowledge graph from several independent Wikipedia paragraphs.\n\n" + _RULES.replace(
    "{naming}", "Entity names: for the subject of each paragraph, write that paragraph's TITLE exactly as given.")
    .replace('Return JSON: {"triples": [', 'Return JSON: {"paragraphs": [{"title": str, "triples": [')
    .replace('"sentences": [int]}]}', '"sentences": [int]}]}]}')
    .replace("in THIS paragraph", "of that same paragraph (indices restart at 0 in every paragraph)")
    .replace("explicitly stated in the paragraph.", "explicitly stated in the paragraph.\n"
             "- Treat every paragraph INDEPENDENTLY. Never combine facts from different paragraphs.\n"
             "- Output one entry per paragraph, using its exact TITLE, even if its triples list is empty."))


def _sent_text(sentences):
    return "\n".join(f"[{i}] {s.strip()}" for i, s in enumerate(sentences))


def build_messages(title, sentences, all_titles, rels):
    return [
        {"role": "system", "content": SYSTEM.replace("{relations}", relation_list_text(rels))},
        {"role": "user", "content": USER.format(titles="\n".join(all_titles), title=title,
                                                sentences=_sent_text(sentences))},
    ]


def build_messages_shared(title, sentences, rels):
    return [
        {"role": "system", "content": SYSTEM_SHARED.replace("{relations}", relation_list_text(rels))},
        {"role": "user", "content": USER_SHARED.format(title=title, sentences=_sent_text(sentences))},
    ]


def build_messages_batch(titles, corpus, rels):
    blocks = [f"PARAGRAPH {k} — TITLE: {t}\nSENTENCES:\n{_sent_text(corpus[t])}" for k, t in enumerate(titles, 1)]
    return [
        {"role": "system", "content": SYSTEM_BATCH.replace("{relations}", relation_list_text(rels))},
        {"role": "user", "content": "\n\n".join(blocks)},
    ]


def make_batches(corpus: dict, per_call: int, batch_tokens: int, seed: int):
    """Trộn THỨ TỰ ĐOẠN (không trộn câu) với seed cố định rồi xếp vào lô ≤ per_call đoạn và ≤ batch_tokens token
    văn bản (ước lượng 4 ký tự ≈ 1 token). Không gom theo câu hỏi: đồ thị dựng độc lập với câu hỏi (D12)."""
    titles = list(corpus)
    random.Random(seed).shuffle(titles)
    batches, cur, cur_tok = [], [], 0
    for t in titles:
        tok = len(" ".join(corpus[t])) // 4 + 10
        if cur and (len(cur) >= per_call or cur_tok + tok > batch_tokens):
            batches.append(cur)
            cur, cur_tok = [], 0
        cur.append(t)
        cur_tok += tok
    if cur:
        batches.append(cur)
    return batches


def _mentions(name: str, text: str) -> bool:
    return norm(name) in norm(text)


class TitleLinker:
    """Liên kết tên thực thể do LLM trả về với tiêu đề đoạn văn (= tên bài Wikipedia, duy nhất trong kho).

    Thứ tự: khớp đúng tiêu đề → khớp tiêu đề đoạn đang đọc khi bỏ phần trong ngoặc → khớp duy nhất một tiêu đề
    khi bỏ phần trong ngoặc ('Strange Fruit' ~ 'Strange Fruit (film)'). Nhiều tiêu đề cùng khớp → giữ nguyên tên,
    ghi 'ambiguous' (đây là lỗi hợp nhất thực thể có thật, không cố đoán)."""

    def __init__(self, titles):
        self.exact = {norm(t): t for t in titles}
        self.stripped = defaultdict(set)
        for t in titles:
            self.stripped[norm(strip_paren(t))].add(t)
        self.stats = Counter()
        self.ambiguous = Counter()

    def resolve(self, name: str, current_title: str) -> str:
        n = norm(name)
        if n in self.exact:
            self.stats["exact_title"] += 1
            return self.exact[n]
        if n == norm(strip_paren(current_title)):
            self.stats["current_title"] += 1
            return current_title
        cands = self.stripped.get(n, set())
        if len(cands) == 1:
            self.stats["unique_stripped_title"] += 1
            return next(iter(cands))
        if len(cands) > 1:
            self.stats["ambiguous"] += 1
            self.ambiguous[name] += 1
        else:
            self.stats["not_a_title"] += 1
        return name


def _new_log(prompt_version):
    return {"prompt_version": prompt_version, "raw_triples": 0, "kept": 0, "dropped": [], "suspect": 0,
            "parse_errors": []}


def _process(kg, title, sentences, resp, rels, log, resolve=lambda name, title: name):
    """Đọc phản hồi của một đoạn rồi thêm các bộ ba vào kg."""
    try:
        triples = parse_json(resp["content"]).get("triples", [])
    except Exception as e:  # noqa: BLE001 - ghi lại mọi lỗi định dạng
        log["parse_errors"].append({"title": title, "error": str(e), "content": resp["content"]})
        return
    _add(kg, title, sentences, triples, rels, log, resolve)


def _add(kg, title, sentences, triples, rels, log, resolve=lambda name, title: name):
    """Kiểm tra và thêm các bộ ba của một đoạn vào kg."""
    if not isinstance(triples, list):
        triples = []
    for t in triples:
        if not isinstance(t, dict):
            log["dropped"].append({"title": title, "triple": t, "reason": "not_an_object"})
            continue
        log["raw_triples"] += 1
        head, tail, rel = str(t.get("head", "")).strip(), str(t.get("tail", "")).strip(), t.get("relation")
        sids = [i for i in t.get("sentences", []) if isinstance(i, int) and 0 <= i < len(sentences)]
        reason = None
        if rel not in rels:
            reason = "relation_not_in_schema"
        elif not head or not tail:
            reason = "empty_entity"
        elif not sids:
            reason = "no_valid_sentence"
        elif norm(head) == norm(tail):
            reason = "self_loop"
        if reason:
            log["dropped"].append({"title": title, "triple": t, "reason": reason})
            continue

        cited = " ".join(sentences[i] for i in sids)
        head_ok = _mentions(head, cited) or norm(head) == norm(title) or _mentions(strip_paren(head), cited)
        tail_ok = _mentions(tail, cited) or norm(tail) == norm(title) or _mentions(strip_paren(tail), cited)
        suspect = not (head_ok and tail_ok)

        ht = t.get("head_type") if t.get("head_type") in ENTITY_TYPES else None
        tt = t.get("tail_type") if t.get("tail_type") in ENTITY_TYPES else None
        h = kg.add_node(resolve(head, title), ht)
        tl = kg.add_node(resolve(tail, title), tt)
        if h == tl:
            log["dropped"].append({"title": title, "triple": t, "reason": "self_loop_after_linking"})
            continue
        eid, new = kg.add_edge(h, rel, tl, [[title, i] for i in sids], origin="EXTRACTED",
                               provenance_suspect=suspect)
        if not new and not suspect:
            kg.edges[eid]["provenance_suspect"] = False
        log["kept"] += 1
        log["suspect"] += int(suspect)


def build_graph(example: dict, llm, rels: dict):
    """extract-v1. example: một bản ghi HotpotQA. Trả về (KG, log)."""
    kg = KG(example["_id"])
    titles = [t for t, _ in example["context"]]
    for t in titles:
        kg.add_node(t, is_title=True)
    log = {"qid": example["_id"], **_new_log(PROMPT_VERSION)}
    for title, sentences in example["context"]:
        resp = llm.chat(build_messages(title, sentences, titles, rels), json_mode=True,
                        session_id=f"extract:{example['_id']}:{title}")
        _process(kg, title, sentences, resp, rels, log)
    return kg, log


def _parse_batch(resp, titles, log):
    """→ ({tiêu đề: [bộ ba]}, [tiêu đề bị bỏ sót]). Tiêu đề lạ → bỏ, ghi 'unknown_paragraph'."""
    try:
        items = parse_json(resp["content"]).get("paragraphs", [])
    except Exception as e:  # noqa: BLE001
        log["parse_errors"].append({"batch": titles, "error": str(e), "content": resp["content"]})
        return {}, list(titles)
    by_norm = {norm(t): t for t in titles}
    got = {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        t = by_norm.get(norm(it.get("title", "")))
        if t is None:
            log["dropped"].append({"title": it.get("title"), "reason": "unknown_paragraph",
                                   "n_triples": len(it.get("triples") or []), "batch": titles})
            continue
        got.setdefault(t, []).extend(it.get("triples") or [])
    return got, [t for t in titles if t not in got]


def build_shared_graph(corpus: dict, llm, rels: dict, progress=None, workers: int = 1, per_call: int = 1,
                       batch_tokens: int = 1200, seed: int = 0):
    """corpus: {tiêu đề: [câu]}. Trả về (KG, log)."""
    def single(title, retry=False):
        msgs = build_messages_shared(title, corpus[title], rels)
        if retry:  # tin nhắn khác → khoá cache khác → gọi mới thật
            msgs.append({"role": "user", "content": "Reply with ONLY the JSON object described above."})
        return llm.chat(msgs, json_mode=True, session_id=f"extract:{title}")

    lock, done = threading.Lock(), [0]

    def run_all(fn, jobs, label):
        def wrapped(job):
            out = fn(job)
            if progress:
                with lock:
                    done[0] += 1
                    progress(done[0], len(jobs), label)
            return out
        done[0] = 0
        if workers <= 1:
            return [wrapped(j) for j in jobs]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(wrapped, jobs))  # giữ đúng thứ tự jobs

    def singles(titles, label):
        """Mỗi đoạn một lần gọi; phản hồi không đọc được JSON → gọi lại đúng 1 lần."""
        bad = []
        for t, resp in zip(titles, run_all(single, titles, label)):
            try:
                per_par[t] = parse_json(resp["content"]).get("triples", [])
            except Exception:  # noqa: BLE001
                bad.append(t)
        log["parse_retries"] = log.get("parse_retries", 0) + len(bad)
        for t, resp in zip(bad, run_all(lambda x: single(x, retry=True), bad, label + " (gọi lại vì JSON hỏng)")):
            try:
                per_par[t] = parse_json(resp["content"]).get("triples", [])
            except Exception as e:  # noqa: BLE001
                log["parse_errors"].append({"title": t, "error": str(e), "content": resp["content"]})
        return len(bad)

    log = _new_log(SHARED_PROMPT_VERSION if per_call <= 1 else BATCH_PROMPT_VERSION)
    log.update({"per_call": per_call, "workers": workers, "batch_tokens": batch_tokens, "batch_seed": seed})
    per_par = {}  # tiêu đề → [bộ ba] (None = phản hồi hỏng)

    if per_call <= 1:
        titles = list(corpus)
        log["requests"] = len(titles) + singles(titles, "đoạn")
    else:
        batches = make_batches(corpus, per_call, batch_tokens, seed)
        log["batches"] = batches
        jobs = list(enumerate(batches))
        resps = run_all(lambda job: llm.chat(build_messages_batch(job[1], corpus, rels), json_mode=True,
                                             session_id=f"extract-batch:{seed}:{job[0]}"), jobs, "lô")
        skipped = []
        for (_, titles), resp in zip(jobs, resps):
            got, miss = _parse_batch(resp, titles, log)
            per_par.update(got)
            skipped.extend(miss)
        log["paragraph_skipped"] = skipped
        # đoạn bị bỏ sót → gọi lại riêng từng đoạn (prompt extract-v2)
        log["requests"] = len(batches) + len(skipped) + singles(skipped, "đoạn gọi lại")

    kg = KG("shared")
    for t in corpus:
        kg.add_node(t, is_title=True)
    linker = TitleLinker(list(corpus))
    for t in corpus:  # luôn theo thứ tự kho → id nút/cạnh không phụ thuộc thứ tự luồng
        if t in per_par:
            _add(kg, t, corpus[t], per_par[t], rels, log, resolve=linker.resolve)
    log["linking"] = dict(linker.stats)
    log["ambiguous_names"] = linker.ambiguous.most_common(50)
    return kg, log


def sf_coverage(kg: KG, supporting_facts, covered=None) -> float:
    """Tỷ lệ câu bằng chứng của HotpotQA sinh ra được ít nhất một cạnh."""
    if covered is None:
        covered = {tuple(p) for e in kg.edges.values() for p in e["provenance"]}
    sf = [tuple(x) for x in supporting_facts]
    return sum(s in covered for s in sf) / len(sf) if sf else 0.0
