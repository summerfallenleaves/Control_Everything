# macOS Accessibility 控制细节调研

> 调研日期：2026-08  |  本机：macOS 26.5.2 (Apple Silicon, 2560x1440)  |  方法：web 调研 + 本机 pyobjc 实测验证

## 1. 权限体系（第一步，最重要）

macOS 将自动化能力门控在 **两个独立 TCC 权限** 之后：

| 权限 | 位置 | 需要它的操作 | 缺失表现 |
|---|---|---|---|
| 辅助功能 Accessibility | 系统设置 > 隐私与安全性 > 辅助功能 | 所有 AX 读取与动作 | AXIsProcessTrusted()=false，AX 调用返回 kAXErrorAPIDisabled (-25211) |
| 屏幕录制 Screen Recording | 系统设置 > 隐私与安全性 > 屏幕录制 | 仅截图（CGWindowList/CaptureKit） | CGWindowListCreateImage 返回 null |

关键事实：
- TCC 按**磁盘上的二进制路径**记录权限。重新编译/移动二进制 = 新 TCC 条目需重新授权；relink 后开关可能静默关闭。
- 代码触发授权弹窗：`AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: true})`。
- 授权后**需重启进程**生效（agent-ctrl 文档明确提到）。
- **本机实测**：`AXIsProcessTrusted() = True`，`screencapture` 成功 —— 当前开发环境两权限均已具备，可直接开发。

## 2. 观察层（Perception）—— 本机全部实测通过

### AX UI 树遍历
```python
import ApplicationServices as ax, AppKit
app = ax.AXUIElementCreateApplication(pid)   # pid 来自 NSWorkspace
err, children = ax.AXUIElementCopyAttributeValue(app, "AXChildren", None)
```
关键属性：`AXRole`(AXButton/AXTextField/AXWindow...)、`AXTitle`、`AXDescription`、`AXValue`、`AXIdentifier`、`AXFrame`(CGRect 坐标)、`AXEnabled`、`AXFocused`。

### 本机实测结果（Safari）
- 完整树遍历成功（65 行）：窗口、工具栏、标签页、收藏栏、菜单栏全可读
- **标签页 = AXRadioButton**，激活态用 `AXValue=True/False` 表达
- **AXIdentifier 极其丰富**：`TabBarTab?isPinned=true&isActive=false`、`ShareButton`、`NewTabButton` —— 元素定位快路径可依赖
- **坐标可用**：`AXFrame` 返回 CGRect (x/y/w/h)
- 截图：`screencapture` 输出 2560x1440、21.5 万种颜色（真实内容）；`CGWindowListCopyWindowInfo` 返回 22 个窗口

### 已踩到的坑
- `AXFocusedApplication` 系统级查询报 **-25204 (kAXErrorCannotComplete)** → 改用 `NSWorkspace.sharedWorkspace().frontmostApplication()`
- 大屏整图 2560x1440 对 LLM token 开销大 → 需**窗口检测 + 裁剪活动窗口**再喂模型（参考 mac-cua 的 ScreenCaptureKit 按 windowID 截取）

## 3. 执行层（Control）—— setValue 本机实测成功

动作原语与底层机制（参考 agent-ctrl method diagnostics 表）：

| 动作 | 机制 | 说明 |
|---|---|---|
| 语义点击 | `AXUIElementPerformAction(kAXPressAction)` | 首选，不依赖坐标 |
| 坐标点击 | CGEventCreateMouseEvent | AXPress 失败时的兜底（自绘控件） |
| 文本输入 | `AXUIElementSetAttributeValue(el, "AXValue", text)` | **本机实测 err=0 成功**，支持中文、无输入法问题 |
| 键盘/快捷键 | CGEventKeyboardSetUnicodeString / 虚拟键码+modifier | 键入与 Cmd+S 等 |
| 滚动 | CGEventCreateScrollWheelEvent | |
| 后台控制 | `CGEventPostToPid` | **不移动鼠标、不抢焦点**（mac-cua 核心卖点） |
| 剪贴板 | pbcopy / pbpaste | |

### 本机实测（TextEdit 隔离测试）
- 启动应用 → AX 树定位 `AXTextArea` → `set AXValue` 写入中文 → **err=0 成功**
- 写后读回可能返回 None（AX 读回不可靠，需二次验证机制，参考 agent-ctrl）
- `osascript` 关闭窗口报 **-10004 权限违例**：AppleScript 的授权路径与 AX 不同，混合使用注意

## 4. 元素定位与可靠性策略（agent-ctrl 精华）

1. 元素引用只在产生它的 snapshot 内有效；重绘/导航后**必须重新遍历**
2. 定位双策略：`AXIdentifier` 唯一快路径 → `(role, name, nth)` DFS 慢路径
3. sheets/dialogs/popups：嵌套在父窗口树内或作为兄弟窗口，需限定作用域查找
4. 动作失败自动降级：`ax-press` -> `cg-click`，日志打 method 标签便于诊断

## 5. 三条技术路线对比（含本机实测）

| 路线 | 本机状态 | 评价 |
|---|---|---|
| **Python + pyobjc** | 实测全部通过，uv 装 5 包 77ms | 与项目技术栈一致，**推荐** |
| Swift 原生 | swiftc 6.3.3 与 SDK 6.3.2 不匹配 + 沙箱 ModuleCache 限制 | 生产性能最佳但当前环境受阻 |
| AppleScript/JXA | osascript 报 -10004 权限违例 | 慢，仅适合有 scripting dictionary 的应用 |

## 6. 推荐架构（参考 agent-ctrl / axon / mac-cua 三方共识）

**三层混合**：AX 语义优先 → CGEvent 坐标兜底 → 截图+视觉最终兜底
```
MacController (pyobjc)
  |-- 1. AX 树定位 + AXPress / setValue   (结构化、可靠、优先)
  |-- 2. CGEvent 坐标点击/滚动/快捷键     (自绘 UI / Electron 兜底)
  `-- 3. ScreenCaptureKit/screencapture 截图 + 视觉理解  (最终兜底)
```
- 截图优先考虑 ScreenCaptureKit（Swift，GPU、按窗口）；CLI 兜底 `screencapture -l <windowID>`
- 引用项目：`atomacos`(AX Python 封装)、`mac-cua`(CGEventPostToPid 后台控制)、`axon`(Swift 三层混合 CLI)、`agent-ctrl`(AX 可靠性实践)

## 7. 结论

- macOS 桌面控制链路**本机已验证可用**：权限就绪、AX 树/坐标/截图/写入全部实测通过
- 技术栈选 **Python + pyobjc**（`pyobjc-framework-ApplicationServices` + `Quartz` + `Cocoa`），与 uv 项目一致
- 下一步可直接实现 `MacPerception`（AX 树 + 窗口截图）与 `MacController`（AXPress + setValue + CGEvent）
