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
- **LLM (từ 2026-10-20): `deepseek-v4.1-flash` qua OpenCode Go**, endpoint chat/completions tương thích OpenAI, thư viện `openai`. Endpoint, tên header và User-Agent cố định trong `dcg/llm.py`; `.env` chỉ cần `OPENCODE_API_KEY` (đã gitignore, không bao giờ commit). `DCG_MODEL` để chọn model khác trên OpenCode Go (dùng cho critic khác họ model).
- 2026-10-24: xoá code của các nhà cung cấp cũ (Gemini, proxy) khỏi `dcg/llm.py`, `.env`, README. Lịch sử bên dưới giữ để giải thích baseline-v1/v2.
- Mỗi lần chạy lưu: model, prompt version, temperature, thời điểm.
- 2026-10-16: Gemini trực tiếp quá tải (503) → gọi `gemini-3.8-flash` qua proxy tương thích OpenAI (cấu hình trong `.env`). Proxy là bên thứ ba: không đảm bảo model thật phía sau → mọi lần chạy đều lưu `base_url` + `model`; cache tách theo `base_url`.
- 2026-10-20: chuyển sang **OpenCode Go**, model `deepseek-v4.1-flash` (endpoint chat/completions; OpenCode xác nhận cho phép dùng cho nghiên cứu). Client gửi `User-Agent: dual-critic-graph/0.1` và header `x-opencode-session` = một mã cho mỗi cuộc hội thoại (mỗi lượt agent, mỗi đoạn trích xuất), theo yêu cầu của OpenCode. Đồ thị chung dựng lại toàn bộ bằng model này (không trộn với ~1.100 phản hồi Gemini-proxy đã có).
- Về sau: critic LLM nên khác họ model với agent (tránh cùng mù một kiểu lỗi) → chọn model họ khác trên OpenCode Go qua `DCG_MODEL`.

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
- ~~Phạm vi đồ thị: mỗi câu hỏi một đồ thị (10 đoạn của câu đó).~~ Chỉ dùng cho bản thử baseline-v1/v2. **Thay bằng D12 (2026-10-17): một đồ thị chung.**
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
- `action.type` = `follow` (đi theo một cạnh) hoặc `start` (xuất phát tại thực thể trong câu hỏi, D14). Cả hai đều qua `traversal_gate`.

## D8. Nhãn đúng
- **Không bao giờ** lấy hành vi agent làm nhãn đúng. Nhãn đến từ: dữ liệu gốc, quy tắc xác định từ dữ liệu gốc, hoặc gán tay.
- Quy tắc sơ bộ cho Traversal:
  - provenance của cạnh có trong `supporting_facts` → ACCEPT; không có → REJECT;
  - đường đi đã phủ hết `supporting_facts` → STOP.
- Lỗ hổng đã biết: một câu bằng chứng sinh cả cạnh cần lẫn cạnh thừa (vd. *nhà sản xuất → Donna Gigliotti*). Hướng sửa: thêm điều kiện cạnh nằm trên đường từ thực thể trong câu hỏi tới đáp án.
- RQ0a trả lời bằng: quy tắc gán ~100 tình huống, người gán tay độc lập cùng 100 tình huống, tính κ. Không thể dùng LLM làm người gán thứ hai (vòng lặp tự chấm).

## D9. Quan sát lỗi bền vững
*(2026-10-17: với đồ thị chung D12, câu hỏi tiếp theo không còn cần thiết — câu sau tự đi qua cạnh câu trước ghi. Giữ mục này cho chế độ mỗi câu một đồ thị.)*
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
3. ~~**`start_at` vẫn cho tới mọi nút nhưng qua `traversal_gate`**~~ → **thay bằng D14** (không còn nhảy). (`action.type = start`), log ghi `start_in_question` = tên nút (bỏ phần trong ngoặc) có trong câu hỏi không. Không cấm nhảy: nhảy nhờ trí nhớ model là hành vi thật, là một loại lỗi duyệt cần critic chấm.
   Nút xuất phát hợp lệ = thực thể được nhắc trong câu hỏi (topic entity). Hợp lệ ≠ tối ưu: vd. xuất phát từ CBS ra đúng đáp án chỉ vì đồ thị nhỏ, bỏ qua điều kiện "diễn viên trong Strange Fruit".
