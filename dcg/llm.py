"""Client LLM qua giao diện OpenAI (mặc định trỏ tới Gemini).

Đổi nhà cung cấp chỉ bằng biến môi trường:
  DCG_API_KEY_ENV  tên biến chứa key      (mặc định GEMINI_API_KEY)
  DCG_BASE_URL     endpoint tương thích OpenAI (mặc định Gemini)
  DCG_MODEL        tên model               (mặc định gemini-3.8-flash)
  DCG_TEMPERATURE  nhiệt độ                (mặc định 0)
  DCG_MIN_INTERVAL số giây tối thiểu giữa 2 lần gọi (mặc định 4, hợp gói miễn phí)

Biến có thể đặt trong file .env ở gốc repo (KEY=VALUE mỗi dòng); biến môi trường thật được ưu tiên hơn.

Mọi phản hồi được cache theo hash(model, temperature, messages, tools) trong data/cache/llm/
→ chạy lại không tốn request và cho kết quả y hệt.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from .common import DATA, ROOT

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-3.8-flash"  # 2026-10-16: gemini-2.5-flash không còn cấp cho người dùng mới


def load_dotenv(path=None):
    """Nạp .env ở gốc repo vào os.environ (không ghi đè biến đã có). Không cần thư viện ngoài."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().removeprefix("export ").strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


class LLM:
    def __init__(self, model=None, temperature=None, use_cache=True, cache_dir=None):
        from openai import OpenAI  # import muộn để test offline không cần key

        load_dotenv()
        key_env = os.environ.get("DCG_API_KEY_ENV", "GEMINI_API_KEY")
        key = os.environ.get(key_env)
        if not key:
            raise SystemExit(f"Thiếu {key_env}: thêm dòng {key_env}=... vào file .env ở gốc repo.")
        self.base_url = os.environ.get("DCG_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.environ.get("DCG_MODEL", DEFAULT_MODEL)
        self.temperature = float(os.environ.get("DCG_TEMPERATURE", "0")) if temperature is None else temperature
        self.min_interval = float(os.environ.get("DCG_MIN_INTERVAL", "4"))
        self.use_cache = use_cache
        self.cache_dir = cache_dir or DATA / "cache" / "llm"
        self.client = OpenAI(api_key=key, base_url=self.base_url)
        self._last_call = 0.0
        self.stats = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def info(self) -> dict:
        return {"model": self.model, "base_url": self.base_url, "temperature": self.temperature}

    def _key(self, payload) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def chat(self, messages, tools=None, json_mode=False) -> dict:
        """Trả về {"content": str|None, "tool_calls": [{"id","name","arguments"}]}."""
        payload = {"base_url": self.base_url, "model": self.model, "temperature": self.temperature, "messages": messages,
                   "tools": tools, "json_mode": json_mode}
        path = self.cache_dir / f"{self._key(payload)}.json"
        if self.use_cache and path.exists():
            self.stats["cache_hits"] += 1
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        kwargs = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        resp = self._call_with_retry(kwargs)
        msg = resp.choices[0].message
        out = {
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                for tc in (msg.tool_calls or [])
            ],
        }
        if resp.usage:
            self.stats["prompt_tokens"] += resp.usage.prompt_tokens or 0
            self.stats["completion_tokens"] += resp.usage.completion_tokens or 0
        self.stats["calls"] += 1
        if self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False)
        return out

    def _call_with_retry(self, kwargs, max_tries=6):
        import openai

        delay = 10.0
        for attempt in range(max_tries):
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            try:
                return self.client.chat.completions.create(**kwargs)
            except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError) as e:
                if attempt == max_tries - 1:
                    detail = getattr(e, "message", str(e))
                    raise LLMUnavailable(
                        f"\n[llm] Dừng: {type(e).__name__} sau {max_tries} lần thử ({self.model}).\n"
                        f"      {detail}\n"
                        "      Các lần gọi đã xong nằm trong cache: chạy lại đúng lệnh này để tiếp tục.\n"
                        "      Nếu lỗi quá tải (503) kéo dài: thử lại sau, hoặc đổi DCG_MODEL / nhà cung cấp trong .env.") from None
                print(f"  [llm] {type(e).__name__}, thử lại sau {delay:.0f}s")
                time.sleep(delay)
                delay *= 2


class LLMUnavailable(SystemExit):
    """Nhà cung cấp lỗi kéo dài sau nhiều lần thử. Dừng gọn; chạy lại lệnh sẽ tiếp tục nhờ cache."""


def parse_json(text: str):
    """Đọc JSON từ phản hồi LLM, chịu được khối ```json ... ```."""
    if text is None:
        raise ValueError("phản hồi rỗng")
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return json.loads(t)
