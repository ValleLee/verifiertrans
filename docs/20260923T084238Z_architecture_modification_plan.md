# VerifierTrans 结构修改方案（2026-09-23）

## 0. 文档定位

本文是基于当前源码的结构修改方案，不是对 `architecture.md`、`0923re_op.md` 或
`process/framework_issue_summary.md` 的逐字改写。那些文档提供了问题线索；本方案以
当前代码、现有测试和 `process/` 中的修复记录为事实来源，回答两个问题：

1. 接下来要修改哪些结构，按什么顺序修改，如何避免把 instance workaround 变成公共框架；
2. 修改完成后，VerifierTrans 应该具备什么样的边界、数据流和验收条件。

目标是保留已经验证过的主骨架：

```text
Prepare / Preflight
        ↓
单一 Converter（BUILD / REPAIR）
        ↓
Sanity → Semantic Judge → Hard Validator
        ↓
Positive / Negative QA
        ↓
累计证据 replay
        ↓
Package → clean smoke → atomic publish
```

本方案不新增一个“设计 Agent”、不把 Gold 变成规范、不以当前某个仓库的文件名或
测试名写特判，也不把一次 fresh Docker 尚未完成的验证描述成已经支持的语言能力。

### 0.1 核心问题覆盖核对

补充审计将长期问题归纳为四类。本方案已全部覆盖，且将其与实现工作流明确对应：

| 核心问题 | 本方案对应章节 | 需要达到的结果 |
| --- | --- | --- |
| Execution Contract 尚未唯一化 | A、Phase 1 | Prepare 冻结唯一 `ExecutionSpec`；preflight、replay、QA、package smoke 只消费它 |
| Verifier Artifact 边界隐式 | B、Phase 2 | manifest/output 成为 artifact 唯一来源；取消 `functional_*`、目录扫描和 blacklist 的正式语义 |
| Verifier Semantic Independence 不充分 | E、Phase 4 | verifier 测 public/observable behavior；其自有 fixture/mock/runtime 不得缩小合理实现空间 |
| Package 仍推理历史 patch | F、Phase 5 | Prepare 产出 P2P asset bundle；Package 机械消费，ambiguity 显式暴露，clean environment 独立复现 |

本计划中的 C（Source/Provenance）和 D（Evidence State Machine）是四类问题的横向保障，
不是另立的第五、第六类业务问题：没有它们，执行契约的来源、artifact 的身份、semantic
repair 的 revision 边界和 package 的可追溯性都无法被证明。Positive/Negative QA 也不是
独立的“问题类别”，而是验证 Semantic Independence 和 Package/Execution 结果是否真实
成立的证据机制。

四类问题可以用一句话区分：

```text
Execution 解决“怎么跑”
Artifact   解决“跑什么”
Semantic   解决“测的是不是正确的功能”
Package    解决“最终结果能否脱离构造现场复现”
```

---

## 1. 现状审计：已经有的能力与真正的结构缺口

### 1.1 已经形成的基础能力

当前代码已经有几项应当保留的公共能力：

- `RunLayout` / `AttemptLayout` 将 instance 分为 `source`、`intermediate`、`review` 和
  `final_task`，并以 `.compat` 兼容旧路径；
- `discover_execution_spec()` 已能从 Python、Node/TypeScript、Go 的 repository-native
  metadata 发现基础 runner、cwd/module root、selector style 和 loader；
- replay、candidate replay、package 已经通过 execution adapter 生成命令的主路径；
- Prepare 会冻结 resolved selectors，并把 source selector 与 canonical selector 区分开；
- verifier sanity 对 F2P accounting、conversion trace、路径和最小功能源文件有确定性检查；
- Positive QA 已区分候选筛选、Solution Judge 和当前 verifier replay，能够表达
  `VALID candidate + current F2P FAIL` 的 false negative；
- Negative QA 从 valid Positive 派生，并要求 P2P 仍通过、只破坏已映射语义；
- attempt/controller/converter lock、revision hash、contract version、repair packet 和
  atomic final publication 已经存在；
- 当前测试集 70 项通过，说明上述局部契约有回归保护。

这些是收敛工作的起点，不应因为存在旁路就全部推倒重写。

### 1.2 从实际代码确认的结构性缺口

以下问题不是“还缺一个 instance 的适配”，而是同一事实在多个地方被重新解释：

