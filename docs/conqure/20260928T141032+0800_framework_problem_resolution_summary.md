# VerifierTrans 主要问题与处理方式总结

时间：2026-09-28 14:10:32（Asia/Shanghai）

本文根据历史对话、`process/` 过程记录、转换审计和 qutebrowser/Navidrome 等实际运行结果，
把这段时间遇到的问题压缩为几类主线。重点是说明问题如何被识别、如何判断责任边界，以及
修复后形成了什么通用契约。

## 总结结论

这次工作的核心不是不断修改某一个 verifier，而是逐步把转换框架的边界收紧：

```text
正确输入
  → 正确的 Base checkout
  → 冻结的仓库原生 ExecutionSpec
  → 可审计的 functional verifier artifact
  → 统一、语言正确的容器 replay
  → 可区分基础设施与语义的 QA
  → 可复用的 DeepSWE package
```

qutebrowser、OpenLibrary、NodeBB、Element Web、Tutanota 和 Navidrome 的运行暴露了不同层
的问题。现在框架已经能够完成代表性的跨语言转换，但仍应称为受控 beta：模型服务、复杂
仓库运行环境和 verifier 的语义质量仍需逐任务验证。

## 1. 输入和 Prepare 不可信：stale repo、Docker 权限和路径错误

### 遇到的问题

最早的 Prepare 只判断 repo 目录是否存在。Docker materialization 失败后，`/tmp` 中旧的
staging 目录仍然存在，框架把它误判为本次 Base checkout 成功。类似问题还包括：

- Docker socket 或镜像权限失败被混入后续语义流程；
- `/app`、`/workspace`、`test/tests` 等容器路径被直接当成仓库相对路径；
- JS/TS 扩展名别名、扁平化测试目录和 basename 歧义导致错误 missing-file；
- image 内已有 `node_modules`，但 preflight 的 host mount 把它遮蔽。

### 处理方式

Prepare 现在是确定性 source gate：必须同时满足 materialization return code 为 0、观测到的
HEAD 等于声明的 base commit、repo link 有效且目录存在。selector 在 Prepare 阶段统一解析并
写入 `restricted/resolved_test_selectors.json`，不让 Converter 自己猜路径。预检改为在容器
内保留 image 依赖，再检查 repo、toolchain、collection 和 selector。

### 当前状态

这类问题归为 `INFRASTRUCTURE`，不会生成 semantic repair，也不会消耗 Converter revision。
对应记录包括：

- `20260922T025500Z_framework_prepare_materialization_gate.md`
- `20260922T161653Z_framework_selector_logical_root_normalization.md`
- `20260922T162223Z_framework_preflight_preserve_image_dependencies.md`

## 2. Docker 中“能挂载”不等于“会正确执行”：runner、mount、cwd 和 service

### 遇到的问题

Verifier 确实在 Docker 中运行，但早期各阶段的执行契约不统一：

- NodeBB 的 P2P 被错误交给 Python runner；
- runner 挂载到错误的 `/framework`、`/app/framework` 或 `/workspace/framework`；
- Docker mount 被追加到 image 之后，实际上没有生效；
- verifier 从 `/verifier` 推导仓库根目录为 `/`，找不到 `/app` 下的源码或测试；
- Node/TS loader、Jest 标题、ospec cwd/env、selector 批量执行方式不一致；
- NodeBB 镜像有 Redis，但 `/bin/bash` entrypoint 不会自动启动 Redis；
- 原生 TS/JS 编译超过统一 timeout；
- Navidrome 的 `run.sh` 被 Go adapter 错误生成为 `go test /app/verifier/run.sh`。

### 处理方式

框架收回通用运行职责，新增冻结的 `ExecutionSpec` 和统一 execution adapter：

- Prepare 根据仓库 metadata 发现 language、runner、cwd、module root、loader、service、
  timeout 和 selector style，并写入 hash；后续 replay 不重新 discovery；
- F2P、P2P、candidate replay 和 package smoke 共用同一 adapter、mount 顺序、cwd 和环境；
- Python、Node/TypeScript、Go 使用语言对应 runner；`.sh/.bash` functional artifact 按后缀
  用 `bash`，不会按仓库语言盲目调用 native compiler；
