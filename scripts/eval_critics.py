"""Đánh giá critic offline trên benchmark (DECISIONS D17).

  .venv\\Scripts\\python scripts\\eval_critics.py --gates rule                 # critic luật, không tốn API
  .venv\\Scripts\\python scripts\\eval_critics.py --gates llm --workers 6      # critic LLM
  .venv\\Scripts\\python scripts\\eval_critics.py --gates llm --score-only     # chỉ tính lại chỉ số từ dự đoán đã lưu
                                                                              # (vd. sau khi gán thêm nhãn tay)
Tập đánh giá Traversal (mặc định, cố định theo seed): mọi STOP + 250 ACCEPT + 250 REJECT lấy ngẫu nhiên
  + mọi cạnh agent thật sự chọn + 100 tình huống của mẫu κ. --full: cả 3.560 tình huống.
Construction: cả 116 phép ghi; chỉ tính chỉ số trên dòng đã có nhãn tay (build_benchmarks.py import).

Đầu ra: data/benchmarks/eval/<tên>/ : traversal_pred.jsonl, construction_pred.jsonl, metrics.json
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.common import DATA, read_json, read_jsonl, write_json  # noqa: E402
from dcg.gates import GATES, make_context  # noqa: E402

BENCH = DATA / "benchmarks"


def write_jsonl(path, rows):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def eval_ids(items, kappa_ids, n_each, seed):
    rng = random.Random(seed)
    ids = {it["id"] for it in items if it["gold"] == "STOP" or it["agent_chose"]} | set(kappa_ids)
    for lab in ("ACCEPT", "REJECT"):
        pool = sorted(it["id"] for it in items if it["gold"] == lab)
        ids |= set(rng.sample(pool, min(n_each, len(pool))))
    return [it["id"] for it in items if it["id"] in ids]  # giữ thứ tự benchmark


# ---------------------------------------------------------------- chỉ số
def prf(gold, pred, pos):
    tp = sum(g == pos and p == pos for g, p in zip(gold, pred))
    fp = sum(g != pos and p == pos for g, p in zip(gold, pred))
    fn = sum(g == pos and p != pos for g, p in zip(gold, pred))
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(pr, 3), "recall": round(rc, 3),
            "f1": round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0, "support": sum(g == pos for g in gold)}


def scores(gold, pred, labels):
    if not gold:
        return None
    per = {lab: prf(gold, pred, lab) for lab in labels}
    return {"n": len(gold), "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / len(gold), 3),
            "macro_f1": round(sum(v["f1"] for v in per.values()) / len(labels), 3), "per_label": per,
            "confusion": dict(sorted(Counter(f"gold={g} / pred={p}" for g, p in zip(gold, pred)).items()))}


def traversal_metrics(rows, human):
    go = lambda x: "GO" if x == "ACCEPT" else "NO"  # noqa: E731
    out = {"all_vs_rule": scores([r["gold"] for r in rows], [r["pred"] for r in rows], ("ACCEPT", "REJECT", "STOP")),
           "all_go_vs_no": scores([go(r["gold"]) for r in rows], [go(r["pred"]) for r in rows], ("GO", "NO"))}
    ch = [r for r in rows if r["agent_chose"]]
    out["agent_chosen_steps"] = {
        "n": len(ch), "rule_bad": sum(r["gold"] != "ACCEPT" for r in ch),
        "blocked_bad": sum(r["gold"] != "ACCEPT" and r["pred"] != "ACCEPT" for r in ch),
        "blocked_good": sum(r["gold"] == "ACCEPT" and r["pred"] != "ACCEPT" for r in ch)}
    hk = [r for r in rows if r["id"] in human]
    if hk:
        out["kappa_sample_vs_human"] = scores([human[r["id"]] for r in hk], [r["pred"] for r in hk],
                                              ("ACCEPT", "REJECT", "STOP"))
    out["parse_errors"] = sum(bool(r.get("parse_error")) for r in rows)
    return out


def construction_metrics(rows):
    lab = [r for r in rows if r["gold"] in ("ACCEPT", "REJECT")]
    out = {"n_items": len(rows), "n_labeled": len(lab),
           "pred": dict(Counter(r["pred"] for r in rows)),
           "reason_codes": dict(Counter(r.get("reason_code") for r in rows)),
           "parse_errors": sum(bool(r.get("parse_error")) for r in rows)}
    if lab:
        out["vs_human"] = scores([r["gold"] for r in lab], [r["pred"] for r in lab], ("ACCEPT", "REJECT"))
        out["reject_rate_by_human_label"] = {
            k: f"{sum(r['pred'] == 'REJECT' for r in lab if r['gold_label'] == k)}/"
               f"{sum(r['gold_label'] == k for r in lab)}" for k in ("SUPPORTED", "UNSUPPORTED", "WRONG")}
    return out


# ---------------------------------------------------------------- chạy critic
def run_traversal(gates, items, workers, corpus, graphs):
    def one(it):
        edges = graphs[it["run_id"]]
        provs = [edges[s["edge_id"]]["provenance"] for s in it["path"]
                 if s["type"] == "follow" and s["edge_id"] in edges]
        ctx = make_context(corpus, provs, it["action_edge"]["provenance"], it["paragraphs_read_before"])
        v = gates.traversal_gate(it["question"], it["path"], it["action"], context=ctx)
        return {"id": it["id"], "qtype": it["qtype"], "agent_chose": it["agent_chose"], "gold": it["gold"],
                "pred": v["verdict"], "reason": v.get("reason"), "parse_error": v.get("parse_error", False)}
    with ThreadPoolExecutor(max(1, workers)) as ex:
        return list(ex.map(one, items))


def run_construction(gates, items, workers):
    def one(c):
        v = gates.construction_gate(c["write"], c["evidence"], c["provenance"])
        return {"id": c["id"], "pred": v["verdict"], "reason_code": v.get("reason_code"), "reason": v.get("reason"),
                "parse_error": v.get("parse_error", False)}
    with ThreadPoolExecutor(max(1, workers)) as ex:
        return list(ex.map(one, items))


def main(argv=None, llm=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", required=True, choices=sorted(GATES))
    ap.add_argument("--bench", default=str(BENCH))
    ap.add_argument("--only", choices=["traversal", "construction"])
    ap.add_argument("--full", action="store_true", help="đánh giá Traversal trên toàn bộ tình huống")
    ap.add_argument("--n-each", type=int, default=250)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--name", help="tên thư mục kết quả (mặc định: <gates>[-<model>])")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--corpus", default=str(DATA / "interim" / "shared" / "corpus.json"))
    ap.add_argument("--runs-root", default=str(DATA / "runs"), help="nơi có <run_id>/graph_after.json")
    args = ap.parse_args(argv)
    bench = Path(args.bench)

    gates = None
    name = args.name or args.gates
    if not args.score_only:
        gates = GATES[args.gates](llm=llm) if args.gates == "llm" else GATES[args.gates]()
        if args.gates == "llm" and not args.name:
            name = f"llm-{gates.llm.info()['model']}"
    out = bench / "eval" / name
    human_path = bench / "label" / "traversal_human.json"
    human = read_json(human_path) if human_path.exists() else {}
    metrics = {"gates": args.gates, "name": name}

    if args.only != "construction":
        items = read_jsonl(bench / "traversal.jsonl")
        if args.score_only:
            rows = read_jsonl(out / "traversal_pred.jsonl")
        else:
            kpath = bench / "label" / "traversal_kappa_sample_ids.json"
            ids = set(eval_ids(items, read_json(kpath) if kpath.exists() else [], args.n_each, args.seed)) \
                if not args.full else {it["id"] for it in items}
            items = [it for it in items if it["id"] in ids][: args.limit]
            corpus = read_json(Path(args.corpus))
            graphs = {r: {e["id"]: e for e in read_json(Path(args.runs_root) / r / "graph_after.json")["edges"]}
                      for r in {it["run_id"] for it in items}}
            print(f"Traversal: {len(items)} tình huống ...")
            rows = run_traversal(gates, items, args.workers, corpus, graphs)
            write_jsonl(out / "traversal_pred.jsonl", rows)
        metrics["traversal"] = traversal_metrics(rows, human)

    if args.only != "traversal":
        cons = read_jsonl(bench / "construction.jsonl")
        if args.score_only:
            rows = read_jsonl(out / "construction_pred.jsonl")
        else:
            cons = cons[: args.limit]
            print(f"Construction: {len(cons)} phép ghi ...")
            rows = run_construction(gates, cons, args.workers)
            write_jsonl(out / "construction_pred.jsonl", rows)
        gold = {c["id"]: c for c in cons}
        for r in rows:  # nhãn tay lấy MỚI NHẤT từ benchmark (có thể gán sau khi chạy critic)
            r["gold"], r["gold_label"] = gold[r["id"]]["gold"], gold[r["id"]].get("gold_label")
        metrics["construction"] = construction_metrics(rows)

    if gates is not None and getattr(gates, "llm", None) is not None:
        metrics["llm"] = gates.llm.info()
        metrics["llm_stats"] = getattr(gates.llm, "stats", None)
    write_json(out / "metrics.json", metrics)
    show(metrics)
    return metrics


def show(m):
    t = m.get("traversal")
    if t:
        a = t["all_vs_rule"]
        print(f"\nTRAVERSAL ({a['n']} tình huống, so với nhãn quy tắc): accuracy {a['accuracy']}, macro-F1 {a['macro_f1']}")
        for lab, v in a["per_label"].items():
            print(f"  {lab:7s} P {v['precision']:.2f}  R {v['recall']:.2f}  F1 {v['f1']:.2f}  (n={v['support']})")
        c = t["agent_chosen_steps"]
        print(f"  Bước agent thật sự chọn: {c['n']} — quy tắc cho là sai {c['rule_bad']}; "
              f"critic chặn được {c['blocked_bad']}, chặn nhầm bước đúng {c['blocked_good']}")
        if "kappa_sample_vs_human" in t:
            h = t["kappa_sample_vs_human"]
            print(f"  So với nhãn NGƯỜI (mẫu κ, {h['n']}): accuracy {h['accuracy']}, macro-F1 {h['macro_f1']}")
    c = m.get("construction")
    if c:
        print(f"\nCONSTRUCTION ({c['n_items']} phép ghi, {c['n_labeled']} đã có nhãn tay): dự đoán {c['pred']}")
        print(f"  reason_code: {c['reason_codes']}")
        if "vs_human" in c:
            h = c["vs_human"]
            r = h["per_label"]["REJECT"]
            print(f"  So với nhãn người: accuracy {h['accuracy']}, REJECT P {r['precision']:.2f} R {r['recall']:.2f} "
                  f"F1 {r['f1']:.2f}; tỷ lệ REJECT theo nhãn người: {c['reject_rate_by_human_label']}")
    if m.get("llm_stats"):
        print("LLM:", m["llm_stats"])


if __name__ == "__main__":
    main()
