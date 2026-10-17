# DECISIONS — các quyết định đã chốt

Cập nhật: 2026-10-16. File này cùng **đề xuất đề tài** là nguồn chuẩn.
`README.md`, `docs/RESEARCH_SPEC_V1.md`, `docs/DATASET_AUDIT_V1` có thể lỗi thời: chỗ nào mâu thuẫn thì theo file này.
Sửa một quyết định: ghi ngày + lý do ngay dưới mục đó, không xoá nội dung cũ.

---

## D1. Thứ tự làm việc
1. Dựng đồ thị từ HotpotQA.
2. Chạy agent **không có critic** (hai cổng luôn ACCEPT), ghi log.
3. Đọc, gán nhãn tay ~20 trace → chốt taxonomy lỗi + schema mẫu.
4. Dựng benchmark Traversal + Construction theo đúng định dạng log.
5. Xây critic (luật + LLM), đánh giá offline → RQ1, RQ2.
6. *(Mở rộng, làm khi 1–5 xong, cần GVHD đồng ý)* bật critic trong agent, báo cáo dạng thử nghiệm sơ bộ, không kết luận thống kê.

Lý do: thiết kế benchmark từ hành vi thật thay vì suy đoán. Bước 1–2 giới hạn ~1 tuần; agent là công cụ quan sát, không cần trả lời giỏi.

## D2. Công nghệ
- Python 3.11, NetworkX, JSON/JSONL. **Không** Neo4j, **không** LangGraph (không có giá trị nghiên cứu, thêm chỗ hỏng).
- LLM: Gemini qua endpoint tương thích OpenAI, dùng thư viện `openai` → đổi sang DeepSeek/OpenAI chỉ cần sửa `base_url` + tên model.
- API key `GEMINI_API_KEY` đặt trong `.env` ở gốc repo (đã gitignore) hoặc biến môi trường. Không bao giờ commit key.
- Mỗi lần chạy lưu: model, prompt version, temperature, thời điểm.
- 2026-10-16: Gemini trực tiếp quá tải (503) → gọi `gemini-3.8-flash` qua proxy tương thích OpenAI (cấu hình trong `.env`). Proxy là bên thứ ba: không đảm bảo model thật phía sau → mọi lần chạy đều lưu `base_url` + `model`; cache tách theo `base_url`.
- Về sau: critic LLM nên khác họ model với agent (tránh cùng mù một kiểu lỗi). Nếu critic chính thức dùng Gemini thì sửa lại báo cáo (đề xuất ghi DeepSeek/OpenAI).

## D3. Dữ liệu
| Bộ | Vai trò | Ghi chú |
|---|---|---|
| HotpotQA (distractor, dev) | Chạy agent + benchmark Traversal | Bộ duy nhất có câu hỏi. Bắt đầu 20 câu, mở rộng khi pipeline ổn |
| Re²-DocRED | Benchmark Construction; bộ quan hệ cố định | *Tuỳ chọn ở bước 1:* chạy prompt trích xuất trên văn bản Re²-DocRED, so với nhãn gốc → đo tỷ lệ lỗi trích xuất |
| CoDEx | Benchmark Construction (mẫu âm khó) | Chưa dùng ở bước 1–3 |

Chọn câu hỏi HotpotQA: chủ yếu loại *bridge* (có đường đi qua thực thể cầu nối), vài câu *comparison* để quan sát. Mặc định 16 bridge + 4 comparison.

## D4. Dạng đồ thị
- Cạnh = bộ ba **(đầu, quan hệ, đuôi)** + nguồn gốc.
- **Quan hệ: chỉ dùng 96 mã quan hệ Wikidata (PID) của Re²-DocRED** (đã kiểm tra: 96 PID trong train/dev/test). Không có quan hệ tự do. LLM trả quan hệ ngoài danh sách → bỏ cạnh, ghi log.
- Phạm vi đồ thị: **mỗi câu hỏi một đồ thị** (10 đoạn của câu đó). Không gộp thực thể giữa các câu hỏi.
- Phép ghi của agent: chỉ `ADD_EDGE`.
- **Agent có hai nguồn thông tin:** đồ thị + văn bản gốc (10 đoạn của câu hỏi). Đồ thị trích xuất luôn thiếu cạnh; khi thiếu, agent đọc đoạn văn rồi ghi cạnh mới.
  Lý do (2026-10-16): nếu agent chỉ đọc đồ thị thì mọi phép ghi chỉ là cạnh tắt, không thêm thông tin mới → không có lý do để ghi, và không sinh ra loại lỗi "diễn giải sai văn bản" mà Construction Critic nhắm tới.

