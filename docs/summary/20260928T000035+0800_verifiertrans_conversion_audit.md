# VerifierTrans 转换框架审计

> 审计时间：2026-09-28 00:00:35（Asia/Shanghai）  
> 审计范围：`VerifierTrans` 当前代码、4 条已发布转换运行、`final_task` 产物、`Data/deepswe/tasks` 参考目录  
> 目标：判断 SWE-Bench Pro historical F2P 是否已经被转换为面向功能、允许多种实现的 DeepSWE 类任务，以及框架是否具备批量稳定转换能力。

## 结论

当前框架已经形成一条可执行的转换流水线：Prepare 冻结 source 和执行契约，Converter 生成功能 verifier，确定性校验和 Semantic Judge 审查语义，Hard Validator 做 Base/Gold/F2P/P2P 回放，Positive/Negative QA 检查实现多样性与拒绝能力，最后生成 DeepSWE 形态的 `final_task` 并执行 package smoke。

已有 4 条真实 Docker 运行（Python、JavaScript/React、Go、TypeScript/Node）都通过了核心门禁和 smoke，因此可以称为“可批量运行的 beta 框架”。当前证据还不足以称为对 SWE-Bench Pro 任意任务都稳定、无人工介入的通用转换器，原因是：模型生成仍具有非确定性；四条样本的 P2P 和 F2P accounting 差异很大；两条运行没有 retained P2P；Tutanota 的 78 条 suite-level F2P 中 77 条被 drop；Navidrome 的 instruction 和 verifier 明确绑定了内部可见性结构。

因此，本次审计判定为：

- 框架主流程：**已闭环，适合继续批量试运行**。
- 已发布任务的硬执行质量：**4/4 通过**，但这是实例级证据，不是总体成功率。
- instruction 面向功能：**3 条基本通过，Navidrome 需要修订或人工豁免**；Element 的公开 DOM icon selector 和 Tutanota synthetic runtime 需要持续做替代实现审计。
- 生产级稳定性：**尚未达到**。应先完成下文的高优先级修复和更宽的 fresh matrix。

## 1. 实际架构

代码实际执行顺序如下：

```text
SWE-Bench Pro parquet row
  -> Prepare: source boundary + base checkout + selector freeze + preflight
  -> Converter BUILD/REPAIR
  -> artifact/schema sanity + manifest normalization
  -> fresh Semantic Judge
  -> deterministic Hard Validator
       Base/Gold converted F2P
       Base/Gold retained P2P
       repeat + stability
  -> accumulated evidence replay
  -> Positive QA: deterministic precheck -> Solution Judge -> replay
  -> Negative QA: near-correct mutant -> Mutation Judge -> replay
  -> package_task -> package_smoke
  -> atomic final_task publication
```

职责边界已经在代码中分开：

- `pipeline/orchestrator.py` 是单实例控制器，负责 revision、重试、修复路由和 gate 顺序；没有独立 design agent，Converter 只有 BUILD/REPAIR 两种模式。
- `deterministic/preparation/prepare_instance.py` 生成 immutable `source/`、物化 Base repo、解析 historical test selectors，并冻结 `ExecutionSpec`。
- `deterministic/execution/discovery.py` 从仓库原生 metadata 识别语言、runner、cwd、module root、selector 风格、TypeScript loader、service、timeout 和 result parser。后续 replay、candidate replay、package smoke 都消费同一份 spec/hash。
- `deterministic/validation/validate_verifier.py`、`artifact_contract.py` 和 `path_contract.py` 检查 manifest、coverage accounting、路径和 artifact schema；模型不能靠一个可执行 `run.sh` 绕过正式 artifact 声明。
- `deterministic/replay/verifier.py` 执行统一的 Base/Gold F2P/P2P 硬门禁；Docker、mount、cwd、selector、service、toolchain、timeout 和 marker 错误归为 infrastructure。
- `pipeline/qa.py` 与 orchestrator 实现 positive/negative evidence contract。Positive 必须经过结构差异检查、Solution Judge 和再次 replay；Negative 必须是只违反一个已映射语义的 mutant，并被当前 verifier 拒绝。
- `deterministic/packaging/package_task.py` 只读取 accepted manifest、Prepare 生成的 `p2p_assets.json` 和冻结 ExecutionSpec，对原始 test patch 做确定性 P2P accounting，生成 `task.toml`、`instruction.md`、`tests/`、`environment/` 和 `solution/`。
- `deterministic/packaging/package_smoke.py` 在 clean Base checkout 上应用 package wiring 和 Gold patch，执行最终 `tests/test.sh`；只有 smoke PASS 才发布 `final_task`。
- `batch.py` 只负责已 Prepare workspace 的有界并发调度和 `batch_summary.json` 汇总，不能替代单实例 gate，也不能把模型调用变成确定性过程。

