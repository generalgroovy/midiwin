from __future__ import annotations

from typing import Any

from .actions import ActionDispatcher
from .common import ControlEvent


class EventRouter:
    def __init__(self, config: dict[str, Any], dry_run: bool = False, monitor: bool = False):
        self.config = config
        self.dispatcher = ActionDispatcher(config, dry_run=dry_run)
        self.monitor = monitor
        self.modifiers: set[str] = set()

    def _modifier_name(self, event: ControlEvent) -> str | None:
        if event.control in {"shift", "hotcue"}:
            return f"{event.device}.{event.control}"
        return None

    def emit(self, event: ControlEvent) -> None:
        if self.monitor:
            print(
                f"device={event.device} control={event.control} kind={event.kind} "
                f"value={event.value} min={event.minimum} max={event.maximum}",
                flush=True,
            )

        modifier = self._modifier_name(event)
        if modifier:
            if event.kind == "press":
                self.modifiers.add(modifier)
            elif event.kind == "release":
                self.modifiers.discard(modifier)

        for mapping in self.config.get("mappings", []):
            if not mapping.get("enabled", True):
                continue
            if mapping.get("device") != event.device:
                continue
            if mapping.get("control") != event.control:
                continue
            if mapping.get("kind") != event.kind:
                continue
            required = set(mapping.get("requires", []))
            excluded = set(mapping.get("unless", []))
            if not required.issubset(self.modifiers) or excluded.intersection(self.modifiers):
                continue
            self.dispatcher.dispatch(mapping, event)
