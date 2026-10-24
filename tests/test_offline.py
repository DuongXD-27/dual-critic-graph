"""Kiểm thử toàn bộ pipeline không cần mạng, dùng LLM giả trên ví dụ Big Stone Gap.

  python tests/test_offline.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_graphs  # noqa: E402
import build_shared_kg  # noqa: E402
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
    def __init__(self, agent_scripts, drop_in_batch=(), broken=()):
        self.agent_scripts = agent_scripts  # {câu hỏi: [bước...]}
        self.drop_in_batch = set(drop_in_batch)  # giả lập model bỏ sót đoạn khi gộp
        self.broken = set(broken)                # giả lập JSON hỏng ở lần gọi đầu
        self.stats = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def info(self):
        return {"model": "fake"}

    def chat(self, messages, tools=None, json_mode=False, session_id=None):
        self.stats["calls"] += 1
        if json_mode:  # trích xuất
            user = messages[1]["content"]
            batch = re.findall(r"^PARAGRAPH \d+ — TITLE: (.*)$", user, flags=re.M)
            if batch:
                paras = [{"title": t, "triples": EXTRACTION[t]} for t in batch if t not in self.drop_in_batch]
                return {"content": json.dumps({"paragraphs": paras}), "tool_calls": []}
            title = user.split("PARAGRAPH TITLE: ", 1)[1].split("\n", 1)[0]
            if title in self.broken and len(messages) == 2:
                return {"content": "{not json", "tool_calls": []}
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
        e_own = f"e{len(g['edges'])}"                                    # cạnh agent sắp ghi ở ngõ cụt
        script = [
            ("search_nodes", {"query": "Big Stone Gap"}),
            ("start_at", {"node": nodes["Big Stone Gap, Virginia"]}),    # không có trong câu hỏi → bị từ chối (D14)
            ("start_at", {"node": nodes["Big Stone Gap (film)"]}),
            ("follow_edge", {"edge_id": e_dir}),
            ("read_paragraph", {"paragraph": "Adriana Trigiani"}),       # ngõ cụt: thiếu cạnh nơi sống
            ("add_edge", {"head": "Adriana Trigiani", "relation": "P551", "tail": "Greenwich Village",
                          "evidence_sentences": [{"paragraph": "Adriana Trigiani", "sentence": 0}]}),
            ("follow_edge", {"edge_id": e_own}),                         # ghi rồi đi tiếp theo cạnh vừa ghi
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
        assert ep["em"] == 1.0 and ep["follows"] == 2
        assert ep["starts_refused"] == 1 and ep["follows_on_own_edges"] == 1
        assert ep["path"][-1]["to"] == "Greenwich Village" and ep["path"][-1]["origin"] == "AGENT_TEXT"
        assert summ["starts_refused"] == 1 and summ["episodes_following_own_write"] == 1
        assert summ["episodes_using_earlier_agent_edges"] == 0        # cạnh tự ghi trong cùng lượt không tính là "dùng lại"
        assert ep["answer_grounded"] is True and summ["correct_but_ungrounded"] == 0
        assert ep["paragraphs_read"] == ["Adriana Trigiani"]
        assert [w["status"] for w in ep["writes"]] == ["added", "invalid_relation", "added"]
        assert [w["phase"] for w in ep["writes"]] == ["answer", "answer", "memory"]
        assert ep["writes"][0]["origin"] == "AGENT_TEXT" and ep["writes"][0]["new_tail_node"] is True
        assert ep["writes"][2]["origin"] == "AGENT_DERIVED"
        assert [r["kind"] for r in gates] == ["traversal", "traversal", "construction", "traversal", "construction"]
        assert gates[0]["action"]["type"] == "start" and gates[0]["action"]["start_in_question"] is True
        assert gates[1]["action"]["to"] == "Adriana Trigiani" and [p["type"] for p in gates[1]["path"]] == ["start"]
        assert gates[2]["evidence"][0]["text"].startswith("Adriana Trigiani is")
        assert gates[3]["action_edge"]["origin"] == "AGENT_TEXT"
        assert gates[4]["phase"] == "memory" and gates[4]["evidence"][0]["type"] == "edge"
        assert ep["starts"] == 1 and ep["starts_not_in_question"] == 0
        new = [e for e in after["edges"] if e["origin"] == "AGENT_TEXT"]
        assert len(new) == 1 and new[0]["provenance"] == [["Adriana Trigiani", 0]]
        assert summ["writes_by_origin"] == {"AGENT_TEXT": 1, "AGENT_DERIVED": 1}
        assert summ["writes_by_phase"] == {"answer": 2, "memory": 1}
        assert ep["path_sf_coverage"] == 1.0
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
    check_shared()
    check_batch()
    check_header_safe()
    print("TẤT CẢ OK")


def check_tools():
    """Quy tắc công cụ (D10, D11, D14): chỉ xuất phát ở thực thể trong câu hỏi; get_edges chỉ nút hiện tại;
    chỉ đọc đoạn đã tới được; giới hạn 2 đoạn; nối tên khi ghi; chặn cạnh tự nối."""
    from dcg.agent import MAX_READS, Episode, in_question
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
    assert "only accepts entities named in the question" in ep.t_start_at(a)["error"]   # D14: không nhảy cóc
    assert "only accepts" in ep.t_start_at(v)["error"] and ep.current is None
    r = ep.t_start_at(f)
    assert r["edges"][0]["source_paragraphs"] == ["Big Stone Gap (film)"]
    assert ep.path[0]["start_in_question"] is True and ep.path[0]["start_grounded_by"] == "question"
    assert "only list edges of the current node" in ep.t_get_edges(a)  # không nhìn nút khác
    assert "not reached" in ep.t_read_paragraph(titles[1])["error"]      # đoạn Trigiani chưa tới
    assert "sentences" in ep.t_read_paragraph(titles[0])
    ep.t_follow_edge(e)                                                   # tới Trigiani → đọc được đoạn đó
    assert "sentences" in ep.t_read_paragraph(titles[1])
    assert "sentences" in ep.t_read_paragraph(titles[0])                 # đọc lại: không tính
    assert ep._jump_grounding("Big Stone Gap, Virginia") == "text_read"   # đoạn phim đã đọc nhắc tên này
    assert ep._jump_grounding("Kyle Schickner") is None
    ep.reachable.add(titles[2])
    assert "limit" in ep.t_read_paragraph(titles[2])["error"]            # đoạn thứ 3: quá giới hạn
    assert ep.paragraphs_read == titles[:2] and ep.reads_refused == 3
    sm = ep.summary()
    assert sm["starts"] == 1 and sm["starts_refused"] == 2 and sm["starts_not_in_question"] == 0

    # ghi ở ngõ cụt: tên được nối với nút có sẵn; cạnh tự nối bị chặn; kết quả gợi ý follow_edge
    r = ep.t_add_edge("adriana trigiani", "P551", "Greenwich Village",
                      evidence_sentences=[{"paragraph": "Adriana Trigiani", "sentence": 0}])
    assert r["head"] == "Adriana Trigiani" and r["next"] == f"you can now follow_edge {r['edge_id']}"
    assert "same entity" in ep.t_add_edge("Adriana Trigiani", "P57", "adriana trigiani")
    assert ep.writes[-1]["status"] == "self_loop"
    ep2 = Episode(KG("x"), EXAMPLE, "Which club did Claudio López join in 1998?", None, AcceptAllGates(),
                  load_relations(), "t", "x", paragraphs={"Claudio López (footballer)": ["."], "Valencia CF": ["."],
                                                          "Mercury (planet)": ["."], "Mercury (element)": ["."]})
    assert ep2._resolve("Claudio López") == "Claudio López (footballer)"
    assert ep2._resolve("Mercury") == "Mercury"                           # mơ hồ → giữ nút riêng
    assert ep2._resolve("Valencia CF") == "Valencia CF"

    # so khớp tên với câu hỏi
    assert in_question("Thomas Boutflower Bennett (cricketer)", "Which team did Thomas Boutflower Bennet play for?")
    assert not in_question("Pablo Aimar", "Which player joined Valencia in 1998?")
    assert not in_question("Big Stone Gap, Virginia", EXAMPLE["question"])
    assert in_question("Big Stone Gap (film)", EXAMPLE["question"])
    assert not in_question("US", "Which famous musician was born first?")   # tên ngắn: chỉ khớp nguyên từ
    print("Quy tắc công cụ OK")


Q2 = {
    "_id": "q_at", "question": "Where is Adriana Trigiani based?", "answer": "Greenwich Village",
    "type": "bridge", "level": "easy", "supporting_facts": [["Adriana Trigiani", 0]],
    "context": [
        EXAMPLE["context"][1],  # cùng đoạn "Adriana Trigiani" với câu 1 → dùng chung trong đồ thị chung
        ["Strange Fruit (film)", ["Strange Fruit is a 2004 film directed by Kyle Schickner."]],
        ["Strange Fruit (song)", ["\"Strange Fruit\" is a song recorded by Billie Holiday in 1939."]],
        ["Billie Holiday", ["Billie Holiday was an American jazz singer known for Strange Fruit."]],
    ],
}
EXTRACTION.update({
    "Strange Fruit (film)": [{"head": "Strange Fruit (film)", "relation": "P57", "tail": "Kyle Schickner", "sentences": [0]}],
    "Strange Fruit (song)": [{"head": "Strange Fruit", "relation": "P175", "tail": "Billie Holiday", "sentences": [0]}],
    # "Strange Fruit" từ đoạn khác khớp 2 tiêu đề (film, song) → mơ hồ, giữ nút riêng
    "Billie Holiday": [{"head": "Billie Holiday", "relation": "P800", "tail": "Strange Fruit", "sentences": [0]}],
})


def check_shared():
    """Đồ thị chung (D12): gộp kho theo tiêu đề, liên kết tên→tiêu đề, câu sau đi qua cạnh câu trước ghi."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        sdir = tmp / "shared"
        write_json(sdir / "questions.json", [EXAMPLE, Q2])          # thứ tự trả lời cố định
        summ = build_shared_kg.main(["--out", str(sdir)], llm=FakeLLM({}))
        c = summ["corpus"]
        assert c["paragraphs_total"] == 7 and c["paragraphs_unique"] == 6, c
        assert c["questions_whose_evidence_paragraph_is_in_another_question"] == 2
        assert summ["linking"]["ambiguous"] == 1, summ["linking"]
        assert summ["linking"]["current_title"] >= 1      # "Strange Fruit" trong đoạn của chính nó → (song)
        g = read_json(sdir / "graph.json")
        names = {n["name"] for n in g["nodes"]}
        assert {"Strange Fruit", "Strange Fruit (song)", "Strange Fruit (film)"} <= names
        assert edge_id(g, "Strange Fruit (song)", "P175", "Billie Holiday")
        assert edge_id(g, "Billie Holiday", "P800", "Strange Fruit")    # nút mơ hồ, không gán bừa
        nodes = {n["name"]: n["id"] for n in g["nodes"]}
        e_dir = edge_id(g, "Big Stone Gap (film)", "P57", "Adriana Trigiani")
        e_new = f"e{len(g['edges'])}"                                   # id của cạnh đầu tiên agent sẽ ghi
        s1 = [
            ("search_nodes", {"query": "Big Stone Gap"}),
            ("start_at", {"node": nodes["Big Stone Gap (film)"]}),
            ("follow_edge", {"edge_id": e_dir}),
            ("read_paragraph", {"paragraph": "Adriana Trigiani"}),
            ("answer", {"answer": "Greenwich Village, New York City"}),
            ("add_edge", {"head": "Adriana Trigiani", "relation": "P551", "tail": "Greenwich Village",
                          "evidence_sentences": [{"paragraph": "Adriana Trigiani", "sentence": 0}]}),
            None,
        ]
        s2 = [
            ("search_nodes", {"query": "Adriana Trigiani"}),
            ("start_at", {"node": nodes["Adriana Trigiani"]}),
            ("follow_edge", {"edge_id": e_new}),
            ("answer", {"answer": "Greenwich Village"}),
            None,
        ]
        summ2 = run_agent.main(["--run-name", "s", "--graph", str(sdir / "graph.json"), "--out-root", str(tmp / "runs")],
                               llm=FakeLLM({EXAMPLE["question"]: s1, Q2["question"]: s2}))
        eps = read_jsonl(tmp / "runs" / "s" / "episodes.jsonl")
        assert eps[0]["writes"][0]["phase"] == "memory" and eps[0]["writes"][0]["edge_id"] == e_new
        assert eps[1]["agent_edges_used_detail"] == [{"edge_id": e_new, "origin": "AGENT_TEXT", "created_by": "q_bsg:main"}]
        assert summ2["episodes_using_earlier_agent_edges"] == 1 and summ2["earlier_agent_edges_reused"] == 1
        after = read_json(tmp / "runs" / "s" / "graph_after.json")
        assert len(after["edges"]) == len(g["edges"]) + 1
        assert read_json(tmp / "runs" / "s" / "run.json")["mode"] == "shared"
        print("Đồ thị chung OK")


