# Conversion trace schema contract

## 现象与关键 evidence

qutebrowser rev_006 和 Tutanota rev_001 的 Converter 都写出了 JSON 数组形式的 `conversion_trace.json`。OpenLibrary rev_001 虽然是对象，却漏了一个 canonical F2P selector，且 `specification_source` 不符合 contract。deterministic artifact gate 拒绝这些 revision。

## Failure classification

artifact/schema，framework-level 的 prompt/contract 描述不清；具体遗漏行仍由各任务 Converter 修复。

## 根因

Converter prompt 只说 trace 要“包含逐条 row”，没有明确顶层必须是对象、`f2p_accounting` 必须是数组，以及 `specification_source` 的准确值。不同语言和任务均可生成合法 JSON 但不符合 controller 的 schema，因此不是某个 repo 的特性。

## 通用修复

在 `Swepro_test_trans/prompts/converter.md` 明确 trace schema：顶层 JSON object，`specification_source` 为 `source/problem_statement.md`，`f2p_accounting` 为逐条 canonical F2P 的数组。仍由 artifact gate 严格检查，不接受自动猜测或补齐缺失语义行。

## 验证方法与现状

旧 revision 的 artifact gate 已正确 FAIL 并自动生成 repair feedback；后续新 revision 必须通过同一 gate。此修改只影响后续 mini-swe prompt，不改变已经生成的 revision。残余风险是 1755 条 F2P 等大规模任务需要 Converter 完整 accounting，不能因 prompt 修复而降低覆盖要求。

补充：由于修复 revision 仍将字段命名为 `rows`，Converter prompt 已加入精确 JSON 示例并明确禁止 `rows`、`mappings` 等别名；下一轮将由 artifact gate 验证 canonical 字段。
