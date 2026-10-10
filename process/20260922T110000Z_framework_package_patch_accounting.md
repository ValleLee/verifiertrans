# Step 2: package test patch accounting

- UTC: 2026-09-22T11:00:00Z
- Stage: B / final package
- Scope: deterministic packaging only; no fresh task or model/API call.

`package_task.py` no longer blindly concatenates the complete historical
`original_test.patch`. It now calls `retain_p2p_test_patch()` with resolved selector evidence.
The package keeps P2P-selected files, shared setup/fixture files, and unclassified support
files; removes files selected only by historical F2P; and removes explicit F2P-only test lines
from shared hunks while preserving valid unified-diff counts. Every source, retained, shared,
fixture, excluded file, excluded hunk, and ambiguous shared hunk is written to
`tests/package_report.json`.

The final package continues to grade only converted F2P and retained P2P. Historical F2P is not
invoked by `test.sh` and has no reward weight. The slicer is selector/file based and generic; it
contains no instance, repository, or test-name branch.

## Verification

- `tests/unit/test_package_test_patch.py`: 2 passed.
- `tests/unit/test_execution_adapters.py`: 5 passed while the package change was integrated.
- The package source remains auditable through `test.patch` plus `package_report.json`.

Real package smoke remains part of the full gate and is not claimed here because Step 5 fresh
validation is explicitly excluded.
