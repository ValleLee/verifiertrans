# Framework issue: Prepare accepted an unmaterialized repository

## 现象

本次 NodeBB `attempt_001` 在默认 sandbox 中执行 Docker materialization 时返回
`returncode=126`，日志为 Docker socket permission denied。由于 `/tmp` 中已有同实例名
的 staging 目录，旧逻辑仍看到 `public/repo` 目录并错误写出 `source_preflight=PASS`。

## 根因

`prepare_instance.py` 的 `base_repo_materialized` 只检查当前 attempt 的 repo 路径是否为
目录，没有绑定本次 materialize 命令的返回码和观测到的 base commit。

## 影响

这会把不可信的 stale repository 传给 Converter，属于 framework/infrastructure failure，
不是 verifier semantic failure。该 attempt 未用于模型转换。

## 通用修复

Prepare source gate 现在要求：materialization 结果存在、返回码为 0、观测 HEAD 与声明的
base commit 匹配、repo link 已建立且目录存在。Docker 权限失败或 stale cache 不再能够
伪装成 Prepare PASS。

## 测试结果

使用用户已授权的 Docker 权限重新创建 `attempt_002`；materialization 返回码 0，观测 HEAD
为 `da2441b9bd293d7188ee645be3322a7305a43a19`，复制 10424 个文件，`source_preflight`
和 `environment_preflight` 均为 PASS。后续转换只使用 `attempt_002`。
