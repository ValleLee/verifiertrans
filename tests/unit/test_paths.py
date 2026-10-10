from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from verifier_trans.paths import RunLayout
from verifier_trans.pipeline.artifacts import publish_final_task


class RunLayoutTests(unittest.TestCase):
    def test_attempts_preserve_instance_id_and_increment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            instance_id = "instance_example__repo-0123456789abcdef"
            run = RunLayout.for_instance(Path(raw), instance_id)
            first = run.allocate_attempt()
            second = run.allocate_attempt()

            self.assertEqual(run.root.name, instance_id)
            self.assertEqual(first.root.name, "attempt_001")
            self.assertEqual(second.root.name, "attempt_002")
            self.assertEqual(run.latest_attempt().root, second.root)
            self.assertTrue((run.root / "source/public").is_dir())
            self.assertTrue((run.root / "layout_manifest.json").is_file())
            self.assertTrue((second.root / "source/public").is_dir())
            self.assertTrue((second.root / "converter/current").is_dir())
            self.assertTrue((second.root / "validation/hard_replay").is_dir())
            self.assertTrue((second.root / "qa/positive").is_dir())
            self.assertTrue((second.root / "control").is_dir())

    def test_old_attempt_centric_layout_remains_resolvable(self) -> None:
        from verifier_trans.paths import attempt_from_path
        with tempfile.TemporaryDirectory() as raw:
            old = Path(raw) / "attempt_001"
            (old / "source/public").mkdir(parents=True)
            (old / ".compat").mkdir()
            resolved = attempt_from_path(old)
            self.assertEqual(resolved.source, old / "source")
            self.assertTrue((resolved.runtime / "public").is_dir())

    def test_runtime_view_writes_to_classified_directories(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            attempt = RunLayout.for_instance(Path(raw), "instance_demo").allocate_attempt()
            (attempt.runtime / "public" / "problem_statement.md").write_text(
                "task", encoding="utf-8"
            )
            (attempt.runtime / "run" / "metadata.json").write_text(
                "{}", encoding="utf-8"
            )
            self.assertEqual(
                (attempt.source / "public" / "problem_statement.md").read_text(),
                "task",
            )
            self.assertEqual((attempt.prepare / "metadata.json").read_text(), "{}")

    def test_invalid_instance_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(ValueError):
                RunLayout.for_instance(Path(raw), "../escape")

    def test_final_task_is_published_only_on_explicit_success(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            run = RunLayout.for_instance(Path(raw), "instance_demo")
            attempt = run.allocate_attempt()
            (attempt.prepare / "metadata.json").write_text(
                json.dumps({"instance_id": "instance_demo"}), encoding="utf-8"
            )
            (attempt.converter / "current" / "verifier.py").write_text(
                "assert True\n", encoding="utf-8"
            )
            (attempt.packaging / "candidate_task" / "environment").mkdir(
                parents=True, exist_ok=True
            )
            (attempt.packaging / "candidate_task" / "instruction.md").write_text(
                "task\n", encoding="utf-8"
            )
            self.assertFalse(run.final_task.exists())

            published = publish_final_task(attempt.runtime, 2)

            self.assertEqual(published, run.final_task)
            provenance = json.loads(
                (published / "provenance.json").read_text(encoding="utf-8")
            )
            self.assertEqual(provenance["source_attempt"], "attempt_001")
            self.assertEqual(provenance["verifier_revision"], 2)


if __name__ == "__main__":
    unittest.main()
