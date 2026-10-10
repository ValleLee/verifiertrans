# Step 4: instance-centric runs layout

- UTC: 2026-09-22T12:30:00Z
- Stage: D / paths and artifact boundaries
- Scope: layout/preparation/report compatibility only; no fresh task or model/API call.

New attempts now use four instance-root boundaries: `source/`, `intermediate/`, `final_task/`,
and `review/`. Dataset row, original task materials, source metadata and `source_manifest.json`
are written under immutable instance-root `source/`. Mutable materialized repo, preflight,
converter, validation, QA, packaging and control artifacts remain under
`intermediate/attempts/attempt_NNN/`; the repo is exposed through a compatibility symlink while
its prepared path is `prepare/repo`. `layout_manifest.json` records the contract.

`AttemptLayout.source` resolves the new root source and falls back to the old
attempt-centric `attempt/source` layout. `.compat`, report generation, resume, package and
atomic publish continue to use the resolver, so existing runs are readable and are not
physically migrated. A source-row mismatch is rejected instead of silently overwriting the
instance source contract.

## Verification

- Path/report/isolation focused tests: 33 passed.
- Full pytest after Step 4 integration: 80 passed.
- New path tests cover root source, layout manifest, fresh attempt isolation and old layout resolver.
- Materialized repo is excluded from final_task by the existing atomic publish boundary.

The four fresh cross-language tasks in plan Step 5 were not started; NodeBB/API remains paused.
