# F2P 功能转换与规格缺口审订流程

## 目标

Stage 2 的目标是把 historical F2P 转成基于 Base repo 公开接口或可观察输出的 functional verifier，同时保留每条 F2P 背后的行为意图。`final` 不能通过填写完整账本来掩盖未完成的功能转换。

## 共享框架规则

### 1. Problem Statement 是唯一规范来源

- `source/problem_statement.md` 是解题者可见的不可变规范输入。
- Requirements、New Interfaces、historical tests、Gold、repo 和 environment 只是 construction evidence。
- Converter 可以写 `functional_specification.md`，但它是非规范的 proposal record，不会自动并入最终 instruction。
- 只有显式审订 `source/problem_statement.md` 并重新启动转换，缺失行为才会成为解题契约。

### 2. 每条 F2P 的决定

每条 canonical historical F2P 必须恰好出现一次，决定只能是：

- `rewrite`：改写为一个或多个公开行为测试；
- `merge`：与其他 F2P 合并为公开行为测试；
- `specification_gap`：行为重要且可观察，但当前 P 没有授权该行为。

`drop` 和 `manual_review` 不是合法 F2P 决定。`specification_gap` 也不是成功结果：它会停止当前 revision，阻止 hard replay、QA、acceptance 和 final packaging。

### 3. specification_gap 的内容

Gap 行必须包含：

- `specification_gap`：缺少的行为语义；
- `specification_proposal`：建议补充到 P 的行为级文字；
- `planned_observable_surface`：审订后计划使用的 Base 公开/可观察边界；
- `emitted_tests: []` 或尚未发布的候选测试，不得作为最终判分测试。

Proposal 不得指定新增类名、方法名、模块路径、构造器、签名、类型存在性、Gold 文件或特定实现算法。

## Pipeline 行为

```text
F2P accounting
       │
       ├─ rewrite / merge + public test ──> semantic gate
       │                                      │
       │                                      └─> replay -> QA -> acceptance -> final
       │
       └─ specification_gap ───────────────> specification_review_required
                                              │
                                   审订 source/problem_statement.md
                                              │
                                   新 attempt 重新 Converter
```

Controller 在 artifact contract 通过后检查 gap。发现 gap 时写入 `validation/specification_review.json` 和状态 `specification_review_required`，不调用自动 repair 来偷偷补写 P，也不生成 `final/`。

## 各组件职责

- `prompts/converter.md`：指导逐条行为映射和 gap proposal。
- `agents/runner.py`：校验决定集合和 gap 字段，不允许 drop。
- `validation/revision.py`：校验 F2P 完整覆盖、每行唯一、rewrite/merge 测试和 gap proposal。
- `validation/semantic.py` 与 semantic Judge：检查 under-conversion、Gold-only/private binding，并将 gap 判为当前 revision 的 FAIL。
- `pipeline/orchestrator.py`：将 gap 路由到 `specification_review_required`，不进入 QA 或 package。
- `validation/acceptance.py`：要求 100% rewrite/merge、0 unresolved gap、0 drop、0 manual_review、0 hidden-contract violation。
- `reporting/human_review.py`：分别列出 rewrite、merge、specification_gap、提议 P 文本和计划观测面。
- `layout.py`：final instruction 只复制经过审订的 `source/problem_statement.md`，proposal 只作为审计记录。

## 两类任务的处理

### qutebrowser FontFamilies

历史 `test_to_str` 不能因为直接构造新增类型而删除。若配置系统的公开读写边界在 Base 中可用，先将顺序保持、逗号分隔和可重新读取等行为改写到该边界；若这些行为没有被 P 授权，则输出 `specification_gap`，提出行为级 P 文本，等待审订后重跑。

### OpenLibrary name_from_list

历史 helper 调用应改写为 MARC 输入到公开作者结构的集成行为，覆盖 100、700、720、880 等输入及 `name` / `alternate_names` 输出。若名称规范化行为没有出现在 P，先输出 gap proposal；不能因为 Gold 中存在 helper 就将 helper 变成隐藏解题接口。

## 验证要求

每次重新转换后必须检查：

1. canonical F2P 数量与 trace 行数一致；
2. 每行唯一且决定合法；
3. rewrite/merge 每行有真实 emitted test；
4. gap 行具有完整 proposal，且 pipeline 在 review 状态停止；
5. accepted revision 的 gap、drop、manual_review 数量均为 0；
6. final instruction 的 hash 与审订后的 Problem Statement 一致；
7. 通过 Base/Gold replay、stability、positive QA 和 negative QA。


## 本轮重新转换记录（2026-09-30）

- qutebrowser `attempt_004/rev_001`：artifact contract 通过；11/11 F2P 记录为 `specification_gap`，包含行为级 proposal；pipeline 已自动停止为 `specification_review_required`，没有执行 replay/QA，也没有生成 final。
- OpenLibrary：已分配新的 `attempt_003`，真实 Converter 等待任务上下文外发授权。
