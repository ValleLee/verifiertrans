# VerifierTrans 结构修改方案（最终收敛版，2026-09-23）

## 0. 文档定位

本轮目标不是重新设计一套更大的系统，而是：

> **保留已经打通的主 Pipeline，消除执行旁路、隐式 artifact 规则和 verifier 的实现耦合，使框架从“能跑”收敛到“契约清晰、可复现、可扩展”。**

当前主骨架保持不变：

```text
Prepare / Preflight
        ↓
Single Functional Converter（BUILD / REPAIR）
        ↓
Sanity → Semantic Judge → Hard Validator
        ↓
Positive / Negative QA
        ↓
Accumulated Evidence Replay
        ↓
Package → Clean Smoke → Atomic Publish
```

本方案不新增额外的“设计 Agent”或“Semantic Mapper”；不把 Gold 变成规范；不为单个 instance、repository、runner 或 runtime 写任务特判；也不因为 adapter 已存在就提前声称某个语言生态已经获得完整 E2E 支持。

---

# 1. 实验目标

VerifierTrans 的目标是将 SWE-Bench Pro 中以 historical F2P 为核心的测试任务，转换为更加 implementation-independent 的 functional verifier。

转换后的任务应满足：

- verifier 验证的是 public API、observable output、外部状态变化或错误语义；
- historical F2P 用于界定转换范围、恢复历史验证意图并提供 provenance；
- Gold patch 只是一个 known-correct implementation，不是唯一规范；
- verifier 不依赖 private helper、内部字段、Gold-specific 文件结构、调用顺序或算法；
- verifier 自己引入的 fixture、mock、fake runtime、test harness 不能缩小合理实现空间；
- 不同于 Gold、但满足 instruction 的合理实现应该能够通过；
- 只满足部分语义或故意破坏目标行为的实现应该被拒绝；
- 最终 `final_task` 应脱离 construction workspace 独立运行。

本轮结构修改主要解决四类长期问题：

| 问题类别 | 当前核心问题 | 目标状态 |
| --- | --- | --- |
| Execution Contract | 同一个 task 在不同阶段仍可能被不同方式执行 | 全流程只有一个“怎么运行”的定义 |
| Verifier Artifact Contract | 仍依赖文件名、目录扫描和 blacklist 推断正式 verifier | manifest 明确声明正式 artifact |
| Verifier Semantic Independence | assertion 已逐步解耦，但 fixture/mock/runtime 仍可能绑定 Gold | Solver 只需满足 specification；verifier 自己负责完整、中立的测试设施 |
| Package Contract | package 仍会重新理解 historical patch 和 verifier 文件 | Package 只机械消费前面已确定的 artifact |

Source/provenance、状态记录和 failure classification 作为横向保障保留，但不再扩展成新的业务阶段。

---

# 2. 最终 Pipeline

