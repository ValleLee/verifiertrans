# Specification source contract (2026-09-30)

The conversion trace uses one canonical value for its normative source:
`problem_statement.md`. This is a trace artifact field, relative to the
revision evidence bundle. The Harbor source directory itself remains
`source/`, so the input file is still `source/problem_statement.md`; the trace
field must not repeat that container directory.

The artifact validator, converter prompt, and repaired revisions must enforce
the same value. A mismatch is an artifact contract failure and must be fixed as
metadata before replay; it must not trigger a semantic rewrite of the verifier.
The rule is generic and independent of task, repository, commit, or test name.
