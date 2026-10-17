"""Kiểm thử toàn bộ pipeline không cần mạng, dùng LLM giả trên ví dụ Big Stone Gap.

  python tests/test_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_graphs  # noqa: E402
import run_agent  # noqa: E402
from dcg.common import read_json, read_jsonl, write_json  # noqa: E402

EXAMPLE = {
    "_id": "q_bsg",
    "question": "The director of the romantic comedy \"Big Stone Gap\" is based in what New York city?",
    "answer": "Greenwich Village, New York City",
    "type": "bridge", "level": "medium",
    "supporting_facts": [["Big Stone Gap (film)", 0], ["Adriana Trigiani", 0]],
    "context": [
        ["Big Stone Gap (film)", [
            "Big Stone Gap is a 2014 American drama romantic comedy film written and directed by Adriana Trigiani and produced by Donna Gigliotti.",
            " The film is set in Big Stone Gap, Virginia."]],
        ["Adriana Trigiani", [
            "Adriana Trigiani is an Italian American best-selling author, film director, and entrepreneur based in Greenwich Village, New York City.",
            " She has published sixteen books."]],
        ["Big Stone Gap, Virginia", ["Big Stone Gap is a town in Wise County, Virginia, United States."]],
    ],
}

EXTRACTION = {
    "Big Stone Gap (film)": [
        {"head": "Big Stone Gap (film)", "head_type": "MISC", "relation": "P57", "tail": "Adriana Trigiani", "tail_type": "PER", "sentences": [0]},
        {"head": "Big Stone Gap (film)", "head_type": "MISC", "relation": "P162", "tail": "Donna Gigliotti", "tail_type": "PER", "sentences": [0]},
        {"head": "Big Stone Gap (film)", "head_type": "MISC", "relation": "P840", "tail": "Big Stone Gap, Virginia", "tail_type": "LOC", "sentences": [1]},
        {"head": "Big Stone Gap (film)", "relation": "P9999", "tail": "2014", "sentences": [0]},          # quan hệ ngoài schema → bị bỏ
    ],
    # cố ý KHÔNG trích cạnh nơi sống → agent phải đọc văn bản
    "Adriana Trigiani": [
        {"head": "Adriana Trigiani", "head_type": "PER", "relation": "P27", "tail": "United States", "tail_type": "LOC", "sentences": [0]},  # nghi ngờ: câu không nhắc "United States"
    ],
    "Big Stone Gap, Virginia": [
        {"head": "Big Stone Gap, Virginia", "head_type": "LOC", "relation": "P131", "tail": "Wise County", "tail_type": "LOC", "sentences": [0]},
    ],
}


class FakeLLM:
    def __init__(self, agent_scripts):
        self.agent_scripts = agent_scripts  # {câu hỏi: [bước...]}
        self.stats = {"calls": 0}

    def info(self):
        return {"model": "fake"}

    def chat(self, messages, tools=None, json_mode=False):
        self.stats["calls"] += 1
        if json_mode:  # trích xuất
            user = messages[-1]["content"]
            title = user.split("PARAGRAPH TITLE: ", 1)[1].split("\n", 1)[0]
            return {"content": "```json\n" + json.dumps({"triples": EXTRACTION[title]}) + "\n```", "tool_calls": []}
        question = messages[1]["content"].split("Question: ", 1)[1].split("\n", 1)[0]
        turn = sum(m["role"] == "assistant" for m in messages)
        step = self.agent_scripts[question][turn]
        if step is None:
            return {"content": "Greenwich Village, New York City", "tool_calls": []}
        name, args = step
        return {"content": None, "tool_calls": [{"id": f"c{turn}", "name": name, "arguments": json.dumps(args)}]}


def edge_id(graph, head, rel, tail):
    names = {n["id"]: n["name"] for n in graph["nodes"]}
    for e in graph["edges"]:
        if (names[e["head"]], e["relation"], names[e["tail"]]) == (head, rel, tail):
            return e["id"]
    raise AssertionError((head, rel, tail))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        write_json(tmp / "hotpot.json", [EXAMPLE])

        # ---- bước 1: dựng đồ thị ----
        s = build_graphs.main(["--hotpot", str(tmp / "hotpot.json"), "--n-bridge", "1", "--n-comparison", "0",
                               "--out", str(tmp / "interim")], llm=FakeLLM({}))
        g = read_json(tmp / "interim" / "graphs" / "q_bsg.json")
        log = read_json(tmp / "interim" / "graphs" / "q_bsg.log.json")
        assert s["total_edges"] == 5, s
        assert [d["reason"] for d in log["dropped"]] == ["relation_not_in_schema"]
        assert log["suspect"] == 1
        assert s["questions"][0]["sf_coverage"] == 1.0     # câu (Trigiani,0) chỉ sinh cạnh nghi ngờ P27 nhưng vẫn tính là có cạnh
        e_dir = edge_id(g, "Big Stone Gap (film)", "P57", "Adriana Trigiani")
        assert all(e["origin"] == "EXTRACTED" for e in g["edges"])
        print("Bước 1 OK:", s["questions"][0])

        # ---- bước 2: agent ----
        nodes = {n["name"]: n["id"] for n in g["nodes"]}
        script = [
            ("search_nodes", {"query": "Big Stone Gap"}),
            ("start_at", {"node": nodes["Big Stone Gap (film)"]}),
            ("follow_edge", {"edge_id": e_dir}),
            ("read_paragraph", {"paragraph": "Adriana Trigiani"}),
            ("add_edge", {"head": "Adriana Trigiani", "relation": "P551", "tail": "Greenwich Village",
                          "evidence_sentences": [{"paragraph": "Adriana Trigiani", "sentence": 0}]}),
            ("add_edge", {"head": "Big Stone Gap (film)", "relation": "P999", "tail": "Greenwich Village"}),
            ("answer", {"answer": "Greenwich Village, New York City"}),
            # bước cập nhật bộ nhớ
            ("add_edge", {"head": "Adriana Trigiani", "relation": "P800", "tail": "Big Stone Gap (film)",
                          "evidence_edges": [e_dir]}),
            None,  # DONE
        ]
        summ = run_agent.main(["--run-name", "t", "--interim", str(tmp / "interim"),
                               "--out-root", str(tmp / "runs"), "--followups", str(tmp / "none.json")],
                              llm=FakeLLM({EXAMPLE["question"]: script}))
        run = tmp / "runs" / "t"
        eps = read_jsonl(run / "episodes.jsonl")
        gates = read_jsonl(run / "gates.jsonl")
        after = read_json(run / "graphs_after" / "q_bsg.json")
        ep = eps[0]
        assert ep["em"] == 1.0 and ep["follows"] == 1
        assert ep["answer_grounded"] is True and summ["correct_but_ungrounded"] == 0
        assert ep["paragraphs_read"] == ["Adriana Trigiani"]
        assert [w["status"] for w in ep["writes"]] == ["added", "invalid_relation", "added"]
        assert [w["phase"] for w in ep["writes"]] == ["answer", "answer", "memory"]
        assert ep["writes"][0]["origin"] == "AGENT_TEXT" and ep["writes"][0]["new_tail_node"] is True
        assert ep["writes"][2]["origin"] == "AGENT_DERIVED"
        assert [r["kind"] for r in gates] == ["traversal", "traversal", "construction", "construction"]
        assert gates[0]["action"]["type"] == "start" and gates[0]["action"]["start_in_question"] is True
        assert gates[1]["action"]["to"] == "Adriana Trigiani" and [p["type"] for p in gates[1]["path"]] == ["start"]
        assert gates[2]["evidence"][0]["text"].startswith("Adriana Trigiani is")
        assert gates[3]["phase"] == "memory" and gates[3]["evidence"][0]["type"] == "edge"
        assert ep["starts"] == 1 and ep["starts_not_in_question"] == 0
        new = [e for e in after["edges"] if e["origin"] == "AGENT_TEXT"]
        assert len(new) == 1 and new[0]["provenance"] == [["Adriana Trigiani", 0]]
        assert summ["writes_by_origin"] == {"AGENT_TEXT": 1, "AGENT_DERIVED": 1}
        assert summ["writes_by_phase"] == {"answer": 2, "memory": 1}
        assert ep["path_sf_coverage"] == 0.5
        print("Bước 2 OK:", summ)

        # ---- câu hỏi tiếp theo dùng cạnh agent vừa ghi ----
        write_json(tmp / "fu.json", {"q_bsg": [{"question": "Where is Adriana Trigiani based?", "answer": "Greenwich Village"}]})
        g2 = read_json(run / "graphs_after" / "q_bsg.json")
        n2 = {n["name"]: n["id"] for n in g2["nodes"]}
        e_new = edge_id(g2, "Adriana Trigiani", "P551", "Greenwich Village")
        script2 = [
            ("start_at", {"node": n2["Adriana Trigiani"]}),
            ("follow_edge", {"edge_id": e_new}),
            None,  # trả lời bằng văn bản, không gọi công cụ
            None,  # bước cập nhật bộ nhớ: DONE
        ]
        run_agent.main(["--run-name", "t2", "--interim", str(tmp / "interim"), "--out-root", str(tmp / "runs"),
                        "--followups", str(tmp / "fu.json")],
                       llm=FakeLLM({EXAMPLE["question"]: script, "Where is Adriana Trigiani based?": script2}))
        eps2 = read_jsonl(tmp / "runs" / "t2" / "episodes.jsonl")
        assert eps2[1]["episode_id"] == "q_bsg:followup0"
        assert eps2[1]["agent_edges_used"] == [e_new], eps2[1]["agent_edges_used"]
        print("Câu hỏi tiếp theo OK: dùng cạnh do agent ghi", eps2[1]["agent_edges_used"])
    check_tools()
    print("TẤT CẢ OK")


def check_tools():
    """Quy tắc công cụ (D10, D11): get_edges chỉ nút hiện tại; chỉ đọc đoạn đã tới được; giới hạn 2 đoạn; ghi nhận nhảy."""
    from dcg.agent import MAX_READS, Episode
    from dcg.common import load_relations
    from dcg.gates import AcceptAllGates
    from dcg.graph import KG

    kg = KG("q_bsg")
    f, a = kg.add_node("Big Stone Gap (film)", is_title=True), kg.add_node("Adriana Trigiani", is_title=True)
    v = kg.add_node("Big Stone Gap, Virginia", is_title=True)
    e = kg.add_edge(f, "P57", a, [["Big Stone Gap (film)", 0]])[0]
    ep = Episode(kg, EXAMPLE, EXAMPLE["question"], None, AcceptAllGates(), load_relations(), "t", "q_bsg:main")
    titles = [t for t, _ in EXAMPLE["context"]]
    assert MAX_READS == 2
    assert "error" in ep.t_get_edges()                                   # chưa xuất phát
    assert "not reached" in ep.t_read_paragraph(titles[0])["error"]      # chưa tới được
    r = ep.t_start_at(f)
    assert r["edges"][0]["source_paragraphs"] == ["Big Stone Gap (film)"]
    assert ep.path[0]["start_in_question"] is True
    assert "only list edges of the current node" in ep.t_get_edges(a)  # không nhìn nút khác
    assert "not reached" in ep.t_read_paragraph(titles[1])["error"]      # đoạn Trigiani chưa tới
    assert "sentences" in ep.t_read_paragraph(titles[0])
    ep.t_follow_edge(e)                                                   # tới Trigiani → đọc được đoạn đó
    assert "sentences" in ep.t_read_paragraph(titles[1])
    assert "sentences" in ep.t_read_paragraph(titles[0])                 # đọc lại: không tính
    ep.t_start_at(v)                                                      # nhảy tới nút không có trong câu hỏi
    assert ep.path[-1]["start_in_question"] is False
    assert "limit" in ep.t_read_paragraph(titles[2])["error"]            # đoạn thứ 3: quá giới hạn
    assert ep.paragraphs_read == titles[:2] and ep.reads_refused == 3
    assert ep.summary()["starts_not_in_question"] == 1
    print("Quy tắc công cụ OK")


if __name__ == "__main__":
    main()
