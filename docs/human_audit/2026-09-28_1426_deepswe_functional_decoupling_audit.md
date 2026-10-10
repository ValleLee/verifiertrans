# VerifierTrans 功能性测试与 instruction 解耦审计

- **审计时间**：2026-09-28 14:26（Asia/Shanghai；对应 06:26 UTC）
- **审计范围**：Deepswe 任务格式与 verifier 基线；最新 `navidrome`、`qutebrowser` 转换运行
- **运行产物**：
  - `VerifierTrans/runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e`（`attempt_008`，final_task 13:11）
  - `VerifierTrans/runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c`（`attempt_005`，final_task 10:24）

## 1. 结论摘要

### 问题 1：测试是否已经面向功能、与具体函数实现解耦？

**结论：总体已经做到，但解耦层次取决于任务的功能边界。**

- **qutebrowser：是，高度解耦。** F2P verifier 只通过 `qutebrowser.utils.qtlog.hide_qt_warning`、标准库 `logging.Handler` 和 `LogRecord` 观察结果；没有断言私有 helper、过滤器类、文件布局、pytest fixture 或 mock 调用形状。只要公共入口和可观察日志行为相同，替代实现即可通过。
- **navidrome：对内部实现是解耦的，对公共导出边界是有意耦合的。** verifier 先用 `go build` 验证三个包能独立编译，再从外部包分别尝试编译 `NewClient` 和 `Client`。它不使用目标实现改名后的 `client`/`newClient`，不依赖私有字段、方法、错误文本或 Gold 文件结构；但必须引用旧的导出符号，才能证明“外部不可访问”这一公共 API 边界已经消失。这属于契约耦合，不是 Gold 实现耦合。
- **覆盖上的限制**：navidrome 的 `p2p` 为空，最终 verifier 只检查包编译和外部可见性，不独立回归 agent/router 的运行时行为；qutebrowser 的 F2P 没有在上下文退出后再次发 warning，因此没有直接验证“临时抑制、退出后恢复”。这两个限制不改变“解耦方式”判断，但会限制行为覆盖范围。

### 问题 2：instruction 是否类似 Deepswe，还是泄露实现信息？

**结论：可观察行为与公共接口的写法接近 Deepswe；没有发现 Gold 算法或私有结构被直接写给 solver。但“更具体”会改变解题提示强度，且少数条款没有原始 F2P 的直接支持，因此不能仅凭“没有私有名字”就判定 instruction 完全恰当。**

- Deepswe 的 instruction 本来就可以写公共 API 名称、参数、输入输出和可观察边界。例如 `kea-atomic-signal-selectors` 明确要求 `resetContext({ atomicSelectors: true })`、`logic.selectorHealth()`、叶级依赖和 React 重渲染行为；新增测试通过 Jest 的真实 API 和输出验证这些行为，而不是要求某个内部算法。
- Deepswe 的 grader 是通用的报告解析与白名单判分器：`tests/test.sh` 运行 base/new 测试，`grader.py` 按 F2P/P2P node id 汇总通过、失败、缺失和跳过；solution patch 只用于离线参考，不是评分答案。这与本次转换保留 F2P 意图、把测试改到可观察表面、保留 P2P 回归的方向一致。
- qutebrowser instruction 明确了模块路径、函数签名和日志语义。这些是“移动公共入口”任务的接口/行为契约，不是私有实现泄露；但默认 logger、上下文恢复等条款需要 verifier 直接覆盖，不能只写在 instruction 中。
- navidrome instruction 把原文“所有 client 方法改为 package-private”压缩成“构造器和 concrete type 对外不可访问”，避免列出 `albumGetInfo`、`validateToken`、`searchArtists` 等新私有名字。它没有泄露内部字段布局、请求实现或 helper 命名；这是更好的 solver-facing 表述，同时准确表达外部封装目标。

### “比原始 problem statement 更具体”究竟意味着什么

