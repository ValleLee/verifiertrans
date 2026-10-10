# Framework issue: reject vacuous JavaScript P2P adapters

- UTC timestamp: 2026-09-22T05:48:00Z
- Instance observed: `instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan`

## Phenomenon

During revision 2 repair, the Converter proposed a Python pytest collector whose selected JS items had `runtest(): pass`. That would make 288 inherited NodeBB P2P nodes appear green without executing their Mocha bodies.

## Root cause

The original generic P2P prompt required exact inherited nodes but did not explicitly state that JavaScript/TypeScript nodes must execute through the repository's native runner and that synthetic/no-op collectors are invalid.

## Impact

Accepting the proposed artifact would create a vacuous P2P gate and violate the required Base/Gold P2P replay semantics. The candidate was stopped before submission and did not become a verifier revision.

## General fix

Updated `prompts/converter.md` with an explicit JS/TS P2P execution contract: use native Mocha/project runner, derive exact selection from canonical `p2p_nodes.txt`, and forbid synthetic pytest items, empty `runtest`, no-op, or collection-only checks.

## Test result

The interrupted revision 2 was not accepted. The next REPAIR must submit a real native-runner implementation; Hard Validator remains authoritative and will require both Base and Gold P2P to execute successfully.
