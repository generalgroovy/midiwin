from __future__ import annotations

import struct
import threading
import time
from typing import Any, Callable

from .common import ControlEvent

NI_VENDOR_ID = 0x17CC
F1_PRODUCT_ID = 0x1120
X1_PRODUCT_ID = 0x2305

F1_BUTTON_MASKS = {
    "grid_8": 0x00000001, "grid_7": 0x00000002,
    "grid_6": 0x00000004, "grid_5": 0x00000008,
    "grid_4": 0x00000010, "grid_3": 0x00000020,
    "grid_2": 0x00000040, "grid_1": 0x00000080,
    "grid_16": 0x00000100, "grid_15": 0x00000200,
    "grid_14": 0x00000400, "grid_13": 0x00000800,
    "grid_12": 0x00001000, "grid_11": 0x00002000,
    "grid_10": 0x00004000, "grid_9": 0x00008000,
    "select_push": 0x00040000, "browse": 0x00080000,
    "size": 0x00100000, "type": 0x00200000,
    "reverse": 0x00400000, "shift": 0x00800000,
    "capture": 0x02000000, "quant": 0x04000000,
    "sync": 0x08000000, "play_4": 0x10000000,
    "play_3": 0x20000000, "play_2": 0x40000000,
    "play_1": 0x80000000,
}
F1_ANALOG_OFFSETS = {
    "knob_1": 6, "knob_2": 8, "knob_3": 10, "knob_4": 12,
    "fader_1": 14, "fader_2": 16, "fader_3": 18, "fader_4": 20,
}

X1_BUTTONS = {
    "deck_a_play": (0, 0), "deck_a_cue": (0, 1),
    "deck_a_beat_left": (0, 2), "deck_a_out": (0, 3),
    "deck_a_fx2": (1, 0), "deck_a_fx1": (1, 1),
    "deck_b_in": (1, 4), "deck_b_beat_right": (1, 5),
    "deck_b_cup": (1, 6), "deck_b_sync": (1, 7),
    "deck_b_play": (2, 0), "deck_b_cue": (2, 1),
    "deck_b_beat_left": (2, 2), "deck_b_out": (2, 3),
    "deck_a_in": (2, 4), "deck_a_beat_right": (2, 5),
    "deck_a_cup": (2, 6), "deck_a_sync": (2, 7),
    "deck_a_browse_button": (3, 0), "deck_b_browse_button": (3, 1),
    "deck_a_loop_button": (3, 2), "deck_b_loop_button": (3, 3),
    "fx1_on": (3, 4), "fx1_button_1": (3, 5),
    "fx1_button_2": (3, 6), "fx1_button_3": (3, 7),
    "fx2_on": (4, 0), "fx2_button_1": (4, 1),
    "fx2_button_2": (4, 2), "fx2_button_3": (4, 3),
    "shift": (4, 4), "deck_b_fx2": (4, 5),
    "deck_b_fx1": (4, 6), "hotcue": (4, 7),
}
X1_ENCODERS = {
    "deck_a_browse_encoder": (6, False),
    "deck_b_browse_encoder": (6, True),
    "deck_a_loop_encoder": (7, False),
    "deck_b_loop_encoder": (7, True),
}
X1_ANALOGS = {
    "fx1_dry_wet": (16, 17), "fx1_knob_1": (20, 21),
    "fx1_knob_2": (22, 23), "fx1_knob_3": (18, 19),
    "fx2_dry_wet": (12, 13), "fx2_knob_1": (10, 11),
    "fx2_knob_2": (8, 9), "fx2_knob_3": (14, 15),
}


def list_devices() -> list[str]:
    found: list[str] = []
    try:
        import hid
        for item in hid.enumerate(NI_VENDOR_ID, F1_PRODUCT_ID):
            found.append(f"F1 HID path={item.get('path')!r} serial={item.get('serial_number')!r}")
    except Exception as exc:
        found.append(f"F1 HID unavailable: {exc}")
    try:
        import usb.core
        devices = list(usb.core.find(find_all=True, idVendor=NI_VENDOR_ID, idProduct=X1_PRODUCT_ID) or [])
        for device in devices:
            found.append(f"X1 USB bus={getattr(device, 'bus', '?')} address={getattr(device, 'address', '?')}")
    except Exception as exc:
        found.append(f"X1 USB unavailable: {exc}")
    return found