| 类别 | 当前代码证据 | 后果 |
| --- | --- | --- |
| 执行契约碎片化 | `ExecutionSpec` 只有扁平 service 名称；Prepare 在 `prepare_instance.py` 自建预检 shell；replay/candidate/package 各自组装 Docker mounts；`verifier.py` 和 `package_task.py` 直接调用 `redis_bootstrap_script()` | Prepare 能跑不代表 candidate、package 或 clean replay 用的是同一执行语义 |
| artifact 身份不够严格 | `execution/base.py::_functional_file()` 按 `functional_*` 找入口；`validate_verifier.py` 扫描顶层源文件；`package_task.py::verifier_files()` 在缺 `test_files` 时再次扫描，并特别查找 `functional_f2p.*` | 文件名、扫描 fallback 和 manifest 同时成为隐式协议，临时文件可能流入正式包 |
| 路径/来源双轨 | canonical `source/intermediate` 与 `.compat/run`、`/app`、`/workspace`、`/verifier`、`/framework` 并存；兼容路径仍被若干脚本直接消费 | source evidence、构造中间产物、最终 artifact 的身份可能在交接时改变 |
| 控制流不是可验证状态机 | `append_event()` 可写任意字符串，未统一校验 `PipelineState` 转移；`FailureClass` 在 `state.py`、`artifact_contract.py`、replay 脚本中不完全一致（例如 PACKAGE 未纳入 artifact contract） | 中断、重试、repair、旧 evidence 重用的边界依赖 controller 分支，难以证明不会跳过 gate |
| 语义有效性风险 | Tutanota 审计已观察到 mock DOM、runtime/transpiler shim 使合理实现到达 assertion 前失败；Semantic Judge 目前主要看 verifier 文件和摘要 | verifier 可能测到 Gold-shaped fixture，而不是 public/observable behavior |
| package 仍有二次解释 | `retain_p2p_test_patch()` 需要 patch/hunk heuristic；`package_smoke.py` 直接以 source image 启动，而不是构建 package 的 environment/Dockerfile | package 阶段可能重新猜历史测试依赖，且 clean environment 边界没有被证明 |
| 能力声明超前于证据 | 代码和静态测试覆盖 Node/TS/Go，但 fresh Docker cross-validation 尚未形成完整闭环 | “有 adapter”被误读成“该生态已获得 E2E 支持” |

### 1.3 当前基线证据

在本方案形成时执行：

```text
.venv/bin/python -m unittest discover -s tests -v
Ran 70 tests ... OK
```

这证明当前回归测试基线可运行；它不证明四种语言、service lifecycle、package image 构建
或 Tutanota 语义 repair 已经端到端通过。后者必须作为后续阶段的独立证据。

---

## 2. 目标架构：六个边界、一个事实源

### 2.1 总体数据流：无损证据平面与执行契约平面分离

```text
Dataset row + repository image
            │
            ▼
  ┌─────────────────────────────────────────────────────────┐
  │ [1] Source Evidence Plane（immutable, lossless）        │
  │ raw row / original patch / raw selectors / test seeds    │
  │ public contract / repository / sealed construction data │
  └───────────────┬─────────────────────────────────────────┘
                  │ raw + derived views, on-demand for Converter
                  ├───────────────────────┐
                  ▼                       ▼
  [2] Converter Revision       [3] Execution Contract Plane
  what to test                 frozen ExecutionSpec
                               runner + cwd + module root + selectors
                               mounts + services + timeout + result parser
                                          │
                                          ▼
                              [4] Deterministic Executor
                              how to run preflight/replay/QA/package
             same ExecutionSpec for preflight/replay/candidate/package
             └──────────────┬────────────────┘
                            │ revision artifact + execution evidence
                            ▼
  [5] Evidence State Machine
  sanity → semantic → hard → QA → accumulated replay
                   │
                   ▼
  [6] Package Contract
  accepted manifest + retained P2P bundle + built environment → smoke → final_task
```

六个边界的职责必须单向流动，但 Source Evidence Plane 与 Execution Contract Plane 必须
保持并列，不能把后者当成前者的压缩替代品：

- Source Evidence Contract 只保存事实和 provenance，不被模型或执行阶段回写；它是
  **无损超集**，不是只保留执行所需字段的摘要；
- Execution Contract 只由 Prepare 从 source evidence 派生并冻结，后续执行阶段只消费，
  但它不能删除、覆盖或替代 raw evidence；
- Converter 可以按需读取完整的原始任务资料、仓库和允许的 construction evidence，再使用
  resolved/normalized view 提高效率；“按需”表示延迟读取，不表示只能看到摘要；
