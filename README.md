# VerifierTrans

VerifierTrans 将 SWE-Bench Pro 的 historical F2P 测试转换为基于可观察行为的
functional verifier。单一 Converter 只负责把历史测试语义化；确定性的 Hard Validator
execution adapter 负责 Docker cwd、mount、语言 runner、selector replay 和可选 Redis
启动。这样 verifier 的“测什么”和执行环境的“怎么运行”保持分离。


详细架构见：[docs/architecture.md](docs/architecture.md)。

## Pipeline

~~~text
Prepare / source + environment preflight
  → Converter BUILD
  → deterministic sanity
  → fresh Semantic Judge
  → Hard Validator execution adapter
      → Base/Gold F2P
      → Base/Gold P2P
      → stability
  → replay accumulated QA evidence
  → Positive QA + Negative QA
  → Converter REPAIR + evidence replay（发现 verifier 缺陷时，循环）
  → package + package smoke
  → atomic final_task publication
~~~

Converter 只有 BUILD 和 REPAIR 两种 mode，没有独立的 design agent。Prompt 位于
prompts/；确定性准备、执行、replay、验证、报告和 packaging 位于
src/verifier_trans/deterministic/。

Positive QA 先要求 candidate 的 retained P2P 通过、current F2P 可运行、结构上不同且没有
基础设施失败，再交给 Solution Judge；current F2P 此时可以是可运行的语义失败，用于发现
verifier false negative。Judge 判为 VALID 后会重新 replay current F2P/P2P：只有两者都通过
才接受 Positive；若有效 candidate 被 current F2P 拒绝，则回到 Converter REPAIR。historical
F2P 始终只是 audit 证据，PASS、FAIL 或基础设施不可运行都不决定 Positive validity。
当前 Positive evidence contract 为 v5。Negative candidate 必须是只违反一个已映射 F2P
语义的 near-correct mutant，且被当前 verifier 拒绝。

## Installation

API 配置保存在本地 .env，不会提交到 Git：

~~~bash
cd /lg-home/cog8/lwli6/VerifierTrans
/lg-home/cog8/lwli6/.local/share/uv/python/cpython-3.12-linux-x86_64-gnu/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
chmod 600 .env
~~~

锁定依赖可用：

~~~bash
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -e . --no-deps
~~~

## CLI

先 Prepare 一个全新的 attempt：

~~~bash
cd /lg-home/cog8/lwli6/VerifierTrans

INSTANCE_ID='instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan'
RUNS_ROOT='/lg-home/cog8/lwli6/VerifierTrans/runs'
DATA='/lg-home/cog8/lwli6/Data/swebench_pro/test-00000-of-00001.parquet'

.venv/bin/verifier-trans prepare \
  --data "$DATA" \
  --instance-id "$INSTANCE_ID" \
  --runs-root "$RUNS_ROOT" \
  --materialize-repo \
  --timeout 1800
~~~

开始一次转换：

~~~bash
.venv/bin/verifier-trans run \
  --instance-id "$INSTANCE_ID" \
  --runs-root "$RUNS_ROOT" \
  --env-file /lg-home/cog8/lwli6/VerifierTrans/.env \
  --config /lg-home/cog8/lwli6/VerifierTrans/configs/experiment.yaml \
  --allow-external-model-data
~~~

allow-external-model-data 是显式授权开关；没有它，model-backed conversion 会被拒绝。
框架会自动调用 Docker，但 Converter/QA 容器和 replay 容器职责不同：Converter 容器用于
repo 探索和 artifact 写入，replay 容器从 /app 运行真实项目，把 verifier 挂载到
/app/verifier，并使用 /framework 的框架 runner。

如果已经 Prepare 过，只恢复最新 attempt：

~~~bash
.venv/bin/verifier-trans resume \
  --instance-id "$INSTANCE_ID" \
  --runs-root "$RUNS_ROOT" \
  --env-file /lg-home/cog8/lwli6/VerifierTrans/.env \
  --config /lg-home/cog8/lwli6/VerifierTrans/configs/experiment.yaml \
  --allow-external-model-data
~~~

恢复会校验 Prepare、revision hash 和 execution contract，并尽量复用已有确定性
evidence；不会把旧格式 Positive evidence 当成当前 contract 的有效证据。

只重建审计报告，不会重新调用模型：

~~~bash
.venv/bin/verifier-trans report \
  --instance-id "$INSTANCE_ID" \
  --runs-root "$RUNS_ROOT"
~~~

实时进度：

~~~bash
tail -f "$RUNS_ROOT/$INSTANCE_ID/review/progress.md"
~~~

## Run layout

~~~text
runs/<instance_id>/
├── source/                             immutable 原始任务材料
│   ├── dataset_row.json
│   ├── metadata.json
│   ├── source_manifest.json
│   ├── public/{problem_statement.md,interface_contract.md}
│   ├── restricted/{original_test.patch,test_seeds.json,resolved_test_selectors.json,original_tests/}
│   ├── reference/{deepswe_verifier_taxonomy.md}
│   └── sealed/{gold.patch,requirements.md,interface.md}
└── intermediate/
    ├── latest_attempt.json
    └── attempts/attempt_NNN/
        ├── prepare/{repo,logs,metadata.json,source_preflight.json,environment_preflight.json}
        ├── converter/{current,revisions,staging,trajectories,live}
        ├── validation/{sanity,semantic,hard_replay,evidence_replay}
        ├── qa/{positive,negative,candidates,evidence.json}
        ├── packaging/{candidate_task,logs,package_report.json,smoke_report.json}
        ├── control/{state.json,events.jsonl,final.json,report.json}
        └── .compat/                      public/restricted/verifier/run 兼容视图
├── final_task/                           全部 gate + smoke 后原子发布
└── review/                               progress/report/metrics/f2p mapping
~~~

final_task 只会在下列条件全部满足后发布：Base F2P 失败、Gold F2P 通过、Base/Gold
P2P 通过且稳定，Positive/Negative QA 达标，package smoke 通过。中间目录用于复现和
审计，不会被打包进最终 task。`source/` 是实例级 immutable 边界；materialized repo 和
所有可变运行产物在具体 attempt 的 `intermediate/attempts/attempt_NNN/prepare` 及其阶段目录中，旧的
attempt-centric runs 通过 resolver 继续可读。

“可解”在这里由三类联动证据支持：package smoke 证明最终 wiring 可执行，Gold replay
证明任务至少有 known-correct 解，Positive QA 证明结构不同的功能正确解也能通过。它不
宣称任意未知 solver 都必然成功。

## Current validation boundary

ExecutionSpec 和对应的 Python、Node/TypeScript、Go adapter 已落在代码中，但四条 fresh
Docker cross-validation 仍未完成。最新 Tutanota Rev3 Semantic Judge 发现 synthetic DOM
query API 与 TypeScript runtime shim 的公共契约耦合；Rev4 目前停在 partial Converter
failure，尚未完成后续 replay/QA。因此这部分是当前的未闭环框架修复状态，不应被表述为
已经验证完成的跨实现保证。详见
[`process/20260923T065319Z_framework_dom_query_and_runtime_shim.md`](process/20260923T065319Z_framework_dom_query_and_runtime_shim.md)。

## Tests

~~~bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src tests
verifier-trans --help
~~~

历史 runs、模型缓存和旧 virtualenv 不属于源码仓库。
