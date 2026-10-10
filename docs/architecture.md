# VerifierTrans：SWE-bench Pro 到 DeepSWE 功能验证任务的转换框架

更新时间：2026-09-28（Asia/Shanghai）

本文是 VerifierTrans 的当前架构说明和执行契约。内容以代码、生成的运行目录和已完成的
qutebrowser/Navidrome 转换结果为准；它不是早期设计草图。读者可以仅凭本文理解：输入从
哪里来、哪些信息可以被哪个角色看到、模型负责什么、确定性代码负责什么、一个 revision
如何被接受、最终 DeepSWE task 如何生成，以及失败如何分类和恢复。

## 1. 框架目的

VerifierTrans 的输入是 SWE-bench Pro 数据行及其仓库镜像，主要包含：

- Base commit 和仓库镜像；
- Problem Statement、Requirements、Interface；
- historical F2P（fail-to-pass）和 P2P（pass-to-pass）测试 selector；
- historical test patch 和 Gold patch。

输出是一个可供 DeepSWE/mini-SWE 使用的任务目录。任务包含 solver-facing instruction、
环境 Dockerfile、保留的 P2P 测试、转换后的 functional verifier、grader 和 known-correct
solution。目标不是把历史测试原样搬运，而是把 F2P 中有证据支持的行为改写成面向功能的
验证：

- 通过 public API 或公开入口触发行为；
- 检查可观察输出、状态变化和错误语义；
- 不依赖 Gold patch 的具体文件布局、private helper、内部字段或 mock 调用形状；
- 允许多个结构不同但满足同一 public contract 的实现；
- 仍然拒绝保持 P2P 行为、但违反已有 F2P 语义的实现。

Gold patch 是一种 known-correct construction 和 package smoke evidence。它帮助确定性代码
建立 Base/Gold 对照，但不是唯一规范。Problem Statement 中没有 F2P seed 支持的额外行为
只记录为 `spec_gap`，不会由通用框架凭空新增测试。

框架当前没有人工审核阶段。模型判断必须转化为结构化证据，并经过确定性门禁、复放、QA
和 package smoke；无法证明的实例以明确失败终态结束。

## 2. 设计原则和信息边界

### 2.1 模型与确定性代码分工

框架只有一个 pipeline controller：`pipeline/orchestrator.py`。它编排 revision、修复、
终态和发布，但不让模型决定运行命令或 Docker 结构。

| 部分 | 负责 | 不负责 |
| --- | --- | --- |
| Converter agent | 阅读允许的契约和证据，生成/修复 verifier artifact、instruction 和 F2P mapping | 不生成 Docker 命令，不实现通用 selector runner，不改变 frozen ExecutionSpec |
| Semantic Judge | 判断转换语义是否有缺陷、是否需要下一轮 repair | 不决定容器、mount、cwd 或测试返回码 |
| Positive/Mutation agent | 生成结构不同的候选实现或单语义 mutant | 不直接决定候选是否有效 |
| Solution/Mutation Judge | 判断候选是否是合法 alternative 或相关非等价实现 | 不覆盖确定性 replay 结果 |
| deterministic code | 准备数据、路径、schema、命令、Docker、replay、QA 判定、打包和报告 | 不根据模型猜测仓库运行方式 |

模型 endpoint 的返回只是一种提议或判断。Hard Validator、candidate replay 和 package smoke
读取同一个冻结的 `ExecutionSpec`，以实际容器结果作最终依据。

### 2.2 三个信息区域

Prepare 将输入拆成不同可见性区域，形成模型和数据的边界：

| 区域 | 典型内容 | 可见角色 | 用途 |
| --- | --- | --- | --- |
| `public/` | Base repo、Problem Statement、提取后的 public interface contract | Converter、solver/candidate role | 描述任务和公开行为 |
| `restricted/` | 原始 test patch、F2P/P2P seed、解析后的 selector、Base state | Converter 和 deterministic replay | 提供历史测试证据，但不是 solver instruction |
| `sealed/` | Gold patch、原始 Requirements、原始 Interface | Converter 和 package/smoke 的确定性步骤 | 构造 evidence、应用 known-correct patch；不进入 solver-facing instruction |
| `reference/` | taxonomy、框架参考资料 | Converter/Judge | 提供转换分类和审计参考 |

