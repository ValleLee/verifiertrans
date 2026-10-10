# VerifierTrans Agent 工作规范

## 1. 项目目标

VerifierTrans 的目标是将 SWE-Bench Pro 中的 historical F2P 测试转换为面向功能行为的 functional verifier，而不是验证某一种特定参考实现。

转换后的 verifier 应优先检查：

- public API；
- observable output；
- externally visible state change；
- externally observable error semantics。

应尽量避免不必要地绑定：

- private helper；
- 内部状态；
- Gold-specific 文件结构；
- Gold-specific algorithm；
- mock call shape；
- 其他 implementation detail。

基本原则：

- historical F2P 定义本次转换的 scope，即“哪些行为需要被转换和验证”；
- Problem Statement 定义功能语义边界；
- Requirements / Interface 与 historical tests 属于 construction evidence，需要结合仓库事实审慎解释；
- Gold 是一个已知正确实现，可用于 construction 和 validation evidence，但不得反向成为 specification；
- 不得因为 Gold 中存在某种实现方式，就把该实现方式写进 verifier；
- 不得仅因为 Problem Statement 中存在额外行为，就新增没有 historical F2P seed 支持的测试要求。


## 2. 主 Agent 与子 Agent 的职责

主 Agent 负责需要全局上下文、跨阶段综合和较强推理能力的工作，包括：

- 理解 F2P intent 和任务语义；
- 判断 verifier semantic correctness；
- 综合多个阶段的 evidence；
- 判断失败属于 instance-specific 还是 framework-level；
- 根因分析；
- 制定 repair plan；
- 判断是否有充分证据修改共享框架；
- 修改 VerifierTrans 的通用代码、prompt、配置和流程；
- 判断修复是否存在 regression risk；
- 做最终 acceptance 判定。

对于低风险、边界明确、读取量大或机械性较强的工作，应优先委派给默认子 Agent，例如：

- 查看 `state.json`、`events.jsonl`、`progress.json`；
- 阅读 trajectory 和长日志；
- 提取失败命令、return code、stdout/stderr；
- 汇总 Base / Gold replay 结果；
- 检查 artifact 是否存在、schema 是否完整；
- 检查 selector、cwd、module root、mount/path 等执行信息；
- 收集和整理 QA evidence；
- 对 repo 做目标明确的只读探索；
- 在框架修复后执行 deterministic validation 或 replay；
- 汇总执行 evidence。

子 Agent 应返回压缩后的结构化 evidence，不要将大量原始日志整体回灌到主线程。

推荐返回格式：

```text
stage:
failure_category:
observed:
expected:
key_evidence:
suspected_scope: instance | framework | uncertain
relevant_files:
recommended_next_check:
```

不要为了使用子 Agent 而使用子 Agent。

以下情况通常不需要创建子 Agent：

- 一个很短的 shell command；
- 主线程已经掌握的信息；
- 强依赖前一步结果的短链式操作；
- 只需查看几行文件即可完成的检查。

除非有明确理由覆盖，否则普通 spawned subagent 应使用 `.codex/config.toml` 中配置的默认模型和 reasoning effort。

不要让多个 Agent 并行修改同一组共享框架文件。需要修改共享代码时，由主 Agent 统一负责或明确串行协调。


## 3. Failure Classification

遇到失败时，先收集 evidence，再分类。不要看到失败就立即修改 verifier 或框架。

一级 failure category 至少包括：

```text
artifact/schema
infrastructure/execution
selector/cwd/module-root
verifier semantic
candidate
packaging
```

随后进一步判断 scope：

```text
instance-specific
framework-level
uncertain
```

当 scope 仍为 `uncertain` 时，不应修改共享框架。

### instance-specific

如果问题只来自当前 repo、当前构建方式、当前数据特征或当前任务本身，并没有足够证据说明它能够泛化到其他任务：

- 记录问题；
- 在当前任务范围内处理；
- 不污染通用框架。

### framework-level

