# Framework issue: JavaScript replay used the Python P2P runner and wrong mount root

## 现象

NodeBB rev1 Semantic Judge 已 PASS，但 deterministic Hard Validator 在 Base/Gold 的 F2P
和 P2P 四个分支均返回 `verifier_rc=2`。Gold F2P 日志为 `mocha not found`；Gold P2P
则把 `test/controllers.js` 交给 pytest，收集 0 项后返回 2。

## 根因

通用 `replay/verifier.py` 对所有 P2P 使用 Python `p2p_runner.py`，没有遵循 Converter
manifest 的语言特定 `VERIFIER_GROUP=p2p bash verifier/run.sh`。同时 F2P 通过
`/verifier/run.sh` 启动，脚本按自身路径把 checkout root 推导为 `/`，于是从 `/` 查找
`node_modules/.bin/mocha`，而真实仓库在 `/app`。

## 影响

这是 replay/Docker/语言分派基础设施故障，不是 verifier semantic failure；它会把一个
应当运行的 NodeBB verifier 错误分类为失败，并可能错误触发 Converter REPAIR。

## 通用修复

1. deterministic verifier replay 对 F2P/P2P 都调用 `/app/verifier/run.sh`，由 verifier
   自身根据 `VERIFIER_GROUP` 选择并运行对应语言的测试入口；
2. candidate replay 使用同一 `/app/verifier/run.sh` 路径，确保 repository-relative
   runner 的 `SCRIPT_DIR` 解析到 `/app`；
3. 增加 unit regression tests，禁止回退到 Python-only P2P dispatch。

当前 rev1 artifact 保持不变，修复后重新 replay，不消耗新的 semantic verifier revision。
