# Element Web 当前会话 kebab 菜单转换审计

## 审计对象与结论

- **实例**：`instance_element-hq__element-web-776ffa47641c7ec6d142ab4a47691c30ebf83c2e`
- **Base commit**：`8b54be6f48631083cb853cda5def60d438daa14f`
- **本次审计时间**：2026-09-24 14:28（Asia/Shanghai）；运行产物最后验证时间为 2026-09-24 13:44（Asia/Shanghai）。
- **运行状态**：`VERIFIED / PACKAGED`，final revision 7，semantic judge `PASS`，稳定回放 `True`。
- **结果**：历史 F2P 10 条，全部映射并发出 10 条功能测试；历史 P2P 39 条保持通过。回放中 Base+F2P 失败、Gold+F2P 通过，说明测试能区分“没有实现”和“正确实现”。

**结论：通过。** 这是一次较完整的“从快照/实现绑定测试到用户可观察功能测试”的转换。测试现在围绕页面 DOM、可访问属性和点击后的公开副作用工作；没有要求候选人采用 `KebabContextMenu` 这个内部组件结构。仍有一个小边界：图标 CSS selector 和 `data-testid` 是稳定的 DOM 契约，属于 UI 公共表面，不是黑盒业务输出。

## 1. 原始 problem statement（中文翻译）

**标题：设备管理器当前会话缺少 Kebab 菜单。**

**描述：** 设备管理器的当前会话区域没有专门的、针对会话操作的上下文菜单，用户因此更难快速退出登录或管理会话。加入 Kebab 上下文菜单，可以让用户直接在当前会话条目中访问关键操作，从而改善可访问性、易用性和界面一致性。

**希望做什么：** 在设备管理器的“当前会话”区域增加一个 Kebab（三点）按钮，并提供“退出登录”和“退出所有其他会话”等选项。这些选项应有 destructive（危险操作）视觉提示，并且能从当前会话界面直接访问。

**为什么做：** 目前，退出当前设备或退出所有其他设备等操作没有专门的上下文菜单入口，用户不容易发现或访问。把这些操作放进上下文菜单，可以改善会话管理的易用性、清晰度和一致性。

**希望如何做：** 在“当前会话”区域引入 Kebab 上下文菜单组件。菜单应包含退出登录和退出所有其他会话这两个危险操作，并提供适当的禁用逻辑和可访问性支持。菜单应在交互后自动关闭，并正确显示危险操作的视觉提示。

**补充背景：** 这项改动还应增加 Kebab 菜单 CSS、危险颜色样式和交互后关闭逻辑；修改相关 React 组件和测试，以覆盖渲染、可访问性和用户交互；必要时更新翻译字符串。视觉样式和 UI 结构由补丁中的组件与样式改动定义。

原题还隐含了若干实现偏好：新增 `KebabContextMenu` 组件、`closeOnInteraction` 属性、CSS 文件和翻译字符串。这些内容是 Gold patch 的实现方式，不应自动成为等价实现的硬要求。

## 2. 当前 instruction（中文翻译）

**目标：** 实现当前会话的 Kebab 上下文菜单，使下面的可观察行为成立。

1. 当前会话标题显示 Kebab 上下文菜单按钮。
2. Kebab 按钮渲染公开的 `mx_KebabContextMenu_icon` 图标 selector，并作为可访问按钮暴露 `aria-haspopup`、`aria-expanded` 和 `role="button"`。
3. 当前会话区域渲染当前设备 tile 和正确的安全卡：
   - 已验证设备显示 `Verified session` 卡片，且不显示 `Verify session` 操作；
   - 未验证设备显示 `Unverified session` 卡片，且显示 `Verify session` 操作。
4. 设备列表加载中或没有当前设备时，Kebab 按钮处于 disabled 状态，并带有 `aria-disabled`。
5. 打开 Kebab 菜单并选择 `Sign out` 时，打开退出登录对话框。
6. 只有当前设备时，不提供 `Sign out all other sessions`。
7. 存在多个设备时，选择 `Sign out all other sessions` 会请求删除除当前会话设备 id 以外的所有设备 id。

**验证边界：** verifier 停留在渲染 DOM 和公开交互副作用边界；不要求特定内部组件结构、私有 helper、私有图标 markup 或关闭动画。

## 3. 原始 F2P 与当前 F2P

### 原始 F2P（10 条）

| 原始测试类型 | 原测试绑定点/断言 |
| --- | --- |
| `CurrentDeviceSection` 的 3 条 | 对 React snapshot 做整体比较；snapshot 同时包含 heading、设备 tile、安全卡、图标和菜单 DOM。 |
| `SessionManagerTab` 的 2 条状态测试 | 通过 `getByTestId` 检查加载中、空设备列表时菜单 `aria-disabled`。 |
| `SessionManagerTab` 的 2 条会话 snapshot | 对整个 `current-session-section` 做 snapshot，分别覆盖已验证和未验证设备。 |
| 退出当前设备 | 点击菜单和 `Sign out`，断言 `Modal.createDialog` 收到 `LogoutDialog`。 |
| 只有一台设备 | 点击菜单，断言没有 `Sign out all other sessions`。 |
| 多台设备 | 点击菜单和 `Sign out all other sessions`，断言 `deleteMultipleDevices` 收到其他设备 id。 |

