# F2P 功能转换框架本轮修改总结

## 记录信息

- 时间：2026-09-29 16:23:38 UTC（2026-09-30 00:23:38 +08:00）
- 范围：VerifierTrans / Swepro_test_trans 共享转换框架
- 验证任务：qutebrowser `instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d`
- 当前 attempt：`attempt_002`

## 目标调整

本轮将转换目标收敛为：

1. 保留每条 historical F2P 想验证的功能行为；
2. 尽量把断言移动到 public API 或其他可观察边界；
3. 不把 Gold 的新增方法、模块路径、内部结构自动当作 solver 契约；
4. 不再增加独立的“意图解析 Agent”。意图解析作为单个 mini-swe Converter 对每条 F2P 的必需子步骤；
5. 每条 F2P 必须有明确去向，不能静默删除；
6. 语义不确定时停止打包并进入人工审阅，不通过放宽规则制造成功。

## 观察到的问题

早期转换暴露了四类可跨任务复现的问题：

1. F2P 只有 selector accounting，没有记录行为意图、可观察表面和证据，导致可观察的序列化行为被误删；
2. verifier 直接调用 Gold 新增的 `FontFamilies.from_str`，把参考实现接口当成了题目契约；
3. 语义扫描器用符号的最后一个组件匹配 Gold diff，把普通的 `font.families` 误判成 Gold-only 符号；
4. 路径解析依赖 `runs/<id>/original` 是否存在。Docker 挂载或旧产物留下同名目录后，派生产物可能被误当成 Stage 1 原始任务。

这些问题分别属于转换语义、artifact contract、语义扫描和 canonical path contract，具有跨任务意义，不能通过当前 instance 特判解决。

## 已落地的框架修改

### 1. Converter 改为逐条 F2P 轻量意图映射

Converter 仍是一个 mini-swe Agent，但对每条 F2P 强制执行以下步骤：

1. 描述 historical assertion 背后的行为意图；
2. 将意图映射到 Problem Statement 的语义；
3. 识别 private symbol、内部状态、Gold-only 路径、mock 细节和固定序列化调用；
4. 寻找 public API、CLI、文件输入输出、外部状态、异常或用户可见输出；
5. 选择 `rewrite`、`merge`、`manual_review` 或例外性的 `drop`；
6. 记录 emitted tests 和理由。

每条 F2P 的 `conversion_trace.json` 现在至少需要：

```text
source_f2p
behavior_intent
functional_surface
evidence
decision
emitted_tests
rationale
```

`rewrite`/`merge` 必须产生测试；`drop` 必须有明确的不可恢复理由；`manual_review` 不得伪装成已经完成的转换。

### 2. 明确 Problem Statement、construction evidence 和 Gold 的边界

- `problem_statement.md` 是唯一的 solver normative specification；
- Requirements、Interface、historical tests、P2P、Gold、Repo 和 Env 只用于解释意图与构造验证；
- Problem Statement 明确命名的 class 可以保留 class-level 契约；
- 未被 Problem Statement 明确声明的 method、module path、signature 和 Gold-only helper 不自动成为契约；
- 如果行为可由基础仓库中的公开边界表达，优先改写到该边界；
- 如果无法证明存在公开或可观察边界，进入 `manual_review`。

这条规则解决了“为了保留 selector 而直接调用 Gold 新增 API”的问题。

### 3. 强化 artifact/schema gate

`revision.py` 现在检查：

- 标准 verifier 文件是否齐全；
- `conversion_trace.json` 是否覆盖全部 canonical F2P；
- 每行是否包含行为意图、functional surface、evidence、decision、emitted tests 和 rationale；
- `rewrite`/`merge` 是否真的有 emitted tests；
- `manual_review` 是否错误地产生了已完成测试；
- `drop` 是否提供 justification；
- specification source 是否为 `source/problem_statement.md`；
- `self_review.md`、`manifest.json` 和测试文件是否满足 artifact contract。

### 4. 语义扫描改为完整限定符匹配

Gold-only 检查现在只在以下条件同时满足时触发：

- 候选 verifier 中出现完整限定符；
- 完整限定符出现在 Gold 新增行；
- Base 中不存在该符号；
- Problem Statement 没有明确支持该符号。

不再使用最后一级名称匹配。因此普通变量或库方法，例如 `families`、`status`、`items`，不会仅因为 Gold 中出现同名局部变量就被判为隐藏契约。

### 5. Judge 不确定时停止自动修复

