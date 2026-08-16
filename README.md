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
| macOS desktop | Accessibility API / AppleScript | Planned |
| Windows desktop | pywinauto / UIAutomation | Planned |
| Android | adb + UIAutomator + scrcpy | Planned |
| iOS | XCUITest / Appium | Planned |

## Brain Options

- Cloud APIs: Anthropic *Computer Use*, OpenAI *Operator*
- Open / on-prem vision models: UI-TARS, Qwen2.5-VL

## Roadmap

- [ ] Core agent loop (observe -> plan -> act -> verify)
- [ ] macOS desktop controller (first runnable target)
- [ ] Android controller (adb / scrcpy)
- [ ] Task planning & self-verification
- [ ] Multi-platform abstraction layer

## Getting Started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14.5 (pinned in `.python-version`).

```bash
uv sync        # create venv & install deps
uv run python main.py
```

## License

[MIT](LICENSE)
