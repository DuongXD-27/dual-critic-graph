"""Dựng benchmark cho hai cổng từ log một lượt chạy (DECISIONS D8, D16). Không gọi LLM.

  .venv\\Scripts\\python scripts\\build_benchmarks.py build            # từ data/runs/shared-v2
  .venv\\Scripts\\python scripts\\build_benchmarks.py import           # đọc nhãn tay trong các file Excel

Đầu ra trong data/benchmarks/ :
  traversal.jsonl     mỗi dòng = (câu hỏi, đường đi, MỘT cạnh ứng viên tại nút hiện tại) + nhãn tự động theo quy tắc
  construction.jsonl  mỗi dòng = một phép ghi agent đã nộp cho cổng; nhãn (gold) điền sau khi gán tay
  stats.json          thống kê
  label/traversal_kappa_sample.xlsx   100 tình huống duyệt để NGƯỜI gán độc lập (không hiện nhãn quy tắc) → κ (RQ0a)
  label/construction.xlsx             116 phép ghi để người gán SUPPORTED / UNSUPPORTED / WRONG
File Excel đã có thì KHÔNG ghi đè (tránh mất nhãn đã gán), trừ khi dùng --force-labels.
"""
from __future__ import annotations

import argparse
import html
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.agent import in_question  # noqa: E402
from dcg.common import DATA, load_relations, norm, read_json, read_jsonl, strip_paren, write_json  # noqa: E402
from dcg.metrics import normalize_answer  # noqa: E402

RULE_VERSION = "trav-rule-v1"
OUT = DATA / "benchmarks"
TRAV_LABELS = ("ACCEPT", "REJECT", "STOP")
CONS_LABELS = ("SUPPORTED", "UNSUPPORTED", "WRONG")


# ---------------------------------------------------------------- Traversal
def episode_states(ep, trav_gates):
    """Các trạng thái agent đã đứng: sau mỗi start_at / follow_edge thành công.
    Mỗi trạng thái: đường đi tới đó, nút hiện tại, các cạnh agent nhìn thấy, đoạn đã đọc, cạnh agent chọn đi tiếp."""
    states, k, reads = [], 0, []
    for e in ep["events"]:
        if e["phase"] != "answer":
            continue
        res = e.get("result")
        if e["tool"] == "read_paragraph" and isinstance(res, dict) and "sentences" in res:
            if res["paragraph"] not in reads:
                reads.append(res["paragraph"])
        if e["tool"] in ("start_at", "follow_edge") and isinstance(res, dict) and "current" in res:
            g = trav_gates[k]
            k += 1
            states.append({"path": g["path"] + [g["action"]], "node": res["current"], "node_name": res["name"],
                           "candidates": [x["edge_id"] for x in res["edges"]], "reads": list(reads)})
    assert k == len(trav_gates), (ep["episode_id"], k, len(trav_gates))
    for j, st in enumerate(states):
        nxt = trav_gates[j + 1]["action"] if j + 1 < len(trav_gates) else None
        st["chosen"] = nxt["edge_id"] if nxt and nxt["type"] == "follow" else None
        st["next"] = "follow" if st["chosen"] else ("start" if nxt else "answer")
    return states


def covered_sf(path, reads, sf, edges):
    cov = set()
    for s in path:
        if s["type"] == "follow" and s["edge_id"] in edges:
            cov |= {tuple(p) for p in edges[s["edge_id"]]["provenance"]} & sf
    return cov | {x for x in sf if x[0] in reads}


def relevant(name, question, gold, sf_titles):
    """Nút 'nằm trên đường' tới đáp án (sửa lỗ hổng D8): là đoạn bằng chứng, là đáp án, hoặc có trong câu hỏi.
    Tên nút nằm trong tiêu đề đoạn bằng chứng (theo từ, bỏ ngoặc và mã HTML): "Derry City" ~ "Derry City F.C.".
    Không xét chiều ngược lại: "Big Stone Gap, Virginia" KHÔNG khớp đoạn "Big Stone Gap (film)"."""
    for t in sf_titles:
        if in_question(html.unescape(name), strip_paren(html.unescape(t))):
            return True
    a, nn = normalize_answer(gold), normalize_answer(name)
    if a and a not in ("yes", "no") and (nn == a or (len(a) >= 4 and a in nn)):
        return True
    return in_question(name, question)


