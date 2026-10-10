# VerifierTrans 最终框架收敛与跨语言验证计划（现状对齐版）

## 1. 目标与边界

本计划是在当前 VerifierTrans 实现上继续收敛的指导文件。目标是让同一套框架在不写
instance-specific 特判、不修改主 Pipeline、不新增 Agent 的前提下，逐步验证并支持
不同仓库语言和测试基础设施。

职责保持不变：

~~~text
Converter / LLM
    → 负责“测什么”：historical F2P 到 observable functional verifier

Deterministic execution layer
    → 负责“怎么运行”：runner、cwd、mount、selector、service

QA
    → 验证 acceptance breadth 和错误实现拒绝能力
~~~

本计划不把 Gold patch 当作唯一规范，也不因没有 F2P seed 的 Problem Statement 行为
自动扩大 verifier 或 QA 范围。

状态标记：

- 已实现：当前代码已经提供，下一步只需回归验证或补测试。
- 部分实现：主路径存在，但有明确能力缺口。
- 未实现：当前源码还没有对应能力。
- 不纳入：原计划内容与当前已经确认的项目契约冲突。

## 2. 当前基线：主 Pipeline 不变

~~~text
Prepare / source + environment preflight
        ↓
单一 Converter BUILD 或 REPAIR
        ↓
deterministic sanity
        ↓
Semantic Judge
        ↓
Hard Validator + execution adapter
  ├─ Base F2P
  ├─ Gold F2P
  ├─ Base P2P
  ├─ Gold P2P
  └─ stability
        ↓
Positive QA + Negative QA
        ↓
Accumulated evidence replay
        ↓
Package + package smoke
        ↓
atomic final_task publication
~~~

这次只扩展现有 deterministic execution、packaging、artifact contract、preflight 和
测试，不增加 Runner Agent、Design Agent、QA Agent 或新的 Pipeline 状态。

主要模块：

| 责任 | 当前模块 |
| --- | --- |
| 路径和 attempt | src/verifier_trans/paths.py |
| 控制、revision、resume、QA 路由 | pipeline/orchestrator.py |
| Converter BUILD/REPAIR | pipeline/converter.py、agents/miniswe_session.py |
| 语言执行计划 | deterministic/execution/base.py、node.py、python.py、go.py |
| service bootstrap | deterministic/execution/services.py |
| Base/Gold/P2P replay | deterministic/replay/verifier.py |
| candidate replay | deterministic/replay/candidate.py |
| artifact/schema | deterministic/validation/ |
| package/smoke | deterministic/packaging/ |
| report/progress | deterministic/reporting/report.py |

## 3. 四项修改的状态总表

| 项目 | 状态 | 结论 |
| --- | --- | --- |
| A. repository-native execution adapter | 已实现 | ExecutionSpec/discovery 已被 replay、candidate replay、package 和 Prepare preflight 共用；Node Mocha/Jest/Vitest、TS loader metadata、Python/Go discovery 已接入 |
| B. final package 与 historical F2P 解耦 | 已实现 | package 按 P2P selector accounting source patch，排除 F2P-only 文件/可识别 hunk，并写 package_report；reward 只执行 converted F2P + retained P2P |
| C. Positive QA 放宽 historical F2P 条件 | 已实现 | current F2P + P2P + Judge 是硬条件；历史 F2P PASS/FAIL/infra 只写 audit evidence，旧 evidence 按 contract version 重新验证 |
| D. runs 数据目录整理 | 已实现 | 新 Prepare 使用 instance-root source + intermediate attempt；source manifest/layout manifest、repo 边界和旧布局 resolver 已实现 |

# 4. A：repository-native execution adapter

## 4.1 已实现

当前调用链已经把语义和运行环境分开：

~~~text
replay/verifier.py
replay/candidate.py
        ↓
execution_plan(...)
        ↓
language adapter
        ↓
command + runner mount + adapter version
~~~

已实现：