只有当 evidence 表明问题来自 VerifierTrans 的通用能力缺失或错误，并且合理预期会影响其他任务时，才允许修改共享框架。

单个 instance 在修改后能够通过，本身不能证明该修改属于 framework-level repair。


## 4. 通用框架修改规则

严禁使用以下信息做硬编码特判：

- `instance_id`；
- repo 名称；
- exact commit；
- 当前 historical test 的具体名称；
- 当前任务特有路径；
- 当前任务特有 artifact 名称。

共享框架修改应体现可泛化能力，例如：

- runner discovery；
- ExecutionSpec；
- selector family；
- cwd / module-root detection；
- service bootstrap；
- mount / path contract；
- artifact / schema handling；
- failure classification；
- resume；
- packaging；
- 其他经 evidence 证明具有跨任务意义的 infrastructure / orchestration bug。

在修改共享框架前，主 Agent 应能够回答：

1. 当前观察到的现象是什么？
2. 根因是什么？
3. 为什么这不是当前 instance 的偶然特性？
4. 修改后的规则如何适用于其他任务？
5. 如何验证该修改没有引入退化？

如果无法回答，应继续调查，不要仓促修改共享框架。


## 5. 转换流程

每个新的任务默认从：

```text
Prepare
↓
Preflight
```

开始，除非当前任务明确要求 resume。

不要默认复用旧 attempt。

使用单一 Converter，但区分两个工作模式：

```text
BUILD
  首次生成 functional verifier

REPAIR
  根据 Judge、Hard Validator、replay 或 QA evidence 修复 verifier
```

Converter 可以按需探索完整仓库和允许使用的 construction evidence，但必须对所有 historical F2P seed 做逐条 accounting。

每个 verifier revision 应保持以下 gate 顺序：

```text
Semantic Judge
↓
Deterministic Hard Validator
↓
Base / Gold converted-F2P replay
↓
Base / Gold P2P replay
↓
Stability check
```

后面的 gate PASS 不能作为跳过前面 gate 的理由。


## 6. Functional Verifier 转换原则

转换的目标不是简单重写原测试语法，而是保留原 historical F2P 的行为意图，同时尽量摆脱 implementation binding。

优先寻找能够从真实 public / observable surface 触发和观测行为的方式，例如：

- public API；
- CLI；
- HTTP / service interface；
- 文件输入输出；
- externally visible state；
- observable exception / error；
- 用户可见输出。

避免仅为了复现原 F2P 而直接断言：

- private method；
- private field；
- internal cache；
- 内部容器内容；
- mock call count / exact call shape；
- Gold 新增的内部文件或 helper；
- 只对某个实现路径成立的内部状态。

如果某个 symbol 本身就是产品真实公共契约，则可以验证它；“出现在 Gold 或 historical test 中”本身不足以证明它是公共契约。


## 7. Positive QA

Core verifier 通过后执行 Positive QA。

Positive candidate 应是：

> 功能正确，但实现结构相对于 Gold 有明显差异的 alternative implementation。

Candidate 必须先经过 deterministic precheck，再进入 LLM Solution Judge。

一个 VALID Positive 至少需要满足当前任务定义的 acceptance 条件，例如：

- current verifier PASS；
- P2P PASS；
- Solution Judge 判定 VALID；
- historical F2P replay 已执行并记录。

historical F2P 在 Positive 上 PASS 或 FAIL 可以作为 evidence 记录，但不得单独决定 Positive validity。

Positive QA 的目的，是检查当前 verifier 是否错误地把 Gold 的实现结构当成唯一正确答案。


## 8. Negative QA

Negative candidate 应是 near-correct mutant：

- 每个 mutant 尽量只违反一个明确的 F2P functional semantic；
- unrelated behavior 尽量保持正确；
- 必须能够明确说明它违反了哪一条功能语义；
- 应先通过 candidate deterministic precheck，再进入后续判断。

qualified Negative 必须被当前 verifier 拒绝。

