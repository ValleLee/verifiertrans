from verifier_trans.deterministic.packaging.test_patch import retain_p2p_test_patch


def test_p2p_patch_accounting_excludes_f2p_file_and_hunk() -> None:
    patch = """diff --git a/test/f2p.js b/test/f2p.js
new file mode 100644
--- /dev/null
+++ b/test/f2p.js
@@ -0,0 +1,3 @@
+describe('old behavior', () => {});
+it('f2p title', () => {});
+
diff --git a/test/shared.js b/test/shared.js
--- a/test/shared.js
+++ b/test/shared.js
@@ -1,2 +1,5 @@
 setup();
+it('f2p title', () => {});
+it('p2p title', () => {});
+helper();
"""
    output, report = retain_p2p_test_patch(
        patch,
        {
            "fail_to_pass": {"resolved": ["test/f2p.js::f2p title", "test/shared.js::f2p title"]},
            "pass_to_pass": {"resolved": ["test/shared.js::p2p title"]},
        },
    )
    assert "test/f2p.js" not in output
    assert "f2p title" not in output
    assert "p2p title" in output
    assert report["excluded_f2p_files"] == ["test/f2p.js"]
    assert report["excluded_f2p_hunks"]
    assert report["retained_shared_files"] == ["test/shared.js"]


def test_fixture_file_is_retained_and_empty_patch_is_audited() -> None:
    patch = """diff --git a/test/helper.js b/test/helper.js
--- a/test/helper.js
+++ b/test/helper.js
@@ -1 +1 @@
-old();
+new();
"""
    output, report = retain_p2p_test_patch(
        patch,
        {"pass_to_pass": {"resolved": []}, "selected_test_files_to_run": ["test/helper.js"]},
    )
    assert output == patch
    assert report["retained_fixture_files"] == ["test/helper.js"]
    unrelated, unrelated_report = retain_p2p_test_patch(
        patch, {"pass_to_pass": {"resolved": []}}
    )
    assert unrelated == ""
    assert unrelated_report["excluded_unreferenced_files"] == ["test/helper.js"]
    _, empty = retain_p2p_test_patch("", {})
    assert empty["source_patch_present"] is False
