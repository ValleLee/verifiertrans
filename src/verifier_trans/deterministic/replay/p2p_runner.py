#!/usr/bin/env python3
"""Run exactly prepared Python test node ids through the native pytest runner."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pytest


class ExactNodeFilter:
    def __init__(self, allowed: set[str]):
        self.allowed = allowed
        self.seen: set[str] = set()
        self.selected: list[str] = []

    def pytest_collection_modifyitems(self, config, items):  # noqa: ANN001
        kept = []
        for item in items:
            self.seen.add(item.nodeid)
            if item.nodeid in self.allowed:
                kept.append(item)
                self.selected.append(item.nodeid)
        items[:] = kept


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("selectors", type=Path)
    parser.add_argument("--group", choices=("pass_to_pass", "fail_to_pass"), default="pass_to_pass")
    args = parser.parse_args()
    document = json.loads(args.selectors.read_text(encoding="utf-8"))
    nodes = list((document.get(args.group) or {}).get("resolved") or [])
    allowed = {str(node) for node in nodes if str(node).strip()}
    if not allowed:
        print("No prepared P2P nodes; nothing to run.")
        return 0
    files = sorted({node.split("::", 1)[0].split("|", 1)[0] for node in allowed})
    if any(not path for path in files):
        print("P2P node has no test file", file=sys.stderr)
        return 2
    os.chdir("/app")
    plugin = ExactNodeFilter(allowed)
    rc = pytest.main(["-q", *files], plugins=[plugin])
    missing = sorted(allowed - plugin.seen)
    if missing:
        print("Missing prepared P2P nodes after collection:", file=sys.stderr)
        for node in missing:
            print(f"  {node}", file=sys.stderr)
        return 2
    if len(plugin.selected) != len(allowed):
        print(f"P2P selection mismatch: selected={len(plugin.selected)} expected={len(allowed)}", file=sys.stderr)
        return 2
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
