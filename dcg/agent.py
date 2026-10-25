"""Agent GraphRAG thử nghiệm (DECISIONS D1, D4, D7, D10, D11, D14).

Agent chỉ nhận câu hỏi; đồ thị và văn bản chỉ truy cập qua công cụ:
  search_nodes(query)      tìm nút theo tên                                   (không phải bước duyệt)
  start_at(node)           xuất phát, CHỈ tại thực thể có tên trong câu hỏi   → traversal_gate (type=start)
  get_edges()              xem cạnh của NÚT HIỆN TẠI                          (không phải bước duyệt)
  follow_edge(edge_id)     đi theo 1 cạnh của nút hiện tại = cách DUY NHẤT để di chuyển → traversal_gate (type=follow)
  read_paragraph(...)      đọc đoạn văn ĐÃ GẶP trên đường đi, tối đa MAX_READS đoạn
  add_edge(...)            ghi cạnh mới                                       → construction_gate
  answer(answer)           trả lời
Ngõ cụt (D14): cạnh cần đi bị thiếu nhưng câu văn đã đọc có nói → add_edge rồi follow_edge theo cạnh vừa ghi.
Sau khi trả lời có bước cập nhật bộ nhớ riêng: agent chỉ được gọi add_edge.

Mọi lần gọi cổng được ghi thành một bản ghi theo định dạng mẫu benchmark (gate records).
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from .common import norm, relation_list_text, strip_paren
from .graph import KG

PROMPT_VERSION = "agent-v5"
MAX_FOLLOWS = 8
MAX_TOOL_CALLS = 25
MAX_READS = 2           # số đoạn văn khác nhau được đọc mỗi lượt; đọc lại không tính (D10)
MAX_MEMORY_CALLS = 8    # số lần gọi add_edge tối đa ở bước cập nhật bộ nhớ (D11)

SYSTEM = """You answer a multi-hop question by walking a knowledge graph hop by hop, like following links.

How to work:
1. Start: use search_nodes to find the node of an entity NAMED IN THE QUESTION, then start_at it.
   start_at only accepts entities named in the question. For a comparison question, start at each of them in turn.
2. Walk: get_edges lists the edges of the node you are at. Move only with follow_edge, one hop at a time,
   toward the answer. You cannot jump to a node that is not named in the question; reach it by following edges.
   Each edge lists source_paragraphs: the paragraph(s) it was extracted from.
3. Missing edge: the graph was built automatically and may miss facts. If the edge you need is not there,
   read_paragraph a paragraph you have reached (the paragraph of a node you visited, or one listed in
   source_paragraphs of an edge you have seen; at most {max_reads} different paragraphs). If a sentence states the
   missing fact, write it with add_edge (head, relation id, tail, evidence_sentences), then follow_edge along the
   new edge and continue.
4. Stop: when you reach the node that answers the question, or at a dead end (no useful edge and no sentence that
   states the missing fact), call answer with a short answer (an entity name, a date, "yes" or "no").
   At a dead end give your best answer. After you answer, you will be asked to update the graph memory.

Limits: at most {max_follows} follow_edge calls, {max_reads} different paragraphs, and {max_calls} tool calls in total.