def label_candidate(q, state, edge, other_name, edges):
    """Quy tắc trav-rule-v1 (D8 + D16). Trả về (nhãn, chi tiết).
    STOP: đường đi + đoạn đã đọc phủ hết supporting_facts. REJECT: đi lại cạnh cũ.
    bridge:     ACCEPT ⇔ câu nguồn thuộc một ĐOẠN bằng chứng VÀ đầu kia 'nằm trên đường' (relevant).
    comparison: ACCEPT ⇔ câu nguồn là đúng một CÂU bằng chứng, hoặc thuộc đoạn bằng chứng và đầu kia relevant."""
    sf = {tuple(x) for x in q["supporting_facts"]}
    sf_titles = {t for t, _ in sf}
    cov = covered_sf(state["path"], state["reads"], sf, edges)
    prov = {tuple(p) for p in edge["provenance"]}
    d = {"sf_covered": len(cov), "sf_total": len(sf), "prov_in_sf": bool(prov & sf),
         "prov_in_sf_paragraph": any(t in sf_titles for t, _ in prov),
         "other_end_relevant": relevant(other_name, q["question"], q["answer"], sf_titles)}
    if cov == sf:
        return "STOP", {**d, "why": "evidence_complete"}
    if any(s["type"] == "follow" and s["edge_id"] == edge["id"] for s in state["path"]):
        return "REJECT", {**d, "why": "revisit"}
    if not d["prov_in_sf_paragraph"]:
        return "REJECT", {**d, "why": "not_evidence"}
    if d["other_end_relevant"] or (q["type"] == "comparison" and d["prov_in_sf"]):
        return "ACCEPT", {**d, "why": "evidence_on_path"}
    return "REJECT", {**d, "why": "off_path"}


def build_traversal(run_dir, questions, graph, corpus):
    episodes = read_jsonl(run_dir / "episodes.jsonl")
    gates = read_jsonl(run_dir / "gates.jsonl")
    by_ep = {}
    for g in gates:
        if g["kind"] == "traversal":
            by_ep.setdefault(g["episode_id"], []).append(g)
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = {e["id"]: e for e in graph["edges"]}
    items = []
    for ep in episodes:
        qid = ep["episode_id"].split(":")[0]
        q = questions[qid]
        for j, st in enumerate(episode_states(ep, by_ep.get(ep["episode_id"], []))):
            for eid in st["candidates"]:
                e = edges[eid]
                fwd = e["head"] == st["node"]
                other = nodes[e["tail"] if fwd else e["head"]]["name"]
                gold, detail = label_candidate(q, st, e, other, edges)
                items.append({
                    "id": f"t-{qid[:10]}-{j}-{eid}", "kind": "traversal", "run_id": run_dir.name, "qid": qid,
                    "qtype": q["type"], "question": q["question"], "path": st["path"],
                    "action": {"type": "follow", "from": st["node_name"], "edge_id": eid, "relation": e["relation"],
                               "relation_name": e.get("relation_name"), "to": other,
                               "direction": "forward" if fwd else "backward"},
                    "action_edge": {"origin": e["origin"], "provenance": e["provenance"]},
                    "action_evidence": [corpus[t][i].strip() for t, i in e["provenance"]
                                        if t in corpus and i < len(corpus[t])],
                    "paragraphs_read_before": st["reads"],
                    "agent_chose": st["chosen"] == eid, "agent_next": st["next"],
                    "gold": gold, "gold_source": RULE_VERSION, "rule_detail": detail})
    return items


# ---------------------------------------------------------------- Construction
def build_construction(run_dir):
    items = []
    for k, g in enumerate(r for r in read_jsonl(run_dir / "gates.jsonl") if r["kind"] == "construction"):
        items.append({"id": f"c-{k:03d}", "kind": "construction", "run_id": run_dir.name,
                      "episode_id": g["episode_id"], "phase": g["phase"], "question": g["question"],
                      "write": g["write"], "evidence": g["evidence"], "provenance": g["provenance"],
                      "gold": None, "gold_label": None, "gold_source": None})
    return items


# ---------------------------------------------------------------- Excel
def path_text(path):
    parts = []
    for s in path:
        if s["type"] == "start":
            parts.append(("  |  " if parts else "") + f"[bắt đầu] {s['to']}")
        else:
            arrow = f" —{s.get('relation_name') or s['relation']}→ " if s["direction"] == "forward" \
                else f" ←{s.get('relation_name') or s['relation']}— "
            parts.append(f"{arrow}{s['to']}")
    return "".join(parts)


