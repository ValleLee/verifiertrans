# F2P 映射与隐藏契约门槛修复

## 现象

qutebrowser 的 rev_004 能通过 Base/Gold、正负 QA 和打包，但最终 verifier 直接调用了 Gold 新增的 `FontFamilies.from_str`。此外，两条可观察的序列化 F2P 被静默 drop，Hypothesis 中的 `str(families)` 行为也没有进入功能测试。

## failure classification

- 类型：verifier semantic / artifact contract
- scope：framework-level

## 根因

1. Converter 只要求每个历史 selector 有 accounting 行，没有强制记录 behavior intent、functional surface 和 evidence。
2. Artifact gate 没有禁止无理由 drop。
3. Semantic probe 没有读取最终生成的 `tests/test.sh`，因此没有可靠检查 verifier 使用的符号来源。
4. Converter prompt 把 Gold-only serialization 归入可 drop 范围，导致 observable behavior under-conversion。

这些问题不依赖当前 repo 的具体名称，任何任务都可能因为相同的 F2P accounting 和构造证据混用而发生。

## 通用修复

- Converter 每条 F2P 必须输出 `behavior_intent`、`functional_surface`、`evidence`、`decision`、`emitted_tests` 和 `rationale`。
- `rewrite`/`merge` 必须有 emitted tests；`manual_review` 不得伪装成已转换；`drop` 必须提供 `drop_justification`。
- Artifact contract 现在校验上述 schema，并拒绝静默 drop。
- Semantic Base probe 读取最终 verifier 的 test.sh/run_script.sh，并将 Base 不存在、Problem Statement 未声明的 Gold-only 方法视为隐藏契约风险。
- Converter prompt 要求默认 rewrite 或 merge，可观察的 serialization、ordering、error 和 side-effect 行为不得因原测试构造方式而丢失。
- Acceptance 拒绝包含 unresolved `manual_review` 的 revision。

## 验证方法

- `compileall` 检查共享 Python 代码。
- 对现有 qutebrowser rev_004 运行新 artifact/schema gate，应暴露旧 trace 缺少新字段；运行新 semantic gate 应检查最终 test.sh 中的符号来源。
- 重新创建 attempt 并运行 mini-swe converter、semantic review、hard replay、stability、positive/negative QA 和 package。

## 残余风险

本修复只提供 deterministic provenance 门槛；对于没有稳定公开或可观察边界的任务，Converter 仍可能输出 `manual_review`，此时 acceptance 会拒绝打包，需要人工决定任务是否可转换。
