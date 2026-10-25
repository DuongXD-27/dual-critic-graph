"""Bước 2: chạy agent trên các đồ thị đã dựng, ghi log đầy đủ.

Chạy (Windows):
  .venv\\Scripts\\python scripts\\run_agent.py --run-name baseline                    # mỗi câu một đồ thị (bản thử)
  .venv\\Scripts\\python scripts\\run_agent.py --run-name shared-v1 --graph data\\interim\\shared\\graph.json
      → đồ thị chung (D12): các câu chạy LẦN LƯỢT trên cùng một đồ thị, phép ghi của câu trước được giữ cho câu sau
Tuỳ chọn:
  --gates accept_all       bộ cổng (hiện chỉ có baseline luôn ACCEPT)
  --limit N                chỉ chạy N câu đầu
  --followups PATH         mặc định data/manual/followups.json (nếu có): câu hỏi tiếp theo chạy trên đồ thị đã bị sửa

Đầu ra trong data/runs/<run-name>/ :
  run.json           cấu hình: model, prompt version, cổng, thời điểm
  episodes.jsonl     một dòng / lượt trả lời: đường đi, đoạn đã đọc, phép ghi, câu trả lời, EM/F1, toàn bộ lời gọi công cụ
  gates.jsonl        mọi lần gọi cổng, đúng định dạng mẫu benchmark (gold = null, gán sau)
  graphs_after/      đồ thị sau khi agent ghi
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg import agent as agent_mod  # noqa: E402
from dcg.common import DATA, append_jsonl, load_relations, read_json, write_json  # noqa: E402
from dcg.gates import GATES  # noqa: E402
from dcg.graph import KG  # noqa: E402
from dcg.metrics import contains_gold, exact_match, f1, normalize_answer  # noqa: E402


def answer_grounded(ep, answer):
    """Câu trả lời có xuất hiện trong thông tin agent đã thực sự xem không:
    tên các nút trên đường đi + tên hai đầu các cạnh đã thấy + nội dung các đoạn đã đọc. yes/no → None (không kiểm tra được kiểu này).
    False + trả lời đúng ⇒ nhiều khả năng agent trả lời bằng kiến thức nền."""
    a = normalize_answer(answer)
    if not a or a in ("yes", "no"):
        return None
    seen = [s.get("to", "") for s in ep.path] + [s.get("name", "") for s in ep.path]
    seen += [s for t in ep.paragraphs_read for s in ep.paragraphs.get(t, [])]
    # tên hai đầu của mọi cạnh đã hiện ra cho agent (start_at / follow_edge / get_edges)
    for ev in ep.events:
        r = ev.get("result")
        edges = r.get("edges", []) if isinstance(r, dict) else (r if isinstance(r, list) else [])
        seen += [x.get(k, "") for x in edges if isinstance(x, dict) for k in ("head", "tail")]
    # so theo TỪ (2026-10-24): câu trả lời ghép từ nhiều thứ đã thấy ("Hey Pa! ..." + "1966") vẫn là có căn cứ;
    # từ nào chưa từng thấy (vd. "Bahamas" trong "Great Exuma, Bahamas") → False, liệt kê trong answer_unseen_words
    seen_words = {w for x in seen if x for w in normalize_answer(x).split()}
    ep.answer_unseen_words = [w for w in a.split() if w not in seen_words]
    return not ep.answer_unseen_words


def run_episode(kg, ex, question, gold, llm, gates, rels, run_id, episode_id, out, paragraphs=None):
    ep = agent_mod.Episode(kg, ex, question, llm, gates, rels, run_id, episode_id, paragraphs=paragraphs)
    res = ep.run()
    res["gold_answer"] = gold
    res["answer_grounded"] = answer_grounded(ep, res["answer"])
    res["answer_unseen_words"] = getattr(ep, "answer_unseen_words", [])
    res["em"] = exact_match(res["answer"], gold) if gold is not None else None
    res["f1"] = f1(res["answer"], gold) if gold is not None else None
    res["gold_in_answer"] = contains_gold(res["answer"], gold) if gold is not None else None
    if episode_id.endswith(":main"):
        sf = {tuple(x) for x in ex["supporting_facts"]}
        res["supporting_facts"] = sorted(sf)
        res["path_sf_coverage"] = round(len(sf & set(res["path_provenance"])) / len(sf), 3) if sf else None
    append_jsonl(out / "episodes.jsonl", res)
    for r in ep.gate_records:
        append_jsonl(out / "gates.jsonl", r)
    return res


def main(argv=None, llm=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--gates", default="accept_all", choices=sorted(GATES))
    ap.add_argument("--interim", default=str(DATA / "interim"))
    ap.add_argument("--followups", default=str(DATA / "manual" / "followups.json"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out-root", default=str(DATA / "runs"))
    ap.add_argument("--graph", help="đồ thị chung (D12); questions.json và corpus.json lấy cùng thư mục")
    args = ap.parse_args(argv)

    out = Path(args.out_root) / args.run_name
    if (out / "episodes.jsonl").exists():
        raise SystemExit(f"{out} đã có kết quả. Đặt --run-name khác hoặc xoá thư mục đó.")
    interim = Path(args.interim)
    shared = None
    if args.graph:
        gdir = Path(args.graph).parent
        questions = read_json(gdir / "questions.json")[: args.limit]
        shared = {"kg": KG.from_json(read_json(args.graph)), "corpus": read_json(gdir / "corpus.json")}
        followups = {}
    else:
        questions = read_json(interim / "questions.json")[: args.limit]
        followups = read_json(args.followups) if Path(args.followups).exists() else {}
    rels = load_relations()
    gates = GATES[args.gates]()
    if llm is None:
        from dcg.llm import LLM
        llm = LLM()

    write_json(out / "run.json", {
        "run_id": args.run_name, "started": datetime.now().isoformat(timespec="seconds"),
        "llm": getattr(llm, "info", lambda: {})(), "agent_prompt_version": agent_mod.PROMPT_VERSION,
        "max_follows": agent_mod.MAX_FOLLOWS, "max_tool_calls": agent_mod.MAX_TOOL_CALLS,
        "max_reads": agent_mod.MAX_READS,
        "gates": gates.name, "n_questions": len(questions), "followups_file": args.followups if followups else None,
        "mode": "shared" if shared else "per_question", "graph": args.graph})

    rows = []
    for k, ex in enumerate(questions, 1):
        qid = ex["_id"]
        kg = shared["kg"] if shared else KG.from_json(read_json(interim / "graphs" / f"{qid}.json"))
        print(f"[{k}/{len(questions)}] {ex['question'][:80]}")
        r = run_episode(kg, ex, ex["question"], ex["answer"], llm, gates, rels, args.run_name, f"{qid}:main", out,
                        paragraphs=shared["corpus"] if shared else None)
        reused = [d for d in r["agent_edges_used_detail"] if d["created_by"] != r["episode_id"]]
        print(f"    → {r['answer']!r}  (đúng: {ex['answer']!r}, F1={r['f1']:.2f}, ghi {len(r['writes'])} cạnh"
              + (f", ĐI QUA {len(reused)} cạnh do câu trước ghi" if reused else "") + ")")
        rows.append(r)
        if shared:
            if k % 20 == 0:
                write_json(out / "graph_after.json", kg.to_json())
            continue
        for j, fu in enumerate(followups.get(qid, [])):
            r2 = run_episode(kg, ex, fu["question"], fu.get("answer"), llm, gates, rels, args.run_name,
                             f"{qid}:followup{j}", out)
            print(f"    follow-up → {r2['answer']!r}  (dùng {len(r2['agent_edges_used'])} cạnh do agent ghi)")
        write_json(out / "graphs_after" / f"{qid}.json", kg.to_json())

    if shared:
        write_json(out / "graph_after.json", shared["kg"].to_json())
    n = len(rows)
    writes = [w for r in rows for w in r["writes"]]
    reuse = [(r["episode_id"], d) for r in rows for d in r["agent_edges_used_detail"]
             if d["created_by"] != r["episode_id"]]
    summary = {
        "n": n,
        "em": round(sum(r["em"] for r in rows) / n, 3) if n else None,
        "f1": round(sum(r["f1"] for r in rows) / n, 3) if n else None,
        "gold_in_answer": sum(bool(r.get("gold_in_answer")) for r in rows),
        "mean_follows": round(sum(r["follows"] for r in rows) / n, 2) if n else None,
        "correct_but_ungrounded": sum(r["f1"] >= 0.8 and r["answer_grounded"] is False for r in rows),
        "starts_total": sum(r["starts"] for r in rows),
        "starts_not_in_question": sum(r["starts_not_in_question"] for r in rows),
        "starts_ungrounded": sum(r["starts_ungrounded"] for r in rows),
        "starts_refused": sum(r.get("starts_refused", 0) for r in rows),
        "episodes_following_own_write": sum(r.get("follows_on_own_edges", 0) > 0 for r in rows),
        "episodes_reading_text": sum(bool(r["paragraphs_read"]) for r in rows),
        "mean_paragraphs_read": round(sum(len(r["paragraphs_read"]) for r in rows) / n, 2) if n else None,
        "episodes_hit_read_limit": sum(r["reads_refused"] > 0 for r in rows),
        "writes_total": len(writes),
        "writes_by_origin": {o: sum(w.get("origin") == o for w in writes) for o in ("AGENT_TEXT", "AGENT_DERIVED")},
        "writes_by_phase": {p: sum(w.get("phase") == p for w in writes) for p in ("answer", "memory")},
        "writes_invalid_relation": sum(w["status"] == "invalid_relation" for w in writes),
        "episodes_using_earlier_agent_edges": len({e for e, _ in reuse}),
        "earlier_agent_edges_reused": len({d["edge_id"] for _, d in reuse}),
        "llm_stats": getattr(llm, "stats", None),
    }
    run_meta = read_json(out / "run.json")
    run_meta.update({"finished": datetime.now().isoformat(timespec="seconds"), "summary": summary})
    write_json(out / "run.json", run_meta)
    print("Tổng kết:", summary)
    return summary


if __name__ == "__main__":
    main()