- Redis 仅在镜像同时提供 `redis-server`/`redis-cli` 时有界启动并等待 readiness；
- 候选 replay 对 `/app`、`/workspace`、`/framework` 和 `/restricted` 提供兼容挂载，避免
  runner 的相对路径把合法 candidate 误判为失败；
- Go 裸 `TestXxx`/`BenchmarkXxx`/`FuzzXxx`/`ExampleXxx` selector 会解析到唯一 `_test.go`
  package，找不到或歧义时明确失败。

### 当前状态

这是通用框架问题，不能通过修改某个 verifier 掩盖。qutebrowser 和 Navidrome 的最终
package smoke 都证明了修复后的 adapter 与 package wiring 一致。关键记录包括：

- `20260922T033000Z_framework_js_replay_entrypoint_fix.md`
- `20260922T034000Z_framework_redis_runtime_bootstrap.md`
- `20260922T151824Z_framework_docker_mount_order.md`
- `20260922T161012Z_framework_candidate_mount_order.md`
- `20260928T114544+0800_go_shell_functional_adapter_fix.md`

## 3. Converter artifact 交接不可靠：symlink、scratch 泄漏、partial output 和旧状态

### 遇到的问题

模型 session 的输出曾出现以下交接问题：

- `.compat/verifier` 是 symlink，直接 `copytree` 导致 `FileExistsError` 或递归展开；
- scratch `app`、`node_modules`、临时依赖和实验文件被带进 verifier；
- 模型用绝对路径、扫描 vendor/build tree 或联网安装依赖，消耗预算却没有可审计提交；
- 只提交 `run.sh`，没有真实功能源文件和 manifest；
- step limit 或中断后已有 partial artifact 丢失；
- stale repair packet 或旧 positive evidence 污染新 revision；
- Judge 返回 fenced/prose/multiple JSON 时解析失败并造成无意义等待。

### 处理方式

框架现在把提交变成显式 contract：

- Converter 只在 staging 工作，必须发出 submission sentinel；
- `copy_tree` 保留 symlink 语义，revision snapshot 保存真实 artifact tree 和 hash；
- snapshot 过滤 scratch、依赖、缓存和未声明文件；
- `validate_verifier` 强制要求 `manifest.json`、可执行 `run.sh`、真实功能源、coverage、
  trace、instruction 和 self-review；
- partial BUILD 可被恢复为下一次单一 Converter REPAIR，保留已有诊断；
- revision、evidence、controller lock 和 contract version 绑定，resume 只复用同一 immutable
  evidence；
- Judge 使用结构化 JSON extraction，无法得到无歧义 verdict 才归为 bounded infrastructure
  retry。

### 当前状态

模型生成仍然可能失败，但失败不会再悄悄变成“成功 artifact”或重复 BUILD。对应记录包括：

- `20260922T051500Z_framework_recovery_repair_routing.md`
- `20260922T052200Z_framework_symlink_snapshot_guard.md`
- `20260922T060500Z_framework_converter_snapshot_filter.md`
- `20260922T213438Z_framework_converter_partial_repair_routing.md`
- `20260924T001000Z_framework_judge_json_extraction.md`

## 4. Selector、coverage 和 package accounting 不一致

### 遇到的问题

历史数据里的 selector 有 raw source、container path、resolved repository path 等多种形式。
早期 Converter 把 raw id 写入 manifest，而 validator 按 canonical resolved id 检查，导致
合法 artifact 在 semantic judge 前就失败。另一个问题是 package 曾经整体携带历史 test patch，
把 F2P-only hunk 混入最终任务；空 P2P 还曾用伪造节点表示。

### 处理方式

- Prepare 只生成一份 canonical `resolved_test_selectors.json`；raw selector 只保留为 provenance；
- manifest 和 `conversion_trace.json` 必须逐条覆盖 resolved F2P/P2P id；
- Semantic Judge 同时看到 source 和 resolved context，但 deterministic accounting 是权威；
- package 只保留 P2P 所需测试文件、fixture、setup 和 support hunk；F2P-only 内容被记录为
  excluded；