这里的“具体”指最终 instruction 把原题中的概括句展开成**可判定的输入、输出和接口边界**，并非必然给出内部实现方案。qutebrowser 的原题只说“过滤行为保持一致”，最终 instruction 则写出 `strip()` 后前缀匹配、非匹配 warning 保持级别与消息，以及 context manager 的公共路径和签名；navidrome 的原题说封装低层 client，最终 instruction 特别指出旧 constructor 与 concrete type 两个导出边界都要消失。这样的展开通常减少需求歧义和探索成本，可能让任务更好解；若它暴露了隐藏测试的精确判定点，也会改变原题的难度。更好解不等于更好的 benchmark，关键是细节是否本来就属于公开、可合理推断的产品契约。

Deepswe 的本地样本不支持“instruction 应越模糊越好”这一概括：`dateutil-rfc5545-timezone-interop` 逐项规定 TZID、序列化顺序、异常文本、属性和集合操作；`fastapi-implicit-head-options` 写出公开参数、默认值、HTTP 结果、方法顺序和中间件路径；`kea-atomic-signal-selectors` 甚至给出稳定 identity 的实现提示。更准确的追求是**行为和公共 API 足够精确，以便公平验收；内部方案保持开放**。Deepswe 样本本身也未完全遵守“绝不出现实现提示”，不能拿它作为绝对标准。

对这两条转换需再作区分：qutebrowser 的签名来自 `source/public/interface_contract.md`，四个原始 F2P 只直接支持显式传入 `'qt-tests'` 的过滤情形；退出后恢复和默认 `'qt'` 的要求合理但当前 F2P 未直接证明。navidrome 的旧 `NewClient`/`Client` 来自原题与历史测试上下文，不过“两个边界分别移除，否则不够”恰好揭示了转换 verifier 的两个独立判定点，提示强度高于原始 problem statement。它不是 Gold 私有实现泄露，却可能降低这个实例的解题难度。`INSTRUCTION_SCOPE: PASS` 和“verifier contract”等字样属于转换流程元信息，solver-facing instruction 没必要展示。

## 2. Deepswe 基线：instruction 与 verifier 的典型关系

### 2.1 instruction 的信息粒度

Deepswe instruction 通常由三类信息组成：

1. **用户可观察行为**：返回值、错误、HTTP 响应、渲染输出、状态变化、日志记录。
2. **必要的公共接口契约**：真实公共函数/类/参数名、模块位置、开关或 CLI 入口；这些信息用于让 agent 找到正确扩展点，不等于指定内部实现。
3. **范围和兼容性约束**：默认值、优先级、旧行为保持、不能破坏的生命周期或路由行为。

例如 `Data/deepswe/tasks/fastapi-implicit-head-options/instruction.md` 写出 `auto_head`/`auto_options` 的公共构造器与 decorator 参数、HEAD/OPTIONS 的 HTTP 结果、`Allow` 和 OpenAPI 语义；`tests/test_implicit_head_options.py` 用 `TestClient`、响应头、状态码和 OpenAPI 结果观察这些行为。`psd-tools` 的测试则通过 `BlendRangeChannel`/`BlendRanges` 的构造、raw round-trip 和 mask 输出验证公共 API。

### 2.2 verifier 形态

Deepswe task 目录的基本结构是 `task.toml`、`instruction.md`、`environment/`、`tests/` 和 `solution/`。`tests/test.sh` 在干净仓库中运行已有 base 测试和新增测试；共享 `grader.py` 读取 CTRF/JUnit 报告，只按配置中的 F2P/P2P 白名单判分。其核心原则是“任何实现只要可观察行为正确即可通过”，而不是复现 `solution/solution.patch`。

这给本次审计一个基线：

- 测试可以引用公共 API，因为公共 API 本身就是产品契约。
- 测试不应要求私有 helper 名称、Gold 的文件布局、内部缓存或某个 mock 交互序列。
- 如果历史测试直接进入包内并访问私有对象，转换应寻找真实公共/外部观测边界；如果任务本身就是可见性变化，则编译器的外部包边界就是功能结果。