- Converter 只决定“测什么”和 artifact 内容，不决定 Docker、selector runner、service；
- Deterministic Executor 只决定“怎么运行”，不修改 verifier 语义；
- Evidence State Machine 只按结构化结果转移，不读取日志文本猜状态；
- Package Contract 只消费已接受 artifact 和 Prepare 的 P2P 依赖结果，不重新发现 verifier。

### 2.2 Source Evidence 不丢失原则

`ExecutionSpec` 是运行视图，不是信息边界。Prepare 必须同时保留两层数据：

```text
Source Evidence（不可变原始层）
├── dataset_row.json              # 原始 row，保留未使用字段
├── original_test.patch           # 原始 patch，不被切片覆盖
├── test_seeds.json               # raw F2P/P2P seed
├── raw selectors / metadata      # 原始 selector、命令、环境字段
├── public/                       # 对应可见契约
├── restricted/original_tests/    # historical tests 原貌
└── sealed/                       # Converter 可用 construction evidence

Derived Views（可重建派生层）
├── resolved_test_selectors.json
├── p2p_assets.json
├── execution_spec.json
└── selector/source mapping
```

必须遵守以下规则：

1. `resolved_test_selectors.json`、`p2p_assets.json` 和 `ExecutionSpec` 都带
   `source_manifest_hash`，并保存 source-id → resolved-id 的一一对应关系；规范化发现
   冲突时记录 conflict，不覆盖 raw 值。
2. Converter 的可见范围由 role policy 控制，但在其允许范围内可以读取原始文件和派生
   视图：包括完整 repository、Problem Statement、public contract、raw/resolved
   selectors、original tests/patch，以及 sealed construction evidence。Converter 应渐进
   探索，而不是被框架预先裁剪成只剩摘要。
3. Solver/Positive/Negative role 仍只能看到各自的 public scope；“Converter 可读取原始
   证据”不等于向候选泄露 Gold 或 restricted construction data。
4. revision/manifest/trace 不复制一份可能漂移的原始材料，而是通过 source id、path 和
   hash 引用它；审计需要时可以从 source 重建当时的输入。
5. 任何为了执行方便的 flatten、extension alias、selector normalization 或 patch
   accounting 都属于 derived view；都不能替换 source evidence，也不能改变 Converter
   对原始意图的 accounting。

因此最终原则是：

> Execution Contract 冻结“怎么跑”；Source Evidence Contract 保证“原始事实没有丢”，
> Converter 在权限范围内仍可按需读取全部原始数据。

### 2.3 目标目录与 artifact 身份

```text
runs/<instance_id>/
├── source/                         # immutable；只由 Prepare 写入
│   ├── dataset_row.json
│   ├── source_manifest.json        # schema + sha256 + producer + visibility
│   ├── public/                     # solver/QA 可见的契约
│   ├── restricted/                 # selectors、原始测试及 P2P dependency bundle
│   ├── sealed/                     # 仅 Converter 可见的 construction evidence
│   └── reference/                  # taxonomy/guidance
├── intermediate/attempts/attempt_NNN/
│   ├── prepare/                    # repo、ExecutionSpec、preflight、logs
│   ├── converter/
│   │   ├── staging/<revision>/     # session 临时写入
│   │   ├── revisions/rev_NNN/     # 不可变快照
│   │   └── current/               # 只指向已选 revision
│   ├── validation/                # sanity/semantic/hard/evidence replay
│   ├── qa/                        # candidate、positive、negative、evidence
│   ├── packaging/                 # candidate package、report、smoke
│   ├── control/                   # state/events/leases/final/report
│   └── .compat/                   # 仅旧接口视图，不能成为新逻辑的数据源
├── final_task/                    # 仅 atomic publish 产生
└── review/                        # 人类汇总，不作为执行输入
```

artifact 的生命周期固定为：

```text
raw source → normalized source → revision staging → immutable revision
           → accepted verifier → package candidate → smoke-tested final_task
```

每次交接都必须携带 `schema_version`、`producer`、`revision`、`source_hash`/
`verifier_hash`、`contract_version` 和 `visibility`。`.compat` 可以保留，但新的模块不得
通过扫描 `.compat` 反推 canonical artifact。

---

## 3. 具体修改项目与落地方式

### A. 收敛 Execution Contract（最高优先级）

#### 要做什么

1. 将 `ExecutionSpec` 从“发现结果”升级为冻结的、可序列化的执行契约，至少包括：
   `language`、`runner_family`、`package_manager`、`cwd`、`module_root`、
   `selector_strategy`、`typescript_loader`、`environment`、`services`、
   `timeouts`、`container_paths`、`result_parser` 和 `support_status`。
