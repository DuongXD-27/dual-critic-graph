"""Đối chiếu data/manual/relations.json với tập PID thực tế trong Re²-DocRED.

  python scripts/check_relations.py data/raw/re2-docred/dataset
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcg.common import load_relations, read_json  # noqa: E402


def main(dataset_dir):
    used = set()
    for f in sorted(Path(dataset_dir).glob("re2docred_*_re.json")):
        for doc in read_json(f):
            used.update(lab["r"] for lab in doc["labels"])
    ours = set(load_relations())
    print(f"Re²-DocRED: {len(used)} PID; relations.json: {len(ours)} PID")
    print("Thiếu trong relations.json:", sorted(used - ours) or "không")
    print("Thừa trong relations.json:", sorted(ours - used) or "không")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/raw/re2-docred/dataset")
