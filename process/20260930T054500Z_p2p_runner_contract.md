# P2P runner contract

## Evidence

Element rev_007 passed semantic review and Base/Gold F2P replay, but stability
found `original p2p_count=39` and `candidate p2p_count=5`. The candidate had
renamed retained selectors to generated `Kebab` tests. Its runner also passed
the full Harbor selector string directly as a test-file argument, so replaying
the original selectors could not execute the repository tests.

## Generic rule

The converter must copy the original `pass_to_pass` selector strings exactly.
The runner must separate a selector's test-file prefix from its descriptive
test name when invoking the repository test command. The full selector remains
the accounting key; only the file prefix is a process argument. A leading
`/app/` is stripped when the command runs inside `/app`.

## Gate

Stability requires exact equality of candidate and original P2P selector lists,
and each repeated P2P replay must pass on both Base and Gold. A candidate with
renamed, missing, or non-runnable P2P selectors is rejected and repaired.
