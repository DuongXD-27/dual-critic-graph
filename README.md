# dual-critic-graph

Đồ án IT5024E – Graduation Research II: kiểm chứng hai giai đoạn (Traversal Critic, Construction Critic) cho Agentic GraphRAG tự cập nhật.

Nguồn chuẩn: đề xuất đề tài + [`docs/DECISIONS.md`](docs/DECISIONS.md) (mọi quyết định thiết kế, lý do và quan sát).

## Cấu trúc
```
dcg/        lõi: đồ thị, trích xuất, agent, hai cổng critic, client LLM
scripts/    build_graphs.py, run_agent.py, smoke_llm.py, check_relations.py
tests/      test_offline.py (chạy không cần mạng, dùng LLM giả)
data/       manual/ (relations.json), interim/ (câu hỏi + đồ thị), runs/ (log từng lần chạy)
            raw/ và cache/ không đưa lên git
```

## Chạy
```
pip install -r requirements.txt
# .env ở gốc repo: GEMINI_API_KEY=... (hoặc DCG_API_KEY_ENV / DCG_BASE_URL / DCG_MODEL, xem dcg/llm.py)
python tests/test_offline.py
python scripts/smoke_llm.py
python scripts/build_graphs.py                    # cần data/raw/hotpotqa/hotpot_dev_distractor_v1.json
python scripts/run_agent.py --run-name <tên>
```
