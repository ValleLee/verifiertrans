# Specification source contract (2026-09-30)

The canonical conversion trace value is `source/problem_statement.md`. This
matches the Harbor evidence layout and all previously accepted revisions. The
input file is located at `task/source/problem_statement.md`; the trace records
that path relative to the task bundle. `problem_statement.md` and
`evidence/problem_statement.md` are not accepted aliases because they caused
validator, prompt, and generated artifact drift.

The converter prompt, artifact validator, layout metadata, and generated
manifest must use this same value. A source mismatch is an artifact contract
failure and is repaired as metadata before replay. The rule is generic and
independent of task, repository, commit, or test name.
