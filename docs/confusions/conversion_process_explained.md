# VerifierTrans 任务转换过程说明

这份文档解释一个 SWE-Bench Pro 任务从原始数据到 `final_task/` 的真实运行过程，
重点说明 `workspace`、Docker、`app`、verifier 和各种测试材料之间的关系。

## 先看一句话版本

VerifierTrans 不是把 Gold patch 复制出来，也不是简单重新运行 historical F2P。
它做的是：

```text
历史上能区分 Base / Gold 的 F2P 证据
        ↓ Converter
一个可执行的、面向 public/observable behavior 的 verifier
        ↓ Docker 中的确定性回放
确认 Base 被拒绝、Gold 被接受、回归测试不被破坏
        ↓ QA
确认结构不同但正确的实现能通过，近似正确但违反语义的实现会被拒绝
        ↓ package smoke
发布 final_task/
```

每一层都有自己的职责。很多“执行问题”并不是 verifier 逻辑错误，而是上一层
产生的文件没有正确传给下一层，或者 Docker 运行环境没有按约定提供路径和服务。

## 1. 一次任务中有哪些对象

| 名称 | 实际含义 | 所在位置或运行位置 |
| --- | --- | --- |
| Dataset row | 一个 SWE-Bench Pro instance 的元数据、题面、patch、selector 等 | parquet 数据集 |
| Base | 未应用 Gold patch 的仓库 | Prepare 产生的 source/repository 材料，以及 Docker 中的 `/app` |
| Gold | 应用 Gold patch 后的仓库 | Prepare 产生的 reference 材料，以及 Docker 中的 `/app` |
| Historical F2P | 原始的 fail-to-pass 测试；转换范围的唯一种子 | `source/restricted` |
| Historical P2P | 原始的 pass-to-pass 回归测试 | `source/restricted` |
| Converter | 探索仓库并生成 verifier 的 mini-SWE-agent 会话 | 主机进程；可读完整 repo 和证据目录 |
| Verifier | Converter 生成的 `run.sh`、功能测试和审计文件 | `converter/revisions/rev_NNN` |
| Semantic Judge | 只读地判断 verifier 是否忠实表达 F2P 语义的模型调用 | 主机进程/API |
| Hard Validator | 不依赖模型判断的确定性回放脚本 | 主机进程启动 Docker |
| QA candidate | Positive alternative 或 Negative mutant 的候选实现 | `qa/positive`、`qa/negative` |
| `final_task` | 所有 gate 通过后才发布的最终任务包 | `runs/<instance>/final_task` |

这里的 `Base` 和 `Gold` 是两份不同的仓库状态；它们不是两个 verifier。verifier
应该在两份仓库状态上执行相同的可观察行为检查。

## 2. 主机上的 workspace 是什么

一次 Prepare 会创建一个新的 attempt：

```text
runs/<instance_id>/
└── intermediate/attempts/attempt_001/
    ├── source/        原始任务材料、Base/Gold/restricted/sealed
    ├── prepare/       preflight、仓库 materialization、Docker 日志
    ├── converter/     live snapshot、trajectory、verifier revisions
    ├── validation/    sanity、Semantic Judge、Hard replay 证据
    ├── qa/            positive/negative candidate 和 evidence
    ├── packaging/     package candidate、smoke 日志
    ├── control/       state.json、events.jsonl、report.json
    └── .compat/       给旧 runner 使用的相对路径适配层
```

这个目录就是主机上的“任务 workspace”。它不是 Docker 容器，也不是 NodeBB 的
运行目录。它是流水线的持久化工作台，保存每个阶段的输入、输出和证据。

`.compat/` 通常只包含指向正式分类目录的相对 symlink。例如：

```text
.compat/verifier  -> converter/current
.compat/restricted -> source/restricted
.compat/core_gate -> validation/hard_replay
```

