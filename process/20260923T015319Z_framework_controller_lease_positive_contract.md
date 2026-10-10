# Framework controller lease and Positive contract correction

- UTC: 2026-09-23T01:53:19Z
- Scope: generic controller lifecycle and QA contract
- Observed during: TypeScript/Tutanota Step 5 fresh validation

## Phenomenon

Multiple controller/resume processes wrote the same attempt.  The Converter
lock prevented only simultaneous Converter sessions; another controller could
still run QA or overwrite `state.json`, `events.jsonl`, `final.json`, and
`report.json`.  Tutanota attempt014 consequently contained events through
`semantic_rev_4` while its final report still described an earlier Converter
`LimitsExceeded` failure.

The active Positive implementation also required historical F2P to fail.  The
frozen plan's §11 says historical F2P PASS/FAIL is replayed and recorded as
audit evidence, not used as a Positive validity gate.

## General fix

- Added an attempt-scoped `controller_session.lock` around the complete
  controller lifecycle, while retaining the narrower Converter lock.
- A controller `KeyboardInterrupt` now records an explicit `INTERRUPTED`
  event/state before propagating the interrupt, so resume can distinguish an
  interrupted run from an active one.
- Bumped the Positive contract to v4.  Current converted F2P and retained P2P
  remain hard gates; historical F2P runnable/pass/fail/infrastructure fields
  remain audit evidence only.
- Removed the legacy-separation condition from both the deterministic Positive
  precheck and the resume acceptance check.

## Regression

- Added a controller lease collision test.
- Added an interrupted-state source regression.
- Updated Positive truth-table tests for historical PASS, FAIL, and
  infrastructure outcomes.
- Related unit tests will be run before resuming Tutanota.  A fresh regression
  replay of qutebrowser and element-web is required before entering Go.

## Impact

This is language-neutral and does not mention a repository, commit, selector,
or instance-specific behavior.  Existing stale Positive evidence versions are
revalidated instead of silently promoted.