## D5. Đặt tên nút
1. Mỗi tiêu đề đoạn văn → một nút (điểm neo).
2. Prompt trích xuất nhận kèm danh sách 10 tiêu đề: thực thể trùng tiêu đề thì dùng đúng tên tiêu đề; đại từ / "the film"… thay bằng tiêu đề của đoạn đang đọc.
3. Thực thể khác giữ nguyên tên; chỉ gộp tên giống hệt nhau (sau chuẩn hoá hoa/thường, khoảng trắng).
4. Lỗi gộp nhầm / gộp thiếu là lỗi của đồ thị ban đầu, ghi nhận riêng, không tính cho agent.

## D6. Nguồn gốc cạnh
- Mỗi cạnh lưu `provenance = [[tiêu đề đoạn, số câu], ...]`, **đúng định dạng `supporting_facts`** của HotpotQA để so sánh trực tiếp.
- Mỗi cạnh có `origin`:
  - `EXTRACTED`: sinh khi dựng đồ thị.
  - `AGENT_TEXT`: agent đọc văn bản và ghi sự kiện mới; bằng chứng = các câu `[tiêu đề, số câu]`.
  - `AGENT_DERIVED`: cạnh tắt ghép từ đường đi (vd. A→B→C ⇒ A→C); bằng chứng = id các cạnh đã dùng. Quan hệ ghép vẫn phải thuộc 96 PID.
  - Cạnh do agent ghi lưu thêm id câu hoặc lượt chạy đã tạo ra nó.
- Tác dụng của `origin`: tách lỗi trích xuất khỏi lỗi agent; cổng Construction chỉ áp cho cạnh agent; truy vấn sau sai thì truy ngược được có đi qua cạnh agent không.
- Kiểm tra bằng code: tên đầu hoặc đuôi phải xuất hiện trong câu được trích; không qua → gắn cờ `provenance_suspect`, không xoá.

## D7. Hai cổng (giao diện cố định từ đầu)
```
traversal_gate(question, path, action)         -> {verdict: ACCEPT|REJECT|STOP, reason}
construction_gate(write, evidence, provenance)  -> {verdict: ACCEPT|REJECT, reason_code}
```
- Bộ verdict theo đề xuất (không thêm REPLAN/ABSTAIN lúc này).
- Critic **không** nhận lời giải thích của agent.
- `evidence` = nội dung câu văn được nộp kèm phép ghi (chưa chắc đã hỗ trợ — việc của critic là kiểm tra).
- Bước 2: cả hai cổng luôn trả ACCEPT (= baseline không critic).
- Mỗi lần gọi cổng ghi một dòng JSONL, chính là định dạng mẫu benchmark → critic chạy offline và chạy trong agent dùng cùng giao diện.
- `action.type` = `follow` (đi theo một cạnh) hoặc `start` (xuất phát / nhảy tới một nút, D11). Cả hai đều qua `traversal_gate`.

## D8. Nhãn đúng
- **Không bao giờ** lấy hành vi agent làm nhãn đúng. Nhãn đến từ: dữ liệu gốc, quy tắc xác định từ dữ liệu gốc, hoặc gán tay.
- Quy tắc sơ bộ cho Traversal:
  - provenance của cạnh có trong `supporting_facts` → ACCEPT; không có → REJECT;
  - đường đi đã phủ hết `supporting_facts` → STOP.
- Lỗ hổng đã biết: một câu bằng chứng sinh cả cạnh cần lẫn cạnh thừa (vd. *nhà sản xuất → Donna Gigliotti*). Hướng sửa: thêm điều kiện cạnh nằm trên đường từ thực thể trong câu hỏi tới đáp án.
- RQ0a trả lời bằng: quy tắc gán ~100 tình huống, người gán tay độc lập cùng 100 tình huống, tính κ. Không thể dùng LLM làm người gán thứ hai (vòng lặp tự chấm).

## D9. Quan sát lỗi bền vững
Mỗi câu hỏi một đồ thị → cạnh ghi ở câu này không ảnh hưởng câu khác. Vì vậy mỗi câu hỏi có thêm **một câu hỏi tiếp theo** chạy trên đồ thị đã bị agent sửa, đi qua cạnh vừa ghi.

