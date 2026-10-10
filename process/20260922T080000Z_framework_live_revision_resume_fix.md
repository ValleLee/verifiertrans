# Framework live-revision resume fix

- UTC: 2026-09-22T08:00:00Z
- Scope: generic controller resume/recovery

## Phenomenon

After rev4 Converter submission, Semantic Judge timed out before the immutable
rev4 snapshot was written. On resume, the controller saw only rev1--rev3 in
`artifacts/verifier` but `.compat/verifier` pointed to the live rev4 artifact.
It therefore labeled the live rev4 files as `verifier_rev_3` and started another
Semantic Judge request under the wrong revision.

## Root cause

Resume selected `max(revision_dirs)` without comparing the digest of the live
submitted artifact to the latest immutable snapshot.

## Impact

This could repeat expensive Semantic Judge calls, obscure which verifier was
being judged, and make a valid submitted artifact appear stuck in validation.
It is a framework state/recovery error, not a NodeBB verifier defect.

## General fix

Resume now compares `file_digest(workspace/verifier)` with the latest immutable
revision record. If they differ, it runs sanity and snapshots the live artifact
as the next revision before semantic validation. If they match, normal reuse is
unchanged.

## Test result

- Python syntax compilation: PASS.
- The next NodeBB resume will snapshot the live rev4 artifact consistently and
  use the rev4 semantic evidence path.
