# 2026-09-24 bounded Converter repair budget adjustment

## Evidence

The fresh Tutanota attempt reached Semantic Judge repair with Prepare and
artifact sanity passing. The repair sessions were stopped by the configured
`repair_step_cap: 120` after writing useful but incomplete DOM/DOMPurify
fixture changes. The corresponding BUILD session has a 160-step cap and was
able to submit a complete artifact. The failure was therefore a bounded
Converter-session budget exhaustion, not a Docker, cwd, mount, service, or
ExecutionSpec failure.

## Minimal generic change

Raise the repair cap from 120 to 180, matching the same bounded-session model
while leaving `max_verifier_revisions`, semantic gates, replay gates, QA gates,
and package gates unchanged. The deprecated alias is kept consistent for old
configuration readers.

## Boundary

This is not a task-specific retry and does not accept partial artifacts. A
repair still must explicitly submit, pass artifact sanity and Semantic Judge,
then pass deterministic replay and QA. If the new cap is exhausted, the
attempt remains manual review with its partial trajectory preserved.