def check_header_safe():
    """Mã phiên gửi trong header phải là ASCII (tiêu đề Wikipedia có thể chứa '–', 'é'...)."""
    from dcg.llm import header_safe
    assert header_safe("extract:Big Stone Gap (film)") == "extract:Big Stone Gap (film)"
    h = header_safe("extract:Rolling Papers – Wiz Khalifa")
    assert h.isascii() and h.startswith("s-") and h == header_safe("extract:Rolling Papers – Wiz Khalifa")
    assert header_safe("extract:Beyoncé") != h
    print("Mã phiên ASCII OK")


def check_batch():
    """D13: gộp đoạn + song song cho ra đúng đồ thị như từng đoạn; đoạn bị bỏ sót được gọi lại; thử nghiệm chạy được."""
    from dcg.common import load_relations
    from dcg.extract import build_shared_graph, make_batches

    corpus = {}
    for q in (EXAMPLE, Q2):
        for t, sents in q["context"]:
            corpus.setdefault(t, sents)
    rels = load_relations()

    def triples(kg):
        return sorted((kg.name(e["head"]), e["relation"], kg.name(e["tail"]), str(e["provenance"])) for e in kg.edges.values())

    batches = make_batches(corpus, 3, 1200, seed=0)
    assert sorted(t for b in batches for t in b) == sorted(corpus) and all(len(b) <= 3 for b in batches)
    kg1, log1 = build_shared_graph(corpus, FakeLLM({}), rels)
    kg2, log2 = build_shared_graph(corpus, FakeLLM({}, drop_in_batch={"Billie Holiday"}), rels,
                                   workers=3, per_call=3)
    assert triples(kg1) == triples(kg2)
    assert [n["name"] for n in kg1.nodes.values()] == [n["name"] for n in kg2.nodes.values()]  # cùng id
    assert log1["requests"] == 6 and log2["requests"] == len(batches) + 1
    assert log2["paragraph_skipped"] == ["Billie Holiday"] and log2["prompt_version"] == "extract-v3-batch"
    kg3, log3 = build_shared_graph(corpus, FakeLLM({}, broken={"Billie Holiday"}), rels, workers=2)
    assert triples(kg3) == triples(kg1) and log3["parse_retries"] == 1 and log3["requests"] == 7
    assert log3["parse_errors"] == []

    with tempfile.TemporaryDirectory() as tmp:
        sdir = Path(tmp) / "shared"
        write_json(sdir / "questions.json", [EXAMPLE, Q2])
        rep = build_shared_kg.main(["--out", str(sdir), "--pilot", "5", "--per-call", "3", "--workers", "2"],
                                   llm=FakeLLM({}))
        assert rep["paragraphs"] == 5 and rep["edge_jaccard"] == 1.0 and rep["decision"] == "per_call=3"
        assert (sdir / "pilot.json").exists() and not (sdir / "graph.json").exists()
    print("Gộp đoạn + song song + thử nghiệm OK")


if __name__ == "__main__":
    main()