`public/interface_contract.md` 是从原始 interface 提取的公开子集。原始 requirements/interface
可能暴露 Gold-specific helper 或路径，因此保存在 `sealed/`，不直接提供给最终解题模型。

向外部模型发送仓库和任务上下文必须显式使用 `--allow-external-model-data`。凭据从 `.env`
读取，任何 trajectory、report、summary 和文档都不能写出密钥。

### 2.3 不可变证据和 revision

Prepare 生成的 source 与 ExecutionSpec 在一个 instance 内共享且冻结。每次模型提交得到一个
revision：

1. 模型先在隔离的 `converter/staging/` 中工作；
2. 只有显式提交信号出现后才复制到 `converter/revisions/rev_NNN/` 和 `converter/current/`；
3. sanity、semantic、hard replay、QA 和 package 结果都绑定 revision、artifact hash 和
   `execution_spec_hash`；
4. repair 只能由结构/语义证据触发，并从已有证据继续；不会覆盖历史 revision。

这样可以区分“模型生成错了”“执行环境不可用”和“框架路径/runner 错了”，也允许 resume
复用已经通过的不可变证据。

## 3. 代码组件

```text
VerifierTrans/src/verifier_trans/
├── cli.py                         # 统一命令入口
├── batch.py                       # 已 Prepare workspace 的有界并发调度
├── paths.py                       # RunLayout、AttemptLayout、兼容视图和路径安全
├── model_clients/
│   ├── base.py                    # 统一模型客户端接口和错误分类
│   ├── openai_compatible.py       # OpenAI-compatible endpoint
│   └── anthropic_compatible.py    # Anthropic-compatible endpoint
├── agents/
│   ├── miniswe_session.py         # Converter/solver/mutation 的 mini-SWE session
│   ├── workspace_tools.py         # 模型使用的受控 workspace 工具
│   └── judge.py                   # Semantic/Solution/Mutation Judge 调用
├── pipeline/
│   ├── orchestrator.py            # 唯一 controller：revision、门禁、QA、发布
│   ├── converter.py               # Converter session、submission、step budget
│   ├── qa.py                      # positive/negative contract 和证据累计
│   ├── state.py                   # PipelineState、FailureClass、事件持久化
│   └── artifacts.py               # hash、原子复制、final_task 发布
└── deterministic/
    ├── preparation/
    │   ├── prepare_instance.py    # parquet、角色区域、repo、preflight
    │   └── common.py              # selector、repo path、Base state 等工具
    ├── execution/
    │   ├── discovery.py           # ExecutionSpec 发现和 hash
    │   ├── base.py                # 统一 ExecutionPlan/容器 mount
    │   ├── python.py              # pytest/unittest 和 P2P adapter
    │   ├── node.py                # Mocha/Jest/Vitest/ospec adapter
    │   ├── go.py                  # Go functional/P2P adapter
    │   ├── *_p2p_runner.*         # 容器内 selector runner
    │   └── services.py            # 有界 service bootstrap
    ├── validation/
    │   ├── normalize_manifest.py  # 兼容旧 manifest 的确定性规范化
    │   ├── validate_verifier.py   # artifact schema、coverage、路径、scope
    │   ├── artifact_contract.py   # revision/hash/status contract
    │   ├── instruction_policy.py  # solver instruction 范围审计
    │   ├── path_contract.py       # verifier 运行时路径审计
    │   └── positive_structure.py  # 候选结构差异审计
    ├── replay/
    │   ├── verifier.py            # Base/Gold F2P/P2P Core Gate
    │   ├── candidate.py           # positive/mutant 解决方案复放
    │   └── p2p_runner.py          # Python selector runner
    ├── packaging/
    │   ├── package_task.py        # DeepSWE task、grader、test patch
    │   ├── package_smoke.py       # clean Base + Gold 的无网络 smoke
    │   └── test_patch.py           # P2P patch 保留和 F2P accounting
    └── reporting/
        └── report.py              # progress、metrics、mapping、报告
```