4. **Bước cập nhật bộ nhớ sau khi trả lời:** agent được hỏi ghi các sự kiện đã dùng mà đồ thị chưa có; chỉ được gọi `add_edge` (tối đa 8 lần). Phép ghi lưu `phase = answer | memory`.
   Lý do: baseline-v1 có 0/20 phép ghi khi việc ghi chỉ là tuỳ chọn. Hệ agent có bộ nhớ thường có bước này.

## D12. Một đồ thị chung cho 200 câu hỏi (2026-10-17)
**Lý do:** với mỗi câu một đồ thị, đồ thị bị bỏ sau mỗi câu → cạnh sai không bao giờ được câu khác dùng → lỗi bền vững *không thể xảy ra về mặt cấu trúc*, trong khi đó là câu hỏi tổng thể của đề tài. Ngoài ra 10 đoạn được chọn sẵn (luôn chứa đủ đoạn đáp án) làm bài toán dễ hơn thực tế nhiều; thực tế là một đồ thị lớn có trước, phục vụ nhiều câu hỏi.
- **Kho văn bản** = hợp các đoạn của 200 câu HotpotQA dev (distractor), bỏ trùng theo tiêu đề. Đồ thị dựng **một lần** từ kho, độc lập với câu hỏi.
- **Chọn câu theo cụm** (`--select cluster`): xen kẽ 1 câu ngẫu nhiên với 1 câu có đoạn bằng chứng đã nằm trong kho. Đo trước: chọn ngẫu nhiên 200 câu → chỉ 2/1.990 tiêu đề dùng chung, 1/200 câu có đoạn bằng chứng ở câu khác (đồ thị = 200 đảo rời); theo cụm → 185 tiêu đề dùng chung, 65/200 câu. Bản cài đặt cuối (ưu tiên câu có *đoạn bằng chứng* đã nằm trong kho), seed 0: 149 bridge + 51 comparison, 1.994 đoạn → **1.839 đoạn duy nhất**, 137 tiêu đề dùng chung, **98/200 câu** có đoạn bằng chứng xuất hiện ở câu khác, 0 xung đột tiêu đề. **Cái giá:** tập câu thiên về thực thể phổ biến → ghi vào threats to validity.
- **Thứ tự trả lời** = thứ tự trong `data/interim/shared/questions.json`. Agent chạy lần lượt trên cùng đồ thị; phép ghi được giữ. Log ghi `agent_edges_used_detail.created_by` → biết câu nào đi qua cạnh do câu trước ghi.
- **Trích xuất `extract-v2`:** prompt không còn danh sách tiêu đề (không có "câu hỏi" khi dựng đồ thị). Liên kết tên → tiêu đề bằng code (`TitleLinker`): khớp đúng tiêu đề → tiêu đề đoạn đang đọc khi bỏ phần trong ngoặc → khớp duy nhất một tiêu đề khi bỏ ngoặc. Nhiều tiêu đề cùng khớp (vd. "Strange Fruit" ~ film/song) → giữ nút riêng, ghi `ambiguous`. Không cố đoán: đây là lỗi hợp nhất thực thể có thật, cần đo.
- Agent đọc được mọi đoạn trong kho, nhưng vẫn chỉ đoạn **đã tới được** (D10). `search_nodes` xếp hạng: trùng tên → bắt đầu bằng → chứa.
- Tiêu đề trùng nhưng nội dung khác giữa hai câu (2 trường hợp khi đo thử): giữ bản đầu, ghi `title_conflicts`.
- Benchmark Traversal (D8) sẽ sinh trên đồ thị chung: nút có nhiều cạnh hơn → tình huống chọn cạnh khó và thật hơn.