## D10. Truy cập văn bản của agent (2026-10-16)
- Mỗi lượt trả lời agent được đọc **tối đa 2 đoạn văn khác nhau** (`read_paragraph`); đọc lại đoạn đã đọc không tính. Vượt giới hạn → công cụ trả lỗi, ghi `reads_refused`.
  Lý do: mỗi câu chỉ có 10 đoạn; không giới hạn thì agent có thể đọc hết rồi bỏ qua đồ thị (thành RAG thường) → không còn bước duyệt để kiểm tra.
- 2026-10-17: agent **chỉ được đọc đoạn đã tới được**: tiêu đề của nút đã ghé, hoặc tên đoạn trong `source_paragraphs` của cạnh đã thấy. Bỏ danh sách 10 tiêu đề khỏi prompt (D11).
- Khi xem cạnh (`get_edges`, `start_at`, `follow_edge`), mỗi cạnh hiện `source_paragraphs` = tên các đoạn sinh ra cạnh đó.
  Lý do: khi kẹt ở nút không phải tiêu đề, agent cần biết đoạn nào nhắc tới nút đó. Nguồn gốc là một phần của đồ thị, không phải gian lận. Không hiện `origin` cho agent.
- Theo dõi trong log: `mean_paragraphs_read`, `episodes_hit_read_limit`. Nếu agent gần như luôn chạm giới hạn → xem lại con số 2.