## 3. 最新 navidrome：具体分析

### 3.1 原始问题与最终 instruction 的差异

原始文件：`source/public/problem_statement.md`。

原文要点是：LastFM、ListenBrainz、Spotify 的 `Client` 类型及其方法当前导出；应把类型和**所有方法**改成 package-private，同时保持 agent interface 的外部行为不变。

最终文件：`final_task/instruction.md`。

最终 instruction 改为：

- 限定在三个 music-service 包；
- 要求 concrete low-level constructor 和 concrete client type 对外不可访问；
- 要求两个导出边界分别移除；
- 保持高层 agent/router 入口和可观察行为；
- 明确不要求新的 public interface，也不约束私有 request/response 布局和 helper 名称。

这不是把 Gold 的 `client`/`newClient` 告诉 solver。它把原文的“类型及所有方法均改为 package-private”收窄成可验证的两个旧公共边界：构造器和 concrete type 不再可从外部引用。这个收窄避免了强迫候选采用某种私有方法命名，却也意味着最终 verifier **没有逐一证明原文所说的所有方法都已变成非导出方法**。在旧入口被移除且没有替代的导出返回入口时，外部调用者不能再经这些旧入口构造或命名客户端；这是当前测试实际证明的范围。

### 3.2 verifier 做了什么

最终 `tests/test.patch` 只安装：

- `verifier/run.sh`；
- 每个服务两个独立的外部包 probe：`NewClient` 和 `Client`；
- `p2p_nodes.txt`（本任务为空）。

`run.sh` 的顺序是：

1. `go build ./core/agents/{lastfm,listenbrainz,spotify}`，证明包源代码自身仍能构建；
2. 在 `lastfm_test`、`listenbrainz_test`、`spotify_test` 外部包中分别编译旧构造器和旧 concrete type 的 probe；
3. probe 成功表示边界仍公开，记为失败；probe 编译失败表示该边界已被封装。

这与历史测试相比有明确的解耦收益：原始 `original_test.patch` 在包内把 `NewClient`/`Client`/各方法改成小写，并继续直接驱动私有客户端的 HTTP fake、请求 URL、解析结果和错误文本；最终 verifier 不需要知道候选实现使用哪个私有名字、是否拆分文件、是否改用另一种内部客户端结构。它只观测 Go 外部包的访问规则。

### 3.3 仍然存在的耦合与覆盖缺口

- **必要契约耦合**：probe 必须写出 `lastfm.NewClient`、`lastfm.Client` 等旧公共符号；否则无法检测“它们仍然导出”。这不是对新实现的绑定，而是对待移除的公共 API 名称的负向测试。
- **负向编译 probe 的误判风险**：`run.sh` 把 probe 的任意 `go test` 非零退出都当成“不可访问”，只用预先的包级 `go build` 排除目标包本身不编译的情况；它没有检查失败是否确由旧符号不可访问引起。现有 Base/Gold replay 与两个针对单边界保留的 mutant 缓解了这一风险，但不能逻辑上排除所有与符号无关的 probe 失败。
- **运行时回归未覆盖**：`config.json` 的 F2P 是 `TestLastFM`、`TestListenBrainz`、`TestSpotify`，P2P 为空；`package_report.json` 也显示原始六个 Go 测试文件作为未引用 F2P 文件被排除。因此“高层 agent/router 行为保持不变”主要来自任务语义和包构建约束，并非一个独立的 runtime P2P 断言。
- **验证强度是合适但狭窄的**：两个 probe 分开后，可以拒绝只隐藏 constructor 或只隐藏 type 的 mutant；但它不会继续验证每个低层请求的业务语义。这正是从历史私有测试解耦后的取舍，应在审计中明确标注。

## 4. 最新 qutebrowser：具体分析

### 4.1 原始问题与最终 instruction 的差异

原始文件：`source/public/problem_statement.md`。

原文是一个测试迁移任务：`hide_qt_warning` 和相关测试从 `log.py` 移到 `qtlog.py`，测试应迁移，过滤行为保持一致。