这样做是为了兼容 deterministic runner 的固定接口，不复制同一份 artifact。也因此，
直接把 `.compat/verifier` 当作普通目标目录复制，可能触发 symlink 相关的 artifact
错误；框架的 artifact handoff 必须解析并正确处理这些链接。

## 3. Docker、`/app` 和 `/workspace` 的关系

Docker 是“实际执行仓库测试和 verifier 的隔离运行时”。主机上的 workspace 负责保存
材料；Docker 容器负责在指定镜像中运行 NodeBB、Redis、Mocha 和测试命令。

一次典型 replay 可以抽象成：

```text
主机
┌────────────────────────────────────────────────────────┐
│ attempt_001/source       Base 或 Gold checkout         │
│ attempt_001/.compat/verifier  生成的 run.sh/verifier   │
│ attempt_001/source/restricted  selector 和 F2P/P2P     │
│ framework/p2p_runner.py  通用回放辅助程序              │
└───────────────┬────────────────────────────────────────┘
                │ Docker mounts
                ▼
容器
┌────────────────────────────────────────────────────────┐
│ /app                  当前被测仓库                       │
│ /app/verifier         当前生成的 verifier                │
│ /app/framework        容器内可用的通用 runner             │
│ /workspace/public     public task material               │
│ /workspace/restricted selector、历史测试                  │
│ /workspace/run        replay 输出和日志                    │
└────────────────────────────────────────────────────────┘
```

几个容易混淆的名字：

### `workspace`

通常指主机上的 attempt workspace；在容器中也可能指挂载点 `/workspace`。两者保存的
内容相近，但不是同一个进程空间：主机路径需要通过 Docker mount 才能在容器内看到。

### `app`

`/app` 是容器内的“当前仓库根目录”。它不是一个额外的应用，也不是 VerifierTrans
项目本身。对于 NodeBB，NodeBB 的代码、`package.json`、`test/` 等应该出现在这里。
生成的 `run.sh` 通常先进入 `/app`，再使用仓库相对路径运行 Mocha 或其他项目 runner。

### `verifier`

`/app/verifier` 是由 Converter 生成的功能检查入口，不等于被测 NodeBB 仓库。
它需要读取 `/app` 中的 public code/API，并通过 observable behavior 判断当前仓库是
否满足转换后的语义。

### `framework`

`/app/framework` 是 Hard Validator 的容器内辅助挂载点，不是 Converter 应该实现的
任务逻辑。执行适配层根据 `repo_language` 选择原生命令、cwd、mount 和服务启动方式：
Node 使用原生 Mocha selector runner，Python 使用 pytest runner，Go 使用 `go test`。
Converter 只生成“测什么”的 functional F2P；它不再生成 `run_p2p.*`、selector parser、
Docker 命令或 Redis bootstrap。这样 `/app`、`/workspace` 和 `/framework` 的关系由一个
确定性的 Hard Validator contract 管理，而不是由每个模型生成的 `run.sh` 决定。

### Docker image

镜像提供 Node、系统依赖、项目运行时以及可能的 Redis 等服务。镜像不是 verifier，
也不是 workspace；它只是创建容器时使用的基础文件系统和工具集合。

## 4. 从 Prepare 到发布的时序

### 阶段 A：Prepare / Preflight

Prepare 从 parquet 找到指定 instance，并准备：

1. Problem Statement、Requirements/Interface、Gold patch、Base patch 等材料。
2. Base checkout 和 Gold checkout。
3. F2P/P2P selector 的 canonical 解析结果。
4. 对应 Docker image、测试文件和基本 entrypoint 的检查。
5. `state.json`、`events.jsonl` 和 attempt 目录。

Prepare PASS 只表示“材料和基础环境准备可信”。它不表示 verifier 已经正确，也不
表示 Mocha、Redis 或全部测试节点已经成功执行。JS 环境当前可能只做基础存在性检查，
完整执行要等到 Hard replay 才能验证。

### 阶段 B：Converter BUILD