2. 将 service 从 `("redis",)` 这类字符串改成结构化 descriptor：
   `name/type`、启动方式、readiness probe、启动/停止超时、是否由 image 提供、失败分类。
   Redis 只是第一个 descriptor，不为 NodeBB 写特例。
3. Prepare 只生成一次 `execution_spec.json` 和摘要 hash；replay、candidate replay、
   package smoke、environment preflight 均读取同一文件并校验 hash。
4. 抽出统一执行入口（概念上为 `Executor.run(spec, state, target)`），统一：
   Docker mount 顺序、`/app` repo、`/verifier` artifact、`/framework` runner、`/logs`、
   cwd、service bootstrap、timeout/kill-after、marker/result parser。
5. Prepare 的 Node/Python/Go 预检不再自行拼另一套 runner 语义；预检只是 Executor 的
   `mode=preflight`。
6. 对 unsupported runner 明确返回 `UNSUPPORTED_EXECUTION`，禁止静默回退到会伪装成原生
   支持的 `run.sh`。

#### 涉及模块

`deterministic/execution/discovery.py`、`execution/base.py`、各语言 adapter、
`execution/services.py`、`preparation/prepare_instance.py`、`replay/verifier.py`、
`replay/candidate.py`、`packaging/package_smoke.py`、`packaging/package_task.py`。

#### 完成后的不变量

- 同一 attempt 的所有执行结果都能指向同一个 `execution_spec_hash`；
- replay、candidate、package 不再有自己的 cwd/mount/service/timeout 分支；
- runner 缺失、service readiness、selector 未执行、timeout 都归为 deterministic
  infrastructure subtype，不进入 Converter semantic repair；
- 语言支持声明只由 fresh Docker acceptance matrix 晋级，不由静态代码存在决定。

---

### B. 从“扫描发现”迁移到 Manifest 驱动 artifact

#### 要做什么

1. 定义唯一 verifier manifest（建议升级到新的 schema major version），明确声明：
   `entrypoints`、`test_files`、`fixtures`、`runtime_files`、`f2p_command`、
   `p2p_contract_ref`、`source_coverage`、`artifact_hash` 和允许的 runner family。
2. Converter workspace 分成 `scratch/` 与 `output/`：模型可在 scratch 探索，只有 output
   中由 manifest 声明的文件进入 revision。由 output allowlist 取代越来越长的 blacklist；
   现有 scratch pruning 保留作为防御层，不再是正式边界。
3. `execution_plan()` 只读取 manifest 的 entrypoint，不再调用 `_functional_file()`；
   `validate_verifier.py` 只验证 manifest 声明的 source/runtime 文件；
   `package_task.py::verifier_files()` 不再在缺声明时扫描目录。
4. `run.sh` 降级为可选兼容 wrapper：不得承担 artifact discovery、P2P selector parser、
   Docker 或安装依赖；最终 package 直接按 manifest 复制文件。
5. 将当前 `functional_*`、`functional_f2p.*` 规则标记为 legacy migration only，并提供
   一次性 deterministic migration；新 revision 不接受依赖文件名前缀的 manifest。
6. manifest、conversion trace、instruction scope、self-review 统一引用 revision hash，
   防止“检查的是 A、打包的是 B”。

#### 涉及模块

`validation/validate_verifier.py`、`validation/artifact_contract.py`、
`validation/path_contract.py`、`execution/base.py`、`agents/miniswe_session.py`、
`pipeline/orchestrator.py`、`packaging/package_task.py`。

#### 完成后的不变量

- 没有 manifest 就不能进入 Semantic Judge、Hard Validator 或 Package；
- verifier 中未声明的文件不会进入 revision/package；
- package 不会再次扫描 `functional_*` 或顶层语言文件猜入口；
- scratch、依赖、缓存、symlink target 和 audit-only 文件不会因 copytree 意外进入正式包。

---

### C. 固化 Source / Path / Provenance 边界

#### 要做什么

1. 为 source 建立 immutable `source_manifest.json`：记录 dataset row hash、base commit、
   test patch hash、selector source/resolved hash、sealed evidence hash、materialization
   结果和 producer；同时保留 raw dataset row 的完整字段清单和 hash，禁止用“已抽取字段”
   覆盖原始 row。
2. 将 source path、host path、container path、logical selector path 统一表示为带类型的
   `ArtifactRef`/`ContainerRef`，禁止在业务代码中散落字符串替换 `/app`、`/workspace`。
