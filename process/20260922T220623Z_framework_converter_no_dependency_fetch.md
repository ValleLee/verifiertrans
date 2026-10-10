# Framework issue: Converter attempted an external package fetch

- UTC: 2026-09-22T22:06:23Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8`
- Attempt: `attempt_012`, Converter `rev_1`

## Phenomenon

The Converter explored DOMPurify and then executed
`cd app/.converter-exp && npm pack dompurify@2.3.0`. The command waited on the
external npm/package path and produced no verifier artifact. The session was
stopped to avoid further API/network usage.

## Classification

This is a generic Converter exploration-efficiency/infrastructure interaction,
not a TypeScript verifier semantic failure and not a Hard Validator runner
failure. The prepared Docker image already contains the repository dependencies;
fetching another package is outside the conversion contract and can make a
fresh task depend on registry availability.

## General fix

Strengthened the shared Converter prompt and BUILD task to prohibit registry or
dependency-fetch commands (`npm install/pack`, `yarn add`, `pip install`, `go
get`, `cargo fetch`). Converter exploration must use the prepared image and
checked-in repository only; missing libraries are recorded as evidence rather
than downloaded.

## Regression

Added a prompt regression test covering the prohibited package-fetch families.
The full unit suite passed: `99 passed`. No instance-specific command or
dependency name was added to the framework.

