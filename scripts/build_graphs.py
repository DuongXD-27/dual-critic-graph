"""Bước 1: chọn câu hỏi HotpotQA và dựng đồ thị cho từng câu.

Chạy (Windows, trong thư mục repo):
  .venv\\Scripts\\python scripts\\build_graphs.py
Tuỳ chọn:
  --hotpot PATH        mặc định data/raw/hotpotqa/hotpot_dev_distractor_v1.json
  --n-bridge 16 --n-comparison 4 --seed 0
  --force              dựng lại cả đồ thị đã có

Đầu ra:
  data/interim/questions.json            các câu đã chọn (giữ nguyên định dạng HotpotQA)
  data/interim/graphs/<qid>.json         đồ thị
  data/interim/graphs/<qid>.log.json     log trích xuất (cạnh bị bỏ, lý do, cạnh nghi ngờ)
  data/interim/graphs/_summary.json      thống kê
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.common import DATA, load_relations, read_json, write_json  # noqa: E402
from dcg.extract import PROMPT_VERSION, build_graph, sf_coverage  # noqa: E402


def select(data, n_bridge, n_comparison, seed):
    rng = random.Random(seed)
    bridge = [x for x in data if x["type"] == "bridge"]
    comp = [x for x in data if x["type"] == "comparison"]
    return rng.sample(bridge, n_bridge) + rng.sample(comp, n_comparison)


def main(argv=None, llm=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hotpot", default=str(DATA / "raw" / "hotpotqa" / "hotpot_dev_distractor_v1.json"))
    ap.add_argument("--n-bridge", type=int, default=16)
    ap.add_argument("--n-comparison", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(DATA / "interim"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    out = Path(args.out)
    qpath = out / "questions.json"
    if qpath.exists() and not args.force:
        questions = read_json(qpath)
        print(f"Dùng lại {len(questions)} câu trong {qpath}")
    else:
        hotpot = Path(args.hotpot)
        if not hotpot.exists():
            raise SystemExit(f"Không thấy {hotpot}. Tải hotpot_dev_distractor_v1.json từ trang HotpotQA và đặt vào đó.")
        questions = select(read_json(hotpot), args.n_bridge, args.n_comparison, args.seed)
        write_json(qpath, questions)
        print(f"Đã chọn {len(questions)} câu → {qpath}")

    rels = load_relations()
    if llm is None:
        from dcg.llm import LLM
        llm = LLM()

    gdir = out / "graphs"
    rows = []
    for k, ex in enumerate(questions, 1):
        gpath = gdir / f"{ex['_id']}.json"
        if gpath.exists() and not args.force:
            from dcg.graph import KG
            kg, log = KG.from_json(read_json(gpath)), read_json(gdir / f"{ex['_id']}.log.json")
        else:
            print(f"[{k}/{len(questions)}] {ex['_id']}  {ex['question'][:70]}")
            kg, log = build_graph(ex, llm, rels)
            write_json(gpath, kg.to_json())
            write_json(gdir / f"{ex['_id']}.log.json", log)
        rows.append({"qid": ex["_id"], "type": ex["type"], "nodes": len(kg.nodes), "edges": len(kg.edges),
                     "raw_triples": log["raw_triples"], "dropped": len(log["dropped"]), "suspect": log["suspect"],
                     "parse_errors": len(log["parse_errors"]),
                     "sf_coverage": round(sf_coverage(kg, ex["supporting_facts"]), 3)})

    summary = {"prompt_version": PROMPT_VERSION, "llm": getattr(llm, "info", lambda: {})(),
               "questions": rows,
               "mean_sf_coverage": round(sum(r["sf_coverage"] for r in rows) / len(rows), 3),
               "total_edges": sum(r["edges"] for r in rows),
               "total_dropped": sum(r["dropped"] for r in rows),
               "total_suspect": sum(r["suspect"] for r in rows)}
    write_json(gdir / "_summary.json", summary)
    print(f"Xong. Cạnh: {summary['total_edges']}, bị bỏ: {summary['total_dropped']}, "
          f"nghi ngờ: {summary['total_suspect']}, độ phủ câu bằng chứng TB: {summary['mean_sf_coverage']}")
    return summary


if __name__ == "__main__":
    main()
