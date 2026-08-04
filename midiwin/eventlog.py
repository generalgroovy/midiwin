from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import APP_DIR

_LOCK = threading.Lock()
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:password|passwd|token|api[_-]?key)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_path() -> Path:
    configured = os.environ.get("MIDIWIN_EVENT_LOG", "").strip()
    return Path(configured).expanduser() if configured else APP_DIR / "events.jsonl"


def redact(value: Any) -> Any:
    if isinstance(value, str):
        rendered = value
        for pattern in _SECRET_PATTERNS:
            if pattern.groups:
                rendered = pattern.sub(r"\1<REDACTED>", rendered)
            else:
                rendered = pattern.sub("<REDACTED>", rendered)
        return rendered
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def emit(kind: str, **fields: Any) -> dict[str, Any]:
    event = {
        "schema_version": 1,
        "timestamp": utcnow(),
        "kind": str(kind),
        **redact(fields),
    }
    path = event_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return event


def read_tail(limit: int = 100) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("event tail limit must be positive")
    path = event_path()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def clear() -> bool:
    path = event_path()
    if not path.exists():
        return False
    with _LOCK:
        path.unlink(missing_ok=True)
    return True