3. 统一 canonical container layout：

   ```text
   /app        materialized repository
   /verifier   accepted/replay verifier (read-only)
   /framework  framework-owned runner (read-only)
   /restricted frozen selectors (read-only)
   /sealed     Gold construction evidence (only where permitted)
   /logs       execution logs/results
   ```

   `/workspace` 只属于 mini-SWE role workspace，不作为 replay 语义路径。
4. source 创建完成后设为只读/拒绝非 Prepare 写入；所有 derived artifact 进入 attempt。
   `.compat` 继续兼容旧 runs，但在新代码中只由 resolver 生成和读取。
5. Prepare 的 materialization gate 必须以 Docker return code、HEAD、link target、source
   manifest 一起判定，避免 stale directory 冒充成功。
6. 任何规范化步骤都只写入 derived view；如果无法解析 selector、patch hunk、interface
   字段或依赖关系，保留原始值并写入 `unresolved/conflicts`，不能为了让后续阶段顺利而
   丢弃该信息。Converter 仍可读取 raw 值并自行完成语义判断。

#### 完成后的不变量

- 任何 revision 都可以追溯到唯一 source hash 和 attempt；
- `final_task` 不包含 repo staging、模型 trajectory、sealed evidence 或 `.compat`；
- 旧 runs 仍可读取，但不会被静默升级为新 contract；
- 任何绝对 host path、越界相对路径、未声明 symlink 都在 artifact sanity 失败。

---

### D. 把 Controller 变成受约束的 Evidence State Machine

#### 要做什么

1. 建立显式 transition table，而不是仅在 `orchestrator.py` 的长分支中隐式决定下一步：

   ```text
   NEW → PREPARED → CONVERTING → SANITY_PASS
       → SEMANTIC_PASS → HARD_PASS → QA
       → EVIDENCE_REPLAY_PASS → PACKAGE → SMOKE_PASS → PUBLISHED
   ```

   失败只允许进入：`RETRY_INFRA`、`REPAIR_CONVERTER`、`REGENERATE_CANDIDATE`、
   `MANUAL_REVIEW` 或 `INTERRUPTED`，不能用任意字符串跳跃。
2. 将每个 stage result 定义成统一 envelope：`stage`、`status`、`failure_class`、
   `failure_subtype`、`attempt`、`revision`、`input_hashes`、`output_paths`、`retryable`。
3. 统一 failure taxonomy：

   ```text
   ARTIFACT_SCHEMA
   INFRASTRUCTURE_EXECUTION
   SELECTOR_OR_PATH
   VERIFIER_SEMANTIC
   CANDIDATE_SEMANTIC
   PACKAGE
   INTERRUPTED
   ```

   保持大类稳定，用 subtype 描述 timeout、runner missing、false negative、mock coupling
   等。所有 producer 共用 enum；修正 `artifact_contract.py` 与 `state.py` 的不一致。
4. 每个 evidence 必须声明适用的 `contract_version`、`execution_spec_hash`、
   `verifier_hash` 和生成阶段；旧 evidence 只能审计，不能直接满足新 gate。
5. lock 之外增加 attempt lease/fencing token：controller 读取 state、提交 artifact、
   发布 final_task 时检查 lease，防止旧进程在恢复后覆盖新状态。
6. resume 只从最近一个满足 hash/contract 的 checkpoint 恢复；不能通过“看见文件存在”
   直接跳过 Semantic Judge 或 Hard Validator。

#### 完成后的不变量

- `events.jsonl` 是追加事实，`state.json` 是可重建的快照，二者不会各自产生事实；
- 每个状态都有合法前驱和可审计证据；
- infrastructure retry 不增加 verifier revision，semantic repair 必须增加 revision；
- interruption、endpoint timeout、Docker timeout 不会被写成 verifier semantic failure；
- Controller 不理解 pytest/Redis/DOM，只消费 stage envelope。

---

### E. 重新定义 Verifier Semantic Contract：测公共行为，不测 Gold 环境

#### 要做什么

1. 保留历史 F2P 作为 scope/provenance/accounting，不把 Gold patch、private helper 或
   historical test 的调用形状直接升格为 specification。
2. 在 manifest/trace 中要求每条 F2P 映射写明：observable surface、输入、输出/状态/错误
   语义、为何不绑定 implementation detail，以及 fixture/runtime contract。
3. 扩充 Semantic Judge checklist：
   - 是否直接调用 private helper、private field、Gold-only path；
   - mock/fixture 是否实现了真实 public runtime 需要的标准行为；
   - DOM、sanitizer、serialization、filesystem、TypeScript runtime shim 是否让某种
     等价实现提前崩溃；
   - assertion 前失败是否会被错误归为 candidate semantic failure；
   - 是否存在“只因 Gold shape 才能构造输入”的隐藏前提。
