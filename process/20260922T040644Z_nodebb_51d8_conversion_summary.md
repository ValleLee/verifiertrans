# NodeBB 51d8f3 conversion summary

## 任务与最终产物

- instance：`instance_NodeBB__NodeBB-51d8f3b195bddb13a13ddc0de110722774d9bb1b-vf2cf3cbd463b7ad942381f1c6d077626485a1e9e`
- dataset：`/lg-home/cog8/lwli6/Data/swebench_pro/test-00000-of-00001.parquet`
- attempt：`attempt_002`（`attempt_001` 因 Docker 权限导致 materialization 不可信，未进入模型转换）
- verifier revision：`rev1`
- verifier hash：`sha256:f4cd00404364e1f7e7b787f00a9906afdcbf3c153e2d7a7b0966f2524d3ca015`
- final status：`VERIFIED / PACKAGED`
- final task：`/lg-home/cog8/lwli6/VerifierTrans/runs/instance_NodeBB__NodeBB-51d8f3b195bddb13a13ddc0de110722774d9bb1b-vf2cf3cbd463b7ad942381f1c6d077626485a1e9e/final_task`
- machine report：`/lg-home/cog8/lwli6/VerifierTrans/runs/instance_NodeBB__NodeBB-51d8f3b195bddb13a13ddc0de110722774d9bb1b-vf2cf3cbd463b7ad942381f1c6d077626485a1e9e/intermediate/attempts/attempt_002/control/report.json`

## 转换结果与验收

- Prepare/source preflight：PASS；base commit `da2441b9bd293d7188ee645be3322a7305a43a19` 已由 Docker materialize，4 条 F2P 和 182 条 P2P selector 均解析。
- F2P accounting：4/4；每条均写入 `conversion_trace.json`、`conversion_log.md` 和 `coverage_matrix.md`。
- Semantic Judge：PASS；`unconverted_f2p=[]`、`overreach=[]`、`mapping_gaps=[]`。
- Hard Validator：PASS 且 repeat=2 stable；Base F2P FAIL，Gold F2P PASS，Base/Gold P2P PASS。
- Positive QA：`positive_1_attempt_1`，3 个文件，deterministic P2P/F2P PASS，Judge `VALID`；结构使用独立 webfinger controller 和直接 route 注册，不依赖 Gold 文件布局。
- Negative QA：两个合格 mutant 均被拒绝：
  - `mutant_1_attempt_1`：缺少 `resource` 时返回 200 而非 400；P2P PASS、F2P FAIL，Judge `RELEVANT_NON_EQUIVALENT`。
  - `mutant_2_attempt_2`：缺少 `resource` 时返回 404 而非 400；P2P PASS、F2P FAIL，Judge `RELEVANT_NON_EQUIVALENT`。
- 最新 QA evidence：1 VALID positive、2 rejected mutants，均绑定 rev1 hash。
- package smoke：PASS；`setup_rc=0`、`test_rc=0`、未超时。

## 发现并修复的通用框架问题

1. Prepare materialization gate：Docker permission failure 曾因 stale `/tmp` repo 伪装成 PASS；现在 source gate 同时要求本次 materialization returncode=0、观测 HEAD 匹配 base commit、link 和目录有效。记录：`20260922T025500Z_framework_prepare_materialization_gate.md`。
2. JS replay entrypoint：Hard Validator 原先对 P2P 使用 Python-only runner，并从 `/verifier/run.sh` 导致 root-relative runner 找到 `/`；现在 F2P/P2P 都调用 `/app/verifier/run.sh`，由 verifier 自身进行语言分派。记录：`20260922T033000Z_framework_js_replay_entrypoint_fix.md`。
3. Redis runtime bootstrap：NodeBB image 内置 Redis，但 `/bin/bash` entrypoint 不启动它；replay 和 candidate runner 现在在命令可用且 Redis 未 ready 时启动 daemon 并等待 readiness。记录：`20260922T034000Z_framework_redis_runtime_bootstrap.md`。

上述修复均未修改 NodeBB verifier 语义；rev1 在修复后被复用并完成全部 gates。新增通用 replay regression tests：6 passed。

## 尚未解决的效率问题

- Converter 和 QA generator 仍会多次尝试被 workspace tool 拒绝的 host-absolute path，尤其 NodeBB 的 JS/Redis 任务使模型探索时间较长。
- JS environment preflight 目前只确认 repo/selector/container 基础条件，不做完整 Mocha/Redis collection；因此 toolchain/service 缺口要到 Hard replay 才暴露。
- `report.json` 中 package audit 显示 `audit_verdict=MISSING`，但 package replay 和 smoke 均 PASS；这属于现有 audit 输入缺失，不影响本次用户验收，后续可增加不依赖外部审计器的 package provenance 检查。
