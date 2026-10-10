# Tutanota verifier semantic defect: incomplete DOM mock caused a Positive false negative

- UTC: 2026-09-23T05:50:00Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`
- Attempt: `attempt_001`
- Revision: `rev_001`
- Classification: verifier semantic / harness defect; not candidate, Docker, path, selector, or module-root failure

## Phenomenon

Positive candidate `positive_1_attempt_1` completed setup and replay. P2P and
legacy F2P passed, while current functional F2P reached
`/app/verifier/verifier.cjs` and failed at the XML-declaration assertion.
The candidate's implementation used the standard DOM APIs
`parsedSvg.documentElement` and `svgElement.nodeName`.

## Root cause

The generated verifier transpiles the public `HtmlSanitizer.ts` source and
provides a hand-written DOMParser mock. The mock returned a document with
`root`, but omitted the standard `documentElement` and `nodeName` properties.
The Gold implementation used `getElementsByTagName("svg")[0]`, which the mock
did implement, so Gold passed while the structurally different candidate was
incorrectly reduced to empty output.

This is not a private-helper dependency: `sanitizeInlineAttachment` is the
public API required by the task, and `documentElement`/`nodeName` are standard
observable DOM APIs. The failure is therefore a false negative caused by the
verifier harness not modeling the public runtime contract.

## Impact

The current verifier cannot distinguish a semantically valid alternative DOM
implementation from a broken implementation when it uses standard document
properties absent from the mock. Positive QA would waste attempts and could
incorrectly conclude that the converted contract is too strict.

The verifier also currently exercises only the sanitizer surface; the
`loadInlineImages` integration requirement should remain an explicit repair
review item rather than being silently inferred from the Gold patch.

## General repair direction

- Route this evidence to the single Converter in `REPAIR` mode.
- Make the functional harness expose the minimum standard DOM properties it
  claims to model (`documentElement`, `nodeName`) and keep assertions at the
  public observable behavior boundary.
- Do not add candidate-specific or Gold-specific branches.
- Review coverage of the public `loadInlineImages` integration behavior during
  the same repair.

No generic framework execution-layer change was made for this finding.

## Evidence

- `qa/candidates/positive_1_attempt_1.f2p.json`: runnable, verifier semantic
  failure at the XML declaration assertion.
- `qa/candidates/positive_1_attempt_1.p2p.json`: PASS.
- `qa/candidates/positive_1_attempt_1.legacy_f2p.json`: PASS.
- `qa/positive/positive_1_attempt_1/precheck.json`: current F2P FAIL, P2P PASS,
  legacy F2P PASS.
- `validation/hard_replay/rev_001.json`: Base F2P FAIL, Gold F2P PASS, both
  P2P groups PASS, core accepted.

## Test result

The repair has not yet been run. The interrupted attempt remains preserved for
audit and must not be counted as a valid Positive result.