def read_text(titles, corpus):
    """Toàn văn các đoạn agent đã đọc (để người gán biết đã đủ bằng chứng chưa)."""
    parts = [f"■ {t}\n" + "\n".join(f"[{i}] {x.strip()}" for i, x in enumerate(corpus.get(t, []))) for t in titles]
    return "\n\n".join(parts) or "(chưa đọc đoạn nào)"


def evidence_text(ev, rels=None):
    rels = rels or {}
    out = []
    for v in ev:
        if v["type"] == "sentence":
            out.append(f"[{v.get('title')} #{v.get('sid')}] {v['text']}" if v.get("text") else f"(câu không hợp lệ: {v.get('ref')})")
        else:
            src = " ".join(s["text"] for s in v["sentences"])
            out.append(f"[cạnh {v['head']} —{rels.get(v['relation'], v['relation'])}→ {v['tail']}] {src}")
    return "\n".join(out) or "(không có bằng chứng)"


def write_sheet(path, headers, rows, label_col, choices, guide, widths):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "label"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    for c in ws[1]:
        c.font = Font(bold=True)
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{label_col}2:{label_col}{len(rows) + 1}")
    ws.freeze_panes = "A2"
    g = wb.create_sheet("huong_dan")
    for line in guide:
        g.append([line])
    g.column_dimensions["A"].width = 140
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


TRAV_GUIDE = [
    "Mỗi dòng: agent đang trả lời câu hỏi, đã đi theo 'đường đi', đang đứng ở 'nút hiện tại' và cân nhắc đi theo 'cạnh ứng viên'.",
    "Bạn biết đáp án đúng. Chọn nhãn ở cột 'nhan' cho QUYẾT ĐỊNH đi theo cạnh ứng viên:",
    "  ACCEPT — cạnh này là một bước cần thiết trên đường tới đáp án (câu nguồn của cạnh nói đúng điều câu hỏi cần).",
    "  REJECT — cạnh không giúp trả lời (lạc đề, quay lại chỗ cũ, hoặc câu nguồn không nói điều cần).",
    "  STOP   — đường đi + các đoạn đã đọc (toàn văn ở cột 'noi_dung_doan_da_doc') ĐÃ đủ bằng chứng để trả lời; không cần đi thêm.",
    "Chỉ dựa vào câu hỏi, đáp án, đường đi, cạnh và câu nguồn. Không đoán theo hành vi agent. Không chắc thì ghi chú ở cột 'ghi_chu'.",
]
CONS_GUIDE = [
    "Mỗi dòng: agent muốn ghi một cạnh (đầu —quan hệ→ đuôi) vào đồ thị, kèm bằng chứng nó nộp.",
    "Chỉ dựa vào BẰNG CHỨNG trong dòng đó (không dùng hiểu biết riêng). Chọn nhãn ở cột 'nhan':",
    "  SUPPORTED   — bằng chứng nói rõ đúng sự kiện này: đúng đầu, đúng đuôi, đúng quan hệ, đúng chiều.",
    "  UNSUPPORTED — có thể đúng ngoài đời nhưng bằng chứng không nói đủ (phải suy luận thêm, cạnh bằng chứng không nối nhau, không có bằng chứng).",
    "  WRONG       — trái với bằng chứng hoặc hỏng: sai quan hệ (cousin→sibling), sai đầu, đảo chiều, đuôi không phải thực thể (tính từ 'American', năm vô nghĩa).",
    "Nhãn cổng: SUPPORTED → ACCEPT; UNSUPPORTED, WRONG → REJECT.",
    "Ví dụ: (Fyre Festival, founded by, Billy McFarland) với câu 'charged ... related to the organization of the Fyre Festival' → UNSUPPORTED.",
]


