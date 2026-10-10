# Candidate replay root-relative runner 修复

## 发现

OpenLibrary 第二条任务的 Positive QA 候选全部在 deterministic precheck 失败。日志中的实际原因是候选 verifier 使用：

```text
SCRIPT_DIR=/verifier
WS_ROOT=/
python3 framework/p2p_runner.py restricted/resolved_test_selectors.json
```

因此 runner 被解析为 `//framework/p2p_runner.py`。这属于候选 replay 的挂载契约问题，不是 candidate 语义问题，也不应消耗 Positive QA 的候选次数。

## 修复

`src/verifier_trans/deterministic/replay/candidate.py` 现在同时提供：

- `/app/framework/p2p_runner.py`
- `/workspace/framework/p2p_runner.py`
- `/framework/p2p_runner.py`
- `/app/restricted/resolved_test_selectors.json`
- `/workspace/restricted/resolved_test_selectors.json`
- `/restricted/resolved_test_selectors.json`

这样候选 `run.sh` 无论从 `/app`、role workspace，还是由 `/verifier` 推导到 `/`，都能使用框架提供的相对路径。增加了 `test_candidate_replay_mounts.py`，相关 3 个 unit tests 已通过。

修复不依赖具体仓库、任务或测试 selector；后续应复用本次已经生成的候选，不能将这次 infrastructure failure 当作新的 verifier revision。
