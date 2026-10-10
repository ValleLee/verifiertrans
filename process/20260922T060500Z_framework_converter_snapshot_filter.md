# Framework issue: exclude temporary Converter dependencies from snapshots

- UTC timestamp: 2026-09-22T06:05:00Z
- Instance observed: `instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan`

## Phenomenon

The Converter installed Mocha dependencies under `verifier/.deps/node_modules` for local P2P validation. The live snapshot callback then recursively copied that dependency tree every five actions; interruption showed it blocked in `shutil.copytree` while copying ordinary files, and final handoff hit the same path.

## Root cause

Converter artifact snapshots used a symlink-safe copy but had no filter for temporary dependency and scratch directories. These directories are not part of the verifier contract and can be very large.

## Impact

Monitoring and session cancellation became unboundedly slow, preventing the Converter from returning a revision. This is an artifact transport/infrastructure failure, not a P2P semantic result.

## General fix

`_copy_tree` now accepts a Converter-scratch filter, and live/final verifier snapshots exclude `node_modules`, `.deps`, `__pycache__`, `.gold_workspace`, and `.tmp_app_gold`. Repository/app and candidate copies retain their existing behavior.

## Test result

The affected REPAIR was interrupted before submission; its temporary artifact was not accepted. The next same-attempt REPAIR will exercise filtered snapshots and must still submit a verifier containing only contract artifacts.
