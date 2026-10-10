# Framework issue: project-owned ospec runner discovery

- UTC 时间：2026-09-22T19:53:00Z
- 暴露实例：`instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`

## 现象

TypeScript tutanota 的 selector 已全部解析，但 Prepare 将环境判定为 `unsupported`，因为其 `package.json` 不使用 Mocha/Jest/Vitest，而是 `ospec` 配合仓库内 `test/TestBuilder.js` 和 `test/test.js`。

## 根因

Node execution discovery 只识别通用 runner 名称，未识别项目自带的原生测试 harness；这会把可执行的 Node/TypeScript 项目误分类为 infrastructure failure。

## 影响

Converter 无法进入，P2P/legacy replay 也没有确定性执行命令；问题属于通用 execution adapter，不是 tutanota 业务语义。

## 通用修复

- discovery 支持 `ospec` 和 `test/test.js + test/TestBuilder.js` harness。
- Prepare 对 ospec 做 Node/npm、ospec 依赖、项目入口和 `node --check` 检查。
- framework-owned Node runner 对 ospec 使用项目原生 `test/test.js api/client`；不引入新的 Agent 或 Pipeline 角色，也不伪造 selector 通过。

## 测试结果

- 增加 ospec discovery 和 runner source 单测。
- 以新鲜 Prepare attempt 验证完整 TypeScript 实例。