4. 对 mock/fixture/runtime shim 引入中立性分级：
   `REAL_RUNTIME`、`STANDARD_MINIMAL`、`TASK_SPECIFIC_ADAPTER`。后者必须有公共契约证据，
   否则 Semantic Judge 不能 PASS。
5. 明确 Execution Environment 与 Verifier-owned Test Facility 的责任边界：
   - repo/toolchain/dependency/service/runner/cwd 属于 Execution Environment，由
     `ExecutionSpec` 和 deterministic Executor 负责；例如真实项目需要 Redis 但 Redis 未
     readiness，这是 execution/infrastructure 问题；
   - fixture/fake input/mock DOM/test-local runtime/assertion 属于 Verifier，由 manifest
     和 semantic review 负责；例如真实 public DOM 支持 `querySelector`，但 verifier 自己
     的 FakeDOM 不支持，这是 verifier semantic/fixture coupling 问题；
   - 任何 assertion 前的异常都必须先按这条边界分类，不能笼统记成 candidate FAIL。
6. 将 Tutanota DOM/querySelector/runtime-shim 记录作为通用 taxonomy 和 repair input，
   不新增 Tutanota 特判，也不在证据不足时设计一个庞大的通用 DOM 框架。
7. Positive/Negative 四象限保持不变：Judge 判断候选语义有效性，deterministic replay
   判断 verifier 通过与否；只有 VALID+FAIL（false negative）或 INVALID+PASS（false
   positive）才触发 Converter REPAIR。

#### 完成后的不变量

- Base/Gold 通过只证明必要的 known-correct gate，不证明 acceptance breadth；
- 至少一个结构不同的 VALID Positive 被接受，至少两个 qualified Negative 被拒绝；
- mock/runtime 造成的失败能被定位为 `VERIFIER_SEMANTIC / fixture_coupling`，而非 Docker
  或 candidate 错误；
- 同一错误在“真实软件运行条件缺失”和“verifier 自造测试设施过窄”两种情况下会得到
  不同且可复核的 failure subtype；
- repair 后必须在最新 revision 重放全部累计 Positive/Negative evidence。

---

### F. 让 Package 成为“机械消费层”，并验证真实 clean environment

#### 要做什么

1. Prepare 阶段输出 `p2p_assets.json` 或等价 dependency bundle：resolved selectors、
   test nodes/files、shared fixtures、support files、ambiguous items 和来源 hash。
2. Package 先消费该 bundle，再对无法静态切分的 patch hunk 做 heuristic；`AMBIGUOUS`
   必须显式失败或进入人工复核，不能静默保留整份 historical patch。
3. package 输入只允许：accepted verifier manifest、instruction scope、P2P dependency
   bundle、ExecutionSpec、environment descriptor。禁止 package 再扫描 verifier 或重新
   推断 F2P/P2P。
4. `package_smoke.py` 改为先构建/加载 package 自己声明的 `environment/Dockerfile`，
   再在 clean Base checkout 应用 package `tests/test.patch` 和 Gold patch，执行：

   ```text
   Base converted F2P FAIL
   Gold converted F2P PASS
   Base P2P PASS
   Gold P2P PASS
   ```

   若暂时受基础设施限制使用 source image，结果必须标注为 `SOURCE_IMAGE_ONLY`，不能宣称
   final environment 已验收。
5. 只在 smoke PASS 后调用 `publish_final_task()`；发布 provenance 中写入 source hash、
   execution spec hash、verifier hash、package report hash、environment image/Dockerfile hash。

#### 完成后的不变量

- final `test.sh` 的 reward 只有 converted F2P + retained P2P；historical F2P 不进入 reward；
- package_report 能说明每个 test file/hunk 是 retained/shared/excluded/ambiguous；
- final_task 离开 construction workspace 后仍可从自身 environment/tests 运行；
- package 不会因为 `functional_f2p` 文件名恰好存在才可执行。

---

## 4. 分阶段实施路线

### Phase 0：契约冻结与基线（先做）

**产出**：schema、transition table、failure enum、当前测试/任务状态清单。

- 冻结当前 `ARTIFACT_SCHEMA_VERSION`、Positive contract、`EXECUTION_CONTRACT_VERSION`；
- 为 source、execution、artifact、stage envelope 写 schema fixture；
- 记录当前 70 项测试结果和已有 Python 成功任务作为 regression baseline；
- 不修改 verifier 语义，不迁移旧 runs，不调用外部模型。

