# Framework/infrastructure issue: replay Docker context lacked the prepared image

## UTC 时间

2026-09-22T06:30:23Z

## 现象

NodeBB-049989 `attempt_001` 的 Hard Validator 在四个 replay 组中都返回：

```text
container_exit_code: 126
failure_cause: docker_unavailable
verifier_runnable: false
```

日志最初显示当前受限执行上下文无法访问 `/var/run/docker.sock`。在获得 Docker
daemon 访问后，默认 context 可以响应，但 `docker image ls` 没有任务镜像。

## 根因

Prepare 记录的镜像为：

```text
jefzda/sweap-images:nodebb.nodebb-NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5
```

该镜像没有存在于当前 Docker daemon 的本地 image store。因而此前的 replay 没有
机会进入容器创建、mount、NodeBB/Mocha 或 verifier 执行阶段。这个结果不能用于
判断 verifier 语义。

## 影响

本次 revision 的 Base/Gold F2P、Base/Gold P2P 均未实际执行，不能计为任何 core gate
通过或失败。状态被记录为 infrastructure/manual review，而不是 semantic repair。

## 通用处理

按 dataset/Prepare 的精确 image reference 拉取镜像，并保留原有 attempt/artifact；不
更换 tag、不修改 verifier、不删除其他 image 或容器。后续框架应考虑在 Hard Validator
前将“daemon 可访问”和“精确 image 可 inspect”作为明确的 deterministic preflight，
避免把四组 replay 的同一 Docker 缺失重复记录成 verifier failure。

## 测试结果

```text
docker version                                  PASS
docker pull <exact prepared image>              PASS
Digest: sha256:e49637ebe82a479ca43b4663525955bc9cdd58c457140ee31c20958d621d3cf7
Status: Image is up to date
```

下一步是在 Docker 可用且 image 已加载的同一 attempt 上 resume，并重新取得真实
Semantic/Hard/QA/package 证据。