最终文件：`final_task/instruction.md`。

最终 instruction 将“迁移测试”改写为 solver 可执行的公共契约：

- `qutebrowser.utils.qtlog.hide_qt_warning` 必须存在并且是 context manager；
- 参数为 `pattern: str`、`logger: str = 'qt'`；
- 对指定 logger，消息 `strip()` 后以 pattern 开头的 warning 在上下文内被抑制；
- 不匹配 warning 的 severity 和 message 保持；
- 抑制只在上下文内生效，其他 logging/warning 行为不变。

这比原 problem statement 更具体，但具体的是公共入口和可观察日志结果，没有给出过滤器类、字段、注册方式或调用栈。`instruction_scope_trace.json` 还把“测试文件迁移”明确排除为 provenance，而不是 solver-facing runtime requirement；这是符合功能转换原则的。

### 4.2 verifier 的解耦证据

F2P 共 4 条，分别对应不匹配透传、精确匹配、前缀匹配、首尾空白匹配；转换后的 `verifier.py`：

- 从 `qutebrowser.utils.qtlog` 导入公共入口；
- 使用最小的标准 `logging.Handler` 记录真实 `LogRecord`；
- 只检查记录数量、`levelname` 和 `getMessage()`；
- 不引用 `QtWarningFilter`、私有字段、`caplog` 的内部结构或 Gold 文件；
- 52 条历史 P2P 节点在 `p2p_nodes.txt` 中原样保留，由 exact-node runner 执行。

因此，一个使用 logging filter、record factory 或其他等价公共实现的候选都可以通过。Positive QA 的替代实现和两个针对空白/透传语义的 Negative QA 也通过了当前 gate，支持“测试不是只认 Gold 结构”的判断。

### 4.3 instruction 与 verifier 的未闭合条款

当前 verifier 的 `_emit_qt_tests_warning` 只在 `with qtlog.hide_qt_warning(...)` 内发出一条 warning，然后移除 recording handler。它没有在 `with` 退出后再次发出同一 warning 来验证“suppression is temporary”。此外，F2P 只显式使用 `'qt-tests'` logger；没有独立测试默认参数 `'qt'` 的运行时路径，虽然签名写进了 instruction。

所以 qutebrowser 的正确审计结论是：**核心过滤行为已面向公共功能并与实现解耦；instruction 中的恢复语义和默认 logger 仍需要补一到两个行为断言，才能使 instruction 与 verifier 完全闭合。** 这属于覆盖增强建议，不应通过加入私有实现断言来修复。

## 5. “原始 F2P 没覆盖”与“转换后没保留”的区别

这两种情况需要分开写，不能把最终 verifier 的缺口都归因于原始 F2P。

### navidrome

navidrome 的 source F2P selector 只有三个 suite-level id：`TestLastFM`、`TestListenBrainz`、`TestSpotify`；它没有细到单个 Go test case，也没有 P2P。原始 `source/restricted/original_test.patch` 并非只改测试名称：它在包内继续执行了 Last.fm 的 album/artist/session 请求与错误断言、ListenBrainz 的 token/now-playing/scrobble 请求断言，以及 Spotify 的 authorize/search/error 断言，同时还改动了部分 agent/router 测试中的构造方式。

因此，navidrome 的准确说法是：**原始 F2P 有运行时测试，但这些测试与待隐藏的包内符号强绑定；转换后的 verifier 为取得实现解耦，只保留了源码可编译和外部导出边界检查，运行时覆盖被主动收窄。** 这属于 conversion scope/coverage trade-off，不是 source F2P 完全没有覆盖。由于 source selector 是 suite-level，不能从 selector 本身推断每个原始子测试都被单独计分；但原始补丁内容证明这些行为断言确实存在。

### qutebrowser

