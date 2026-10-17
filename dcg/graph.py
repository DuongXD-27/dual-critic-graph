"""Đồ thị tri thức (DECISIONS D4–D6, D12).

Nút: {id, name, type, is_title, origin}
Cạnh: {id, head, relation, tail, provenance, origin, ...}
  provenance = [[tiêu đề đoạn, số câu], ...]  (đúng định dạng supporting_facts của HotpotQA)
  origin     = EXTRACTED | AGENT_TEXT | AGENT_DERIVED
  AGENT_DERIVED còn có evidence_edges = [id cạnh đã dùng]

Có chỉ mục theo tên, theo bộ ba và theo nút kề để chạy được với đồ thị chung hàng chục nghìn cạnh.
"""
from __future__ import annotations

from collections import defaultdict

from .common import norm

ORIGINS = ("EXTRACTED", "AGENT_TEXT", "AGENT_DERIVED")


class KG:
    def __init__(self, qid: str):
        self.qid = qid
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self._by_name: dict[str, str] = {}
        self._by_triple: dict[tuple, str] = {}
        self._adj: dict[str, list[str]] = defaultdict(list)

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
        return self._by_triple.get((head, relation, tail))

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
        self._index_edge(self.edges[eid])
        return eid, True

    def _index_edge(self, e: dict):
        self._by_triple[(e["head"], e["relation"], e["tail"])] = e["id"]
        self._adj[e["head"]].append(e["id"])
        if e["tail"] != e["head"]:
            self._adj[e["tail"]].append(e["id"])

    def incident(self, nid: str) -> list[dict]:
        return [self.edges[x] for x in self._adj.get(nid, [])]

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
            kg._index_edge(kg.edges[e["id"]])
        return kg

    def to_networkx(self):
        import networkx as nx

        g = nx.MultiDiGraph()
        for n in self.nodes.values():
            g.add_node(n["id"], **n)
        for e in self.edges.values():
            g.add_edge(e["head"], e["tail"], key=e["id"], **e)
        return g
