# Semantic Judge protocol and revision handoff repair

## 现象

语义 Judge 在完整 construction evidence 上经常返回长 reasoning 文本而不是合法 JSON。旧流程把 `UNCERTAIN` 当成可继续的结果，导致一个绕过 historical parser 行为的 verifier 进入 replay 和 packaging。随后压缩 evidence 后，Judge 能返回明确 FAIL，并发现 revision 直接绑定了未由 Problem Statement 声明的 Gold-only 方法。

## Failure classification

- 第一问题：framework-level, semantic protocol / orchestration。
- 第二问题：verifier semantic，属于当前 revision；不能通过放宽框架门槛解决。
- Agent 收尾阻塞：framework-level, mini-SWE subprocess / Docker handoff。

## 根因

1. reasoning 模型的完整输入过大，输出预算被分析文本消耗，JSON 解析失败。
2. deterministic fallback 过去只检查结构完整性，结构通过时可能错误接受 `UNCERTAIN`。
3. agent 已经把 revision 文件写入共享目录，但 Docker 清理或提交 sentinel 没有及时返回，controller 只看进程返回码。

## 通用修复

- semantic Judge 使用压缩 evidence，并在协议失败时重试紧凑 JSON 请求。
- 所有无法得到合法语义判定的结果自动 FAIL，进入 Converter REPAIR；不得由结构门槛替代语义审查。
- repair controller 为 agent 子进程增加有界等待；超时后只有在 revision contract 文件齐全时才接管，随后仍运行正常 artifact/schema gate。
- semantic FAIL 的结构化 findings、mapping gaps、hidden contracts 和 unjustified drops 写入下一 revision 的 `repair_feedback.json`。

## 验证证据

- rev_004 的 semantic Judge FAIL：测试通过 `QtFont.to_py` 绕过 `FontFamilies` 解析。
- rev_005 的 semantic Judge FAIL：测试直接绑定 `configutils.FontFamilies.from_str`，该方法未在 Problem Statement 中声明。
- rev_006 已由自动 repair 创建，要求使用配置加载等公开可观察行为保留每条 F2P 的语义。
- `python3 -m compileall -q Swepro_test_trans/src` 通过。

## 影响范围

规则适用于所有 Harbor-to-Harbor 任务：不接受无法解析的语义判定；不因 agent 收尾阻塞丢失完整 revision；仍禁止把 Gold-only symbol 变成 verifier 契约。

## 残余风险

每个 revision 仍需通过 semantic Judge、artifact gate、Base/Gold replay、P2P、stability 和正负 QA。当前 qutebrowser rev_006 和新任务转换仍在运行，尚未形成最终 acceptance。