`runs/<instance_id>/` 的 canonical 布局和容器语义已同步更新到 [`docs/architecture.md`](../architecture.md)。`source/` 是输入和 construction evidence 边界；`intermediate/attempts/attempt_NNN/` 保存可变阶段产物；`.compat/` 是相对 symlink 兼容视图；`final_task/` 只包含 package 后的公开任务材料。

## 2. 已转换结果审计

### 2.1 实例级 gate 结果

| instance | repo/ExecutionSpec | F2P / P2P | revision | Hard Validator | QA | package smoke |
| --- | --- | ---: | ---: | --- | --- | --- |
| Element Web | JavaScript/React + Jest | 10 / 39 | 7 | Base F2P FAIL、Gold F2P PASS、Base/Gold P2P PASS、stable | 1 positive + 2 mutants | PASS |
| Navidrome | Go + go test | 3 / 0 | 2 | Base F2P FAIL、Gold F2P PASS、Base/Gold P2P PASS、stable | 1 positive + 2 mutants | PASS |
| qutebrowser | Python + pytest | 4 / 52 | 2 | Base F2P FAIL、Gold F2P PASS、Base/Gold P2P PASS、stable | 1 positive + 2 mutants | PASS |
| Tutanota | TypeScript/Node + repository-native ospec harness | 78 / 0 | 3 | Base F2P FAIL、Gold F2P PASS、Base/Gold P2P PASS、stable | 1 positive + 2 mutants | PASS |

证据位置：每个实例的 `review/metrics.json`、最新 attempt 的 `validation/hard_replay/`、`qa/evidence.json`、`packaging/smoke_report.json`、`final_task/provenance.json`。所有四条运行的 `instruction_scope.md` 都以 `INSTRUCTION_SCOPE: PASS` 结束，所有 `conversion_trace.json` 都覆盖了全部 canonical F2P id。

### 2.2 F2P accounting

- Element：10 条 F2P，5 条 `rewrite`、5 条 `keep`；快照被改写成 DOM、可访问性和交互副作用断言。instruction 明确排除了 private helper、内部结构、private icon markup 和动画细节，整体符合面向可观察行为的目标。
- qutebrowser：4 条 F2P 全部 `keep`，断言 `qtlog.hide_qt_warning` 的日志级别、消息保留和前缀过滤结果；这是四条中最干净的 public API 功能转换。
- Navidrome：3 条 suite-level F2P 全部 `rewrite`，功能回放之外又加入 AST surface guard 检查客户端类型、构造器和低级方法的导出状态。它证明了 encapsulation 任务，但测试的核心是源码结构，而不是可替换实现可观察行为。
- Tutanota：78 条 suite-level F2P 中 1 条 `rewrite`、77 条 `drop`。drop 的理由是原始 bundled suite 因一个缺失方法而整体 fail-to-pass，其他 suite 没有由 Problem Statement 支持的新增行为。accounting 逻辑是可追溯的，但最终功能覆盖高度集中在一个 sanitizer 行为上，不能把“78 条均已独立转换”作为结论。

## 3. instruction 是否透露实现绑定

### 通过项

qutebrowser instruction 使用 `qutebrowser.utils.qtlog.hide_qt_warning` 这一题目要求的公共入口，并以日志捕获结果描述行为，没有写入 helper、字段、文件布局或 mock 调用形状。Tutanota instruction 以 `HtmlSanitizer.sanitizeInlineAttachment(dirty) -> DataFile` 的公共入口和返回数据行为为中心，也没有暴露测试路径。

Element instruction 大部分是 rendered DOM 和用户交互边界；它仍要求 `mx_KebabContextMenu_icon` selector。这是历史测试暴露的公开 DOM selector，属于可观察界面契约，但 CSS class 仍有脆弱性，建议在后续转换中优先采用角色、label、aria 状态和公开事件结果，只在 F2P 明确要求时保留 class selector。

### 需要修订的项：Navidrome

Navidrome instruction 直接出现以下实现可见性表述：

