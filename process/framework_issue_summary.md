# VerifierTrans 框架问题与修复总结

## 总览

`process/` 中记录的问题，绝大多数不是某个仓库或 verifier 逻辑错误，而是框架在“准备、执行、产物交接、恢复、QA 判定和证据分类”上的契约不完整。总体修复方向是：

> 把任务语义交给 Converter，把路径、运行器、挂载、服务、超时、状态和证据判定收回到确定性的框架层。

## 1. Prepare、源码与 selector 路径契约

**问题**

- Prepare 只检查目录是否存在，可能把 Docker 失败后的 stale 目录误判为已物化仓库。
- selector 中的 `/app`、`/workspace`、`test/tests`、`.js/.ts/.jsx/.tsx` 等逻辑路径与 checkout 实际路径不一致；目录扁平化还会导致大量误报 missing file。
- 为每个 selector 重复递归扫描仓库，启动很慢；Node 预检直接挂载 host 源码又遮蔽了镜像内的 `node_modules`。
- Docker 权限、镜像不存在、预检代码回归等基础设施失败曾被混入后续语义流程。

**修复**

- Prepare gate 同时校验 materialization 返回码、HEAD/base commit、repo link 和目录状态；Docker/image 权限不可用时在 Converter 前停止并标记 infrastructure。
- 统一 `normalize_repo_path`、扩展名 alias、`test/tests → test` 规则和唯一 basename fallback；建立一次性 basename 索引缓存，歧义时不猜测。
- 预检改为向容器提供 `/source`，再复制到镜像 `/app`，保留镜像依赖；所有 replay 共用同一 resolved selector。
- 增加源清单、dataset-row、instance layout 校验，防止静默替换源码。

## 2. 执行适配、Docker replay 与运行时

**问题**

- JavaScript/TypeScript 曾被错误地用 Python P2P runner 执行；框架 runner 挂载在错误路径，或 Docker mount 被放到 image 之后而根本未生效。
- F2P/P2P、candidate replay、package、Prepare 各自拥有不同的 cwd、入口和挂载契约；候选常因 `/framework`、`/app/framework` 不一致而被误判失败。
- Node runner 错选 `tsx`、逐 selector 启动进程、Jest 标题格式不匹配，甚至“进程成功但一个测试也没执行”；ospec 的环境变量和 cwd 也曾错误。
- NodeBB 所需 Redis 未启动；原生 TypeScript 冷启动超过统一 120 秒预算。

**修复**

- 引入 repository-native `ExecutionSpec`，统一发现语言、runner（pytest/Mocha/Jest/Vitest/ospec/Go）、cwd/module root、loader、服务和支持状态。
- 所有 replay 统一走 deterministic execution adapter：使用原生 runner，框架负责 mounts、cwd、环境变量和 Redis readiness；mount 一律位于 Docker image 之前。
- Node selector 按文件批量执行，规范化层级标题，并校验 JSON 报告中每个目标确实以非 pending 状态执行；Jest/Vitest 不再注入无关 `tsx`。
- 支持项目自带 ospec harness，修正其 env 传递和 `test/` cwd；原生 replay 超时预算提升为 300 秒并保持有界。

## 3. Verifier 产物、Converter 边界与交接

**问题**

- symlink 形式的 `.compat/verifier`、scratch `app` 链接和临时依赖在 `copytree` 时被递归展开，导致提交/快照卡死或 `FileExistsError`。
- Converter 可把 `node_modules`、`tmp_*`、实验包、完整第三方依赖带进 verifier；也可能只提交 `run.sh`，没有真正的功能测试源文件。
- Converter 曾使用绝对路径、扫描 vendor/build 树、联网下载依赖，消耗 action/API 预算却没有形成 revision。
- step-limit 或中断后，部分有效产物和 repair packet 丢失；旧 packet 还可能污染已经成功的 revision。

**修复**

- 统一 symlink-preserving、scratch-filtered 的快照/交接/清理逻辑；过滤 `tmp_*`、依赖、缓存和归档，并改用剪枝式遍历。
- `validate_verifier` 强制要求真实功能源文件、静态 import/path 可在 `/app` replay 布局下解析；执行适配器按 `functional_*` 前缀发现功能文件，`run.sh` 仅作兼容入口。
- Prompt 明确禁止绝对路径、生成目录深挖和 `npm/pip/go/cargo` 外部依赖抓取，要求先提交最小可执行 verifier。
- 失败 BUILD 的部分 staging 被提升到下一次单一 Converter REPAIR；repair packet 持久化、可由 `--repair-packet` 注入；成功 sanity 后清空旧 packet。

## 4. Selector、覆盖率与打包会计

**问题**

- Converter 把原始 dataset selector 写入 manifest，而验证器要求的是 canonical resolved selector，导致合法产物在语义判断前就失败。
- Semantic Judge 只看到 source selector，看不到 source→resolved 的一一对应关系。
- final package 曾无条件携带完整历史 test patch，混入 F2P-only 内容。

