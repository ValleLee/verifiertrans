from pathlib import Path

from verifier_trans.deterministic.validation.positive_structure import structural_precheck


def workspace_with_gold(tmp_path: Path, gold: str, candidate: str) -> Path:
    base = tmp_path / "public" / "repo" / "src"
    base.mkdir(parents=True)
    (base / "feature.py").write_text("return 1\n", encoding="utf-8")
    (tmp_path / "sealed").mkdir()
    (tmp_path / "sealed" / "gold.patch").write_text(gold, encoding="utf-8")
    output = tmp_path / "run" / "validator" / "positive"
    output.mkdir(parents=True)
    (output / "src").mkdir()
    (output / "src" / "feature.py").write_text(candidate, encoding="utf-8")
    return tmp_path


GOLD_PATCH = """diff --git a/src/feature.py b/src/feature.py
index 2c9a..3b1e 100644
--- a/src/feature.py
+++ b/src/feature.py
@@ -1 +1 @@
-return 1
+return 2
"""


def test_exact_gold_postimage_is_rejected(tmp_path: Path) -> None:
    result = structural_precheck(workspace_with_gold(tmp_path, GOLD_PATCH, "return 2\n"), tmp_path / "run/validator/positive")
    assert result["status"] == "FAIL"
    assert result["exact_gold_reproduction"] is True


def test_same_file_different_implementation_remains_judge_eligible(tmp_path: Path) -> None:
    result = structural_precheck(workspace_with_gold(tmp_path, GOLD_PATCH, "value = 1\nreturn value + 1\n"), tmp_path / "run/validator/positive")
    assert result["status"] == "PASS"
    assert result["exact_gold_reproduction"] is False
