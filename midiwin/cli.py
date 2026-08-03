from __future__ import annotations

import argparse
from pathlib import Path

from .common import APP_DIR, load_config, validate_config
from .hardware import list_devices, run_runtime
from .router import EventRouter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="midiwin")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--validate-config", action="store_true")
    parser.add_argument("--show-layout", action="store_true")
    parser.add_argument("--monitor", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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

    read_only = args.monitor or args.dry_run
    router = EventRouter(config, dry_run=read_only, monitor=read_only)
    mode = "monitor" if args.monitor else "dry-run" if args.dry_run else "active"
    print(f"MIDIWIN running in {mode} mode. Config: {args.config or APP_DIR / 'config.json'}")
    print("Press Ctrl+C to stop.")
    run_runtime(router.emit)
    return 0