语义 Judge 返回空响应、不可解析 JSON 或重试后仍为协议错误时，结果记录为 `UNCERTAIN`：

- 不把协议错误当作 verifier semantic FAIL；
- 不自动触发新的 Converter revision；
- 写入 `manual_review_required` 状态；
- 保留已有 revision、replay 和 Judge evidence，等待人工决定。

这避免了模型没有给出语义反馈时，Converter 无依据地重写一个可能正确的 verifier。

### 6. 统一 canonical task/run 路径

`resolve_task()` 现在遵循固定布局：

```text
tasks/<id>/original       immutable Stage 1 source
runs/<id>/                derived run root
runs/<id>/attempts/...    attempt artifacts
```

从 task root、run root 或 attempt root 进入时，均回溯到 `tasks/<id>` 作为原始输入。旧的 `original/` 目录推断只作为外部旧 checkout 的最后兼容分支，不能覆盖 canonical layout。

### 7. 调整语义 Judge 输出预算

语义 Judge 使用紧凑 JSON 协议，`judge_max_tokens` 调整为 4096。此前 16384 的配置在同一证据上多次产生协议不确定；4096 曾成功返回结构化、可执行的语义反馈。该参数调整是通用的协议稳定性修复，不依赖具体任务。

## qutebrowser 验证结果

证据位置：

- [metrics.json](/lg-home/cog8/lwli6/Swepro_test_trans/runs/instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d/attempts/attempt_002/review/metrics.json)
- [conversion_audit.json](/lg-home/cog8/lwli6/Swepro_test_trans/runs/instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d/attempts/attempt_002/review/conversion_audit.json)

结果：

- 11/11 条 F2P 均有映射；
- `drop_count = 0`；
- 两条序列化行为仍被覆盖；
- artifact contract：PASS；
- deterministic binding gate：PASS；
- Gold replay：57/57 PASS；
- Base replay：46/57 PASS，11 条新增功能测试未通过，符合预期；
- 最新语义 Judge 调用仍为 `UNCERTAIN`；
- stability、positive QA、negative QA 和 package 按门槛顺序未执行；
- 当前状态：`manual_review_required`，没有生成 `final/`。

这个结果表示框架正确阻止了在语义证据不足时发布最终包。它不表示 11 条 F2P 已经被证明可以自动接受。

## 修改文件类别

本轮涉及的共享能力集中在以下类别：

- Converter prompt：逐条 F2P 意图、surface、evidence 和决策规则；
- Artifact validation：trace schema、accounting 和 drop 约束；
- Semantic validation：Base/Gold symbol provenance 和 P-only class boundary；
- Pipeline orchestration：`UNCERTAIN` 的人工审阅路由；
- Path resolution：canonical task/run/attempt 解析；
- Experiment config：Judge JSON 输出预算。

## 残余风险与后续规则

1. `manual_review` 仍是必要的终态。某些 historical F2P 的行为意图可能没有稳定的 public/observable surface，不能用弱测试掩盖边界；
2. 当前 artifact schema 允许有 justification 的 `drop`，后续可以根据更多任务证据决定是否把它提升为默认拒绝、只允许人工批准；
3. Base/Gold replay 证明执行和差异，但不能替代语义 Judge；
4. Positive/Negative QA 只有在语义和 deterministic gate 都通过后才有意义；
5. 后续任务应优先检查 `conversion_trace.json` 和 `review/metrics.json`，而不是从目录名称推测流程状态。

## 验证记录

- 共享 Python 代码执行 `python -m compileall -q src`：通过；
- canonical task/run/attempt 三种入口均解析到 `tasks/<id>/original`；
- qutebrowser rev_004 artifact contract：通过；
- qutebrowser rev_004 deterministic binding gate：通过；
- qutebrowser Gold direct replay：57/57 通过；
- qutebrowser Base direct replay：11 条功能 F2P 未通过，符合预期的 Base/Gold 区分；
- 语义 Judge 协议不确定时未继续自动 repair，已记录人工审阅状态。

## 结论

本轮把“额外增加一个意图 Agent”的方案收敛为单 Converter 内的逐条意图映射，并补齐了 artifact、隐藏契约、路径和 Judge 不确定性门槛。后续转换的最小合格条件是：每条 F2P 有可审计映射、没有静默删除、测试使用可证明的公开或可观察边界、确定性 replay 通过，并且语义 Judge 得到明确结果。未满足这些条件时保持 `manual_review_required`，不生成最终包。
