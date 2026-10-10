# Framework issue: Converter format-error/API wait did not converge

- UTC 时间：2026-09-22T20:12:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`
- attempt：`attempt_007`

## 现象

Converter 在 100 个动作附近连续出现两次 `FormatError`，之后外层仍保持 `CONVERTING`；容器只剩环境保活进程，模型请求在等待 API 响应。未提交的 verifier 目录只有模型探索残片，没有进入 Judge/Hard Validator。

## 根因

这是 Converter 模型会话的格式错误和外部 API 长等待组合；不是 execution adapter 或 verifier semantic evidence。当前 controller 在该请求被中断前没有及时将未提交 BUILD 标记为失败。

## 影响

本次 attempt 无法形成可验证 revision，并消耗了额外等待时间。已保留 trajectory/progress/events 供审计，不复用不完整 artifact。

## 通用处理

中断该失效会话，清理本次任务的临时 Docker 环境，保留 attempt_007；后续用 fresh Prepare attempt 重新 BUILD。暂不把该数据特异的模型探索结果写入 verifier 或通用 prompt。

## 测试/状态

- attempt_007：Prepare PASS，但 Converter 未提交，未进入后续阶段。
- ospec execution adapter 的 Prepare 验证已在该 attempt PASS。
- 下一次 attempt 将重新执行 BUILD，并继续监控 format-error/API 收敛。
