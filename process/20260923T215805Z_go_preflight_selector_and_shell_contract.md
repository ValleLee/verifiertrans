# Go preflight selector and Docker shell contract

- UTC: 2026-09-23T21:58:05Z
- Trigger: fresh navidrome Prepare attempt_001/attempt_002
- Classification: framework / execution environment contract

## Evidence

The navidrome dataset supplies bare Go selectors (`TestLastFM`, `TestListenBrainz`, `TestSpotify`). The first Prepare treated those values as file paths and failed before execution. After selector handling was corrected to derive concrete files from `original_test.patch`, Docker preflight reached the image and reported `go: command not found`. A read-only image probe showed Go exists at `/usr/local/go/bin/go`, while the framework's `bash -lc` invocation reset PATH to omit `/usr/local/go/bin`.

## Minimal generic fix

- Preflight now ignores bare selectors as file paths and uses test-patch headers for concrete test files.
- Docker image commands in deterministic execution, replay, package smoke, and mini-SWE sessions now use `bash -c`, preserving the image-provided environment PATH. Host workspace shell use is unchanged.

## Validation

- New deterministic regression: `tests/unit/test_prepare_selectors.py` (bare Go selector resolves to patched `.go` file).
- Targeted execution/shell/preparation tests: 15 passed.
- No instance/repo/test-title special case was added.

## Next

Fresh navidrome Prepare must be rerun after this repair; only then can Converter and downstream gates be evaluated.

## Follow-up evidence

With the PATH repair, Go was found and `go version` passed, but `go test ./... -run '^$'` compiled the Base checkout's F2P tests and failed on the expected missing `newClient` implementation. The preflight collection probe now uses `go list ./...`, which validates package discovery without imposing Gold-only F2P compilation on Base. The deterministic contract test covers this choice.


A subsequent fresh preflight showed `go list ./...` attempted VCS stamping after the framework intentionally omitted `.git` from the copied repo. The probe now uses `go list -buildvcs=false ./...` so package discovery is hermetic and independent of repository metadata.