Negative QA 的目的，是确认 verifier 不只是“宽松到什么都能过”，而确实能够区分关键功能错误。


## 9. Repair Routing

如果 evidence 表明是：

```text
verifier semantic issue
```

则回到：

```text
Converter REPAIR
```

不要通过修改 runner、Docker、路径或 framework 逻辑去掩盖 verifier semantic 问题。

如果 evidence 表明问题来自：

```text
path
Docker
artifact
selector
API
mount
schema
cwd
module-root
service bootstrap
execution environment
packaging
```

则：

1. 先完成 failure classification；
2. 判断是 instance-specific、framework-level 还是 uncertain；
3. 只有 framework-level 才修改共享框架；
4. 尽量复用已有 artifact / candidate；
5. 从最早必要阶段恢复，不无条件全部重跑；
6. 不得把 infrastructure failure 误判成 verifier semantic failure。


## 10. Monitoring 与上下文控制

运行过程中使用已有 evidence，包括但不限于：

```text
state.json
events.jsonl
progress.json
trajectory
replay evidence
QA evidence
```

主 Agent 不应反复读取大量原始日志。

当日志较长、重复 replay 较多、或需要从多个 artifact 中抽取事实时，应优先让子 Agent：

1. 读取原始 evidence；
2. 提取关键事实；
3. 按结构化格式返回；
4. 主 Agent 再进行跨阶段推理。

这样做的目的是让主线程保留：

- task requirements；
- semantic decisions；
- framework decisions；
- repair rationale；
- final acceptance evidence。

而不是被大量机械日志占满上下文。


## 11. Framework Issue 文档

每发现并确认一个 framework issue，或完成一个 framework repair，都应在：

```text
VerifierTrans/process/
```

写入带 UTC 时间戳的 Markdown 记录。

至少记录：

```text
现象
关键 evidence
failure classification
根因
为什么属于 framework issue
影响范围
通用修复
修改文件
验证方法
测试结果
残余风险
```

如果只是 instance-specific / repo-specific / data-specific 问题，也可以记录，但必须明确标注其 scope，不得据此向共享框架加入特判。


## 12. Progress Reporting

不要逐条汇报无意义的 shell command。

应在有实质信息的节点进行汇报，例如：

- Prepare / Preflight 结果；
- Semantic Judge PASS / FAIL；
- Hard Validator PASS / FAIL；
- Base / Gold replay 结果；
- P2P 结果；
- verifier revision 变化；
- Positive / Negative QA 结果；
- failure classification；
- confirmed framework issue；
- framework repair；
- final acceptance status。

推荐简洁格式：

```text
当前阶段:
状态: PASS | FAIL | RUNNING
关键 evidence:
failure category:
scope:
是否修改框架:
下一步:
```

如果只是长时间运行的命令，可以在有状态变化或出现 blocker 时再汇报。


## 13. 安全与边界

除非当前任务获得明确授权，否则：

- 不输出 `.env` 或其他 secret；
- 不在日志、报告、测试输出中打印 API key；
- 不删除无关 Docker container / image；
- 不删除其他任务的 runs；
- 不删除旧项目或无关工作目录；
- 不修改当前任务授权范围之外的资源。

清理资源时，只清理能够确认由当前任务创建且不再需要的临时资源。


## 14. Acceptance 原则

不得为了宣布成功而弱化验收条件。

如果任务未满足当前 Goal 中的全部 success criteria：

- 如实标记为未完成或 blocked；
- 列出已完成 gate；
- 列出失败 gate；
- 给出关键 evidence；
- 说明 blocker；
- 说明继续执行需要什么；
- 不通过降低标准、跳过 QA 或放宽 verifier 来制造“成功”。

最终目标始终是：

> 通过真实 SWE-Bench Pro 任务检验 VerifierTrans 的转换质量和通用性，只把具有跨任务意义的问题沉淀为共享框架能力，而不是为了让单个 instance 特判通过。