Relations:
{relations}"""

MEMORY_PROMPT = """Memory update. The graph is persistent memory that will be reused for future questions.
Look back at the facts you used for your answer. For each fact that is NOT already an edge in the graph, call add_edge
with a relation id from the list and the evidence you saw: evidence_sentences (paragraph + sentence index) if it comes
from text, or evidence_edges (edge ids) if you derived it by combining edges.
When you are finished, or if there is nothing to add, reply with the single word DONE."""

ADD_EDGE_TOOL = {"type": "function", "function": {
    "name": "add_edge", "description": "Write a new fact (head, relation, tail) into the graph.",
    "parameters": {"type": "object", "properties": {
        "head": {"type": "string", "description": "entity name"},
        "relation": {"type": "string", "description": "relation id, e.g. P57"},
        "tail": {"type": "string", "description": "entity name"},
        "evidence_sentences": {"type": "array", "description": "sentences that state the fact",
                               "items": {"type": "object", "properties": {
                                   "paragraph": {"type": "string"}, "sentence": {"type": "integer"}},
                                   "required": ["paragraph", "sentence"]}},
        "evidence_edges": {"type": "array", "items": {"type": "string"}, "description": "edge ids"}},
        "required": ["head", "relation", "tail"]}}}

TOOLS = [
    {"type": "function", "function": {
        "name": "search_nodes", "description": "Find graph nodes whose name contains the query.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "start_at", "description": "Start (or restart) the traversal at a node.",
        "parameters": {"type": "object", "properties": {"node": {"type": "string", "description": "node id, e.g. n3"}},
                       "required": ["node"]}}},
    {"type": "function", "function": {
        "name": "get_edges", "description": "List the edges of the current node.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "follow_edge", "description": "Move from the current node along one of its edges.",
        "parameters": {"type": "object", "properties": {"edge_id": {"type": "string"}}, "required": ["edge_id"]}}},
    {"type": "function", "function": {
        "name": "read_paragraph", "description": "Read a reachable source paragraph with numbered sentences.",
        "parameters": {"type": "object", "properties": {"paragraph": {"type": "string", "description": "paragraph title"}},
                       "required": ["paragraph"]}}},
    ADD_EDGE_TOOL,
    {"type": "function", "function": {
        "name": "answer", "description": "Give the final answer.",
        "parameters": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}}},
]


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+", norm(text))


def in_question(name: str, question: str, threshold: float = 0.85) -> bool:
    """Tên nút có được nhắc trong câu hỏi không (D14). Bỏ phần ngoặc của tiêu đề, so theo từ;
    chấp nhận sai chính tả nhẹ (vd. "Bennett"/"Bennet") bằng tỉ lệ giống nhau trên cửa sổ từ cùng độ dài."""
    nt, qt = _tokens(strip_paren(name)), _tokens(question)
    if not nt or not qt:
        return False
    n, q = " ".join(nt), " ".join(qt)
    if f" {n} " in f" {q} ":
        return True
    if len(n) < 5:
        return False
    for w in {len(nt) - 1, len(nt), len(nt) + 1} - {0}:
        for i in range(max(len(qt) - w + 1, 0)):
            if SequenceMatcher(None, n, " ".join(qt[i:i + w])).ratio() >= threshold:
                return True
    return False


class Episode:
    """Một lần agent trả lời một câu hỏi trên một đồ thị (đồ thị bị thay đổi tại chỗ nếu agent ghi)."""

    def __init__(self, kg: KG, example: dict, question: str, llm, gates, rels: dict, run_id: str, episode_id: str,
                 paragraphs: dict | None = None):
        """paragraphs: kho đoạn văn agent có thể tới được. Mặc định = 10 đoạn của câu hỏi;
        với đồ thị chung (D12) là toàn bộ kho."""
        self.kg, self.example, self.question = kg, example, question
        self.llm, self.gates, self.rels = llm, gates, rels
        self.run_id, self.episode_id = run_id, episode_id
        self.paragraphs = paragraphs if paragraphs is not None else {t: s for t, s in example["context"]}
        self.current = None
        self.path: list[dict] = []          # các hành động duyệt đã được chấp nhận (start + follow)
        self.events: list[dict] = []        # mọi lần gọi công cụ
        self.gate_records: list[dict] = []  # định dạng mẫu benchmark
        self.writes: list[dict] = []
        self.paragraphs_read: list[str] = []
        self.reachable: set[str] = set()    # đoạn văn agent đã "tới được" (D10)
        self.seen_names: set[str] = set()   # tên hai đầu các cạnh đã hiện cho agent (để phân loại cú nhảy)
        self.seen_text: list[str] = []      # câu văn agent đã đọc
        self.follows = 0
        self.reads_refused = 0
        self.starts_refused = 0             # start_at tại nút không có tên trong câu hỏi (D14)
        self.phase = "answer"
        self.final_answer = None
        self.memory = True                  # False: bỏ bước cập nhật bộ nhớ (chạy câu hỏi dò, D15)

    # ---------- mô tả cho agent ----------
    def _edge_view(self, e: dict) -> dict:
        sources = sorted({t for t, _ in e["provenance"]})
        self.reachable.update(s for s in sources if s in self.paragraphs)
        self.seen_names.update((norm(self.kg.name(e["head"])), norm(self.kg.name(e["tail"]))))
        return {"edge_id": e["id"], "head": self.kg.name(e["head"]), "relation": e["relation"],
                "relation_name": self.rels.get(e["relation"], "?"), "tail": self.kg.name(e["tail"]),
                "source_paragraphs": sources}

    def _arrive(self, nid: str) -> dict:
        self.current = nid
        if self.kg.name(nid) in self.paragraphs:
            self.reachable.add(self.kg.name(nid))
        return {"current": nid, "name": self.kg.name(nid),
                "edges": [self._edge_view(e) for e in self.kg.incident(nid)][:40]}

    def _path_view(self) -> list:
        keys = ("type", "from", "edge_id", "relation", "relation_name", "to", "direction", "start_in_question",
                "start_grounded_by")
        return [{k: s[k] for k in keys if k in s} for s in self.path]

    def _gate_traversal(self, action: dict, extra: dict) -> dict:
        path_view = self._path_view()
        from .gates import make_context
        context = make_context(self.paragraphs, [s.get("provenance", []) for s in self.path if s["type"] == "follow"],
                               (extra.get("action_edge") or {}).get("provenance"), self.paragraphs_read)
        verdict = self.gates.traversal_gate(self.question, path_view, action, context=context)
        self.gate_records.append({
            "kind": "traversal", "run_id": self.run_id, "episode_id": self.episode_id, "qid": self.kg.qid,
            "step": len(path_view), "question": self.question, "path": path_view, "action": action, **extra,
            "verdict": verdict["verdict"], "reason": verdict.get("reason"), "gold": None})
        return verdict

    # ---------- công cụ ----------
    def t_search_nodes(self, query):
        q = norm(query)
        if not q:
            return "no match"
        hits = []
        for n in self.kg.nodes.values():
            name = norm(n["name"])
            if name == q or norm(strip_paren(n["name"])) == q:
                rank = 0
            elif name.startswith(q):
                rank = 1
            elif q in name:
                rank = 2
            elif len(name) >= 4 and name in q:
                rank = 3
            else:
                continue
            hits.append((rank, len(name), n))
        hits.sort(key=lambda x: (x[0], x[1]))
        return [{"node": n["id"], "name": n["name"]} for _, _, n in hits[:10]] or "no match"

    def t_start_at(self, node):
        if node not in self.kg.nodes:
            return f"error: unknown node {node}"
        name = self.kg.name(node)
        if not in_question(name, self.question):
            self.starts_refused += 1
            return {"error": f"start_at only accepts entities named in the question; '{name}' is not. "
                             "Start at an entity of the question, then move with follow_edge."}
        action = {"type": "start", "from": self.kg.name(self.current) if self.current else None, "to": name,
                  "start_in_question": True, "start_grounded_by": "question"}
        verdict = self._gate_traversal(action, {})
        if verdict["verdict"] == "REJECT":
            return {"rejected": verdict.get("reason")}
        if verdict["verdict"] == "STOP":
            return {"stop": "enough evidence collected; call answer"}
        self.path.append(action)
        return self._arrive(node)

    def t_get_edges(self, node=None, **_):
        if self.current is None:
            return "error: call start_at first"
        if node not in (None, "", self.current):
            return f"error: you can only list edges of the current node {self.current}; use follow_edge or start_at"
        return [self._edge_view(e) for e in self.kg.incident(self.current)][:40]

    def t_follow_edge(self, edge_id):
        if self.current is None:
            return "error: call start_at first"
        e = self.kg.edges.get(edge_id)
        if not e or self.current not in (e["head"], e["tail"]):
            return f"error: {edge_id} is not an edge of the current node {self.current}"
        if self.follows >= MAX_FOLLOWS:
            return "error: follow limit reached, call answer"
        self.follows += 1
        nxt = self.kg.other_end(e, self.current)
        action = {"type": "follow", "from": self.kg.name(self.current), "edge_id": edge_id, "relation": e["relation"],
                  "relation_name": self.rels.get(e["relation"], "?"), "to": self.kg.name(nxt),
                  "direction": "forward" if e["head"] == self.current else "backward"}
        verdict = self._gate_traversal(action, {"action_edge": {"origin": e["origin"], "provenance": e["provenance"]}})
        if verdict["verdict"] == "REJECT":
            return {"rejected": verdict.get("reason")}
        if verdict["verdict"] == "STOP":
            return {"stop": "enough evidence collected; call answer"}
        self.path.append({**action, "origin": e["origin"], "provenance": e["provenance"]})
        return self._arrive(nxt)

    def _resolve(self, name: str) -> str:
        """Nối tên agent viết với nút có sẵn (D14): trùng tên nút, hoặc khớp DUY NHẤT một tiêu đề đoạn sau khi
        bỏ phần ngoặc ("Claudio López" → "Claudio López (footballer)"). Không khớp thì giữ nguyên (nút mới)."""
        nid = self.kg.find(name)
        if nid:
            return self.kg.name(nid)
        base = norm(strip_paren(name))
        cands = [t for t in self.paragraphs if norm(strip_paren(t)) == base]
        return cands[0] if len(cands) == 1 else name

    def _jump_grounding(self, name: str):
        """Tên nút có căn cứ từ đâu (D11.3, nay chỉ dùng để phân tích): 'question' | 'edges_seen' | 'text_read' | None.
        None = tên chưa từng xuất hiện trong những gì agent đã thấy → nhảy nhờ trí nhớ của model."""
        n = norm(strip_paren(name))
        if n in norm(self.question):
            return "question"
        if norm(name) in self.seen_names or n in self.seen_names:
            return "edges_seen"
        if any(n in norm(s) for s in self.seen_text):
            return "text_read"
        return None

    def t_read_paragraph(self, paragraph):
        title = paragraph
        if not title:
            return {"error": "missing argument 'paragraph'", "reachable": sorted(self.reachable)}
        if title not in self.paragraphs:
            matches = [t for t in self.reachable if norm(title) in norm(t)]
            if len(matches) != 1:
                return {"error": "unknown or ambiguous paragraph", "reachable": sorted(self.reachable)}
            title = matches[0]
        if title not in self.reachable:
            self.reads_refused += 1
            return {"error": "paragraph not reached yet", "reachable": sorted(self.reachable)}
        if title not in self.paragraphs_read:
            if len(self.paragraphs_read) >= MAX_READS:
                self.reads_refused += 1
                return {"error": f"read limit reached ({MAX_READS} paragraphs)", "already_read": self.paragraphs_read}
            self.paragraphs_read.append(title)
            self.seen_text.extend(self.paragraphs[title])
        return {"paragraph": title, "sentences": [f"[{i}] {s.strip()}" for i, s in enumerate(self.paragraphs[title])]}

    def t_add_edge(self, head, relation, tail, evidence_sentences=None, evidence_edges=None):
        evidence_sentences = evidence_sentences or []
        evidence_edges = evidence_edges or []
        raw = {"head_as_written": head, "tail_as_written": tail}
        head, tail = self._resolve(head), self._resolve(tail)
        attempt = {"head": head, "relation": relation, "tail": tail, "phase": self.phase,
                   "evidence_sentences": evidence_sentences, "evidence_edges": evidence_edges, **raw}
        if relation not in self.rels:
            self.writes.append({**attempt, "status": "invalid_relation"})
            return f"error: relation {relation} is not in the schema"
        if norm(head) == norm(tail):
            self.writes.append({**attempt, "status": "self_loop"})
            return "error: head and tail are the same entity"

        evidence, prov_sents = [], []
        for item in evidence_sentences:
            try:
                t, i = (item["paragraph"], int(item["sentence"])) if isinstance(item, dict) else (item[0], int(item[1]))
                text = self.paragraphs[t][i].strip()
            except (KeyError, IndexError, TypeError, ValueError):
                evidence.append({"type": "sentence", "ref": item, "text": None, "invalid": True})
                continue
            evidence.append({"type": "sentence", "title": t, "sid": i, "text": text,
                             "agent_had_read": t in self.paragraphs_read})
            prov_sents.append([t, i])
        used_edges = [x for x in evidence_edges if x in self.kg.edges]
        for x in used_edges:
            e = self.kg.edges[x]
            evidence.append({"type": "edge", "edge_id": x, "head": self.kg.name(e["head"]), "relation": e["relation"],
                             "tail": self.kg.name(e["tail"]), "origin": e["origin"],
                             "sentences": [{"title": t, "sid": i, "text": self.paragraphs.get(t, [""] * (i + 1))[i].strip()}
                                           for t, i in e["provenance"]]})
        origin = "AGENT_TEXT" if prov_sents else "AGENT_DERIVED"
        write = {"operation": "ADD_EDGE", "head": head, "relation": relation,
                 "relation_name": self.rels[relation], "tail": tail, "origin": origin}
        provenance = {"sentences": prov_sents, "edges": used_edges, "episode_id": self.episode_id}
        verdict = self.gates.construction_gate(write, evidence, provenance)
        self.gate_records.append({
            "kind": "construction", "run_id": self.run_id, "episode_id": self.episode_id, "qid": self.kg.qid,
            "phase": self.phase, "question": self.question, "write": write, "evidence": evidence,
            "provenance": provenance, "verdict": verdict["verdict"], "reason_code": verdict.get("reason_code"),
            "gold": None})
        if verdict["verdict"] != "ACCEPT":
            self.writes.append({**attempt, "origin": origin, "status": "rejected"})
            return {"rejected": verdict.get("reason_code")}

        h_existing, t_existing = self.kg.find(head), self.kg.find(tail)
        h = self.kg.add_node(head, origin=origin)
        tl = self.kg.add_node(tail, origin=origin)
        eid, new = self.kg.add_edge(h, relation, tl, prov_sents, origin=origin,
                                    evidence_edges=used_edges, created_by=self.episode_id)
        self.writes.append({**attempt, "origin": origin, "status": "added" if new else "duplicate",
                            "edge_id": eid, "new_head_node": h_existing is None, "new_tail_node": t_existing is None})
        res = {"edge_id": eid, "status": "added" if new else "already in graph", "head": head, "tail": tail}
        if self.phase == "answer" and self.current in (h, tl):
            res["next"] = f"you can now follow_edge {eid}"
        return res

    def t_answer(self, answer):
        self.final_answer = str(answer)
        return "ok"

    # ---------- vòng lặp ----------
    def _call_tools(self, messages, resp, allowed=None):
        """Thực thi mọi tool call trong một phản hồi; luôn trả lời đủ từng tool_call_id."""
        assistant = {"role": "assistant",
                     "tool_calls": [{"id": tc["id"], "type": "function",
                                     "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                                    for tc in resp["tool_calls"]]}
        if resp["content"]:
            assistant["content"] = resp["content"]
        messages.append(assistant)
        for tc in resp["tool_calls"]:
            if allowed is not None and tc["name"] not in allowed:
                result = f"error: only {sorted(allowed)} can be called now"
            elif self.final_answer is not None and self.phase == "answer":
                result = "ignored: answer already given"
            else:
                result = self._dispatch(tc["name"], tc["arguments"])
            self.events.append({"phase": self.phase, "tool": tc["name"], "args": tc["arguments"], "result": result,
                                "thought": resp["content"]})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, ensure_ascii=False)})

    def run(self) -> dict:
        system = SYSTEM.format(max_follows=MAX_FOLLOWS, max_calls=MAX_TOOL_CALLS, max_reads=MAX_READS,
                               relations=relation_list_text(self.rels))
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": f"Question: {self.question}"}]
        calls, nudges = 0, 0
        while self.final_answer is None:
            forced = calls >= MAX_TOOL_CALLS
            if forced:
                messages.append({"role": "user", "content": "Tool limit reached. Reply with the final answer only."})
            resp = self.llm.chat(messages, tools=None if forced else TOOLS, session_id=f"{self.run_id}:{self.episode_id}")
            if not forced and not resp["tool_calls"] and not (resp["content"] or "").strip() and nudges < 2:
                nudges += 1
                self.events.append({"phase": "answer", "tool": None, "content": resp["content"], "nudge": nudges})
                messages.append({"role": "user", "content": "Your last reply was empty. Call a tool, or call answer."})
                continue
            if forced or not resp["tool_calls"]:
                # không gọi công cụ → coi nội dung là câu trả lời
                self.final_answer = (resp["content"] or "").strip()
                self.events.append({"phase": "answer", "tool": None, "content": resp["content"], "forced": forced})
                messages.append({"role": "assistant", "content": resp["content"] or ""})
                break
            calls += len(resp["tool_calls"])
            self._call_tools(messages, resp)
        if self.memory:
            self.memory_update(messages)
        return self.summary()

    def memory_update(self, messages):
        """Bước cập nhật bộ nhớ sau khi trả lời (D11): chỉ add_edge."""
        self.phase = "memory"
        messages.append({"role": "user", "content": MEMORY_PROMPT})
        calls = 0
        while calls < MAX_MEMORY_CALLS:
            resp = self.llm.chat(messages, tools=[ADD_EDGE_TOOL], session_id=f"{self.run_id}:{self.episode_id}")
            if not resp["tool_calls"]:
                self.events.append({"phase": "memory", "tool": None, "content": resp["content"]})
                return
            calls += len(resp["tool_calls"])
            self._call_tools(messages, resp, allowed={"add_edge"})
        self.events.append({"phase": "memory", "tool": None, "content": "memory call limit reached"})

    def _dispatch(self, name, arguments):
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return f"error: unknown tool {name}"
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
            return fn(**args)
        except TypeError as e:
            return f"error: bad arguments ({e})"
        except json.JSONDecodeError:
            return "error: arguments are not valid JSON"

    def summary(self) -> dict:
        steps = [s for s in self.path if s["type"] == "follow"]
        starts = [s for s in self.path if s["type"] == "start"]
        return {
            "run_id": self.run_id, "episode_id": self.episode_id, "qid": self.kg.qid, "question": self.question,
            "answer": self.final_answer, "follows": self.follows, "starts": len(starts),
            "starts_refused": self.starts_refused,
            "follows_on_own_edges": sum(self.kg.edges[s["edge_id"]].get("created_by") == self.episode_id
                                        for s in steps),
            "starts_not_in_question": sum(not s["start_in_question"] for s in starts),
            "starts_ungrounded": sum(s["start_grounded_by"] is None for s in starts),
            "path": self.path, "paragraphs_read": self.paragraphs_read, "reads_refused": self.reads_refused,
            "writes": self.writes,
            "agent_edges_used": [s["edge_id"] for s in steps if s.get("origin", "").startswith("AGENT")],
            "agent_edges_used_detail": [
                {"edge_id": s["edge_id"], "origin": s["origin"],
                 "created_by": self.kg.edges[s["edge_id"]].get("created_by")}
                for s in steps if s.get("origin", "").startswith("AGENT")],
            "path_provenance": sorted({tuple(p) for s in steps for p in s.get("provenance", [])}),
            "events": self.events,
        }
