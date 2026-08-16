# Control_Everything

> 用 AI 控制一切 —— 一个能「看」界面、「操作」界面的自主 GUI Agent。

**Control_Everything** 是一个自主 **GUI Agent**：它能感知并操作任何带交互界面的设备
（手机、电脑、平板），端到端完成用户指派的任务——点外卖、买除湿机、订机票等等。
用户只需说出目标，剩下的交给 Agent。

---

## 它能做什么

给定一个自然语言任务，Agent 自主完成：

1. **观察**当前屏幕（截图 + UI 可访问性树 / OCR）
2. **规划**下一步动作（点击、输入、滑动、滚动、等待……）
3. **执行**动作到真实设备
4. **验证**结果并迭代，直到任务完成

```
+--------------------------------------------------------------------------+
|                    任务编排器（LLM Agent）                                |
|  "买除湿机" -> 打开应用 -> 搜索 -> 筛选 -> 加购 -> 下单 -> 确认 -> 验证订单   |
+-----------------------------+---------------------------+----------------+
|                             |                           |                |
|          观察               |           执行            |                |
|                             |                           |                |
+-----------------------------v----------------------------+---------------+
|  感知层                     |  控制层                                    |
|  . 屏幕截图                 |  . 桌面端: 可访问性 API (macOS / Windows)   |
|  . UI 层级树                |  . Android: adb + UIAutomator / scrcpy     |
|  . OCR / 视觉理解           |  . iOS: XCUITest / Appium                  |
+-----------------------------+-------------------------------------------+
```

## 目标平台

| 平台 | 控制机制 | 状态 |
|---|---|---|
| macOS 桌面 | 可访问性 API（pyobjc）+ CGEvent | 已实现（可用） |
| Android | adb + UIAutomator + scrcpy | 骨架（映射已设计） |
| iOS | Appium / WebDriverAgent | 骨架（映射已设计） |
| Windows 桌面 | pywinauto / UIAutomation | 未开始 |

## 大脑选型

- 云 API：Anthropic Computer Use、OpenAI Operator
- 开源 / 本地视觉模型：UI-TARS、Qwen2.5-VL / Qwen3 系列
- 当前支持（OpenAI 兼容协议）：DeepSeek、Qwen、GLM、Kimi、OpenRouter、Ollama 等

## Roadmap

- [x] 核心 Agent 循环（观察 -> 规划 -> 执行 -> 验证）- `core/orchestrator.py`
- [x] 统一数据模型与动作空间 - `core/types.py`（Element 树、归一化坐标、统一 Action）
- [x] macOS 桌面控制器 - `backends/macos.py`（AX + CGEvent，macOS 26.5.2 实测）
- [x] 视觉接入 - `llm/vision.py`（qwen3.7-plus 看截图，给纯文本大脑装上眼睛）
- [ ] Android 控制器（adb / scrcpy）- `backends/android.py` 骨架
- [ ] iOS 控制器（Appium / WDA）- `backends/ios.py` 骨架
- [ ] LLM 任务规划 - `core/planner.py` 桩
- [ ] MCP server 封装 - `server.py`（规划中）

## 快速开始

需要 [uv](https://docs.astral.sh/uv/) 和 Python 3.14.5（已固化在 `.python-version`）。
macOS 后端还需要在「系统设置 > 隐私与安全性」中授予**辅助功能**与**屏幕录制**权限。

```bash
uv sync                                            # 创建虚拟环境并安装依赖
uv run python main.py --platform macos --inspect   # 导出当前 UI 树
uv run python main.py --goal "打开 Safari" --platform macos   # 运行 Agent（需在 .env 配置模型）
uv run python main.py --goal "..." --llm dummy --platform macos # 离线冒烟测试
```

### 配置（`.env`，按用途配置完整供应商信息）

复制 [`.env.example`](.env.example) 为 `.env` 并填入 API key。每个用途是一个**完整的
供应商配置块**，换供应商无需改代码：

```
# {PURPOSE}_PROVIDER   anthropic | openai（openai 覆盖所有 OpenAI 兼容端点）
# {PURPOSE}_BASE_URL   端点地址（留空 = 供应商默认）
# {PURPOSE}_API_KEY    认证密钥
# {PURPOSE}_MODEL      模型标识
DECISION_PROVIDER=deepseek
DECISION_BASE_URL=https://api.deepseek.com
DECISION_API_KEY=sk-...
DECISION_MODEL=deepseek-v4-flash
```

支持的供应商：**anthropic**（官方或兼容端点）与 **openai**（任意 OpenAI 兼容端点——
DeepSeek、Qwen、GLM、Kimi、OpenRouter、Ollama、vLLM、LM Studio……）。

模型推荐配置（DeepSeek / Qwen / OpenRouter）：见
[docs/model-recommendations.md](docs/model-recommendations.md)。

## 架构

完整设计见 [docs/architecture.md](docs/architecture.md)——重点：统一的 `Element` 树 +
`Action` 空间让 Agent 循环与平台无关，Android / iOS 只需新增 `DeviceBackend` 实现即可接入。
调研笔记：[docs/macos-accessibility-research.md](docs/macos-accessibility-research.md)。

## 许可证

[MIT](LICENSE)
