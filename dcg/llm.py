"""Client LLM: DeepSeek V4.1 Flash qua OpenCode Go (endpoint chat/completions tương thích OpenAI) — DECISIONS D2.

.env ở gốc repo:
  OPENCODE_API_KEY   key OpenCode Go (bắt buộc)
  DCG_MODEL          model trên OpenCode Go (mặc định deepseek-v4.1-flash; critic sau này có thể chọn model khác họ)
  DCG_TEMPERATURE    mặc định 0
  DCG_MIN_INTERVAL   số giây tối thiểu giữa hai lần BẮT ĐẦU request (mặc định 1)
Biến môi trường thật được ưu tiên hơn .env.

Theo yêu cầu của OpenCode Go, client gửi User-Agent riêng và header x-opencode-session cho mỗi cuộc hội thoại.
Mọi phản hồi được cache theo hash(base_url, model, temperature, messages, tools) trong data/cache/llm/
→ chạy lại không tốn request và cho kết quả y hệt.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

from .common import DATA, ROOT

BASE_URL = "https://opencode.ai/inference/go/openai/v1"
API_KEY_ENV = "OPENCODE_API_KEY"
DEFAULT_MODEL = "deepseek-v4.1-flash"
USER_AGENT = "dual-critic-graph/0.1"
SESSION_HEADER = "x-opencode-session"


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
        key = os.environ.get(API_KEY_ENV)
        if not key:
            raise SystemExit(f"Thiếu {API_KEY_ENV}: thêm dòng {API_KEY_ENV}=... vào file .env ở gốc repo.")
        self.base_url = BASE_URL
        self.model = model or os.environ.get("DCG_MODEL", DEFAULT_MODEL)
        self.temperature = float(os.environ.get("DCG_TEMPERATURE", "0")) if temperature is None else temperature
        self.min_interval = float(os.environ.get("DCG_MIN_INTERVAL", "1"))
        self.use_cache = use_cache
        self.cache_dir = cache_dir or DATA / "cache" / "llm"
        self.client = OpenAI(api_key=key, base_url=self.base_url, default_headers={"User-Agent": USER_AGENT})
        self._last_call = 0.0
        self._lock = threading.Lock()  # an toàn khi gọi song song (--workers): giãn cách + thống kê
        self.stats = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def info(self) -> dict:
        return {"model": self.model, "base_url": self.base_url, "temperature": self.temperature}

    def _key(self, payload) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def chat(self, messages, tools=None, json_mode=False, session_id=None) -> dict:
        """Trả về {"content": str|None, "tool_calls": [{"id","name","arguments"}]}.
        session_id: mã ổn định cho một cuộc hội thoại (một lượt agent, một lô trích xuất).
        Chỉ gửi trong header, không ảnh hưởng cache. An toàn khi gọi từ nhiều luồng."""
        payload = {"base_url": self.base_url, "model": self.model, "temperature": self.temperature, "messages": messages,
                   "tools": tools, "json_mode": json_mode}
        path = self.cache_dir / f"{self._key(payload)}.json"
        if self.use_cache and path.exists():
            with self._lock:
                self.stats["cache_hits"] += 1
            with open(path, encoding="utf-8") as f:
                return json.load(f)

        kwargs = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if session_id:
            kwargs["extra_headers"] = {SESSION_HEADER: str(session_id)}
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
        with self._lock:
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
            with self._lock:  # giãn cách thời điểm BẮT ĐẦU các request, kể cả khi nhiều luồng
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
                        "      Nếu OpenCode báo quá tải kéo dài: thử lại sau hoặc giảm --workers.") from None
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
