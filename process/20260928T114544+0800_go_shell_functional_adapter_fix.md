# Go shell functional artifact adapter 修复

时间：2026-09-28 11:45:44 Asia/Shanghai

## 现象

Navidrome fresh attempt_008 的 revision 3 通过了 Prepare 和 artifact sanity，且 replay 日志显示：

- Base/Gold repo checkout 正确回到 `7fc964aec5d432480d76bb90eee14a09aca5125f`；
- `patch_check_rc=0`、`patch_rc=0`、`setup_rc=0`；
- Base/Gold P2P 均通过；
- Base/Gold F2P 均执行为：

```text
go test /app/verifier/run.sh
main module ... does not contain package .../verifier/run.sh
```

因此失败发生在容器内 functional entrypoint 的 runner 选择，不是 Docker mount、仓库路径、
patch 应用或模型额度问题。

## 根因

Verifier artifact 的实际文件是模型生成的可执行 `verifier/run.sh`。manifest 正确声明：

```json
{"functional_artifact":"run.sh","target":"verifier/run.sh"}
```

但 `deterministic/execution/go.py` 只按仓库语言生成 `go test <artifact>`。容器隔离只保证
命令在正确环境中运行，不能自动判断命令是否适合 artifact 类型；框架仍必须把
`ExecutionSpec`、manifest target 和 artifact suffix 组合成正确的容器内命令。

## 修复

2026-09-28 11:45 修改 Python、Node 和 Go execution adapter：声明为 `.sh` 或 `.bash` 的
functional artifact 统一由 `bash` 执行；其他 artifact 保留各语言 native runner。Replay 和
package 使用同一 adapter，因此 package smoke 不会重新引入不同的命令选择。

修复后的 Navidrome 命令为：

```text
cd /app/. && VERIFIER_REPO_ROOT=/app VERIFIER_ARTIFACT_ROOT=/app/verifier \
VERIFIER_CWD=/app/. bash /app/verifier/run.sh
```

路径仍由 manifest 解析并挂载到 `/app/verifier/run.sh`，只是 runner 从 `go test` 改为
`bash`。这是一项跨语言、按 artifact 类型判断的通用修复，没有加入 Navidrome 专用路径或
断言。

## 三层边界

```text
Prepare / ExecutionSpec
  → Replay container mount
      /app/verifier/run.sh
  → Adapter command selection
      bash /app/verifier/run.sh
  → artifact observable checks
      Base/Gold F2P result
```

Verifier 始终在 Docker 容器中执行。此次问题出在第二层：容器内的框架 runner 把一个 shell
脚本当成 Go package。容器化没有替代 execution adapter，它只提供隔离环境。

## 证据和后续验证

证据位于：

- `runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e/intermediate/attempts/attempt_008/validation/hard_replay/rev_003.json`；
- 同一 attempt 的 `prepare/logs/round_3_repeat_*_{base,gold}_f2p.log`；
- `converter/revisions/rev_003/manifest.json` 和 `run.sh`。

当前 revision 4 已重新生成 verifier。新 controller 进程必须使用修复后的 adapter 重新做
Core Gate；只有 Base F2P fail、Gold F2P pass、P2P pass、稳定，并完成 QA 与 package smoke，
才计为 Navidrome fresh conversion 成功。

## 2026-09-28 13:12 后续验证与第二项修复

新 controller 使用修复后的 adapter 恢复 attempt_008。rev4 的 Semantic Judge 发现了真实
的 verifier 构造问题：每个 Go service 只用一个编译单元同时探测 constructor 和 concrete
client type，任意一个符号仍存在时都会被另一个缺失符号的编译错误掩盖。rev5 将两类探针
拆开，sanity 和 instruction audit 均通过（仅有 visibility advisory）。

rev5 的确定性 Core Gate 结果为：Base F2P fail、Gold F2P pass、Base/Gold P2P pass，重复
两次稳定，所有 setup/patch return code 为 0。Positive QA 接受了一个结构不同的实现；
Negative QA 接受了两个只违反一个封装边界的 mutant。一次 QA 复放又发现框架问题：Navidrome
原始 F2P selector 是裸的 `TestLastFM`、`TestListenBrainz`、`TestSpotify`，旧 Go runner
只接受 `file::test`，导致合法 positive candidate 的 historical F2P 被错误标记为
`Invalid Go selector`。

`deterministic/execution/go_p2p_runner.py` 现会在 replay checkout 中查找裸 Go test 名称的
唯一声明 package；不唯一或不存在时返回明确错误，避免猜测。修复后同一个 candidate 的
historical F2P、current F2P 和 P2P 全部通过。最终 package smoke PASS，attempt_008 已发布
`final_task`，报告状态为 `VERIFIED`，state 为 `PACKAGED`。

本次证据：

- `validation/hard_replay/rev_005.json`：Core Gate accepted/stable；
- `qa/evidence.json`：1 positive、2 relevant non-equivalent mutants；
- `packaging/logs/smoke.log`：setup_rc=0、test_rc=0；
- `control/final.json`：revision 5、VERIFIED/PACKAGED。
