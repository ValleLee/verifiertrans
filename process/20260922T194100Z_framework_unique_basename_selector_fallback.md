# Framework issue: flattened test-directory selector fallback

- UTC 时间：2026-09-22T19:41:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`

## 现象

在 `test/tests/` → `test/` 和 `.js` → `.ts` 归一化后，仍有 selector 使用额外历史分组目录（如 `api/common/utils`），而仓库实际将测试文件放在 `api/common` 或 `api/error`。

## 根因

数据集生成的测试 selector 路径反映 runner/测试布局，不总是 checkout 中的物理目录布局。仅依赖固定目录替换会漏掉安全可解析的目录扁平化情况。

## 影响

Prepare 误报大量 `missing_test_files`，阻止后续转换；不涉及业务语义或 Docker 执行。

## 通用修复

在 exact path、逻辑测试根和扩展 alias 均失败后，按 basename 及 JS/TS 同 stem 在仓库中搜索；仅当结果唯一时接受，否则继续报告 unresolved，避免猜测重复文件。

## 测试结果

- `resolve_repo_test_path` 增加唯一 basename 回退。
- 单测覆盖 `test/tests/api/common/utils/LoggerTest.js` → `test/api/common/LoggerTest.ts`。
- 已对真实 tutanota staging repo 做直接解析检查，返回 `test/api/common/LoggerTest.ts`。
- 后续用新鲜 Prepare attempt 验证完整 selector 集合。