```text
                 Original SWE-Pro Instance
        P / R / I / F2P / P2P / Gold / Repo / Env
                           │
                           ▼
              ① PREPARE / PREFLIGHT
                     [SCRIPT]
                           │
             freeze source evidence
             materialize Base repo
             resolve F2P / P2P selectors
             identify required P2P assets
             discover + freeze ExecutionSpec
             repository-native preflight
                           │
                           ▼
              ② FUNCTIONAL CONVERTER
                  [mini-swe-agent]
                           │
          historical F2P intent
                   ↓
          behavior to verify
                   ↓
          how to observe behavior
                   ↓
          executable functional verifier
                           │
          + instruction
          + verifier manifest
          + conversion trace
                           │
                 ┌─────────┴─────────┐
                 │  Converter Loop   │
                 │                  │
                 │ Sanity [SCRIPT]  │
                 │       ↓          │
                 │ Semantic Judge   │
                 │   [fresh LLM]    │
                 │       ↓          │
                 │ Hard Validator   │
                 │   [SCRIPT]       │
                 │       ↓          │
                 │ Base functional  │
                 │        FAIL      │
                 │ Gold functional  │
                 │        PASS      │
                 │ Base P2P PASS    │
                 │ Gold P2P PASS    │
                 │ Stability PASS   │
                 │                  │
                 │ FAIL → REPAIR    │
                 └─────────┬────────┘
                           │
                           ▼
                  accepted revision
                           │
                           ▼
                   ③ VERIFIER QA
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
       POSITIVE MODE                NEGATIVE MODE
        Solver Agent                 Mutant Agent
      [fresh session]              [fresh session]
             │                           │
      different valid              violate one mapped
      implementation                    behavior
             │                           │
       Solution Judge               Mutation Judge
             │                           │
             └────────────┬──────────────┘
                          ▼
                deterministic replay
                          │
           ┌──────────────┴──────────────┐
           │                             │
     VALID + FAIL                  INVALID + PASS
     false negative                false positive
           │                             │
           └──────────────┬──────────────┘
                          ▼
                  Converter REPAIR
                          │
                  new verifier revision
                          │
          Sanity → Judge → Hard Validator
                          │
              replay ALL accumulated QA
                          │
                          ▼
                     QA ACCEPTED
                          │
                          ▼
              ④ PACKAGE / CLEAN SMOKE
                     [SCRIPT]
                          │
             accepted verifier manifest
             + retained P2P assets
             + execution/environment contract
                          │
                 mechanical package
                          │
              clean environment replay
                          │
       Base FAIL / Gold PASS / P2P PASS
                          │
                          ▼
                     final_task
```

这四个阶段就是唯一顶层 Pipeline。Execution contract、manifest、evidence/state 等都属于它们内部的框架契约，不再单独扩成新的业务层。

---

# 3. 三个核心职责边界

## 3.1 Prepare：冻结事实与执行边界

Prepare 负责回答：

> **这个 repository 在什么稳定条件下可以被执行？**

主要职责：

- 保存原始 SWE-Pro row、P/R/I、F2P/P2P、Gold、test patch；
- materialize pristine Base repo；
- 冻结 source selector 与 resolved selector 的映射；
- 确定 repository-native runner；
- 确定 cwd、module root、loader、services、container paths、timeout 与 result parsing；
- 完成 source/environment preflight；
- 提前识别 P2P 所需 test files、fixtures 和 support assets。

Prepare 不决定：

- 最终 verifier 应验证什么功能；
- 应该调用哪个 public API 来验证功能；
- verifier 应该构造什么 fixture/mock；
- assertion 应该是什么。

这些属于 Converter。

---

## 3.2 Converter：负责“测什么 + 怎么把它测出来”

Converter 不是只写 assertion，也不是只抽象一个纯语义 specification。

它必须同时完成：

```text
historical F2P intent
        ↓
真正需要验证的 behavior
        ↓
选择 public / observable surface
        ↓
设计如何构造输入和观察结果
        ↓
实现 functional verifier
```

因此 Converter 负责：

- 理解 historical F2P 的真实行为意图；
- 去除 private helper、内部状态和 Gold-shaped assumptions；
- 决定通过哪个 public/observable surface 检查功能；
- 构造 verifier-owned fixture/mock/fake input/test harness；
- 编写 functional tests；
- 生成 instruction；
- 生成 verifier manifest；
- 生成 conversion trace；
- 在 REPAIR 模式下根据 QA evidence 修复 verifier。

核心原则：

> **Converter owns verification design：它负责“测什么”和“如何观察”；但不负责 Docker、repository-native runner、service lifecycle、mount、timeout 等执行基础设施。**

---

## 3.3 Executor：只负责稳定执行

Deterministic Executor 不理解 verifier 的语义。

它只回答：

> **给定 repo state、ExecutionSpec 和 verifier manifest，怎样稳定、可重复地执行它？**

Executor 负责：

- Docker image/container；
- mount；
- cwd/module root；
- Python/Node/TypeScript/Go runner；
- service bootstrap/readiness；
- environment variables；
- timeout/kill-after；
- selector execution；
- exit code、marker 和 result parsing；
- Base / Gold / candidate / mutant / package replay。

可以简单理解为：

