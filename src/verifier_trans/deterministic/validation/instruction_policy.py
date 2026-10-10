"""Deterministic audit for solver-facing instruction coupling."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# These are construction/test artifacts, not solver-facing contracts.
_HARD_PATTERNS = {
    "absolute_path": re.compile(r"(?:^|[\s(`])/(?:app|workspace|tmp|home|lg-home|tests)(?:[/\s)`]|$)", re.I),
    "historical_selector": re.compile(r"(?:^|[\s`])(?:test/|tests/|[A-Za-z0-9_./-]+\.(?:py|go|js|jsx|ts|tsx))::", re.I),
    "gold_or_layout": re.compile(r"\b(?:gold[- ]specific|reference[- ]solution|exact file layout|file layout|mock call shape|AST scan|AST/name)\b", re.I),
}

# Visibility is a legitimate public contract for encapsulation tasks, so it is
# advisory rather than an automatic schema failure. The Semantic Judge decides
# whether the F2P evidence really supports it.
_VISIBILITY = re.compile(r"\b(?:package[- ]private|unexported|private (?:type|class|constructor|method)|low[- ]level (?:method|client)|concrete (?:http )?client type)\b", re.I)


def audit_instruction_scope(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    hard: list[str] = []
    for name, pattern in _HARD_PATTERNS.items():
        if pattern.search(text):
            hard.append(name)
    advisory = ["visibility_binding"] if _VISIBILITY.search(text) else []
    return {
        "status": "FAIL" if hard else "PASS",
        "hard_errors": hard,
        "advisories": advisory,
        "instruction_bytes": len(text.encode("utf-8")),
    }
