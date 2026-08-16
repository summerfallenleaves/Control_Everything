"""Unified action JSON schema for LLM structured output.

The LLM only ever emits one of these actions. Every backend implements
exactly this action space, so the schema is platform-agnostic and never
changes when a new device type is added.
"""

from core.types import ActionKind

ACTION_KINDS_LIST = list(ActionKind.__args__)

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ACTION_KINDS_LIST},
        "reasoning": {"type": "string", "description": "short rationale for the action"},
        "target": {"type": ["string", "null"], "description": "element ref from the provided UI tree"},
        "pos": {"type": ["object", "null"], "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "description": "normalized 0-1000 coordinate fallback"},
        "text": {"type": ["string", "null"], "description": "text to type / app id to open"},
        "dir": {"type": ["string", "null"], "enum": ["up", "down", "left", "right", None]},
        "key": {"type": ["string", "null"], "description": "key name, e.g. return / escape / v"},
        "modifiers": {"type": "array", "items": {"type": "string"}},
        "duration_s": {"type": "number"},
        "to": {"type": ["object", "null"], "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
    },
    "required": ["kind", "reasoning"],
}

OBSERVATION_PROMPT = """
You are an autonomous GUI agent. You operate a real device by emitting one
JSON action at a time. The UI tree below lists clickable/visible elements
with stable refs and normalized coordinates (0-1000). Use element refs
whenever possible; coordinates only as a fallback.

Available actions: tap, type, swipe, scroll, key, open_app, back, home,
app_switch, wait, copy, paste, long_press, pinch, done.

You may reply with SHORT text ONLY when you genuinely cannot pick an
action yet (e.g. waiting for the page to load). Otherwise you MUST call
the gui_action tool - do not narrate, do not restate the plan.

Return exactly one JSON object matching the action schema.
"""
