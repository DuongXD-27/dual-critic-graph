"""Dựng MỘT đồ thị chung cho nhiều câu hỏi HotpotQA (DECISIONS D12).

Chạy (Windows):
  .venv\\Scripts\\python scripts\\build_shared_kg.py
Tuỳ chọn:
  --n 200 --seed 0          số câu và hạt giống
  --select cluster|random   cluster (mặc định): xen kẽ 1 câu ngẫu nhiên với 1 câu dùng chung đoạn văn với tập đã chọn
  --select-only             chỉ chọn câu + gộp kho đoạn văn, chưa gọi LLM (xem thống kê trước)
  --force                   chọn lại câu và dựng lại đồ thị
  --workers 4               số request gửi song song (mặc định 1)
  --per-call 8              gộp tối đa 8 đoạn mỗi lần gọi (mặc định 1 = mỗi đoạn một lần gọi)
  --batch-tokens 1200       giới hạn token văn bản mỗi lô khi gộp
  --pilot 100               THỬ NGHIỆM (D13): lấy ngẫu nhiên 100 đoạn, trích bằng cả hai cách (1 đoạn/lần và
                            --per-call đoạn/lần), so sánh, ghi pilot.json; không dựng đồ thị đầy đủ

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
from dcg.extract import build_shared_graph, sf_coverage  # noqa: E402


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


def mode_metrics(kg, log, n_paragraphs):
    by_par = Counter(t for e in kg.edges.values() for t in {p[0] for p in e["provenance"]})
    return {
        "prompt_version": log["prompt_version"], "requests": log["requests"],
        "triples_kept": log["kept"], "triples_per_paragraph": round(log["kept"] / n_paragraphs, 2),
        "paragraphs_with_edges": round(sum(1 for c in by_par.values() if c) / n_paragraphs, 3),
        "suspect_rate": round(log["suspect"] / log["kept"], 3) if log["kept"] else None,
        "dropped": len(log["dropped"]), "parse_errors": len(log["parse_errors"]),
        "paragraph_skipped_then_retried": len(log.get("paragraph_skipped", [])),
    }


def run_pilot(corpus, args, out, llm):
    """D13: so sánh 1 đoạn/lần với --per-call đoạn/lần trên cùng các đoạn lấy ngẫu nhiên."""
    if args.per_call <= 1:
        raise SystemExit("--pilot cần --per-call > 1 để có cách gộp mà so sánh.")
    rels = load_relations()
    if llm is None:
        from dcg.llm import LLM
        llm = LLM()
    pick = set(random.Random(args.seed + 1).sample(list(corpus), min(args.pilot, len(corpus))))
    sub = {t: s for t, s in corpus.items() if t in pick}
    res, triples = {}, {}
    for name, per_call in (("single", 1), ("batch", args.per_call)):
        before = dict(getattr(llm, "stats", {}) or {})
        kg, log = build_shared_graph(sub, llm, rels, workers=args.workers, per_call=per_call,
                                     batch_tokens=args.batch_tokens, seed=args.seed)
        res[name] = mode_metrics(kg, log, len(sub))
        after = getattr(llm, "stats", {}) or {}
        res[name]["tokens"] = {k: after.get(k, 0) - before.get(k, 0) for k in ("prompt_tokens", "completion_tokens")}
        triples[name] = {(kg.name(e["head"]), e["relation"], kg.name(e["tail"])) for e in kg.edges.values()}
    a, b = res["single"], res["batch"]
    inter = len(triples["single"] & triples["batch"])
    union = len(triples["single"] | triples["batch"]) or 1
    ok_recall = b["triples_per_paragraph"] >= 0.9 * a["triples_per_paragraph"]
    ok_suspect = (b["suspect_rate"] or 0) <= (a["suspect_rate"] or 0) + 0.02
    report = {"paragraphs": len(sub), "per_call": args.per_call, "batch_tokens": args.batch_tokens,
              "single": a, "batch": b, "edge_jaccard": round(inter / union, 3),
              "rule": "dùng cách gộp nếu bộ ba/đoạn ≥ 90% cách đơn VÀ tỷ lệ nghi ngờ không cao hơn quá 2 điểm %",
              "recall_ok": ok_recall, "suspect_ok": ok_suspect,
              "decision": f"per_call={args.per_call}" if ok_recall and ok_suspect else "per_call=1 (+ --workers)"}
    write_json(out / "pilot.json", report)
    print(f"Thử nghiệm trên {len(sub)} đoạn:")
    for k in ("requests", "triples_per_paragraph", "paragraphs_with_edges", "suspect_rate", "dropped",
              "paragraph_skipped_then_retried", "tokens"):
        print(f"  {k:32s} đơn: {a[k]!s:28s} gộp: {b[k]!s}")
    print(f"  trùng cạnh (Jaccard)             {report['edge_jaccard']}")
    print(f"→ Kết luận theo quy tắc chốt trước: {report['decision']}")
    return report


def main(argv=None, llm=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hotpot", default=str(DATA / "raw" / "hotpotqa" / "hotpot_dev_distractor_v1.json"))
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--select", choices=["cluster", "random"], default="cluster")
    ap.add_argument("--out", default=str(DATA / "interim" / "shared"))
    ap.add_argument("--select-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--per-call", type=int, default=1)
    ap.add_argument("--batch-tokens", type=int, default=1200)
    ap.add_argument("--pilot", type=int, default=0)
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

    if args.pilot:
        return run_pilot(corpus, args, out, llm)
    if (out / "graph.json").exists() and not args.force:
        raise SystemExit(f"{out / 'graph.json'} đã có. Dùng --force để dựng lại (phản hồi đã có lấy từ cache).")
    rels = load_relations()
    if llm is None:
        from dcg.llm import LLM
        llm = LLM()

    def progress(k, total, title):
        if k == 1 or k % 25 == 0 or k == total:
            print(f"  [{k}/{total}] {title[:60]}")

    kg, log = build_shared_graph(corpus, llm, rels, progress=progress, workers=args.workers,
                                 per_call=args.per_call, batch_tokens=args.batch_tokens, seed=args.seed)
    write_json(out / "graph.json", kg.to_json())
    write_json(out / "extract_log.json", log)

    covered = {tuple(p) for e in kg.edges.values() for p in e["provenance"]}
    cov = [sf_coverage(kg, q["supporting_facts"], covered) for q in questions]
    degrees = sorted((len(kg.incident(n)) for n in kg.nodes), reverse=True)
    summary = {
        "corpus": stats,
        "prompt_version": log["prompt_version"], "llm": getattr(llm, "info", lambda: {})(),
        "per_call": args.per_call, "workers": args.workers, "requests": log["requests"],
        "paragraph_skipped_then_retried": len(log.get("paragraph_skipped", [])),
        "llm_stats": getattr(llm, "stats", None),
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
