# Framework issue: selector fallback scan cost

- UTC 时间：2026-09-22T19:45:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`

## 现象

为支持安全的唯一 basename selector fallback，初版实现对每个 selector 独立递归扫描仓库。tutanota Prepare 在完成 Docker materialization 后长时间没有生成 preflight 结果，影响继续转换。

## 根因

fallback 的搜索空间相同，但实现没有复用扫描结果；80 个 selector 重复遍历同一仓库文件树。

## 影响

这是通用 Prepare 性能问题，不改变 verifier 语义，但会把路径解析误表现为执行卡住，增加不同语言任务的启动成本。

## 通用修复

为每个 prepared repo 建立一次 basename → 相对路径元组索引，并通过有限缓存复用；仍只接受唯一同 stem 匹配，保持 ambiguous selector unresolved。

## 测试结果

- 直接真实仓库解析检查通过：`LoggerTest.js` → `test/api/common/LoggerTest.ts`。
- 后续用新鲜 Prepare attempt 验证完整流程和耗时。