```text
ExecutionSpec
    = 运行边界

Verifier Manifest
    = 要执行的 verifier artifact

Executor
    = 按冻结边界机械运行 artifact
```

---

# 4. 问题一：Execution Contract 唯一化

## 4.1 当前问题

虽然已经有 `ExecutionSpec + execution adapter`，但仍存在执行旁路：

- Prepare/preflight 可能自行拼 runner command；
- replay、candidate、package 对 cwd/mount/container path 仍存在重复解释；
- service、timeout、result parsing 没有完全收进统一契约；
- selector/path normalization 在部分阶段仍可能重新处理；
- `/app`、`/framework`、`/tests`、`/workspace` 等路径存在历史兼容语义。

本质不是缺 ExecutionSpec，而是：

> **ExecutionSpec 还没有成为唯一执行事实源。**

## 4.2 目标状态

```text
Prepare
   ↓
freeze execution_spec.json
   ↓
Preflight
Base / Gold replay
Positive / Negative replay
Package smoke
   ↓
全部只消费同一 ExecutionSpec
```

## 4.3 建议修改

适度扩展现有 `ExecutionSpec`，统一包含：

```text
language
runner_family
package_manager
cwd
module_root
selector strategy
loader
services
container paths
environment
timeouts
result parser
support status
```

不需要现在建立庞大的通用 service framework；只需要把 Redis 等从散落字符串/脚本变成结构化 descriptor，并让所有阶段通过统一 Executor 消费。

Prepare 的 preflight 也不再拥有独立 runner 语义，而只是：

```text
Executor(mode=preflight)
```

### 完成标准

- 同一 attempt 的所有执行结果引用同一 `execution_spec_hash`；
- Prepare、replay、candidate、package 不再自行组装另一套 runner/mount/cwd/service；
- infrastructure failure 不进入 Converter semantic repair；
- adapter 存在不等于语言已支持，支持状态必须由 fresh Docker E2E 验证晋级。

---

# 5. 问题二：Verifier Artifact Contract 显式化

## 5.1 当前问题

当前仍存在隐式 artifact discovery：

```text
functional_*
functional_f2p.*
扫描顶层 .py/.js/.go/.sh
run.sh
workspace blacklist
```

这意味着 framework 仍可能通过“文件叫什么、目录里有什么”去猜正式 verifier。

## 5.2 目标状态

Converter 最终只提交明确的 verifier bundle，例如：

```text
Verifier Output
├── instruction.md
├── verifier_manifest.json
├── tests/
├── fixtures/          # 可选
├── runtime/           # 可选的 verifier-owned harness
└── conversion_trace.json
```

其中 `verifier_manifest.json` 是正式 artifact 的唯一声明。

Validator、Executor、QA、Package 只读取 manifest，不再扫描目录猜入口。

## 5.3 建议修改

Converter workspace 收敛为：

```text
workspace/
├── scratch/       # 模型探索、临时脚本、依赖、调试输出
└── output/        # 允许提交的正式产物
```

正式 revision 只接受：

```text
output/
+
manifest 中声明的 artifact
```

`functional_*` 仅保留 legacy compatibility，不再是新 revision 的执行契约。

`run.sh` 可以继续作为薄兼容入口，但不能承担 artifact discovery、Docker orchestration、P2P selector parsing 或动态安装依赖。

### 完成标准

- 没有合法 manifest 就不能进入 Semantic Judge / Hard Validator / Package；
- 未声明文件不会进入 accepted revision 或 final package；
- package 不再扫描 `functional_*` 或顶层语言文件；
- scratch、node_modules、缓存、临时实验文件不会进入 artifact。

---

# 6. 问题三：Verifier Semantic Independence

## 6.1 当前问题

早期主要防止：

```text
private helper
internal field
Gold-specific symbol
Gold-specific file layout
```

现在进一步发现：

```text
fixture
mock
FakeDOM
sanitizer shim
TypeScript runtime/transpiler shim
fake service
```

同样可能产生 implementation coupling。

也就是说：

> assertion 本身可以是 functional 的，但 verifier 为了运行 assertion 构造的测试设施仍可能只支持 Gold 的实现形状。

