from __future__ import annotations

import argparse
import atexit
import os
from pathlib import Path

from .actions import ActionDispatcher
from .common import APP_DIR, load_config, validate_config
from .hardware import list_devices, run_runtime
from .router import EventRouter

PID_FILE = APP_DIR / "runtime.pid"


def _read_runtime_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="ascii").strip())
    except (FileNotFoundError, ValueError):
        return None


def _runtime_process():
    pid = _read_runtime_pid()
    if not pid:
        return None
    try:
        import psutil
        process = psutil.Process(pid)
        if process.is_running() and "python" in process.name().lower():
            return process
    except Exception:
        pass
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass
    return None


def stop_runtime() -> bool:
    process = _runtime_process()
    if process is None:
        print("MIDIWIN runtime is not running.")
        return False
    process.terminate()
    try:
        process.wait(timeout=4)
    except Exception:
        process.kill()
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass
    print(f"Stopped MIDIWIN runtime PID {process.pid}.")
    return True


def claim_runtime() -> None:
    process = _runtime_process()
    if process is not None and process.pid != os.getpid():
        raise SystemExit(
            f"MIDIWIN is already running as PID {process.pid}. "
            "Use `python -m midiwin --stop-runtime` first."
        )
    APP_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="ascii")

    def release() -> None:
        try:
            if _read_runtime_pid() == os.getpid():
                PID_FILE.unlink()
        except FileNotFoundError:
            pass
    atexit.register(release)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="midiwin")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--show-layout", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--set-brightness", type=int, metavar="PERCENT")
    parser.add_argument("--diagnose-display", action="store_true")
    parser.add_argument("--runtime-status", action="store_true")
    parser.add_argument("--stop-runtime", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.gui:
        from .gui import main as gui_main
        return gui_main()
    if args.stop_runtime:
        return 0 if stop_runtime() else 1
    if args.runtime_status:
        process = _runtime_process()
        if process is None:
            print("MIDIWIN runtime: stopped")
            return 1
        print(f"MIDIWIN runtime: running PID {process.pid}")
        return 0

    config = load_config(args.config)
    if args.list_devices:
        devices = list_devices()
        for item in devices:
            print(item)
        return 0 if any(item.startswith(("F1 ", "X1 ")) for item in devices) else 1
    if args.validate_config:
        errors = validate_config(config)
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print(f"Configuration valid: {len(config.get('mappings', []))} mappings")
        return 0
    if args.show_layout:
        for mapping in config.get("mappings", []):
            if mapping.get("enabled", True):
                requirements = "+".join(mapping.get("requires", []))
                layer = f" [{requirements}]" if requirements else ""
                detail = mapping.get("slot") or mapping.get("parameter") or ""
                print(
                    f"{mapping['device']:>3} {mapping['control']:<28} "
                    f"{mapping['kind']:<8} -> {mapping['action']} {detail}{layer}"
                )
        return 0

    errors = validate_config(config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    dispatcher = ActionDispatcher(config)
    if args.set_brightness is not None:
        return 0 if dispatcher.set_brightness_percent(args.set_brightness) else 1
    if args.diagnose_display:
        for line in dispatcher.diagnose_displays():
            print(line)
        return 0

    claim_runtime()
    read_only = args.monitor or args.dry_run
    router = EventRouter(config, dry_run=read_only, monitor=read_only)
    mode = "monitor" if args.monitor else "dry-run" if args.dry_run else "active"
    print(f"MIDIWIN running in {mode} mode. Config: {args.config or APP_DIR / 'config.json'}")
    print("Press Ctrl+C to stop.")
    run_runtime(router.emit)
    return 0