`cli.py` 将 `prepare`、`run`、`resume` 交给 orchestrator，将 `batch` 和 `report` 分别交给
对应模块。旧的 `.compat` 接口仍被 `paths.py` 提供给 deterministic 脚本，但它只是相对
symlink 视图，不是第二份 artifact 真相。

## 4. 运行目录和数据真相

每个 instance 只有一个 instance root；每次重新转换或恢复失败会产生新的 attempt：

```text
runs/<instance_id>/
├── source/                              # instance 级冻结输入
│   ├── dataset_row.json                 # 原始 parquet row
│   ├── metadata.json / source_manifest.json
│   ├── public/
│   │   ├── problem_statement.md
│   │   ├── interface_contract.md
│   │   └── repo -> attempt/prepare/repo
│   ├── restricted/
│   │   ├── original_test.patch
│   │   ├── test_seeds.json
│   │   ├── resolved_test_selectors.json
│   │   ├── base_state.json
│   │   └── p2p_assets.json
│   ├── sealed/
│   │   ├── gold.patch
│   │   ├── requirements.md
│   │   ├── interface.md
│   │   └── README.md
│   └── reference/
├── intermediate/
│   ├── latest_attempt.json               # 当前 attempt 指针
│   └── attempts/attempt_NNN/
│       ├── prepare/                      # repo、metadata、preflight、Docker 日志
│       ├── converter/
│       │   ├── current/                  # 当前已提交 verifier
│       │   ├── revisions/rev_NNN/        # 不可变 revision 快照
│       │   ├── staging/                  # 未提交 session 工作区
│       │   ├── trajectories/             # 模型 session
│       │   └── live/                     # 当前 session 的进度/输出
│       ├── validation/
│       │   ├── sanity/                   # artifact/schema/scope
│       │   ├── semantic/                 # Semantic Judge
│       │   ├── hard_replay/              # Core Gate 和 evidence replay
│       │   └── evidence_replay/
│       ├── qa/
│       │   ├── positive/                  # candidate precheck/judge
│       │   ├── negative/                  # mutant precheck/judge
│       │   ├── candidates/                # 候选源码/patch
│       │   └── evidence.json              # 累计 accepted evidence
│       ├── packaging/
│       │   ├── candidate_task/
│       │   └── logs/
│       └── control/
│           ├── events.jsonl               # 追加事实
│           ├── state.json                 # 快速状态
│           ├── final.json                 # 最终 core 判定
│           └── report.json                # 对外汇总报告
├── final_task/                            # smoke 后原子发布
├── review/                                # metrics/mapping/progress
└── layout_manifest.json
```

`attempt_NNN/.compat/` 提供旧脚本使用的逻辑路径：`.compat/public`、`.compat/restricted`、
`.compat/sealed`、`.compat/verifier`、`.compat/artifacts` 和 `.compat/run`。它们指向上述
canonical 目录；写入兼容视图就是写入 canonical 目录。

`instance_id` 禁止路径分隔符。Controller 和 Converter 使用 attempt-scoped lock；Converter
工作先写 staging，避免两个进程同时更新 `current`。`final_task` 只由 smoke 后的原子发布
函数生成，并附带 source attempt、revision、verifier hash 和 environment hash。

## 5. Prepare：冻结输入和执行契约

入口：

```bash
verifier-trans prepare \
  --data /lg-home/cog8/lwli6/Data/swebench_pro/test-00000-of-00001.parquet \
  --instance-id <instance_id> \
  --runs-root /lg-home/cog8/lwli6/VerifierTrans/runs \
  --materialize-repo
```

Prepare 不调用模型。它按以下顺序工作：

