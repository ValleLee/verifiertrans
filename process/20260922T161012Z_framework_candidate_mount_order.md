# Framework fix: candidate replay Docker mounts

- UTC: 2026-09-22T16:10:12Z
- Discovered during: qutebrowser Positive QA, attempt_002

The core replay mount-order fix did not cover `deterministic/replay/candidate.py`, which independently appended adapter mounts after the Docker image. The first Positive candidate therefore showed a false P2P/legacy failure with `/framework/p2p_runner.py` missing. The candidate replay now appends all plan mounts before `IMAGE -lc SCRIPT`, matching the core replay contract.

Tests: candidate/execution/replay contract tests 12 passed; full framework pytest 85 passed. Reusing the candidate after the fix yielded P2P PASS; a later candidate was judged VALID.
