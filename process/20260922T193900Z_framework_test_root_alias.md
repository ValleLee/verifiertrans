# Framework issue: generated test-root alias

- UTC 时间：2026-09-22T19:39:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`

## 现象

在 base repo 已成功物化、且 `.js→.ts` 扩展 alias 已生效后，Prepare 仍无法解析 78 个 F2P selector。数据路径为 `test/tests/api/...`，仓库路径为 `test/api/...`。

## 根因

selector 生成格式把 `tests` 作为 `test/` 下的逻辑目录，但仓库采用 `test/` 直接承载测试子目录。解析器只做了根目录和扩展名归一化，没有处理这一通用测试根路径变体。

## 影响

Prepare 会错误报告 `missing_test_files`，阻止 TypeScript 转换在 Converter 阶段开始。问题属于通用 selector/path execution preparation，不属于 tutanota 业务语义。

## 通用修复

`resolve_repo_test_path` 现在在 exact path 后尝试 `test/tests/<rest>` → `test/<rest>`，并对每个逻辑路径组合应用 JS/TS 扩展 alias；仍要求最终文件真实存在，不硬编码具体测试文件。

## 测试结果

- 新增单测覆盖 `test/tests/api/example.js` → `test/api/example.ts`。
- 直接解析检查通过。
- 将以新鲜 Prepare attempt 重跑 tutanota。
