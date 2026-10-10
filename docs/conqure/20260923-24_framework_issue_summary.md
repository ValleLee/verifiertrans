# VerifierTrans 框架问题与修复总结（2026-09-23～24）

## 1. 文档范围

本文只总结 `VerifierTrans/process` 中 2026 年 9 月 23 日和 24 日记录暴露出的**框架性问题**，并说明对应的通用修复。记录中的 Tutanota、qutebrowser、element-web、navidrome 等实例只是问题的触发场景；修复不能依赖某个仓库、测试名、文件名或候选实现。

本总结的事实来源包括：

- 23 号各条 `framework_*`、`infrastructure_*` 记录，以及少量用于说明分类边界的实例记录；
- 24 号 Judge、Node/Jest 和超时记录；
- `20260923T_framework_architecture_convergence.md` 的架构收敛记录。

## 2. 总体结论

这两天发现的多数问题不是“某个 verifier 写错了”，而是同一任务在不同阶段没有共享同一套事实来源：Prepare、Hard Replay、Candidate、QA、Package 对 runner、路径、selector、服务、产物和证据各自做了推断。修复的主线因此是收紧契约：

```text
Prepare 冻结唯一 ExecutionSpec
        ↓
所有 replay / QA / package 只消费冻结事实
        ↓
manifest 明确声明 verifier artifact
        ↓
状态、证据和 contract version 可恢复、可审计
        ↓
Semantic Judge 只判断语义，确定性 replay 只判断执行结果
```

最终可以归纳为六类问题：

1. 执行契约碎片化；
2. 产物、路径和来源边界不清；
3. 控制器与证据生命周期不完整；
4. Verifier 可能被 Gold、mock 或 runtime shim 绑定；
5. 基础设施、模型传输和超时边界不清；
6. 通用框架退化为实例特判的风险。

---

## 3. 分类总结

### 3.1 执行契约碎片化（Execution Contract Fragmentation）

#### 发现了什么

- Prepare 已经发现了 runner、cwd、module root、selector、服务和超时，但 replay/candidate/package 仍会重新 discovery 或自行拼命令。
- Node functional artifact 曾直接执行 `node /app/verifier/<artifact>`，绕过冻结的 Jest/TypeScript `ExecutionSpec`；Jest 因此在加载 `.tsx` 前就失败。
- ospec runner 一度没有传入构造好的环境，随后又从仓库根目录启动，导致项目相对导入失败。
- Go 的 bare selector 被当成文件路径；Docker 中用 `bash -lc` 又重置了镜像提供的 PATH，遮蔽了 `/usr/local/go/bin/go`。
- Candidate 使用 `cp -a` 保留 solver uid/gid，目标镜像中不存在该 uid 时，原生测试在断言前失败。
- Docker mount、`/app`、`/framework`、artifact cwd、服务启动和结果解析在不同阶段有旁路；Prepare 能通过不代表 candidate replay 能通过。

#### 如何修复

1. **冻结并复用 `ExecutionSpec`**：增加 `from_dict` 和稳定 hash；把 runner、cwd、module root、loader、selector、service、timeout、startup timeout、kill grace、result parser 都纳入 spec。replay、candidate、package smoke 只消费冻结 spec。
2. **统一走原生 runner**：Jest 使用 package manager 的 `--runInBand --runTestsByPath`，Vitest 使用 native `run`，ospec 传递显式 env 并在项目要求的 cwd 启动；保留 Mocha 等已有兼容路径，但不能越过 spec。
3. **修正跨语言 preflight**：Go bare selector 从 `original_test.patch` 的文件头解析具体测试文件；镜像命令改用 `bash -c` 保留 PATH；包发现使用 `go list -buildvcs=false ./...`，不要求被复制仓库带有 `.git`。
4. **统一容器和文件语义**：mount 顺序固定，artifact 的本地 import 按 `/app` replay 布局静态检查；执行时导出 `VERIFIER_REPO_ROOT`、`VERIFIER_ARTIFACT_ROOT`、`VERIFIER_CWD`；候选源码复制不保留外部 uid/gid。
5. **限制服务和依赖边界**：只启动 spec 声明的服务，未知服务显式失败；Positive QA 和 Converter 禁止联网安装依赖。
6. **让超时能杀掉容器内子进程**：Docker 命令同时使用 host timeout 和容器内 `timeout/kill-after`，避免 host 客户端中断后留下后台下载或测试进程。

