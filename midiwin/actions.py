from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes
from typing import Any

from .common import APP_DIR, ControlEvent
from .eventlog import emit

user32 = ctypes.windll.user32

WM_CLOSE = 0x0010
KEYEVENTF_KEYUP = 0x0002
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x00000002
SW_RESTORE = 9
SW_MAXIMIZE = 3


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class ActionDispatcher:
    def __init__(self, config: dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

    def _log(self, message: str) -> None:
        print(message, flush=True)
        emit("action_log", message=message, dry_run=self.dry_run)

    @staticmethod
    def _foreground() -> int:
        return int(user32.GetForegroundWindow())

    @staticmethod
    def _rect(hwnd: int) -> RECT:
        rect = RECT()
        if not hwnd or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("no foreground window")
        return rect

    def _media_key(self, key: int, name: str) -> None:
        self._log(f"action={name}")
        if self.dry_run:
            return
        user32.keybd_event(key, 0, 0, 0)
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)

    def _move_resize(self, dx: int = 0, dy: int = 0, dw: int = 0, dh: int = 0) -> None:
        hwnd = self._foreground()
        rect = self._rect(hwnd)
        x, y = rect.left + dx, rect.top + dy
        width = max(160, rect.right - rect.left + dw)
        height = max(120, rect.bottom - rect.top + dh)
        self._log(f"action=window_geometry x={x} y={y} width={width} height={height}")
        if not self.dry_run:
            user32.ShowWindow(hwnd, SW_RESTORE)
            if not user32.MoveWindow(hwnd, x, y, width, height, True):
                raise ctypes.WinError()

    def _set_opacity(self, ratio: float) -> None:
        hwnd = self._foreground()
        alpha = max(64, min(255, round(ratio * 255)))
        self._log(f"action=window_opacity alpha={alpha}")
        if self.dry_run:
            return
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
        if not user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA):
            raise ctypes.WinError()

    def _set_volume(self, ratio: float) -> None:
        self._log(f"action=volume_absolute value={ratio:.3f}")
        if self.dry_run:
            return
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        endpoint = device.EndpointVolume
        endpoint.SetMasterVolumeLevelScalar(float(ratio), None)

    def _brightness_settings(self) -> dict[str, Any]:
        controls = self.config.get("display_controls", {})
        if not isinstance(controls, dict):
            return {}
        value = controls.get("brightness", {})
        return value if isinstance(value, dict) else {}

    def set_brightness_percent(self, percent: int,
                               mapping: dict[str, Any] | None = None) -> bool:
        mapping = mapping or {}
        settings = self._brightness_settings()
        minimum = int(mapping.get("minimum_percent", settings.get("minimum_percent", 1)))
        percent = min(max(int(percent), minimum), 100)
        display: Any = mapping.get("display", settings.get("display", None))
        if display == "":
            display = None
        self._log(f"action=brightness_absolute percent={percent} display={display!r}")
        if self.dry_run:
            return True
        try:
            import screen_brightness_control as sbc
            kwargs = {"display": display} if display is not None else {}
            sbc.set_brightness(percent, **kwargs)
            emit("action_result", action="brightness_absolute", backend="screen_brightness_control", success=True, percent=percent)
            return True
        except Exception as primary:
            self._log(f"screen_brightness_control failed: {primary}")

        command = [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$m=Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
            "-ErrorAction Stop | Where-Object Active; "
            "if(-not $m){throw 'No active WMI brightness monitor'}; "
            f"$m | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=0;Brightness=[byte]{percent}}} "
            "-ErrorAction Stop | Out-Null",
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode == 0:
            emit("action_result", action="brightness_absolute", backend="wmi", success=True, percent=percent)
            return True
        error = (result.stderr or result.stdout).strip()
        self._log("WMI brightness fallback failed: " + error)
        emit("action_result", action="brightness_absolute", backend="wmi", success=False, percent=percent, error=error)
        return False

    def diagnose_displays(self) -> list[str]:
        lines: list[str] = []
        try:
            import screen_brightness_control as sbc
            monitors = sbc.list_monitors_info()
            if monitors:
                for index, monitor in enumerate(monitors):
                    lines.append(f"display[{index}]={monitor}")
            else:
                lines.append("screen_brightness_control found no displays")
        except Exception as exc:
            lines.append(f"screen_brightness_control error: {exc}")
        command = [
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods "
            "-ErrorAction SilentlyContinue | Select-Object Active,InstanceName | Format-List | Out-String",
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        text = (result.stdout or result.stderr).strip()
        lines.append("WMI brightness methods:\n" + (text or "none"))
        return lines

    def _controller_brightness(self, ratio: float) -> None:
        path = APP_DIR / "controller-brightness"
        value = round(ratio * 100)
        self._log(f"action=controller_brightness value={value}")
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{value}\n", encoding="utf-8")

    def _run_script_slot(self, slot: str) -> None:
        spec = self.config.get("script_slots", {}).get(slot, {})
        if not spec.get("enabled", False):
            self._log(f"script slot disabled: {slot}")
            return
        command = spec.get("command")
        self._log(f"action=script_slot slot={slot} command={command}")
        if self.dry_run:
            return
        if isinstance(command, str):
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", command])
        elif isinstance(command, list):
            subprocess.Popen([os.path.expandvars(str(v)) for v in command])
        else:
            raise ValueError(f"invalid command for slot {slot}")

    def dispatch(self, mapping: dict[str, Any], event: ControlEvent) -> None:
        action = str(mapping["action"])
        emit(
            "action_dispatch",
            action=action,
            dry_run=self.dry_run,
            mapping={
                "device": mapping.get("device"),
                "control": mapping.get("control"),
                "kind": mapping.get("kind"),
                "requires": mapping.get("requires", []),
                "unless": mapping.get("unless", []),
                "slot": mapping.get("slot"),
                "parameter": mapping.get("parameter"),
            },
            event={
                "device": event.device,
                "control": event.control,
                "kind": event.kind,
                "value": event.value,
                "minimum": event.minimum,
                "maximum": event.maximum,
                "ratio": event.ratio,
            },
        )
        sensitivity = int(mapping.get("sensitivity", 40))
        if action == "media_play_pause":
            self._media_key(VK_MEDIA_PLAY_PAUSE, action)
        elif action == "media_next":
            self._media_key(VK_MEDIA_NEXT_TRACK, action)
        elif action == "media_previous":
            self._media_key(VK_MEDIA_PREV_TRACK, action)
        elif action == "volume_mute":
            self._media_key(VK_VOLUME_MUTE, action)
        elif action == "volume_absolute":
            self._set_volume(event.ratio)
        elif action == "brightness_absolute":
            self.set_brightness_percent(round(event.ratio * 100), mapping)
        elif action == "controller_brightness_absolute":
            self._controller_brightness(event.ratio)
        elif action == "close_focused_window":
            hwnd = self._foreground()
            self._log("action=close_focused_window")
            if not self.dry_run and hwnd:
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        elif action == "window_move_horizontal_relative":
            self._move_resize(dx=event.value * sensitivity)
        elif action == "window_move_vertical_relative":
            self._move_resize(dy=event.value * sensitivity)
        elif action == "window_resize_width_relative":
            self._move_resize(dw=event.value * sensitivity)
        elif action == "window_resize_height_relative":
            self._move_resize(dh=event.value * sensitivity)
        elif action == "window_opacity_absolute":
            self._set_opacity(event.ratio)
        elif action == "window_maximize":
            hwnd = self._foreground()
            self._log("action=window_maximize")
            if not self.dry_run and hwnd:
                user32.ShowWindow(hwnd, SW_MAXIMIZE)
        elif action == "window_restore":
            hwnd = self._foreground()
            self._log("action=window_restore")
            if not self.dry_run and hwnd:
                user32.ShowWindow(hwnd, SW_RESTORE)
        elif action == "open_terminal":
            self._log("action=open_terminal")
            if not self.dry_run:
                subprocess.Popen(["wt.exe"])
        elif action == "open_browser":
            self._log("action=open_browser")
            if not self.dry_run:
                os.startfile("https://www.google.com")
        elif action == "script_slot":
            self._run_script_slot(str(mapping.get("slot", "")))
        else:
            self._log(f"unknown action: {action}")
