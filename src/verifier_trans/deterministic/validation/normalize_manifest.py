#!/usr/bin/env python3
"""Deterministically migrate legacy manifest coverage to the list schema."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalize_ids(value: Any, field: str) -> tuple[list[str], bool]:
    if isinstance(value, list):
        return [str(item) for item in value], False
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a list or a legacy object")
    nested = value.get("source_test_ids")
    if nested is not None:
        if not isinstance(nested, list):
            raise ValueError(f"{field}.source_test_ids must be a list")
        return [str(item) for item in nested], True
    # Older artifacts used {source_test_id: emitted_tests}.
    return [str(item) for item in value], True


def normalize_manifest(workspace: Path) -> dict[str, Any]:
    path = workspace / "verifier" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")
    changed = False
    for field in ("source_f2p_coverage", "source_p2p_coverage"):
        values, field_changed = normalize_ids(manifest.get(field), field)
        manifest[field] = values
        changed = changed or field_changed
    if manifest.get("schema_version") != "3.0":
        manifest["schema_version"] = "3.0"
        changed = True
    if changed:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace_path = workspace / "verifier" / "conversion_trace.json"
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if isinstance(trace, dict) and trace.get("schema_version") != "3.0":
            trace["schema_version"] = "3.0"
            trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed = True
    return {"changed": changed, "fields": ["source_f2p_coverage", "source_p2p_coverage"],
            "schema": "list", "manifest": "verifier/manifest.json"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    result = normalize_manifest(args.workspace.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
