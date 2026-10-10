# Tutanota Step 5 Positive QA result

- UTC: 2026-09-23T03:44:23Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`
- Attempt: `attempt_015`
- Verifier revision: `rev_003`

## Result

The verifier core passed its deterministic gate: Base F2P failed, Gold F2P
passed, Base/Gold P2P passed, and replay was stable. Prepare and semantic
validation also passed.

Three Positive candidates were generated. Every candidate passed retained P2P
and the historical/legacy F2P replay, but failed the current converted
functional verifier. The current failures were runnable verifier assertions,
not Docker, mount, selector, toolchain, API, or service failures. The first
two candidates failed the XML-declaration/output contract; the third caught a
runtime SVG-sanitization exception and returned empty data before the same
assertion. No candidate reached Solution Judge and no Positive was added to
`evidence.json`.

## Interpretation

This is data-specific candidate semantic failure. The historical F2P replay is
not evidence that these candidates implement the new inline-SVG contract: the
historical selector runs the old test corpus, whose relevant behavior does not
cover the newly converted four-case functional contract. The verifier was not
repaired on this evidence because Gold F2P passed and the current assertions
are supported by the task Requirements/Interface and the retained relevant
historical F2P.

The attempt ended at `BUDGET_EXHAUSTED` for Positive generation. It did not
produce `final_task`; the next action is a fresh/reused-artifact QA continuation
under the updated framework contracts, not a claim of conversion success.