## D13. Gộp đoạn khi trích xuất + gọi song song (2026-10-24) → **KHÔNG gộp; 1 đoạn/lần + song song**
**Lý do:** 1.839 request gọi lần lượt mất ~2–3 giờ. Hệ thật không gọi theo từng đoạn ngắn: Microsoft GraphRAG mặc định mẩu ~1.200 token/lần gọi, gọi song song, và thêm lượt "gleaning" để bù phần sót. Chính bài GraphRAG đo trên HotpotQA: mẩu 600 token trích được gần gấp đôi số thực thể so với mẩu 2.400 token → gộp có thể làm sót, phải đo.
- `--workers N`: gọi song song. Kết quả luôn ghép vào đồ thị theo thứ tự kho → đồ thị (kể cả id nút/cạnh) không phụ thuộc thời gian chạy.
- `--per-call K` (`extract-v3-batch`): trộn **thứ tự đoạn** (không trộn câu) với seed cố định, xếp lô ≤ K đoạn và ≤ `--batch-tokens` (1.200) token văn bản. Không gom theo câu hỏi (đồ thị độc lập với câu hỏi, D12; tránh ghép thông tin giữa các đoạn liên quan). Prompt yêu cầu xử lý từng đoạn độc lập, kết quả tách theo đoạn, số câu tính riêng trong từng đoạn → nguồn vẫn `[tiêu đề, số câu]` (D6, D8 không đổi).
- Tiêu đề trả về không thuộc lô → bỏ, ghi `unknown_paragraph`. Đoạn không có trong kết quả → `paragraph_skipped`, **gọi lại riêng** đoạn đó bằng prompt `extract-v2`.
- **Thử nghiệm trước khi dùng** (`--pilot 100 --per-call 8`): 100 đoạn ngẫu nhiên, trích bằng cả hai cách. **Quy tắc chốt trước:** dùng cách gộp nếu bộ ba/đoạn ≥ 90% cách đơn **và** tỷ lệ nghi ngờ không cao hơn quá 2 điểm %. Nếu không đạt: giữ 1 đoạn/lần + `--workers`. Kết quả ghi `data/interim/shared/pilot.json` và vào mục này.
- Model: `deepseek-v4.1-flash` qua OpenCode Go (D2). Một đồ thị chỉ dựng bằng một model và một chế độ trích xuất.
- **Kết quả thử nghiệm** (`pilot.json`, 100 đoạn, gộp 8 đoạn/≤1.200 token, 4 luồng):

  | | 1 đoạn/lần | gộp 8 đoạn |
  |---|---|---|
  | request | 100 | 23 (+8 đoạn bị bỏ sót, gọi lại) |
  | bộ ba/đoạn | **6,86** | 5,43 (= **79%**) |
  | đoạn có ≥1 cạnh | 99% | 95% |
  | tỷ lệ nghi ngờ nguồn | 6,0% | 4,1% |
  | token đầu ra | 246.619 | 166.801 |
  | trùng cạnh giữa hai cách (Jaccard) | 0,60 | |

  Gộp sót ~21% bộ ba (< ngưỡng 90%) → theo quy tắc chốt trước: **`per_call=1` + `--workers`**. Khớp với quan sát của bài GraphRAG (mẩu lớn → trích ít hơn). Không đổi quy tắc sau khi xem kết quả.
