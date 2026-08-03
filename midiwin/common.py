from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "MidiWin"
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.default.json"


@dataclass(frozen=True)
class ControlEvent:
    device: str
    control: str
    kind: str
    value: int
    minimum: int = 0
    maximum: int = 1

    @property
    def ratio(self) -> float:
        span = self.maximum - self.minimum
        if span <= 0:
            return 0.0
        return min(max((self.value - self.minimum) / span, 0.0), 1.0)


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or APP_DIR / "config.json"
    if not target.exists():
        target = DEFAULT_CONFIG
    value = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("configuration root must be an object")
    return value


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mappings = config.get("mappings")
    if not isinstance(mappings, list):
        return ["mappings must be an array"]
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            errors.append(f"mapping {index} must be an object")
            continue
        for field in ("device", "control", "kind", "action"):
            if not isinstance(mapping.get(field), str) or not mapping[field]:
                errors.append(f"mapping {index} missing {field}")
        key = (
            str(mapping.get("device", "")),
            str(mapping.get("control", "")),
            str(mapping.get("kind", "")),
            tuple(sorted(str(v) for v in mapping.get("requires", []))),
        )
        if key in seen:
            errors.append(f"duplicate mapping: {key}")
        seen.add(key)
    return errors
