"""Helpers for user-defined writable controls (for firmware without varinfo).

A control is stored in ``entry.options["controls"]`` as a plain dict so it
survives serialization. Shapes:

    {"type": "switch", "uri": str, "name": str | "", "on": int, "off": int}
    {"type": "number", "uri": str, "name": str | "", "min": float,
     "max": float, "step": float}
    {"type": "select", "uri": str, "name": str | "", "options": {label: int}}
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

CONF_CONTROLS = "controls"


def get_controls(entry: ConfigEntry, control_type: str | None = None) -> list[dict]:
    controls = entry.options.get(CONF_CONTROLS, [])
    if control_type is None:
        return list(controls)
    return [c for c in controls if c.get("type") == control_type]


def controlled_uris(entry: ConfigEntry) -> set[str]:
    return {c["uri"] for c in entry.options.get(CONF_CONTROLS, [])}
