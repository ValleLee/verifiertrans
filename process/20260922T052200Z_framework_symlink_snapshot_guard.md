# Framework issue: preserve Converter scratch symlinks during snapshots

- UTC timestamp: 2026-09-22T05:22:00Z
- Instance observed: `instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan`

## Phenomenon

The REPAIR session stopped making progress after the Converter created a scratch `app` symlink beneath `verifier/`. The live snapshot callback and the session-finally handoff used `shutil.copytree` with default symlink resolution, recursively copying the NodeBB checkout. Interrupting the session showed the stack blocked in `shutil.copytree`/`sendfile`.

## Root cause

The role contract allows exploratory scratch files inside the writable verifier directory, but two snapshot paths did not use the framework's symlink-preserving copy helper.

## Impact

Monitoring and cancellation could hang for several minutes and prevent the Converter from returning its artifact. This is an infrastructure/artifact handoff failure, not a NodeBB verifier semantic result.

## General fix

`src/verifier_trans/agents/miniswe_session.py` now uses the existing symlink-preserving `_copy_tree` helper for live snapshots and final Converter handoff. Scratch links are copied as links instead of recursively resolving repository contents.

## Test result

The interrupted session was cleaned by its normal `finally` path after the stack trace; no unrelated task output was touched. The next same-attempt REPAIR will exercise the corrected snapshot and handoff paths.