## 6.2 目标状态

Solver 只负责：

```text
Base Repo + Instruction
        ↓
实现任务要求
```

Verifier 自己负责：

```text
构造输入
提供必要 fixture/mock/harness
调用 public/observable surface
观察 output/state/error
完成 assertion
```

Verifier 可以依赖：

1. Base repo 已有的 public behavior/API；
2. Instruction 明确要求新增的 public contract；
3. Verifier 自己提供的 fixture/mock/test harness。

Verifier 不应依赖：

- Gold 才新增、但 specification 未要求的 helper；
- Gold-specific object shape；
- Gold-specific call sequence；
- Gold-specific runtime assumption；
- 只实现 Gold 所使用少量 API 的 synthetic mock。

核心原则：

> **Environment 提供真实软件执行条件；Verifier 自己构造测试条件，并负责保证这些测试条件不会缩小 specification 允许的合理实现空间。**

## 6.3 Environment 与 Verifier 的边界

```text
真实项目本来需要 Redis，但 Redis 没启动
→ Execution / Infrastructure Problem

真实 public DOM 支持 querySelector，
但 verifier 自己的 FakeDOM 不支持
→ Verifier Semantic / Fixture Coupling
```

Converter 可以设计 `how to observe`，但必须在冻结 execution capabilities 中实现。

例如 Converter 不能因为自己喜欢 jsdom 就临时联网安装 jsdom。

优先级：

```text
repository-native / real runtime
        ↓
已有标准 runtime/dependency
        ↓
必要时使用行为中立的 synthetic fixture/mock
```

不要因为单个 Tutanota 问题立即构建一个庞大的通用 DOM/runtime framework；先把该问题作为通用 semantic taxonomy，并依靠 Positive/Negative QA 暴露真实 coupling。

---

# 7. Verifier QA 设计

QA 不是新的问题类别，而是验证 verifier semantic independence 的主要证据机制。

## 7.1 Positive Mode

Positive Solver 使用：

```text
Base Repo + Instruction
```

生成与 Gold 在结构上不同、但语义上有效的实现。

流程：

```text
candidate
   ↓
deterministic precheck
   ↓
Solution Judge
   ↓
VALID
   ↓
deterministic verifier replay
```

若：

```text
Judge VALID
+
Verifier FAIL
```

则：

```text
VERIFIER FALSE NEGATIVE
→ Converter REPAIR
```

historical F2P PASS/FAIL 只作为 audit，不决定 candidate correctness。

---

## 7.2 Negative Mode

Negative Mutator 从已确认 valid 的 Positive parent 出发，只破坏一个已经映射的目标行为，同时尽量保持其余功能与 P2P 正常。

流程：

```text
valid positive parent
        ↓
violate one mapped behavior
        ↓
Mutation Judge
        ↓
RELEVANT NON-EQUIVALENT
        ↓
deterministic verifier replay
```

若：

```text
Judge INVALID
+
Verifier PASS
```

则：

```text
VERIFIER FALSE POSITIVE
→ Converter REPAIR
```

---

## 7.3 四象限判定

```text
                     Verifier

                 PASS          FAIL

VALID            TP            FALSE NEGATIVE
candidate

INVALID          FALSE         TRUE REJECTION
candidate        POSITIVE
```

Judge 负责判断 candidate/mutant 的语义属性。

Deterministic replay 负责判断 verifier 实际 PASS/FAIL。

两者结合后才能判断 verifier 是否存在 defect。

---

## 7.4 Repair 规则

只有 verifier semantic defect 才生成新的 verifier revision，例如：

```text
VALID + FAIL
INVALID + PASS
prompt/verifier mismatch
fixture/mock/runtime coupling
```

流程：

```text
Converter REPAIR
      ↓
new revision
      ↓
Sanity
      ↓
Semantic Judge
      ↓
Hard Validator
      ↓
Replay ALL accumulated Positive / Negative evidence
```

Infrastructure defect：

```text
Docker
mount
runner
service
timeout
endpoint
```

只进入 framework retry/repair，不生成新 verifier revision。