1. javascript、typescript、node、js、ts 统一归一化为 node；
2. Python、Node、Go 有独立 adapter；
3. replay 和 candidate replay 使用 execution_plan；
4. package 使用 package_execution_plan，与 replay 共用语言命令生成；
5. execution contract 为 execution-adapter-v1；
6. replay 固定 cwd=/app，挂载 verifier、selectors、sealed patch、logs；
7. services.py 提供有界 Redis bootstrap；
8. Docker、toolchain、timeout、setup、patch、marker 失败进入 infrastructure；
9. Converter prompt 和 sanity 禁止模型生成 Docker、selector parser、P2P runner；
10. package 只改变 runner 的容器路径（/tests 对应 replay 的 /framework）。

当前实际覆盖范围：

| 生态 | 当前实现 | 状态 |
| --- | --- | --- |
| Python | functional 直接 python3，P2P 使用框架 pytest runner | 基础支持 |
| JavaScript + Mocha | functional 直接 node，P2P 调用 node_modules/.bin/mocha | 基础支持，需真实任务验证 |
| TypeScript | Node adapter + discovered loader metadata + shared selector runner | 已实现，fresh task 仍留待 Step 5 |
| JavaScript + Jest/Vitest | Node adapter 按 discovered runner family 执行 | 已实现，fresh task 仍留待 Step 5 |
| Go | go test + framework Go selector adapter | 基础支持，需真实任务验证 |
| 其他语言 | run.sh fallback | 不应宣称通用支持 |

## 4.2 实现边界与验证限制

### A1. Native runner discovery

当前已在现有 adapter 内实现 deterministic ExecutionSpec。它解析 package.json、
pyproject.toml/pytest.ini/tox.ini、go.mod/Makefile，记录 runner、cwd/module root、
package manager、selector style、TypeScript loader、services 和 support status。原 test
command 仍只是 dataset execution evidence，不能直接作为最终命令。

~~~text
repo metadata
  ↓
runner discovery
  ↓
ExecutionSpec
  ├─ runtime/language
  ├─ package manager
  ├─ runner family
  ├─ cwd/module root
  ├─ selector strategy
  ├─ required services
  └─ environment
  ↓
replay + candidate replay + package
~~~

Gold checkout、historical private selector、Gold-specific assertion 和实现绑定命令不能
直接继承。

### A2. Node/TypeScript runner family

同一个 Node adapter 现在支持：

- Mocha；
- Jest；
- Vitest；
- ts-node、tsx、Node type-stripping 或 repository-native TypeScript script；
- monorepo/package subdirectory 的 cwd/module root。

TypeScript 不能仅因为 language 归一化为 node 就 PASS。必须确认：

~~~text
functional artifact 可执行
TS loader/transpiler 可用
P2P runner 可执行
selector 能映射到真实测试
package smoke 使用同一执行规格
~~~

缺 runner/loader 时应报告 toolchain/runner infrastructure，而不是让 Converter 绕过。

### A3. 非 Python preflight

Prepare preflight 现在增加：

- Node：node 版本、package manager、runner binary、依赖加载和 selector collection；
- TypeScript：loader/transpiler 和 TS collection；
- Go：go version、module root、package build/test collection；
- 实际执行数量、selector mismatch 和退出码检查；
- package command 可生成性。

### A4. Service metadata

当前只有通用 Redis bootstrap，且只在镜像已有 redis-server/redis-cli 时尝试启动。没有
通用数据库或消息队列生命周期。

本阶段只扩展已有 service contract 和 failure classification。只有能由
dataset/image metadata 稳定描述的 service 才纳入；不能由 Converter 临时启动。

## 4.3 A 的实施顺序和测试

1. 定义并实现现有 adapter 使用的 runner metadata/schema；
2. 接入 Python、Node/TS、Go discovery 和语言对应 preflight；
3. 扩展 Node selector runner family，保留 Mocha；
4. 让 replay、candidate replay、package smoke 消费同一个 ExecutionSpec；
5. unknown language 保留明确 fallback，但不计入跨语言支持；
6. 每个通用修复写 process UTC 记录。

