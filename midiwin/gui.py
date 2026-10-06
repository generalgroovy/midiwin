from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from .common import APP_DIR, load_config, validate_config
from .gui_support import execute_command, mapping_rows, save_profile
from .mapping_inspector import MappingInspector

EVENT_RE = re.compile(r"device=(\w+) control=([^ ]+).*kind=([^ ]+).*value=(-?\d+)")


def _mapping_index(config: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for mapping in config.get("mappings", []):
        if isinstance(mapping, dict) and mapping.get("enabled", True):
            result.setdefault((str(mapping.get("device")), str(mapping.get("control"))), mapping)
    return result


class ControllerCanvas(tk.Canvas):
    def __init__(self, master: tk.Misc, config: dict[str, Any], **kwargs: Any):
        super().__init__(master, background="#15171a", highlightthickness=0, **kwargs)
        self.config_data = config
        self.items: dict[str, int] = {}
        self.normal_fill: dict[int, str] = {}
        self.bind("<Configure>", lambda _event: self.redraw())

    def _add_control(self, device: str, control: str, x1: float, y1: float,
                     x2: float, y2: float, label: str, oval: bool = False) -> None:
        mapping = self.mapping_lookup.get((device, control), {})
        action = str(mapping.get("action", "unmapped"))
        fill = "#292d33" if action != "unmapped" else "#202327"
        maker = self.create_oval if oval else self.create_rectangle
        item = maker(x1, y1, x2, y2, fill=fill, outline="#7b8794", width=1)
        self.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label,
                         fill="#f2f4f8", font=("Segoe UI", 8))
        self.create_text((x1 + x2) / 2, y2 + 10, text=action[:22],
                         fill="#9aa6b2", font=("Segoe UI", 7))
        self.items[f"{device}.{control}"] = item
        self.normal_fill[item] = fill

    def redraw(self) -> None:
        self.mapping_lookup = _mapping_index(self.config_data)
        self.delete("all")
        self.items.clear()
        self.normal_fill.clear()
        w = max(self.winfo_width(), 900)
        h = max(self.winfo_height(), 560)
        margin = 24
        gap = 28
        left_w = (w - margin * 2 - gap) * 0.55
        right_w = w - margin * 2 - gap - left_w
        self._draw_f1(margin, 18, left_w, h - 36)
        self._draw_x1(margin + left_w + gap, 18, right_w, h - 36)

    def _draw_f1(self, x: float, y: float, w: float, h: float) -> None:
        self.create_rectangle(x, y, x + w, y + h, fill="#0c0d0f",
                              outline="#8e99a5", width=2)
        self.create_text(x + w / 2, y + 18, text="TRAKTOR F1 — WINDOWS",
                         fill="#ffffff", font=("Segoe UI", 11, "bold"))
        knob_y = y + 58
        for i in range(4):
            cx = x + (i + 0.5) * w / 4
            self._add_control("f1", f"knob_{i+1}", cx - 18, knob_y - 18,
                              cx + 18, knob_y + 18, f"K{i+1}", oval=True)
        fader_top, fader_bottom = y + 115, y + 245
        for i in range(4):
            cx = x + (i + 0.5) * w / 4
            self._add_control("f1", f"fader_{i+1}", cx - 11, fader_top,
                              cx + 11, fader_bottom, f"F{i+1}")
        pad_top = y + 285
        pad_h = min(48, (h - 390) / 4)
        pad_w = (w - 50) / 4
        for row in range(4):
            for col in range(4):
                number = row * 4 + col + 1
                px = x + 16 + col * (pad_w + 6)
                py = pad_top + row * (pad_h + 8)
                self._add_control("f1", f"grid_{number}", px, py,
                                  px + pad_w, py + pad_h, str(number))
        transport_y = y + h - 64
        controls = ["play_1", "play_2", "play_3", "play_4", "reverse", "shift"]
        labels = ["PLAY", "PREV", "NEXT", "MUTE", "CLOSE", "SHIFT"]
        bw = (w - 28) / len(controls)
        for i, (control, label) in enumerate(zip(controls, labels)):
            bx = x + 8 + i * bw
            self._add_control("f1", control, bx, transport_y, bx + bw - 5,
                              transport_y + 34, label)

    def _draw_x1(self, x: float, y: float, w: float, h: float) -> None:
        self.create_rectangle(x, y, x + w, y + h, fill="#0c0d0f",
                              outline="#8e99a5", width=2)
        self.create_text(x + w / 2, y + 18, text="TRAKTOR X1 — WINDOWS",
                         fill="#ffffff", font=("Segoe UI", 11, "bold"))
        knob_controls = ["fx1_dry_wet", "fx1_knob_1", "fx1_knob_2", "fx1_knob_3",
                         "fx2_dry_wet", "fx2_knob_1", "fx2_knob_2", "fx2_knob_3"]
        for row in range(2):
            for col in range(4):
                i = row * 4 + col
                cx = x + (col + 0.5) * w / 4
                cy = y + 66 + row * 84
                self._add_control("x1", knob_controls[i], cx - 17, cy - 17,
                                  cx + 17, cy + 17, f"FX{i+1}", oval=True)
        button_controls = ["fx1_on", "fx1_button_1", "fx1_button_2", "fx1_button_3",
                           "fx2_on", "fx2_button_1", "fx2_button_2", "fx2_button_3"]
        for row in range(2):
            for col in range(4):
                i = row * 4 + col
                bx = x + 8 + col * (w - 16) / 4
                by = y + 190 + row * 48
                self._add_control("x1", button_controls[i], bx, by,
                                  bx + (w - 16) / 4 - 5, by + 28, f"B{i+1}")
        encoders = ["deck_a_browse_encoder", "deck_b_browse_encoder",
                    "deck_a_loop_encoder", "deck_b_loop_encoder"]
        for i, control in enumerate(encoders):
            cx = x + (i + 0.5) * w / 4
            cy = y + 320
            self._add_control("x1", control, cx - 20, cy - 20,
                              cx + 20, cy + 20, f"E{i+1}", oval=True)
        deck_controls = ["deck_a_play", "deck_a_cue", "deck_a_in", "deck_a_out",
                         "deck_b_play", "deck_b_cue", "deck_b_in", "deck_b_out"]
        for row in range(2):
            for col in range(4):
                i = row * 4 + col
                bx = x + 8 + col * (w - 16) / 4
                by = y + 380 + row * 58
                self._add_control("x1", deck_controls[i], bx, by,
                                  bx + (w - 16) / 4 - 5, by + 34,
                                  deck_controls[i].replace("deck_", "").upper())

    def flash(self, device: str, control: str) -> None:
        item = self.items.get(f"{device}.{control}")
        if not item:
            return
        self.itemconfigure(item, fill="#00a6ff", outline="#ffffff", width=2)
        self.after(300, lambda: self._restore(item))

    def _restore(self, item: int) -> None:
        if item in self.normal_fill:
            self.itemconfigure(item, fill=self.normal_fill[item],
                               outline="#7b8794", width=1)