def kappa_sample(items, n, seed):
    rng = random.Random(seed)
    want = {"ACCEPT": n * 2 // 5, "REJECT": n * 2 // 5}
    want["STOP"] = n - sum(want.values())
    pick = []
    for lab, k in want.items():
        pool = [it for it in items if it["gold"] == lab]
        pick += rng.sample(pool, min(k, len(pool)))
    rest = [it for it in items if it not in pick]
    pick += rng.sample(rest, min(n - len(pick), len(rest)))
    rng.shuffle(pick)
    return pick


def cmd_build(args):
    run_dir = Path(args.run)
    gdir = Path(args.shared)
    questions = {q["_id"]: q for q in read_json(gdir / "questions.json")}
    corpus = read_json(gdir / "corpus.json")
    graph = read_json(run_dir / "graph_after.json")
    out = Path(args.out)
    rels = load_relations()
    trav = build_traversal(run_dir, questions, graph, corpus)
    for it in trav:
        it["action"]["relation_name"] = rels.get(it["action"]["relation"], "?")
    cons = build_construction(run_dir)
    write_jsonl(out / "traversal.jsonl", trav)
    if (out / "construction.jsonl").exists() and not args.force_labels:
        print("construction.jsonl đã có (có thể đã gán nhãn) → giữ nguyên")
    else:
        write_jsonl(out / "construction.jsonl", cons)

    chosen = [it for it in trav if it["agent_chose"]]
    stats = {
        "run": run_dir.name, "rule": RULE_VERSION,
        "traversal_items": len(trav), "traversal_states": len({it["id"].rsplit("-", 1)[0] for it in trav}),
        "traversal_gold": dict(Counter(it["gold"] for it in trav)),
        "traversal_why": dict(Counter(it["rule_detail"]["why"] for it in trav)),
        "traversal_gold_by_qtype": {t: dict(Counter(it["gold"] for it in trav if it["qtype"] == t))
                                    for t in ("bridge", "comparison")},
        "agent_chosen_edges_vs_rule": dict(Counter(it["gold"] for it in chosen)),
        "construction_items": len(cons),
        "construction_by_phase": dict(Counter(c["phase"] for c in cons)),
        "construction_by_origin": dict(Counter(c["write"]["origin"] for c in cons)),
    }
    write_json(out / "stats.json", stats)
    print("Thống kê:", stats)

    lab = out / "label"
    tpath, cpath = lab / "traversal_kappa_sample.xlsx", lab / "construction.xlsx"
    if tpath.exists() and not args.force_labels:
        print(f"{tpath} đã có → không ghi đè")
    else:
        sample = kappa_sample(trav, args.kappa_n, args.seed)
        write_json(lab / "traversal_kappa_sample_ids.json", [it["id"] for it in sample])
        rows = [[it["id"], it["question"], questions[it["qid"]]["answer"], path_text(it["path"]), it["action"]["from"],
                 f"{it['action']['from']} —{it['action']['relation_name']}→ {it['action']['to']}"
                 if it["action"]["direction"] == "forward" else
                 f"{it['action']['to']} —{it['action']['relation_name']}→ {it['action']['from']}",
                 "\n".join(it["action_evidence"]) or "(không có câu nguồn)",
                 "\n".join(it["paragraphs_read_before"]) or "(chưa đọc đoạn nào)",
                 read_text(it["paragraphs_read_before"], corpus), None, None] for it in sample]
        write_sheet(tpath, ["id", "cau_hoi", "dap_an", "duong_di", "nut_hien_tai", "canh_ung_vien", "cau_nguon",
                            "doan_da_doc", "noi_dung_doan_da_doc", "nhan", "ghi_chu"], rows, "J", TRAV_LABELS, TRAV_GUIDE,
                    {"A": 14, "B": 40, "C": 16, "D": 40, "E": 20, "F": 36, "G": 50, "H": 20, "I": 70, "J": 10, "K": 25})
        print(f"→ {tpath} ({len(rows)} dòng)")
    if cpath.exists() and not args.force_labels:
        print(f"{cpath} đã có → không ghi đè")
    else:
        rows = [[c["id"], c["question"], c["phase"], c["write"]["head"],
                 f"{c['write']['relation']} {c['write']['relation_name']}", c["write"]["tail"], c["write"]["origin"],
                 evidence_text(c["evidence"], rels), None, None] for c in cons]
        write_sheet(cpath, ["id", "cau_hoi", "luc_ghi", "dau", "quan_he", "duoi", "nguon_goc", "bang_chung",
                            "nhan", "ghi_chu"], rows, "I", CONS_LABELS, CONS_GUIDE,
                    {"A": 8, "B": 40, "C": 9, "D": 25, "E": 22, "F": 25, "G": 14, "H": 80, "I": 14, "J": 25})
        print(f"→ {cpath} ({len(rows)} dòng)")
    return stats


# ---------------------------------------------------------------- import nhãn tay
def read_sheet(path, label_col_name):
    from openpyxl import load_workbook

    ws = load_workbook(path, read_only=True)["label"]
    rows = list(ws.iter_rows(values_only=True))
    h = list(rows[0])
    i_id, i_lab, i_note = h.index("id"), h.index(label_col_name), h.index("ghi_chu")
    return {r[i_id]: {"label": (str(r[i_lab]).strip().upper() if r[i_lab] else None), "note": r[i_note]}
            for r in rows[1:] if r[i_id]}


def cohen_kappa(a, b):
    n = len(a)
    labels = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[lab] * cb[lab] for lab in labels) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0, round(po, 3)


