"""Dựng đồ thị từ đoạn văn HotpotQA (DECISIONS D4–D6, D12).

Hai chế độ:
  build_graph(example)        extract-v1: mỗi câu hỏi một đồ thị (bản thử baseline-v1/v2; giữ để tái lập)
  build_shared_graph(corpus)  extract-v2: MỘT đồ thị chung cho cả kho đoạn văn; prompt không có danh sách tiêu đề,
                              tên thực thể được liên kết với tiêu đề bằng code (TitleLinker)

Mỗi đoạn một lần gọi LLM. LLM trả bộ ba + số câu nguồn; code kiểm tra:
  - quan hệ phải thuộc 96 PID, nếu không → bỏ, ghi log;
  - số câu phải hợp lệ, nếu không → bỏ;
  - tên đầu/đuôi có xuất hiện trong câu được trích không → nếu không, gắn cờ provenance_suspect.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .common import ENTITY_TYPES, norm, relation_list_text, strip_paren
from .graph import KG
from .llm import parse_json

PROMPT_VERSION = "extract-v1"
SHARED_PROMPT_VERSION = "extract-v2"

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
    """Kiểm tra và thêm các bộ ba của một đoạn vào kg."""
    try:
        triples = parse_json(resp["content"]).get("triples", [])
    except Exception as e:  # noqa: BLE001 - ghi lại mọi lỗi định dạng
        log["parse_errors"].append({"title": title, "error": str(e), "content": resp["content"]})
        return
    for t in triples:
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


def build_shared_graph(corpus: dict, llm, rels: dict, progress=None):
    """extract-v2. corpus: {tiêu đề: [câu]}. Trả về (KG, log)."""
    kg = KG("shared")
    for t in corpus:
        kg.add_node(t, is_title=True)
    linker = TitleLinker(list(corpus))
    log = _new_log(SHARED_PROMPT_VERSION)
    for k, (title, sentences) in enumerate(corpus.items(), 1):
        if progress:
            progress(k, len(corpus), title)
        resp = llm.chat(build_messages_shared(title, sentences, rels), json_mode=True, session_id=f"extract:{title}")
        _process(kg, title, sentences, resp, rels, log, resolve=linker.resolve)
    log["linking"] = dict(linker.stats)
    log["ambiguous_names"] = linker.ambiguous.most_common(50)
    return kg, log


def sf_coverage(kg: KG, supporting_facts, covered=None) -> float:
    """Tỷ lệ câu bằng chứng của HotpotQA sinh ra được ít nhất một cạnh."""
    if covered is None:
        covered = {tuple(p) for e in kg.edges.values() for p in e["provenance"]}
    sf = [tuple(x) for x in supporting_facts]
    return sum(s in covered for s in sf) / len(sf) if sf else 0.0
