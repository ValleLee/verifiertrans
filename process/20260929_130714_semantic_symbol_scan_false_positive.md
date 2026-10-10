# Semantic gate repair: qualified-symbol matching

- **Observed:** The semantic gate classified `font.families` in a candidate verifier as a Gold-only symbol because the final component `families` also appeared as a local name in the Gold diff.
- **Evidence:** `attempt_002` `rev_004` semantic review reported `font.families`; the emitted test uses the public Qt/PyQt result method, while the Gold patch contains local `families` assignments. The candidate did not contain a Gold-added qualified `font.families` symbol.
- **Root cause:** The scanner accepted either the complete candidate symbol or its final component as a Gold match. Final-component matching is ambiguous for ordinary variables and library methods.
- **Scope:** Framework-level. The scanner is shared by every task and any repository can use common names such as `name`, `items`, `families`, or `status`.
- **Rule:** A candidate symbol is Gold-only only when the complete qualified symbol occurs in an added Gold line, is absent from Base, and is not explicitly supported by Problem Statement. Do not infer a contract from a leaf token.
- **Verification:** Recompile `swepro_trans.validation.semantic`; rerun the semantic gate on the current revision; confirm the false-positive `font.families` is absent while a real `configutils.FontFamilies.from_str` reference remains detectable.
- **Risk:** A Gold diff that introduces a symbol only through an unqualified local declaration may no longer be recognized by this gate. That is intentional: local declarations are not sufficient evidence of an API contract; the Judge and F2P accounting remain responsible for semantic review.

## Related Judge boundary

The first rev_004 Judge also treated omission of `FontFamilies.from_str` as under-conversion even though the Problem Statement names only the class and observable parsing behavior. The generic review rule is: an exact historical method is not required when it is absent from P and the candidate preserves the behavior through a public Base/product boundary plus any P-explicit type contract. Existence-only checks remain insufficient by themselves; they must accompany the behavioral assertion.

## Judge protocol uncertainty

A semantic Judge response of `UNCERTAIN` (for example, empty or unparsable
provider output after the built-in retry) is not converter evidence. The
controller now records `manual_review_required` and does not invoke a new
converter revision for that condition. This rule is generic: retrying a model
on a protocol failure can rewrite a valid artifact without semantic feedback.
