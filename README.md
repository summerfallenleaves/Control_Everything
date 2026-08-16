# Control_Everything

> Use AI to control everything - an autonomous agent that sees and operates any GUI.

**Control_Everything** is an autonomous **GUI Agent** that perceives and operates any device with an
interactive interface - phones, desktops, tablets - to complete user-assigned tasks end to end:
order a takeaway, buy a dehumidifier, book a flight, and so on. The user states the goal;
the agent figures out the rest.

---

## What It Does

Given a natural-language task, the agent autonomously:

1. **Observes** the current screen (screenshot + UI accessibility tree / OCR)
2. **Plans** the next action with an LLM (tap, type, swipe, scroll, wait...)
3. **Executes** the action on the real device
4. **Verifies** the result and iterates until the task is done

```
+--------------------------------------------------------------------------+
|                Task Orchestrator (LLM Agent)                             |
|  "buy a dehumidifier" -> open app -> search -> filter                    |
|  -> add to cart -> checkout -> confirm -> verify order                    |
+-----------------------------+---------------------------+----------------+
|                             |                           |                |
|          observe            |           act             |                |
|                             |                           |                |
+-----------------------------v----------------------------+---------------+
|  Perception Layer            |  Control Layer                            |
|  . screen capture            |  . Desktop: a11y API                      |
|  . UI hierarchy dump         |    (macOS / Windows)                      |
|  . OCR / vision              |  . Android: adb + UIAutomator / scrcpy    |
|                              |  . iOS: XCUITest / Appium                 |
+-----------------------------+-------------------------------------------+
```

## Target Platforms

| Platform | Control mechanism | Status |
|---|---|---|
| macOS desktop | Accessibility API (pyobjc) + CGEvent | Implemented (skeleton) |
| Android | adb + UIAutomator + scrcpy | Skeleton (mapping designed) |
| iOS | Appium / WebDriverAgent | Skeleton (mapping designed) |
| Windows desktop | pywinauto / UIAutomation | Not started |

## Brain Options

- Cloud APIs: Anthropic *Computer Use*, OpenAI *Operator*
- Open / on-prem vision models: UI-TARS, Qwen2.5-VL

## Roadmap

- [x] Core agent loop (observe -> plan -> act -> verify) - `core/orchestrator.py`
- [x] Unified data model & action space - `core/types.py` (Element tree, normalized coords, unified Action)
- [x] macOS desktop controller - `backends/macos.py` (AX + CGEvent, verified on macOS 26.5.2)
- [ ] Android controller (adb / scrcpy) - `backends/android.py` skeleton
- [ ] iOS controller (Appium / WDA) - `backends/ios.py` skeleton
- [ ] LLM-backed task planning - `core/planner.py` stub
- [ ] MCP server wrapper - `server.py` (planned)

## Getting Started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14.5 (pinned in `.python-version`).
macOS backends additionally need **Accessibility** and **Screen Recording** permissions
(System Settings > Privacy & Security).

```bash
uv sync                                            # create venv & install deps
uv run python main.py --platform macos --inspect   # dump the current UI tree
uv run python main.py --goal "open Safari" --platform macos   # run the agent
uv run python main.py --goal "..." --llm dummy --platform macos # offline smoke test
```

### Configuration (`.env`, full provider per purpose)

Copy [`.env.example`](.env.example) to `.env`. Each purpose is a **complete
provider block**, so any vendor can back any role without code changes:

```
# {PURPOSE}_PROVIDER  anthropic | openai (openai covers OpenAI-compatible endpoints)
# {PURPOSE}_BASE_URL  endpoint (empty = provider default)
# {PURPOSE}_API_KEY   authentication
# {PURPOSE}_MODEL     model id
DECISION_PROVIDER=anthropic
DECISION_BASE_URL=
DECISION_API_KEY=sk-ant-...
DECISION_MODEL=claude-sonnet-4-5
```

Supported providers: **anthropic** (official or compatible) and **openai**
(any OpenAI-compatible endpoint - DeepSeek, Moonshot, Qwen, Ollama, vLLM,
LM Studio...).

Examples:

```
# DeepSeek as the decision brain
DECISION_PROVIDER=openai
DECISION_BASE_URL=https://api.deepseek.com
DECISION_API_KEY=sk-...
DECISION_MODEL=deepseek-chat

# Local Qwen via Ollama as vision fallback
VISION_PROVIDER=openai
VISION_BASE_URL=http://localhost:11434/v1
VISION_MODEL=qwen2.5-vl
```

`.env` is git-ignored; commit only `.env.example`. CLI overrides: `--provider`,
`--model`, `--llm dummy` (offline smoke test).

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full design - especially
how the unified `Element` tree + `Action` space keeps the agent loop
platform-agnostic, and how Android / iOS slot in as new `DeviceBackend`s.
Research notes: [docs/macos-accessibility-research.md](docs/macos-accessibility-research.md).

## License

[MIT](LICENSE)
