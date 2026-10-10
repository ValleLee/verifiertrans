#!/usr/bin/env python3
"""Unit tests for the deterministic stage-A core.

These cover exactly the claims the framework's execution evidence depends on:
instance-id parsing across all three real tail shapes, base-state construction,
contract extraction that must not leak the reference implementation path, and
the f2p/p2p classification rule.
"""
from __future__ import annotations

import unittest

from verifier_trans.deterministic.preparation.common import (
    as_list,
    build_base_state_script,
    checkout_commit,
    classify_results,
    extract_contract,
    normalize_node_id,
    normalize_repo_path,
    parse_instance_id,
    resolve_repo_test_path,
)

BASE = "1e137b07052bc3ea0da44ed201702c94055b8ad2"
PR = "04998908ba6721d64eba79ae3b65a351dcfbc5b5"

DATASET_CMD = "\n".join([
    f"git reset --hard {BASE}",
    "git clean -fd ",
    f"git checkout {BASE} ",
    f"git checkout {PR} -- test/database/keys.js test/user/emails.js",
])


class ParseInstanceIdTests(unittest.TestCase):
    def test_sha_only_tail(self) -> None:
        info = parse_instance_id("instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e")
        self.assertEqual(info["pr_commit"], "7073d18b54da7e53274d11c9e2baef1242e8769e")
        self.assertIsNone(info["version_commit"])
        self.assertEqual(info["tail_kind"], "sha_only")

    def test_version_prefixed_tail(self) -> None:
        info = parse_instance_id(f"instance_NodeBB__NodeBB-{PR}-vf2cf3cbd463b7ad942381f1c6d077626485a1e9e")
        self.assertEqual(info["pr_commit"], PR)
        self.assertEqual(info["version_commit"], "f2cf3cbd463b7ad942381f1c6d077626485a1e9e")
        self.assertEqual(info["tail_kind"], "v_sha")

    def test_vnan_tail_still_yields_commit(self) -> None:
        """`vnan` means an empty version field, not a missing commit."""
        info = parse_instance_id(f"instance_NodeBB__NodeBB-{PR}-vnan")
        self.assertEqual(info["pr_commit"], PR)
        self.assertIsNone(info["version_commit"])
        self.assertEqual(info["tail_kind"], "vnan")

    def test_missing_commit_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_instance_id("instance_repo__repo-no-commit-here")


class AsListTests(unittest.TestCase):
    def test_json_array_text(self) -> None:
        self.assertEqual(as_list('["a", "b"]'), ["a", "b"])

    def test_python_literal_text(self) -> None:
        self.assertEqual(as_list("['a', 'b']"), ["a", "b"])

    def test_real_list_passthrough(self) -> None:
        self.assertEqual(as_list(["a"]), ["a"])

    def test_blank(self) -> None:
        self.assertEqual(as_list(""), [])
        self.assertEqual(as_list(None), [])

    def test_double_encoded(self) -> None:
        self.assertEqual(as_list('"[\\"a\\"]"'), ["a"])


class BaseStateTests(unittest.TestCase):
    def test_dataset_command_is_preserved_verbatim(self) -> None:
        script = build_base_state_script(BASE, DATASET_CMD)
        self.assertIn(f"git reset --hard {BASE}", script)
        self.assertIn(f"git checkout {PR} -- test/database/keys.js", script)

    def test_canonical_prefix_precedes_dataset_command(self) -> None:
        """The restored test files must survive; the reset must not come after."""
        script = build_base_state_script(BASE, DATASET_CMD)
        self.assertLess(script.index("git reset --hard"), script.index(PR))

    def test_empty_command_falls_back_to_plain_checkout(self) -> None:
        script = build_base_state_script(BASE, "")
        self.assertIn(f"git reset --hard {BASE}", script)
        self.assertNotIn("None", script)

    def test_checkout_commit_extracted(self) -> None:
        self.assertEqual(checkout_commit(DATASET_CMD), PR)
        self.assertIsNone(checkout_commit(""))


INTERFACE_TEXT = """
Type: Method

Name: db.mget

Path: src/database/mongo/main.js, src/database/postgres/main.js, src/database/redis/main.js

Input: keys: string[] (An array of database keys to retrieve.)

Output: Promise<(string | null)[]> (A promise that resolves to an array of values.)

Description: A method on the database abstraction layer that retrieves multiple objects.

Type: Function

Name: user.email.getEmailForValidation

Path: src/user/email.js

Input: uid: number (The user ID for which to find a validation email.)

Output: Promise<string | null>

Description: A utility function that retrieves the most appropriate email address.
"""


class ContractExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract, self.audit = extract_contract(INTERFACE_TEXT, "problem text")

    def test_keeps_symbol_and_signature(self) -> None:
        self.assertIn("db.mget", self.contract)
        self.assertIn("keys: string[]", self.contract)
        self.assertIn("Promise<(string | null)[]>", self.contract)

    def test_drops_implementation_paths(self) -> None:
        """`Path:` is literally which files the gold patch touched."""
        self.assertNotIn("src/database/mongo/main.js", self.contract)
        self.assertNotIn("src/database/redis/main.js", self.contract)
        self.assertNotIn("Path:", self.contract)

    def test_drops_prose_description(self) -> None:
        self.assertNotIn("Description:", self.contract)
        self.assertNotIn("database abstraction layer", self.contract)

    def test_audit_records_dropped_fields(self) -> None:
        self.assertEqual(self.audit["mode"], "structured")
        self.assertEqual(self.audit["blocks_kept"], 2)
        self.assertIn("Path", self.audit["fields_dropped"])
        self.assertIn("Description", self.audit["fields_dropped"])

    def test_unparseable_interface_falls_back_and_says_so(self) -> None:
        contract, audit = extract_contract("just some prose with no fields", "the problem statement")
        self.assertEqual(audit["mode"], "fallback_problem_statement")
        self.assertIn("the problem statement", contract)


class NodeIdTests(unittest.TestCase):
    def test_python_node_id_untouched(self) -> None:
        node = "tests/unit/utils/test_urlutils.py::TestWiden::test_widen_hostnames[a.b.c-expected0]"
        self.assertEqual(normalize_node_id(node, "python"), node)

    def test_js_pipe_form_normalised(self) -> None:
        raw = "test/database.js | Test database test/database/keys.js::Key methods should return null"
        self.assertEqual(
            normalize_node_id(raw, "js"),
            "test/database.js::Key methods should return null",
        )

    def test_container_root_is_removed_from_paths(self) -> None:
        self.assertEqual(
            normalize_repo_path("/app/test/components/example.test.tsx"),
            "test/components/example.test.tsx",
        )
        self.assertEqual(
            normalize_node_id("/workspace/app/test/example.ts::case", "typescript"),
            "test/example.ts::case",
        )

    def test_relative_paths_are_unchanged(self) -> None:
        self.assertEqual(normalize_repo_path("./test/example.js"), "test/example.js")

    def test_typescript_selector_extension_alias_is_resolved(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "test").mkdir()
            (repo / "test/example.tsx").write_text("", encoding="utf-8")
            self.assertEqual(
                resolve_repo_test_path(repo, "/app/test/example.ts"),
                "test/example.tsx",
            )

    def test_javascript_selector_resolves_typescript_source(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "test").mkdir()
            (repo / "test/example.ts").write_text("", encoding="utf-8")
            self.assertEqual(
                resolve_repo_test_path(repo, "test/example.js"),
                "test/example.ts",
            )

    def test_generated_test_root_alias_is_resolved(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "test/api").mkdir(parents=True)
            (repo / "test/api/example.ts").write_text("", encoding="utf-8")
            self.assertEqual(
                resolve_repo_test_path(repo, "test/tests/api/example.js"),
                "test/api/example.ts",
            )

    def test_unique_basename_resolves_flattened_test_directory(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "test/api/common").mkdir(parents=True)
            (repo / "test/api/common/LoggerTest.ts").write_text("", encoding="utf-8")
            self.assertEqual(
                resolve_repo_test_path(repo, "test/tests/api/common/utils/LoggerTest.js"),
                "test/api/common/LoggerTest.ts",
            )


class ClassifyTests(unittest.TestCase):
    def test_f2p_is_observed_not_copied(self) -> None:
        """A test absent from the source f2p list can still be f2p if it behaves so."""
        base = {"a": False, "b": True, "c": False}
        gold = {"a": True, "b": True, "c": False}
        out = classify_results(base, gold, inherited_p2p=["b"])
        self.assertEqual(out["f2p"], ["a"])
        self.assertEqual(out["anomalies"]["gold_failed"], ["c"])

    def test_inherited_p2p_liveness_is_reported(self) -> None:
        base = {"b": True}
        gold = {"b": False}
        out = classify_results(base, gold, inherited_p2p=["b", "gone"])
        self.assertEqual(out["p2p_missing"], ["gone"])
        self.assertEqual(out["p2p_regressed"], ["b"])




