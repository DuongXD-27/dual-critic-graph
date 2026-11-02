"""Tạo bản TIẾNG VIỆT của file gán nhãn κ (D16) để người gán đọc dễ hơn.

  .venv\\Scripts\\python scripts\\kappa_sheet_vi.py
  → data/benchmarks/label/traversal_kappa_sample_vi.xlsx  (cùng id, cùng thứ tự; nhãn đã gán ở bản tiếng Anh được chép sang)

Gán nhãn trên bản tiếng Việt. Lệnh `build_benchmarks.py import` tự chép nhãn từ bản tiếng Việt sang bản tiếng Anh
(theo id) trước khi tính κ. Bản dịch: data/benchmarks/label/kappa_vi_translations.json (giữ nguyên tên riêng,
tên quan hệ kèm tiếng Anh trong ngoặc). Ba cột cuối giữ nguyên văn tiếng Anh để đối chiếu.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.common import DATA, read_json, read_jsonl  # noqa: E402

LAB = DATA / "benchmarks" / "label"
GUIDE_VI = [
    "Mỗi dòng: agent đang trả lời câu hỏi, đã đi theo 'đường đi', đang đứng ở 'nút hiện tại' và cân nhắc đi theo 'cạnh ứng viên'.",
    "Bạn biết đáp án đúng. Tự hỏi theo thứ tự:",
    "  1) Những gì agent đã có (đường đi + nội dung các đoạn đã đọc) ĐÃ ĐỦ để trả lời chưa? → đủ thì chọn STOP (khỏi xét cạnh).",
    "  2) Chưa đủ: cạnh ứng viên có đưa tới thứ cần đi qua / chính là đáp án không? → có: ACCEPT; lạc đề, quay lại, không giúp gì: REJECT.",
    "Chỉ dựa vào câu hỏi, đáp án, đường đi, cạnh, câu nguồn, nội dung đoạn đã đọc. Không chắc thì ghi lý do vào cột 'ghi_chu'.",
    "Bản dịch do máy dịch; nếu nghi ngờ nghĩa, xem nguyên văn tiếng Anh ở 3 cột cuối.",
    "Tên quan hệ có tiếng Anh trong ngoặc, ví dụ 'đạo diễn (director)'. Mũi tên A —quan hệ→ B nghĩa là: quan hệ của A là B.",
]


def main():
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    tr = read_json(LAB / "kappa_vi_translations.json")
    rel, ans, qv, sv = tr["relations"], tr["answers"], tr["questions"], tr["sentences"]
    corpus = read_json(DATA / "interim" / "shared" / "corpus.json")
    qs = {q["_id"]: q for q in read_json(DATA / "interim" / "shared" / "questions.json")}
    items = {it["id"]: it for it in read_jsonl(DATA / "benchmarks" / "traversal.jsonl")}
    en = load_workbook(LAB / "traversal_kappa_sample.xlsx", read_only=True)["label"]
    rows = list(en.iter_rows(values_only=True))
    h = list(rows[0])
    prev = {r[0]: (r[h.index("nhan")], r[h.index("ghi_chu")]) for r in rows[1:] if r[0]}

    R = lambda name: rel.get(name, name)  # noqa: E731
    S = lambda s: sv.get(s.strip(), s.strip())  # noqa: E731

    def path_vi(path):
        parts = []
        for s in path:
            if s["type"] == "start":
                parts.append(("  |  " if parts else "") + f"[bắt đầu] {s['to']}")
            else:
                r = R(s.get("relation_name") or s["relation"])
                parts.append(f" —{r}→ {s['to']}" if s.get("direction") == "forward" else f" ←{r}— {s['to']}")
        return "".join(parts)

    def read_vi(titles, vi=True):
        out = []
        for t in titles:
            sents = corpus.get(t, [])
            out.append(f"■ {t}\n" + "\n".join(f"[{i}] {S(x) if vi else x.strip()}" for i, x in enumerate(sents)))
        return "\n\n".join(out) or "(chưa đọc đoạn nào)"

    wb = Workbook()
    ws = wb.active
    ws.title = "label"
    head = ["id", "cau_hoi", "dap_an", "duong_di", "nut_hien_tai", "canh_ung_vien", "cau_nguon", "doan_da_doc",
            "noi_dung_doan_da_doc", "nhan", "ghi_chu", "EN_cau_hoi", "EN_cau_nguon", "EN_noi_dung_doan_da_doc"]
    ws.append(head)
    for r in rows[1:]:
        it = items[r[0]]
        a = it["action"]
        rn = R(a["relation_name"])
        edge = (f"{a['from']} —{rn}→ {a['to']}" if a["direction"] == "forward" else f"{a['to']} —{rn}→ {a['from']}")
        gold = qs[it["qid"]]["answer"]
        lab, note = prev.get(r[0], (None, None))
        ws.append([r[0], qv.get(it["question"], it["question"]), ans.get(gold, gold), path_vi(it["path"]), a["from"], edge,
                   "\n".join(S(x) for x in it["action_evidence"]) or "(không có câu nguồn)",
                   "\n".join(it["paragraphs_read_before"]) or "(chưa đọc đoạn nào)",
                   read_vi(it["paragraphs_read_before"]), lab, note,
                   it["question"], "\n".join(x.strip() for x in it["action_evidence"]),
                   read_vi(it["paragraphs_read_before"], vi=False)])
    for c in ws[1]:
        c.font = Font(bold=True)
    for k, w in {"A": 14, "B": 40, "C": 18, "D": 40, "E": 20, "F": 36, "G": 50, "H": 20, "I": 70, "J": 10, "K": 25,
                 "L": 30, "M": 30, "N": 30}.items():
        ws.column_dimensions[k].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    dv = DataValidation(type="list", formula1='"ACCEPT,REJECT,STOP"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"J2:J{ws.max_row}")
    ws.freeze_panes = "B2"
    g = wb.create_sheet("huong_dan")
    for line in GUIDE_VI:
        g.append([line])
    g.column_dimensions["A"].width = 140
    out = LAB / "traversal_kappa_sample_vi.xlsx"
    if out.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{out} đã có (có thể đã gán nhãn). Dùng --force để tạo lại.")
    wb.save(out)
    print(f"→ {out}: {ws.max_row - 1} dòng; chép sẵn {sum(1 for v in prev.values() if v[0])} nhãn từ bản tiếng Anh")


if __name__ == "__main__":
    main()