---

# 8. Validation Gate

每个 verifier revision 至少经过：

```text
Artifact Sanity
      ↓
Semantic Judge
      ↓
Hard Validator
```

Hard Validator 使用冻结的 ExecutionSpec 和统一 Executor，检查：

```text
Base converted functional verifier FAIL
Gold converted functional verifier PASS

Base retained P2P PASS
Gold retained P2P PASS

stability PASS
```

historical F2P：

```text
用于 conversion scope / provenance / audit
不进入 final reward
不作为 alternative solution validity 的硬门槛
```

Semantic Judge 重点检查：

- instruction 与 verifier 是否一一对应；
- 是否测试了 specification 之外的行为；
- 是否依赖 private helper/internal state/Gold-only path；
- fixture/mock/runtime 是否会让合理实现提前在 assertion 前失败；
- test harness 是否把 Gold 的实现选择伪装成环境要求。

---

# 9. 问题四：Package 机械化

## 9.1 当前问题

Package 当前仍可能：

```text
resolved P2P
+
original_test.patch
        ↓
重新判断 test file / hunk / fixture / shared setup
```

同时如果 manifest 不完整，还可能重新扫描 verifier。

这样 Package 会逐渐变成另一个“推理阶段”。

## 9.2 目标状态

Package 只消费：

```text
accepted verifier manifest
+
instruction
+
Prepare 已确定的 P2P assets
+
ExecutionSpec / environment descriptor
```

然后：

```text
mechanical copy/build
        ↓
clean replay
        ↓
atomic publish
```

## 9.3 建议修改

Prepare 在 selector resolve 后增加一个轻量资产清单：

```text
p2p_assets.json
```

记录：

```text
resolved selectors
required test files
required fixtures
shared setup/support files
ambiguous items
```

Package 优先使用这个清单。

只有无法静态判断的 shared hunk 才保留当前 heuristic，并明确标记：

```text
AMBIGUOUS / FALLBACK
```

不能静默携带整份 historical test patch。

Package 不再重新发现 verifier。

---

# 10. Clean Smoke

当前 clean Base checkout 的方向保留，但最终要验证 package 自己声明的环境，而不是隐式依赖 construction/source image。

目标流程：

```text
final package candidate
        ↓
fresh package environment
        ↓
pristine Base repo
        ↓
apply packaged retained P2P assets
        ↓
mount packaged verifier
        ↓
Base functional FAIL
Gold functional PASS
Base / Gold P2P PASS
        ↓
atomic publish
```

如果暂时只能使用 source image，则报告必须明确标记：

```text
SOURCE_IMAGE_ONLY
```

而不能声称 final environment 已独立验收。

---

# 11. Source、Revision 与 Controller：轻量收敛

这些是横向保障，不单独扩展成新的业务模块。

## 11.1 Source

保持：

```text
source/
```

为 immutable raw evidence。

至少保存：

```text
dataset_row.json
problem_statement
requirements
interface
original test.patch
raw F2P/P2P selectors
Gold patch
source_manifest/hash
```

resolved selectors、ExecutionSpec、P2P asset list 都是 derived view，不能覆盖 raw evidence。

---

## 11.2 Revision

Converter revision 保持 immutable：

```text
rev_001
rev_002
...
```

`current` 可以保留作为人类/兼容视图，但程序判断应引用明确 revision/hash。

Repair 必须产生新 revision。

Infrastructure retry 不产生新 revision。

---

## 11.3 Controller

Controller 不需要重新设计成复杂 DAG engine。

只要求：

- 合法 stage transition；
- stable failure class + subtype；
- evidence 带 attempt/revision/contract/hash；
- old evidence 不静默满足新 contract；
- interrupted/resume 不跳过 gate；
- Controller 不理解 pytest/Redis/DOM，只消费结构化 stage result。

建议保持少量稳定 failure class：

```text
ARTIFACT
INFRASTRUCTURE
SELECTOR_OR_PATH
VERIFIER_SEMANTIC
CANDIDATE_SEMANTIC
PACKAGE
INTERRUPTED
```