- concrete HTTP client type must be package-private/unexported；
- client constructor must be package-private/unexported；
- low-level client methods must be package-private/unexported；
- 指定 LastFM、ListenBrainz、Spotify 三个内部 package 和若干低级方法类别。

对应 verifier `verifier_test.go` 使用 Go AST 扫描 package surface，通过 `Client` 后缀、`New…Client` 构造器、具体方法拼写和 `Do(*http.Request)` 形状推断目标类型。这不是普通的功能替代实现检查，而是对语言级可见性、命名和包内源码结构的硬约束。若该任务的真实产品契约就是“外部 package 不能构造或调用低级 client”，可以保留“外部调用者不可见”的公共 API 语义，但应删除具体 type/method 拼写和 AST 识别启发式，并用跨 package 编译/调用失败及高层 agent 行为来验证。

审计结论：Navidrome 当前 `INSTRUCTION_SCOPE: PASS` 只表示 Converter 自己的 scope trace 完整，不表示它已经满足“面向多种实现、instruction 不绑定实现细节”的验收要求。

## 4. 框架稳定性与批量能力

### 已经具备的稳定性基础

- 每次 Prepare 都创建新 attempt；source、sealed、restricted 和 public contract 有明确边界，旧 attempt 通过 resolver 兼容读取。
- revision snapshot、verifier hash、`execution_spec_hash` 和 evidence contract 绑定，resume 不会静默复用不同 revision 的旧 evidence。
- hard gate、QA replay、package smoke 共用冻结 ExecutionSpec；同一 attempt 不会因重新 discovery 改变 cwd、runner 或 selector 语义。
- infrastructure 与 verifier semantic 分流，基础设施失败只做有界 retry，不用改 verifier 语义来掩盖 Docker/selector/timeout 问题。
- package patch accounting 可报告 retained、excluded、shared、fixture 和 ambiguity；最终发布是原子 rename。
- `.venv/bin/python -m pytest -q` 已通过 141 个仓库测试（2026-09-28），证明本地 deterministic contract 和 isolation 测试当前通过。

### 仍不能称为“批量稳定生产”的原因

1. **模型层非确定性。** Converter、Positive/Negative generator 和 Judges 依赖外部模型；step cap、timeout 和 retry 能限制成本，却不能保证同一输入得到相同 verifier。
2. **P2P 不可缺省为空。** Navidrome、Tutanota 的 retained P2P 为 0，当前硬门禁仍可接受。对“不得破坏历史行为”的任务，空 P2P 会显著降低回归保护，应成为需要显式解释或人工批准的状态。
3. **suite-level F2P 会掩盖 coverage gap。** Tutanota 的 77 个 drop 是有理由的，但需要在报告中将“source accounting 完整”和“独立功能覆盖充分”分别计量。
4. **harness 可能重新绑定实现。** Tutanota 使用 synthetic DOM、TS transpiler 和 runtime shim；Element 依赖公开 DOM class selector。Positive QA 只有 1 个 accepted alternative，不能覆盖所有 fixture/shim 误报。
5. **服务和 runner 覆盖有限。** 当前 adapter 主要覆盖 Python/pytest、Node 的 Jest/Mocha/Vitest/ospec、Go test，并对 Redis 做有界 bootstrap；未知 runner、复杂多服务和需要网络的任务仍会被标成 unsupported/infrastructure。
6. **生成的 grader 只实现了最小 aggregate-exit 合约。** `package_task.py` 生成的 `tests/grader.py` 只有 `prepare` 和 `grade`，而 `Data/deepswe/tasks` 的参考 grader 还提供 `patch-paths`、按 F2P/P2P node 读取报告、partial reward 和更完整的失败统计。当前 package smoke 证明自有 test.sh 能跑通，不足以证明接入所有 DeepSWE evaluator 时完全兼容。
7. **batch 是调度器，不是全自动质量保证。** batch 要求先 Prepare，按 workspace 并发调用 controller；它没有跨任务质量阈值、自动 quarantine、失败重试策略汇总或人工复核替代机制。
8. **四条样本不能代表总体成功率。** 现有证据是 4/4 通过的实例集合，不是 SWE-Bench Pro 全量统计，也没有完成不同 runner/service/repository layout 的 fresh matrix。

## 5. 问题清单与修复建议