**通过条件**：新旧 evidence 不会被静默混用；每项后续改动都有 schema/hash 可检查。

### Phase 1：Execution Contract 单一事实源

**优先级：P0。**

- 扩展 `ExecutionSpec`、service descriptor、container path 和 timeout；
- 让 Prepare preflight、replay、candidate、package 统一调用 Executor；
- 保留 Python/Mocha/Jest/Vitest/ospec/Go adapter，但删除重复 command 拼装；
- 增加 fixture：cwd/module root、loader、runner missing、service readiness、timeout、
  result parser、不同容器路径的同构结果。

**通过条件**：同一个 spec hash 生成所有 replay/package plan；unknown runner 明确为
`UNSUPPORTED_EXECUTION`；无一处以 Redis/runner 名称为 instance 分支。

### Phase 2：Manifest/output artifact boundary

**优先级：P0。**

- 新 manifest schema 与 deterministic migration；
- converter `scratch/output` 隔离；
- execution、sanity、package 全部 manifest-only；
- 旧 `functional_*` 仅在 legacy reader 中保留，并记录 migration warning。

**通过条件**：构造临时依赖、顶层未声明源文件、只提交 run.sh、恶意 symlink、路径越界
均不能进入 accepted revision；package 不扫描猜入口。

### Phase 3：Source/provenance 与状态机收敛

**优先级：P0。**

- source manifest/hash 和 typed path refs；
- stage envelope、合法转移、统一 failure taxonomy；
- lease/fencing 和 resume checkpoint；
- 将现有 `append_event()` 改为 transition-checked writer，保留 JSONL 追加和 state snapshot。

**通过条件**：注入中断、重复 controller、旧 repair packet、旧 contract evidence、迟到
converter session 的测试都不会覆盖当前 revision 或跳过 gate。

### Phase 4：Semantic validity 与 QA 闭环

**优先级：P1。**

- 更新 converter/semantic/positive/negative prompts 和 trace schema；
- 增加 fixture/runtime coupling 审计字段与 Judge checklist；
- fresh 复现 Tutanota 类问题，验证其走 Converter REPAIR 而非 infra retry；
- 在新 revision 上 replay 所有累计 QA evidence。

**通过条件**：一个结构不同的 valid Positive 通过；两个只违反单一语义的 Negative 被拒；
false negative/false positive 路由、累计 replay 和 contract migration 都有可读 evidence。

### Phase 5：Package clean environment 与跨语言 acceptance

**优先级：P1。**

- `p2p_assets` 从 Prepare 进入 package；
- package smoke 构建自身 environment；
- 按 Python → JavaScript → TypeScript → Go 使用 fresh Prepare 验证，不复用旧 attempt；
- 每个生态记录 ExecutionSpec、完整 gate、package image、剩余风险。

**通过条件**：只有完成 fresh matrix 的生态才在 README/architecture 中标记为支持；失败必须
附带 framework issue 记录和 scope（framework / instance / uncertain）。

### Phase 6：清理兼容层与发布规则

**优先级：P2，必须在前五阶段稳定后做。**

- 统计 `.compat`、legacy manifest、`functional_*` fallback 的调用者；
- 在有迁移和回归证据后逐步删除新逻辑中的 fallback；
- 旧 runs 保持只读 resolver，不做破坏性物理迁移；
- 更新 architecture 文档，只描述已证明的能力和明确的未闭环项。

---

## 5. 代码改造责任矩阵

| 责任 | 主要文件 | 目标结果 |
| --- | --- | --- |
| source/materialization | `paths.py`, `prepare_instance.py`, `preparation/common.py` | source manifest、typed refs、materialization gate |
| execution | `deterministic/execution/*`, `prepare_instance.py` | frozen ExecutionSpec + single Executor |
| replay | `replay/verifier.py`, `replay/candidate.py` | 只消费 spec，统一 result/failure envelope |
| artifact | `validation/artifact_contract.py`, `validate_verifier.py`, `path_contract.py`, `miniswe_session.py` | manifest/output allowlist、revision hash |
| control | `pipeline/state.py`, `orchestrator.py`, `artifacts.py` | transition table、lease、resume、统一 failure |
| semantic QA | `pipeline/qa.py`, `prompts/*`, `orchestrator.py` | four-quadrant verdict、fixture coupling、累计 replay |
| package | `packaging/package_task.py`, `test_patch.py`, `package_smoke.py` | dependency bundle + built environment smoke |
| reporting | `deterministic/reporting/report.py`、`process/` | 阶段、证据、scope、支持矩阵可审计 |

