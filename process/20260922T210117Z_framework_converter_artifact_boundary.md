# Framework issue: Converter scratch tree escaped into verifier artifact

- UTC: 2026-09-22T21:01:17Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`
- Stage: TypeScript Step 5, `attempt_009`, Converter `rev_2`

## Phenomenon

The Converter created `verifier/tmp_mithril/` and unpacked the complete
Mithril package into it while investigating DOM behavior. The live snapshot
then enumerated more than one thousand dependency/package files. Snapshot and
session-final handoff entered recursive `copytree`, consumed substantial time,
and had to be interrupted. The attempt did not reach Semantic Judge or Hard
Validator.

The preceding `rev_1` also reached the Converter step limit after extensive
exploration without submitting the required artifact. This is a Converter
efficiency/contract failure, not evidence that the TypeScript verifier or its
execution adapter is semantically wrong.

## Root cause

The role prompt described the desired verifier contents but did not enforce a
machine-level boundary for scratch experiments. The live snapshot filter only
ignored a few known dependency directory names and still traversed arbitrary
`tmp_*` trees. The file inventory used `rglob` and therefore paid the cost of
walking the entire accidental package before the model could continue.

## Impact

- No verifier revision was accepted for this TypeScript instance.
- API/tool actions were spent on dependency archaeology rather than the 78
  historical F2P mappings.
- A large scratch tree could have contaminated a submitted artifact or made
  artifact handoff appear to be an infrastructure timeout.

## General fix

- Added a shared Converter scratch-name policy in
  `agents/miniswe_session.py` for live snapshots and submitted handoff:
  `tmp_*`, `scratch_*`, `experiment_*`, dependency/cache directories, and
  archive files are excluded.
- Replaced recursive `rglob` inventory with a pruned `os.walk`, so live
  monitoring does not traverse excluded scratch trees.
- Strengthened the Converter prompt and BUILD task with a strict artifact
  boundary: only final tests, small fixtures/modules, and audit files belong
  under `verifier/`; experiments remain under `app/` and are removed before
  submission.

## Test result

Added `tests/unit/test_miniswe_session.py`, covering both pruned inventory and
handoff copying. The interrupted Docker session was cleaned by the existing
session teardown path; no unrelated containers or task outputs were removed.

