# 架构设计（Architecture）

## 核心思想

macOS / Android / iOS 底层完全不同，但暴露给 agent 的抽象可以统一：
三者都是 **树形 UI 结构 + 截图**，元素都带 **id / text / role / bounds** 四要素。
因此架构把平台差异全部吸收在 `DeviceBackend` 实现层，
orchestrator 与 LLM 只认识统一模型（core/types.py），不认识任何平台概念
（AXFrame、resource-id、WDA path 等）。

## 分层

```
+-------------------------------------------------------------+
|            AgentOrchestrator (core/orchestrator.py)          |
|  目标理解 -> 循环(perceive -> LLM decide -> act -> verify)    |
+-----------------------------+-------------------------------+
                              | 只依赖抽象接口 DeviceBackend
+-----------------------------v-------------------------------+
|                   DeviceBackend (backends/base.py)           |
|  perceive() -> ScreenState   |   act(Action) -> ActionResult |
+--------+----------------+----+----------------+--------------+
         |                |                   |
  +------v-----+   +------v------+   +--------v--------+
  | MacOSBackend|  |AndroidBackend|  |   IOSBackend     |
  | AX+CGEvent  |  | adb+UA+scrcpy|  | Appium/WDA       |
  | (已实现)    |  | (骨架)       |  | (骨架)           |
  +------------+   +-------------+   +-----------------+
```

## 统一数据模型（core/types.py）

- `Element`: ref / role(归一化) / text / bounds / children / meta
- `Rect` / `Point`: **归一化坐标 0-1000**，跨分辨率可比较
  （macOS 2560x1440 vs 手机 1080x2400）
- `ScreenState`: tree + screenshot + app + platform
- `Action`: 统一动作空间（tap/type/swipe/scroll/key/open_app/back/home/
  app_switch/wait/copy/paste/long_press/pinch/done）

## 为什么元素引用优先、坐标兜底

1. 纯坐标对分辨率、窗口移动、滚动后错位极脆弱
2. AXIdentifier / resource-id / WDA identifier 三端都有，是跨平台最稳锚点
3. 视觉模型输出坐标时可反查最近元素转语义执行

## 手机扩展的兼容映射

Android 接入 = 新增一个 backend 实现，orchestrator 与 LLM schema 零改动：

```
uiautomator dump XML node                      -> Element
  resource-id / text / class / bounds            ref / text / role / Rect

统一 Action       -> macOS            -> Android            -> iOS
tap(ref)          AXPress             input tap (bounds)    WDA tap
type(text)        set AXValue         ADBKeyboard/IME       WDA sendKeys
swipe             CGEvent drag        input swipe           WDA swipe
key(back/home)    窗口切换(no-op)      keyevent 4/3          WDA pressButton
open_app(id)      NSWorkspace         am start              openurl
screenshot        screencapture       exec-out screencap    WDA screenshot
```

## 为手机预留的扩展点

1. **手势类**：long_press / pinch 已列入 Action（macOS 返回 unsupported）
2. **物理导航**：back / home / app_switch 已是一级动作（macOS no-op）
3. **弹窗干扰**：Android/iOS 权限弹窗/广告，需内置 dismiss 策略 + wait 原语
4. **输入法**：中文输入三端机制不同，统一在 type 内屏蔽差异
5. **实时屏幕流**：Android scrcpy / macOS ScreenCaptureKit，统一为 capture 差异

## LLM 接入（llm/）

- `schema.py`: 统一动作 JSON Schema，平台无关
- `client.py`: LLMClient ABC + AnthropicClient（Messages API + tool-use）+
  DummyClient（离线冒烟测试）
- 观察上下文: 压缩 UI 树 + 截图（macOS 需裁剪活动窗口省 token，手机整屏）

## 目录结构

```
control_everything/
  core/          平台无关（orchestrator 只依赖这里）
    types.py     Element/ScreenState/Action 统一模型
    orchestrator.py   observe-plan-act-verify 主循环
    planner.py   任务分解（Phase 2: LLM-backed checklist）
    verify.py    步骤验证启发式
  backends/      平台实现（唯一的平台分叉点）
    base.py      DeviceBackend ABC + 异常
    macos.py     AX + CGEvent（pyobjc，已实现）
    android.py   adb + uiautomator + scrcpy（骨架）
    ios.py       Appium/WDA（骨架）
  llm/           大脑接入
    schema.py    统一动作 JSON Schema
    client.py    多模型客户端
  main.py        CLI 入口
  server.py      (规划) MCP server 封装
```

## 决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 坐标表示 | 归一化 0-1000 | 跨分辨率复用 prompt 模板、LLM 更易理解 |
| 动作定位 | 元素 ref 优先、坐标兜底 | 稳定性（agent-ctrl 实测） |
| 控制策略 | 三层混合（AX -> CGEvent -> 视觉） | 自绘 UI / Electron 兜底 |
| 验证 | 独立 verify 模块、可开关 | AX 读回不可靠，需启发式 |
| MCP | 先做自有 orchestrator，预留封装层 | 控制权归属清晰，生态兼容后期加 |
| 手机扩展 | 新增 backend + 解析器即可 | 数据模型三端同构 |
