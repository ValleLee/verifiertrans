# Navidrome 音乐服务客户端封装转换审计

## 审计对象与结论

- **实例**：`instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e`
- **Base commit**：`7fc964aec5d432480d76bb90eee14a09aca5125f`
- **本次审计时间**：2026-09-24 14:28（Asia/Shanghai）；运行产物最后验证时间为 2026-09-24 07:17（Asia/Shanghai）。
- **运行状态**：`VERIFIED / PACKAGED`，final revision 2，semantic judge `PASS`，稳定回放 `True`。
- **结果**：历史 F2P 3 个测试套件全部映射；最终 verifier 发出 6 项检查（3 个原有 agent/client 行为套件 + 3 个公开导出面检查）。Gold+F2P 通过，Base+F2P 失败；P2P/回归检查通过。

**结论：通过，但这是“公开 API 契约验证”，不是纯运行时黑盒测试。** 需求本身是“外部代码不能构造或调用低层 client”，这个性质不能只靠一次 agent 输出证明。因此转换采用两层证据：保留现有 agent-level 行为测试，并用 Go AST 检查包对外可见的类型、构造函数和方法集合。它已经摆脱了对某个私有字段或具体实现代码的绑定，但仍然需要读取源码的公开导出面；这是该类封装任务的合理最小检查。

## 1. 原始 problem statement（中文翻译）

**标题：改善客户端函数的封装性。**

**描述：** LastFM、ListenBrainz 和 Spotify 的内部 HTTP client 当前暴露了导出的 `Client` 类型和导出方法。这会把实现细节泄露给包外调用方，使外部代码可以无意中直接使用这些低层对象，并增加误用风险。把这些 client 封装起来，可以加强包边界，让公开 API 只保留更高层的 agent 接口。

**当前行为：** `Client` 结构体及其方法（例如获取信息、token/session 处理、更新正在播放、scrobble、搜索）是导出的，因此包外代码可以调用它们。

**预期行为：** 每个音乐服务包中的 client 类型及其方法都改为未导出（package-private）。只有包内代码（agent、router 和包内测试）可以构造和调用它们；通过 agent 接口提供给外部的行为保持不变。

## 2. 当前 instruction（中文翻译）

**目标：** 封装 LastFM、ListenBrainz 和 Spotify 的内部 HTTP client。每个音乐服务包当前都暴露了 HTTP client 类型和低层请求/响应方法；外部调用方不能构造或调用这些内部对象，公开 API 仍然是高层 agent 接口。

**必须满足：**

1. 三个音乐服务包中的具体 HTTP client 类型必须是未导出的。
2. client 构造函数必须是未导出的。
3. 历史 F2P 覆盖的低层方法必须是未导出的：fetch-info 方法、LastFM session 获取、update-now-playing、scrobble 和 artist search。LastFM 的 token-request 方法不在必须重命名的范围内；即使保留导出名，其接收者也必须是未导出的 client 类型。
4. 只有包内代码（agent、router 和包内测试）可以构造和调用 client。
5. 现有 agent 接口的外部行为保持不变；受影响的包仍能编译，agent-level 入口继续工作。

**明确不在范围内：** 不改变公开 agent 接口，不添加新的 agent 行为，不改变已有请求/响应格式；这次改动只解决封装问题。

## 3. 原始 F2P 与当前 F2P

### 原始 F2P（3 个套件）

| 原始套件 | 原来的绑定方式 | 要证明的语义 |
| --- | --- | --- |
| `TestLastFM` | 包内测试直接声明 `*Client`、调用 `NewClient` 和 `AlbumGetInfo`、`ArtistGetInfo`、`GetSession`、`Scrobble` 等导出方法。测试补丁把这些名字改成 `client`、`newClient` 和小写方法。 | 低层 LastFM HTTP client 被封装，同时既有请求/响应和 agent 行为不变。 |
| `TestListenBrainz` | 直接构造 `*Client` 并调用 `ValidateToken`、`UpdateNowPlaying`、`Scrobble`；测试补丁改为小写。 | ListenBrainz client 只能包内使用，router/agent 行为不变。 |
| `TestSpotify` | 直接构造 `*Client` 并调用 `SearchArtists`；测试补丁改为小写。 | Spotify artist search client 方法不再对外导出，agent-level 图片/搜索行为不变。 |

这类原始测试天然知道具体类型名、构造函数名和方法名，是典型的实现/符号绑定测试。

### 当前 F2P（6 项检查）