单一 Converter 在 BUILD 模式下可以查看完整仓库并按需探索。它逐条处理 historical
F2P，生成类似下面的 artifact：

```text
converter/revisions/rev_001/
├── run.sh
├── functional_f2p.js
├── p2p_nodes.txt
├── manifest.json
├── conversion_trace.json
├── conversion_log.md
├── coverage_matrix.md
├── instruction_scope.md
└── self_review.md
```

`conversion_trace.json` 是每条 F2P 的 accounting。一个 F2P 可以被 `keep`、`rewrite`、
`merge`、`drop` 或标记为 `spec_gap`，但不能无记录地消失。P2P 主要保留其 canonical
selector，作为回归证据。

### 阶段 C：Verifier sanity 和 Semantic Judge

首先由 deterministic sanity 检查 schema、文件、selector、manifest、trace、scope 和
`run.sh`。然后由 fresh Semantic Judge 检查：

```text
F2P intent 是否被覆盖？
是否转成了 public/observable behavior？
是否依赖 private helper、内部状态或 Gold 文件布局？
是否凭空增加了没有 F2P 支持的要求？
```

这里通过只说明 verifier 的“语义描述和 artifact 结构”基本可信，还没有证明它能在
容器里运行。

### 阶段 D：Hard Validator / deterministic replay

Hard Validator 才真正启动 Docker，分别准备：

```text
Base + verifier + F2P
Gold + verifier + F2P
Base + verifier + P2P
Gold + verifier + P2P
```

期望结果是：

```text
Base F2P  FAIL       Gold F2P  PASS
Base P2P  PASS       Gold P2P  PASS
重复执行结果稳定
```

F2P 的 Base FAIL 是预期的，因为 Base 尚未实现修复；Gold PASS 说明 verifier 能识别
修复后的 observable behavior。P2P 两边 PASS 说明转换没有破坏已有回归行为。

对 JS/TS 任务，P2P 必须由项目原生 Mocha/项目 runner 真正执行 test body。只收集节点、
生成空 `runtest`、或使用与项目无关的 Python synthetic collector，都不算 P2P 通过。

### 阶段 E：QA

Core gate 通过后：

- Positive Generator 生成结构不同但功能正确的实现；先 deterministic precheck，再交给
  Judge。合格 Positive 必须同时满足：converted F2P 通过、保留 P2P 通过，以及历史
  F2P 测试可运行但失败。最后一项是必要的多实现证据，证明候选不是只复现旧测试实现；
  Judge 必须给 `VALID`，且最新 revision replay 仍满足这三个结果。
- Negative Generator 生成只违反一个明确 F2P 语义的 near-correct mutant；同样先做
  deterministic precheck，再由 Judge 确认它是相关且非等价，最后 verifier 应拒绝。
- 每次 verifier revision 都要重放已有 QA evidence，不能只验证新 candidate。

### 阶段 F：Package

只有 core、QA、最新 revision replay 和 package smoke 全部通过，才生成
`final_task/`。中间的 `review/`、`.compat/`、trajectory、sealed evidence 不应进入
最终任务包。

## 5. 为什么会出现“看起来执行上的问题”

整个系统跨越四种边界：

```text
模型输出的文件
    ↓ artifact/schema/path
主机 workspace
    ↓ Docker mount
容器内 /app、/workspace、/framework
    ↓ 项目 runner、依赖、Redis、selector
真实测试执行
```

任一边界出错，结果都可能表现为“verifier 没通过”，但修复位置完全不同。

### 典型问题一：selector accounting 不一致

数据集中的原始 selector 可能带有文件前缀或 suite 描述，而 Prepare 解析后使用的
canonical ID 可能只有 `file::test title`。如果 Converter 的 trace 使用前者、sanity
使用后者，verifier 内容可能完全合理，但 artifact schema 会失败。

解决办法是让 manifest、trace、coverage matrix 统一使用 Prepare 输出的 canonical
selector；不能为某个任务硬编码字符串。

