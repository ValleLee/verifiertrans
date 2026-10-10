# VerifierTrans Round 2 follow-up audit

**时间**：2026-09-28 01:31 +0800  
**范围**：框架通用性修正、fresh Navidrome attempt、模型端故障分类、既有产物回归审计

## 已完成

- Converter 和 Semantic Judge prompt 已统一为 public API / observable behavior 约束；具体 private type、constructor、method、package path、历史 selector、Gold file layout、mock call shape 和 AST/name heuristic 不应进入 solver-facing instruction。
- 新增 deterministic instruction hard audit，并把 visibility 绑定作为 advisory 证据；4 个既有 published final_task 均未触发 hard error。Navidrome 旧产物仍触发 visibility advisory，说明它仍需 fresh rerun 才能证明 prompt 修正已落地。
- Package grader 增加 `patch-paths`，空 P2P 明确记录为 `source_empty_noop`，不再制造占位节点。
- Prepare CLI 对 `--data` 做 fail-closed 存在性检查；空路径会在 worker 启动前失败。
- Controller 对模型端 HTTP 400/401/402/403/404、余额、认证和权限错误分类为不可重试的 `infrastructure / MODEL_ENDPOINT`，避免把外部服务故障误转成 Converter REPAIR。
- VerifierTrans 测试：`144 passed`；新增 orchestrator/session 回归：`19 passed`；既有 4 个 final_task 的 instruction audit：hard errors 均为空。

## Fresh run 证据

Navidrome 创建了新的 `attempt_006`，Prepare source/environment preflight PASS，仓库物化 PASS（123799 files，836M）。Converter revision 1 调用外部模型时收到 HTTP 402 `Insufficient Balance`；旧 controller 曾错误推进到 revision 2，已停止该 run 并修复分类逻辑。由于模型端余额不足，Navidrome 尚未完成 Semantic Judge、Hard Validator、QA、package smoke 和 final_task 发布。

qutebrowser 尚未启动 fresh model-driven run；在当前模型端点恢复前启动不会增加有效验收证据。

## 当前剩余问题

1. **外部模型端点不可用（阻塞端到端验收）**：配置的模型组返回 402，导致本轮无法证明新 prompt 能否把 Navidrome 从具体 unexported 名称改成外部契约，也无法再次转换 qutebrowser。
2. **DeepSWE evaluator 合约仍不完整**：生成 grader 已有 `prepare`、`grade`、`patch-paths`，但 node-level report 解析和 partial reward 合约尚未与参考 grader 完全对齐；需要真实 evaluator integration smoke。
3. **空 P2P 是合法但需显式消费的情况**：Navidrome/Tutanota 这类任务没有 retained P2P，当前 package 可发布，但外部评测策略仍应明确 `source_empty_noop` 是否接受。
4. **批量稳定性尚未有统计证据**：`verifier-trans batch` 具备有界调度，但目前只有 4 条历史闭环，且模型余额/限流/超时等服务侧故障仍会限制批量吞吐；应在端点恢复后用 fresh matrix 记录成功率、重试次数和每阶段耗时。
5. **可观测性仍需加强**：instruction audit 已写入 verifier evidence，但 batch summary 尚未汇总 hard/advisory binding 计数，后续应把它加入批次报告。

## 下一步建议

- 恢复或切换到有余额且已授权的模型端点后，仅从新的 Prepare attempt 继续 Navidrome 和 qutebrowser；验收新 instruction、`instruction_audit`、Hard Validator、两类 QA、package smoke 和 final_task。
- 为 `MODEL_ENDPOINT` 增加按错误码的 metrics（不可重试计数、重试计数、首个失败时间），并让 batch 在遇到该类失败时快速汇总而不是继续占用并发槽位。
- 增加 DeepSWE 真实 evaluator integration smoke，覆盖 `patch-paths`、node-level report 和 partial reward；在此之前只宣称 package smoke 兼容。

Navidrome `attempt_006` was resumed after the controller fix and now terminates explicitly as `INFRASTRUCTURE / MODEL_ENDPOINT` with `retryable: false` in `control/state.json` and `run/final.json`; no downstream gate is counted as passed.

另外，controller 已取消“所有失败都进入 MANUAL_REVIEW”的模糊状态：自动流程现在使用 `FINAL_VALIDATED`、`INFRASTRUCTURE`、`PACKAGE` 或 `FAILED`，当前 Navidrome attempt 的 report 已同步为 `INFRASTRUCTURE / MODEL_ENDPOINT`。

qutebrowser 已创建 fresh `attempt_004`，source/environment preflight 和物化通过（4 F2P、52 P2P，936 files/20M）。它尚未调用模型，等待唯一配置端点恢复；不复用旧 attempt 的 verifier/evidence。

最终回归：VerifierTrans 全量测试 `149 passed`。当前实现没有自动人工审核队列；失败会落到显式终态。

qutebrowser fresh `attempt_004` 已完成 Converter、Semantic 和 Hard Gate：Base F2P FAIL、Gold F2P PASS、Base/Gold P2P PASS、stable PASS（4 F2P / 52 P2P）。Positive QA 随后收到 HTTP 402；controller 已新增 QA 阶段的不可重试端点终止逻辑，避免继续消耗 solver attempts。

QA 终止逻辑加入后的全量回归：`150 passed`。

qutebrowser `attempt_004` 已用修复后的 controller 恢复并终止为 `INFRASTRUCTURE / MODEL_ENDPOINT`；它保留本 attempt 自身的 Core Gate PASS 证据，没有伪造 Positive/Negative QA 或 package 成功。

模型端点曾短暂接受最小健康请求，但 Navidrome fresh `attempt_007` 的大上下文 Converter 在提交前再次收到 HTTP 402；controller 已正确终止，没有把 partial session 当成 verifier 成功。剩余阻塞仍是服务 quota。
