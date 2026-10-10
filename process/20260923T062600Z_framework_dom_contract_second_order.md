# Rev2 DOM harness audit: second-order public-contract coupling

## Phenomenon

The first repair added `documentElement` and `nodeName`, allowing a standard
SVG retrieval path to proceed. Rev2 nevertheless failed the Semantic Judge.
The remaining verifier harness still modeled only the reference sanitizer path:
its DOM shim omitted standard public mutation and traversal behavior such as
`parentNode`, `childNodes`, `removeChild`, `textContent`, `setAttribute`, and
`insertBefore`. It also replaced the public sanitizer behavior with a bespoke
`purify()` helper.

## Evidence and classification

The Semantic Judge reported that an equivalent implementation using standard
DOM mutation to remove script nodes could throw before the observable
assertions while Gold still passed. This is `VERIFIER_SEMANTIC`, specifically
the generic `Mock/Fixture-Induced Implementation Coupling` category. It is not
a candidate failure, because no candidate was involved in this gate, and it is
not an execution/infrastructure failure.

## Impact

The initial anti-coupling checklist was too narrow: it checked one alternative
SVG lookup path but did not require auditing the full public DOM contract used
by the instruction's sanitizer behavior. A verifier could therefore appear
implementation-independent while its fixture still encoded Gold's traversal,
mutation, and sanitizer strategy.

## General repair route

The controller routed the evidence through the existing generic Converter
REPAIR path as revision 3. The repair must either provide a minimum standard
DOM contract sufficient for all observable behaviors or use a real DOM/runtime
implementation, and must avoid replacing a public runtime contract with a
Gold-shaped bespoke helper. No task-specific selector or file-path rule is
added.

## Test/result status

Rev2 semantic evidence is stored at the attempt's
`validation/semantic/rev_002.json`. Rev3 repair is currently running; its
Semantic Judge, deterministic replay, and QA results remain pending.
