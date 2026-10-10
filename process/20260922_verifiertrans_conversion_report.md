# VerifierTrans 两条任务转换实验报告

## 实验范围

本轮在独立项目 `/lg-home/cog8/lwli6/VerifierTrans` 中完成两条已下载镜像任务的完整 pipeline：

1. qutebrowser c580：验证较复杂 Python 任务以及 rev1 → rev2 语义修复路径。
2. OpenLibrary 4a5d：验证较小 Python 任务以及新框架 runner 契约的跨仓库复用。

两条任务均从 Prepare 开始，未复制或复用旧项目 `runs/` 产物。

## 最终结果

| instance | final verifier | F2P/P2P | Semantic | Hard | Positive | Negative | Package |
|---|---:|---:|---|---|---:|---:|---|
| qutebrowser-c580 | rev2 | 11 / 191 | PASS | stable PASS | 1 VALID | 2 FAIL | PASS |
| OpenLibrary-4a5d | rev1 | 1 / 8 | PASS | stable PASS | 1 VALID | 2 FAIL | PASS |

两条任务最终状态均为 `VERIFIED / PACKAGED`。

## Pipeline 证据

每条任务的正式产物统一位于：

```text
runs/<完整 instance_id>/
├── final_task/
└── intermediate/attempts/attempt_001/
```

核心机器报告：

- qutebrowser：`.../control/report.json`
- OpenLibrary：`.../control/report.json`

转换细节和每条 F2P 的映射分别保存在各自：

```text
intermediate/attempts/attempt_001/converter/current/conversion_trace.json
intermediate/attempts/attempt_001/converter/current/coverage_matrix.md
```

## 本轮发现并修复的通用框架问题

### 1. verifier symlink artifact handoff

Converter 的 current verifier 通过 symlink 暴露时，原复制逻辑直接调用 `copytree` 导致 `FileExistsError`。已在 `pipeline/artifacts.py` 中解析目录 symlink 并使用安全覆盖复制；qutebrowser rev1 被确定性恢复，没有把 plumbing bug 计为语义 rev2。

记录：`process/20260922T181500Z_framework_artifact_symlink_fix.md`

### 2. candidate replay runner 挂载契约

候选 replay 以前只提供 `/app/framework` 和部分 workspace 路径；当 Converter 生成的 `run.sh` 从 `/verifier` 推导到根目录时，会访问 `/framework`，从而误报候选失败。现在 deterministic candidate runner 同时准备 `/app`、`/workspace` 和根相对路径所需的 framework runner 与 resolved selectors。

记录：

- `process/20260922T183000Z_framework_candidate_runner_fix.md`
- `process/20260922T031000Z_framework_root_relative_candidate_runner_fix.md`

### 3. QA candidate 的 infrastructure failure 不应消耗模型候选

已有的 candidate reuse 路径在本轮复用成功：框架修复后直接重新 replay 原候选，并进入 Judge；没有因为 deterministic harness 错误而重新生成候选。

## 观察到但未影响正确性的效率问题

OpenLibrary Converter 前期花费了较多 actions 探测 mini-swe-agent 的路径安全规则，留下了 live verifier 中的临时 probe 文件；这些文件没有进入最终 `final_task/tests/test.patch`，但说明 workspace contract 还可以更明确地向 agent 提供固定的 verifier 执行入口，减少无效探索。它属于效率/清理优化，不是本轮验收阻塞，也没有为此修改数据特定逻辑。

## 结论

在当前两条不同规模、不同仓库的 Python 任务上，框架已经完成了从数据解析、Converter、Semantic Judge、Hard Validator、Positive/Negative QA 到 package smoke 的完整闭环。结果同时满足：

```text
Gold PASS
+ valid alternative PASS
+ near-correct invalid mutants FAIL
```

本轮没有发现需要继续修改 verifier 语义的通用问题；已修复的代码变更集中在 artifact handoff 与 candidate replay infrastructure。
