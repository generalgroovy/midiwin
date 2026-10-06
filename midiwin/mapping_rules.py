"""Pure routing rules shared by the runtime and the offline inspector.

This module deliberately has no action, device or subprocess imports.
"""
from __future__ import annotations

from typing import Any

SUPPORTS_PROFILES = False


def layer_reasons(mapping: dict[str, Any], held: set[str]) -> list[str]:
    for field in ("requires", "unless"):
        values = mapping.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
            return [f"Invalid {field}: use a list of modifier names"]
    missing = [v for v in mapping.get("requires", []) if v not in held]
    blocked = [v for v in mapping.get("unless", []) if v in held]
    return (["Hold " + ", ".join(missing)] if missing else []) + (["Release " + ", ".join(blocked)] if blocked else [])


def update_modifiers(held: set[str], device: str, control: str, kind: str) -> None:
    if control in {"shift", "hotcue"}:
        if kind == "press":
            held.add(f"{device}.{control}")
        elif kind == "release":
            held.discard(f"{device}.{control}")


def preview_event(config: dict[str, Any], device: str, control: str, kind: str,
                  held_text: str = "", profile: str = "") -> dict[str, Any]:
    if kind not in {"press", "release", "relative", "absolute"}:
        raise ValueError("Choose press, release, relative or absolute.")
    if not device.strip() or not control.strip():
        raise ValueError("Choose a device and control.")
    device, control = device.strip(), control.strip()
    held = set(held_text.replace(",", " ").split())
    unsupported = [v for v in held if "." not in v or v.split(".", 1)[1] not in {"shift", "hotcue"}]
    if unsupported:
        raise ValueError("MIDIWIN holds qualified shift/hotcue modifiers, such as f1.shift. Unsupported: " + ", ".join(sorted(unsupported)))
    # Windows removes a released modifier before evaluating its mappings.
    update_modifiers(held, device, control, kind)
    decisions = []
    for index, mapping in enumerate(config.get("mappings", [])):
        if not isinstance(mapping, dict) or (mapping.get("device"), mapping.get("control")) != (device, control):
            continue
        reasons = []
        if not mapping.get("enabled", True):
            reasons.append("Disabled")
        if mapping.get("kind") != kind:
            reasons.append("Needs " + str(mapping.get("kind", "event kind")))
        reasons.extend(layer_reasons(mapping, held))
        decisions.append((index, mapping, reasons))
    return {"control": control, "profile": "", "decisions": decisions}