#### 证据与状态

- 23 号 ospec、Go、候选 uid、artifact path 等修复分别有执行适配器和 orchestrator 回归测试。
- 24 号 Node/Jest functional runner 修复后，adapter/judge parser 相关测试达到 18 passed；Jest namespace root 修复有 16 个 deterministic adapter 测试通过。
- 架构收敛记录报告 `compileall` 通过、全量回归 130 passed；但尚未用 fresh Docker E2E 为所有 Node/TS/Go adapter 给出完整支持保证。

---

### 3.2 产物、路径与来源边界不清（Artifact & Provenance Boundary）

#### 发现了什么

- manifest 的 `test_files` 曾允许 bare string，`functional_artifact` 又没有成为显式声明；Package 因此会扫描 `functional_f2p.*` 或 verifier 目录来“猜”入口。
- source selector、resolved selector、主机路径、容器路径、Converter workspace 和最终 artifact 的身份混用。
- 绝对路径或错误的相对 import 可以通过 schema/self-review，却在 `/app/verifier` 的真实 replay 布局中解析到 `/src` 等错误位置。
- symlink、`node_modules`、`tmp_*`、缓存和实验包曾可能随快照进入 verifier；历史 test patch 也可能被 package 误带入。
- Converter 中断或 repair 后，部分 payload、packet 和正式 revision 的边界不清。

#### 如何修复

1. **manifest 成为 artifact 的唯一声明**：显式要求 `functional_artifact`/`functional_entrypoint`、typed `{source, target}` 的 `test_files`、fixtures 和入口；Sanity 在 Judge/Hard Replay 之前拒绝缺失或未声明文件。
2. **停止目录扫描式 discovery**：Package 机械消费 manifest 和 Prepare 产出的 `restricted/p2p_assets.json`；不再用 `functional_*` 命名或顶层源码扫描推断 verifier。
3. **建立运行时路径契约**：以 `/app` 为 repo root、`/app/verifier` 为 artifact root，静态检查 local import 是否越出 root、目标是否存在，并把同一规则写进 Converter prompt。
4. **隔离 scratch 与正式 output**：Converter workspace 将探索文件放进 `scratch/`，只有 `output/` 进入 revision；快照、复制和清理保留 symlink、剪除依赖/缓存/临时目录。
5. **保留来源追踪但不混用语义**：raw selector 只作为 provenance，manifest/trace 使用 canonical resolved selector；Package 的 P2P 文件和 shared fixture 由 derived asset list 机械消费，歧义记录到 package report。
6. **修复交接 schema，而不是放宽校验**：repair packet 将 manifest schema 错误转换为明确的 typed-artifact 指令，Sanity 仍是权威门禁，不静默接收 malformed artifact。

#### 证据与状态

- qutebrowser 的 manifest 修复记录给出 `test_orchestrator_state.py: 8 passed`。
- 架构收敛记录报告 manifest、asset list、scratch/output 和 path-contract 已进入主路径；旧 adapter 的无 manifest/spec 兼容分支仍只用于读取旧 runs。

---

### 3.3 控制器与证据生命周期不完整（Control & Evidence Lifecycle）

#### 发现了什么

- Candidate payload 已经写入磁盘，但模型没有发出 `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` 时，控制器直接丢弃 payload。
- Positive evidence 的 contract version 变化后，旧 evidence 仍可能进入 active list，导致 resume 跳过当前 contract 所需的重验证。
- 多个 controller 可同时操作同一个 attempt；Converter lock 不能阻止 QA 或 report/state/events 被另一进程覆盖。
- 中断后只保留 immutable revision 和 QA evidence，内存中的 `repair_packet` 消失；resume 不知道应继续 QA 还是启动 Converter REPAIR。
- Positive contract 曾在 00:37 的中间修复中把“历史 F2P 必须失败”误设为硬门槛；01:53 的 v4 修复按冻结计划将历史 F2P 恢复为 audit-only，并要求当前 F2P 与 retained P2P 作为硬门槛。这个过程说明 contract version 必须是可执行门禁，而不能只是日志说明。

