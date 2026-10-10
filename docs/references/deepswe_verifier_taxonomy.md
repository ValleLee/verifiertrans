# DeepSWE Verifier 设计:功能验证而非实现绑定

数据来源:`/lg-home/cog8/lwli6/Data/deepswe/tasks/*`(113 个 task 的 `instruction.md`/`tests/*`/`solution/*`)与共享判分脚本 `grader.py`。
用途:供 SWE-Bench Pro → DeepSWE 风格转换时直接参考的规则与 checklist。

---

## 1. Verifier Taxonomy

| 类型 | 核心验证目标 | 常见测试方式 | 适用场景 | 示例 |
|---|---|---|---|---|
| 公共 API 行为验证 | 调用公开导出的函数/方法后返回值或状态是否符合规格 | 直接调用公开符号,断言返回值/集合成员/长度 | 库/框架新增 API | koota `createPredicate` → `world.query(pred)` 返回集合是否恰好包含满足谓词的实体 |
| 契约式异常验证 | 特定非法输入必须抛出特定异常类型,合法输入不抛 | `pytest.raises(SpecificError)` 等,不检查内部校验函数是否被调用 | 解析器、协议实现、输入校验 | httpx 畸形 multipart 边界行抛 `httpx.DecodingError`,重复消费流抛 `httpx.StreamConsumed` |
| 黑盒协议/CLI 验证 | 通过用户真实使用的接口(HTTP 请求、CLI 调用)驱动系统,只看外部响应 | 起真实进程/server 发 HTTP 请求断言 status/headers/body;或 spawn CLI 断言 stdout | Web 框架路由、CLI 工具、跨进程验证 | fastapi 用 `TestClient` 发 `HEAD`/`OPTIONS` 断言 status、`Allow` header、OpenAPI JSON;fd 用真实文件树跑二进制断言排序后的 stdout |
| 状态转换/时序验证 | 验证"状态如何随事件序列变化",非单一时刻快照 | 有序操作 + 每步后重新查询,断言中间态和终态 | 响应式系统、增量计算、有状态服务 | koota `Added`/`Removed`/`Changed(predicate)` 断言"false→true 才出现,稳定不变则不出现";prometheus 断言"reload 失败后重启,仍能读出上次失败原因" |
| 可观察副作用验证 | 系统对外部世界(文件系统等)产生的、有文档含义的副作用 | 读文件系统里约定路径/格式,或用公开 API 读取状态 | 有明确文件格式契约的系统(git、构建工具) | go-git 断言工作区文件出现 `<<<<<<< HEAD`、`.git/MERGE_HEAD` 内容为目标 commit hash、index 用 `index.Stage(n)`(公开类型)校验 stage 1/2/3 |
| 规则化 I/O 变换验证 | 断言输出满足 instruction 描述的规则,非逐字节 diff 参考实现输出 | 每条规则单独一个测试用例,断言该规则的局部效果 | 文本/数据格式转换、linter、formatter | obsidian-linter TOC:"YAML frontmatter 里的标题被忽略""显式 id 重复用 `-1`/`-2` 去重"各自独立成一个 test case |
| 参数化边界矩阵验证 | 遍历"实现容易踩坑但语义不变"的输入维度,证明行为一致 | `@pytest.mark.parametrize`/表驱动,维度含流分片点、换行风格、大小写、空/边界值 | 流式解析、编解码 | httpx 对同一份 multipart body 在 10 个不同字节位置切分喂入,断言解析结果不受影响 |
| 回归保留验证 | 新功能不能破坏已有行为 | 复用既有测试套件中不受本次改动影响的用例 | 所有 task(判分机制里的硬性必选项) | 每个 task 的 `p2p_node_ids` |
| Mock/Fixture-Induced Implementation Coupling | 测试基础设施本身不能只支持 reference solution 的实现路径 | 审计 mock/fake/fixture/stub/serializer/transpiler shim 的 public runtime contract，并用结构不同但语义等价的访问路径验证；缺失的标准属性/方法必须视为 harness defect | 需要合成运行时、依赖替身、无完整 toolchain 的功能 verifier | Gold 通过 `getElementsByTagName`，但等价实现使用标准 `documentElement` 被 mock 错误拒绝 |

**共同机制:** 断言对象永远是"调用公开接口后能观察到的东西";描述方式是"规则"和"事件序列"而非"和参考 diff 逐行相同";涉及文件系统的断言用的是协议/框架本身定义的公开格式,不是待测代码的内部中间结构。

---

## 2. 案例证据(供转换时对照)

### koota `createPredicate`
- 41 个测试全部通过 `world.spawn`/`entity.set`/`world.query`/`.toContain(entity)` 驱动,零断言涉及内部字段(`predicateResults`、`predicateTransitions` 等参考实现引入的内部结构,测试完全不涉及)。
- "updateEach 迭代期间延迟重新求值"这条规则,断言方式是 `visited.length === 2`(观察副作用),不是断言某个队列被使用。

### httpx `iter_multipart`/`aiter_multipart`
- 全黑盒:构造原始字节流,断言 `MultipartPart.headers`/`.content` 与异常类型(`DecodingError`/`StreamConsumed`)。
- 关键测试模式:同一份数据在 10 个不同字节位置切分成 chunk 喂入,断言解析结果与切分点无关——这是显式验证"实现对无关输入维度不敏感"的属性,防止参考实现的具体 buffer 策略泄漏进测试。

