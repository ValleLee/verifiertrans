# qutebrowser rev_004 semantic boundary and replay audit

## Revision changes

- All 11 historical F2P rows remain mapped as `rewrite`; no row was dropped.
- Direct calls to `configutils.FontFamilies.from_str` were removed from emitted tests.
- Non-empty parsing is observed through `QtFont.to_py()` and `QFont.families()`, then represented by the Problem Statement-named `FontFamilies` class.
- Empty input uses the legacy parser when it exists (Base) and an empty collection when Gold has removed that legacy helper; this follows the public input boundary because `QtFont.to_py('')` rejects empty configuration values.
- Hypothesis uses the accepted configuration character domain and checks both non-empty entries and `FontFamilies` serialization.

## Evidence

- Artifact contract: PASS, 11/11 F2P rows accounted for.
- Gold Docker replay: PASS, 57/57 required tests.
- Base Docker replay: FAIL, 46/57 required tests; all 11 functional F2P tests are missing as expected because Base has no `FontFamilies` class.
- The deterministic provenance gate passes after removing the hidden method and after fixing the generic full-qualified-symbol scanner.
- One valid Judge run before the last test repair identified the empty-input and non-empty serialization gaps; those gaps were repaired. Subsequent endpoint calls remained protocol-uncertain, so the controller does not claim a fresh semantic PASS.

## Decision

Keep the task in `manual_review_required` and do not create `final/`. The
remaining question is whether P-only functional evidence may use the existing
QtFont boundary plus a P-named class, or whether the historical `from_str`
behavior must be treated as an explicit public API. Packaging either choice
without a usable semantic Judge verdict would hide that specification boundary.