## D11. Quy tắc công cụ của agent (2026-10-17, sau baseline-v1)
Agent chỉ nhận **hướng dẫn + câu hỏi**. Đồ thị và văn bản chỉ truy cập qua công cụ; mọi lần thu thông tin phải để lại một hành động nhìn thấy được.
1. **Bỏ danh sách 10 tiêu đề khỏi prompt.** Lý do: danh sách lộ tên thực thể cầu nối → agent nhảy thẳng tới đó (#13 baseline-v1); hệ thật không có danh sách này.
2. **`get_edges` chỉ trả cạnh của nút hiện tại.** Lý do: trước đó gọi được cho mọi nút → agent "nhìn từ xa" lấy đáp án, không đi bước nào (#19, #20: 0 bước). Muốn xem nút khác phải `follow_edge` hoặc `start_at`.
3. **`start_at` vẫn cho tới mọi nút nhưng qua `traversal_gate`** (`action.type = start`), log ghi `start_in_question` = tên nút (bỏ phần trong ngoặc) có trong câu hỏi không. Không cấm nhảy: nhảy nhờ trí nhớ model là hành vi thật, là một loại lỗi duyệt cần critic chấm.
   Nút xuất phát hợp lệ = thực thể được nhắc trong câu hỏi (topic entity). Hợp lệ ≠ tối ưu: vd. xuất phát từ CBS ra đúng đáp án chỉ vì đồ thị nhỏ, bỏ qua điều kiện "diễn viên trong Strange Fruit".
4. **Bước cập nhật bộ nhớ sau khi trả lời:** agent được hỏi ghi các sự kiện đã dùng mà đồ thị chưa có; chỉ được gọi `add_edge` (tối đa 8 lần). Phép ghi lưu `phase = answer | memory`.
   Lý do: baseline-v1 có 0/20 phép ghi khi việc ghi chỉ là tuỳ chọn. Hệ agent có bộ nhớ thường có bước này.

## Quan sát từ baseline-v1 (2026-10-17)
- Lỗi code đã sửa: tham số `title` của `read_paragraph` bị proxy/Gemini làm rơi (đổi thành `paragraph`); câu trả lời rỗng bị coi là đáp án (giờ nhắc tối đa 2 lần); cờ nghi ngờ nguồn báo nhầm khi đại từ ở đuôi bộ ba.
- 96 quan hệ không biểu diễn được một số đáp án (khoảng cách, số lượng, mô tả) → giới hạn của schema, ghi vào threats to validity.
- Gộp nút theo tên giống hệt (D5) đã gộp nhầm 2 thực thể khác nhau ("Strange Fruit": tiểu thuyết + bài hát).
- Bịa đáp án khi không đọc được văn bản (#10: "Jackie", đúng là "Lynwood").
- EM/F1 không đáng tin cho bản thử: nhiều câu "sai" chỉ khác cách viết ("10"/"ten").

## Quan sát từ baseline-v2 (2026-10-17, agent-v4)
- Trả lời: 20/20 đúng về nội dung (EM 0,7 do khác cách viết). Sau khi sửa chỉ số, 0 câu trả lời bằng kiến thức nền thật (#12 "10"/"ten", #16 diễn đạt khác).
- **Duyệt:** 29 `start_at`, chỉ 7 `follow_edge`. Agent điều hướng bằng *tìm tên + nhảy* thay vì đi theo cạnh. 8 lần nhảy tới nút không có trong câu hỏi: 3 nhờ văn bản vừa đọc, 1 dù cạnh đã hiện sẵn (#10), 4 tên chưa từng thấy (trí nhớ model; #14 nhảy thẳng tới nút đáp án).
- **Ghi:** 10 phép ghi, tất cả ở bước bộ nhớ, tất cả `AGENT_TEXT`, 0 `AGENT_DERIVED`. 5 trùng cạnh đã có; 5 mới: 2 có căn cứ rõ, 2 suy từ tính từ quốc tịch ("Dominican" → Dominican Republic, "Ghanaian" → Ghana), 1 đuôi là tính từ chứ không phải thực thể (Judas Priest, P495, "British").
- Chưa thấy chuỗi *duyệt sai → ghi sai* trên 20 câu.
- Nhãn sơ bộ Traversal (D8) trên 20 câu: 216 tình huống chọn cạnh tại các nút trên đường đúng (114 ACCEPT / 102 REJECT), ~11/câu.

---

## Chưa chốt
| # | Vấn đề | Mặc định tạm |
|---|---|---|
| O1 | Câu hỏi tiếp theo (D9) tạo bằng tay hay LLM | Tự viết tay cho 20 câu đầu |
| O2 | Bộ công cụ của agent + giới hạn | `search_nodes`, `start_at` + `follow_edge` (qua traversal_gate), `get_edges` (nút hiện tại), `read_paragraph`, `add_edge` (qua construction_gate), `answer`; tối đa 6 `follow_edge`, 2 đoạn văn (D10), 20 lần gọi công cụ, 8 `add_edge` ở bước bộ nhớ (D11) |
| O3 | Tên model Gemini | `gemini-3.8-flash` (2026-10-16: `gemini-2.5-flash` không còn cấp cho người dùng mới). Đổi qua `DCG_MODEL` trong `.env` |
| O4 | Agent được ghi những suy diễn nào (vd. cạnh tắt 2 bước) | Cho ghi tự do để quan sát; có bước cập nhật bộ nhớ bắt buộc hỏi (D11.4) |
| O6 | Có chủ động xoá bớt cạnh để buộc agent đọc văn bản không | Không; dùng độ thiếu tự nhiên của trích xuất, xem lại sau khi đọc trace |
| O5 | Bảng tên tiếng Anh cho 96 PID (để đưa vào prompt) | Lấy nhãn Wikidata, lưu `data/manual/relations.json` |

## Môi trường và dữ liệu thô
- Script chạy bằng `.venv` (Python 3.11) trên Windows. Môi trường của Claude không gọi được Gemini và không tải được HotpotQA → chạy LLM do người dùng thực hiện.
- `data/` đã xoá (2026-10-16). HotpotQA: tải tay `hotpot_dev_distractor_v1.json`. Re²-DocRED: clone lại khi làm benchmark Construction.
- `data/manual/relations.json` lập từ danh sách 96 quan hệ của DocRED (Re²-DocRED dùng cùng bộ); khi có lại Re²-DocRED phải chạy đối chiếu (`scripts/check_relations.py`).

## Việc tiếp theo
- [x] Code bước 1–2: `dcg/` (đồ thị, trích xuất, agent, cổng, LLM), `scripts/build_graphs.py`, `scripts/run_agent.py`; kiểm thử offline `tests/test_offline.py` đạt
- [x] `data/manual/relations.json` (96 PID + tên)
- [x] Gemini API key trong `.env` (đã gitignore; `dcg/llm.py` tự nạp)
- [x] Cài thư viện, `smoke_llm.py`, tải HotpotQA, `build_graphs.py`
- [x] `run_agent.py --run-name baseline-v1` (agent-v3) → phát hiện lỗi + lối tắt, dẫn tới D11
- [ ] `build_graphs.py --force` (tính lại cờ nghi ngờ; lấy từ cache, không gọi LLM)
- [ ] `run_agent.py --run-name baseline-v2` (agent-v4)
- [ ] (O1) viết `data/manual/followups.json`: `{"<qid>": [{"question": "...", "answer": "..."}]}` rồi chạy lại với run-name mới
- [ ] Đọc, gán nhãn tay ~20 trace (`data/runs/<run>/episodes.jsonl`, `gates.jsonl`)