测试需要覆盖：

- language normalization 和 package/replay plan 一致性；
- package.json、pyproject、go.mod、Makefile discovery fixtures；
- Mocha/Jest/Vitest/TS loader selector contract；
- cwd/module root；
- 缺 runner/loader/依赖时的 infrastructure 分类；
- Redis 和 unsupported service；
- package smoke 使用相同 execution family。

A 完成定义：

~~~text
语言识别成功不再等于 runner PASS；
runner、cwd、module root、selector、service、package 命令都有确定性 ExecutionSpec；
replay 和 package 不维护会漂移的独立 runner 分支；
Converter 仍然不负责 runtime plumbing；
~~~

# 5. B：清理 final package 与 historical F2P 的关系

## 5.1 已实现

package_task.py 当前已经：

1. 打包 converted functional verifier；
2. 打包 framework-owned P2P runner；
3. tests/test.sh 只执行 package F2P 和 package P2P；
4. grader.py reward 只由 converted F2P 与 retained P2P 退出码决定；
5. package smoke 在 clean Base + Gold model patch 上运行；
6. package 阶段不调用 legacy_f2p execution group；
7. Gold 仍然只是 known-correct solution.patch/reference。

所以 historical F2P 已经不再是最终 reward 的直接执行判据。

## 5.2 实现结果与保守边界

最终 test.patch 现在是：

~~~text
P2P-retained slice of restricted/original_test.patch
+
converted verifier files
~~~

original_test.patch 可能同时包含：

- P2P 所需 post-PR test files；
- historical F2P test files；
- F2P/P2P 共用 fixture、helper 和 setup；
- 其他影响测试运行的文件修改。

这里需要区分两个概念：

1. P2P 的功能语义不依赖 historical F2P。P2P 本来就是 Base/Gold 都应通过的回归
   测试，不应因为 F2P 的断言而获得额外的 grading 权重。
2. P2P 的测试文件、fixture、helper 或 post-PR test state 可能与 F2P 物理上共用。
   这是测试文件依赖问题，不等于 P2P 依赖 historical F2P 语义。

因此 package 不再保留完整 original_test.patch，而是确定性保留 P2P 所需的测试状态和
fixture，排除只服务于 historical F2P 的测试内容。`package_report.json` 记录保留、排除
和 shared/ambiguous accounting；不能仅凭“当前 test.sh 没有调用 legacy selector”判断隔离。

## 5.3 B 的实施范围

在现有 package Pipeline 内增加 deterministic package accounting：

1. 根据 resolved_test_selectors 识别 P2P 需要的 nodes/files；
2. 分析 original_test.patch 的文件和 hunks；
3. 区分 P2P 必需状态、shared fixture、F2P-only test body 和 F2P-only fixture；
4. package test patch 只保留 P2P 状态、必要 fixture、converted verifier 和
   framework-owned support；
5. 如果 F2P/P2P 位于同一文件，使用确定性的 hunk/test-node 依赖分析；无法安全切分时
   必须显式失败为 package artifact ambiguity，不能静默把完整 F2P patch 带入；
6. final grader 只运行 converted F2P + P2P；
7. package report 记录 retained P2P files、shared fixtures、excluded F2P files/hunks；
8. package smoke 验证清理后的 package patch 仍能在 Gold 上通过。

不能按 instance 文件名写分支，也不能粗暴删除可能被 P2P 使用的 helper。

涉及模块：

- deterministic/packaging/package_task.py；
- deterministic/packaging/package_smoke.py；
- deterministic/preparation/prepare_instance.py；
- deterministic/preparation/common.py；
- deterministic/replay/verifier.py；
- deterministic/validation/artifact_contract.py；
- paths.py 的 package artifact link。

测试需要增加：

- package test.patch composition fixture；
- test.sh 不调用 legacy F2P；
- P2P 所需 test file/helper 被保留；
- F2P-only test/hunk 被排除，且不会通过副作用影响 P2P；
- package smoke Gold replay；
- package report 的 source/retained/excluded accounting。

