# Framework issue: selected JS/TS test paths used a stale extension

## UTC timestamp

2026-09-22T16:19:52Z

## Phenomenon

After logical-root normalization fixed JavaScript F2P/P2P selectors, fresh Prepare still failed because `selected_test_files_to_run` contained `CurrentDeviceSection-test.ts` and `SessionManagerTab-test.ts`, while the checked-out repository contained the corresponding `.tsx` files. The F2P/P2P node selectors themselves referenced the existing `.tsx` files.

## Root cause

Preparation treated every selected file string as an exact filesystem path. Some dataset-generated JS/TypeScript execution metadata records a source extension that differs from the checked-out JSX/TSX file, so exact-only validation incorrectly classified the execution environment as unavailable.

## Impact

This was a deterministic framework/preflight failure. It occurred before Converter and did not indicate a verifier semantic defect, missing Docker image, or unavailable JavaScript toolchain.

## Generic fix

Added `resolve_repo_test_path`, which first accepts an exact repository-relative path and then applies only standard cross-extension aliases (`.ts`/`.tsx` and `.js`/`.jsx`). The resolved path is used consistently by original-test snapshotting, frozen selector resolution, and environment preflight. Source selector text remains preserved for accounting; only the executable repository-relative representation is canonicalized.

## Test result

- Focused tests: `44 passed`.
- Full test suite: `88 passed`.
- Next validation: fresh JavaScript Prepare attempt; the earlier attempts remain immutable evidence.
