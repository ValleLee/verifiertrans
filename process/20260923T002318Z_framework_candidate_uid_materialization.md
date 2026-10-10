# Framework issue: candidate replay preserved an unmapped solver uid

- UTC timestamp: 2026-09-23T00:23:18Z
- Scope: TypeScript/Tutanota attempt_014 Positive QA candidate

## Symptom

The recovered candidate passed P2P, but current F2P stopped in the native
Tutanota build server with `uv_os_get_passwd ENOENT`. The candidate payload was
written by the solver container as an unprivileged uid and candidate replay
materialized it with `cp -a`, preserving that uid/gid inside the task image.

## Root cause

Candidate replay used archive-preserving copy semantics for a solver-produced
payload. The source ownership is not part of a candidate's repository
semantics and can refer to a uid absent from the target image's passwd
database.

## Impact

The candidate was incorrectly recorded as a verifier semantic failure even
though its native test process never reached the functional assertions. This
blocked Positive QA and obscured whether the alternative implementation was
valid.

## General fix

Candidate replay now copies parent and candidate payloads with
`cp -r --no-preserve=all`, allowing the image's execution user and metadata to
remain authoritative. The deterministic result also classifies
`uv_os_get_passwd` as `environment_missing`/`INFRASTRUCTURE` if it occurs
again, so it cannot be confused with a semantic rejection.

## Tests

- Candidate replay/entrypoint/orchestrator regressions: `8 passed`.
- Re-run the existing recovered Positive payload without another solver
  request; only then adjudicate semantic validity.