B 完成定义：

~~~text
final test.sh 的 reward 只由 converted F2P + retained P2P 决定；
P2P 的功能语义不依赖 historical F2P；
P2P 状态和 fixtures 仍可用；
historical F2P test body/hunk 不进入最终 grading artifact；
test.patch 来源、保留项和排除项可审计；
package smoke 与 hard replay execution contract 一致；
~~~

# 6. C：Positive QA contract 放宽 historical F2P 限制

## 6.1 修改目标

原实现曾把 historical F2P runnable + FAIL 当成 Positive 的硬条件；现已移除，因为
historical F2P 也可能包含合理的功能性测试：

~~~text
Positive candidate
  current converted F2P PASS
  P2P PASS
  Solution Judge = VALID
  historical F2P 可以 PASS，也可以 FAIL
~~~

如果一个功能正确的 Positive 同时通过 historical F2P，不能因此把它判为无效。旧测试
可能本身就是 public/observable functional test，而不是 implementation-bound test。
historical F2P FAIL 仍有研究价值，但只能作为对比统计，不能作为 Positive validity gate。

该修改不改变主 Pipeline，不新增 Agent，也不新增 strong/weak evidence 等 Pipeline state。

## 6.2 当前实现

relaxed contract 已在以下位置统一实现：

- Positive deterministic precheck；
- Solution Judge 后重新 replay current/P2P；
- evidence 写入 `contract_version: 2` 和 historical F2P audit 字段；
- resume 对旧 evidence 做当前 contract revalidation；
- accumulated evidence replay；
- positive generator 和 judge prompt；
- README、architecture 和报告口径。

需要修改的有效条件：

~~~text
P2P runnable + PASS
current F2P runnable + PASS
Solution Judge = VALID
~~~

historical F2P 仍然执行，但只记录：

~~~json
{
  "historical_f2p_runnable": true,
  "historical_f2p_pass": true
}
~~~

如果 historical F2P 不 runnable，应记录 infrastructure evidence，但不能因此把当前
Positive 的功能性判断伪装成 semantic failure。Positive Judge 可以看到该结果用于分析，
但 prompt 必须明确：historical F2P PASS/FAIL 不决定 VALID。

已同步修改：

- pipeline/orchestrator.py 的 precheck、Judge 后 recheck 和 evidence append；
- pipeline/qa.py 的 evidence schema/helper；
- prompts/qa/positive_generator.md；
- prompts/judges/positive.md；
- README、architecture、reporting；
- resume 时的 Positive evidence migration/revalidation 逻辑。

旧 Positive evidence 不能静默当作新 evidence。应在当前 revision 上重新执行 current F2P
和 P2P，并补写 historical_f2p_pass；不能因为旧 evidence 曾经满足 strict gate 就跳过
replay。

## 6.3 C 的测试和完成定义

测试需要覆盖：

- current PASS / historical PASS / P2P PASS / Judge VALID：接受；
- current PASS / historical FAIL / P2P PASS / Judge VALID：接受；
- current FAIL：拒绝；
- P2P FAIL：拒绝；
- historical 不 runnable：标记 infrastructure，不当作 Positive semantic verdict；
- Judge VALID 后仍重新 replay current/P2P；
- historical_f2p_pass 只影响统计，不影响 accepted；
- prompt、代码、evidence schema 和 report 口径一致。

C 完成定义：

~~~text
Positive 的 accepted 不依赖 historical F2P FAIL；
current functional verifier PASS；
P2P PASS；
Solution Judge VALID；
historical F2P 结果完整记录但只作为统计/audit evidence；
不新增 Agent、不新增 Pipeline state；
historical F2P 不进入 final package reward；
~~~

# 7. D：runs 数据目录整理

## 7.1 当前布局与目标布局

当前 RunLayout 已实现：

