"""Kiểm tra nhanh key + endpoint trước khi chạy dài: 1 lời gọi JSON, 1 lời gọi công cụ. Không dùng cache.

  .venv\\Scripts\\python scripts\\smoke_llm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.llm import LLM, parse_json  # noqa: E402

llm = LLM(use_cache=False)
print("Cấu hình:", llm.info())

try:
    names = sorted(m.id for m in llm.client.models.list())
    print("Model có thể dùng (lọc 'flash'):", [n for n in names if "flash" in n] or names)
except Exception as e:  # noqa: BLE001
    print("Không liệt kê được model:", e)

r = llm.chat([{"role": "user", "content": 'Return JSON {"ok": true}.'}], json_mode=True)
print("JSON mode:", parse_json(r["content"]))

tools = [{"type": "function", "function": {
    "name": "answer", "description": "Give the final answer.",
    "parameters": {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}}}]
r = llm.chat([{"role": "user", "content": "What is 2+2? Use the answer tool."}], tools=tools)
print("Tool call:", r["tool_calls"])
print("OK" if r["tool_calls"] else "CẢNH BÁO: model không gọi công cụ")
