# Framework issue: Converter prompt path and exploration ambiguity

- UTC 时间：2026-09-22T20:20:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8`
- attempts：`attempt_007`, `attempt_008`

## 现象

两次 fresh Converter BUILD 都在未提交 artifact 前反复使用绝对路径命令，触发 `run_bash rejects absolute paths and parent traversal`；同时长时间扫描 tutanota 的 `libs/`、bundle 等生成内容，未优先形成 verifier。

## 根因

prompt 同时展示了 `/app`、`/workspace/...` 逻辑挂载文档和“使用相对路径”的约束，模型将文档路径误当作可执行命令路径。对大型 Node/TypeScript 仓库，原有 need-driven 措辞仍不足以阻止扫描生成/vendor 树。

## 影响

Converter API 调用和 Docker 环境被长时间占用，未形成可验证 revision；问题属于通用 Converter 会话效率/提示契约，不属于 tutanota verifier 语义。

## 通用修复

更新 `prompts/converter.md`：明确任何 shell 命令禁止绝对路径（包括 `/app`、`/workspace`），统一使用相对 workspace 路径；大型仓库先检查 source/tests/package metadata/native harness，跳过 `build/`、`libs/`、`node_modules/`、coverage 和 bundles，先提交最小可执行 verifier 再渐进完善。

## 测试/状态

- attempt_007：Prepare PASS，Converter 因 format/API wait 未提交。
- attempt_008：Prepare PASS，Converter 因重复绝对路径 PermissionError 未提交。
- 两次不完整会话均未进入 Semantic Judge/Hard Validator，临时容器已清理。
- 下一次 fresh attempt 验证 prompt 修复。