1. 校验 parquet 文件确实存在，并按 `instance_id` 或 row index 选择唯一数据行；
2. 生成 source/public/restricted/sealed/reference 目录和 metadata；
3. 从 raw interface 提取 public contract；Requirements、raw Interface 和 Gold patch 放入
   sealed；
4. 规范化历史 selector：统一 node id、解析测试路径、检查重复和缺失文件。Go 的裸
   `TestXxx` 名称保留为 selector，不会被当成文件路径；
5. 在 Docker 中 checkout Base commit，去除不需要的 `node_modules`/`.git` 后物化 repo，
   保存 `base_state.json`、commit 和原始 patch；
6. 根据已物化 repo 的 package.json、pyproject/pytest metadata、go.mod/Makefile 等发现
   `ExecutionSpec`；
7. 运行 source preflight 和 environment preflight，检查 repo、toolchain、测试文件、
   selector collection 和必要 service；
8. 计算 `execution_spec_hash` 并写入 metadata。之后所有 replay 只读取这个冻结 spec，
   不重新猜测命令。

### 5.1 ExecutionSpec

`ExecutionSpec` 是所有后续阶段共享的运行契约，包含：

- `language`、`runner_family`、`package_manager`；
- `cwd`、`module_root`、`selector_style`；
- 环境变量和 service；
- TypeScript loader metadata；
- `timeout_seconds`、startup timeout、kill grace；
- 统一结果解析器 `marker-v1`；
- `supported` 和 discovery reason。

当前确定性发现器覆盖：

| 语言 | 运行族 | selector/loader |
| --- | --- | --- |
| Python | pytest，必要时 unittest fallback | file-and-node |
| Node/JavaScript | Mocha、Jest、Vitest、ospec | file-and-grep、file-and-test-name 或项目原生 harness |
| TypeScript | 上述 Node runner 加 ts-node/tsx/仓库 loader metadata | 由仓库声明的 loader 执行 |
| Go | `go test` | package-and-test-name，支持 `file::TestName` 和裸 Go test name |

不支持的语言、缺失必要 metadata、无法 collection、缺 toolchain 或 service 不可用属于
infrastructure；Converter 不得在 session 中自行发明命令绕过 Prepare。

Redis 只在镜像同时存在 `redis-server` 和 `redis-cli` 时执行有界 bootstrap。其他 service
不会由 Converter 临时启动。

## 6. Converter artifact contract

Converter 每次 BUILD/REPAIR 必须在 verifier 目录产生一个完整 artifact。当前 schema 为
`3.0`，至少包含：

```text
verifier/
├── run.sh                         # 可执行 functional entrypoint
├── manifest.json                  # functional artifact、coverage、target、命令
├── instruction_scope.md           # solver-facing contract，末尾 INSTRUCTION_SCOPE: PASS
├── conversion_trace.json          # 每个 source F2P 的映射和决策
├── coverage_matrix.md             # 行为覆盖说明
├── conversion_log.md              # 转换说明
├── self_review.md                 # 末尾 SELF_REVIEW: PASS
└── <declared support/probe files>
```

`manifest.json` 至少声明：

- `schema_version`；
- `functional_artifact`；
- `functional_surfaces`；
- `f2p_command`、`p2p_command`（用于记录功能意图，不替代框架 runner）；
- `source_f2p_coverage`、`source_p2p_coverage`；
- `test_files` 中每个 source 到 repository target 的安全映射。

`validate_verifier.py` 会拒绝绝对路径、`..` 穿越、缺失文件、重复 coverage、未声明文件、
manifest/trace 不一致，以及把 selector parser、P2P runner、Docker 或 pytest runtime
塞回 `run.sh`。Converter 可以产生功能探针和 support fixture，但通用 Docker、selector
parser、语言 runner 必须留在 deterministic execution adapter。

`conversion_trace.json` 对每个 source F2P 记录：

- `source_test_id` 和原始意图；
- 相关 evidence、是否发现 binding；
- observable surface；
- `keep`、`rewrite`、`merge`、`drop` 或 `spec_gap`；
- emitted functional tests 和理由。