def _normalize_f1_report(data: list[int] | bytes) -> bytes | None:
    report = bytes(data)
    if len(report) >= 22 and report[0] == 0x01:
        return report
    if len(report) >= 21:
        return b"\x01" + report
    return None


def run_f1(emit: Callable[[ControlEvent], None], stop: threading.Event) -> None:
    import hid
    devices = hid.enumerate(NI_VENDOR_ID, F1_PRODUCT_ID)
    if not devices:
        raise RuntimeError("F1 not found")
    device = hid.device()
    device.open_path(devices[0]["path"])
    device.set_nonblocking(False)
    previous_buttons: int | None = None
    previous_encoder: int | None = None
    previous_analog: dict[str, int] = {}
    try:
        while not stop.is_set():
            raw = device.read(64, 250)
            if not raw:
                continue
            report = _normalize_f1_report(raw)
            if report is None:
                continue
            buttons = int.from_bytes(report[1:5], "little")
            if previous_buttons is not None:
                changed = previous_buttons ^ buttons
                for control, mask in F1_BUTTON_MASKS.items():
                    if changed & mask:
                        pressed = bool(buttons & mask)
                        emit(ControlEvent("f1", control, "press" if pressed else "release", int(pressed)))
            previous_buttons = buttons
            encoder = report[5]
            if previous_encoder is not None:
                delta = ((encoder - previous_encoder + 128) % 256) - 128
                if delta:
                    emit(ControlEvent("f1", "select_encoder", "relative", delta, -128, 127))
            previous_encoder = encoder
            for control, offset in F1_ANALOG_OFFSETS.items():
                value = struct.unpack_from("<H", report, offset)[0]
                if previous_analog.get(control) not in (None, value):
                    emit(ControlEvent("f1", control, "absolute", value, 0, 4096))
                previous_analog[control] = value
    finally:
        device.close()


def run_x1(emit: Callable[[ControlEvent], None], stop: threading.Event) -> None:
    import usb.core
    import usb.util
    device = usb.core.find(idVendor=NI_VENDOR_ID, idProduct=X1_PRODUCT_ID)
    if device is None:
        raise RuntimeError("X1 not found or WinUSB driver not installed")
    device.set_configuration()
    previous_buttons: dict[str, bool] = {}
    previous_encoders: dict[str, int] = {}
    previous_analogs: dict[str, int] = {}
    try:
        while not stop.is_set():
            try:
                raw = bytes(device.read(0x84, 24, timeout=250))
            except Exception as exc:
                if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
                    continue
                raise
            if len(raw) != 24:
                continue
            for control, (byte_index, bit_index) in X1_BUTTONS.items():
                pressed = bool(raw[1 + byte_index] & (1 << bit_index))
                previous = previous_buttons.get(control)
                previous_buttons[control] = pressed
                if previous is not None and previous != pressed:
                    emit(ControlEvent("x1", control, "press" if pressed else "release", int(pressed)))
            for control, (index, high_nibble) in X1_ENCODERS.items():
                position = raw[index] >> 4 if high_nibble else raw[index] & 0x0F
                previous = previous_encoders.get(control)
                previous_encoders[control] = position
                if previous is not None:
                    delta = ((position - previous + 8) % 16) - 8
                    if delta:
                        emit(ControlEvent("x1", control, "relative", delta, -8, 7))
            for control, (high, low) in X1_ANALOGS.items():
                value = (raw[high] << 8) | raw[low]
                previous = previous_analogs.get(control)
                previous_analogs[control] = value
                if previous is not None and previous != value:
                    emit(ControlEvent("x1", control, "absolute", value, 0, 4095))
    finally:
        try:
            usb.util.dispose_resources(device)
        except Exception:
            pass


def run_runtime(emit: Callable[[ControlEvent], None]) -> None:
    stop = threading.Event()
    threads: list[threading.Thread] = []
    for name, target in (("F1", run_f1), ("X1", run_x1)):
        def runner(label: str = name, worker: Any = target) -> None:
            while not stop.is_set():
                try:
                    print(f"Connecting {label}...", flush=True)
                    worker(emit, stop)
                except Exception as exc:
                    print(f"{label}: {exc}", flush=True)
                    stop.wait(2.0)
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        threads.append(thread)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        for thread in threads:
            thread.join(timeout=2)
