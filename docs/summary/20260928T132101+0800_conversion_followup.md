# 转换框架后续修复与复验

时间：2026-09-28 13:21:01（Asia/Shanghai）

## 结论

本轮修复后，qutebrowser 和 Navidrome 都完成了从 Prepare、转换、Core Gate、QA 到
DeepSWE package smoke 的闭环。Navidrome fresh `attempt_008` 的最终报告为
`VERIFIED`，状态为 `PACKAGED`，revision 5 已发布到 `final_task`。

这次过程同时确认了两类不同问题：

1. `run.sh` 被 Go adapter 生成为 `go test /app/verifier/run.sh`，是框架的 artifact-runner
   选择错误；容器路径和挂载本身正确。
2. rev4 的 verifier 探针把 constructor/type 两个边界合并，是 verifier 构造缺陷；Semantic
   Judge 正确要求修复。
3. QA historical F2P 使用裸 Go selector（例如 `TestLastFM`），旧 runner 只接受
   `file::test`，错误淘汰了合法 positive candidate；这是框架 selector 兼容性缺陷。

## 修复

- Python、Node、Go functional adapter 根据 manifest target 后缀执行 `.sh/.bash`，否则使用
  对应语言 runner。
- Go selector runner 支持裸 `Test`、`Benchmark`、`Fuzz`、`Example` 名称：在 replay
  checkout 中解析唯一 `_test.go` package；不存在或多包歧义时明确失败。
- 架构和 process 记录已同步更新：
  - `docs/architecture.md`
  - `process/20260928T114544+0800_go_shell_functional_adapter_fix.md`

## Navidrome 证据

实例：
`instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e`

attempt_008/rev5：

- Core Gate：Base F2P fail；Gold F2P pass；Base/Gold P2P pass；重复结果 stable；setup、
  patch check、patch return code 均为 0。
- Positive QA：1 个结构不同的 alternative implementation 被判定为 `VALID`，current、
  historical F2P 和 P2P 均通过。
- Negative QA：2 个只违反一个已有封装边界的 mutant 被判定为
  `RELEVANT_NON_EQUIVALENT`，P2P 通过且 F2P 被拒绝。
- Package smoke：`setup_rc=0`、`test_rc=0`、`PASS`。
- 发布状态：`control/report.json` 为 `VERIFIED/PACKAGED`，`final_task` 已存在。

发布 instruction 明确描述 public boundary 和 observable behavior，末尾为
`INSTRUCTION_SCOPE: PASS`；没有 `/app`、历史 selector、Gold-specific 文件布局或 helper
绑定。`visibility_binding` 仅是内部可见性词汇 advisory，不是实现路径泄漏。

## 验证

- VerifierTrans 全量测试：`150 passed`。
- Go selector focused test：`2 passed`。
- Python compile：Go/Python/Node execution adapter 与 Go selector runner 均通过。
- qutebrowser fresh conversion：Core Gate、positive/negative QA、package smoke 均通过。

## 当前剩余边界

框架已经可以批量、可恢复、可审计地完成这两类数据，但“所有数据都可转换”仍不成立：

- 模型 endpoint 额度、认证和返回格式仍是外部依赖；余额不足应报告为 infrastructure，
  不能伪装成 verifier 失败。
- instruction audit 是有限模式扫描，Semantic Judge 和 positive/negative QA 仍需共同
  证明功能包容性。
- 未知语言、仓库服务、toolchain 或无法唯一解析的 selector 仍应在 Prepare/Replay 阶段
  明确失败，不能让 Converter 猜命令。
- QA 和 Go 大型仓库 replay 成本较高，批处理时需要继续使用有界 worker 和 frozen
  ExecutionSpec。