class InterfaceFormatRegressionTests(unittest.TestCase):
    """Formats taken verbatim from the real parquet, all of which once failed.

    These are the shapes that made the first implementation lose 598 of 731
    rows, an earlier one leak 148, and a later one silently delete valid type
    expressions. They are pinned here so the parser cannot regress silently.
    """

    def test_repr_quoted_newlines_are_unescaped(self) -> None:
        raw = '"Type: Method\\n\\nName: db.mget\\n\\nInput: keys\\n\\nOutput: Promise"'
        contract, audit = extract_contract(raw, "")
        self.assertIn("db.mget", contract)
        self.assertIn("keys", contract)

    def test_numbered_heading_with_inline_fields_still_scrubs_locations(self) -> None:
        """A heading plus packed inline fields: shape may be thin, but the path
        ``src/controllers/well-known.js`` must never survive either way."""
        raw = (
            "1) Controller: WebFinger handler Name: webfinger Type: Function "
            "Location: src/controllers/well-known.js Input: req: Request res: Response "
            "Output: HTTP 200"
        )
        contract, _ = extract_contract(raw, "Problem statement fallback.")
        self.assertNotIn("src/controllers", contract)
        self.assertNotIn("well-known.js", contract)

    def test_bulleted_fields(self) -> None:
        raw = (
            "- Type: Function\\n- Name: `prepare_multipart`\\n"
            "- Path: `lib/ansible/module_utils/urls.py`\\n"
            "- Input: fields: Mapping[str, Any]\\n- Output: dict"
        )
        contract, audit = extract_contract(raw, "")
        self.assertEqual(audit["mode"], "structured")
        self.assertIn("prepare_multipart", contract)
        self.assertNotIn("lib/ansible", contract)

    def test_colonless_signature_field(self) -> None:
        raw = (
            "Function\\n\\n- Name `DeduplicateDatabaseServers`\\n"
            "- Signature `func F(s []T) []T`\\n- Path `api/types/databaseserver.go`\\n"
            "- Output `[]DatabaseServer`"
        )
        contract, _ = extract_contract(raw, "")
        self.assertNotIn("api/types", contract)
        self.assertNotIn("databaseserver.go", contract)

    def test_type_expression_is_not_mistaken_for_a_path(self) -> None:
        """`Promise<(string | null)[]>` once looked like a path and was deleted."""
        raw = "Type: Method\\nName: db.mget\\nInput: keys: string[]\\nOutput: Promise<(string | null)[]>"
        contract, _ = extract_contract(raw, "")
        self.assertIn("Promise<(string | null)[]>", contract)

    def test_no_new_interfaces_uses_problem_statement(self) -> None:
        contract, audit = extract_contract("No new interfaces are introduced", "Fix the widget.")
        self.assertEqual(audit["mode"], "no_new_interfaces")
        self.assertIn("Fix the widget.", contract)

    def test_prose_interface_falls_back_with_reason(self) -> None:
        contract, audit = extract_contract(
            "The golden patch created two new files 'a/b/c.ts' and 'd/e/f.ts'", "Fix the widget."
        )
        self.assertEqual(audit["mode"], "fallback_problem_statement")
        self.assertTrue(audit["reason"])

    def test_thin_contract_falls_back_rather_than_looking_authoritative(self) -> None:
        """One surviving field is worse than the problem statement: it looks like a spec."""
        raw = "Type: Class\\nName: VersionChange\\nPath: qutebrowser/config/configfiles.py\\nDescription: An enum."
        contract, audit = extract_contract(raw, "The problem statement text.")
        self.assertEqual(audit["mode"], "fallback_problem_statement")
        self.assertEqual(audit["reason"], "insufficient_shape")
        self.assertIn("The problem statement text.", contract)

    def test_scraped_prose_does_not_put_description_into_output(self) -> None:
        raw = "Method: run(self) Input: self Output: HTTP 200 on cases Description: Fetches metadata from the API."
        contract, _ = extract_contract(raw, "")
        for line in contract.splitlines():
            if line.startswith("- Output:"):
                self.assertNotIn("Fetches metadata", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
