# qutebrowser Qt warning 过滤转换审计

## 审计对象与结论

- **实例**：`instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c`
- **Base commit**：`ebfe9b7aa0c4ba9d451f993e08955004aaec4345`
- **本次审计时间**：2026-09-24 14:28（Asia/Shanghai）；运行产物最后验证时间为 2026-09-24 05:43（Asia/Shanghai）。
- **运行状态**：`VERIFIED / PACKAGED`，final revision 2，semantic judge `PASS`，稳定回放 `True`。
- **结果**：历史 F2P 4 条全部保留并发出 4 条功能测试；历史 P2P 52 条保持通过。Base+F2P 失败、Gold+F2P 通过。

**结论：通过。** 这是三条案例中最直接的功能化转换：测试从模块迁移/内部位置叙述，落到 `qtlog.hide_qt_warning` 的公开调用和日志捕获结果；没有要求过滤器内部如何实现。

## 1. 原始 problem statement（中文翻译）

**标题：把 Qt warning 过滤测试移动到合适的模块。**

**描述：** `hide_qt_warning` 函数及其相关测试已经从 `log.py` 移动到 `qtlog.py`，这样可以更好地组织 Qt 专用的日志功能。测试也需要迁移，以便继续验证新模块中的 warning 过滤行为。

**预期行为：** 代码重组后，Qt warning 过滤仍应与之前完全一致，使用相同的过滤模式和行为。

**当前问题：** 功能已经移动，但测试还需要更新，以反映新的模块组织方式。

题目的真实功能要求是：不匹配过滤模式的 warning 继续被记录；匹配模式的 warning 被抑制；模块移动不应改变这两种结果。

## 2. 当前 instruction（中文翻译）

**任务：** `hide_qt_warning` 及其 warning 过滤逻辑已经从 `qutebrowser.utils.log` 重组到 `qutebrowser.utils.qtlog`。在新模块中提供同样的过滤行为，不改变 Qt warning 过滤的语义。

**公开契约：**

- `qutebrowser.utils.qtlog` 必须暴露可调用的 `hide_qt_warning(pattern, logger='qt')` context manager；它会为指定 logger 临时安装 warning filter，并在 context 退出时移除 filter。
- 关联的 `QtWarningFilter` 必须能用一个 pattern 字符串构造，并表现为标准 logging filter。

**可观察行为：**

- `hide_qt_warning` 激活时，消息不以配置的 pattern 开头的 warning 仍到达日志捕获，保留原来的 warning level 和消息文本。
- 激活时，去掉首尾空白后以配置的 pattern 开头的 warning 不产生 captured log record。这里包括精确匹配、pattern 作为前缀的更长消息，以及带首尾空白的消息。

## 3. 原始 F2P 与当前 F2P

### 原始 F2P（4 条）

| 原始测试 | 原始可观察行为 |
| --- | --- |
| `test_unfiltered` | 在 `hide_qt_warning("World", "qt-tests")` 中记录 `Hello World`，保留一条 WARNING 和原消息。 |
| `test_filtered[Hello]` | pattern 精确匹配时没有记录。 |
| `test_filtered[Hello World]` | pattern 位于消息开头时没有记录。 |
| `test_filtered[  Hello World  ]` | 消息带首尾空白但 trim 后匹配时没有记录。 |

这些测试本身已经使用 `qtlog.hide_qt_warning`、标准 `logging` 和 pytest `caplog`，没有调用私有 helper。

### 当前 F2P（4 条功能测试）

| 原始 F2P | 当前功能测试 | 变化 |
| --- | --- | --- |
| `test_unfiltered` | `TestHideQtWarning.test_unfiltered_message_is_emitted` | 从仓库测试文件中的同名断言，变为独立 verifier 对公开 context manager 和 caplog 输出的同一断言。 |
| 3 个 `test_filtered[...]` | 参数化 `test_filtered_message_is_suppressed[...]` | 保留 exact、prefix、surrounding whitespace 三个输入和“无 captured record”结果。 |

当前 verifier（`final_task/tests/test.patch` 中的 `verifier/verifier.py`）只导入 `qutebrowser.utils.qtlog`，创建名为 `qt-tests` 的标准 logger，用 `caplog` 观察记录。它不检查代码文件位于哪个模块、是否使用某个 filter 私有字段、是否调用 `strip()` 的具体写法。


### 核心代码：原始 F2P 的可观察断言

原始测试已经通过公开 context manager 和标准 logging 观察结果：

```python
with qtlog.hide_qt_warning("World", "qt-tests"):
    with caplog.at_level(logging.WARNING, "qt-tests"):
        qt_logger.warning("Hello World")

assert len(caplog.records) == 1
assert caplog.records[0].levelname == "WARNING"
assert caplog.records[0].message == "Hello World"
```

被过滤的三个输入也直接来自原测试参数化用例：

```python
@pytest.mark.parametrize("line", [
    "Hello",
    "Hello World",
    "  Hello World  ",
])
```

### 核心代码：当前独立功能 verifier

当前 verifier 把相同契约放到独立的 `verifier/verifier.py`，只导入新模块并观察日志输出：

```python
from qutebrowser.utils import qtlog

with qtlog.hide_qt_warning("Hello", "qt-tests"):
    with caplog.at_level(logging.WARNING, "qt-tests"):
        qt_logger.warning(line)

assert not caplog.records
```

未匹配消息则要求 level 和原文都保持不变：

```python
assert len(caplog.records) == 1
record = caplog.records[0]
assert record.levelname == "WARNING"
assert record.message == "Hello World"
```

## 4. 是否完成了从实现绑定到面向功能？

**是。**

- 测试入口是用户/调用方能使用的 `qtlog.hide_qt_warning`，结果是日志系统中“有一条什么内容的记录”或“没有记录”。
- 过滤规则用三种实际消息形状验证，尤其覆盖最容易遗漏的首尾空白情形。
- Base 版本无法通过，Gold 版本和两轮稳定回放均通过；两个负向候选只改变过滤语义，也被 F2P 捕获。这表明测试在验证“过滤行为”，而不是验证文件搬迁或某个函数体。

**现实依据**：Qt 经常输出大量已知、无害的 warning；应用需要暂时隐藏指定前缀，同时不能吞掉其他 warning，也不能篡改 level 和文字。日志捕获结果就是调用方实际能观察到的效果。

**残余边界**：instruction 还写明 `QtWarningFilter` 可独立构造，但四条 converted F2P 通过 context manager 间接覆盖它，没有单独断言构造函数签名。该类契约在当前实现和 QA 证据中成立，但若要把它作为独立公共 API 长期承诺，后续可增加一条直接构造/`filter(record)` 的测试；这不影响本次四条源 F2P 的完整映射。

## 5. 取证位置

- 原 problem statement：`runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c/source/public/problem_statement.md`
- 当前 instruction：同一 run 下的 `final_task/instruction.md`
- 原始 F2P 与 selector：`source/restricted/original_test.patch`、`source/restricted/resolved_test_selectors.json`
- 当前 verifier：`final_task/tests/test.patch` 中的 `verifier/verifier.py`
- F2P 映射与审查报告：`review/f2p_mapping.csv`、`review/conversion_report.md`
- 稳定回放与语义结果：`review/metrics.json`、`review/progress.json`
