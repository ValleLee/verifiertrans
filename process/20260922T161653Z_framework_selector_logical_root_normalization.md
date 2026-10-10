# Framework issue: container-root test selectors were not repository-relative

## UTC timestamp

2026-09-22T16:16:53Z

## Phenomenon

JavaScript Prepare for `instance_element-hq__element-web-776ffa47641c7ec6d142ab4a47691c30ebf83c2e` failed before Converter execution. The dataset's F2P/P2P selectors used paths such as `/app/test/...`, while the prepared repository was mounted and checked out using repository-relative paths. Selector resolution therefore reported existing files as missing, and environment preflight stopped with `FAIL`.

## Root cause

The preparation code normalized JavaScript selector syntax (`file | suite | case`) but did not normalize the execution-container root embedded in the file component. The same raw paths were also consumed independently by test snapshotting and environment preflight, so fixing only one consumer would leave inconsistent downstream behavior.

## Impact

This was a generic Prepare/framework failure, not a JavaScript semantic-verifier failure and not an image or Docker availability failure. It prevented the JavaScript cross-language validation from reaching Converter and could have affected any language whose source selectors were recorded with `/app` or `/workspace` prefixes.

## Generic fix

Added `normalize_repo_path` to the shared deterministic test-id helpers. It removes standard logical execution roots (`/app`, `/workspace`, `/workspace/app`, and their relative spellings) while preserving repository-relative paths. `normalize_node_id` now applies the helper to the file component for JavaScript/TypeScript pipe selectors and conventional `path::node` selectors. Prepare now uses the same normalization for:

- `copy_original_tests`;
- frozen F2P/P2P selector resolution;
- selected files and node-derived files used by environment preflight.

No repository, task, test name, or language-specific exception was added.

## Test result

- Focused preparation/replay/orchestrator tests: `43 passed`.
- Full test suite: `87 passed`.
- Next validation: fresh JavaScript Prepare attempt; the previous failed attempt remains immutable evidence.