class MidiWinGui:
    def __init__(self, root: tk.Tk, config_path: Path | None = None):
        self.root = root
        self.root.title("MIDIWIN Controller Console")
        self.root.geometry("1180x760")
        self.requested_config_path = config_path.resolve() if config_path is not None else None
        self.config_path = self.requested_config_path or APP_DIR / "config.json"
        self.config = load_config(self.requested_config_path)
        self.process: subprocess.Popen[str] | None = None
        self.resume_runtime = False
        self.output_queue: queue.Queue = queue.Queue()
        self.detection = "Devices not checked"
        self.command_serial = 0
        self.detection_serial = 0
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._drain_output)

    def _build(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="MIDIWIN", font=("Segoe UI", 16, "bold")).pack(side="left")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(toolbar, textvariable=self.status).pack(side="right")
        setup = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        setup.pack(fill="x")
        self.readiness = tk.StringVar()
        ttk.Label(setup, textvariable=self.readiness, wraplength=980).pack(anchor="w")
        steps = ttk.Frame(setup)
        steps.pack(anchor="w", pady=(5, 0))
        for label, action in [("1 · Check saved profile", lambda: self.run_once(["--validate-config"])), ("2 · Detect devices", lambda: self.run_once(["--list-devices"])), ("3 · Monitor input", lambda: self.start_process(["--monitor"]))]:
            ttk.Button(steps, text=label, command=action).pack(side="left", padx=(0, 6))
        self._refresh_readiness()
        book = ttk.Notebook(self.root)
        book.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        overview = ttk.Frame(book)
        settings = ttk.Frame(book, padding=12)
        mappings = ttk.Frame(book, padding=8)
        monitor = ttk.Frame(book, padding=8)
        book.add(overview, text="Controller layout")
        book.add(settings, text="Configuration")
        book.add(mappings, text="Mappings")
        book.add(monitor, text="Monitoring")
        self.canvas = ControllerCanvas(overview, self.config)
        self.canvas.pack(fill="both", expand=True)
        self._build_settings(settings)
        self._build_mappings(mappings)
        self._build_monitor(monitor)
        self.track_settings()

    def _build_settings(self, parent: ttk.Frame) -> None:
        display = self.config.setdefault("display_controls", {}).setdefault("brightness", {})
        self.brightness_display = tk.StringVar(value=str(display.get("display", "")))
        self.min_brightness = tk.IntVar(value=int(display.get("minimum_percent", 1)))
        ttk.Label(parent, text="Screen brightness", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(parent, text="Display index/name (blank = all)").grid(row=1, column=0, sticky="w")
        ttk.Entry(parent, textvariable=self.brightness_display, width=28).grid(row=1, column=1, sticky="w")
        ttk.Label(parent, text="Minimum %").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(parent, from_=0, to=100, textvariable=self.min_brightness,
                    width=8).grid(row=2, column=1, sticky="w")
        ttk.Button(parent, text="Save configuration", command=self.save_settings).grid(
            row=3, column=0, pady=14, sticky="w")
        ttk.Button(parent, text="Open config", command=self.open_config).grid(
            row=3, column=1, pady=14, sticky="w")
        ttk.Separator(parent, orient="horizontal").grid(row=4, column=0, columnspan=3,
                                                         sticky="ew", pady=12)
        ttk.Label(parent, text="Live display test", font=("Segoe UI", 12, "bold")).grid(
            row=5, column=0, columnspan=3, sticky="w")
        self.brightness_test = tk.IntVar(value=50)
        scale = ttk.Scale(parent, from_=1, to=100, variable=self.brightness_test,
                          command=lambda _v: self._schedule_brightness())
        scale.grid(row=6, column=0, columnspan=2, sticky="ew", pady=8)
        self.brightness_label = ttk.Label(parent, text="50%")
        self.brightness_label.grid(row=6, column=2, padx=8)
        ttk.Button(parent, text="Diagnose displays", command=self.diagnose_displays).grid(
            row=7, column=0, sticky="w")
        self.draft_status = tk.StringVar(value="No unsaved display changes")
        ttk.Label(parent, textvariable=self.draft_status).grid(row=8, column=0, columnspan=3, sticky="w", pady=8)
        parent.columnconfigure(1, weight=1)
        self._brightness_job: str | None = None

    def _schedule_brightness(self) -> None:
        value = int(float(self.brightness_test.get()))
        self.brightness_label.configure(text=f"{value}%")
        if self._brightness_job:
            self.root.after_cancel(self._brightness_job)
        self._brightness_job = self.root.after(180, lambda: self.run_once(["--set-brightness", str(value)]))

    def _build_mappings(self, parent: ttk.Frame) -> None:
        search = ttk.Frame(parent)
        search.pack(fill="x", pady=(0, 6))
        self.mapping_query = tk.StringVar()
        self.mapping_state = tk.StringVar(value="All")
        self.mapping_count = tk.StringVar()
        ttk.Label(search, text="Find mapping").pack(side="left")
        ttk.Entry(search, textvariable=self.mapping_query).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Combobox(search, textvariable=self.mapping_state, values=("All", "Enabled", "Disabled"), state="readonly", width=10).pack(side="left")
        ttk.Label(search, textvariable=self.mapping_count).pack(side="left", padx=6)
        columns = ("device", "control", "kind", "action", "layer", "state")
        table = ttk.Frame(parent)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="browse")
        widths = (70, 200, 80, 240, 180, 80)
        for name, width in zip(columns, widths):
            self.tree.heading(name, text=name.title())
            self.tree.column(name, width=width, anchor="w")
        self.mapping_scrollbars(table)
        self.tree.bind("<Double-1>", lambda _event: self.inspect_mapping())
        self.tree.bind("<Return>", lambda _event: self.inspect_mapping())
        self._fill_mappings()
        self.mapping_query.trace_add("write", lambda *_: self._fill_mappings())
        self.mapping_state.trace_add("write", lambda *_: self._fill_mappings())
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Inspect / try event", command=self.inspect_mapping).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Reload", command=self.reload).pack(side="left")
        ttk.Button(row, text="Show layout in console", command=lambda: self.run_once(["--show-layout"])).pack(side="left", padx=6)

    def _fill_mappings(self) -> None:
        selected = self.tree.selection()
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = mapping_rows(self.config, self.mapping_query.get(), self.mapping_state.get())
        for key, values in rows:
            self.tree.insert("", "end", iid=key, values=values)
        self.mapping_count.set(f"{len(rows)} shown")
        for key in selected:
            if self.tree.exists(key):
                self.tree.selection_add(key)

    def _refresh_readiness(self) -> None:
        if not hasattr(self, "readiness"):
            return
        enabled = sum(bool(m.get("enabled", True)) for m in self.config.get("mappings", []) if isinstance(m, dict))
        self.readiness.set(f"Loaded profile: {self.config_path} · {enabled} enabled mappings · {self.detection}")

    def _build_monitor(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="Detect devices", command=lambda: self.run_once(["--list-devices"])).pack(side="left")
        ttk.Button(row, text="Read-only monitor", command=lambda: self.start_process(["--monitor"])).pack(side="left", padx=6)
        ttk.Button(row, text="Dry-run mappings", command=lambda: self.start_process(["--dry-run"])).pack(side="left")
        ttk.Button(row, text="Start active runtime", command=lambda: self.start_process([])).pack(side="left", padx=6)
        ttk.Button(row, text="Stop", command=self.stop_process).pack(side="left")
        self.log = tk.Text(parent, wrap="none", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)

    def python_command(self) -> list[str]:
        command = [sys.executable, "-m", "midiwin"]
        if self.requested_config_path is not None:
            command += ["--config", str(self.requested_config_path)]
        return command

    def start_process(self, arguments: list[str]) -> None:
        restore_previous = self.resume_runtime
        self.stop_process(resume=False)
        self.resume_runtime = restore_previous
        command = self.python_command() + arguments
        self._append("$ " + subprocess.list2cmdline(command) + "\n")
        try:
            status = subprocess.run(self.python_command() + ["--runtime-status"], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, check=False, timeout=5).returncode == 0
            if status:
                subprocess.run(self.python_command() + ["--stop-runtime"], check=True, timeout=5,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.resume_runtime = (status or restore_previous) and bool(arguments)
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, bufsize=1)
        except (OSError, subprocess.SubprocessError) as error:
            self.status.set("Could not start; use Stop to restore runtime" if self.resume_runtime else "Could not start; see Monitoring")
            self._append(f"Could not start: {error}\n")
            return
        self.process = process
        threading.Thread(target=self._read_process, args=(process,), daemon=True).start()
        self.status.set("Running " + (" ".join(arguments) or "active runtime"))

    def run_once(self, arguments: list[str]) -> None:
        command = self.python_command() + arguments
        self.command_serial += 1
        token = self.command_serial
        if "--list-devices" in arguments:
            self.detection_serial = token
        self.status.set("Checking…")
        def worker() -> None:
            code, output = execute_command(command)
            self.output_queue.put(("command", token, arguments, code, "$ " + subprocess.list2cmdline(command) + "\n" + output))
        threading.Thread(target=worker, daemon=True).start()

    def _read_process(self, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout:
                for line in process.stdout:
                    self.output_queue.put(("line", process, line))
            code = process.wait()
        except (OSError, ValueError) as error:
            self.output_queue.put(("line", process, f"Read error: {error}\n"))
            code = -1
        self.output_queue.put(("stopped", process, code))

    def _handle_output(self, item: tuple) -> None:
        if item[0] == "command":
            _, token, arguments, code, text = item
            self._append(text)
            self._append(f"[exit {code if code is not None else 'unavailable'}]\n")
            if "--list-devices" in arguments and token == self.detection_serial:
                self.detection = "Devices detected" if code == 0 else "Device check failed; see Monitoring"
                self._refresh_readiness()
            if token == self.command_serial:
                self.status.set("Check completed" if code == 0 else "Check failed; see Monitoring")
            return
        _, process, value = item
        if process is not self.process:
            return
        if item[0] == "stopped":
            self.process = None
            self.status.set(f"Process stopped (exit {value})")
            self._append(f"[process stopped: exit {value}]\n")
            return
        self._append(value)
        match = EVENT_RE.search(value)
        if match:
            self.canvas.flash(match.group(1), match.group(2))

    def _drain_output(self) -> None:
        try:
            for _ in range(200):
                self._handle_output(self.output_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(80, self._drain_output)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        if int(self.log.index("end-1c").split(".")[0]) > 2000:
            self.log.delete("1.0", "end-2000l")
        self.log.see("end")
        self.log.configure(state="disabled")

    def stop_process(self, resume: bool = True) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if resume and self.resume_runtime:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                subprocess.Popen(self.python_command(), cwd=Path(__file__).resolve().parents[1],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, creationflags=creationflags)
            except OSError as error:
                self._append(f"Could not restore runtime: {error}\n")
                self.status.set("Could not restore runtime; retry Stop")
                return
        self.resume_runtime = False
        self.status.set("Stopped")

    def save_settings(self) -> bool:
        try:
            minimum = int(self.min_brightness.get())
            if not 0 <= minimum <= 100:
                raise ValueError("Minimum brightness must be between 0 and 100%.")
            raw = load_config(self.requested_config_path)
            controls = raw.setdefault("display_controls", {}).setdefault("brightness", {})
            value = self.brightness_display.get().strip()
            controls["display"] = int(value) if value.isdigit() else value
            controls["minimum_percent"] = minimum
            errors = validate_config(raw)
            if errors:
                raise ValueError("\n".join(errors))
            save_profile(self.config_path, raw)
            if self.reload(confirm=False):
                self.status.set("Configuration saved")
                return True
        except Exception as exc:
            messagebox.showerror("MIDIWIN", str(exc))
        return False

    def open_config(self) -> None:
        if not self.config_path.exists():
            messagebox.showinfo("MIDIWIN", "Save configuration first to create your profile.")
            return
        try:
            os.startfile(self.config_path)
        except OSError as error:
            messagebox.showerror("Could not open configuration", str(error))

    def diagnose_displays(self) -> None:
        self.run_once(["--diagnose-display"])

    def reload(self, confirm: bool = True) -> bool:
        if confirm and not self.confirm_settings("reloading"):
            return False
        try:
            candidate = load_config(self.requested_config_path)
            errors = validate_config(candidate)
            if errors:
                raise ValueError("\n".join(errors))
            display = candidate.get("display_controls", {}).get("brightness", {})
            minimum = int(display.get("minimum_percent", 1))
            if not 0 <= minimum <= 100:
                raise ValueError("Minimum brightness must be between 0 and 100%.")
        except (OSError, ValueError, TypeError, AttributeError) as error:
            messagebox.showerror("Invalid configuration", str(error))
            return False
        self.config = candidate
        selected_display = display.get("display", "")
        self.brightness_display.set("" if selected_display is None else str(selected_display))
        self.min_brightness.set(minimum)
        self.canvas.config_data = self.config
        self.canvas.redraw()
        self._fill_mappings()
        self._refresh_readiness()
        self.status.set("Configuration reloaded")
        self.remember_settings()
        return True

    def mapping_scrollbars(self, table: ttk.Frame) -> None:
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

    def inspect_mapping(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self.status.set("Select a mapping, then Inspect / try event")
            self.tree.focus_set()
            return
        previous = getattr(self, "inspector", None)
        if previous is not None and previous.winfo_exists():
            previous.destroy()
        self.inspector = MappingInspector(self.root, self.config, int(selected[0]))

    def settings_snapshot(self) -> tuple[str, ...]:
        values = []
        for name in ("brightness_display", "min_brightness"):
            try:
                values.append(str(getattr(self, name).get()))
            except (tk.TclError, ValueError):
                values.append("<invalid>")
        return tuple(values)

    def track_settings(self) -> None:
        self.remember_settings()
        for name in ("brightness_display", "min_brightness"):
            getattr(self, name).trace_add("write", lambda *_: self.update_draft_status())

    def remember_settings(self) -> None:
        self.settings_baseline = self.settings_snapshot()
        self.update_draft_status()

    def update_draft_status(self) -> None:
        if hasattr(self, "draft_status"):
            dirty = self.settings_snapshot() != self.settings_baseline
            self.draft_status.set("Unsaved display changes" if dirty else "No unsaved display changes")

    def confirm_settings(self, action: str) -> bool:
        if not hasattr(self, "settings_baseline") or self.settings_snapshot() == self.settings_baseline:
            return True
        choice = messagebox.askyesnocancel("Unsaved display changes", f"Save your display changes before {action}?\nYes: save. No: discard. Cancel: keep editing.", parent=self.root)
        if choice is None:
            return False
        return self.save_settings() if choice else True

    def close(self) -> None:
        if self.confirm_settings("closing"):
            self.stop_process()
            self.root.destroy()


def main(config_path: Path | None = None) -> int:
    try:
        config = load_config(config_path)
        errors = validate_config(config)
        if errors:
            raise ValueError("\n".join(errors))
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 1
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        pass
    MidiWinGui(root, config_path)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