#### 如何修复

1. **中断可恢复**：只要 candidate 目录有非空 payload，即使没有 sentinel 也交给 deterministic precheck；没有 sentinel 且没有 payload 才报错。不伪造 completion signal。
2. **版本化 evidence**：只有当前 `POSITIVE_CONTRACT_VERSION` 的 evidence 进入 active list；旧版本保留作审计，并按名称重新验证，不能直接满足当前目标。
3. **attempt 级 controller lease**：增加 `controller_session.lock` 覆盖完整 controller 生命周期；`KeyboardInterrupt` 写入显式 `INTERRUPTED` state/event，再允许 resume 区分中断和活动进程。
4. **持久化 repair handoff**：增加 `--repair-packet PATH`，验证 JSON、记录 `REPAIR_REQUESTED`，并强制新 revision 进入 Converter REPAIR；修复意图不再依赖单次进程内存。
5. **分层 Positive 状态机**：
   - `candidate_positive`：候选可运行、P2P 通过、当前 F2P 有可判定结果、结构上不是 exact Gold；
   - `validated_positive`：Solution Judge 判定语义有效；
   - accepted positive：validated candidate 再通过当前 F2P 和 P2P replay。
   当前 F2P 的 runnable semantic failure 仍可进入 Judge；只有 Judge 有效且 replay 失败才发出 `VERIFIER_FALSE_NEGATIVE` 并进入 Converter REPAIR。基础设施失败和候选无效不触发 verifier repair。

#### 证据与状态

- QA dependency/payload recovery 回归分别为 9 passed、10 passed。
- Positive contract、controller lease、stale evidence 和状态机测试达到 21 passed、24 passed 等 targeted suites。
- v4 的最终语义是：历史 F2P 是 comparative audit evidence；当前 converted F2P 与 retained P2P 才是 acceptance hard gates。

---

### 3.4 Verifier 语义独立性不足（Semantic Validity / Acceptance Breadth）

#### 发现了什么

- Exact Gold post-image 在 structural precheck 之前可以直接进入 Judge，Positive QA 因而可能接受“复制 Gold”而不是不同实现。
- Tutanota 的 verifier mock 只提供 Gold 使用的 DOM 路径：缺少 `documentElement`、`nodeName`，随后又发现缺少 `parentNode`、`childNodes`、`removeChild`、`textContent`、`setAttribute`、`insertBefore`、`querySelector`/`querySelectorAll` 等标准 API。
- `verifier.cjs` 剥离 TypeScript import、注入固定 globals/runtime shim；等价实现只要采用普通 module import 或标准 runtime API，就可能在断言前失败。
- 因而“Gold 通过、候选失败”不一定是候选错误，也可能是 synthetic runtime 将可接受实现空间缩窄了。

#### 如何修复

1. **Exact Gold 结构门禁**：只把 Gold patch 应用到其 touched baseline files；若候选 payload 在相同 Gold paths 上形成完全相同 post-image，则 deterministic precheck 拒绝，不调用 Judge。相同文件但内容不同仍允许进入 Judge。
2. **建立 mock/fixture coupling taxonomy**：新增 `Mock/Fixture-Induced Implementation Coupling` 和 `Transpiler/Runtime-Shim-Induced Implementation Coupling`，并将其加入 Converter 与 Semantic Judge checklist。
3. **按 public runtime contract 修复 harness**：补足实现说明所需的最小标准 DOM/query/mutation 行为，或使用真实 runtime；禁止用 Gold-shaped helper、task-specific selector 或 no-op collector 掩盖缺陷。
4. **让 QA 识别 false negative**：Solution Judge 负责判断候选是否满足 public behavior，deterministic replay 负责报告 verifier PASS/FAIL；两者组合成 false negative/true rejection 等结果。
5. **证据进入统一 REPAIR**：确认是 verifier/harness 缺陷时，使用持久化 repair packet 进入单一 Converter REPAIR，并在新 revision 上重跑全部历史 QA evidence。