| 优先级 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| P0 | Navidrome instruction 和 AST verifier 绑定 unexported type/constructor/method 与内部包结构 | 违反面向多实现目标；合法重命名/重构可能被拒绝 | 重新定义为外部 package 的 public API 不可构造/调用 + 高层 agent 行为；移除 exact spelling、后缀启发式和源码结构扫描，或记录明确的“API visibility task”豁免 |
| P1 | P2P 为空仍可发布 | 缺少回归保护，package 可能只验证 converted F2P | 对空 P2P 增加显式 policy：要求 Problem Statement 解释、人工批准或将结果降级为 audit-only；报告中单独统计 `p2p_absent` |
| P1 | suite-level F2P drop 与独立行为覆盖没有分开计量 | 容易把 accounting 完整误读为行为覆盖完整 | 在 report/metrics 增加 `mapped_behavior_count`、`dropped_suite_count`、`drop_reason` 汇总和最低覆盖阈值 |
| P1 | synthetic harness/shim 的公共 API 兼容性不足 | alternative implementation 可能在断言前因 fixture 缺失而失败，形成 false negative | 为 DOM、XML、TS runtime 建立标准 API contract smoke；对 candidate 失败区分 harness failure 与 semantic failure；保留 Tutanota DOM/runtime 修复过程记录 |
| P1 | instruction 未做确定性实现绑定 lint | Navidrome 这类泄漏只能靠人工发现 | 在 package gate 增加 instruction linter：禁止 absolute path、historical test id、Gold/file layout、private helper、exact mock shape；对语言可见性要求标记需要人工豁免 |
| P1 | generated grader 与参考 DeepSWE grader 合约不完整 | 外部 evaluator 可能调用 `patch-paths` 或依赖 node-level/partial reward 字段而失败 | 让 package 生成共享 grader 或实现完整兼容命令；至少增加 `patch-paths`、按 config node ids 的报告解析和标准 reward 字段，并用一个真实 DeepSWE runner 做 integration smoke |
| P2 | batch 缺少全量质量汇总策略 | 批量运行后仍需人工逐个查 report | 增加按 failure domain、P2P 缺失、drop 比例、QA contract、smoke 状态的 batch summary 指标和 quarantine 队列 |
| P2 | 四生态代表性不足 | 无法推断未知 runner/service 的成功率 | 完成 Python/Node/TS/Go × runner/service/layout 的 fresh matrix，并保存每格的 preflight、hard replay、QA、smoke 结果 |
| P2 | 模型和依赖版本漂移 | 同一任务可能生成不同 artifact 或执行结果 | 固定 model endpoint/model id、prompt hash、依赖 lock、Docker image digest，并把它们写入 provenance；对重跑保留随机种子或明确不可复现标记 |

## 6. 建议的发布判定

在修复 P0/P1 前，建议将框架标为“受控 beta”：可以批量 Prepare、运行和产出 DeepSWE 形态任务，但每个 task 仍需检查 instruction scope、P2P 是否为空、drop 比例和 QA evidence。

达到“可批量稳定转换”应至少满足以下条件：

1. instruction binding lint 通过，或有明确、可审计的 API visibility 豁免；
2. 空 P2P、过高 drop 比例和 unsupported runner 不再静默进入发布；
3. 生成的 grader 通过参考 DeepSWE evaluator 的完整合约检查；
4. Base/Gold/P2P stability、至少一个结构不同 positive、至少两个语义 negative、package smoke 全部通过；
5. synthetic harness contract smoke 和 candidate failure classification 通过；
6. fresh matrix 覆盖主要语言、runner、service 和仓库布局，并能给出按 failure domain 的成功率；
7. batch summary 能自动标出需人工复核的任务，不把 `VERIFIED` 单独当作总体质量证明。

## 7. 可复核命令与证据

```bash
cd /lg-home/cog8/lwli6/VerifierTrans
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src tests
```

重点审计文件：

- 架构：[`docs/architecture.md`](../architecture.md)
- 运行总览：`runs/<instance_id>/review/metrics.json`
- F2P accounting：`intermediate/attempts/attempt_NNN/converter/current/conversion_trace.json`
- instruction：`intermediate/attempts/attempt_NNN/converter/current/instruction_scope.md` 与 `final_task/instruction.md`
- 硬门禁：`validation/hard_replay/` 或 `.compat/run/check.json`
- QA：`qa/evidence.json`
- package accounting：`packaging/package_report.json` 与 `final_task/tests/package_report.json`
- smoke/provenance：`packaging/smoke_report.json`、`final_task/provenance.json`

最终判断应以这些结构化 evidence 为准，而不是只看 controller 的退出码或 `VERIFIED` 标签。
