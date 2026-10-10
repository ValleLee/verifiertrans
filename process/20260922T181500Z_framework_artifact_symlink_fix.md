# Framework issue: Converter submission failed on compatibility symlink

## Observation

During qutebrowser c580 `attempt_001`, Converter `rev1` produced all required
artifacts and analyzed all 11 F2P nodes. Submission then failed with:

```text
FileExistsError(17, 'File exists')
```

The failure was in framework artifact handoff, before Semantic Judge or Hard
Validator. The new run layout intentionally exposes `.compat/verifier` as a
symlink to `converter/current`, but the generic `copy_tree()` helper passed the
symlink itself as the `shutil.copytree()` destination.

## Fix

`src/verifier_trans/pipeline/artifacts.py::copy_tree` now:

1. resolves an existing directory symlink to its real classified artifact
   directory;
2. removes only the existing real destination tree; and
3. copies with `dirs_exist_ok=True` while preserving source symlinks.

A unit regression test covers the compatibility-link case. This is a generic
artifact-layout fix and is not tied to qutebrowser.

## Handling of the run

The already-started `rev2` is retained for trajectory evidence. The corrected
helper applies to a subsequent resume/retry; `rev1` is not counted as a
semantic verifier revision because it never reached validation.
