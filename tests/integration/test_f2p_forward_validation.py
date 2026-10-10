#!/usr/bin/env python3
"""Regression tests for final F2P accounting and instruction scoping."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from verifier_trans.deterministic.packaging.package_task import build_instruction


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def trace_row(source_id: str, decision: str = "rewrite") -> dict[str, object]:
    return {
        "source_test_id": source_id,
        "original_intent": f"observable intent for {source_id}",
        "relevant_evidence": ["problem statement and Base repo call path"],
        "binding_found": ["private helper"],
        "observable_surface": "public behavior" if decision not in {"drop", "spec_gap"} else "",
        "decision": decision,
        "emitted_functional_tests": [f"functional::{source_id}"] if decision not in {"drop", "spec_gap"} else [],
        "brief_rationale": "preserves only the source F2P intent",
    }


class FinalArtifactValidationTests(unittest.TestCase):
    def make_workspace(self, source_ids: list[str]) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        verifier = root / "verifier"
        verifier.mkdir(parents=True)
        write_json(root / "restricted" / "resolved_test_selectors.json", {
            "fail_to_pass": {"resolved": source_ids},
        })
        (verifier / "run.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (verifier / "functional_verifier.py").write_text(
            "def functional_check():\n    return True\n", encoding="utf-8"
        )
        (verifier / "conversion_log.md").write_text("one row per F2P\n", encoding="utf-8")
        (verifier / "coverage_matrix.md").write_text(
            "| F2P | intent | decision | observable |\n", encoding="utf-8"
        )
        (verifier / "self_review.md").write_text("SELF_REVIEW: PASS\n", encoding="utf-8")
        (verifier / "instruction_scope.md").write_text(
            "# Final F2P-supported scope\n\nImplement the mapped public behavior.\n\n"
            "INSTRUCTION_SCOPE: PASS\n", encoding="utf-8"
        )
        write_json(verifier / "manifest.json", {
            "schema_version": "3.0",
            "functional_artifact": "functional_verifier.py",
            "test_files": [{"source": "functional_verifier.py", "target": "verifier/functional_verifier.py"}],
            "f2p_command": "./run.sh",
            "p2p_command": "true",
            "functional_surfaces": ["public behavior"],
            "source_f2p_coverage": source_ids,
            "source_p2p_coverage": [],
        })
        write_json(verifier / "conversion_trace.json", {
            "schema_version": "3.0",
            "f2p_mappings": [trace_row(item) for item in source_ids],
        })
        return root

    def tearDown(self) -> None:
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def validate(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "verifier_trans.deterministic.validation.validate_verifier",
                str(root),
                "--revision",
                "1",
            ],
            text=True, capture_output=True, check=False,
        )

    def test_final_trace_is_the_only_required_conversion_plan(self) -> None:
        root = self.make_workspace(["test_a", "test_b"])
        result = self.validate(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_coverage_is_rejected(self) -> None:
        root = self.make_workspace(["test_a", "test_b"])
        manifest_path = root / "verifier" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_f2p_coverage"] = ["test_a"]
        write_json(manifest_path, manifest)
        result = self.validate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unaccounted_f2p:test_b", result.stdout)

    def test_run_sh_alone_is_not_a_functional_verifier(self) -> None:
        root = self.make_workspace(["test_a"])
        (root / "verifier" / "functional_verifier.py").unlink()
        result = self.validate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_functional_verifier_source", result.stdout)

    def test_unexpected_coverage_is_rejected(self) -> None:
        root = self.make_workspace(["test_a", "test_b"])
        manifest_path = root / "verifier" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_f2p_coverage"] = ["test_a", "test_b", "test_c"]
        write_json(manifest_path, manifest)
        result = self.validate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected_f2p_coverage:test_c", result.stdout)

    def test_duplicate_coverage_is_rejected(self) -> None:
        root = self.make_workspace(["test_a", "test_b"])
        manifest_path = root / "verifier" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_f2p_coverage"] = ["test_a", "test_a", "test_b"]
        write_json(manifest_path, manifest)
        result = self.validate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_f2p_coverage_duplicate_ids:test_a", result.stdout)

    def test_nested_coverage_schema_is_rejected_until_deterministically_migrated(self) -> None:
        root = self.make_workspace(["test_a", "test_b"])
        manifest_path = root / "verifier" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_f2p_coverage"] = {
            "count": 2, "source_test_ids": ["test_a", "test_b"],
        }
        write_json(manifest_path, manifest)
        result = self.validate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_f2p_coverage_not_list", result.stdout)

    def test_trace_must_account_for_every_source_f2p(self) -> None:
        root = self.make_workspace(["test_a", "test_b"])
        write_json(root / "verifier" / "conversion_trace.json", {
            "schema_version": "3.0",
            "f2p_mappings": [trace_row("test_a")],
        })
        result = self.validate(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trace_unaccounted_f2p:test_b", result.stdout)

    def test_instruction_uses_final_scope_not_full_problem_statement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "public").mkdir()
            (root / "verifier").mkdir()
            (root / "public" / "problem_statement.md").write_text("A + B + C + D\n", encoding="utf-8")
            scope = "# Supported scope\n\nA + B only.\n\nINSTRUCTION_SCOPE: PASS\n"
            (root / "verifier" / "instruction_scope.md").write_text(scope, encoding="utf-8")
            self.assertEqual(build_instruction(root), scope)


if __name__ == "__main__":
    unittest.main(verbosity=2)
