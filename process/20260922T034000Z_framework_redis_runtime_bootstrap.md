# Framework issue: service-backed JavaScript replay lacked Redis bootstrap

## 现象

在修复 JS entrypoint 后，NodeBB rev1 的 Gold F2P/P2P 都能找到 Mocha，但 Mocha 的
`before all` hook 失败：`Error: connect ECONNREFUSED 127.0.0.1:6379`。Container setup
和 patch application 均为 0，问题发生在测试 runtime。

## 根因

NodeBB image 同时包含 `redis-server` 和 `redis-cli`，但 Hard Validator 使用 `/bin/bash`
作为 container entrypoint，不会执行镜像原有的 service startup。VerifierTrans 原先
没有为自包含测试服务提供通用 readiness bootstrap。

## 影响

这是 Docker/runtime infrastructure failure，不是 verifier semantic failure；若不修复，
所有需要本地 Redis 的 NodeBB F2P/P2P 和 QA candidate 都会稳定误失败。

## 通用修复

Hard Validator 和 candidate replay 在执行 verifier 前：当镜像同时提供 `redis-cli` 和
`redis-server` 且本地 Redis 尚未响应时，启动 daemon 并最多等待 30 次 readiness ping。
不假设具体仓库文件或测试 selector；若命令不存在则保持原行为。

## 测试结果

新增 unit regression assertions 覆盖两条 replay 路径的 bootstrap。修复后将复用 rev1
verifier 重新执行 Hard Validator，不生成新的 Converter revision。
