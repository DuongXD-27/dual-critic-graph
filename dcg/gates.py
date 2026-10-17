"""Hai cổng kiểm tra (DECISIONS D7). Giao diện cố định; critic thật sau này chỉ cần cài lớp mới.

traversal_gate(question, path, action)        -> {"verdict": ACCEPT|REJECT|STOP, "reason": str}
construction_gate(write, evidence, provenance) -> {"verdict": ACCEPT|REJECT, "reason_code": str}

Critic KHÔNG nhận lời giải thích của agent.
"""
from __future__ import annotations

TRAVERSAL_VERDICTS = ("ACCEPT", "REJECT", "STOP")
CONSTRUCTION_VERDICTS = ("ACCEPT", "REJECT")


class AcceptAllGates:
    """Baseline không critic: mọi bước duyệt và mọi phép ghi đều được chấp nhận."""

    name = "accept_all"

    def traversal_gate(self, question: str, path: list, action: dict) -> dict:
        return {"verdict": "ACCEPT", "reason": "baseline"}

    def construction_gate(self, write: dict, evidence: list, provenance: dict) -> dict:
        return {"verdict": "ACCEPT", "reason_code": "baseline"}


GATES = {AcceptAllGates.name: AcceptAllGates}
