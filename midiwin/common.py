from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "MidiWin"
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.default.json"
_SUPPORTED_KINDS = {"press", "release", "relative", "absolute"}


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


def _tokens(mapping: dict[str, Any], field: str, index: int, errors: list[str]) -> tuple[str, ...]:
    value = mapping.get(field, [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        errors.append(f"mapping {index} {field} must be a string or array")
        return ()
    tokens = tuple(sorted(str(item).strip() for item in value if str(item).strip()))
    if len(tokens) != len(set(tokens)):
        errors.append(f"mapping {index} {field} contains duplicates")
    return tokens


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mappings = config.get("mappings")
    if not isinstance(mappings, list):
        return ["mappings must be an array"]
    seen: dict[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], int] = {}
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            errors.append(f"mapping {index} must be an object")
            continue
        for field in ("device", "control", "kind", "action"):
            if not isinstance(mapping.get(field), str) or not mapping[field].strip():
                errors.append(f"mapping {index} missing {field}")
        kind = str(mapping.get("kind", ""))
        if kind and kind not in _SUPPORTED_KINDS:
            errors.append(f"mapping {index} has unsupported kind {kind!r}")
        requires = _tokens(mapping, "requires", index, errors)
        unless = _tokens(mapping, "unless", index, errors)
        overlap = sorted(set(requires).intersection(unless))
        if overlap:
            errors.append(
                f"mapping {index} requires and excludes the same modifier(s): {', '.join(overlap)}"
            )
        if not mapping.get("enabled", True):
            continue
        key = (
            str(mapping.get("device", "")),
            str(mapping.get("control", "")),
            kind,
            requires,
            unless,
        )
        if key in seen:
            errors.append(
                f"ambiguous mapping {index}: same input and modifier conditions as mapping {seen[key]}: {key}"
            )
        else:
            seen[key] = index
    from .autocode import validate as validate_autocode

    errors.extend(validate_autocode(config))
    return errors
