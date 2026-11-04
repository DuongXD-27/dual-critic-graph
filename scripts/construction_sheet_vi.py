"""Tạo bản TIẾNG VIỆT của file gán nhãn Construction (D16) để người gán đọc dễ hơn.

  .venv\\Scripts\\python scripts\\construction_sheet_vi.py
  → data/benchmarks/label/construction_vi.xlsx  (cùng id, cùng thứ tự; nhãn đã gán ở bản tiếng Anh được chép sang)

Gán nhãn trên bản tiếng Việt. Lệnh `build_benchmarks.py import` tự chép nhãn từ bản tiếng Việt sang
`construction.xlsx` (theo id) trước khi đọc nhãn. Bản dịch: kappa_vi_translations.json + construction_vi_translations.json
(do Claude dịch; giữ nguyên tên riêng, tên quan hệ kèm tiếng Anh). Các cột EN_* giữ nguyên văn để đối chiếu.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.common import DATA, read_json, read_jsonl  # noqa: E402

LAB = DATA / "benchmarks" / "label"
OUT = LAB / "construction_vi.xlsx"

GUIDE_VI = [
    "Mỗi dòng: agent muốn GHI một cạnh mới vào đồ thị chung: ĐẦU —QUAN HỆ→ ĐUÔI (đọc là: 'quan hệ của ĐẦU là ĐUÔI'), kèm bằng chứng nó nộp.",
    "Chỉ trả lời MỘT câu hỏi: bằng chứng trong dòng này có nói rõ ĐÚNG sự kiện đó không — đúng đầu, đúng đuôi, đúng quan hệ, đúng chiều?",
    "",
    "Chọn nhãn ở cột 'nhan':",
    "  SUPPORTED   — bằng chứng nói rõ đúng sự kiện này. Đọc câu văn là thấy ngay, không phải suy luận thêm.",
    "  UNSUPPORTED — có thể đúng ngoài đời nhưng bằng chứng KHÔNG nói đủ: phải suy luận thêm, đoán, dùng hiểu biết riêng; hoặc các cạnh bằng chứng không nối với nhau; hoặc không có bằng chứng.",
    "  WRONG       — trái với bằng chứng hoặc bộ ba bị hỏng: sai quan hệ, sai đầu/đuôi, đảo chiều, đuôi không phải một thực thể (tính từ, con số vô nghĩa).",
    "Phân vân giữa UNSUPPORTED và WRONG: chọn một và ghi lý do — cổng chỉ phân biệt SUPPORTED (cho ghi) với hai nhãn còn lại (chặn), nên ranh giới này hầu như không ảnh hưởng kết quả.",
    "",
    "Ví dụ (bịa, không có trong dữ liệu):",
    "  (Nguyễn A, học tại, Đại học X) + 'Nguyễn A tốt nghiệp Đại học X năm 2001.'          → SUPPORTED",
    "  (Nguyễn A, học tại, Đại học X) + 'Nguyễn A từng giảng dạy tại Đại học X.'           → UNSUPPORTED (giảng dạy ≠ học; văn bản không nói A học ở đó)",
    "  (Nguyễn A, anh chị em ruột, Trần B) + 'Trần B là anh HỌ của Nguyễn A.'              → WRONG (sai quan hệ: anh họ ≠ anh ruột)",
    "  (Đại học X, học tại, Nguyễn A) + 'Nguyễn A tốt nghiệp Đại học X.'                  → WRONG (đảo chiều)",
    "  (Nguyễn A, quốc tịch, 'Việt') + 'Nguyễn A là một kỹ sư người Việt.'                → WRONG (đuôi là tính từ, không phải thực thể quốc gia)",
    "",
    "Ba điều cần nhớ:",
    "  1) KHÔNG dùng hiểu biết riêng. Bạn biết sự kiện đúng ngoài đời nhưng văn bản không nói → UNSUPPORTED ('đúng nhưng chưa đủ bằng chứng thì không ghi').",
    "  2) Đọc kỹ NGHĨA của quan hệ (sheet 'quan_he'). Phần lớn lỗi của agent là chọn sai quan hệ cho một câu văn đúng.",
    "  3) nguon_goc = AGENT_DERIVED: agent SUY RA từ các cạnh có sẵn (bằng chứng ghi '[cạnh ...]'). Hỏi: các cạnh đó ghép lại có CHỨNG MINH được sự kiện không? Không nối được với nhau → UNSUPPORTED.",
    "",
    "Cột bằng chứng: '[câu: Tên đoạn #i]' = câu số i của đoạn văn; '[cạnh A —quan hệ→ B]' = một cạnh có sẵn trong đồ thị, kèm câu văn sinh ra cạnh đó.",
    "luc_ghi: 'bước bộ nhớ' = agent ghi sau khi trả lời xong; 'lúc trả lời' = agent ghi ngay khi đang trả lời (ghi rồi đi tiếp).",
    "Bản dịch do Claude (LLM) làm; nếu nghi ngờ nghĩa, xem nguyên văn tiếng Anh ở các cột EN_*. Không chắc thì ghi lý do vào cột 'ghi_chu'.",
]

# Nghĩa các quan hệ xuất hiện trong 116 phép ghi (theo định nghĩa Wikidata, rút gọn). A —r→ B.
REL_MEANING = {
    "country of citizenship": "A là công dân của quốc gia B (B phải là một quốc gia, không phải tính từ chỉ quốc tịch).",
    "instance of": "A là một trường hợp cụ thể của loại B (vd. Hà Nội —là một→ thành phố).",
    "position held": "A (người) đã/đang giữ chức vụ B.",
    "product or material produced": "A (công ty, nơi chốn…) làm ra sản phẩm/vật liệu B.",
    "present in work": "A (nhân vật, sự vật hư cấu) xuất hiện trong tác phẩm B.",
    "influenced by": "A chịu ảnh hưởng (tư tưởng, phong cách) từ B. Không phải 'cùng thời' hay 'được so sánh với'.",
    "creator": "B là người tạo ra A (tác phẩm, nhân vật, chương trình).",
    "notable work": "B là tác phẩm nổi bật của A (A là người sáng tác/tạo ra B).",
    "sibling": "A và B là anh chị em ruột (cùng cha mẹ hoặc cùng cha/mẹ). Anh chị em HỌ không tính.",
    "located in the administrative territorial entity": "A nằm trong đơn vị hành chính B (tỉnh, quận, thành phố…).",
    "location": "A ở / diễn ra tại địa điểm B.",
    "participant": "B là bên tham gia sự kiện / hoạt động A.",
    "publication date": "A (tác phẩm, sản phẩm) được phát hành/xuất bản vào thời điểm B.",
    "performer": "B là người trình bày / biểu diễn A (bài hát, vai diễn…).",
    "point in time": "A (sự kiện) xảy ra vào thời điểm B. Áp cho SỰ KIỆN, không áp cho người.",
    "award received": "A đã nhận giải thưởng B.",
    "cast member": "B là diễn viên trong A (phim, chương trình).",
    "parent taxon": "B là đơn vị phân loại ngay trên A (vd. loài A thuộc chi B).",
    "author": "B là tác giả của A (văn bản, bài hát…).",
    "member of sports team": "A (vận động viên) chơi cho đội B.",
    "founded by": "B là người/tổ chức sáng lập A.",
    "has part": "A có thành phần / bộ phận B (ngược với 'là một phần của').",
    "genre": "A thuộc thể loại B.",
    "inception": "A được thành lập / ra đời vào thời điểm B.",
    "participant of": "A đã tham gia sự kiện B.",
    "follows": "A đứng ngay sau B trong một chuỗi (B là cái trước của A).",
    "followed by": "A được tiếp nối bởi B (B là cái sau của A).",
    "country": "A thuộc / nằm ở quốc gia B.",
    "conflict": "A (người, đơn vị quân đội) đã tham gia xung đột / chiến tranh B.",
    "production company": "B là công ty sản xuất A (phim, chương trình).",
    "chairperson": "B là chủ tịch / người đứng đầu tổ chức A.",
    "subclass of": "Mọi thứ thuộc loại A cũng thuộc loại B (A là lớp con của B).",
    "residence": "A (người) sống / cư trú tại B.",
    "military branch": "A thuộc quân chủng / lực lượng B.",
    "member of": "A là thành viên của tổ chức / nhóm B.",
    "capital of": "A là thủ đô / thủ phủ của B.",
    "location of formation": "A (nhóm, tổ chức) được thành lập tại địa điểm B.",
    "contains administrative territorial entity": "A bao gồm đơn vị hành chính B (ngược với 'thuộc đơn vị hành chính').",
    "child": "B là con của A.",
    "spouse": "A và B là vợ chồng.",
    "screenwriter": "B là người viết kịch bản cho A.",
    "developer": "B là nhà phát triển A (phần mềm, trò chơi).",
    "characters": "B là nhân vật trong A (tác phẩm).",
    "head of government": "B là người đứng đầu chính phủ / chính quyền của A.",
    "replaced by": "A được thay thế bởi B (B kế nhiệm A).",
    "country of origin": "A (tác phẩm, sản phẩm) có xuất xứ từ quốc gia B.",
    "religion": "A theo tôn giáo B.",
}


def main():
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    tr1 = read_json(LAB / "kappa_vi_translations.json")
    tr2 = read_json(LAB / "construction_vi_translations.json")
    rel = {**tr1["relations"], **tr2["relations"]}
    qv = {**tr1["questions"], **tr2["questions"]}
    sv = {**tr1["sentences"], **tr2["sentences"]}
    pid = read_json(DATA / "manual" / "relations.json")["relations"]
    items = read_jsonl(DATA / "benchmarks" / "construction.jsonl")
    prev = {}
    if (LAB / "construction.xlsx").exists():
        from openpyxl import load_workbook

        en = load_workbook(LAB / "construction.xlsx", read_only=True)["label"]
        rows = list(en.iter_rows(values_only=True))
        h = list(rows[0])
        prev = {r[0]: (r[h.index("nhan")], r[h.index("ghi_chu")]) for r in rows[1:] if r[0]}

    R = lambda name: rel.get(name, name)  # noqa: E731
    S = lambda s: sv.get(s.strip(), s.strip())  # noqa: E731
    missing = set()

    def ev_text(ev, vi=True):
        out = []
        for v in ev:
            if v["type"] == "sentence":
                if not v.get("text"):
                    out.append(f"(câu không hợp lệ: {v.get('ref')})")
                    continue
                t = v["text"].strip()
                if vi and t not in sv:
                    missing.add(t)
                out.append(f"[câu: {v.get('title')} #{v.get('sid')}] {S(t) if vi else t}")
            else:
                rn = pid.get(v["relation"], v["relation"])
                src = []
                for s in v["sentences"]:
                    t = s["text"].strip()
                    if vi and t not in sv:
                        missing.add(t)
                    src.append(S(t) if vi else t)
                r = R(rn) if vi else rn
                out.append(f"[cạnh {v['head']} —{r}→ {v['tail']}] " + " ".join(src))
        return "\n".join(out) or "(không có bằng chứng)"

    phase_vi = {"memory": "bước bộ nhớ", "answer": "lúc trả lời"}
    origin_vi = {"AGENT_TEXT": "AGENT_TEXT (từ câu văn)", "AGENT_DERIVED": "AGENT_DERIVED (suy ra từ cạnh có sẵn)"}

    wb = Workbook()
    ws = wb.active
    ws.title = "label"
    head = ["id", "cau_hoi", "luc_ghi", "dau", "quan_he", "duoi", "nguon_goc", "bang_chung", "nhan", "ghi_chu",
            "EN_cau_hoi", "EN_quan_he", "EN_bang_chung"]
    ws.append(head)
    for c in items:
        w = c["write"]
        lab, note = prev.get(c["id"], (None, None))
        q = c["question"]
        if q not in qv:
            missing.add(q)
        ws.append([c["id"], qv.get(q, q), phase_vi.get(c["phase"], c["phase"]), w["head"],
                   f"{R(w['relation_name'])} [{w['relation']}]", w["tail"], origin_vi.get(w["origin"], w["origin"]),
                   ev_text(c["evidence"]), lab, note, q, f"{w['relation']} {w['relation_name']}",
                   ev_text(c["evidence"], vi=False)])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for k, wdt in {"A": 8, "B": 40, "C": 12, "D": 24, "E": 28, "F": 24, "G": 18, "H": 80, "I": 14, "J": 28,
                   "K": 30, "L": 18, "M": 50}.items():
        ws.column_dimensions[k].width = wdt
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    dv = DataValidation(type="list", formula1='"SUPPORTED,UNSUPPORTED,WRONG"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"I2:I{ws.max_row}")
    ws.freeze_panes = "B2"

    g = wb.create_sheet("huong_dan")
    for line in GUIDE_VI:
        g.append([line])
    g.column_dimensions["A"].width = 150
    qr = wb.create_sheet("quan_he")
    qr.append(["quan_he", "nghia (A —quan hệ→ B)"])
    for name, meaning in REL_MEANING.items():
        qr.append([R(name), meaning])
    for cell in qr[1]:
        cell.font = Font(bold=True)
    qr.column_dimensions["A"].width = 55
    qr.column_dimensions["B"].width = 100

    if OUT.exists() and "--force" not in sys.argv:
        raise SystemExit(f"{OUT} đã có (có thể đã gán nhãn). Dùng --force để tạo lại.")
    wb.save(OUT)
    print(f"→ {OUT}: {ws.max_row - 1} dòng; chép sẵn {sum(1 for v in prev.values() if v[0])} nhãn từ bản tiếng Anh;"
          f" {len(missing)} chuỗi chưa có bản dịch (giữ tiếng Anh)")


if __name__ == "__main__":
    main()