- 空 P2P 显式记录为 `source_empty_noop`，不伪造测试节点；
- grader 支持 ordered patch paths、CTRF/JUnit、missing node failure、worst status、partial
  reward 和 `apply_failed`，同时保留旧的 exit-code 接口。

### 当前状态

selector 与 patch accounting 已成为框架 contract。仍需在批量报告中单独统计“source accounting
完整”和“独立行为覆盖充分”，因为 suite-level F2P 可能被合理 drop，但不代表功能覆盖充分。
对应记录包括：

- `20260922T051200Z_framework_selector_accounting_contract.md`
- `20260922T110000Z_framework_package_patch_accounting.md`
- `20260928T013125+0800_framework_functional_contract_and_batch_guard.md`

## 5. Verifier 语义并不天然面向功能：private binding、mock/shim coupling 和 false negative

### 遇到的问题

去掉显式 private helper 断言并不够，verifier 仍可能通过以下方式绑定 Gold：

- instruction 写出内部 package、具体 type/constructor/method、文件布局或 AST/name 规则；
- AST surface guard 只允许某些名字/后缀，合法重命名或重构被拒绝；
- synthetic DOM、XML、transpiler 或 runtime shim 只实现 Gold 使用的访问路径；
- public alternative 使用标准 API（例如 `documentElement`、`nodeName`）时，在真正断言前就因
  mock 缺属性而失败；
- Positive QA 早期先要求 current F2P 通过，导致 verifier 自己造成的 false negative 被当成坏 candidate；
- Navidrome rev4 把 constructor 和 concrete type 放在同一个编译单元，缺一个符号时掩盖另一个
  符号仍存在的问题。

### 处理方式

- Converter/Judge prompt 明确以 public API、observable output/state/error 为中心；private、Gold
  layout、mock call shape、AST/name 绑定禁止进入 solver instruction；可见性要求只有在 F2P
  evidence 支持时保留；
- 增加 deterministic instruction scope audit：绝对路径、历史 selector、Gold-specific layout、
  mock shape、AST scan 等硬拒绝；visibility 词汇只作 advisory；
- 新增 `Mock/Fixture-Induced Implementation Coupling` 和 runtime-shim coupling 分类，要求
  harness 实现中立的 public runtime contract；
- Positive QA 分成 `candidate_positive → validated_positive → accepted positive`：current
  F2P 的可运行失败先交 Solution Judge，不能提前丢弃；合法但被 verifier 拒绝才触发
  `VERIFIER_FALSE_NEGATIVE` 和单一 Converter REPAIR；
- Navidrome rev5 将 constructor/type 探针拆开，分别验证两个边界，避免错误合并。

### 当前状态

这类问题仍是最需要人工理解任务语义的部分。qutebrowser、OpenLibrary、NodeBB、Element
和 Navidrome 已完成 Core Gate/QA/smoke，但 Tutanota 的 DOM/runtime shim 记录说明：Gold
通过和 instruction `PASS` 仍不足以证明 alternative implementation 全部包容。关键记录包括：

- `20260923T055000Z_tutanota_verifier_dom_mock_false_negative.md`
- `20260923T061500Z_framework_mock_fixture_coupling_taxonomy.md`
- `20260923T062429Z_framework_positive_validation_layers.md`
- `20260928T114544+0800_go_shell_functional_adapter_fix.md`

## 6. QA、状态机和模型服务问题

### 遇到的问题

- candidate 的 runner 缺失、uid、依赖下载、Docker 权限和 timeout 曾被当成 verifier semantic failure；
- old positive/negative evidence 在 resume 时可能继续计入目标；
- controller 并发写同一 attempt 或中断后 repair 意图不明确；
- Semantic Judge、Converter、QA model endpoint 可能超时、返回 malformed JSON 或 HTTP 402
  `Insufficient Balance`；
- 早期所有失败都显示为 `MANUAL_REVIEW`，掩盖了真正的 infrastructure/package 原因。

### 处理方式

- candidate replay 使用统一 container contract，不保留 solver uid，并将 Docker/toolchain/timeout/
  missing marker 与 verifier return code 分开分类；
- evidence 带 contract version，旧 evidence 不直接满足新的 QA target；
- 增加 controller/converter lock、`INTERRUPTED` 事件、resume recovery 和显式 repair packet；
- 模型 endpoint 的 400/401/402/403/404、认证/权限/余额错误标为不可重试
  `MODEL_ENDPOINT` infrastructure，不消耗 revision；429/5xx 才做有限 retry；