**修复**

- 明确 raw source 仅作 provenance，manifest/trace 必须使用 resolved ids；deterministic sanity 继续作为权威会计检查。
- Judge 同时接收 `fail_to_pass_source` 与 `fail_to_pass_resolved`，允许路径规范化但要求意图保持。
- package 按 resolved P2P selector 保留 P2P 文件、共享 fixture 和必要 hunk，排除 F2P-only 内容，并生成 `package_report.json` 记录每项决策。

## 5. Positive/Negative QA 与控制器状态机

**问题**

- Positive QA 早期把“当前 F2P 必须通过”当成进入 Judge 的前置条件，无法识别 verifier false negative。
- 历史 Positive evidence 的 contract version 变化后仍可能被计入目标；controller 可并发写同一 attempt；中断后状态和 repair 意图不明确。
- 候选的 infrastructure failure（runner 缺失、uid、依赖命令超时）曾被当作语义失败，造成重复生成候选。
- Gold exact copy 曾可进入 Judge；候选 payload 已落盘但缺少 solver sentinel 时会被丢弃。

**修复**

- Positive QA 分层为 `candidate_positive → validated_positive → accepted positive`：当前 F2P 语义失败仍可交 Judge，Judge 判定有效后才路由 `VERIFIER_FALSE_NEGATIVE` 到单一 Converter REPAIR；历史 F2P 最终按 v4 合同仅作审计证据。
- 所有 evidence 带 contract version；旧 evidence 只保留审计并重新验证，不能直接满足当前目标；增加 exact-Gold structural precheck。
- 增加 attempt 级 `controller_session.lock`、显式 `INTERRUPTED` 状态、持久化 `--repair-packet`，避免并发覆盖和中断后丢失修复意图。
- candidate replay 不保留 solver uid，区分环境失败与语义失败；复用仅因 deterministic infrastructure 失败的既有候选；已有 payload 即使没有 sentinel 也可进入 deterministic precheck。

## 6. 语义 verifier 的 mock/fixture 耦合

**问题**

语义 Judge 发现某些 verifier 虽能通过 Gold，却把 mock DOM、sanitizer、TypeScript transpiler/runtime shim 做成 Gold 专用实现：缺少 `parentNode`、`removeChild`、`textContent`、`querySelector(All)` 等标准 API，或固定剥离 import、注入少量全局变量，导致等价实现尚未到达断言就抛错。

**修复**

- 新增 `Mock/Fixture-Induced Implementation Coupling` 与 `Transpiler/Runtime-Shim-Induced Implementation Coupling` 分类和审计清单。
- Converter/Judge 必须枚举可观察的公共 runtime contract，优先使用真实 runtime 或实现足够完整、行为中立的标准 API；禁止用 Gold-shaped helper、task-specific selector 或 no-op collector 掩盖问题。
- 相关证据统一进入通用 Converter REPAIR，而不再误判为 candidate 或 Docker failure。

## 7. 外部模型/API 与超时分类

**问题**

- Semantic Judge 请求因携带完整 P2P 清单而过大，连续 300 秒超时；模型 endpoint 可连通但推理不返回。
- Converter/QA 的 host timeout 未必能杀掉容器内子进程，依赖下载可能在后台继续。

**修复**

- Judge 只接收 F2P 语义证据和 P2P 摘要，完整 P2P 会计留给 deterministic 层；超时保留 immutable revision，按 infrastructure 重试，不生成新 revision。
- Docker 命令增加容器内 timeout/kill-after；QA/Converter 禁止联网装包，并将 endpoint、Docker、候选、语义失败分层记录。

## 8. 架构收敛结果与未闭环项

- 已形成统一的 `ExecutionSpec`、instance-centric `source/intermediate/review/final_task` 布局、确定性 package accounting 和 Positive QA 合同。
- 两条 Python 转换（qutebrowser、OpenLibrary）已完成 `VERIFIED / PACKAGED`，证明基础 replay、QA 和打包闭环可复用。
- 多数框架回归已由单元测试覆盖；旧 runs 通过 resolver 兼容读取，不做物理迁移。
- 仍需注意：最新 Tutanota DOM/runtime-shim 审计已识别到 Rev4 修复路径，但后续 Semantic Judge、replay 和 QA 结果在记录中仍待完成；Node/TS/Go 的完整 Docker 交叉验证也属于后续验证项。

## 一句话结论

这轮工作的核心不是“不断修改某个 verifier”，而是持续收紧框架契约：准备阶段证明拿到的是正确源码，执行阶段证明跑的是正确原生测试，产物阶段证明提交的是可运行且边界清晰的 verifier，QA 阶段证明候选和证据没有被基础设施或旧状态污染，语义阶段则确保 verifier 检验的是公共行为而不是 Gold 的实现细节。