| 来源 | 当前检查 | 从什么变成什么 |
| --- | --- | --- |
| `TestLastFM` | `go test ./core/agents/lastfm -run TestLastFM` + `TestLastFMClientUnexported` | 从“测试必须调用某个名字的小写 client”，变为运行既有行为套件，并检查最终包的公开导出面没有 concrete client、构造函数或禁止导出的方法。 |
| `TestListenBrainz` | 对应 agent/client 套件 + `TestListenBrainzClientUnexported` | 同上，针对 token validation、now playing、scrobble。 |
| `TestSpotify` | 对应 agent/client 套件 + `TestSpotifyClientUnexported` | 同上，针对 artist search。 |

AST guard 不要求候选人必须使用 Gold 的 `client` 名称；它按 client-like 类型、构造函数返回类型和禁止导出的方法名检查“外部能看到什么”。同时，原有 Go 套件继续验证请求/响应和高层 agent 行为没有回归。


### 核心代码：原始测试直接依赖具体 client

原始包内测试直接声明具体类型、调用导出构造函数和低层方法，例如：

```go
client := NewClient("API_KEY", "SECRET", "pt", httpClient)
artist, err := client.ArtistGetInfo(
    context.Background(), "U2", "123",
)
```

测试补丁把这些名字改成包内版本，正是因为原测试和目标实现绑定在同一组符号上：

```diff
- client := NewClient("API_KEY", "SECRET", "pt", httpClient)
+ client := newClient("API_KEY", "SECRET", "pt", httpClient)
- artist, err := client.ArtistGetInfo(ctx, "U2", "123")
+ artist, err := client.artistGetInfo(ctx, "U2", "123")
```

### 核心代码：当前 verifier 检查公开 API 表面

当前 verifier 仍运行高层/请求行为套件：

```bash
go test ./core/agents/lastfm ./core/agents/listenbrainz \
  ./core/agents/spotify -run 'Test(LastFM|ListenBrainz|Spotify)$'
```

并用 Go AST 收集包的类型、函数和方法，只拒绝外部可见的 client surface：

```go
s := collectPackageSurface(t,
    filepath.Join(root, "core", "agents", "spotify"),
)
assertClientSurface(t, "spotify", s, spotifyContract)
```

检查的不是 `client` 这个私有名字，而是导出类型、导出构造函数和禁止导出的低层方法：

```go
for recv, methods := range s.methods {
    if !s.isClientLikeType(c, recv) {
        continue
    }
    for _, m := range methods {
        if !m.exported {
            continue
        }
        for _, forbidden := range c.forbiddenExportedMethods {
            if m.name == forbidden {
                t.Errorf("client method %q is still exported", m.name)
            }
        }
    }
}
```

## 4. 是否完成了从实现绑定到面向功能？

**完成了一半需要特别说明的转换：从具体实现符号，转为公开 API 表面契约；但它不可能是纯输出黑盒。**

- 已去掉对 `Client` 结构体、`NewClient` 构造函数和私有字段布局的硬编码要求；候选人可以用不同的内部命名和组织方式。
- 真实的外部约束是“包外不能访问低层 HTTP client”。AST 检查直接验证 Go 包对外暴露的类型、构造函数和方法，这比检查 patch 文本更接近用户/调用方实际看到的 public API。
- `go test` 的三套既有测试继续验证 agent-level 功能和请求/响应行为，因此不会为了封装而悄悄破坏音乐服务功能。
- 正负 QA 和回放能区分“只加一个导出 alias”的错误候选：它仍可能通过业务行为，但会被公开导出面 guard 拒绝。

**现实依据**：Navidrome 的 agent/路由是其他包真正使用的入口；外部调用方应只能依赖这些高层接口，而不能直接创建 LastFM、ListenBrainz 或 Spotify 的 HTTP client。封装的成功标准是编译期/API 可见性边界和高层功能同时成立。

**残余风险/边界**：这不是完全黑盒测试。AST guard 仍读取源码来判断导出面，并按方法名识别历史禁止导出的方法；这是因为“不可导出”本身就是源码/API surface 属性。若要进一步贴近外部调用者，可以再加一个独立外部包编译探针，但当前发布物已覆盖报告中定义的公开契约，且 semantic judge 与稳定回放均通过。

## 5. 取证位置

- 原 problem statement：`runs/instance_navidrome__navidrome-7073d18b54da7e53274d11c9e2baef1242e8769e/source/public/problem_statement.md`
- 当前 instruction：同一 run 下的 `final_task/instruction.md`
- 原始测试补丁/Gold 变化：`source/restricted/original_test.patch`、`source/sealed/gold.patch`
- 当前 verifier：`final_task/tests/test.patch` 中的 `verifier/verifier_test.go` 与 `verifier/run.sh`
- F2P 映射与审查报告：`review/f2p_mapping.csv`、`review/conversion_report.md`
- 稳定回放与语义结果：`review/metrics.json`、`review/progress.json`
