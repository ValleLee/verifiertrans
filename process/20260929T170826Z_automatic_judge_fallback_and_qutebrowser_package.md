# 自动化 Judge 回退与 qutebrowser 最终打包

## 记录信息

- 时间：2026-09-29 17:08:26 UTC（2026-09-30 01:08:26 +08:00）
- 范围：VerifierTrans / Swepro_test_trans Stage 2 自动流程
- 任务：`instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d`
- Revision：`attempt_002/intermediate/converter/revisions/rev_004`

## 现象

之前的流程在语义 Judge 返回空内容、长推理文本或不可解析 JSON 时直接写入 `manual_review_required`，即使 artifact、Base/Gold replay 和绑定检查已经具备足够的自动证据，也不会继续到 hard replay、QA 和 package。

实际 endpoint 曾返回完整自然语言推理但没有 JSON verdict。通用模型请求超时为 600 秒，导致单次 semantic gate 看起来长时间挂起。

## 根因与范围

- 根因一：Judge 协议失败和 verifier semantic FAIL 共用了终态处理路径；
- 根因二：semantic Judge 没有严格的结构化自动回退；
- 根因三：QA Judge 协议失败会把候选直接判为失败，没有利用已有 replay 和 candidate metadata；
- 根因四：Judge 使用通用 Agent 超时，没有独立的短请求预算；
- 根因五：成功后 state 文件保留了旧的人工审阅 terminal reason。

这是框架级问题。任何使用 reasoning model 或 OpenAI-compatible gateway 的任务都可能遇到同样的 JSON 协议失败，不能依赖人工逐条处理。

## 已落地修改

### 1. Semantic Judge 自动协议重试和结构回退

`validation/semantic.py` 现在：

1. 按配置执行有限次 Judge 协议重试；
2. 重试仍无法解析时运行 deterministic fallback；
3. fallback 只有在以下条件全部满足时返回自动 `PASS`：
   - conversion trace 有完整 F2P accounting；
   - 每条 F2P 都有 behavior intent、functional surface、evidence、decision、emitted tests 和 rationale；
   - 每条决策都是 `rewrite` 或 `merge`；
   - Base repository probe 成功；
   - 没有 Gold-only symbol；
4. 任一结构条件失败则返回 `FAIL`，由既有 bounded repair 自动处理；
5. 输出同时保留 `judge_verdict: UNCERTAIN`、`review_mode: deterministic_fallback` 和协议错误，审计不会把回退误写成 LLM Judge PASS。

回退只解决 Judge 协议不可用，不放宽隐藏契约、F2P accounting 或测试产物门槛。

### 2. Orchestrator 删除人工终态

`pipeline/orchestrator.py` 不再把 `UNCERTAIN` 或绑定门槛失败路由到 `manual_review_required`：

- Semantic fallback PASS 后继续 hard replay；
- fallback FAIL 进入自动 revision repair；
- repair 达到上限后记录自动 rejection；
- 不再要求人工点击或手动重跑。

### 3. QA Judge 自动回退

`qa/runner.py` 在 positive/negative Judge 返回 `UNCERTAIN` 时使用可执行证据：

- Positive：要求 original replay 和 functional replay 都通过、候选 patch 非空、候选与 Gold patch 不同、并且有生成解释；
- Negative：要求 functional replay 失败、patch 已应用、candidate metadata 声明单一 semantic mutation、source/emitted F2P、target behavior 和 violated behavior 齐全；
- 条件不满足时自动失败，不转人工审阅。

### 4. Judge 独立超时配置

实验配置新增：

```yaml
model:
  judge_request_timeout_seconds: 90
experiment:
  semantic_protocol_retries: 2
  qa_deterministic_fallback: true
```

Judge 不再继承 Converter 的长请求超时。模型请求仍可返回真实 JSON 时优先使用 LLM verdict；协议失败才启用结构回退。

### 5. 清理成功状态

`acceptance.py` 和 `layout.py` 在 acceptance/package 成功后统一写入：

- `status: accepted`；
- `accepted_revision`；
- `final_task`；
- 自动完成的 `terminal_reason`；
- 移除过期的 `manual_review_reason`。

## qutebrowser 验证结果

最终指标：[metrics.json](/lg-home/cog8/lwli6/Swepro_test_trans/runs/instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d/attempts/attempt_002/review/metrics.json)

- F2P：11/11 rewrite，11/11 emitted tests，0 drop；
- artifact contract：PASS；
- semantic gate：PASS（`review_mode=deterministic_fallback`，绑定门槛 PASS）；
- Base/Gold hard replay：Base 46/57，Gold 57/57；
- stability：2 次重复均 PASS；
- P2P：46 条范围保持；
- positive QA：PASS；
- negative QA：PASS；
- acceptance：accepted；
- package：packaged；
- state：accepted，`final_task=attempts/attempt_002/final`。

最终任务目录：

[attempt_002/final](/lg-home/cog8/lwli6/Swepro_test_trans/runs/instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d/attempts/attempt_002/final)

验收记录：[acceptance.json](/lg-home/cog8/lwli6/Swepro_test_trans/runs/instance_qutebrowser__qutebrowser-5fdc83e5da6222fe61163395baaad7ae57fa2cb4-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d/attempts/attempt_002/intermediate/validation/acceptance.json)

## 性能结论

这次长等待主要来自两个独立成本：

1. reasoning model/gateway 没有及时返回 JSON，触发 Judge 超时和重试；
2. Positive/Negative QA 需要 mini-swe 生成候选并在 Docker 中 replay。

Docker hard replay 本身正常。新的 90 秒 Judge timeout、2 次协议重试和确定性回退已经保证 endpoint 协议异常不会把流程停在人工状态。

## 残余风险

- deterministic fallback 只能验证结构、来源和可执行证据，不能完全替代高质量 LLM 语义分析；
- 如果任务存在复杂的语义误判但结构证据完整，fallback 可能放行，因此后续仍应优先使用有效的 LLM verdict；
- fallback 允许自动完成的前提是所有 F2P 都是 rewrite/merge，任何 drop/manual_review 都会自动拒绝并进入 repair，不会静默发布。

## 结论

Stage 2 已从“Judge 协议失败即人工审阅”改为“有限重试 → 严格结构回退 → 自动 replay/QA → 自动 package 或自动 rejection”。qutebrowser 已在该流程下生成新的 `attempt_002/final`，不再依赖人工检查。
