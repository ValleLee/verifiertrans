# Framework issue: JavaScript/TypeScript selector extension alias

- UTC 时间：2026-09-22T19:36:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`

## 现象

Prepare 在已成功物化 base repo 后仍报告 78 个 F2P selector 文件不存在。数据集 selector 使用 `.js`，而同 stem 的仓库测试文件实际使用 `.ts`；例如 `test/tests/api/worker/facades/LoginFacadeTest.js` 对应 `LoginFacadeTest.ts`。

## 根因

共享路径解析只支持 `.js↔.jsx` 和 `.ts↔.tsx`，没有覆盖 JavaScript/TypeScript 之间的同 stem 扩展名差异。

## 影响

TypeScript 实例在 Prepare 阶段被错误阻断，Converter 无法开始；这是通用 selector/path 解析问题，不是 tutanota 特异逻辑，也不是 Docker 镜像缺失。

## 通用修复

扩展 `resolve_repo_test_path` 的确定性 alias 表：在 exact path 之后支持 `.js↔.ts`、`.jsx↔.tsx`，仍只对同 stem 文件回退，不硬编码仓库或测试路径。

## 测试结果

- 修改文件：`src/verifier_trans/deterministic/preparation/common.py`
- 单测：`tests/unit/test_core.py` 增加 `.js` selector → `.ts` 文件覆盖。
- 直接解析检查：通过，返回 `test/example.ts`。
- 后续验证：用新鲜 Prepare attempt 重跑 tutanota。