qutebrowser 的 source F2P 明确列出四个 case，原始测试只在 `with hide_qt_warning(..., 'qt-tests')` 内发出一条 warning，然后在上下文结束后检查捕获结果；没有退出后再次发 warning，也没有省略 `logger` 参数使用默认 `'qt'`。所以“退出后恢复”和“默认 logger 路径”确实不是原 F2P 的直接覆盖。最终 instruction 将它们写成必要公共契约的一部分，但当前 verifier 没有对应断言；按 F2P 证据规则，这两项应标注为 `spec_gap`/补充契约，而不能表述为已由原始 F2P 证明。

## 6. 按“行为精确、实现开放、证据充分”标准的最终判定

| 数据 | 行为契约是否清楚 | 是否泄露实现路径 | 是否与 F2P 证据闭合 | 判定 |
| --- | --- | --- | --- | --- |
| qutebrowser | 是：模块入口、context manager、strip 后前缀匹配和透传结果都清楚 | 基本没有：未指定 filter 类、注册方式或文件内部结构 | **不完全**：退出后恢复、默认 logger 没有原始 F2P 直接支持，当前 verifier 也没测 | **基本符合；需标注 spec_gap** |
| navidrome | 是：外部封装边界清楚 | 基本没有 Gold 私有实现泄露；但“两个边界独立移除”提示了 verifier 的拆分方式 | **不完全**：原始 F2P 有运行时断言，转换后只保留可见性 probe；高层 runtime 行为也没有独立回归 | **部分符合；应在 report 中显式说明 coverage narrowing** |

因此，不能把两条数据都称为“完全符合”。更准确的分级是：

- **qutebrowser：转换方法正确，instruction 需要做证据分层。** 公共行为写得足够精确，内部实现保持开放；但没有 F2P 支持的恢复/default 条款应从“已验证要求”降为 `spec_gap` 或补充契约。
- **navidrome：公共边界 verifier 设计合理，但 scope 不能伪装成完整行为覆盖。** 原始 suite-level F2P 确实包含运行时测试；最终 verifier 的删减是为了实现解耦，却造成覆盖收窄。`report` 应同时记录“implementation-decoupled”和“runtime coverage dropped”，并避免把“独立移除”写成仿佛产品新增需求。

`VERIFIED`、`PACKAGED` 和 Positive/Negative QA PASS 只说明转换产物通过既有转换 gate，不等价于满足本节更严格的人审标准。

## 7. 如果只保留 Problem Statement，会少什么

`Problem Statement` 和最终 `instruction` 不是两份同义文本：前者是数据集原始问题叙述和语义证据，后者是转换器根据 F2P、interface contract 和仓库事实整理出的 solver-facing 验收契约。理想流程不是删除前者，而是保留前者并让后者逐条可追溯。

| 数据 | Problem Statement 主要说什么 | 最终 instruction 增加/删除了什么 | 影响 |
| --- | --- | --- | --- |
| navidrome | 三个服务的 `Client` 类型及方法导出，应该 package-private，agent interface 行为不变 | 增加范围、constructor/type 两个外部边界、分别移除、out-of-scope；删除具体方法示例和私有布局细节 | 更容易判断“完成条件”，但把“所有方法”收窄成两个边界，并暴露了 verifier 的拆分思路；只留原文则更开放但验收更含糊 |
| qutebrowser | `hide_qt_warning` 和测试从 `log.py` 移到 `qtlog.py`，过滤行为保持一致 | 删除“把测试文件搬过去”这一 solver 目标；增加公共模块路径、签名、strip 后前缀匹配、透传和临时性 | 避免 agent 只改测试位置，直接指向产品行为；但恢复/default 条款没有 F2P 直接支持，应标 `spec_gap` |

只给 navidrome 的原文，solver 仍可能按包内重命名方式解决，且不清楚 constructor/type 是否要分别被外部拒绝；只给 qutebrowser 的原文，solver 可能只迁移测试文件，因为原文把“测试需要搬迁”写成当前任务。最终 instruction 的价值是消除这些歧义，但它不能凭空扩大被验证的语义范围。

因此建议保留四层信息：

