# Framework taxonomy update: Mock/Fixture-Induced Implementation Coupling

- UTC: 2026-09-23T06:15:00Z
- Scope: generic Converter and Semantic Judge guidance
- Trigger: Tutanota revision 1 Positive false negative

## Finding

Removing explicit private-helper assertions is insufficient. A verifier can
still be implementation-coupled when its mock, fixture, fake object,
monkeypatch, serializer, or transpiler/runtime shim supports only the path
used by the reference solution. The assertion may appear to check only output,
while the alternative implementation fails earlier because a standard public
property or method is absent from the synthetic runtime.

## General fix

- Added `Mock/Fixture-Induced Implementation Coupling` as a verifier taxonomy
  category and checklist item.
- Added mandatory Converter prompt guidance to enumerate the public runtime
  contract, cover equivalent access paths, and report harness defects instead
  of rejecting candidates.
- Added the same audit to the read-only Semantic Verifier Judge prompt.

## Boundary

This category is distinct from an assertion that directly names a Gold helper:
the coupling is indirect and lives in support code. Observable behavior
assertions remain hard requirements; only the synthetic runtime must be made
behaviorally neutral. No task-specific API, repository path, or instance
special case was added.

## Tests

- Prompt regression tests cover the Converter and Semantic Judge audit terms.
- The Tutanota verifier repair remains responsible for fixing its concrete
  DOM mock and rerunning all gates.
