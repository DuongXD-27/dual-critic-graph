"""Hai cổng kiểm tra (DECISIONS D7, D17). Giao diện cố định:

traversal_gate(question, path, action, context=None) -> {"verdict": ACCEPT|REJECT|STOP, "reason": str}
construction_gate(write, evidence, provenance)        -> {"verdict": ACCEPT|REJECT, "reason_code": str}

context (D17, tuỳ chọn): những gì agent đã thấy, để critic có cùng thông tin với agent:
  {"action_evidence": [câu nguồn của cạnh ứng viên], "path_evidence": [câu nguồn của các cạnh đã đi],
   "paragraphs_read": {tiêu đề: [câu]}}
Critic KHÔNG nhận lời giải thích của agent và KHÔNG biết đáp án.

Bộ cổng:
  accept_all  baseline không critic
  rule        critic luật (rẻ, không gọi LLM) — mốc so sánh
  llm         critic LLM (model đặt bằng DCG_CRITIC_MODEL, mặc định = model của agent)
"""
from __future__ import annotations

import re

from .common import norm, strip_paren

TRAVERSAL_VERDICTS = ("ACCEPT", "REJECT", "STOP")
CONSTRUCTION_VERDICTS = ("ACCEPT", "REJECT")
REASON_CODES = ("SUPPORTED", "NOT_STATED", "NO_EVIDENCE", "WRONG_RELATION", "WRONG_DIRECTION", "WRONG_ENTITY",
                "NOT_ENTITY")
STOPWORDS = set("""a an the of in on at to for from by with and or is are was were be been who whom whose what which
when where why how did does do that this these those as it its his her their both same than more most first other
name named known also has have had into after before between during under over about""".split())


def words(text):
    return re.findall(r"\w+", norm(text))


def mentions(name, text):
    """Tên (bỏ ngoặc) xuất hiện trong câu, theo từ."""
    n, t = " ".join(words(strip_paren(name))), " ".join(words(text))
    return bool(n) and f" {n} " in f" {t} "


def path_text(path):
    parts = []
    for s in path:
        if s["type"] == "start":
            parts.append(("  |  " if parts else "") + f"[start] {s['to']}")
        else:
            rel = s.get("relation_name") or s["relation"]
            parts.append(f" —{rel}→ {s['to']}" if s.get("direction") == "forward" else f" ←{rel}— {s['to']}")
    return "".join(parts) or "(empty)"


def edge_text(action):
    rel = action.get("relation_name") or action["relation"]
    if action.get("direction") == "backward":
        return f'{action["to"]} —{rel}→ {action["from"]}  (moving from "{action["from"]}" to "{action["to"]}")'
    return f'{action["from"]} —{rel}→ {action["to"]}  (moving from "{action["from"]}" to "{action["to"]}")'


def evidence_lines(evidence, rels=None):
    rels = rels or {}
    out, k = [], 0
    for v in evidence:
        if v["type"] == "sentence":
            k += 1
            out.append(f'[S{k}] (paragraph "{v.get("title")}", sentence {v.get("sid")}) {v["text"]}'
                       if v.get("text") else f"[S{k}] (invalid reference)")
        else:
            k += 1
            src = " ".join(s["text"] for s in v.get("sentences", [])) or "(no source sentence)"
            out.append(f'[E{k}] existing edge: {v["head"]} —{rels.get(v["relation"], v["relation"])}→ {v["tail"]}. '
                       f"Its source: {src}")
    return out


def make_context(paragraphs, path_provenances, action_provenance, read_titles):
    """Dựng context cho traversal_gate từ kho đoạn văn: dùng chung cho agent (lúc chạy) và đánh giá offline."""
    def sents(provs):
        out = []
        for t, i in provs:
            s = paragraphs.get(t)
            if s and i < len(s) and s[i].strip() not in out:
                out.append(s[i].strip())
        return out
    return {"action_evidence": sents(action_provenance or []),
            "path_evidence": sents([p for ps in path_provenances for p in ps]),
            "paragraphs_read": {t: paragraphs[t] for t in read_titles if t in paragraphs}}


class AcceptAllGates:
    """Baseline không critic: mọi bước duyệt và mọi phép ghi đều được chấp nhận."""

    name = "accept_all"

    def traversal_gate(self, question, path, action, context=None):
        return {"verdict": "ACCEPT", "reason": "baseline"}

    def construction_gate(self, write, evidence, provenance):
        return {"verdict": "ACCEPT", "reason_code": "baseline"}


class RuleGates:
    """Critic luật (D17) — không gọi LLM, không dùng nhãn.
    Traversal: REJECT nếu quay lại nút đã qua; ACCEPT nếu đầu kia hoặc tên quan hệ có từ nội dung chung với câu hỏi,
               ngược lại REJECT. Không bao giờ STOP.
    Construction: ACCEPT ⇔ có ít nhất một câu bằng chứng (kể cả câu nguồn của cạnh bằng chứng) nhắc CẢ đầu lẫn đuôi."""

    name = "rule"

    def traversal_gate(self, question, path, action, context=None):
        visited = {norm(s["to"]) for s in path}
        if norm(action["to"]) in visited:
            return {"verdict": "REJECT", "reason": "revisit"}
        q = {w for w in words(question) if w not in STOPWORDS}
        cand = {w for w in words(strip_paren(action["to"])) + words(action.get("relation_name") or "")
                if w not in STOPWORDS}
        return {"verdict": "ACCEPT", "reason": "overlap"} if q & cand else {"verdict": "REJECT", "reason": "no_overlap"}

    def construction_gate(self, write, evidence, provenance):
        sents = [v["text"] for v in evidence if v["type"] == "sentence" and v.get("text")]
        sents += [s["text"] for v in evidence if v["type"] == "edge" for s in v.get("sentences", [])]
        if not sents:
            return {"verdict": "REJECT", "reason_code": "NO_EVIDENCE"}
        if any(mentions(write["head"], s) and mentions(write["tail"], s) for s in sents):
            return {"verdict": "ACCEPT", "reason_code": "SUPPORTED"}
        return {"verdict": "REJECT", "reason_code": "NOT_STATED"}