1. 原始 `Problem Statement`：不可改写的 provenance/source semantics；
2. solver-facing `instruction`：只写公共行为和必要接口；
3. `instruction_scope_trace`：说明每条 instruction 来自哪个 F2P/interface evidence；
4. report 中的 `spec_gap` 与 coverage narrowing：明确哪些要求没有原始 F2P 或没有被最终 verifier 保留。

## 8. 对两个问题的判定表

| 项目 | 功能观测面 | 对内部实现解耦 | 对公共契约耦合 | instruction 是否泄露 Gold/私有实现 | 审计判定 |
| --- | --- | --- | --- | --- | --- |
| Deepswe 基线 | 原生测试报告中的行为、API、输出 | 设计目标 | 允许引用真实 public API | 不应泄露 | 参考标准 |
| navidrome | 外部包可见性 + 三包源码构建 | **是**：不引用新私有名字、字段、算法 | **是且必要**：引用待移除的 `NewClient`/`Client` | **否**：没有写 `client`/`newClient` 或内部布局 | 解耦正确，但 runtime 覆盖窄 |
| qutebrowser | 公共模块函数 + stdlib logging records | **是**：不引用过滤器实现和 pytest 内部 | **是且必要**：模块路径、函数签名、日志语义 | **否**：未指定 filter 类/注册方式 | 解耦正确，恢复/default 路径待补测 |

## 9. 建议

1. **保留 navidrome 的外部编译边界设计**。它是验证“不可从外部包访问”的正确观测面；不要改成检查候选是否采用 `client`/`newClient` 等私有命名。
2. **为 qutebrowser 增加行为闭环**：在上下文退出后对同一 logger 再发一条 warning，确认记录恢复；增加一次省略 `logger` 参数、使用默认 `'qt'` 的透传/抑制检查。若历史 F2P scope 不允许扩展，可把它们标记为必要公共契约的补充检查并记录理由。
3. **对 navidrome 的“高层行为不变”保持措辞克制**。当前没有 P2P 节点，不应在报告中把包编译结果表述成完整的 agent/router runtime 回归；可以明确说这是未覆盖风险。
4. **继续沿用 scope trace / coverage matrix / self-review**。它们能把“原始问题中的功能语义”“历史测试意图”和“最终 solver-facing 条款”分开，防止把测试迁移位置或 Gold 结构误写成实现要求。

## 10. 证据索引

- Deepswe 任务约定：[Data/deepswe/README.md](../../../Data/deepswe/README.md)
- Deepswe 功能 instruction 示例：[kea-atomic-signal-selectors/instruction.md](../../../Data/deepswe/tasks/kea-atomic-signal-selectors/instruction.md)、[fastapi-implicit-head-options/instruction.md](../../../Data/deepswe/tasks/fastapi-implicit-head-options/instruction.md)
- Deepswe 行为测试示例：[kea-atomic-signal-selectors/tests/test.patch](../../../Data/deepswe/tasks/kea-atomic-signal-selectors/tests/test.patch)、[psd-tools-blend-range-api/tests/test.patch](../../../Data/deepswe/tasks/psd-tools-blend-range-api/tests/test.patch)
- navidrome 最终 instruction：[final_task/instruction.md](../../runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e/final_task/instruction.md)
- navidrome 原始 problem statement：[problem_statement.md](../../runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e/source/public/problem_statement.md)
- navidrome 最终 verifier：[test.patch](../../runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e/final_task/tests/test.patch)
- navidrome 转换报告：[conversion_report.md](../../runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e/review/conversion_report.md)
- qutebrowser 最终 instruction：[final_task/instruction.md](../../runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c/final_task/instruction.md)
- qutebrowser 原始 problem statement：[problem_statement.md](../../runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c/source/public/problem_statement.md)
- qutebrowser 最终 verifier：[test.patch](../../runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c/final_task/tests/test.patch)
- qutebrowser 转换报告：[conversion_report.md](../../runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c/review/conversion_report.md)
