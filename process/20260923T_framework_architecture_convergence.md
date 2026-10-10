# Framework issue: execution, artifact and QA contract convergence

## 现象

Prepare 已产生 `ExecutionSpec`，但 replay/candidate 仍会从 prepared repository
重新 discovery；Python/Go selector command 未使用冻结 cwd；service bootstrap、超时
和 Package 的 verifier 入口存在旁路。Package 还会扫描 `functional_f2p.*` 或缺失
`test_files` 时扫描 verifier 目录。

## 关键 evidence

- `deterministic/execution/base.py` 原先在每次 `execution_plan` 调用时重新 discovery。
- replay/candidate 原先无条件调用 Redis bootstrap，并各自暴露重复 role mounts。
- Package 原先仅扫描 `functional_f2p.*`，并在 manifest 缺失 `test_files` 时扫描顶层源码。
- 计划文档要求一个 attempt 使用一个冻结 ExecutionSpec，manifest 成为正式 artifact
  唯一声明，Package 不重新发现 verifier。
- 修改前确定性测试基线为 121 passed；当前最新全量验证为 130 passed。

## failure classification / scope

`INFRASTRUCTURE`（执行契约旁路）与 `ARTIFACT_SCHEMA`（manifest/asset 声明缺失）
属于 framework-level；不是任何特定 instance、repo、test title 或 verifier filename
的问题。

## 根因

历史兼容路径把 discovery、文件名和目录结构当成了执行事实源；ExecutionSpec 只被
序列化，却没有统一反序列化/消费入口。QA 负向 replay 也没有一个显式的 deterministic
truth table 来区分 semantic rejection、false positive 和 infrastructure failure。

## 通用修复

- `ExecutionSpec.from_dict` 和稳定 hash；replay/candidate/package 使用 frozen spec。
- spec 纳入 timeout、startup timeout、kill grace、result parser 字段。
- replay/candidate/package smoke now gate optional service bootstrap and
  environment entries through the frozen spec instead of unconditional Redis
  startup.
- Python/Go selector command 遵守 spec cwd；service bootstrap 仅执行 spec 声明的服务，
  未知服务显式失败。
- manifest 存在时 functional artifact 必须由 `functional_artifact`/`functional_entrypoint`
  显式声明；Package 要求显式 `test_files`，不再目录扫描。
- Sanity now rejects missing/undeclared manifest files before Semantic Judge or Hard Replay;
  only declared `test_files` plus named audit files are accepted into a revision.
- Prepare 产出 `restricted/p2p_assets.json`；Package 机械消费该 derived asset list，
  并把 ambiguity 记录到 package report。
- Converter session workspace now separates disposable `scratch/` from formal `output/`;
  the old `verifier/` path is only a compatibility alias during the session.
- 新增 `negative_execution_contract`，确保 infrastructure failure 不路由到 Converter
  semantic repair，只有 qualified false positive 才触发 repair。

## 修改文件

- `src/verifier_trans/deterministic/execution/discovery.py`
- `src/verifier_trans/deterministic/execution/base.py`
- `src/verifier_trans/deterministic/execution/{python,go,services,__init__}.py`
- `src/verifier_trans/deterministic/replay/{verifier,candidate}.py`
- `src/verifier_trans/deterministic/preparation/prepare_instance.py`
- `src/verifier_trans/deterministic/packaging/{package_task,package_smoke}.py`
- `src/verifier_trans/pipeline/{qa,orchestrator}.py`
- `tests/unit/test_architecture_convergence.py`

## 验证方法与结果

- `python3 -m compileall -q src tests`：PASS
- `./.venv/bin/pytest -q`：130 passed
- 未启动新的转换、instance、外部模型或跨语言 E2E。

## 残余风险

- 没有 fresh Docker E2E，不能把现有语言 adapter 晋级为 supported。
- 直接调用 adapter 的无 manifest/无 spec 兼容分支仍保留，便于读取旧 runs；新的
  package 主路径在进入 adapter 前拒绝这些旧形状。
- replay/candidate 的 role mounts 仍保留历史兼容路径，下一轮可在不改变语义的前提下
  统一构造；本轮未做大规模 runtime 重写。
