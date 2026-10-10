# OpenLibrary 第二条转换结果

## 任务与 Prepare

- instance：`instance_internetarchive__openlibrary-4a5d2a7d24c9e4c11d3069220c0685b736d5ecde-v13642507b4fc1f8d234172bf8129942da2c2ca26`
- repo：`internetarchive/openlibrary`
- language：Python
- attempt：`attempt_001`
- F2P：1 条
- P2P：8 条
- test collection：9 项
- Prepare：PASS，Base checkout、依赖、import、pytest collection、selector resolution 全部通过

## 转换与 Gate

Converter 首次 BUILD 直接得到 rev1，Semantic Judge PASS，Hard Validator PASS 且重复 2 次稳定：

- Base + converted F2P：FAIL
- Gold + converted F2P：PASS
- Base/Gold + P2P：PASS
- verifier hash：`sha256:3a931716c19fea62501a511e3bafe5572b66e2e5f9c3909d3afcdcb97b5ce9c8`

原始 F2P 是 `test_get_statement_values`，转换为 public `WikidataEntity.get_statement_values(property_id)` 的四个行为检查：单值、多值保持顺序、缺少 property 返回空列表、malformed statement 被跳过。Converter 使用 public dataclass/field 构造输入，没有依赖原测试 private helper。

## QA 与打包

- Positive：1 个 VALID alternative。它用显式 defensive loop 替代 Gold 的 list comprehension，并通过 P2P/F2P。
- Negative 1：使用 `insert(0, ...)` 反转多值顺序；Judge 关联到同一 historical F2P，P2P PASS、F2P FAIL。
- Negative 2：错误接受缺少 `content` 的 malformed entry；Judge 关联到同一 historical F2P，P2P PASS、F2P FAIL。
- package smoke test：PASS
- 最终状态：`VERIFIED / PACKAGED`

最终 task 位于：

`runs/<instance_id>/final_task/`

## 本轮框架问题

第一次 Positive QA 的 3 次 precheck 都因 candidate `run.sh` 从 `/verifier` 推导到 `/` 后找不到 `/framework/p2p_runner.py` 而失败。修复后复用原候选，3 个候选均 P2P/F2P PASS；因此这次没有创建 verifier 新 revision，也没有重复调用模型生成候选。

该问题及修复记录在：

`process/20260922T031000Z_framework_root_relative_candidate_runner_fix.md`