### 典型问题二：symlink 或 snapshot 复制错误

`.compat/verifier` 是指向正式 revision 的 symlink。通用复制函数如果把它当成普通
目录目标，可能得到 `FileExistsError`；Converter 的 app workspace 如果包含指向仓库
的 symlink，普通递归复制还可能把整个仓库或 `.deps/node_modules` 复制进 live snapshot，
导致卡住或 artifact 膨胀。

这类问题发生在 artifact handoff 或 snapshot 层，不能让 Converter 修改 verifier 语义。

### 典型问题三：相对路径和 mount 不一致

`run.sh` 在 `/app` 中执行 `python3 framework/p2p_runner.py`，但 replay 只挂载了
`/workspace/framework/p2p_runner.py`，就会得到：

```text
python3: can't open file '/app/framework/p2p_runner.py'
```

这是 replay contract 问题，不是 NodeBB 代码问题。通用修复应统一 `/app`、`/workspace`
和 framework runner 的布局，并把缺少 runner 明确分类为 infrastructure。

### 典型问题四：Docker daemon 或 image 不可用

即使 Prepare 发现了 image 名称，后续 Hard Validator 仍可能因为：

- 当前进程没有访问 `/var/run/docker.sock` 的权限；
- Docker daemon 不可用；
- image 没有在当前 Docker context 中加载；
- image tag 包含不合法的大写或与实际 tag 不一致；
- bind mount 路径不可见；

而无法创建容器。这时四组 replay 通常同时失败，`verifier_runnable` 为 false，不能
据此修改 verifier。应先修复执行权限、image materialization 或通用 image resolver。

### 典型问题五：运行时服务没有启动

NodeBB image 可能包含 Redis，但 entrypoint 不一定自动启动 Redis。verifier 或原生
Mocha 测试遇到连接失败时，问题在 runtime bootstrap；通用 replay 可以在镜像提供
命令且服务未 ready 时启动并等待 Redis。不能通过删掉依赖 Redis 的 F2P 来“修复”结果。

### 典型问题六：模型生成了假 P2P runner

一个 Python collector 即使返回成功，也可能没有执行任何 JS test body。对 NodeBB，
这是 verifier artifact / execution contract 失败，而不是合格的 P2P PASS。Prompt 和
deterministic checks 必须要求 native Mocha/project runner，并核对每个 selected node
确实被执行。现在 sanity 会拒绝 `run_p2p.*`、`p2p_runner.*` 等模型生成的 runtime
文件，Hard Validator 统一从 execution adapter 提供 runner。

## 6. 如何根据证据判断该修哪里

不要只看最后的 `accepted=false`。按下面顺序看：

```text
state.json / events.jsonl
        ↓ 当前阶段
sanity JSON
        ↓ artifact/schema 是否正确
semantic review
        ↓ F2P 语义是否合理
hard_replay/latest_check.json
        ↓ Docker、Base/Gold、F2P/P2P、稳定性
qa/evidence.json
        ↓ alternative/mutant 是否合格
packaging/package_report.json
        ↓ smoke 和 final_task
```

粗略分类：

| 现象 | 应归类 | 优先修复位置 |
| --- | --- | --- |
| selector 未 accounting、manifest 与 trace 不一致 | artifact/schema | Converter contract 或 sanity/framework |
| `/app/framework/...` 不存在、mount 缺文件 | infrastructure | replay mount / runner contract |
| Docker socket denied、image 不存在 | infrastructure | Docker 权限、image 准备、通用 resolver |
| verifier 能运行但 Base/Gold 结果不符合语义 | verifier semantic | Converter REPAIR |
| Semantic Judge 指出 overreach/private helper coupling | verifier semantic | Converter REPAIR |
| 合格 Positive 被拒绝 | false negative / verifier semantic | 先确认 candidate precheck，再 REPAIR |
| 不合格 Negative 被接受 | false positive / verifier semantic | 先确认 mutant 语义，再 REPAIR |
| package smoke 失败 | packaging/infrastructure | package runner、路径或 artifact |

