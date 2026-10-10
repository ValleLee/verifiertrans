# Framework issue: QA candidate dependency fetch escaped command timeout

- UTC timestamp: 2026-09-23T00:06:42Z
- Scope: TypeScript/Tutanota attempt_014 Positive QA candidate

## Symptom

The core verifier had already passed. The Positive QA solver repeatedly ran
`npm install dompurify@2.3.0 jsdom@20.0.0` in a temporary validation directory.
The image had no progress in that directory and the long-lived mini-SWE
container retained the child process after the host-side execution was
interrupted.

## Root cause

The Positive Generator prompt did not explicitly inherit the framework's
prepared-dependency boundary used by Converter. More importantly, a timeout on
the host `docker exec` client did not guarantee termination of the command
inside the persistent agent container, so a stalled package download could be
reissued by the same QA session.

## Impact

Positive QA could consume time/API/network budget without producing a candidate
payload or deterministic precheck. This was a generic QA execution issue and
did not affect the already-passed core verifier.

## General fix

- Positive QA prompt now forbids dependency fetch/install commands and requires
  use of the prepared image/repository toolchain.
- mini-SWE agent shell execution now wraps each Docker command with an
  in-container `timeout`/kill-after bound in addition to the host subprocess
  timeout, preventing orphaned commands from surviving an interrupted action.

## Tests

- Targeted MiniSWE/orchestrator regression: `9 passed`.
- The exact temporary candidate command was terminated; no unrelated
  containers or task artifacts were removed.
- Resume QA with the existing core-passed revision; candidate generation must
  now obey the prepared-dependency boundary.