def sync_vi(en_path, vi_path):
    """Chép nhãn + ghi chú từ bản tiếng Việt (scripts/kappa_sheet_vi.py) sang bản tiếng Anh, theo id.
    Chỉ chép ô đã có nhãn ở bản tiếng Việt; trả về số dòng đã chép."""
    from openpyxl import load_workbook

    vi = load_workbook(vi_path, read_only=True)["label"]
    vrows = list(vi.iter_rows(values_only=True))
    vh = list(vrows[0])
    src = {r[vh.index("id")]: (r[vh.index("nhan")], r[vh.index("ghi_chu")]) for r in vrows[1:]
           if r[vh.index("id")] and r[vh.index("nhan")]}
    wb = load_workbook(en_path)
    ws = wb["label"]
    eh = [c.value for c in ws[1]]
    i_id, i_lab, i_note = eh.index("id") + 1, eh.index("nhan") + 1, eh.index("ghi_chu") + 1
    n = 0
    for r in range(2, ws.max_row + 1):
        rid = ws.cell(r, i_id).value
        if rid in src:
            ws.cell(r, i_lab).value, ws.cell(r, i_note).value = src[rid]
            n += 1
    wb.save(en_path)
    return n


def cmd_import(args):
    out = Path(args.out)
    lab = out / "label"
    report = {}
    tpath = lab / "traversal_kappa_sample.xlsx"
    vpath = lab / "traversal_kappa_sample_vi.xlsx"
    if tpath.exists() and vpath.exists():
        report["copied_from_vi"] = sync_vi(tpath, vpath)
        print(f"Đã chép {report['copied_from_vi']} nhãn từ {vpath.name} sang {tpath.name}")
    if tpath.exists():
        human = read_sheet(tpath, "nhan")
        gold = {it["id"]: it["gold"] for it in read_jsonl(out / "traversal.jsonl")}
        done = [(gold[i], h["label"]) for i, h in human.items() if h["label"] in TRAV_LABELS and i in gold]
        write_json(lab / "traversal_human.json", {i: h["label"] for i, h in human.items() if h["label"] in TRAV_LABELS})
        bad = [i for i, h in human.items() if h["label"] and h["label"] not in TRAV_LABELS]
        if done:
            k, po = cohen_kappa([g for g, _ in done], [h for _, h in done])
            conf = Counter(f"quy_tac={g} / nguoi={h}" for g, h in done)
            report["traversal_kappa"] = {"labeled": len(done), "of": len(human), "kappa": k, "agreement": po,
                                         "confusion": dict(sorted(conf.items())), "invalid_labels": bad}
            # κ hai lớp (đi / không đi): STOP và REJECT cùng nghĩa "không đi theo cạnh này"
            bin_ = lambda x: "GO" if x == "ACCEPT" else "NO"  # noqa: E731
            report["traversal_kappa"]["kappa_go_vs_no"] = cohen_kappa([bin_(g) for g, _ in done],
                                                                      [bin_(h) for _, h in done])[0]
    cpath = lab / "construction.xlsx"
    if cpath.exists():
        human = read_sheet(cpath, "nhan")
        items = read_jsonl(out / "construction.jsonl")
        n_lab = 0
        for c in items:
            h = human.get(c["id"])
            if h and h["label"] in CONS_LABELS:
                c.update(gold="ACCEPT" if h["label"] == "SUPPORTED" else "REJECT", gold_label=h["label"],
                         gold_source="human", gold_note=h["note"])
                n_lab += 1
        write_jsonl(out / "construction.jsonl", items)
        report["construction"] = {"labeled": n_lab, "of": len(items),
                                  "labels": dict(Counter(c["gold_label"] for c in items if c["gold_label"])),
                                  "invalid_labels": [i for i, h in human.items() if h["label"] and h["label"] not in CONS_LABELS]}
    write_json(out / "labels_report.json", report)
    print("Nhãn tay:", report)
    return report


def write_jsonl(path, rows):
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "import"])
    ap.add_argument("--run", default=str(DATA / "runs" / "shared-v2"))
    ap.add_argument("--shared", default=str(DATA / "interim" / "shared"), help="thư mục có questions.json, corpus.json")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--kappa-n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--force-labels", action="store_true", help="ghi đè file Excel và construction.jsonl (MẤT nhãn đã gán)")
    args = ap.parse_args(argv)
    return cmd_build(args) if args.cmd == "build" else cmd_import(args)


if __name__ == "__main__":
    main()