细节统一放在 `failure_subtype`。

暂时不为了架构形式完整引入复杂 ArtifactRef class hierarchy、通用 fencing system 或庞大 service/runtime abstraction；只有真实证据需要时再扩展。

---

# 12. 预期目录

继续沿用当前 instance-centric runs，不重新发明一套目录：

```text
runs/<instance_id>/

├── source/                         # immutable raw evidence
│   ├── dataset_row.json
│   ├── metadata.json
│   ├── source_manifest.json
│   ├── public/
│   ├── restricted/
│   │   ├── original_test.patch
│   │   ├── test_seeds.json
│   │   ├── resolved_test_selectors.json
│   │   ├── p2p_assets.json
│   │   └── original_tests/
│   ├── sealed/
│   └── reference/
│
├── intermediate/attempts/attempt_NNN/
│   ├── prepare/
│   │   ├── repo
│   │   ├── execution_spec.json
│   │   ├── source_preflight.json
│   │   ├── environment_preflight.json
│   │   └── logs/
│   │
│   ├── converter/
│   │   ├── workspace/
│   │   │   ├── scratch/
│   │   │   └── output/
│   │   ├── revisions/
│   │   │   ├── rev_001/
│   │   │   └── rev_002/
│   │   └── current/
│   │
│   ├── validation/
│   │   ├── sanity/
│   │   ├── semantic/
│   │   ├── hard_replay/
│   │   └── evidence_replay/
│   │
│   ├── qa/
│   │   ├── positive/
│   │   ├── negative/
│   │   ├── candidates/
│   │   └── evidence.json
│   │
│   ├── packaging/
│   │   ├── candidate_task/
│   │   ├── package_report.json
│   │   ├── smoke_report.json
│   │   └── logs/
│   │
│   ├── control/
│   │   ├── state.json
│   │   ├── events.jsonl
│   │   ├── final.json
│   │   └── report.json
│   │
│   └── .compat/                    # legacy only
│
├── final_task/
└── review/
```

`.compat` 继续用于读取旧 runs，但新逻辑不得把 `.compat` 当作 canonical data source。

---

# 13. 分阶段实施计划

为了避免把这次重构重新做成一个大工程，实际开发只按四步推进。

## Step 1：收紧 Execution Contract

优先级：P0。

要做：

- 扩展现有 ExecutionSpec；
- 统一 runner/cwd/mount/service/timeout/result parser；
- Prepare preflight 改为复用统一 Executor；
- replay/candidate/package 删除重复 command 组装；
- 统一 infrastructure failure classification。

通过条件：

- 一个 attempt 只有一个 execution spec/hash；
- 所有 replay/package plan 都由它生成；
- unknown runner 明确 unsupported；
- 没有 instance/repo-specific runner/service 分支。

---

## Step 2：收紧 Verifier Artifact

优先级：P0。

要做：

- manifest 成为唯一正式 artifact 声明；
- Converter workspace 分为 scratch/output；
- execution/sanity/package 改为 manifest-only；
- `functional_*` discovery 降级为 legacy reader；
- Package 禁止 fallback 扫描 verifier。

通过条件：

- 未声明 source/fixture 不进入 revision；
- 临时依赖、cache、symlink target 不进入 package；
- 不再依赖文件名前缀找到 verifier entrypoint。

---

## Step 3：收紧 Semantic QA

优先级：P1。

要做：

- 更新 Converter / Semantic Judge prompt；
- 明确 `how to observe` 属于 Converter；
- 固定 environment vs verifier-owned facility 边界；
- 保留 Positive Solver + Negative Mutator；
- false negative/false positive 才进入 Converter REPAIR；
- repair 后 replay 全部累计 evidence。

通过条件：

- 至少 1 个结构不同的 VALID Positive 被 verifier 接受；
- 至少 2 个 qualified Negative 被拒绝；
- fixture/mock/runtime coupling 能正确归为 verifier semantic defect；
- infrastructure failure 不生成 verifier revision。

---

## Step 4：收紧 Package + Cross-language E2E

优先级：P1。

要做：

