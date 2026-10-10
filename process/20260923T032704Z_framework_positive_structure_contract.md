# Framework issue: Positive structural-diversity contract

- UTC: 2026-09-23T03:27:04Z
- Scope: generic Positive QA; discovered while reviewing the Tutanota Step 5 candidate

## Finding

Positive generation is allowed to inspect the Gold patch as a construction
reference. The generator is prohibited from reading the verifier and historical
F2P evidence. Deterministic precheck already requires current functional F2P
and retained P2P to pass; historical F2P remains comparative audit evidence.

The missing hard boundary was structural diversity: before this change, an
exact Gold post-image could proceed to the LLM Judge. The Judge prompt asked
for a materially different implementation and received the Gold patch, but
there was no deterministic exact-copy rejection or persisted structural
precheck result.

## General fix

- Added `positive_structure.structural_precheck`, which applies the Gold patch
  to only its touched baseline files and rejects a candidate whose complete
  payload is exactly the Gold post-image over exactly the Gold paths.
- The Positive precheck now records `structural` evidence and does not invoke
  the Judge for an exact Gold reproduction.
- Same-file implementations with different content remain eligible for the
  Positive Judge; the framework does not impose the false requirement that a
  valid alternative must touch different files.
- The Judge still receives Gold as a reference and remains responsible for
  semantic equivalence and non-exact structural equivalence.

## Verification

- Exact Gold post-image: deterministic rejection.
- Same-file, different implementation: remains Judge-eligible.
- Targeted tests: `22 passed`.
- No instance-specific paths, symbols, or file names are used by the check.

