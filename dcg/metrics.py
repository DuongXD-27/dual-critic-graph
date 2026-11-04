"""EM/F1 theo cách chấm chuẩn của HotpotQA."""
from __future__ import annotations

import re
import string
from collections import Counter


def normalize_answer(s: str) -> str:
    s = (s or "").lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def exact_match(pred: str, gold: str) -> float:
    return float(normalize_answer(pred) == normalize_answer(gold))


def f1(pred: str, gold: str) -> float:
    p, g = normalize_answer(pred), normalize_answer(gold)
    if p in ("yes", "no", "noanswer") or g in ("yes", "no", "noanswer"):
        return float(p == g)
    pt, gt = p.split(), g.split()
    common = Counter(pt) & Counter(gt)
    same = sum(common.values())
    if same == 0:
        return 0.0
    prec, rec = same / len(pt), same / len(gt)
    return 2 * prec * rec / (prec + rec)


def contains_gold(pred: str, gold: str) -> bool:
    """Đáp án chuẩn nằm trọn trong câu trả lời (theo từ, sau chuẩn hoá). Dùng vì agent hay trả lời cả câu dài,
    khiến EM/F1 chấm sai. yes/no: từ đầu tiên của câu trả lời phải là yes/no đó."""
    p, g = normalize_answer(pred), normalize_answer(gold)
    if not g:
        return False
    if g in ("yes", "no"):
        return p.split()[:1] == [g]
    return f" {g} " in f" {p} "
