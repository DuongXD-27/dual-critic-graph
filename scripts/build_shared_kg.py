"""Dựng MỘT đồ thị chung cho nhiều câu hỏi HotpotQA (DECISIONS D12).

Chạy (Windows):
  .venv\\Scripts\\python scripts\\build_shared_kg.py
Tuỳ chọn:
  --n 200 --seed 0          số câu và hạt giống
  --select cluster|random   cluster (mặc định): xen kẽ 1 câu ngẫu nhiên với 1 câu dùng chung đoạn văn với tập đã chọn
  --select-only             chỉ chọn câu + gộp kho đoạn văn, chưa gọi LLM (xem thống kê trước)
  --force                   chọn lại câu và dựng lại đồ thị

Đầu ra trong data/interim/shared/ :
  questions.json    các câu đã chọn, theo đúng THỨ TỰ agent sẽ trả lời
  corpus.json       kho đoạn văn {tiêu đề: [câu]} = hợp các đoạn của mọi câu, bỏ trùng theo tiêu đề
  graph.json        đồ thị chung
  extract_log.json  log trích xuất (bộ ba bị bỏ, nghi ngờ, thống kê liên kết thực thể, tên mơ hồ)
  summary.json      thống kê: kho, đồ thị, mức dùng chung, độ phủ câu bằng chứng
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.common import DATA, load_relations, read_json, write_json  # noqa: E402
from dcg.extract import SHARED_PROMPT_VERSION, build_shared_graph, sf_coverage  # noqa: E402


def sf_titles(q):
    return {t for t, _ in q["supporting_facts"]}


def select_questions(data, n, seed, mode):
    rng = random.Random(seed)
    order = list(range(len(data)))
    rng.shuffle(order)
    if mode == "random":
        return [data[i] for i in order[:n]]
    # cluster: lượt lẻ chọn câu có đoạn bằng chứng nằm trong kho đã chọn (nhiều nhất), lượt chẵn chọn ngẫu nhiên
    by_title = defaultdict(list)
    for i, q in enumerate(data):
        for t in sf_titles(q):
            by_title[t].append(i)
    chosen, chosen_set, corpus_titles = [], set(), set()
    pos = 0
    while len(chosen) < n:
        pick = None
        if len(chosen) % 2 == 1:
            cand = Counter(j for t in corpus_titles for j in by_title.get(t, ()) if j not in chosen_set)
            if cand:
                best = max(cand.values())
                pick = min(j for j, c in cand.items() if c == best)  # tất định
        if pick is None:
            while order[pos] in chosen_set:
                pos += 1
            pick = order[pos]
        chosen.append(pick)
        chosen_set.add(pick)
        corpus_titles.update(t for t, _ in data[pick]["context"])
    return [data[i] for i in chosen]


def build_corpus(questions):
    corpus, conflicts = {}, []
    for q in questions:
        for t, sents in q["context"]:
            if t in corpus and corpus[t] != sents:
                conflicts.append({"title": t, "qid": q["_id"]})
                continue
            corpus.setdefault(t, sents)
    return corpus, conflicts


def overlap_stats(questions, corpus):
    use = Counter(t for q in questions for t, _ in q["context"])
    return {
        "questions": len(questions),
        "types": dict(Counter(q["type"] for q in questions)),
        "paragraphs_total": sum(use.values()),
        "paragraphs_unique": len(corpus),
        "titles_shared_by_2plus_questions": sum(c > 1 for c in use.values()),
        "questions_whose_evidence_paragraph_is_in_another_question": sum(
            any(use[t] > 1 for t in sf_titles(q)) for q in questions),
    }


def main(argv=None, llm=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hotpot", default=str(DATA / "raw" / "hotpotqa" / "hotpot_dev_distractor_v1.json"))
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--select", choices=["cluster", "random"], default="cluster")
    ap.add_argument("--out", default=str(DATA / "interim" / "shared"))
    ap.add_argument("--select-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)

    if (out / "questions.json").exists() and not args.force:
        questions = read_json(out / "questions.json")
        print(f"Dùng lại {len(questions)} câu trong {out / 'questions.json'}")
    else:
        hotpot = Path(args.hotpot)
        if not hotpot.exists():
            raise SystemExit(f"Không thấy {hotpot}.")
        questions = select_questions(read_json(hotpot), args.n, args.seed, args.select)
        write_json(out / "questions.json", questions)
    corpus, conflicts = build_corpus(questions)
    write_json(out / "corpus.json", corpus)
    stats = {**overlap_stats(questions, corpus), "selection": args.select, "seed": args.seed,
             "title_conflicts": conflicts}
    print("Kho đoạn văn:", {k: v for k, v in stats.items() if k != "title_conflicts"},
          f"| xung đột tiêu đề: {len(conflicts)}")
    if args.select_only:
        write_json(out / "summary.json", {"corpus": stats})
        return stats

    if (out / "graph.json").exists() and not args.force:
        raise SystemExit(f"{out / 'graph.json'} đã có. Dùng --force để dựng lại (phản hồi đã có lấy từ cache).")
    rels = load_relations()
    if llm is None:
        from dcg.llm import LLM
        llm = LLM()

    def progress(k, total, title):
        if k == 1 or k % 25 == 0 or k == total:
            print(f"  [{k}/{total}] {title[:60]}")

    kg, log = build_shared_graph(corpus, llm, rels, progress=progress)
    write_json(out / "graph.json", kg.to_json())
    write_json(out / "extract_log.json", log)

    covered = {tuple(p) for e in kg.edges.values() for p in e["provenance"]}
    cov = [sf_coverage(kg, q["supporting_facts"], covered) for q in questions]
    degrees = sorted((len(kg.incident(n)) for n in kg.nodes), reverse=True)
    summary = {
        "corpus": stats,
        "prompt_version": SHARED_PROMPT_VERSION, "llm": getattr(llm, "info", lambda: {})(),
        "nodes": len(kg.nodes), "edges": len(kg.edges),
        "raw_triples": log["raw_triples"], "dropped": len(log["dropped"]), "suspect": log["suspect"],
        "parse_errors": len(log["parse_errors"]), "linking": log["linking"],
        "mean_sf_coverage": round(sum(cov) / len(cov), 3),
        "top10_node_degree": degrees[:10],
        "top10_hubs": [kg.name(n) for n in sorted(kg.nodes, key=lambda n: -len(kg.incident(n)))[:10]],
    }
    write_json(out / "summary.json", summary)
    print("Xong:", {k: v for k, v in summary.items() if k not in ("corpus", "llm")})
    return summary


if __name__ == "__main__":
    main()
