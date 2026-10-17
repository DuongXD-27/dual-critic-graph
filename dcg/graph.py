"""Đồ thị tri thức của một câu hỏi (DECISIONS D4–D6).

Nút: {id, name, type, is_title, origin}
Cạnh: {id, head, relation, tail, provenance, origin, ...}
  provenance = [[tiêu đề đoạn, số câu], ...]  (đúng định dạng supporting_facts của HotpotQA)
  origin     = EXTRACTED | AGENT_TEXT | AGENT_DERIVED
  AGENT_DERIVED còn có evidence_edges = [id cạnh đã dùng]
"""
from __future__ import annotations

from .common import norm

ORIGINS = ("EXTRACTED", "AGENT_TEXT", "AGENT_DERIVED")


class KG:
    def __init__(self, qid: str):
        self.qid = qid
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self._by_name: dict[str, str] = {}

    # ---------- nút ----------
    def find(self, name: str):
        return self._by_name.get(norm(name))

    def add_node(self, name: str, type_=None, is_title=False, origin="EXTRACTED") -> str:
        nid = self.find(name)
        if nid:
            node = self.nodes[nid]
            if is_title:
                node["is_title"] = True
            if type_ and not node.get("type"):
                node["type"] = type_
            return nid
        nid = f"n{len(self.nodes)}"
        self.nodes[nid] = {"id": nid, "name": name, "type": type_, "is_title": is_title, "origin": origin}
        self._by_name[norm(name)] = nid
        return nid

    # ---------- cạnh ----------
    def find_edge(self, head: str, relation: str, tail: str):
        for e in self.edges.values():
            if e["head"] == head and e["relation"] == relation and e["tail"] == tail:
                return e["id"]
        return None

    def add_edge(self, head: str, relation: str, tail: str, provenance, origin="EXTRACTED", **meta) -> tuple[str, bool]:
        """Trả về (id cạnh, có_phải_cạnh_mới). Cạnh trùng thì gộp provenance."""
        assert origin in ORIGINS, origin
        eid = self.find_edge(head, relation, tail)
        if eid:
            e = self.edges[eid]
            for p in provenance:
                if list(p) not in e["provenance"]:
                    e["provenance"].append(list(p))
            return eid, False
        eid = f"e{len(self.edges)}"
        self.edges[eid] = {"id": eid, "head": head, "relation": relation, "tail": tail,
                           "provenance": [list(p) for p in provenance], "origin": origin, **meta}
        return eid, True

    def incident(self, nid: str) -> list[dict]:
        return [e for e in self.edges.values() if e["head"] == nid or e["tail"] == nid]

    def other_end(self, edge: dict, nid: str) -> str:
        return edge["tail"] if edge["head"] == nid else edge["head"]

    def name(self, nid: str) -> str:
        return self.nodes[nid]["name"]

    # ---------- lưu/đọc ----------
    def to_json(self) -> dict:
        return {"qid": self.qid, "nodes": list(self.nodes.values()), "edges": list(self.edges.values())}

    @classmethod
    def from_json(cls, d: dict) -> "KG":
        kg = cls(d["qid"])
        for n in d["nodes"]:
            kg.nodes[n["id"]] = dict(n)
            kg._by_name[norm(n["name"])] = n["id"]
        for e in d["edges"]:
            kg.edges[e["id"]] = dict(e)
        return kg

    def to_networkx(self):
        import networkx as nx

        g = nx.MultiDiGraph()
        for n in self.nodes.values():
            g.add_node(n["id"], **n)
        for e in self.edges.values():
            g.add_edge(e["head"], e["tail"], key=e["id"], **e)
        return g
