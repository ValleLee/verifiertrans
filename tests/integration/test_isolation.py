#!/usr/bin/env python3
"""Tests for the path-scoped model-session isolation boundary.

These tests assert that a session cannot cross its assigned evidence boundary
through any tool, including the shell, which is where it is easiest to leak by
accident.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from verifier_trans.agents.workspace_tools import WorkspaceTools


def build_workspace() -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for name in ("public", "restricted", "sealed", "verifier"):
        (root / name).mkdir()
    (root / "public" / "problem_statement.md").write_text("the problem\n", encoding="utf-8")
    (root / "public" / "repo").mkdir()
    (root / "public" / "repo" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (root / "restricted" / "original_test.patch").write_text("test diff\n", encoding="utf-8")
    (root / "sealed" / "gold.patch").write_text("REFERENCE SOLUTION\n", encoding="utf-8")
    (root / "sealed" / "requirements.md").write_text("names private helpers\n", encoding="utf-8")
    return tmp


class RestrictedSessionIsolationTests(unittest.TestCase):
    """A public-only session must not reach construction evidence by any route."""

    def setUp(self) -> None:
        self.tmp = build_workspace()
        self.root = Path(self.tmp.name)
        self.tools = WorkspaceTools(self.root, ["public"], ["public"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _result(self, name: str, args: dict) -> dict:
        return json.loads(self.tools.execute(name, args))

    def test_can_read_its_own_evidence(self) -> None:
        self.assertIn("the problem", self.tools.execute("read_file", {"path": "public/problem_statement.md"}))

    def test_cannot_read_gold_patch(self) -> None:
        result = self._result("read_file", {"path": "sealed/gold.patch"})
        self.assertIn("error", result)
        self.assertNotIn("REFERENCE SOLUTION", json.dumps(result))

    def test_cannot_read_sealed_requirements(self) -> None:
        self.assertIn("error", self._result("read_file", {"path": "sealed/requirements.md"}))

    def test_cannot_read_restricted_tests(self) -> None:
        """Historical tests are unavailable to a public-only session."""
        self.assertIn("error", self._result("read_file", {"path": "restricted/original_test.patch"}))

    def test_cannot_reach_sealed_via_relative_traversal(self) -> None:
        for spelling in ("../sealed/gold.patch", "public/../sealed/gold.patch", "./sealed/gold.patch"):
            with self.subTest(spelling=spelling):
                self.assertIn("error", self._result("read_file", {"path": spelling}))

    def test_cannot_write_outside_its_writable_root(self) -> None:
        self.assertIn("error", self._result("write_file", {"path": "verifier/verifier.py", "content": "x"}))

    def test_can_write_to_its_own_root(self) -> None:
        result = self._result("write_file", {"path": "public/notes.md", "content": "task\n"})
        self.assertIn("written", result)

    def test_shell_works_in_the_visible_root(self) -> None:
        result = self._result("run_bash", {"command": "pwd"})
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["output"].strip().endswith("public"))

    def test_shell_cannot_enumerate_sealed_directory(self) -> None:
        """`ls -R .` at the workspace root would reveal the sealed dir's name."""
        result = self._result("run_bash", {"command": "ls -R ."})
        self.assertNotIn("sealed", result.get("output", ""))
        self.assertNotIn("gold.patch", result.get("output", ""))

    def test_shell_cannot_read_sealed_file(self) -> None:
        result = self._result("run_bash", {"command": "cat sealed/gold.patch"})
        self.assertIn("error", result)

    def test_shell_cannot_escape_with_parent_traversal(self) -> None:
        result = self._result("run_bash", {"command": "cd ..; ls"})
        self.assertIn("error", result)

    def test_shell_cannot_use_absolute_paths(self) -> None:
        result = self._result("run_bash", {"command": f"cat {self.root}/sealed/gold.patch"})
        self.assertIn("error", result)

    def test_shell_allows_source_literals_inside_quoted_heredoc(self) -> None:
        command = "cat > literal.txt <<'EOF'\nrelative ../src and markup </script>\nEOF\ncat literal.txt"
        result = self._result("run_bash", {"command": command})
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("../src and markup </script>", result["output"])

    def test_shell_still_rejects_parent_traversal_in_heredoc_header(self) -> None:
        command = "cat > ../escape.txt <<'EOF'\nsafe literal\nEOF"
        result = self._result("run_bash", {"command": command})
        self.assertIn("error", result)

    def test_broad_listing_is_refused_with_guidance(self) -> None:
        result = self._result("list_files", {"path": "."})
        self.assertIn("error", result)
        self.assertIn("broad repository listing", json.dumps(result))


class CandidateIsolationTests(unittest.TestCase):
    """A candidate session must not see the verifier it is measured against."""

    def setUp(self) -> None:
        self.tmp = build_workspace()
        self.root = Path(self.tmp.name)
        (self.root / "verifier" / "verifier.py").write_text("assert behaviour\n", encoding="utf-8")
        (self.root / "run" / "validator").mkdir(parents=True)
        self.tools = WorkspaceTools(self.root, ["public"], ["run/validator"])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_cannot_read_the_verifier(self) -> None:
        result = json.loads(self.tools.execute("read_file", {"path": "verifier/verifier.py"}))
        self.assertIn("error", result)
        self.assertNotIn("assert behaviour", json.dumps(result))

    def test_cannot_read_sealed_reference_solution(self) -> None:
        self.assertIn("error", json.loads(self.tools.execute("read_file", {"path": "sealed/gold.patch"})))

    def test_can_write_its_own_solutions(self) -> None:
        result = json.loads(self.tools.execute(
            "write_file", {"path": "run/validator/solution_a/main.py", "content": "impl\n"}
        ))
        self.assertIn("written", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
