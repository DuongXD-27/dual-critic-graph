"""Tiện ích dùng chung: đường dẫn, đọc/ghi JSON (luôn UTF-8 vì Windows mặc định cp1252), chuẩn hoá tên."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

ENTITY_TYPES = ["PER", "ORG", "LOC", "TIME", "NUM", "MISC"]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def append_jsonl(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def norm(name: str) -> str:
    """Chuẩn hoá tên để so khớp: chữ thường, gộp khoảng trắng, bỏ khoảng trắng thừa trước dấu câu."""
    s = re.sub(r"\s+", " ", str(name)).strip().lower()
    s = re.sub(r"\s+([,.;:!?)])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    return s


def load_relations(path=None) -> dict:
    return read_json(path or DATA / "manual" / "relations.json")["relations"]


def relation_list_text(rels: dict) -> str:
    return "\n".join(f"{pid}: {name}" for pid, name in rels.items())
