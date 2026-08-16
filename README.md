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
uv run python main.py --goal "open Safari" --platform macos   # run the agent (needs ANTHROPIC_API_KEY)
uv run python main.py --goal "..." --llm dummy --platform macos # offline smoke test
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full design - especially
how the unified `Element` tree + `Action` space keeps the agent loop
platform-agnostic, and how Android / iOS slot in as new `DeviceBackend`s.
Research notes: [docs/macos-accessibility-research.md](docs/macos-accessibility-research.md).

## License

[MIT](LICENSE)
