# Framework convergence summary: plan Step 0–4

- UTC: 2026-09-22T14:00:00Z
- Scope completed: A repository-native ExecutionSpec, B package/F2P artifact accounting, C relaxed Positive QA, D instance-centric runs layout.
- Scope explicitly not started: plan Step 5's four fresh Python/JavaScript/TypeScript/Go validation tasks.
- Paused external work: NodeBB conversion and model/API usage remain paused.

## Result

The framework now has one deterministic execution contract shared by replay, candidate replay,
package and Prepare preflight. `discovery.py` reads repository-native metadata and records
language, runner family, package manager, cwd/module root (including nested Node packages and Go
modules), selector style, TypeScript loader, services and support status. Python/pytest, Node
Mocha/Jest/Vitest, TypeScript loader metadata and Go module discovery are represented; unknown native runners are explicit infrastructure
unsupported rather than hidden Converter work.

The final package no longer blindly embeds the complete historical test patch. Resolved P2P
selectors drive deterministic retention of P2P state and referenced/shared fixtures; F2P-only
files and identifiable F2P-only test lines/hunks are excluded. Unreferenced patch files are
excluded and all decisions are recorded in `tests/package_report.json` and the attempt package
report. Final reward remains converted F2P plus retained P2P; legacy F2P is not run by package
`test.sh`.

Positive QA now accepts current converted F2P PASS + P2P PASS + Solution Judge VALID. Historical
F2P is replayed into `historical_f2p_runnable` / `historical_f2p_pass`, but PASS, FAIL and
historical infrastructure failure are audit evidence only. Evidence uses contract version 2;
old evidence is replayed and migrated rather than silently trusted.

Fresh Prepare now writes immutable instance-root `source/`, mutable
`intermediate/attempts/attempt_NNN/`, `review/`, and deferred `final_task/`. Source manifest and
dataset-row checks prevent silent source replacement. Materialized repo is under
`attempt/prepare/repo`; `.compat` and resolver support old attempt-centric runs without physical
migration.

## Verification evidence

- Full pytest: **83 passed**.
- Full unittest discovery: **63 tests, OK**.
- `python -m compileall -q src tests`: **PASS**.
- `.venv/bin/verifier-trans --help`: **PASS**.
- Existing old-run resolver audit: qutebrowser, NodeBB, OpenLibrary and NodeBB-049989 attempts
  resolved successfully; existing final_task artifacts remain present for the previously
  successful runs.
- No fresh validation instance was started and no external model/API call was made.

## Remaining bounded gaps

Host `node` is not installed, so Node runner syntax was not host-executed; native Node/TS/Jest/
Vitest behavior still requires the explicitly deferred Docker Step 5 validation. Redis remains
the only generic service bootstrap. These are validation/efficiency items, not reasons to move
runtime plumbing back into Converter.

## Final artifact paths

- Framework source: `/lg-home/cog8/lwli6/VerifierTrans/src/verifier_trans/`
- Updated architecture/plan: `/lg-home/cog8/lwli6/VerifierTrans/docs/architecture.md` and
  `/lg-home/cog8/lwli6/VerifierTrans/docs/plan_optimize.md`
- Process records: `/lg-home/cog8/lwli6/VerifierTrans/process/`
- New task outputs, when a future fresh Prepare is run, will be under
  `/lg-home/cog8/lwli6/VerifierTrans/runs/<instance_id>/source|intermediate|review|final_task`.
  This convergence pass intentionally did not generate a new final_task.
