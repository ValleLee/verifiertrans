# Framework Semantic Judge API timeout

- UTC: 2026-09-22T07:52:00Z
- Scope: generic model-backed validation infrastructure

## Phenomenon

The rev4 Semantic Judge request timed out twice at the configured 300-second
HTTP timeout. No semantic verdict was produced; the controller ended the run as
`INFRASTRUCTURE` / `MANUAL_REVIEW`.

## Root cause

The configured external model endpoint at `10.101.56.66:4081` did not return
within the request timeout while processing the NodeBB verifier evidence.

## Impact

This is not evidence that rev4's functional verifier is wrong. Semantic and
downstream Hard Validator gates remain unverified. The immutable rev4 artifact
and its sanity PASS are preserved for retry.

## General handling

The controller's existing bounded retry and resume path is used. A subsequent
resume reuses the submitted rev4 artifact, retries Semantic Judge, and only
then proceeds to Hard Validator. No task-specific verifier change is made for
an API timeout.

## Test result

- rev4 deterministic sanity: PASS.
- Semantic Judge: infrastructure timeout, retry pending.
- No QA or package evidence is counted from this interrupted run.