- Prepare 产出 `p2p_assets.json`；
- Package 机械消费 manifest + P2P assets；
- unresolved/ambiguous patch dependency 显式记录；
- clean smoke 验证最终 package environment；
- 使用 fresh attempt 分别验证 Python / JavaScript / TypeScript / Go。

通过条件：

- final package 不重新扫描 verifier；
- historical F2P 不进入 reward；
- final_task 脱离 construction workspace 可运行；
- 只有 fresh E2E 完成的生态才标记为 supported。

---

# 14. 验收矩阵

## 14.1 每个 verifier revision

```text
source / preflight PASS
        ↓
artifact sanity PASS
        ↓
Semantic Judge PASS
        ↓
Base functional FAIL
Gold functional PASS
Base P2P PASS
Gold P2P PASS
stability PASS
        ↓
accumulated QA evidence replay PASS
```

---

## 14.2 每个最终 task

最低要求：

```text
≥ 1 VALID Positive
   Judge VALID
   current functional verifier PASS
   retained P2P PASS

≥ 2 qualified Negative
   Mutation Judge RELEVANT_NON_EQUIVALENT
   current functional verifier FAIL
   retained P2P PASS

latest revision replay all accumulated QA evidence

package report 无未处理 ambiguity

clean smoke PASS

atomic publish PASS
```

如果某个任务天然难以产生足够独立的 Positive/Negative，应进入显式 review，而不是通过降低 QA 标准或复用 Gold 来凑数。

---

# 15. 特别注意

## 15.1 不要重新把系统做重

本轮不优先实现：

- 新的 Semantic Mapper Agent；
- 独立 Verifier Builder Agent；
- 庞大的 Runtime Abstraction；
- 通用 DOM framework；
- 复杂 ArtifactRef class hierarchy；
- 复杂 lease/fencing infrastructure；
- 为每个 service 建立重型插件系统。

只有当真实任务连续暴露同一抽象缺口时，再升级为公共框架能力。

---

## 15.2 不把 Execution Contract 越权成 Specification

ExecutionSpec 只冻结：

```text
怎么执行
```

它不能决定：

```text
测什么行为
如何通过 public surface 观察行为
```

Historical tests 是 evidence/seed，不是 specification。

---

## 15.3 不把 verifier test facility 当成 solver 责任

如果真实 runtime 支持某个标准行为，而 verifier 自己的 mock/shim 不支持：

```text
这是 verifier defect
```

不能要求 Solver 改写实现来适配一个 Gold-shaped mock。

---

## 15.4 不把 adapter 存在等同于生态支持

Python、JavaScript、TypeScript、Go 的代码路径存在，只代表：

```text
implemented
```

只有 fresh Docker：

```text
Prepare
→ Converter
→ Hard
→ QA
→ Package
→ Clean Smoke
→ Publish
```

完整通过后，才能标记：

```text
supported
```

---

# 16. 最终预期

本轮修改完成后，VerifierTrans 不需要变成一个更复杂的系统，而应该变成一个边界更清楚的系统：

```text
Prepare
→ 冻结原始事实与唯一 execution contract

Converter
→ 把 historical F2P intent 转换成
   “测什么 + 如何通过 public/observable behavior 测出来”

Executor
→ 不理解测试语义，只负责稳定执行

QA
→ 用不同正确实现和近似错误实现
   验证 acceptance breadth / rejection strength

Package
→ 不重新推理，只机械消费已接受 artifact
   并在 clean environment 中复现
```

最终要建立的四条不变量是：

1. **一个 task 只有一个执行契约。**
2. **一个 verifier revision 只由 manifest 定义正式 artifact。**
3. **Solver 只负责满足 specification；Verifier 自己负责测试设施的完整性与中立性。**
4. **Package 不做新的语义推理，只机械消费前面已确定的内容。**

这四条成立后，路径、runner、Redis、TypeScript loader、`functional_*`、node_modules、symlink、FakeDOM、旧 evidence、package patch slicing 等问题，都可以被稳定地归入已有契约，而不再通过新的 instance-specific workaround 扩张框架。
