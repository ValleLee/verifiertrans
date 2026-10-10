# Framework issue: Converter progress reminder was Python-only

- UTC: 2026-09-22T21:36:23Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8`
- Stage: TypeScript Step 5, `attempt_010`, Converter `rev_1`

## Phenomenon

The Converter wrote `verifier/functional_tests.ts`, but the controller's
progress reminder still considered the verifier empty because it only checked
for top-level Python files or `run.sh`. The reminder therefore did not switch
the model's attention from initial executable test creation to the required
conversion trace, manifest, self-review, and submission.

## Root cause and impact

The reminder predicate was hard-coded to one language even though execution
adapters support multiple language families. This inflated exploration time and
contributed to the 160-action BUILD limit without submission. It is a generic
framework issue, not a TypeScript-specific semantic failure.

## General fix

Added `_has_initial_verifier_artifact()` using language-neutral source suffixes
for C/C++, CJS/JS/MJS, Go, Java, Python, Ruby, Rust, shell, and TypeScript.
The Converter reminder now fires only when no supported executable test exists,
while still requiring the explicit audit files and submission contract.

## Test result

Added a TypeScript detection regression test. The full suite was green before
this small follow-up; the targeted test and full suite should be rerun before
the next fresh attempt.