TRAVERSAL_SYSTEM = ("You are a strict verifier for an agent that answers multi-hop questions by walking a knowledge "
                    "graph extracted from Wikipedia paragraphs. You judge ONE proposed step. You are not told the "
                    "answer and you do not see the agent's reasoning. Reply with JSON only.")
TRAVERSAL_PROMPT = """TRAVERSAL CHECK
Question: {question}
Path so far: {path}
Source sentences of the edges already followed:
{path_evidence}
Paragraphs the agent has already read in full:
{read}
Proposed step: follow the edge {edge}
Source sentence(s) of this edge:
{action_evidence}

Choose one verdict:
- ACCEPT: following this edge moves toward the answer: its source sentence states a fact the question needs.
- REJECT: this edge does not help answer the question (unrelated fact, wrong entity, going back, or its sentence does
  not state what is needed).
- STOP: the path and the paragraphs already read already contain everything needed to answer; no more steps needed.
Reply with JSON only: {{"verdict": "ACCEPT|REJECT|STOP", "reason": "at most 20 words"}}"""

CONSTRUCTION_SYSTEM = ("You verify a fact before it is written into a knowledge graph that will be reused for future "
                       "questions. A fact can be true in the real world but must still be rejected if the submitted "
                       "evidence does not state it. Use only the evidence, never your own knowledge. Reply with JSON only.")
CONSTRUCTION_PROMPT = """WRITE CHECK
Proposed fact: head = "{head}", relation = {pid} ({rel}), tail = "{tail}"
(read as: "{head}" —{rel}→ "{tail}", following Wikidata conventions for {pid})
Evidence submitted with it:
{evidence}

Choose one reason_code:
- SUPPORTED: the evidence explicitly states this fact, with this head, this relation, this tail and this direction.
- NOT_STATED: the evidence does not state it (it needs extra inference, the evidence edges do not connect, or a link
  is missing).
- NO_EVIDENCE: there is no usable evidence.
- WRONG_RELATION: the evidence links the two entities, but by a different relation.
- WRONG_DIRECTION: head and tail are swapped for this relation.
- WRONG_ENTITY: the head or tail is not the entity the evidence is about.
- NOT_ENTITY: the head or tail is not a proper entity or value for this relation (e.g. an adjective like "American").
Reply with JSON only: {{"reason_code": "...", "reason": "at most 20 words"}}"""


class LLMGates:
    """Critic LLM (D17). Mỗi lần gọi cổng = 1 lời gọi LLM ở JSON mode; phản hồi hỏng → gọi lại 1 lần,
    vẫn hỏng → verdict mặc định (traversal ACCEPT, construction REJECT) và đánh dấu parse_error."""

    name = "llm"

    def __init__(self, llm=None, rels=None):
        if llm is None:
            import os

            from .llm import LLM
            llm = LLM(model=os.environ.get("DCG_CRITIC_MODEL") or None)
        if rels is None:
            from .common import load_relations
            rels = load_relations()
        self.llm, self.rels = llm, rels

    def _ask(self, system, user, field, allowed, session):
        from .llm import parse_json

        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(2):
            r = self.llm.chat(msgs, json_mode=True, session_id=session)
            try:
                p = parse_json(r["content"])
                val = str(p.get(field, "")).strip().upper()
            except (ValueError, AttributeError):
                p, val = {}, ""
            if val in allowed:
                return val, str(p.get("reason", ""))[:300], False
            msgs += [{"role": "assistant", "content": r["content"] or ""},
                     {"role": "user", "content": f'Invalid. Reply with JSON only, "{field}" must be one of {list(allowed)}.'}]
        return None, "parse_error", True

    def traversal_gate(self, question, path, action, context=None):
        ctx = context or {}
        read = ctx.get("paragraphs_read") or {}
        user = TRAVERSAL_PROMPT.format(
            question=question, path=path_text(path),
            path_evidence="\n".join(f"- {s}" for s in ctx.get("path_evidence", [])) or "(none)",
            read="\n".join(f'"{t}": ' + " ".join(s.strip() for s in sents) for t, sents in read.items()) or "(none)",
            edge=edge_text(action) if action["type"] == "follow" else f'start at "{action["to"]}"',
            action_evidence="\n".join(f"- {s}" for s in ctx.get("action_evidence", [])) or "(none)")
        v, reason, bad = self._ask(TRAVERSAL_SYSTEM, user, "verdict", TRAVERSAL_VERDICTS, "critic-traversal")
        return {"verdict": v or "ACCEPT", "reason": reason, "parse_error": bad}

    def construction_gate(self, write, evidence, provenance):
        user = CONSTRUCTION_PROMPT.format(head=write["head"], pid=write["relation"],
                                          rel=write.get("relation_name") or self.rels.get(write["relation"], "?"),
                                          tail=write["tail"],
                                          evidence="\n".join(evidence_lines(evidence, self.rels)) or "(none)")
        code, reason, bad = self._ask(CONSTRUCTION_SYSTEM, user, "reason_code", REASON_CODES, "critic-construction")
        code = code or "NO_EVIDENCE"
        return {"verdict": "ACCEPT" if code == "SUPPORTED" else "REJECT", "reason_code": code, "reason": reason,
                "parse_error": bad}


GATES = {AcceptAllGates.name: AcceptAllGates, RuleGates.name: RuleGates, LLMGates.name: LLMGates}
