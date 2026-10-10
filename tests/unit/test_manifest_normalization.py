from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from verifier_trans.deterministic.validation.normalize_manifest import normalize_manifest


class ManifestNormalizationTests(unittest.TestCase):
    def test_legacy_nested_coverage_is_migrated_without_count(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "verifier").mkdir()
            (root / "verifier" / "manifest.json").write_text(json.dumps({
                "source_f2p_coverage": {"count": 2, "source_test_ids": ["a", "b"]},
                "source_p2p_coverage": {"count": 0, "source_test_ids": []},
            }), encoding="utf-8")
            result = normalize_manifest(root)
            manifest = json.loads((root / "verifier" / "manifest.json").read_text())
            self.assertTrue(result["changed"])
            self.assertEqual(manifest["source_f2p_coverage"], ["a", "b"])
            self.assertEqual(manifest["source_p2p_coverage"], [])

    def test_canonical_lists_are_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "verifier").mkdir()
            original = {
                "schema_version": "3.0",
                "source_f2p_coverage": ["a"],
                "source_p2p_coverage": ["b"],
            }
            (root / "verifier" / "manifest.json").write_text(json.dumps(original), encoding="utf-8")
            result = normalize_manifest(root)
            self.assertFalse(result["changed"])
            self.assertEqual(json.loads((root / "verifier" / "manifest.json").read_text()), original)


if __name__ == "__main__":
    unittest.main()