- Quan sát phụ: `deepseek-v4.1-flash` là model suy luận — ~2.470 token đầu ra/lần gọi trong khi nội dung trả về chỉ ~200 token → ~90% token đầu ra là suy luận ẩn. Đây là nguyên nhân chính của thời gian (~7,5 giây/đoạn với 4 luồng) và chi phí. Ước tính dựng toàn bộ 1.839 đoạn: ~4,5 triệu token đầu ra ≈ 2,7–5,4 USD (trong hạn mức gói Go).
- 2026-10-24: phản hồi không đọc được JSON → **gọi lại đúng 1 lần** với tin nhắn nhắc "chỉ trả JSON" (thử nghiệm có 1/100 đoạn hỏng JSON). Ghi `parse_retries`.

## D14. Agent chỉ đi theo cạnh; ghi rồi đi tiếp ở ngõ cụt (2026-10-24, agent-v5, thay D11.3)
Lý do: `shared-v1-try` (5 câu, agent-v4) có 10 `start_at`, **0 `follow_edge`** → agent không duyệt đồ thị mà tìm tên + nhảy; không có đường đi thì không có gì cho Traversal Critic chấm.
1. **Xuất phát:** `start_at` chỉ nhận nút có tên trong câu hỏi (bỏ phần ngoặc, so theo từ; chấp nhận sai chính tả nhẹ: tỉ lệ giống ≥ 0,85 trên cửa sổ từ, tên ≥ 5 ký tự; vd. "Bennett"/"Bennet"). Câu comparison xuất phát lần lượt ở từng thực thể. Nút khác → trả lỗi, đếm `starts_refused`.
2. **Di chuyển:** chỉ bằng `follow_edge`. Tăng giới hạn: 8 `follow_edge`, 25 lần gọi công cụ.
3. **Ngõ cụt:** cạnh cần đi bị thiếu → đọc đoạn đã tới được (D10). Câu văn nói sự kiện đó → `add_edge` (qua cổng Construction, `phase = answer`) rồi `follow_edge` theo cạnh vừa ghi. Đây là nơi tự nhiên của chuỗi *ghi sai → đi sai*. Khi ghi, tên được nối với nút có sẵn (trùng tên, hoặc khớp **duy nhất** một tiêu đề sau khi bỏ ngoặc); chặn cạnh tự nối.
4. **Dừng:** tới nút đáp án, hoặc ngõ cụt thật (không cạnh, không câu văn) → trả lời tốt nhất có thể. Bước cập nhật bộ nhớ (D11.4) giữ nguyên.
5. Log: `starts_refused`, `follows_on_own_edges` (đi qua cạnh chính lượt đó ghi); tổng kết có `episodes_following_own_write`. Cạnh tự ghi trong cùng lượt không tính là "dùng lại cạnh của câu trước".

## Quan sát: `shared-v1-try` (2026-10-24, agent-v4, 5 câu)
- 79 giây, 37 lần gọi, 3.608 token đầu ra → 200 câu ≈ 55 phút. 0 `follow_edge`, 10 `start_at` → D14.
- #4 trả lời "Pablo Aimar" thay vì "Claudio Javier López" (lỗi duyệt). Phép ghi (Fyre Festival, P112 founded by, Billy McFarland): câu chỉ nói "organization of the Fyre Festival" → đúng ngoài đời nhưng **bằng chứng chưa đủ** — đúng loại lỗi Construction Critic cần bắt.

