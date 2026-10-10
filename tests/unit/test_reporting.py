from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from verifier_trans.deterministic.reporting.report import write_report
from verifier_trans.paths import RunLayout


class ReportingTests(unittest.TestCase):
    def test_report_summarizes_f2p_scope_and_preserves_false_results(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            run = RunLayout.for_instance(Path(raw), "instance_report").allocate_attempt()
            (run.prepare / "metadata.json").write_text(json.dumps({"instance_id": "instance_report"}), encoding="utf-8")
            (run.source / "public" / "problem_statement.md").write_text("A behavior", encoding="utf-8")
            (run.source / "restricted" / "test_seeds.json").write_text(json.dumps({
                "fail_to_pass_source": ["f2p::one"],
                "pass_to_pass_source": ["p2p::one", "p2p::two"],
            }), encoding="utf-8")
            (run.converter / "current" / "instruction_scope.md").write_text(
                "Implement A\nINSTRUCTION_SCOPE: PASS\n", encoding="utf-8"
            )
            (run.converter / "current" / "conversion_trace.json").write_text(json.dumps({
                "f2p_mappings": [{
                    "source_test_id": "f2p::one",
                    "original_intent": "A",
                    "binding_found": True,
                    "observable_surface": "public API",
                    "decision": "rewrite",
                    "emitted_functional_tests": ["test_a"],
                }]
            }), encoding="utf-8")
            (run.converter / "current" / "manifest.json").write_text(json.dumps({
                "source_f2p_coverage": ["f2p::one"],
                "source_p2p_coverage": ["p2p::one", "p2p::two"],
            }), encoding="utf-8")
            (run.control / "events.jsonl").write_text(json.dumps({
                "time": "2026-09-22T00:00:00+00:00", "state": "PREPARED", "node": "prepare"
            }) + "\n" + json.dumps({
                "time": "2026-09-22T00:00:02+00:00", "state": "FINAL_VALIDATED", "node": "rev_1"
            }) + "\n", encoding="utf-8")
            (run.control / "final.json").write_text(json.dumps({"accepted": True, "revision": 1}), encoding="utf-8")
            (run.control / "report.json").write_text(json.dumps({"status": "VERIFIED"}), encoding="utf-8")
            (run.validation / "hard_replay" / "rev_001.json").write_text(json.dumps({
                "base_f2p": {"passed": False}, "gold_f2p": {"passed": True},
                "base_p2p": {"passed": True}, "gold_p2p": {"passed": True}, "stable": True,
            }), encoding="utf-8")
            (run.qa / "evidence.json").write_text(json.dumps({"positives": [], "mutants": []}), encoding="utf-8")

            metrics = write_report(run.runtime)
            review = run.root.parents[2] / "review"
            report = (review / "conversion_report.md").read_text(encoding="utf-8")
            self.assertEqual(metrics["counts"]["source_f2p_count"], 1)
            self.assertEqual(metrics["counts"]["source_p2p_count"], 2)
            self.assertIn("Base + converted F2P | `False`", report)
            self.assertTrue((review / "metrics.json").is_file())
            self.assertTrue((review / "f2p_mapping.csv").is_file())
            self.assertTrue((review / "instruction_scope_trace.json").is_file())


if __name__ == "__main__":
    unittest.main()