修改共享框架时，每一项都必须在 `process/` 写 UTC 记录，包含：现象、证据、根因、为何
framework-level、影响范围、修改文件、验证方式、regression 和残余风险。

---

## 6. 验证矩阵与验收门槛

### 6.1 每个 revision 的 gate

```text
source/preflight PASS
→ artifact sanity PASS
→ Semantic Judge PASS
→ Base F2P FAIL / Gold F2P PASS
→ Base P2P PASS / Gold P2P PASS
→ stability PASS
→ accumulated evidence replay PASS
```

Semantic Judge 或 deterministic gate 未通过，不能以 package smoke 或 QA 结果补偿。

### 6.2 任务级最终验收

```text
至少 1 个 VALID Positive：current F2P PASS + retained P2P PASS + Judge VALID
至少 2 个 qualified Negative：P2P PASS + Judge RELEVANT_NON_EQUIVALENT + F2P FAIL
最新 revision 重放全部累计 QA evidence
package report 无未处理 ambiguity
package environment clean smoke PASS
final_task atomic publish PASS
```

historical F2P 必须逐条有 keep/rewrite/merge/drop/spec_gap accounting 并被 replay/记录，
但其 PASS/FAIL 不单独决定 Positive validity，也不进入 final reward。

### 6.3 Fresh cross-language acceptance matrix

每个生态至少记录以下字段：

```text
instance / language / runner_family / package_manager
cwd / module_root / selector_style / loader / services
execution_spec_hash
Prepare / sanity / semantic / hard / QA / package / smoke / publish
failure_class + subtype + process record
```

未完成 fresh matrix 的生态状态只能写 `implemented, unverified`，不能写 `supported`。

---

## 7. 不做什么：防止架构重新特化

- 不为具体 `instance_id`、repo、commit、测试标题、路径或 artifact 名称写分支；
- 不因一个 Node 项目增加 Redis 特判、因一个 DOM 项目增加任务专用 helper；
- 不让 Converter 负责安装依赖、启动 service、解析 P2P selector 或决定 mount；
- 不用扩大 Problem Statement 来弥补 historical F2P 没有覆盖的行为；
- 不把一次 Gold replay PASS 当作 verifier semantic correctness 的充分证据；
- 不在 Docker/endpoint/runner 失败时生成新的 verifier revision；
- 不在 package 阶段重新扫描/猜测 verifier；
- 不为了通过验收删除 Negative QA、放宽 artifact schema 或跳过累计 evidence replay。

---

## 8. 预期最终系统架构

```text
┌────────────────────────────────────────────────────────────┐
│ Source Boundary (immutable)                                │
│ row / public / restricted / sealed / source manifest       │
└──────────────────────────┬─────────────────────────────────┘
                           │ Prepare only
                           ▼
┌────────────────────────────────────────────────────────────┐
│ Frozen Execution Contract                                  │
│ ExecutionSpec + selector bundle + path refs + service plan  │
└───────────────┬───────────────────────┬────────────────────┘
                │                       │
                │ what to test         │ how to run
                ▼                       ▼
┌─────────────────────────┐   ┌─────────────────────────────┐
│ Single Converter         │   │ Deterministic Executor       │
│ BUILD / REPAIR           │   │ preflight/replay/QA/package  │
│ manifest + trace + tests │   │ one runner/mount/service API │
└────────────┬────────────┘   └──────────────┬──────────────┘
             │ revision/hash                 │ stage envelopes
             └──────────────┬────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────┐
│ Evidence State Machine                                     │
│ sanity → judge → hard → QA → replay; retry/repair typed    │
└──────────────────────────┬─────────────────────────────────┘
                           │ accepted artifact + P2P bundle
                           ▼
┌────────────────────────────────────────────────────────────┐
│ Mechanical Package Builder                                 │
│ manifest copy + package environment build + clean smoke    │
└──────────────────────────┬─────────────────────────────────┘
                           ▼
                 atomic final_task + provenance
```

最终形态不是“更多脚本和更多特判”，而是：

> Prepare 产生唯一的事实和执行契约；Converter 产生唯一的 verifier revision；Executor
> 统一运行所有阶段；Controller 只按证据状态转移；Package 只机械消费已接受 artifact。

这使得问题能够被清楚地路由：执行契约问题修 Executor，产物/状态问题修 deterministic
framework，公共语义过窄修 Converter，候选本身错误不污染共享框架；同时保留足够证据判断
一个修复到底是 framework-level、instance-specific 还是尚未确定。
