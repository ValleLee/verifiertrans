# Framework issue: Node selector titles could silently execute zero tests

## UTC timestamp

2026-09-22T17:36:58Z

## Phenomenon

Element Web P2P replay produced successful Jest processes, but the JSON reports showed every requested assertion as `pending`. The selector format used pipe-separated suite segments, while Jest reports hierarchical full names separated by spaces. The runner returned the process exit code without checking whether requested selectors actually executed. This allowed a vacuous P2P pass; the subsequent replay evidence also exposed a timeout in the pre-fix retry.

## Root cause

The framework-owned Node runner treated dataset titles as literal Jest regular-expression strings and did not validate the native runner's JSON assertion results. A zero-match `--testNamePattern` can still exit zero when the file itself is valid.

## Generic fix

- Normalize pipe-separated selector hierarchy to Jest's space-separated full-name form.
- Batch all selectors for a file into one Jest/Vitest process.
- For Jest JSON output, require every expected normalized title to appear with a non-pending/non-todo status; otherwise return a runner mismatch failure.

This keeps selector semantics deterministic and prevents skipped tests from being counted as P2P success.

## Test result

- Focused Node execution tests: `10 passed`.
- Full framework test suite: `90 passed`.
- The active JS attempt had already exhausted its infrastructure retry before this second runner fix; a fresh Prepare/conversion attempt is required to validate the corrected runner end-to-end.