~~~text
runs/<instance_id>/
├── final_task/
├── review/
│   ├── progress.md
│   ├── progress.json
│   ├── conversion_report.md
│   ├── metrics.json
│   ├── instruction_scope_trace.json
│   └── f2p_mapping.csv
└── intermediate/
    ├── latest_attempt.json
    └── attempts/attempt_NNN/
        ├── source/{public,restricted,sealed,reference}
        ├── prepare/
        ├── converter/{current,revisions,staging,trajectories,live}
        ├── validation/{sanity,semantic,hard_replay,evidence_replay}
        ├── qa/{positive,negative,candidates,evidence.json}
        ├── packaging/{candidate_task,logs,...}
        ├── control/{state,events,final,report}
        └── .compat/
~~~

.compat 是相对 symlink 兼容视图，不复制 artifact，也不进入 final_task；旧 attempt 的
source 仍由 resolver 读取。新 Prepare 将 materialized repo 放在 attempt/prepare/repo。

目标布局改为 instance root 下四个一级边界：

~~~text
runs/<instance_id>/
├── source/                         原数据信息，尽量 immutable
│   ├── dataset_row.json
│   ├── metadata.json
│   ├── public/{problem_statement.md,interface_contract.md}
│   ├── restricted/
│   │   ├── original_test.patch
│   │   ├── test_seeds.json
│   │   ├── resolved_test_selectors.json
│   │   └── original_tests/
│   ├── sealed/{gold.patch,requirements.md,interface.md}
│   └── source_manifest.json
├── intermediate/                   所有构造过程，按 attempt 和阶段分类
│   ├── latest_attempt.json
│   └── attempts/attempt_NNN/
│       ├── prepare/{repo,logs,source_preflight.json,environment_preflight.json}
│       ├── converter/{current,revisions,staging,trajectories,live}
│       ├── validation/{sanity,semantic,hard_replay,evidence_replay}
│       ├── qa/{positive,negative,candidates,evidence.json}
│       ├── packaging/{candidate_task,logs,package_report.json,smoke_report.json}
│       ├── control/{state.json,events.jsonl,final.json,report.json}
│       └── .compat/
├── final_task/                      全部 gates 后原子发布
└── review/                          面向人的汇总和审计
    ├── progress.md
    ├── progress.json
    ├── conversion_report.md
    ├── metrics.json
    ├── instruction_scope_trace.json
    └── f2p_mapping.csv
~~~

目标中的 source 是原始任务信息，不是 materialized working tree。repo、临时 workspace 和
大型 runtime artifact 放入具体 attempt 的 intermediate/prepare，避免 source 被模型或
执行过程写入。

## 7.2 与原计划和当前实现的差异

当前代码已经实现 run-root source：

~~~text
runs/<instance_id>/source/
~~~

旧布局 source 仍位于每个 attempt：

~~~text
runs/<instance_id>/intermediate/attempts/attempt_NNN/source/
~~~

新 Prepare 将 immutable 原始信息保留在 instance root，同时把 selector resolution、preflight、
materialized repo 和 mutable artifact 留在 attempt；source manifest 与 dataset row 检查
防止不同 source row 静默覆盖，旧 runs 不做物理迁移。

命名也有差异：

- dataset_row.json 和 source metadata 位于 instance-root source，prepare/source_row.json
  与 prepare/metadata.json 作为运行时/旧接口兼容文件保留；
- problem_statement/interface contract 位于 source/public；
- gold.patch/requirements/interface 位于 source/sealed；
- selectors/test_seeds 位于 source/restricted；
- 人类报告是 review/conversion_report.md；
- 当前没有必需的 review/audit 目录；review 仍保留 progress 和 conversion_report 等
  现有文件，是否增加 audit 子目录由报告需求决定。

## 7.3 D 的实施原则

D 的目标是实际落地上述 instance-centric 边界，不做破坏性旧 runs 迁移。只实现通用能力：

