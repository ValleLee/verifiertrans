# Rev3 harness audit: query API and runtime-shim coupling

## Phenomenon

Rev3 expanded the synthetic DOM with parent/child mutation, text, attributes,
serialization, and loaded the repository's `purify.js`. The Semantic Judge
still found that the harness exposed only the Gold-oriented query surface:
`getElementsByTagName` was available, while standard `querySelector` and
`querySelectorAll` were absent on both `Document` and `Element`.

The Judge also identified a second generic coupling: `verifier.cjs` strips
TypeScript imports and supplies a fixed collection of globals and runtime
shims. A behaviorally equivalent implementation that uses normal module
imports or another standard runtime API can fail before reaching the observable
DataFile assertions.

## Classification

This is `VERIFIER_SEMANTIC`, not candidate or Docker infrastructure failure.
The first finding remains `Mock/Fixture-Induced Implementation Coupling`; the
second is recorded as `Transpiler/Runtime-Shim-Induced Implementation
Coupling`. Both are framework-level harness design issues because the
conversion claims to test public behavior while the execution environment
narrows the public runtime contract to the reference path.

## Impact

Auditing only one alternative lookup path is insufficient. A verifier can pass
Gold and still reject equivalent implementations that use standard DOM query
APIs or ordinary module/runtime behavior. This creates false negatives before
the functional assertions run.

## General repair route

The controller routed the evidence through the generic Converter REPAIR path
as Rev4. The repair must either use the repository/runtime's real public
execution environment or explicitly implement the minimum standard query and
module/runtime contract needed by all observable behaviors. It must not add a
task-specific selector or candidate-path special case.

## Evidence

The authoritative Semantic Judge result is stored in the attempt's
`validation/semantic/rev_003.json`. Rev4 Converter progress and subsequent
gates are pending.
