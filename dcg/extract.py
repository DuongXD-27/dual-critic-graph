"""Dựng đồ thị từ 10 đoạn văn của một câu HotpotQA (DECISIONS D4–D6).

Mỗi đoạn một lần gọi LLM. LLM trả bộ ba + số câu nguồn; code kiểm tra:
  - quan hệ phải thuộc 96 PID, nếu không → bỏ, ghi log;
  - số câu phải hợp lệ, nếu không → bỏ;
  - tên đầu/đuôi có xuất hiện trong câu được trích không → nếu không, gắn cờ provenance_suspect.
"""
from __future__ import annotations

from .common import ENTITY_TYPES, norm, relation_list_text
from .graph import KG
from .llm import parse_json

PROMPT_VERSION = "extract-v1"

SYSTEM = """You extract a knowledge graph from one Wikipedia paragraph.

Return JSON: {"triples": [{"head": str, "head_type": str, "relation": str, "tail": str, "tail_type": str, "sentences": [int]}]}

Rules:
- relation MUST be one of the relation ids listed below (e.g. "P57"). If no listed relation fits, do not output the triple.
- head_type / tail_type: one of PER, ORG, LOC, TIME, NUM, MISC.
- sentences: indices of the sentence(s) in THIS paragraph that state the fact.
- Entity names: if an entity is the subject of one of the PARAGRAPH TITLES given, write the title exactly as given.
  Replace pronouns and descriptions ("she", "the film", "the band") with the entity they refer to (usually this paragraph's title).
  Otherwise copy the name as it appears in the text.
- Only extract facts explicitly stated in the paragraph. Do not use outside knowledge.

Relations:
{relations}"""

USER = """PARAGRAPH TITLES (all paragraphs of this question):
{titles}

PARAGRAPH TITLE: {title}
SENTENCES:
{sentences}"""


def build_messages(title, sentences, all_titles, rels):
    sent_text = "\n".join(f"[{i}] {s.strip()}" for i, s in enumerate(sentences))
    return [
        {"role": "system", "content": SYSTEM.replace("{relations}", relation_list_text(rels))},
        {"role": "user", "content": USER.format(titles="\n".join(all_titles), title=title, sentences=sent_text)},
    ]


def _mentions(name: str, text: str) -> bool:
    return norm(name) in norm(text)


def build_graph(example: dict, llm, rels: dict):
    """example: một bản ghi HotpotQA. Trả về (KG, log)."""
    kg = KG(example["_id"])
    titles = [t for t, _ in example["context"]]
    for t in titles:
        kg.add_node(t, is_title=True)

    log = {"qid": example["_id"], "prompt_version": PROMPT_VERSION, "raw_triples": 0, "kept": 0,
           "dropped": [], "suspect": 0, "parse_errors": []}

    for title, sentences in example["context"]:
        resp = llm.chat(build_messages(title, sentences, titles, rels), json_mode=True)
        try:
            triples = parse_json(resp["content"]).get("triples", [])
        except Exception as e:  # noqa: BLE001 - ghi lại mọi lỗi định dạng
            log["parse_errors"].append({"title": title, "error": str(e), "content": resp["content"]})
            continue

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
            head_ok = _mentions(head, cited) or norm(head) == norm(title)
            tail_ok = _mentions(tail, cited) or norm(tail) == norm(title)
            suspect = not (head_ok and tail_ok)

            ht = t.get("head_type") if t.get("head_type") in ENTITY_TYPES else None
            tt = t.get("tail_type") if t.get("tail_type") in ENTITY_TYPES else None
            h = kg.add_node(head, ht)
            tl = kg.add_node(tail, tt)
            eid, new = kg.add_edge(h, rel, tl, [[title, i] for i in sids], origin="EXTRACTED",
                                   provenance_suspect=suspect)
            if not new and not suspect:
                kg.edges[eid]["provenance_suspect"] = False
            log["kept"] += 1
            log["suspect"] += int(suspect)
    return kg, log


def sf_coverage(kg: KG, supporting_facts) -> float:
    """Tỷ lệ câu bằng chứng của HotpotQA sinh ra được ít nhất một cạnh."""
    covered = {tuple(p) for e in kg.edges.values() for p in e["provenance"]}
    sf = [tuple(x) for x in supporting_facts]
    return sum(s in covered for s in sf) / len(sf) if sf else 0.0
