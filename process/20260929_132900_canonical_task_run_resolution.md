# Canonical task/run resolution repair

- **Observed:** A semantic rerun given a canonical task root resolved the immutable source as `runs/<id>/original/task.toml` and failed, because an old Docker mount had created an empty `runs/<id>/original/solution/` directory.
- **Root cause:** `resolve_task()` used `(supplied / "original").is_dir()` before checking whether the path was under the canonical `runs/` root. Directory presence was treated as authority, so derived artifacts could masquerade as Stage 1 input.
- **Scope:** Framework-level. Any Docker mount, interrupted attempt, or legacy artifact can leave a same-named directory under `runs`; path resolution must follow the layout contract rather than incidental directories.
- **Rule:** `tasks/<id>` is the only canonical immutable source; `runs/<id>` and `runs/<id>/attempts/attempt_NNN` always map back to `tasks/<id>`. The old `original/` heuristic is a last-resort compatibility branch for external checkouts.
- **Verification:** `resolve_task()` was exercised with the task root, run root, and attempt root for the qutebrowser instance. All three selected `tasks/<id>/original` and the same run/attempt. `paths.py` compiled successfully.
- **Risk:** A nonstandard external checkout must explicitly provide the compatibility layout; canonical project runs no longer infer source from an accidental derived directory.

## Judge protocol budget observation

The configured 16384-token judge budget produced two consecutive protocol
uncertainties for this compact JSON review. The same evidence and prompt with a
4096-token budget returned a structured semantic `FAIL` with actionable
under-conversion findings. The shared experiment config now uses 4096 for
semantic Judge output; the schema is intentionally compact and does not need a
long completion.
