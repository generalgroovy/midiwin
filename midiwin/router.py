from __future__ import annotations

from typing import Any

from .actions import ActionDispatcher
from .common import ControlEvent
from .eventlog import emit as emit_event


class EventRouter:
    def __init__(self, config: dict[str, Any], dry_run: bool = False, monitor: bool = False):
        self.config = config
        self.dispatcher = ActionDispatcher(config, dry_run=dry_run)
        self.monitor = monitor
        self.dry_run = dry_run
        self.modifiers: set[str] = set()

    def _modifier_name(self, event: ControlEvent) -> str | None:
        if event.control in {"shift", "hotcue"}:
            return f"{event.device}.{event.control}"
        return None

    def emit(self, event: ControlEvent) -> None:
        emit_event(
            "control_input",
            monitor=self.monitor,
            dry_run=self.dry_run,
            device=event.device,
            control=event.control,
            event_kind=event.kind,
            value=event.value,
            minimum=event.minimum,
            maximum=event.maximum,
            ratio=event.ratio,
            held_modifiers=sorted(self.modifiers),
        )
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
            emit_event(
                "modifier_state",
                modifier=modifier,
                event_kind=event.kind,
                held_modifiers=sorted(self.modifiers),
            )

        matched = 0
        for index, mapping in enumerate(self.config.get("mappings", [])):
            if not isinstance(mapping, dict) or not mapping.get("enabled", True):
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
            matched += 1
            emit_event(
                "mapping_selected",
                mapping_index=index,
                action=mapping.get("action"),
                device=event.device,
                control=event.control,
                event_kind=event.kind,
                requires=sorted(required),
                unless=sorted(excluded),
                held_modifiers=sorted(self.modifiers),
            )
            self.dispatcher.dispatch(mapping, event)
        if matched == 0:
            emit_event(
                "mapping_unmatched",
                device=event.device,
                control=event.control,
                event_kind=event.kind,
                held_modifiers=sorted(self.modifiers),
            )
