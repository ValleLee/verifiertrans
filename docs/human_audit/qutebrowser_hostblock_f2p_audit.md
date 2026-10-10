# qutebrowser hostname widening / hostblock 转换审计

## 审计对象与结论

- 源实例：`qutebrowser__qutebrowser-c580ebf0801e5a3ecabc54f327498bb753c6d5f2-v2ef375ac784985212b1805e1d0431dc8f1b3c171`
- 发布版本：verifier revision 2（revision 1 的语义问题已修复）
- 结论：**通过，但有一个明确的测试隔离性注意点**。11 条源 F2P 均可追溯地转换为 11 次功能测试执行：7 条 hostname 输出契约、3 条 benchmark smoke、1 条父域拦截集成行为。最终版本不再把未由 F2P 支持的 whitelist 行为塞入 instruction，也没有把 benchmark 改写成无来源的精确结果断言。

最终评分器同样对整个功能组做 aggregate F2P 计分；`tests/config.json` 中列出的 11 个源 node id 是追溯元数据，并非最终测试文件中的 pytest 名称。另有 191 条源 P2P，通过 exact-node runner 原样执行。

## Problem statement → instruction

### 原始 problem statement

原题指出 hosts-based blocking 只做 hostname 精确匹配：封禁 `example.com` 时，`sub.example.com` 和更深层子域不会被封禁。原题还说明 whitelist 应优先于 blocklist，并且建议从请求 host 得到“逐层去掉最左 label”的 widened hostname 序列，在运行时和配置的 blocked sets 中寻找匹配。

### 当前 instruction

当前 instruction 有两部分：

1. 公共 helper `qutebrowser.utils.urlutils.widened_hostnames(hostname)` 返回可迭代字符串：依次返回输入 hostname 和逐层去掉最左 label 的父域，直到空字符串；明确列出 `a.b.c`、单标签、空串、前/后点、`None` 的七个参考案例。
2. 在 hosts-based blocking 已启用时，只要请求 host 或其任一 widened parent 在配置的 blocked-host sets 中，必须阻止请求；`example.com` 必须覆盖其子域和更深子域。

Scope boundary 要求不要改变既有开关、host-list parsing、download handling 和其他 urlutils/configutils 行为。

### 差异分析

| 维度 | 原始 problem statement | 当前 instruction | 审计判断 |
| --- | --- | --- | --- |
| 核心 bug | 精确匹配不覆盖子域 | 明确父域匹配覆盖子域 | 完整保留并可验证。 |
| helper API | 只提“widened sequence” | 指定公开 `urlutils.widened_hostnames` 和七例 | 源 F2P 迁移 helper 时已经以此公开 API 和七例断言，属必要具体化。 |
| whitelist 优先级 | 原题明确要求 | 最终 instruction 未要求 | 合理收缩：该项没有源 F2P；仍有继承 P2P `test_blocking_with_whitelist` 覆盖回归，但不被冒充为新增 F2P 契约。 |
| benchmark | 原 F2P 仅计时三个 host | 当前没有把它们写为输出规则 | revision 2 正确地只保留 smoke 调用。 |

这项收缩尤其重要：revision 1 曾把 whitelist 写入 instruction，并把三个 benchmark 改为精确输出断言；语义审查判为 REPAIR。revision 2 删除前者、将后者恢复为 smoke，语义审查为 PASS，当前发布物即 revision 2。

## F2P：原始测试与当前功能测试

### 原始 F2P（11 个 node）

| 类别 | 数量 | 原始测试方式 |
| --- | ---: | --- |
| 子域封锁 | 1 | `test_subdomain_blocking` 直接改私有 `_blocked_hosts`，调用私有 `HostBlocker._is_blocked(QUrl(...))`，断言 `example.com` 封锁 `subdomain.example.com`。 |
| widening 输出 | 7 | 从 `configutils._widened_hostnames` 搬到 `urlutils.widened_hostnames` 后，逐例比较 `list(...)` 与预期序列。 |
| widening benchmark | 3 | 对三个 hostname 调用 `benchmark(lambda: list(...))`；它只计时，没有结果断言。 |