1. 在 RunLayout 中明确 source、intermediate、final_task、review 四个一级目录；
2. 将 dataset_row、metadata、public/restricted/sealed 原始材料写入 source；
3. 将 source_manifest/hash 作为 immutable source contract；
4. 将 materialized repo、preflight、selector resolution 和 logs 放入 attempt/prepare；
5. 保留 .compat，把旧的 public/restricted/sealed/verifier/run 路径映射到新 canonical path；
6. 提供旧 attempt layout 和新 layout 的 path resolver；
7. report/progress、resume、package、publish 全部通过 resolver 取路径；
8. final_task 继续通过 publish_final_task 原子发布。

可先增加 layout manifest：

~~~json
{
  "schema_version": "1.0",
  "run_root": "...",
  "attempt_root": "...",
  "source_root": "...",
  "derived_root": "...",
  "final_task": "...",
  "compatibility_view": "..."
}
~~~

新 Prepare 已切换到该布局；report、resume、package、publish 通过 `.compat` 和
`AttemptLayout.source` resolver 同时支持新旧布局。

涉及模块：

- paths.py；
- preparation/prepare_instance.py；
- deterministic/reporting/report.py；
- pipeline/orchestrator.py；
- pipeline/artifacts.py；
- tests/unit/test_paths.py；
- tests/unit/test_reporting.py；
- tests/integration/test_isolation.py。

测试需要增加：

- fresh attempt 不覆盖旧 attempt；
- latest_attempt 只指向最新 prepared attempt；
- source 不被 Converter/QA/Prepare runtime 写入；
- source_manifest/hash 防止不同 source row 静默覆盖；
- source 与 intermediate/prepare/repo 的边界；
- materialized repo 不进入 final_task；
- .compat 与真实 artifact 同步；
- report/progress 在 resume/terminal 后可重建；
- old layout resolver；
- layout manifest schema。

D 完成定义：

~~~text
instance root 明确分为 source、intermediate、final_task、review；
source immutable，materialized repo 和 runtime 在 intermediate/attempt；
旧 runs 可读；
attempt isolation 保持；
final_task 不包含中间 artifact；
resume/report/package 使用同一 path contract；
~~~

# 8. 当前 tests 基线与缺口

已有测试覆盖：

- language normalization 和基础 execution plan；
- replay/candidate 委托 execution adapter；
- Redis bootstrap 源码 contract；
- F2P accounting、trace、manifest normalization；
- workspace/candidate isolation；
- AttemptLayout、.compat、final publication；
- report、progress、instruction scope。

仍明确留待 Docker/fresh validation 的范围：

- Docker 内真实 Node/TS/Jest/Vitest/Go native execution；
- package smoke 的多语言 end-to-end；
- Redis 以外的 service contract。

静态 runner discovery、module root/cwd、非 Python preflight、package patch accounting、
Positive truth table、layout manifest 和旧路径 resolver 已由本轮 tests 覆盖；实际 Docker
执行按计划留到 Step 5。

每轮框架改动后执行：

~~~bash
cd /lg-home/cog8/lwli6/VerifierTrans
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
.venv/bin/verifier-trans --help
~~~

真实 Docker/repo 验证必须使用 fresh Prepare，不复用旧 attempt；API 暂停时不能伪造
Semantic Judge、QA 或 package 结果。

# 9. 实施顺序与停止条件

## Step 0：冻结当前基线

记录源码、测试结果、execution-adapter-v1、已有成功任务 regression 和暂停任务状态。
本步骤不调用外部模型。

停止条件：

~~~text
现有测试 baseline 可复现；
暂停任务状态保持；
没有旧 evidence 被静默改写；
~~~

## Step 1：完成 A（已完成）

先做 runner metadata/discovery、Node/TS/Jest/Vitest、Go/非 Python preflight 和
ExecutionSpec 共用。每项先有 fixture test，再接入 replay/package。

停止条件：

~~~text
同一 ExecutionSpec 可生成 replay、candidate replay、package command；
缺 runner 有明确 infrastructure 结果；
没有 Converter runtime plumbing；
~~~

## Step 2：完成 B（已完成）

明确 retained P2P state、shared fixtures、排除 historical F2P test body/hunk 和 final
reward。补 test.patch、package report、smoke tests。

停止条件：

