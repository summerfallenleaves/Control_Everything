# 模型推荐配置（Model Recommendations）

> 更新：2026-08  |  约束：不可用 OpenAI / Anthropic；OpenRouter 视为高成本；
> DeepSeek 与 Qwen 为低成本主力。本文件给出可直接粘贴到 .env 的完整配置。

## 背景：关键事实

- **DeepSeek V4**（2026-04 发布）：`deepseek-chat` / `deepseek-reasoner` 已于
  2026-07-24 **退役**（调用即报错），现在只能使用：
  - `deepseek-v4-flash`：低成本，工具调用好，1M 上下文
  - `deepseek-v4-pro`：更强推理，价格更高
  - 新计费：**峰谷计价**（2026-08-16 起）。峰时 = 北京时间 09:00-12:00 &
    14:00-18:00，为谷时 2 倍；自动上下文缓存命中可再降 80-90%
- **Qwen3.5 系列**（百炼/DashScope，价格按人民币计）：
  - `qwen3.5-flash`：0.2 元/M 输入 + 2 元/M 输出（轻量快）
  - `qwen3.5-plus`：0.8 元/M 输入 + 4.8 元/M 输出（均衡）
  - `qwen3-max`：2.5 元/M 输入 + 10 元/M 输出（旗舰）
  - 视觉：`qwen-vl-max` / `qwen-vl-plus`（多模态）

## 方案 A：均衡首选（推荐默认）

```ini
# DECISION - DeepSeek V4-Flash 直连：便宜 + 工具调用可靠
DECISION_PROVIDER=deepseek
DECISION_BASE_URL=https://api.deepseek.com
DECISION_API_KEY=sk-xxxx
DECISION_MODEL=deepseek-v4-flash

# PLANNING - 与决策同款（任务分解频率低，可共享）
PLANNING_PROVIDER=deepseek
PLANNING_BASE_URL=https://api.deepseek.com
PLANNING_API_KEY=sk-xxxx
PLANNING_MODEL=deepseek-v4-flash

# VISION - 百炼 Qwen-VL（截图理解兜底）
VISION_PROVIDER=qwen
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_API_KEY=sk-xxxx
VISION_MODEL=qwen3.7-plus
```

## 方案 B：极致省钱（大批量/高频）

```ini
# DECISION/PLANNING - Qwen3.5-Flash：0.2 元/M 输入，速度最快
DECISION_PROVIDER=qwen
DECISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DECISION_API_KEY=sk-xxxx
DECISION_MODEL=qwen3.5-flash

PLANNING_PROVIDER=qwen
PLANNING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PLANNING_API_KEY=sk-xxxx
PLANNING_MODEL=qwen3.5-flash

# VISION - qwen-vl-plus（低配视觉足够）
VISION_PROVIDER=qwen
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_API_KEY=sk-xxxx
VISION_MODEL=qwen3.7-flash
```

## 方案 C：效果优先（低成本档内最强）

```ini
# DECISION - DeepSeek V4-Pro：推理最强；注意错峰（谷时省一半）
DECISION_PROVIDER=deepseek
DECISION_BASE_URL=https://api.deepseek.com
DECISION_API_KEY=sk-xxxx
DECISION_MODEL=deepseek-v4-pro

# PLANNING - 规划降档用 flash，省钱且效果损失小
PLANNING_PROVIDER=deepseek
PLANNING_BASE_URL=https://api.deepseek.com
PLANNING_API_KEY=sk-xxxx
PLANNING_MODEL=deepseek-v4-flash

# VISION - qwen-vl-max
VISION_PROVIDER=qwen
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_API_KEY=sk-xxxx
VISION_MODEL=qwen3.7-plus
```

## 为什么这样选

| 角色 | 推荐 | 理由 |
|---|---|---|
| 决策 | deepseek-v4-flash / qwen3.5-plus | GUI agent 每步都要实时决策：需要强工具调用、低延迟；两个都是该价位工具调用最稳的 |
| 规划 | 与决策同款或 qwen3.5-flash | 任务分解频率低，对延迟不敏感，可以降档省钱 |
| 视觉 | qwen3.7-plus / qwen3.7-flash | 百炼推荐的新一代统一多模态：支持 Function Calling + 结构化输出，正好匹配截图理解需求；DeepSeek 官方 API 纯文本无视觉 |


## 视觉模型专项（效果优先）

**重要事实：DeepSeek 官方 API 是纯文本**（2026-07 确认），`deepseek-v4-*` 均不支持
图片输入，视觉必须走 Qwen（或 OpenRouter 上的 VLM）。

百炼当前推荐的新一代统一多模态（旧版 qwen-vl-max/plus 已不作为新项目首选）：

| 模型 | 能力 | 定位 |
|---|---|---|
| `qwen3.8-max` | 对应 GPT-5.5/Claude Opus 档位 | 效果最强，价格高（可不考虑） |
| `qwen3.7-plus` | 1M 上下文、2h 视频、FC、结构化输出 | **旗舰多模态，效果优先首选** |
| `qwen3.7-flash` | 同上（256 图/次） | 接近旗舰效果，成本更低 |
| `qwen3.5-ocr` | 文档/表格/试卷/手写 OCR 优化 | OCR 专项（验证码/证件场景） |

**为什么 qwen3.7 系列适合 GUI agent**：它们是统一多模态（图像+视频+文本），
且支持 **Function Calling + 结构化输出**——视觉模型可以直接输出动作 JSON，
正好覆盖「AX 树缺失时的截图理解兜底」，还能独立承担视觉决策。

```ini
# 效果优先视觉配置
VISION_PROVIDER=qwen
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VISION_API_KEY=sk-xxxx
VISION_MODEL=qwen3.7-plus

# 性价比视觉配置（接近旗舰效果）
# VISION_MODEL=qwen3.7-flash
```

## OpenRouter 的定位

OpenRouter 聚合加价 + 高端模型昂贵，适合偶尔试跑强模型
（如 anthropic/claude-*、openai/gpt-*），不适合作为日常低成本主力：

```ini
DECISION_PROVIDER=openrouter
DECISION_BASE_URL=https://openrouter.ai/api/v1
DECISION_API_KEY=sk-or-xxxx
DECISION_MODEL=deepseek/deepseek-v4-flash   # OpenRouter 上也有低价模型
```

## 思考模式配置（DeepSeek）

DeepSeek 默认**思考开启且 effort=high**。GUI agent 每步实时决策建议：

```ini
DECISION_THINKING=disabled          # 快速稳定（推荐）
# 需要更强推理时：
# DECISION_THINKING=enabled
# DECISION_THINKING_EFFORT=medium   # minimal/low/medium/high
```

注意：DeepSeek 只接受 effort 值 low/high/max（medium 映射为 high）；
思考模式下不支持强制 tool_choice，故 agent 采用宽松模式（auto），
orchestrator 可接受模型输出文本（观察/等待）。


## 省钱要点

1. **DeepSeek 错峰**：北京时间 09:00-12:00 & 14:00-18:00 是峰时（2 倍价），
   长任务调度到谷时可省一半
2. **上下文缓存**：DeepSeek 自动缓存重复前缀（system prompt/tool schema 不变），
   命中后输入成本降 80-90%
3. **规划降档**：PLANNING 用比 DECISION 便宜的模型