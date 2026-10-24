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
# sao chép .env.example thành .env rồi điền OPENCODE_API_KEY (DeepSeek V4.1 Flash qua OpenCode Go)
python tests/test_offline.py
python scripts/smoke_llm.py
python scripts/build_graphs.py                    # cần data/raw/hotpotqa/hotpot_dev_distractor_v1.json
python scripts/run_agent.py --run-name <tên>    # bản thử: mỗi câu một đồ thị

# đồ thị chung (D12): một đồ thị cho 200 câu, agent chạy lần lượt, phép ghi được giữ
python scripts/build_shared_kg.py --select-only    # chọn câu + gộp kho, chưa gọi LLM
python scripts/build_shared_kg.py
python scripts/run_agent.py --run-name shared-v2 --graph data/interim/shared/graph.json
```