### 当前 F2P（11 次 pytest 执行）

| 源 F2P | 当前功能测试 | 从哪里变成了什么 |
| --- | --- | --- |
| 7 个 `TestWiden::test_widen_hostnames[...]` | 参数化 `test_widened_hostnames`（7 例） | 从对公开 helper 的精确序列断言，变为同一公开 helper、同一输入输出契约；语义不变，测试路径统一到独立 verifier。 |
| 3 个 `test_bench_widen_hostnames[...]` | 参数化 `test_widened_hostnames_bench_smoke`（3 例） | 从 `pytest-benchmark` 计时，变为只调用 `list(urlutils.widened_hostnames(hostname))` 的 smoke；不虚构输出要求。 |
| `test_subdomain_blocking` | `test_hostblock_blocks_subdomain_of_blocked_parent` | 从私有集合 + 私有 `_is_blocked` 的白盒断言，变为写入 hosts 文件、`HostBlocker.read_hosts()`、`HostBlocker.filter_request(request)`，最后观察 `Request.is_blocked`。 |

最终 patch 中仍保留源测试 patch（包括测试从 `configutils` 搬至 `urlutils` 的改动），使源测试文件和 191 条 P2P selector 可以正确应用/运行；converted F2P 实际执行的是 `verifier/test_functional.py`。

## 是否已从实现导向改为功能导向？

**整体是，且子域封锁这一条的改进最明显。**

- `widened_hostnames` 七例只检查公开函数的产出序列；没有断言 `split`、`partition`、循环结构或其他内部算法。接受记录也确认一个采用 `split/join + set.isdisjoint`、不同于 Gold 的实现可通过。
- 子域测试不再写 `host_blocker._blocked_hosts.add(...)` 或调用 `_is_blocked`，而是经过可观察的加载、请求过滤、`request.is_blocked` 结果。这直接验证用户可感知的封锁效果。
- 3 个 benchmark 没有被伪装成功能断言：原来没有 oracle，当前也没有强加 oracle。
- 两个 mutant 都把逻辑退回“只检查精确 host”；当前 F2P 均拒绝它们，说明测试锁定的是父域匹配的功能，不是 Gold 的具体代码形状。

**注意点（非阻断结论）：** 子域集成测试仍 monkeypatch 了 `qutebrowser.api.config.val/get` 以构造最小配置。这是隔离 qutebrowser 配置系统的测试支架，而非对待测修复的实现断言；但若未来 HostBlocker 改变从 config API 读取配置的方式，测试可能需要同步维护。它的稳健性弱于端到端真实配置测试，但不改变本次“避免私有 `_is_blocked` / `_blocked_hosts` 绑定”的结论。

## 回放与风险

revision 2 的两轮回放均为 Base F2P 失败、Gold F2P 通过，Base/Gold 的 191 条 P2P 都通过；semantic review revision 2 为 PASS，且无 unconverted F2P、overreach 或 mapping gap。风险边界如下：

- whitelist precedence 保留在 P2P 回归覆盖中，未成为 converted F2P 的独立功能断言，因此不要将本 F2P 的通过解读为对该优先级的专门验证。
- 3 条 benchmark 仅验证可调用，不验证性能阈值；这忠实于源测试的性质。

## 取证位置

- 原 statement：`intermediate/attempts/attempt_001/source/public/problem_statement.md`
- 原 F2P patch/selectors：`source/restricted/original_test.patch`、`source/restricted/resolved_test_selectors.json`
- 当前 instruction/测试：`final_task/instruction.md`、`final_task/tests/test.patch`
- revision 1/2 语义结果：`validation/semantic/rev_001.json`、`validation/semantic/rev_002.json`
- 接受与回放记录：`control/report.json`
