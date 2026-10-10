#!/usr/bin/env python3
"""Small framework-owned Go selector adapter.

Go's native runner accepts a regular expression rather than pytest-style node
ids.  The adapter groups selectors by package directory and passes the test
names to `go test`; it never invents a passing result.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


_BARE_TEST_NAME = re.compile(r"(?:Test|Benchmark|Fuzz|Example)[A-Za-z0-9_]+\Z")
_GO_TEST_DECLARATION = re.compile(r"^\s*func\s+((?:Test|Benchmark|Fuzz|Example)[A-Za-z0-9_]+)\s*\(", re.MULTILINE)
_SKIP_DIRS = {".git", "node_modules", "vendor", "verifier"}


def _resolve_bare_names(root: Path, names: set[str]) -> dict[str, str]:
    """Resolve bare test IDs to a unique package in the replay checkout."""
    matches: dict[str, set[str]] = {name: set() for name in names}
    for directory, dirs, files in os.walk(root):
        dirs[:] = [item for item in dirs if item not in _SKIP_DIRS]
        for filename in files:
            if not filename.endswith("_test.go"):
                continue
            path = Path(directory) / filename
            declarations = _GO_TEST_DECLARATION.findall(path.read_text(encoding="utf-8", errors="replace"))
            for name in names.intersection(declarations):
                matches[name].add(str(path.parent.relative_to(root)).replace("\\", "/"))
    resolved: dict[str, str] = {}
    for name, packages in matches.items():
        if len(packages) != 1:
            reason = "not found" if not packages else "ambiguous: " + ", ".join(sorted(packages))
            raise ValueError(f"Go selector {name!r} {reason}")
        resolved[name] = next(iter(packages))
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("selectors", type=Path)
    parser.add_argument("--group", default="pass_to_pass")
    args = parser.parse_args()
    document = json.loads(args.selectors.read_text(encoding="utf-8"))
    nodes = list((document.get(args.group) or {}).get("resolved") or [])
    if not nodes:
        return 0
    grouped: dict[str, list[str]] = {}
    bare_names = {str(raw) for raw in nodes if "::" not in str(raw)}
    if any(not _BARE_TEST_NAME.fullmatch(name) for name in bare_names):
        for name in sorted(bare_names):
            if not _BARE_TEST_NAME.fullmatch(name):
                print(f"Invalid Go selector: {name}", file=sys.stderr)
        return 2
    try:
        bare_packages = _resolve_bare_names(Path.cwd(), bare_names) if bare_names else {}
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for raw in nodes:
        node = str(raw)
        file, _, title = node.partition("::")
        if not title and file in bare_packages:
            package, title = bare_packages[file], file
        elif not file or not title:
            print(f"Invalid Go selector: {node}", file=sys.stderr)
            return 2
        else:
            package = str(Path(file).parent).replace("\\", "/") or "."
        grouped.setdefault(package, []).append(title)
    for package, titles in grouped.items():
        pattern = "^(?:" + "|".join(re.escape(title) for title in titles) + ")$"
        result = subprocess.run(["go", "test", f"./{package}", "-run", pattern], check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
