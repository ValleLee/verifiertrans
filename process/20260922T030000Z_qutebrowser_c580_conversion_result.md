# qutebrowser-c580 首次完整转换结果

## 结果

该任务已经在 VerifierTrans 新项目中完成一次从 Prepare 开始的完整转换，最终状态为 `VERIFIED / PACKAGED`。

- instance：`instance_qutebrowser__qutebrowser-c580ebf0801e5a3ecabc54f327498bb753c6d5f2-v2ef375ac784985212b1805e1d0431dc8f1b3c171`
- attempt：`attempt_001`
- final verifier：`rev_002`
- F2P：11 条全部 accounting
- P2P：191 条，统一 replay
- verifier hash：`sha256:465e7a96d37d354c399e117d46f73ea6b41b36f62ca90b2c539eb2e1020c2535`

## Gate 与 QA

- Semantic Judge：rev2 PASS
- Hard Validator：PASS，重复执行 2 次稳定
- Base + converted F2P：FAIL
- Gold + converted F2P：PASS
- Base/Gold + P2P：PASS
- Positive QA：1 个 VALID alternative，P2P/F2P 均 PASS
- Negative QA：2 个 `RELEVANT_NON_EQUIVALENT` mutant，P2P PASS、converted F2P FAIL
- package smoke test：PASS

两个 negative mutant 都针对历史 F2P `tests/unit/components/test_hostblock.py::test_subdomain_blocking`，将父域名感知的阻断改为精确 host 匹配；这说明 verifier 能拒绝一个保持大部分行为、但遗漏该 F2P 语义的近似错误实现。

## 产物位置

- 最终 task：
  `runs/<instance_id>/final_task/`
- 完整中间过程：
  `runs/<instance_id>/intermediate/attempts/attempt_001/`
- 机器验收报告：
  `runs/<instance_id>/intermediate/attempts/attempt_001/control/report.json`

## 本轮框架修复

本次转换暴露并已修复两类通用 plumbing 问题：

1. verifier current 目录是 symlink 时，artifact handoff 错误；`copy_tree` 现在解析目录 symlink 并支持安全覆盖复制。
2. candidate replay 的 framework runner 与 restricted selector 未放到 candidate 的 `/app` 相对路径；统一 runner 现在在执行前准备这两个相对路径，并把缺失 runner 分类为 infrastructure failure。

对应记录：

- `20260922T181500Z_framework_artifact_symlink_fix.md`
- `20260922T183000Z_framework_candidate_runner_fix.md`

这些修复没有修改历史数据或 verifier 语义，也没有把由 framework bug 产生的中间 attempt 当作新的语义 revision。
