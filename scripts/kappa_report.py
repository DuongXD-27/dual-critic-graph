"""Báo cáo so sánh nhãn NGƯỜI (mẫu κ, 100 tình huống Traversal) với quy tắc trav-rule-v1 và các critic đã chạy.

  .venv\\Scripts\\python scripts\\kappa_report.py

Đọc: data/benchmarks/label/traversal_kappa_sample.xlsx (nhãn + ghi chú; chạy build_benchmarks.py import trước),
     data/benchmarks/traversal.jsonl, data/benchmarks/eval/<tên>/traversal_pred.jsonl (mọi critic đã chạy).
Ghi: data/benchmarks/eval/kappa_report.md (bảng κ + mọi dòng lệch) và kappa_report.json.
Dòng có ghi chú chứa "cần đáp án" / "nhờ đáp án" được tính thêm một lần ở cột "bỏ dòng cần đáp án" (D16 5f).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_benchmarks import TRAV_LABELS, cohen_kappa, read_sheet  # noqa: E402
from dcg.common import DATA, read_jsonl, write_json  # noqa: E402

BENCH = DATA / "benchmarks"
NEEDS_ANSWER = ("cần đáp án", "nhờ đáp án")


def go(x):
    return "GO" if x == "ACCEPT" else "NO"


def scores(human, pred, ids):
    a, p = [human[i] for i in ids], [pred[i] for i in ids]
    k, acc = cohen_kappa(a, p)
    return {"n": len(ids), "kappa": k, "accuracy": acc, "kappa_go_vs_no": cohen_kappa([go(x) for x in a], [go(x) for x in p])[0],
            "confusion": dict(sorted(Counter(f"nguoi={x} / {y}" for x, y in zip(a, p)).items()))}


def main():
    sheet = read_sheet(BENCH / "label" / "traversal_kappa_sample.xlsx", "nhan")
    human = {i: h["label"] for i, h in sheet.items() if h["label"] in TRAV_LABELS}
    notes = {i: (h["note"] or "") for i, h in sheet.items()}
    items = {it["id"]: it for it in read_jsonl(BENCH / "traversal.jsonl")}
    ids = [i for i in human if i in items]
    needs = {i for i in ids if any(k in notes[i].lower() for k in NEEDS_ANSWER)}
    ids_clean = [i for i in ids if i not in needs]

    sources = {"trav-rule-v1 (nhãn tự động)": {i: items[i]["gold"] for i in ids}}
    critics = {}
    for d in sorted((BENCH / "eval").glob("*/traversal_pred.jsonl")):
        pred = {r["id"]: r for r in read_jsonl(d)}
        if all(i in pred for i in ids):
            critics[d.parent.name] = pred
            sources[f"critic {d.parent.name}"] = {i: pred[i]["pred"] for i in ids}

    report = {"n_labeled": len(ids), "n_needs_answer": len(needs), "human_labels": dict(Counter(human[i] for i in ids)),
              "vs_human": {name: {"all": scores(human, p, ids), "without_needs_answer": scores(human, p, ids_clean)}
                           for name, p in sources.items()}}

    md = ["# So sánh nhãn người với quy tắc và critic (mẫu κ Traversal)", "",
          f"Đã gán: {len(ids)} dòng; nhãn người: {report['human_labels']}; dòng cần đáp án: {len(needs)}.", "",
          "| Nguồn | n | κ (3 lớp) | đồng ý | κ (đi / không đi) | κ bỏ dòng cần đáp án |", "|---|---|---|---|---|---|"]
    for name, s in report["vs_human"].items():
        a, c = s["all"], s["without_needs_answer"]
        md.append(f"| {name} | {a['n']} | {a['kappa']} | {a['accuracy']} | {a['kappa_go_vs_no']} | {c['kappa']} |")
    md += ["", "## Ma trận nhầm lẫn", ""]
    for name, s in report["vs_human"].items():
        md.append(f"- **{name}**: " + "; ".join(f"{k}: {v}" for k, v in s["all"]["confusion"].items()))

    cols = list(sources)
    md += ["", "## Các dòng có ít nhất một nguồn lệch nhãn người", "",
           "| id | câu hỏi | cạnh ứng viên | người | " + " | ".join(cols) + " | lý do quy tắc | ghi chú |",
           "|" + "---|" * (6 + len(cols))]
    rows = []
    for i in ids:
        preds = {c: sources[c][i] for c in cols}
        if all(p == human[i] for p in preds.values()):
            continue
        it, a = items[i], items[i]["action"]
        edge = f"{a['from']} —{a['relation_name']}→ {a['to']}" if a.get("direction") == "forward" \
            else f"{a['to']} —{a['relation_name']}→ {a['from']}"
        row = {"id": i, "question": it["question"], "edge": edge, "human": human[i], **preds,
               "rule_why": it["rule_detail"].get("why"), "note": notes[i],
               "critic_reasons": {c: critics[c][i].get("reason", "") for c in critics}}
        rows.append(row)
        cell = lambda s: str(s).replace("|", "/").replace("\n", " ")  # noqa: E731
        md.append(f"| {i} | {cell(it['question'][:80])} | {cell(edge)} | **{human[i]}** | "
                  + " | ".join(("" if preds[c] == human[i] else "≠ ") + preds[c] for c in cols)
                  + f" | {row['rule_why']} | {cell(notes[i])} |")
    report["disagreements"] = rows
    out = BENCH / "eval"
    write_json(out / "kappa_report.json", report)
    (out / "kappa_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for name, s in report["vs_human"].items():
        print(f"{name:40s} κ={s['all']['kappa']:<6} đồng ý={s['all']['accuracy']:<6} κ2={s['all']['kappa_go_vs_no']}")
    print(f"{len(rows)} dòng lệch -> {out / 'kappa_report.md'}")


if __name__ == "__main__":
    main()