因此可以审计“每条历史 F2P 到哪里去了”，并防止模型悄悄丢弃或无证据新增行为。

## 7. 单实例 Pipeline

Controller 对一个 attempt 执行以下状态机：

```text
PREPARED
  └─ for each verifier revision
       CONVERTING / VALIDATING_EXISTING
         → manifest normalization
         → verifier sanity + path contract + instruction audit
         → Semantic Judge
         → Core Gate (Base/Gold F2P/P2P, repeated)
         → accepted evidence replay
         → Positive QA
         → Negative QA
       FINAL_VALIDATED
         → package_task
         → package_smoke
       PACKAGED → atomic final_task publication
```

### 7.1 BUILD/REPAIR 和提交

- 首个 revision 是 BUILD；后续 revision 是 evidence-led REPAIR。
- Converter session 有 step cap 和 request timeout，但“session 完成”必须以显式
  `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` 为准。
- 没有提交信号的 staging artifact 不进入 `current`，不会被误当成候选 verifier。
- 结构错误、Semantic Judge finding、Core Gate 的 semantic failure 或合法 positive 的
  false negative 才能触发 repair；已有有效 F2P mapping 应被保留。
- 模型 endpoint 的 400/401/402/403/404、Insufficient Balance、认证/权限错误是不可重试的
  `MODEL_ENDPOINT`/infrastructure failure；429、5xx 在有限次数内重试，不消耗 semantic
  repair 轮数。

### 7.2 Sanity 和 instruction audit

Sanity 是确定性检查，不依赖模型。它验证 artifact schema、manifest coverage、文件路径、
`run.sh` executable bit、runtime contract 和 instruction scope。范围审计硬拒绝：

- `/app`、`/workspace`、`/tmp` 等环境绝对路径；
- `tests/file.py::test_name` 之类历史 selector；
- `gold-specific`、`reference solution`、`file layout`、`mock call shape`、`AST scan`、
  `AST/name` 等实现绑定表述。

`private type`、`unexported` 等词只产生 advisory，因为某些 F2P 本身就是 public visibility
contract；Semantic Judge 结合 probe 和 observable evidence 决定是否合理。Instruction audit
是有限模式扫描，不是对所有实现耦合的完备证明。

### 7.3 Semantic Judge

Semantic Judge 接收 public contract、F2P seed、manifest、conversion trace、sanity evidence
和必要的 verifier tree。它只回答 artifact 语义是否合理：

- `PASS`：继续 Core Gate；
- `REPAIR`：写入 finding，Controller 启动下一 revision；
- malformed/endpoint failure：按 infrastructure 处理。

Judge 不能用一段“看起来像通过”的文字覆盖硬 replay 结果。

### 7.4 Core Gate

`deterministic/replay/verifier.py` 在同一个 frozen ExecutionSpec 和无网络 Docker 中执行：

1. Base checkout + functional verifier；
2. Gold patch 应用后 + functional verifier；
3. Base checkout + P2P selector runner；
4. Gold checkout + P2P selector runner；
5. 默认重复两次并比较结果签名。

接受条件是：

```text
Base F2P 失败
Gold F2P 通过
Base P2P 通过
Gold P2P 通过
四组均 runnable
重复结果稳定
```

每组都会记录 container exit、setup、patch check、patch、verifier return code、timeout、
日志路径和 `execution_spec_hash`。Docker、mount、cwd、selector、service、toolchain、
timeout、marker 等问题属于 infrastructure；可运行但返回 verifier failure 才属于 semantic
结果。

## 8. Execution adapter 和容器边界

### 8.1 容器挂载

Replay container 的逻辑约定为：

```text
/app                 image 中的 Base repo，作为当前工作树
/app/verifier        Converter functional artifact 的 repository target
/workspace           mini-SWE workspace 语义目录
/restricted          冻结 selector 和 test seed
/sealed              Gold/requirements/interface construction evidence
/framework           framework-owned replay runner
/logs                marker、测试输出和诊断
```