#### 证据与状态

- 23 号 semantic validation layering targeted suite 为 24 passed；exact Gold 与 same-file-different-content 均有结构回归覆盖。
- Tutanota 的 DOM 审计从 Rev1 到 Rev3 连续暴露二阶 mock/runtime coupling；Rev4 修复和后续 Semantic Judge、replay、QA 结果在记录中仍 pending，不能把该实例描述成已闭环。
- 23 号 Tutanota attempt_015 中三次候选的 current functional F2P 断言失败属于 data-specific candidate semantic failure；它们没有自动触发 verifier repair，不能与 mock 缺陷混为一类。

---

### 3.5 基础设施、模型传输与超时边界（Infrastructure Boundary）

#### 发现了什么

- Positive solver 重复运行 `npm install`，host-side Docker exec 超时后容器内子进程仍存活，既浪费网络/API预算，也可能被同一 QA session 再次启动。
- Docker daemon 权限为 126 时，任务尚未进入 Converter，却可能被错误地当作 verifier 失败。
- 模型 key 对 Luna High 返回 403 `key_model_access_denied`；Prepare 已通过，但没有产生任何 verifier evidence。
- Judge provider 返回 prose、fenced JSON 或多个 JSON object 时，旧 parser 从第一个 `{` 截到最后一个 `}`，触发 `Extra data`；element-web Judge 的两次 300 秒请求也未产生执行或 artifact 结果。

#### 如何修复

1. **分层记录基础设施失败**：Docker、image、endpoint、runner、service、命令 timeout 和 model authorization 在 Prepare/执行层停止，不生成新的 verifier revision，也不路由到 semantic repair。
2. **禁止 QA/Converter dependency fetch**：使用 prepared image/repository toolchain；命令增加容器内 kill-after，host timeout 不再是唯一终止手段。
3. **Judge JSON 容错但保持不确定性失败**：使用 `JSONDecoder.raw_decode` 按边界解码；多对象时优先选择含 `verdict` 的对象，或选择符合 semantic schema（`findings`、`unconverted_f2p`、`overreach`、`mapping_gaps`）的对象；没有唯一可判定对象仍保持 infrastructure error，并保留原始响应和 usage accounting。
4. **扩大共享模型 request timeout**：`configs/experiment.yaml` 从 300s 调整为 600s，保留既有 retry 和 acceptance gate；这是共享 transport 配置，不是实例特判。

#### 证据与状态

- QA command timeout 回归 9 passed；Judge parser 在初始 3 passed 后补充到 4 passed。
- 24 号 adapter/judge parser 相关测试达到 18 passed。
- Luna High 403 和 Docker 126 记录均被保留为 infrastructure audit evidence；它们不代表仓库、selector 或 verifier 语义问题。

---

### 3.6 通用化边界：避免从框架退化为特判集合

#### 风险

23 号记录中有许多实例触发点：Tutanota 需要 DOM mock 审计，Node 项目需要 Redis/ospec/Jest，navidrome 暴露 Go PATH，qutebrowser 暴露 manifest schema。若逐条加入“遇到某个仓库就走某个命令”的分支，框架会从可迁移的转换系统退化成 pilot task 的特判集合。

#### 已采用的修复原则

- 先判断失败属于 `INFRASTRUCTURE`、`ARTIFACT`、`VERIFIER_SEMANTIC` 还是 `CANDIDATE_SEMANTIC`，再决定修改层次。
- 将实例证据提升为缺失的抽象：ExecutionSpec、native execution adapter、manifest、controller lease、contract version、repair packet、runtime coupling taxonomy。
- 所有路径、selector、runner 和 service 规则使用数据驱动或 repository-native discovery；不写 Tutanota、element-web、某个测试标题或某个 verifier 文件名的特判。
- 对尚无完整 E2E 证据的能力只记录为“adapter 已实现/有单元测试”，不宣称语言生态已经 supported。

#### 当前边界

这套原则已经用于 23/24 号修复，但仍需 fresh Docker E2E 验证 Node/TypeScript/Go 的完整跨阶段一致性；不能仅凭 unit tests 或旧 runs 推断所有环境均已支持。

---