- controller 终态明确为 `VERIFIED`、`INFRASTRUCTURE`、`PACKAGE` 或 `FAILED`，保留的
  `MANUAL_REVIEW` 只是兼容枚举，不进入自动流程；
- batch 只调度已 Prepare 的 workspace，使用有界 worker 和 `batch_summary.json`，不绕过单实例 gate。

### 当前状态

模型额度仍是外部依赖，但它不再被错误解释为 verifier 失败，也不会反复消耗 repair budget。对应
记录包括：

- `20260922T075200Z_framework_semantic_judge_timeout.md`
- `20260922T082000Z_framework_model_endpoint_diagnosis.md`
- `20260923T015319Z_framework_controller_lease_positive_contract.md`
- `20260924T024800Z_semantic_judge_timeout_stability.md`
- `20260928T013125+0800_framework_functional_contract_and_batch_guard.md`

## 7. 最终收敛结果

已形成的通用框架能力：

- instance-centric source/intermediate/review/final_task 布局；
- public/restricted/sealed 信息边界；
- repository-native `ExecutionSpec` 和多语言 execution adapter；
- revision snapshot、artifact hash、submission sentinel、lock 和 resume；
- manifest/coverage/path/instruction 的确定性校验；
- Base/Gold F2P/P2P Core Gate 和重复稳定性；
- alternative positive 与 semantic negative QA；
- DeepSWE package、grader、package smoke 和原子发布；
- 明确的 infrastructure、semantic、QA、package 终态。

当前代表性结果：

- qutebrowser fresh attempt：`VERIFIED/PACKAGED`；
- Navidrome fresh attempt_008 rev5：`VERIFIED/PACKAGED`，1 个 positive、2 个 negative，
  package smoke PASS；
- VerifierTrans 全量回归测试：`150 passed`。

## 8. 仍需继续关注的风险

1. **模型非确定性和额度**：step cap、request timeout、有限 retry 只能控制成本，不能保证
   每次生成相同 verifier；余额不足必须保持 infrastructure 终态。
2. **F2P 证据不足**：没有 seed 支持的行为只能是 `spec_gap`，不能从 Problem Statement
   猜测新增测试。
3. **空 P2P 与 F2P suite drop 是两件不同的事**：P2P 为空时，首先要确认源数据本来就没有
   P2P；这种情况只能记录为 `source_empty_noop`，不能声称有回归覆盖。已有 P2P 必须保留，
   并通过 selector accounting、`p2p_policy=retained` 和最终 `p2p_node_ids` 对账。F2P 的
   旧测试文件或 suite-level hunk 被排除，表示它已由 functional verifier 替换，不能据此推断
   P2P 被删除。报告应分别记录：源 P2P 数量、最终保留数量、F2P 映射/functional coverage，
   以及真正无法映射的 F2P `drop/spec_gap`。
4. **synthetic harness 风险**：DOM/TS/Node 等 runtime shim 仍需覆盖标准 public API，
   否则可能产生 false negative。
5. **有限 runner/service 覆盖**：未知 runner、复杂多服务和需要网络的仓库应明确失败，不能
   通过 Converter 猜命令。
6. **批量成功率尚未充分统计**：现有成功案例证明 pipeline 闭环，不代表 SWE-bench Pro 全量
   任务的生产级成功率；需要继续做跨语言、跨 runner、跨 service 的 fresh matrix。

## 9. 核心经验

每次看到失败，先回答三个问题再决定是否改 verifier：

1. **输入是否可信？** Base checkout、selector、镜像和 source gate 是否通过；
2. **框架是否正确执行？** mount、cwd、runner、service、timeout、marker 是否与 frozen
   ExecutionSpec 一致；
3. **verifier 是否真的检查公共行为？** instruction、harness、probe 和 QA 是否允许结构不同
   的合法实现。

只有第三个问题确认无误后，才把失败交给 Converter semantic REPAIR。这样可以避免把 Docker、
路径、模型额度或旧状态问题硬编码进某个任务的 verifier，也保持框架的通用性。
