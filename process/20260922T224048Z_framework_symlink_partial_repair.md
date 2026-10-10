# Framework issue: partial Converter recovery mishandled compatibility symlink

- UTC: 2026-09-22T22:40:48Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8`
- Attempt: `attempt_013`, Converter `rev_3`

## Phenomenon

After Semantic Judge requested two repairs, `rev_3` reached its repair step
limit without submitting. The new generic partial-repair handler correctly
found the filtered staging artifact, but then called `reset_output()` on the
logical `.compat/verifier` path. That path is a compatibility symlink to
`converter/current`; `shutil.rmtree()` rejects symlink targets and the
controller exited with an uncaught `OSError` before recording the repair
evidence.

## Root cause and impact

The recovery code assumed every output path was a real directory, while the
classified attempt layout intentionally exposes verifier/current through a
relative symlink. This was a framework artifact/path-contract failure, not a
semantic verdict on the TypeScript verifier. The attempt did not reach Hard
Validator; revision 3 remains unaccepted.

## General fix

`reset_output()` now resolves a directory symlink, clears its real target, and
preserves the compatibility link. Broken/non-directory links are safely
unlinked before recreating the exact output directory. No instance-specific
path or test name was added.

## Regression

Added a unit test that resets a symlinked verifier output while preserving the
link and clearing its target. Targeted tests passed (`5 passed`); full suite
passed (`100 passed`). The partial-recovery path still needs a fresh attempt
when API capacity is available; no result from rev 3 is treated as valid.