Verifier 确实在 Docker 中执行，但 Docker 只提供隔离和文件边界；“用什么命令执行挂载的
artifact”仍由框架 adapter 决定。因此 manifest target、ExecutionSpec 和 artifact 后缀必须
一起参与命令生成：`.sh/.bash` 用 `bash`，Python/Node/Go 源码才用对应 native runner。
这避免把 `run.sh` 当成 Go package 的错误。

### 8.2 三类执行

1. **Functional F2P**：adapter 根据 manifest target 挂载功能入口并运行；Verifier 自己负责
   observable assertions，返回码代表该 F2P 功能结果。
2. **P2P/legacy F2P**：framework-owned selector runner 读取冻结 selector JSON，运行原历史
   测试；它不被 Converter artifact 替换。
3. **Candidate replay**：在干净 Base checkout 上应用 candidate patch，再使用完全相同的
   functional/P2P/legacy plan。

Python、Node/TypeScript、Go 都统一输出 marker-v1/结构化结果。Go runner 对 `file.go::TestX`
按 package 分组；对 `TestX`、`BenchmarkX`、`FuzzX`、`ExampleX` 裸 selector，会在当前
checkout 找到唯一 `_test.go` 声明 package，未找到或多包歧义时显式失败。

## 9. QA：验证功能包容性

Core Gate 只能证明“Base 不通过、Gold 通过”，不能证明 verifier 没有绑定 Gold 实现。
QA 使用额外实现证据检验包容性。

### 9.1 Positive QA

1. `positive_generator` 从 public contract、P2P 和当前 verifier 约束生成结构不同的 candidate；
2. deterministic precheck 要求 candidate 可运行、P2P 通过、current F2P 可运行、不是
   exact Gold reproduction；
3. candidate 可通过或失败 current F2P。一个可运行的 current F2P failure 正是发现
   verifier false negative 的证据，不能直接当成 infrastructure；
4. Solution Judge 判断它是否满足 public contract；
5. 只有 Judge `VALID` 且 P2P/current functional F2P 通过，才成为 accepted positive；
6. historical F2P 是 audit evidence，不是 functional positive 的最终 validity gate。它可以
   与转换后的 verifier 分离或在旧测试环境中无法运行。

若合法 candidate 被 current verifier 拒绝，Controller 将记录 `VERIFIER_FALSE_NEGATIVE`，
并带着 evidence 回到同一 Converter 的 repair。QA 不直接修改 verifier。

### 9.2 Negative QA

Negative generator 从 accepted positive parent 出发，每个 mutant 只违反一个已有 F2P
语义，例如重新暴露一个被隐藏的 public boundary。Mutation Judge 必须给出
`RELEVANT_NON_EQUIVALENT`。确定性条件为：

```text
mutant 可运行
P2P 仍通过
current functional F2P 被拒绝
没有 infrastructure failure
```

mutant 若仍通过 current F2P，记录 false positive 并触发 verifier repair。通过的 positive
和 mutant 会写入 `qa/evidence.json`，每个新 revision 上再次 replay，防止修复一处语义时
破坏已经接受的包容性证据。

默认目标来自 `configs/experiment.yaml`：positive 1 个、相关 mutant 2 个、revision/step/
request/replay/package timeout 和 infrastructure retry 均有界。QA 失败不会转成隐含人工审核。

## 10. DeepSWE 打包

只有通过 sanity、Semantic Judge、Core Gate、evidence replay、QA 的 revision 才能调用
`deterministic/packaging/package_task.py`。生成的 task 为：

```text
final_task/
├── task.toml
├── instruction.md
├── environment/Dockerfile
├── tests/
│   ├── Dockerfile
│   ├── config.json
│   ├── grader.py
│   ├── test.sh
│   ├── test.patch
│   ├── resolved_test_selectors.json
│   ├── package_report.json
│   └── <framework runner source>
└── solution/
    ├── solution.patch
    └── solve.sh
```

### 10.1 test.patch

