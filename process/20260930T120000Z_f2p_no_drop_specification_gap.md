# F2P 全覆盖与规格缺口门槛

## 现象

历史 F2P 中出现了 `drop`：qutebrowser 的序列化测试和 OpenLibrary 的名称规范化测试被以 Gold-only 或 Problem Statement 未明确为理由删除。这样会让已接受的 verifier 丢失历史行为意图。

## 根因

语义校验器已经倾向拒绝 drop，但 converter prompt、agent 归一化、revision artifact 校验和 acceptance 仍把 `drop` / `manual_review` 当作可接受结果，形成了门槛不一致。

## 影响范围

这是跨任务的转换协议问题，任何包含 Requirements / Interface 中可观察行为的 Harbor 任务都可能被静默 under-convert。

## 通用规则

F2P 的提交结果只有 `rewrite` 或 `merge`。如果 P 没有覆盖一个重要且可观察的历史行为，converter 必须把不绑定实现的行为级描述写入 revision 的 `functional_specification.md`，在 trace 中引用该补充，并使用 Base 仓库已有的公开接口或可观察输出生成测试。找不到合适公开观测面的状态表示 revision 尚未完成，应继续探索或进入 repair loop，而不是提交 `specification_gap`、`drop` 或 `manual_review`。converter 不得直接改写原始 source P，最终 package 将 base P 与经过 semantic gate 的功能补充合并为 solver instruction。

## 修改文件

另外，package 会将 `functional_specification.md` 与 `source/problem_statement.md` 合并写入 final instruction，QA candidate 也读取这份补充。

- `Swepro_test_trans/prompts/converter.md`
- `Swepro_test_trans/prompts/judges/semantic.md`
- `Swepro_test_trans/src/swepro_trans/agents/runner.py`
- `Swepro_test_trans/src/swepro_trans/validation/revision.py`
- `Swepro_test_trans/src/swepro_trans/validation/semantic.py`
- `Swepro_test_trans/src/swepro_trans/validation/acceptance.py`
- `Swepro_test_trans/src/swepro_trans/reporting/human_review.py`

## 验证方法

使用旧 revision 的 `drop` / `specification_gap` trace 运行 artifact contract，应被拒绝；使用新 schema 的 rewrite / merge trace，应继续接受结构校验。之后重新运行 qutebrowser 与 OpenLibrary，要求 F2P 覆盖率为 100%，且每行都映射到实际生成的功能测试。

## 残余风险

Problem Statement 的补充由 converter 以行为级 addendum 自动生成，并接受 semantic gate 审核。qutebrowser 的序列化和 OpenLibrary 的名称规范化分别通过配置边界和 MARC 解析输出重写；新增但不在 Base 的类名或方法名不能因出现在标题、Requirements、Interface 或 Gold 中而变成测试接口；只有 retained P 中出现的完整 qualified symbol 才能例外。

- `src/swepro_trans/validation/semantic.py`：将动态属性和 import 形式的符号引用纳入 Base/Gold 探测，防止隐藏新增 API 依赖。

## 账本的角色

`conversion_trace.json` 和 `f2p_mapping.csv` 只记录每条历史 F2P 的行为意图、公共观测面和生成测试，便于自动发现漏转换、重复映射和 under-conversion。它们不是把工作简化成“填字段后即可 final”的替代物：真正的完成条件是每行都有基于功能目标的 rewrite/merge 测试，缺少 P 描述时已经写入行为级 addendum，并且测试在 Base 已有公共边界上可执行。任何未完成行都会回到 mini-swe repair loop，而不是被标记成 drop 或 gap 后继续打包。

## 2026-09-30 验证结果

- OpenLibrary `attempt_002/rev_005`：6/6 historical F2P 均为 rewrite/merge；artifact、semantic、hard replay、stability、positive QA、negative QA、acceptance 和 package 全部通过。
- qutebrowser：新门槛已发现通过 `getattr` 保留的 Base 不存在 `configutils.FontFamilies` 依赖，并自动进入后续 mini-swe repair。该任务在最新 revision 完成全部门槛前不生成新的 accepted final。
