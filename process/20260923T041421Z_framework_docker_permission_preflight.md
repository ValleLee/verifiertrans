# Framework / infrastructure: Docker permission preflight failure

- UTC: 2026-09-23T04:14:21Z
- Scope: Tutanota TypeScript Step 5 fresh Prepare, attempt_016
- Classification: framework/infrastructure, not verifier semantics

## Phenomenon

Fresh Prepare allocated `attempt_016`, but environment preflight and repository
materialization both failed with Docker exit code 126:

```text
docker: Got permission denied while trying to connect to the Docker daemon socket
at unix:///var/run/docker.sock
```

No Converter artifact was produced and the attempt was not allowed to enter
semantic conversion.

## Root cause

The controller was launched inside a restricted execution context without
permission to access the authorized host Docker daemon socket. This is an
execution authorization boundary; the repository image, selector, and
TypeScript runner were not the cause.

## Impact

The failed attempt has been retained as audit evidence. Treating it as a
verifier failure would incorrectly trigger Converter REPAIR and could waste
model calls.

## Generic handling

Keep Docker access in Prepare/Hard Validator as an explicit preflight
requirement. If the daemon is inaccessible, stop before Converter and classify
the result as infrastructure failure. Re-run the same instance in a context
with the already-authorized Docker capability; do not reuse the failed attempt
as a conversion attempt.

## Test result

Fresh `attempt_017` was run with Docker access enabled. Repository
materialization matched the base commit, Node/TypeScript environment preflight
passed, selector collection passed, and `source_preflight.status` and
`environment_preflight.status` are both `PASS`.