打包器从 historical test patch 中保留 P2P 所需的 test file、shared fixture、setup 和
support file，并将 converted functional artifact 作为 declared file 加入。F2P-only body
或 hunk 按 patch accounting 排除；如果 source 没有 P2P，记录 `source_empty_noop`，不伪造
P2P 节点。

### 10.2 grader 和 test.sh

`tests/test.sh` 在 task 容器中：

1. 应用 solver 的 model patch；
2. 按 unified diff 顺序解析 patch paths，失败即记录 apply_failed；
3. 执行 functional F2P 和 retained P2P；
4. 调用自包含 `grader.py`。

`grader.py` 支持：

- legacy `grade F2P_RC P2P_RC`；
- CTRF 和 JUnit 报告；
- 重复 node 取最差状态；
- 缺失 node 视为失败；
- `reward.json`、CTRF、F2P/P2P count、ratio、partial reward、apply_failed。

`config.json` 冻结 F2P/P2P node ids、报告格式和 execution metadata。grader 不读取转换过程
中的模型判断，也不把 Gold patch 当作 solver 唯一写法。

### 10.3 Package smoke

`package_smoke.py` 在 clean Base checkout 上应用 Gold patch、test.patch 和 functional
artifact，使用无网络 Docker 执行同一个 adapter 生成的 `tests/test.sh`。Smoke 证明 package
wiring 和 known-correct solution 可运行；它不证明任意未知 solver 都一定通过。Smoke PASS
后，`publish_final_task` 才把 candidate_task 原子移动到 instance root 的 `final_task`。

## 11. 状态、终态和报告

### 11.1 PipelineState 与 FailureClass

代码保留的 PipelineState 包括：

```text
NEW → PREPARED → CONVERTING
                 ├→ SEMANTIC_VALIDATING
                 ├→ HARD_VALIDATING
                 ├→ QA
                 ├→ REPAIR → CONVERTING
                 └→ FINAL_VALIDATED → PACKAGED
```

`MANUAL_REVIEW` 仅为兼容枚举；当前 controller 不把失败自动送入人工审核。

确定性 evidence 使用以下 FailureClass：

- `NONE`：当前 contract 通过；
- `ARTIFACT_SCHEMA`：manifest、文件、路径、coverage 或 instruction 不合约；
- `INFRASTRUCTURE`：Docker、toolchain、service、selector、timeout、模型 endpoint 等外部执行问题；
- `VERIFIER_SEMANTIC`：可运行 verifier/候选的行为不满足 gate；
- `QA_DEFECT`：候选或 mutation contract 不成立；
- `PACKAGE`：task 构建或 package smoke 失败。

对外 report status 为：

| 条件 | status/state |
| --- | --- |
| 全部门禁、QA、package smoke 通过 | `VERIFIED` / `PACKAGED` |
| 模型额度/认证、Docker、toolchain、runner、service | `INFRASTRUCTURE` |
| package 构建或 smoke 失败 | `PACKAGE` |
| schema、semantic、candidate 或 mutation 未通过 | `FAILED` |

### 11.2 事实文件

- `control/events.jsonl`：追加的状态事件，是时间线事实；
- `control/state.json`：当前状态的快速读取视图；
- `control/final.json`：Core/QA 最终接受证据；
- `control/report.json`：状态、phase、evidence、failure class、model usage；
- `review/metrics.json`：由 report 命令生成的统计、耗时和模型 usage；
- `review/f2p_mapping.csv`：F2P 到 functional test 的审计表；
- `review/instruction_scope_trace.json`：solver instruction 范围审计。

`review/` 是观察和批处理消费层，不参与判定；判定只依赖 attempt 内的结构化 evidence。

## 12. 恢复、批处理和常用操作

### 12.1 单实例