重要原则是：如果四个 Base/Gold replay 在容器创建之前就同时失败，不应让模型重新
生成 verifier；如果只有 Gold F2P 或某一组功能结果错误，才进入 verifier 语义诊断。

## 7. 当前 NodeBB-049989 实例的证据

当前任务是：

```text
instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan
```

Prepare 已通过，3 条 historical F2P 和 288 条 P2P selector 已解析。早先 rev1 的一轮
执行曾到达 verifier sanity 和 Semantic Judge；首个 P2P 错误是 `/app/framework/p2p_runner.py`
挂载契约问题，已经作为通用 framework issue 记录和修复。

rev2 的 Hard replay 证据已达到：

```text
Base F2P FAIL / Gold F2P PASS / Base-Gold P2P PASS
```

但 rev2 的 Positive 只有 P2P 和 Judge 证据，converted F2P 复核为 FAIL，且没有历史
F2P failure evidence，因此按新的 QA contract 不合格，该 candidate 不会被沿用。

之后 rev3 的 Hard replay 暴露出模型仍提交了 `run_p2p.js`。这属于 artifact execution
contract 违规，已路由为 Converter REPAIR；修复后必须重新执行 Semantic Judge、Hard
Validator 和全部 QA。

更早的一次 resume 的 Hard replay 证据显示四组 replay 都是：

```text
container_exit_code: 126
failure_cause: docker_unavailable
verifier_runnable: false
```

日志的直接原因是 Docker socket permission denied。这个结果不能证明 rev1 verifier
语义错误；它只证明本次运行上下文没有完成容器启动。提升权限后 Docker daemon 可以
响应，任务镜像也已在当前 Docker context 中 materialize；该基础设施问题已单独记录，
不能污染 verifier 语义判断。

因此当前还不能声称任务已完成，也不能把这次 infrastructure failure 计入：

```text
Base F2P FAIL / Gold F2P PASS / Base-Gold P2P PASS
```

这些 gate 必须在 Docker 可用后重新得到真实 replay 证据。

## 8. 一组最小排查命令

以下命令只读，不输出 `.env` 内容：

```bash
cd /lg-home/cog8/lwli6/VerifierTrans

# 当前状态和阶段
cat runs/<INSTANCE_ID>/intermediate/attempts/attempt_001/control/state.json
tail -20 runs/<INSTANCE_ID>/intermediate/attempts/attempt_001/control/events.jsonl

# Hard replay 的机器证据
cat runs/<INSTANCE_ID>/intermediate/attempts/attempt_001/validation/hard_replay/latest_check.json

# 只检查 Docker daemon 和镜像，不删除或启动容器
docker version
docker image ls
```

若 `state.json` 显示 `CONVERTING` 但没有活跃 agent 进程，不能把它当作成功；这是
中断后的 stale state，应查看最后一个 event 和 trajectory，再用 `resume` 继续。若状态
为 `INFRASTRUCTURE`，先读取 replay log；若为 `SEMANTIC_VERIFIER`，再读取 Semantic
Judge/Hard Validator 反馈并让同一 Converter 进入 REPAIR。

## 9. 最终验收条件

“生成了 verifier”不等于“任务转换成功”。必须同时有以下证据：

```text
Prepare PASS
所有 historical F2P 有明确 accounting
Semantic Judge PASS
Hard Validator PASS 且稳定
Base F2P FAIL、Gold F2P PASS
Base/Gold P2P PASS
至少一个 VALID Positive 通过
至少两个合格 Negative 被拒绝
最新 revision 重放所有 QA evidence 仍通过
package smoke PASS
final_task/ 成功发布
```

只要其中一项缺失，`final_task/` 就不应被视为可交付结果。