## Quan sát: `shared-v2-try` (2026-10-24, agent-v5, 5 câu)
- **D14 có tác dụng:** 6 `follow_edge` (trước: 0); 2 lần nhảy bị chặn (Fyre Festival; Mario Kempes — tên lấy từ trí nhớ model). 1 lần *ghi rồi đi tiếp* (#3: ghi McFarland → Fyre Festival từ câu văn, đi theo cạnh đó tới Great Exuma).
- **Lỗi tự nhiên quan sát được:**
  - #1 bước bộ nhớ ghi `AGENT_DERIVED` (Kerensky, P607 conflict, Russian Civil War) từ 2 cạnh **không nối nhau** (Kerensky–Russian Revolution 1917; Bolsheviks–Russian Civil War) → bằng chứng không chứng minh được sự kiện. Cạnh này đã vào đồ thị chung.
  - #4 sai (Pablo Aimar thay vì Claudio López): đồ thị không có cạnh từ *Valencia CF* tới đoạn *1998–99 Valencia CF season* hay tới Claudio López (câu "lethal striker Claudio López" không được trích) → ngõ cụt thật. Agent trả lời theo đoạn 2002–03 mà không kiểm điều kiện "chơi tiền đạo".
  - #5 ghi (My Cousin Rachel, P272, Free Range Films) từ 2 câu: "công ty của họ là Free Range Films" + "phim gần nhất là My Cousin Rachel" → suy ra, chưa nói thẳng.
- Câu comparison (#2) và #5 trả lời không cần `follow_edge` (đọc đoạn của 2 nút xuất phát / đáp án hiện ngay trong cạnh của nút xuất phát).
- Sửa chỉ số `answer_grounded`: so theo **từ** thay vì cả chuỗi (#2 bị báo nhầm vì ghép tên + năm). Từ chưa thấy ghi vào `answer_unseen_words` (#3: "bahamas" do model tự thêm).

## Quan sát: đồ thị chung `extract-v2` (2026-10-24)
- `deepseek-v4.1-flash`, 1 đoạn/lần, 8 luồng, ~1,3 giờ; 1.841 request (2 gọi lại vì JSON hỏng; 2 đoạn vẫn hỏng: *Frank Vennes*, *Bambi Hall*); 5,5 triệu token đầu ra (≈3,5 USD giờ thấp điểm).
- **10.530 nút, 12.361 cạnh**; thành phần liên thông lớn nhất 80% số nút; 591 thành phần; 89 nút cô lập. Cờ nghi ngờ nguồn 6,5%. Độ phủ câu bằng chứng 87,4%.
- Liên kết tên → tiêu đề: 10.682 khớp đúng tiêu đề, 212 khớp sau khi bỏ ngoặc, 34 chủ thể đoạn, **31 mơ hồ**, 14.387 không phải tiêu đề.
- Nút trung tâm: *film* (121, toàn `instance of`), *United States* (105), *studio album*, *song* → nút "lớp" nối các thực thể không liên quan; là nhiễu thật khi duyệt.
- **58/149 câu bridge (39%) có 2 đoạn bằng chứng KHÔNG nối nhau trong ≤3 bước** (57 nối trực tiếp, 25 qua 2 bước, 9 qua 3 bước). Nguyên nhân (đọc tự động): 26 — câu có nhắc thực thể cầu nối nhưng không trích được cạnh tới nó; 20 — câu không nhắc đúng tên (bí danh, cách gọi khác, nối qua thực thể thứ ba); 12 — có trích thực thể nhưng cạnh không chạm nút chủ thể của đoạn.
  → Với ~39% câu bridge, agent **không thể** trả lời chỉ bằng duyệt đồ thị: phải đọc văn bản rồi nhảy tới thực thể cầu nối. Đây cũng là chỗ tự nhiên để agent **ghi cạnh còn thiếu** (`AGENT_TEXT`) — điều kiện để quan sát lỗi bền vững. Nhãn Traversal (D8) cho các câu này chỉ có một phần đường đi.
- Hệ quả cho log (D11.3, 2026-10-24; từ D14 luôn = `question`): mỗi `start_at` ghi thêm `start_grounded_by` = `question` | `edges_seen` | `text_read` | `null`. Chỉ `null` (tên chưa từng xuất hiện trong những gì agent đã thấy) mới là nhảy nhờ trí nhớ model; nhảy theo tên vừa đọc trong văn bản là hợp lệ khi đồ thị thiếu cạnh. Tổng kết có `starts_ungrounded`.

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
| O2 | Bộ công cụ của agent + giới hạn | `search_nodes`, `start_at` (chỉ thực thể trong câu hỏi) + `follow_edge` (qua traversal_gate), `get_edges` (nút hiện tại), `read_paragraph`, `add_edge` (qua construction_gate), `answer`; tối đa 8 `follow_edge`, 2 đoạn văn (D10), 25 lần gọi công cụ, 8 `add_edge` ở bước bộ nhớ (D11, D14) |
| O3 | Model | **Đã chốt** (D2): `deepseek-v4.1-flash` qua OpenCode Go. baseline-v1/v2 đã chạy bằng `gemini-3.8-flash` qua proxy (ghi trong `run.json`) |
| O4 | Agent được ghi những suy diễn nào (vd. cạnh tắt 2 bước) | Cho ghi tự do để quan sát; có bước cập nhật bộ nhớ bắt buộc hỏi (D11.4) |
| O6 | Có chủ động xoá bớt cạnh để buộc agent đọc văn bản không | Không; dùng độ thiếu tự nhiên của trích xuất, xem lại sau khi đọc trace |
| O5 | Bảng tên tiếng Anh cho 96 PID (để đưa vào prompt) | Lấy nhãn Wikidata, lưu `data/manual/relations.json` |

## Môi trường và dữ liệu thô
- Script chạy bằng `.venv` (Python 3.11) trên Windows. Môi trường của Claude không gọi được API LLM và không tải được HotpotQA → chạy LLM do người dùng thực hiện.
- `data/` đã xoá (2026-10-16). HotpotQA: tải tay `hotpot_dev_distractor_v1.json`. Re²-DocRED: clone lại khi làm benchmark Construction.
- `data/manual/relations.json` lập từ danh sách 96 quan hệ của DocRED (Re²-DocRED dùng cùng bộ); khi có lại Re²-DocRED phải chạy đối chiếu (`scripts/check_relations.py`).

## Việc tiếp theo
- [x] Code bước 1–2: `dcg/` (đồ thị, trích xuất, agent, cổng, LLM), `scripts/build_graphs.py`, `scripts/run_agent.py`; kiểm thử offline `tests/test_offline.py` đạt
- [x] `data/manual/relations.json` (96 PID + tên)
- [x] API key trong `.env` (đã gitignore; `dcg/llm.py` tự nạp) — hiện là `OPENCODE_API_KEY`
- [x] Cài thư viện, `smoke_llm.py`, tải HotpotQA, `build_graphs.py`
- [x] `run_agent.py --run-name baseline-v1` (agent-v3) → phát hiện lỗi + lối tắt, dẫn tới D11
- [x] `build_graphs.py --force`, `run_agent.py --run-name baseline-v2` (agent-v4) → PR `probe/per-question-agent`
- [x] Code đồ thị chung (D12): `scripts/build_shared_kg.py`, `run_agent.py --graph`; kiểm thử offline đạt
- [x] `build_shared_kg.py --select-only` (1.839 đoạn, 98/200 câu có đoạn bằng chứng ở câu khác)
- [x] Dán key OpenCode vào `.env`
- [ ] `smoke_llm.py`
- [x] `build_shared_kg.py --pilot 100 --per-call 8 --workers 4` → D13: không gộp
- [x] `build_shared_kg.py --force --workers 8` → đồ thị chung (xem mục Quan sát: đồ thị chung)
- [x] `run_agent.py --run-name shared-v1-try --graph data/interim/shared/graph.json --limit 5` (agent-v4) → 0 `follow_edge`, dẫn tới D14
- [x] Code D14 (agent-v5); kiểm thử offline đạt
- [x] `run_agent.py --run-name shared-v2-try --graph data/interim/shared/graph.json --limit 5` → 6 `follow_edge`, D14 đạt
- [ ] `run_agent.py --run-name shared-v2 --graph data/interim/shared/graph.json`
- [ ] Đọc trace: lỗi tự nhiên trong duyệt/ghi; câu nào đi qua cạnh do câu trước ghi, cạnh đó đúng hay sai