## 4. 记录到问题类别的对应关系

| 日期记录 | 归类 | 核心问题/修复 |
| --- | --- | --- |
| `20260923T000642` | 执行 / 基础设施 | 禁止 QA 安装依赖；host + container 双层 timeout。 |
| `20260923T001934` | 控制与证据 | 已落盘 payload 即使缺 sentinel 也进入 deterministic precheck。 |
| `20260923T002318` | 执行 | 复制候选时不保留 solver uid；`uv_os_get_passwd` 归为 infrastructure。 |
| `20260923T002417`、`003251` | 执行 | ospec 显式传 env，并使用正确 harness cwd。 |
| `20260923T003739`、`003948`、`015319` | 控制与证据 | Positive contract、stale evidence、controller lease；最终以 v4 定稿。 |
| `20260923T030851`、`032704` | 产物 / 语义 | artifact path-contract；exact Gold structural precheck。 |
| `20260923T034423` | 实例证据 | 候选 current F2P 语义失败，未判为框架缺陷。 |
| `20260923T041421` | 基础设施 | Docker 权限失败在 Prepare 阶段停止，不进入 Converter。 |
| `20260923T055000`、`062600`、`065319` | 语义 | DOM mock、query API、runtime shim coupling；统一走 REPAIR。 |
| `20260923T060000`、`062429` | 控制与证据 / 语义 | repair packet；candidate/validated/accepted 三层 Positive 状态机。 |
| `20260923T061500` | 语义 | 将 mock/fixture coupling 固化为通用 taxonomy 和 prompt checklist。 |
| `20260923T164248` | 产物 | typed manifest repair handoff；Sanity 仍为权威门禁。 |
| `20260923T210800` | 基础设施 | 模型授权失败保留为 audit evidence，恢复到 key-authorized model。 |
| `20260923T215805` | 执行 | Go selector、PATH、`go list -buildvcs=false` 的通用修复。 |
| `20260923T_framework_architecture_convergence` | 全局收敛 | 冻结 ExecutionSpec、显式 manifest/P2P assets、scratch/output、negative execution contract。 |
| `20260924T001000` | 基础设施 / Judge | `raw_decode` 提取唯一 schema-shaped verdict，保留原始响应。 |
| `20260924T011900` | 执行 | Jest/Vitest functional artifact 使用冻结 native runner。 |
| `20260924T024800` | 基础设施 | Semantic Judge request timeout 从 300s 调至 600s。 |
| `20260924T_jest_verifier_namespace_root_contract` | 执行 | manifest target 在 `verifier/` 时增加通用 Jest `--roots /app` 与 `--testMatch`。 |

---

## 5. 当前完成度与剩余风险

### 已经落地的框架能力

- `ExecutionSpec` 已能序列化、反序列化并以稳定 hash 识别；主路径开始统一 runner、cwd、服务和超时。
- manifest、typed artifact、P2P derived asset list 和 artifact path-contract 已成为新的正式边界。
- Positive QA 已区分候选无效、基础设施失败、Verifier false negative，并支持跨中断 repair handoff。
- exact Gold structural precheck、mock/fixture coupling taxonomy、Judge JSON fallback 已加入确定性测试。
- 架构收敛记录的静态编译通过，全量回归为 130 passed。

### 仍未闭环的事项

- 没有 fresh Docker E2E，不能据此把所有 Node/TypeScript/Go adapter 宣布为完整 supported。
- Tutanota DOM/runtime-shim 的 Rev4 及其后续 Semantic Judge、Hard Replay、QA 结果仍待记录闭环。
- 旧 runs 的兼容 adapter 分支仍保留；新 package 主路径会在进入 adapter 前拒绝无 manifest/spec 的旧形状。
- replay/candidate 的部分历史 role mount 兼容路径尚未做大规模清理；这属于下一轮无语义变化的收敛工作。

## 6. 一句话结论

23～24 号优化的核心不是继续为某个 verifier 加断言，而是把框架从“多个阶段各自猜测如何执行和如何识别产物”收敛为“一个冻结执行契约、一个显式 artifact 声明、一套可恢复的证据状态机，以及对 public behavior 足够宽容的 verifier runtime”。
