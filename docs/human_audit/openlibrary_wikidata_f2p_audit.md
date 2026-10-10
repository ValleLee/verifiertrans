# OpenLibrary `WikidataEntity.get_statement_values` 转换审计

## 审计对象与结论

- 源实例：`internetarchive__openlibrary-4a5d2a7d24c9e4c11d3069220c0685b736d5ecde-v13642507b4fc1f8d234172bf8129942da2c2ca26`
- 发布版本：verifier revision 1
- 结论：**通过**。源 F2P 的四项可观察行为均被保留；最终 F2P 只断言公共方法的返回值，没有把 Gold patch 的实现形式、私有 helper、mock 调用次数或无关功能写成要求。

这里的“当前 F2P”是指最终 `tests/test.patch` 注入后由 `VERIFIER_GROUP=f2p` 执行的 `verifier/test_wikidata_verifier.py`。`tests/config.json` 仍把源 node id 记为 F2P 元数据，用于可追溯性；评分器将整个功能测试组以一个 aggregate F2P 结果计分，并不表示只运行了一条 pytest 断言。

## Problem statement → instruction

### 原始 problem statement

标题为 “Incomplete Retrieval of Property Statement Values in Wikidata Entities”。其含义是：`WikidataEntity` 保存属性 statements，但没有专用机制取回某一属性的全部值；调用方不得不手动穿行嵌套对象。预期行为是提供一个接收 property identifier 的方法，返回有效值列表、保持顺序、跳过无效项，并在属性不存在或无可用值时返回空列表。

### 当前 instruction

当前 instruction 将上述需求落成明确的公共契约：在 `openlibrary/core/wikidata.py` 的 `WikidataEntity` 上实现 `get_statement_values(property_id)`，返回 `list[str]`；从公共 `statements` mapping 中查找属性，对每个具有 `value.content` 的 statement 收集 content，保持原顺序，忽略形状不完整的 statement；缺属性或没有有效值时返回 `[]`。同时明确“只验证可观察返回值”，不要求任何内部存储格式、helper 或额外方法。

### 差异分析

| 维度 | 原始表述 | 当前 instruction | 审计判断 |
| --- | --- | --- | --- |
| API | “expose a method”，未写全限定路径 | 固定为 `WikidataEntity.get_statement_values` | 收敛而非扩张；源 F2P 正是该方法。 |
| 数据形状 | 泛称嵌套 statements/valid values | 明确 `statements[property]`、`value.content` | 来自源 F2P 的实际输入；使任务可实现、可验证。 |
| 行为 | 顺序、无效项、空结果 | 四项均逐条保留 | 无行为遗漏。 |
| 实现约束 | 未规定 | 显式取消内部实现约束 | 有利于接受等价实现。 |

因此 instruction 比 problem statement 具体，但具体化的每一项都可由源测试看到；没有纳入 Gold patch 中与本需求无关的内容。

## F2P：原始测试与当前功能测试

### 原始 F2P

源 selector 只有 1 个：`openlibrary/tests/core/test_wikidata.py::test_get_statement_values`。该单一测试函数含四组断言：

| 原始断言组 | 原始输入/期望 |
| --- | --- |
| 单值 | `P2038 -> [{value: {content: 'Chris-Wiggins'}}]`，返回 `['Chris-Wiggins']`。 |
| 多值 | 三个 `value.content`，返回 `['Value1', 'Value2', 'Value3']`。 |
| 缺失属性 | 查询 `P9999`，返回 `[]`。 |
| 畸形 statement | 有效项夹杂缺 `value`、缺 `content` 的项，仅返回 `['Valid']`。 |

### 当前 F2P

最终功能测试拆为四个独立测试，映射如下：

| 源 F2P 行为 | 当前测试 | 变化 |
| --- | --- | --- |
| 单值提取 | `test_single_statement_value` | 保留相同输入与返回值。 |
| 多值与顺序 | `test_multiple_statement_values_preserve_order` | 保留相同三值序列，测试名显式说明顺序是契约。 |
| 缺失属性 | `test_missing_property_returns_empty_list` | 保留。 |
| 畸形项跳过 | `test_malformed_statements_are_skipped` | 保留相同的两类畸形项和有效结果。 |

构造对象的方式从源测试的 `createWikidataEntity()` 换为功能测试中的 `make_entity()`，后者通过公开的 `WikidataEntity` dataclass 构造一个最小实体。它没有检视/替换私有成员，也没有 mock 待测方法。

另外，最终 `test.patch` 仍带有原始 `test_get_statement_values`，以维持源测试文件和继承 P2P 的可应用性；真正计入 converted F2P 的是上表四个 `verifier/test_wikidata_verifier.py` 测试。继承的 P2P 有 8 条，均由 exact-node runner 原样选择执行。

## 是否已从实现导向改为功能导向？

**是。** 证据如下：

- 输入通过公开实体和公开 `statements` 数据提供，输出只比较 `get_statement_values` 的返回列表。
- 未断言循环/推导式、helper 名称、调用次数、对象的私有存储结构，亦未比较 patch 文本。
- 已验证可接受结构不同的正确实现：验证记录中的正例使用显式循环与防御性 `isinstance`/dict 检查，而非 Gold 的列表推导式，仍被判为有效。
- 两个仅改变行为的 mutant（把 append 改成头插、使多值顺序反转）均被当前 F2P 拒绝，说明测试捕获的是“顺序”这一功能契约而非某段实现。

小的边界说明：测试确实要求公开的类名、方法名和 `statements`/`value.content` 领域输入形状；这是任务的公开接口/输入协议，并非对内部实现的绑定。

## 回放与风险

两轮 Base/Gold 回放均显示 Base F2P 失败、Gold F2P 通过，Base 和 Gold 的 8 条 P2P 都通过；语义审查（revision 1）为 PASS，且没有 unconverted F2P、overreach 或 mapping gap。主要残余风险低：测试没有额外推断诸如“非字符串 content 应如何处理”或“空 content 应如何过滤”的语义，因源 F2P 从未定义这些规则。

## 取证位置

- 原 statement：`intermediate/attempts/attempt_001/source/public/problem_statement.md`
- 原 F2P patch/selectors：`source/restricted/original_test.patch`、`source/restricted/resolved_test_selectors.json`
- 当前 instruction/测试：`final_task/instruction.md`、`final_task/tests/test.patch`
- 接受与语义记录：`control/report.json`、`validation/semantic/rev_001.json`