### go-git `Worktree.Merge`
- 断言全部落在 git 协议本身定义的可观察产物上:工作区文件含冲突标记、`index.Stage(1/2/3)`(公开类型)、`.git/MERGE_HEAD` 文件内容。
- `index.Stage(0) should not exist during conflict` 验证的是协议语义(index 存在多阶段 entry = 冲突未解决),不是某个函数的调用路径。

### prometheus 事务性 reload 状态
- 测试拉起真实二进制进程,通过 HTTP 请求 `/api/v1/status/reload` 断言 JSON 字段;另有测试验证"状态文件被破坏时不应阻止启动"。
- 测试进程与被测进程之间只有 HTTP 和文件系统两个接口,完全不关心内存里状态的数据结构或持久化格式细节(除非 instruction 已声明)。

---

## 3. Verifier 设计原则(可直接套用的规则)

| 原则 | 说明 |
|---|---|
| observable behavior over implementation details | 断言落点必须是调用者能看到的东西:返回值、异常类型、HTTP 响应、有文档含义的文件产物、stdout。禁止断言私有字段/内部调用次数。 |
| public API / documented artifact over internal structure | 文件系统操作可以断言,前提是该文件/格式本身是协议或框架公开承诺的一部分(如 `.git/MERGE_HEAD`),不是待测代码自造的内部中间态。 |
| reference solution is not the only answer | 参考解不参与自动判分,只用于人工离线核对规格;不能拿参考解做 patch 相似度比较或中间状态断言依据。 |
| oracle-vs-nop differential 决定测试归类 | f2p/p2p 由"参考解 vs 空补丁"的测试结果差分自动产出,不是人工主观标注哪条测试测的是新功能。 |
| regression preservation 是硬性项 | p2p 必须全过才能拿到 reward=1,新功能实现不能以破坏旧行为为代价。 |
| 异常/错误类型是契约的一部分,前提是 instruction 已声明 | 断言异常类型合法的充分条件是:instruction 明确规定了该场景该抛什么错误,不是隐性推断。 |
| black-box across the real interface boundary | 对 Web 框架/后台服务,走真实 HTTP 请求或 CLI 调用,不直接调内部函数,即使内部路由/中间件被完全重写也不受影响。 |
| gaming 信号记录但不作为硬性拦截 | 可疑改动(改包管理配置、越界文件改动)被记录用于事后审查,不直接否决 reward——避免把辅助审计信号变成隐性额外规则。 |

---

## 5. SWE-Bench Pro → DeepSWE 转换 Checklist

**核心判断句:** 把"历史测试恰好验证了什么"翻译成"instruction 明确要求了什么",只保留后者作为 verifier 断言依据;无法从行为规格推导出的断言,要么补规格、要么改写成行为级断言、要么删除。

### 直接保留
- 断言 HTTP status/headers/body、CLI stdout、公开异常类型的测试 —— 天然黑盒,无需改写。
- 断言"事件序列 → 状态变化"的测试(操作 A 断言 B,操作 C 断言 D),只要断言点在公开 API 上。
- `pass_to_pass` → 直接作为 `p2p_node_ids`,承担回归保留角色。

### 需要抽象改写
- `fail_to_pass` 不能直接等价搬为 `f2p_node_ids`:历史 PR 的 f2p 是"这个 commit 让哪些测试从失败变通过",不必然等价于"验证 problem_statement 描述的核心行为"——需要逐条核实测试断言的对象是否为公共契约。
- 依赖具体私有函数名/内部模块路径的 import 或 mock:检查 `interface` 字段是否把该符号列为公共接口;若只是历史实现的内部 helper,改写为通过公共入口触发同一行为。
- 对着 gold patch 输出做逐字节/逐字段 diff 的 golden 测试:拆成规则化断言(每条规则一个独立可读的用例),避免未被规格声明的格式细节(空格、换行位置)被误判为错误。
- 依赖 mock/monkeypatch 验证"内部函数被调用"的测试:改写为验证调用后的可观察结果(返回值、副作用)。
- mock/fixture/fake 只实现 reference solution 实际使用的 API 路径:补齐被测 public runtime 的最小标准契约，并检查至少一个结构不同的等价路径；否则标记为 **Mock/Fixture-Induced Implementation Coupling**，不得把候选判为无效。
- 只测了单一分片/单一编码方式的测试:扩展为参数化矩阵,把"对无关输入维度不敏感"显式变成待验证属性。

### 必须剔除的 implementation details
- 把"gold patch 恰好这样实现"当规格断言(特定字段名、特定类的存在),除非它本身是文档化的公共 API。
- 未经审视直接搬入的强耦合断言(函数签名参数顺序、内部错误码具体数值)——先问"instruction 有没有讲清楚",没讲清楚就补规格或放宽断言。
- 让 verifier 跑 gold patch 做相似度比较,或用 gold patch 中间状态做断言依据 —— 继承 DeepSWE 规则:reference solution 不进入自动判分链路,只做人工离线核对。

### 字段映射参考(SWE-Bench Pro → DeepSWE bundle)
| SWE-Bench Pro 字段 | 转换角色 |
|---|---|
| `problem_statement` | specification 的证据来源成为后来的 `instruction.md` |
| `requirements` | 只参考能回溯到原repo的部分 |
| `interface` | 只参考真正的公共契约部分 |
| `test_patch` + `fail_to_pass` | verifier 断言的候选种子,需按上述 checklist 逐条改写/剔除 |
| `pass_to_pass` | 直接作为回归保留(`p2p_node_ids`) |
| `patch`(gold patch) | 仅作 curator 离线参考,不进入自动判分 |