```bash
# 1. Prepare：读取一条 SWE-Pro 数据并冻结 source/ExecutionSpec
verifier-trans prepare \
  --data /lg-home/cog8/lwli6/Data/swebench_pro/test-00000-of-00001.parquet \
  --instance-id <instance_id> \
  --runs-root /lg-home/cog8/lwli6/VerifierTrans/runs \
  --materialize-repo

# 2. 首次执行或继续最新 attempt
verifier-trans run --instance-id <instance_id> \
  --runs-root /lg-home/cog8/lwli6/VerifierTrans/runs \
  --env-file /lg-home/cog8/lwli6/VerifierTrans/.env \
  --config /lg-home/cog8/lwli6/VerifierTrans/configs/experiment.yaml \
  --allow-external-model-data

verifier-trans resume --instance-id <instance_id> \
  --runs-root /lg-home/cog8/lwli6/VerifierTrans/runs \
  --env-file /lg-home/cog8/lwli6/VerifierTrans/.env \
  --config /lg-home/cog8/lwli6/VerifierTrans/configs/experiment.yaml \
  --allow-external-model-data

# 3. 查看结构化报告
verifier-trans report --workspace <attempt-or-.compat-view>
```

`run --no-resume` 会从下一 revision 开始；`--repair-packet` 用已有 evidence 显式启动下一次
Converter repair。resume 会检测 submitted artifact、immutable revision、已有 semantic/core/QA
结果，并尽量复用，不会重复覆盖已有 revision。

### 12.2 批量

```bash
verifier-trans batch \
  --workspace <prepared-attempt-1> \
  --workspace <prepared-attempt-2> \
  --max-workers 4 \
  --env-file /lg-home/cog8/lwli6/VerifierTrans/.env \
  --config /lg-home/cog8/lwli6/VerifierTrans/configs/experiment.yaml
```

Batch 只接受已经 Prepare 的 attempt，拒绝重复 workspace 和未准备目录；每个 worker 仍运行
完整单实例 controller，不绕过任何 gate。它在 `runs/batch_summary.json` 写入每个 workspace
的 return code、status、report 和日志，并且只有全部 `VERIFIED` 才返回 0。

## 13. 当前能力和边界

当前框架已经具备：

- 角色分区和 sealed/public 信息边界；
- Base/source/ExecutionSpec 冻结；
- revision、submission、hash、lock 和 resume；
- manifest/coverage/instruction/path 的确定性审计；
- Base/Gold Core Gate 和重复稳定性检查；
- positive alternative implementation 与 negative mutant QA；
- evidence 累计 replay；
- DeepSWE task、grader、无网络 package smoke 和原子发布；
- 可观测的事件、报告、mapping 和 model usage。

仍然存在的边界：

1. **模型依赖**：Converter、QA generator 和 Judge 的质量、额度、认证和返回格式会影响
   转换速度和成功率。HTTP 402/Insufficient Balance 是模型 infrastructure failure，不是
   verifier 语义结论。
2. **证据依赖**：只有 historical F2P 提供的行为才可进入通用转换；F2P seed 不足时只能
   标记 `spec_gap`，不能从 Problem Statement 猜测完整规范。
3. **审计边界**：instruction policy 是有限模式扫描；Semantic Judge、conversion trace、
   Core Gate 和 QA 必须共同证明功能导向，单个 PASS 不能视为完备证明。
4. **仓库能力**：未知语言、复杂 service、缺失 toolchain、无法 collection 或有歧义的
   selector 会被明确标为 infrastructure/prepare failure；框架不会让 Converter 猜命令。
5. **QA 成本**：positive/negative candidate 需要额外模型调用和 Docker replay，Go/Node 大型
   仓库可能耗时较长，因此所有 step、request、replay、QA 和 smoke 都有界。
6. **Smoke 语义**：package smoke 只证明 known-correct solution 和 task wiring；最终对未知
   solver 的包容性仍依赖已经累计的 positive/mutant evidence。

因此，VerifierTrans 的承诺是“对每条输入给出可恢复、可审计、确定性门禁的转换结果”，而不是
保证任意仓库都能转换成功。一个成功发布的 `final_task` 必须同时满足 artifact contract、
功能 Core Gate、包容性 QA 和 package smoke。