~~~text
final test.sh 不运行 legacy F2P，且不把 F2P-only test body/hunk 带入 grading artifact；
P2P 在 clean Base + package patch 上真实执行；
F2P/P2P/package 来源可审计；
~~~

## Step 3：实施 C 的 Positive 放宽（已完成）

移除 historical F2P FAIL 的 Positive 硬 gate，保留 historical replay 作为统计/audit
evidence，补 truth-table tests 和 report clarity。

停止条件：

~~~text
Positive 证明 current PASS + P2P PASS + Judge VALID；
historical PASS/FAIL 只进入统计；
旧 Positive evidence 在 current revision 上重新验证；
~~~

## Step 4：完成 D（已完成）

实现 source root、layout manifest、resolver 和 regression；不迁移旧 runs，但让新 Prepare
使用目标布局，旧 runs 通过兼容 resolver 继续可读。

停止条件：

~~~text
fresh attempt、resume、report、package、publish 使用同一 path contract；
旧 runs 可读；
attempt isolation 和 final_task 边界不变；
~~~

## Step 5：冻结后做跨语言验证

按 Python → JavaScript → TypeScript → Go 使用 fresh Prepare：

~~~text
Python
instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c

Go
instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e

JavaScript
instance_element-hq__element-web-776ffa47641c7ec6d142ab4a47691c30ebf83c2e

TypeScript
instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b
~~~

每条任务必须记录 detected language、detected runner、cwd/module root、ExecutionSpec，
完成全部 gates，或把失败归类为通用 framework issue 并写 process UTC 记录。

禁止 instance_id、repo、测试名或 commit 专用逻辑。任务自身的特殊环境只能作为带 schema
的 runtime metadata/evidence，不能进入核心 repo 特判。

# 10. 错误分类与 process 记录

错误先分类，再决定修什么：

~~~text
artifact/schema → deterministic framework
Docker/mount/service/toolchain/runner → infrastructure/execution adapter
selector/cwd/module root → execution contract
observable semantics/overreach/false positive/false negative → Converter REPAIR
candidate 本身无效 → candidate regeneration
package wiring → packaging/execution adapter
~~~

禁止把 Docker、Mocha、pytest、selector 或 mount 未执行误判为 verifier semantic failure。

每个 framework-level 问题在：

~~~text
/lg-home/cog8/lwli6/VerifierTrans/process/
~~~

写 UTC 时间戳 Markdown，至少记录 instance、阶段、现象、root cause、failure category、
通用性判断、修改位置、影响语言/runner、新增测试、旧任务 regression 和是否需要 replay。

# 11. 最终验收

单任务必须满足：

~~~text
Prepare source/environment preflight PASS
所有 historical F2P accounting 完整
deterministic sanity PASS
Semantic Judge PASS
Base converted F2P FAIL
Gold converted F2P PASS
Base P2P PASS
Gold P2P PASS
Hard replay stable
至少 1 个 VALID Positive：
  current verifier PASS
  historical F2P 已 replay 并记录，PASS/FAIL 不决定 validity
  P2P PASS
  Solution Judge VALID
至少 2 个 qualified Negative 被 current verifier 拒绝
最新 revision 上所有累计 QA evidence replay PASS
package smoke PASS
final_task 原子发布成功
~~~

四条跨语言任务完成后，在 process/ 下生成总报告，汇总 instance、语言、repo、runner、
ExecutionSpec、revision、Base/Gold/P2P、QA、package smoke、final_task、framework issues、
是否特判、通用能力、regression 以及稳定性/效率/API 未解决问题。

最终要回答：

> 在不为具体 instance 编写特殊逻辑、且不新增 Agent/主 Pipeline 的前提下，
> VerifierTrans 是否能够稳定支持 Python、JavaScript、TypeScript 和 Go 的 fresh
> SWE-Pro instance，并完成到 final_task？

只有 A/B/C/D 的完成定义满足且四条任务通过同一套 gates，才能把框架从 pilot 视为
跨语言、可复用 baseline。