这些测试里，整体 snapshot 把很多与需求无关的 DOM 细节锁死；它们也容易随布局或 class 调整而变化。

### 当前 F2P（10 条功能测试）

| 原始 F2P | 当前功能测试 | 从什么变成什么 |
| --- | --- | --- |
| 3 条 `CurrentDeviceSection` snapshot | 3 条 targeted DOM 测试 | 从整棵渲染树比较，变为检查菜单可访问属性、公开 icon selector、设备 tile、安全卡标题/图标及 Verify 按钮存在性。 |
| 加载中、无设备 | 2 条 DOM 状态测试 | 保留同一可观察输出：菜单是否 disabled；不再依赖 snapshot。 |
| 2 条 `SessionManagerTab` snapshot | 2 条 scoped DOM 测试 | 从整段 section snapshot，变为只验证 current-session section 中的菜单、设备和安全卡契约。 |
| 当前设备退出 | 1 条交互测试 | 保留点击菜单后的 `LogoutDialog` 公开副作用。 |
| 单设备 | 1 条交互测试 | 保留菜单项缺失这一用户可见结果。 |
| 多设备 | 1 条交互测试 | 保留 `deleteMultipleDevices(其他设备 ids, undefined)` 这一客户端公开调用结果。 |

`review/f2p_mapping.csv` 给出的决策是 `rewrite=5、keep=5`：需要摆脱 snapshot 的项目被重写，已经是行为断言的项目直接保留。当前 verifier 位于 `final_task/tests/test.patch` 注入的 `verifier/verifier.test.tsx`，使用 Base repo 已有的 React Testing Library、Matrix client mock 和 Modal 接口。


### 核心代码：原始测试如何绑定实现

原始测试主要通过整段 snapshot 绑定渲染结构，例如：

```tsx
const { getByTestId } = render(getComponent());
await act(async () => {
    await flushPromisesWithFakeTimers();
});
expect(getByTestId('current-session-section')).toMatchSnapshot();
```

菜单交互本身虽然已经是行为断言，但仍位于原有组件测试文件中：

```tsx
fireEvent.click(getByTestId('current-session-menu'));
fireEvent.click(getByLabelText('Sign out'));
expect(modalSpy).toHaveBeenCalledWith(
    LogoutDialog, {}, undefined, false, true,
);
```

### 核心代码：当前功能 verifier 验证什么

快照被拆成面向功能的 DOM 断言，只检查用户能看到和操作的结果：

```tsx
const menu = getByTestId('current-session-menu');
expect(menu.getAttribute('aria-disabled')).toBeFalsy();
expect(menu.getAttribute('aria-expanded')).toBe('false');
expect(menu.getAttribute('aria-haspopup')).toBe('true');
expect(menu.getAttribute('role')).toBe('button');
expect(menu.querySelector('.mx_KebabContextMenu_icon')).toBeTruthy();

expect(getByTestId(`device-tile-${deviceId}`)).toBeTruthy();
expect(getByText('Unverified session')).toBeTruthy();
expect(getByText('Verify session')).toBeTruthy();
```

交互副作用也按公开结果验证：

```tsx
fireEvent.click(getByTestId('current-session-menu'));
fireEvent.click(getByLabelText('Sign out all other sessions'));
expect(mockClient.deleteMultipleDevices).toHaveBeenCalledWith(
    [alicesMobileDevice.device_id, alicesOlderMobileDevice.device_id],
    undefined,
);
```

## 4. 是否完成了从实现绑定到面向功能？

**是，且转换边界清楚。**

- 用户场景现在可直接讲清楚：用户打开 Sessions，在当前会话的三点菜单中退出当前设备或退出其他设备；没有设备或仍在加载时，菜单不可用；已验证状态和未验证状态显示不同安全卡。
- 测试不再要求必须新增哪个 React 文件、使用哪个 hook、CSS 如何组织或菜单如何自动关闭；这些属于实现选择。
- 断言集中在 DOM 可观察结果和 `Modal.createDialog`、`deleteMultipleDevices` 这类现有公开交互副作用上。候选实现只要产生同样的用户结果即可通过。
- 两个负向候选和 Base F2P 均被拒绝，Gold F2P 和 P2P 均通过，说明测试锁定的是行为而不是 Gold patch 的文本形状。

**现实依据**：这是设备管理页上的直接用户操作，菜单是否出现、是否可访问、退出是否触发对话框、批量删除是否排除当前设备，都能在真实 UI 中观察到。

**剩余边界**：当前测试仍依赖公开 DOM 的 `data-testid` 和 `.mx_KebabContextMenu_icon` selector，也通过 mock client 观察副作用；它没有启动真实服务器或浏览器。这是组件级功能验证，不是端到端验收。

## 5. 取证位置

- 原 problem statement：`runs/instance_element-hq__element-web-776ffa47641c7ec6d142ab4a47691c30ebf83c2e/source/public/problem_statement.md`
- 当前 instruction：同一 run 下的 `final_task/instruction.md`
- 原始测试与 selector：`source/restricted/original_test.patch`、`source/restricted/resolved_test_selectors.json`
- 当前 verifier 与测试 patch：`final_task/tests/test.patch`
- F2P 映射与审查报告：`review/f2p_mapping.csv`、`review/conversion_report.md`
- 稳定回放与语义结果：`review/metrics.json`、`review/progress.json`
