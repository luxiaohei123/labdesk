#!/usr/bin/env python3
"""
LabDesk — Oscilloscope SVG Waveform Capture
============================================

A dark-themed desktop oscilloscope interface for waveform acquisition,
real-time preview, and SVG vector export. Connects to real instruments
via VISA or runs stand-alone with a simulated backend.

Built with Tkinter + Matplotlib. No web stack, no Electron — just a native
Python desktop app that packages into a single Windows executable via PyInstaller.

Includes a simulated backend plus an experimental generic SCPI/pyvisa backend.

Author: Open-source project — see LICENSE
"""

import configparser
import csv
import math
import os
import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from core.engine import SimulatedEngine, VisaScpiEngine, BaseEngine
from core.acquisition import LiveAcquisition, AcquisitionFrame

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
APP_INI = APP_DIR / "labdesk.ini"
ASSETS_DIR = APP_DIR / "assets"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BG = "#07192D"
PANEL = "#0B223B"
FG = "#D9ECFF"
ACCENT = "#00E6FF"
MUTED = "#89A8C5"
DARK_BG = "#061423"
CARD_BG = "#0E2A45"

BW_OPTIONS = ["FULL", "200MHz", "100MHz", "20MHz"]
COUPLING_OPTIONS = ["DC", "AC", "GND"]
TRIG_TYPE_OPTIONS = ["EDGE", "PULSE", "VIDEO", "SLOPE", "RUNT", "WINDOW"]
TRIG_SLOPE_OPTIONS = ["RISE", "FALL", "EITHER"]
TRIG_MODE_OPTIONS = ["AUTO", "NORM", "SINGLE"]
METRIC_OPTIONS = [
    "Vpp", "Vmax", "Vmin", "Vavg", "Vrms",
    "Freq", "Period", "RiseTime", "FallTime",
    "PosWidth", "NegWidth", "DutyCycle",
    "Overshoot", "Undershoot", "PulseCount",
]
DEFAULT_METRICS = ["Vpp", "Vmax", "Vmin", "Freq", "Period", "RiseTime", "DutyCycle"]
LOGO_PATH = ASSETS_DIR / "logo.jpg"


# ===================================================================
# Main Application
# ===================================================================

class LabDeskApp(tk.Tk):
    """Main application window — dark-themed engineering workbench."""

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__()

        # ---- window ----
        self.title("LabDesk — Oscilloscope SVG Capture")
        self.geometry("1680x980")
        self.minsize(1400, 860)
        self.configure(bg=BG)

        # ---- threading ----
        self._ui_queue = queue.Queue()
        self._export_running = False
        self._task_running = False

        # ---- backend ----
        self.engine: BaseEngine = SimulatedEngine()

        # ---- acquisition ----
        self._frame_queue = queue.Queue()
        self._acquisition = LiveAcquisition(self.engine, self._frame_queue, fps=10)
        self._last_frame: dict[int, AcquisitionFrame] = {}

        # ---- variables ----
        self._init_variables()

        # ---- build ----
        self._configure_style()
        self.logo_image = self._load_logo_image()
        self._build_ui()
        self._build_help_map()
        self._build_help_sections()

        # ---- config ----
        self._load_ini()
        self._ensure_engine_for_interface(log_change=False)
        self._init_autosave_watchers()

        # ---- start loops ----
        self.after(80, self._drain_ui_queue)
        self.after(120, self._drain_frame_queue)
        self._log("LabDesk started — ready.")

        # Maximise on start
        try:
            self.state("zoomed")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _init_variables(self):
        # Connection
        self.resource_var = tk.StringVar()
        self.idn_var = tk.StringVar(value="Disconnected")

        # Channel globals
        self.time_div_var = tk.StringVar(value="10ms")
        self.time_offset_var = tk.StringVar(value="30ms")

        # Channel 1-4
        self.ch_ids = ["1", "2", "3", "4"]
        self.ch_name_vars: dict[str, tk.StringVar] = {}
        self.ch_enable_vars: dict[str, tk.BooleanVar] = {}
        self.ch_visible_vars: dict[str, tk.BooleanVar] = {}
        self.ch_bw_vars: dict[str, tk.StringVar] = {}
        self.ch_coupling_vars: dict[str, tk.StringVar] = {}
        self.ch_vdiv_vars: dict[str, tk.StringVar] = {}
        self.ch_offset_vars: dict[str, tk.StringVar] = {}
        self.ch_probe_vars: dict[str, tk.StringVar] = {}

        defaults = {
            "1": ("CH1", True, True, "FULL", "DC", "2V", "0V", "X10"),
            "2": ("CH2", True, True, "FULL", "DC", "1V", "0V", "X10"),
            "3": ("CH3", False, False, "FULL", "DC", "5V", "-2V", "X1"),
            "4": ("CH4", False, False, "FULL", "DC", "5V", "-6V", "X1"),
        }
        for ch in self.ch_ids:
            n, e, v, bw, cp, vd, off, pr = defaults[ch]
            self.ch_name_vars[ch] = tk.StringVar(value=n)
            self.ch_enable_vars[ch] = tk.BooleanVar(value=e)
            self.ch_visible_vars[ch] = tk.BooleanVar(value=v)
            self.ch_bw_vars[ch] = tk.StringVar(value=bw)
            self.ch_coupling_vars[ch] = tk.StringVar(value=cp)
            self.ch_vdiv_vars[ch] = tk.StringVar(value=vd)
            self.ch_offset_vars[ch] = tk.StringVar(value=off)
            self.ch_probe_vars[ch] = tk.StringVar(value=pr)

        # Trigger
        self.trig_type_var = tk.StringVar(value="EDGE")
        self.trig_source_var = tk.StringVar(value="CH1")
        self.trig_slope_var = tk.StringVar(value="RISE")
        self.trig_level_var = tk.StringVar(value="0V")
        self.trig_mode_var = tk.StringVar(value="AUTO")
        self.trig_coupling_var = tk.StringVar(value="DC")
        self.trig_noise_var = tk.StringVar(value="OFF")
        self.trig_holdoff_var = tk.StringVar(value="100ns")

        # Metrics
        self.metrics_switch_var = tk.BooleanVar(value=False)
        self.metrics_source_var = tk.StringVar(value="CH1")
        self.metrics_selected: list[str] = list(DEFAULT_METRICS)

        # Export
        self.output_dir_var = tk.StringVar(value=str(APP_DIR / "output"))
        self.screenshot_name_var = tk.StringVar(value="screenshot")
        self.screenshot_fmt_var = tk.StringVar(value="PNG")
        self.export_channels: list[str] = ["1"]
        self.export_plot_var = tk.BooleanVar(value=True)

        # Plot tuning
        self.plot_title_var = tk.StringVar(value="Waveform")
        self.plot_xlabel_var = tk.StringVar(value="Time")
        self.plot_ylabel_var = tk.StringVar(value="Voltage (V)")
        self.plot_linewidth_var = tk.DoubleVar(value=1.2)
        self.plot_scope_grid_var = tk.BooleanVar(value=True)
        self.plot_filter_var = tk.StringVar(value="OFF")
        self.plot_filter_win_var = tk.IntVar(value=9)
        self.plot_show_legend_var = tk.BooleanVar(value=True)
        self.plot_show_title_var = tk.BooleanVar(value=True)
        self.plot_show_tags_var = tk.BooleanVar(value=True)

        # Interface
        self.interface_var = tk.StringVar(value="Simulated")

        # SVG export options
        self.svg_scope_grid_var = tk.BooleanVar(value=True)
        self.svg_dark_bg_var = tk.BooleanVar(value=False)

        # Status
        self.status_var = tk.StringVar(value="Idle")

    # ------------------------------------------------------------------
    # Style  (matching the documented dark theme exactly)
    # ------------------------------------------------------------------

    def _configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabelframe", background=PANEL, foreground=ACCENT, borderwidth=1)
        style.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT,
                        font=("Consolas", 11, "bold"))
        style.configure("TLabel", background=PANEL, foreground=FG,
                        font=("Consolas", 10))
        style.configure("Header.TLabel", background=BG, foreground=ACCENT,
                        font=("Consolas", 18, "bold"))
        style.configure("SubHeader.TLabel", background=PANEL, foreground=MUTED,
                        font=("Consolas", 10))
        style.configure("TButton", background="#153554", foreground=FG,
                        padding=(8, 5), font=("Consolas", 10), borderwidth=0)
        style.map("TButton", background=[("active", "#1A4A6E"), ("disabled", "#0D1E30")],
                  foreground=[("disabled", "#556677")])
        style.configure("Accent.TButton", background="#087A8A", foreground="#E9FEFF",
                        font=("Consolas", 10, "bold"), padding=(8, 5))
        style.map("Accent.TButton", background=[("active", "#0A9AAA"), ("disabled", "#043A40")])
        style.configure("TEntry", fieldbackground="#0A1D33", foreground=FG,
                        insertcolor=FG, font=("Consolas", 10))
        style.configure("TCombobox", fieldbackground="#0A1D33", foreground=FG,
                        font=("Consolas", 10), arrowsize=16)
        style.map("TCombobox", fieldbackground=[("readonly", "#0A1D33")],
                  foreground=[("readonly", FG)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#12314F", foreground=FG,
                        padding=(12, 6), font=("Consolas", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", "#087A8A")],
                  foreground=[("selected", "#E9FEFF")])
        style.configure("Help.TButton", background=PANEL, foreground=ACCENT,
                        font=("Consolas", 10, "bold"), padding=(4, 1))
        style.configure("Export.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor="#0A1D33", borderwidth=0)
        style.configure("Help.Treeview", background="#0A1D33", foreground=FG,
                        fieldbackground="#0A1D33", font=("Consolas", 10))
        style.configure("TCheckbutton", background=PANEL, foreground=FG,
                        font=("Consolas", 10))
        style.map("TCheckbutton", background=[("active", PANEL)])

        # TCombobox dropdown styling
        self.option_add("*TCombobox*Listbox.background", "#0A1D33")
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.font", ("Consolas", 10))

    # ------------------------------------------------------------------
    # UI skeleton
    # ------------------------------------------------------------------

    def _load_logo_image(self):
        if not LOGO_PATH.exists():
            return None
        image = Image.open(LOGO_PATH)
        image.thumbnail((56, 56))
        return ImageTk.PhotoImage(image)

    def _build_ui(self):
        top = ttk.Frame(self, style="TFrame")
        top.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        # -- left --
        left = ttk.Frame(top, style="TFrame", width=520)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        # Logo row
        logo_row = ttk.Frame(left, style="TFrame")
        logo_row.pack(fill=tk.X, pady=(0, 6))
        if self.logo_image:
            tk.Label(logo_row, image=self.logo_image, bg=BG).pack(side=tk.LEFT)
            ttk.Label(logo_row, text="  LABDESK", style="Header.TLabel").pack(side=tk.LEFT)
        else:
            ttk.Label(logo_row, text="LABDESK", style="Header.TLabel").pack(side=tk.LEFT)
        ttk.Label(logo_row, text="Waveform to Vector",
                  style="SubHeader.TLabel", background=BG).pack(side=tk.LEFT, padx=(8, 0))

        # Notebook
        self.notebook = ttk.Notebook(left)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs
        self.tab_conn = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_params = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_control = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_metrics = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_export = ttk.Frame(self.notebook, style="Card.TFrame")
        self.tab_console = ttk.Frame(self.notebook, style="Card.TFrame")

        self.notebook.add(self.tab_conn, text="Connection")
        self.notebook.add(self.tab_params, text="Channels")
        self.notebook.add(self.tab_control, text="Trigger")
        self.notebook.add(self.tab_metrics, text="Measurements")
        self.notebook.add(self.tab_export, text="Export")
        self.notebook.add(self.tab_console, text="Console")

        self._build_conn_tab()
        self._build_params_tab()
        self._build_control_tab()
        self._build_metrics_tab()
        self._build_export_tab()
        self._build_console_tab()

        # -- right --
        right = ttk.Frame(top, style="TFrame")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        self._build_right_panel(right)

        # -- bottom bar --
        bar = ttk.Frame(self, style="TFrame")
        bar.pack(fill=tk.X, padx=10, pady=(0, 4))
        ttk.Label(bar, text="Status:", font=("Consolas", 10),
                  background=BG, foreground=MUTED).pack(side=tk.LEFT)
        ttk.Label(bar, textvariable=self.status_var, font=("Consolas", 10),
                  background=BG, foreground=ACCENT).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(bar, text="Help Center", style="Help.TButton",
                   command=self._open_help_center).pack(side=tk.RIGHT)

    # ==================================================================
    # TAB 1 — Connection
    # ==================================================================

    def _build_conn_tab(self):
        frm = ttk.LabelFrame(self.tab_conn, text="Device Connection")
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        r, c = 0, 0

        # Interface selector
        ttk.Label(frm, text="Interface:").grid(row=r, column=c, sticky="w", padx=8, pady=6)
        ttk.Combobox(frm, textvariable=self.interface_var,
                     values=["Simulated", "VISA (pyvisa)"], width=20,
                     state="readonly").grid(row=r, column=c + 1, padx=4, pady=6, sticky="w")
        self._add_help_button(frm, r, c + 2, "conn_interface")

        r += 1
        ttk.Label(frm, text="VISA Resource:").grid(row=r, column=c, sticky="w", padx=8, pady=6)
        ttk.Combobox(frm, textvariable=self.resource_var, width=34).grid(
            row=r, column=c + 1, padx=4, pady=6)
        self._add_help_button(frm, r, c + 2, "conn_resource")

        r += 1
        btn_row = ttk.Frame(frm, style="TFrame")
        btn_row.grid(row=r, column=0, columnspan=3, pady=8, padx=8, sticky="w")
        ttk.Button(btn_row, text="Discover", command=lambda: self._safe_action(self._discover)).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Connect", style="Accent.TButton",
                   command=lambda: self._safe_action(self._connect)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Disconnect",
                   command=lambda: self._safe_action(self._disconnect)).pack(side=tk.LEFT)

        r += 1
        ttk.Label(frm, text="Device ID:", font=("Consolas", 10, "bold")).grid(
            row=r, column=0, sticky="w", padx=8, pady=(10, 2))
        idn_entry = ttk.Entry(frm, textvariable=self.idn_var, state="readonly", width=44)
        idn_entry.grid(row=r + 1, column=0, columnspan=3, padx=8, pady=(0, 10), sticky="we")
        idn_entry.configure(foreground=ACCENT)

    # ==================================================================
    # TAB 2 — Parameters (Channel-style multiparameter cards)
    # ==================================================================

    def _build_params_tab(self):
        # Global settings
        glob = ttk.LabelFrame(self.tab_params, text="Global Settings")
        glob.pack(fill=tk.X, padx=8, pady=8)

        row = ttk.Frame(glob, style="TFrame")
        row.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row, text="Time/Div:").pack(side=tk.LEFT)
        cb = ttk.Combobox(row, textvariable=self.time_div_var, width=10,
                          values=["1ns", "10ns", "100ns", "1us", "10us", "100us",
                                  "1ms", "10ms", "100ms", "1s", "10s"])
        cb.pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Apply", command=lambda: self._safe_action(self._set_time_div)).pack(
            side=tk.LEFT)
        self._add_help_button(row, -1, 0, "params_time_div", pack=True)

        ttk.Label(row, text="  Offset:").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Combobox(row, textvariable=self.time_offset_var, width=10,
                     values=["0ms", "10ms", "20ms", "30ms", "50ms", "100ms"]).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(row, text="Apply",
                   command=lambda: self._safe_action(self._set_time_offset)).pack(side=tk.LEFT)
        self._add_help_button(row, -1, 0, "params_offset", pack=True)

        # Per-channel cards
        ch_row = ttk.Frame(self.tab_params, style="TFrame")
        ch_row.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for idx, ch in enumerate(self.ch_ids):
            self._build_channel_card(ch_row, ch, idx)

    def _build_channel_card(self, parent, ch, col):
        frm = ttk.LabelFrame(parent, text=f"Channel {ch}")
        frm.grid(row=0, column=col, padx=4, pady=4, sticky="ns")

        items = [
            ("Name:",        self.ch_name_vars[ch],    "entry",  None, "params_name"),
            ("Switch:",      self.ch_enable_vars[ch],  "check", None, "params_switch"),
            ("Visible:",     self.ch_visible_vars[ch], "check", None, "params_visible"),
            ("Bandwidth:",   self.ch_bw_vars[ch],      "combo", BW_OPTIONS, "params_bw"),
            ("Coupling:",    self.ch_coupling_vars[ch],"combo", COUPLING_OPTIONS, "params_coupling"),
            ("Volt/Div:",    self.ch_vdiv_vars[ch],    "combo",
             ["500uV", "1mV", "10mV", "100mV", "1V", "2V", "5V", "10V"], "params_vdiv"),
            ("Vert Offset:", self.ch_offset_vars[ch],  "combo",
             ["-10V", "-8V", "-6V", "-4V", "-2V", "0V", "2V", "4V", "6V", "8V", "10V"], "params_offset"),
            ("Probe:",       self.ch_probe_vars[ch],   "combo",
             ["X1", "X10", "X100"], "params_probe"),
        ]

        for i, (label, var, kind, opts, help_key) in enumerate(items):
            ttk.Label(frm, text=label, font=("Consolas", 9)).grid(
                row=i, column=0, sticky="w", padx=6, pady=3)
            if kind == "entry":
                ttk.Entry(frm, textvariable=var, width=12).grid(
                    row=i, column=1, padx=4, pady=3)
            elif kind == "check":
                ttk.Checkbutton(frm, variable=var).grid(
                    row=i, column=1, padx=4, pady=3, sticky="w")
            elif kind == "combo":
                ttk.Combobox(frm, textvariable=var, values=opts or [], width=10).grid(
                    row=i, column=1, padx=4, pady=3)

            if help_key:
                self._add_help_button(frm, i, 2, help_key)

        ttk.Button(frm, text="Apply All",
                   command=lambda c=ch: self._safe_action(lambda: self._apply_channel(c)),
                   style="Accent.TButton").grid(row=len(items), column=0, columnspan=3,
                                                pady=(8, 4), padx=6)

        row_bottom = ttk.Frame(self.tab_params, style="TFrame")
        row_bottom.pack(fill=tk.X, padx=8, pady=(4, 8))
        ttk.Button(row_bottom, text="Set Probe X10 All Channels",
                   command=lambda: self._safe_action(self._set_probe_all)).pack(side=tk.LEFT)

    # ==================================================================
    # TAB 3 — Control (Trigger-style)
    # ==================================================================

    def _build_control_tab(self):
        # Trigger config
        cfg = ttk.LabelFrame(self.tab_control, text="Task Control Configuration")
        cfg.pack(fill=tk.X, padx=8, pady=8)

        fields = [
            ("Type:",       self.trig_type_var,      TRIG_TYPE_OPTIONS,   "ctrl_type"),
            ("Source:",     self.trig_source_var,    self.ch_ids,         "ctrl_source"),
            ("Slope:",      self.trig_slope_var,     TRIG_SLOPE_OPTIONS,  "ctrl_slope"),
            ("Level:",      self.trig_level_var,     None,                "ctrl_level"),
            ("Mode:",       self.trig_mode_var,      TRIG_MODE_OPTIONS,   "ctrl_mode"),
            ("Coupling:",   self.trig_coupling_var,  COUPLING_OPTIONS,    "ctrl_coupling"),
            ("Noise Rej:",  self.trig_noise_var,     ["OFF", "ON"],       "ctrl_noise"),
            ("Holdoff:",    self.trig_holdoff_var,   None,                "ctrl_holdoff"),
        ]

        for i, (label, var, opts, help_key) in enumerate(fields):
            r, c = divmod(i, 2)
            ttk.Label(cfg, text=label).grid(row=r, column=c * 3, sticky="w", padx=8, pady=4)
            if opts:
                ttk.Combobox(cfg, textvariable=var, values=opts, width=12).grid(
                    row=r, column=c * 3 + 1, padx=4, pady=4)
            else:
                ttk.Entry(cfg, textvariable=var, width=14).grid(
                    row=r, column=c * 3 + 1, padx=4, pady=4)
            if help_key:
                self._add_help_button(cfg, r, c * 3 + 2, help_key)

        ttk.Button(cfg, text="Apply All", style="Accent.TButton",
                   command=lambda: self._safe_action(self._apply_control)).grid(
            row=4, column=0, columnspan=6, pady=(12, 6))

        # Acquisition control buttons
        acq_frame = ttk.LabelFrame(self.tab_control, text="Acquisition Control")
        acq_frame.pack(fill=tk.X, padx=8, pady=8)

        btn_frame = ttk.Frame(acq_frame, style="TFrame")
        btn_frame.pack(padx=8, pady=8)

        self.btn_run = ttk.Button(btn_frame, text="▶  Run",
                                  style="Accent.TButton",
                                  command=lambda: self._safe_action(self._acq_run))
        self.btn_run.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_stop = ttk.Button(btn_frame, text="■  Stop",
                                   command=lambda: self._safe_action(self._acq_stop))
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_single = ttk.Button(btn_frame, text="⏸  Single",
                                     command=lambda: self._safe_action(self._acq_single))
        self.btn_single.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(btn_frame, text="Query Status",
                   command=lambda: self._safe_action(self._query_status)).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Reset",
                   command=lambda: self._safe_action(self._reset_control)).pack(side=tk.LEFT)

        # FPS label
        self.acq_fps_label = ttk.Label(acq_frame, text="Acquisition: STOP",
                                       font=("Consolas", 9), background=PANEL,
                                       foreground=MUTED)
        self.acq_fps_label.pack(padx=8, pady=(0, 8))

        # Status readout
        out = ttk.LabelFrame(self.tab_control, text="Task Output")
        out.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ctrl_output = tk.Text(out, height=8, bg=DARK_BG, fg=ACCENT,
                                   insertbackground=ACCENT, relief="flat",
                                   font=("Consolas", 10))
        self.ctrl_output.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # ==================================================================
    # TAB 4 — Metrics
    # ==================================================================

    def _build_metrics_tab(self):
        top_frame = ttk.LabelFrame(self.tab_metrics, text="Measurement Control")
        top_frame.pack(fill=tk.X, padx=8, pady=8)

        r = 0
        ttk.Label(top_frame, text="Switch:").grid(row=r, column=0, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(top_frame, variable=self.metrics_switch_var).grid(
            row=r, column=1, sticky="w", padx=4)

        ttk.Label(top_frame, text="Source:").grid(row=r, column=2, sticky="w", padx=(20, 4))
        ttk.Combobox(top_frame, textvariable=self.metrics_source_var,
                     values=self.ch_ids, width=6).grid(row=r, column=3, padx=4)
        self._add_help_button(top_frame, r, 4, "metrics_source")

        # Metric item selection
        sel = ttk.LabelFrame(self.tab_metrics, text="Measurement Items")
        sel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        list_frame = ttk.Frame(sel, style="TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.metrics_listbox = tk.Listbox(
            list_frame, selectmode="multiple", exportselection=False,
            bg="#0A1D33", fg=FG, font=("Consolas", 10), relief="flat",
            yscrollcommand=scrollbar.set, highlightthickness=0,
            selectbackground="#087A8A", selectforeground="#E9FEFF")
        self.metrics_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.metrics_listbox.yview)

        for item in METRIC_OPTIONS:
            self.metrics_listbox.insert(tk.END, item)

        # Pre-select defaults
        for i, item in enumerate(METRIC_OPTIONS):
            if item in self.metrics_selected:
                self.metrics_listbox.selection_set(i)

        # Buttons
        btn_row = ttk.Frame(sel, style="TFrame")
        btn_row.pack(fill=tk.X, padx=8, pady=(4, 8))
        ttk.Button(btn_row, text="Select Common",
                   command=lambda: self._safe_action(self._select_common_metrics)).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Select All",
                   command=lambda: self._safe_action(self._select_all_metrics)).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Clear",
                   command=lambda: self._safe_action(self._clear_metrics)).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Read Metrics", style="Accent.TButton",
                   command=lambda: self._safe_action(self._read_metrics)).pack(
            side=tk.LEFT, padx=(20, 6))
        ttk.Button(btn_row, text="Read Frequency",
                   command=lambda: self._safe_action(self._read_frequency)).pack(side=tk.LEFT)

        # Results
        res = ttk.LabelFrame(self.tab_metrics, text="Results")
        res.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.metrics_output = tk.Text(res, height=6, bg=DARK_BG, fg=ACCENT,
                                      insertbackground=ACCENT, relief="flat",
                                      font=("Consolas", 11))
        self.metrics_output.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # ==================================================================
    # TAB 5 — Export
    # ==================================================================

    def _build_export_tab(self):
        # SVG Export
        svg_frame = ttk.LabelFrame(self.tab_export, text="SVG Vector Export")
        svg_frame.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(svg_frame, text="Output Dir:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(svg_frame, textvariable=self.output_dir_var, width=30).grid(
            row=0, column=1, padx=4)
        ttk.Button(svg_frame, text="Browse...",
                   command=lambda: self._safe_action(self._browse_output_dir)).grid(
            row=0, column=2, padx=4)

        ttk.Label(svg_frame, text="Name:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(svg_frame, textvariable=self.screenshot_name_var, width=28).grid(
            row=1, column=1, padx=4)
        ttk.Label(svg_frame, text="Channels:").grid(row=1, column=2, sticky="w", padx=8, pady=4)
        self.export_svg_ch_vars: dict[str, tk.BooleanVar] = {}
        svg_ch_row = ttk.Frame(svg_frame, style="TFrame")
        svg_ch_row.grid(row=1, column=3, sticky="w")
        for ch in self.ch_ids:
            self.export_svg_ch_vars[ch] = tk.BooleanVar(value=(ch in self.export_channels))
            ttk.Checkbutton(svg_ch_row, text=f"CH{ch}",
                            variable=self.export_svg_ch_vars[ch]).pack(side=tk.LEFT, padx=3)

        ttk.Label(svg_frame, text="Options:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        opt_row = ttk.Frame(svg_frame, style="TFrame")
        opt_row.grid(row=2, column=1, columnspan=3, sticky="w")
        ttk.Checkbutton(opt_row, text="Scope grid", variable=self.svg_scope_grid_var).pack(
            side=tk.LEFT, padx=4)
        ttk.Checkbutton(opt_row, text="Dark background", variable=self.svg_dark_bg_var).pack(
            side=tk.LEFT, padx=4)

        ttk.Button(svg_frame, text="Export SVG", style="Accent.TButton",
                   command=lambda: self._safe_action(self._export_svg)).grid(
            row=3, column=0, columnspan=4, pady=(8, 8))

        # Screenshot (classic PNG/BMP)
        ss = ttk.LabelFrame(self.tab_export, text="Screenshot")
        ss.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(ss, text="Name:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(ss, textvariable=self.screenshot_name_var, width=28).grid(row=0, column=1, padx=4)
        ttk.Label(ss, text="Format:").grid(row=0, column=2, sticky="w", padx=8, pady=4)
        ttk.Combobox(ss, textvariable=self.screenshot_fmt_var,
                     values=["PNG", "BMP"], width=8).grid(row=0, column=3, padx=4)

        ttk.Button(ss, text="Save Screenshot", style="Accent.TButton",
                   command=lambda: self._safe_action(self._save_screenshot)).grid(
            row=1, column=0, columnspan=4, pady=(8, 8))

        # Waveform / CSV Export
        wave = ttk.LabelFrame(self.tab_export, text="CSV Data Export")
        wave.pack(fill=tk.X, padx=8, pady=8)

        ttk.Label(wave, text="Export Channels:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ch_frame = ttk.Frame(wave, style="TFrame")
        ch_frame.grid(row=0, column=1, columnspan=3, sticky="w")

        self.export_ch_vars: dict[str, tk.BooleanVar] = {}
        for ch in self.ch_ids:
            self.export_ch_vars[ch] = tk.BooleanVar(value=(ch in self.export_channels))
            ttk.Checkbutton(ch_frame, text=f"CH{ch}",
                            variable=self.export_ch_vars[ch]).pack(side=tk.LEFT, padx=4)

        ttk.Checkbutton(wave, text="Auto-plot after export",
                        variable=self.export_plot_var).grid(
            row=1, column=1, columnspan=3, sticky="w", padx=8, pady=4)

        ttk.Button(wave, text="Export Data (CSV)", style="Accent.TButton",
                   command=lambda: self._safe_action(self._export_data)).grid(
            row=2, column=1, columnspan=2, pady=(8, 6), sticky="w")

        self.export_progress = ttk.Progressbar(wave,
                                               style="Export.Horizontal.TProgressbar",
                                               length=100, mode="determinate")
        self.export_progress.grid(row=3, column=0, columnspan=4, padx=8, pady=(2, 8), sticky="we")
        self.export_status_var = tk.StringVar(value="")
        ttk.Label(wave, textvariable=self.export_status_var, font=("Consolas", 9),
                  background=PANEL, foreground=MUTED).grid(
            row=4, column=0, columnspan=4, pady=(0, 8))

    # ==================================================================
    # TAB 6 — Console
    # ==================================================================

    def _build_console_tab(self):
        frm = ttk.LabelFrame(self.tab_console, text="Debug Console")
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.console_output = tk.Text(frm, height=14, bg=DARK_BG, fg=ACCENT,
                                      insertbackground=ACCENT, relief="flat",
                                      font=("Consolas", 10))
        self.console_output.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        self.console_output.insert(tk.END, "LabDesk Debug Console — type a command and press Send\n")
        self.console_output.insert(tk.END, "Try: *IDN? | STATUS? | TEMP? | HELP\n\n")

        input_row = ttk.Frame(frm, style="TFrame")
        input_row.pack(fill=tk.X, padx=8, pady=(4, 8))
        self.console_entry = ttk.Entry(input_row, width=50)
        self.console_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.console_entry.bind("<Return>", lambda _: self._safe_action(self._send_command))
        ttk.Button(input_row, text="Send", style="Accent.TButton",
                   command=lambda: self._safe_action(self._send_command)).pack(side=tk.LEFT)
        ttk.Button(input_row, text="Clear",
                   command=lambda: self.console_output.delete("1.0", tk.END)).pack(
            side=tk.LEFT, padx=(4, 0))

    # ==================================================================
    # Right panel — Preview + Log
    # ==================================================================

    def _build_right_panel(self, parent):
        # Preview notebook
        preview_nb = ttk.Notebook(parent)
        preview_nb.pack(fill=tk.BOTH, expand=True)

        # Raw Preview tab
        raw_tab = ttk.Frame(preview_nb, style="Card.TFrame")
        preview_nb.add(raw_tab, text="Raw Preview")
        self.raw_fig = Figure(figsize=(10, 5), dpi=100, facecolor="#0A1D33")
        self.raw_ax = self.raw_fig.add_subplot(111)
        self.raw_ax.set_facecolor("#0E2A45")
        self.raw_ax.tick_params(colors="#A8DDFF", labelsize=8)
        self.raw_ax.spines["bottom"].set_color("#1A3A5A")
        self.raw_ax.spines["left"].set_color("#1A3A5A")
        self.raw_ax.grid(True, alpha=0.15, color="#00E6FF")
        self.raw_canvas = FigureCanvasTkAgg(self.raw_fig, master=raw_tab)
        self.raw_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._draw_empty_preview(self.raw_ax)

        # Datasheet Ready tab
        ds_tab = ttk.Frame(preview_nb, style="Card.TFrame")
        preview_nb.add(ds_tab, text="Datasheet Ready")
        self.ds_fig = Figure(figsize=(10, 5), dpi=100, facecolor="white")
        self.ds_ax = self.ds_fig.add_subplot(111)
        self.ds_ax.set_facecolor("white")
        self.ds_ax.tick_params(colors="#333333", labelsize=8)
        self.ds_ax.grid(True, alpha=0.3, color="#AAAAAA", linestyle="--")
        self.ds_canvas = FigureCanvasTkAgg(self.ds_fig, master=ds_tab)
        self.ds_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._draw_empty_preview(self.ds_ax, dark=False)

        # ---- Log ----
        log_box = ttk.LabelFrame(parent, text="Log")
        log_box.pack(fill=tk.BOTH, expand=False, pady=(8, 0))
        self.log_text = tk.Text(log_box, height=10, bg=DARK_BG, fg="#A8DDFF",
                                insertbackground="#A8DDFF", relief="flat",
                                font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

    # ==================================================================
    # Help system
    # ==================================================================

    def _build_help_map(self):
        self.help_map = {
            "conn_interface": (
                "Interface — Backend Selection\n\n"
                "Simulated: Use the built-in demo engine (no hardware needed).\n"
                "VISA (pyvisa): Experimental generic SCPI connection for real "
                "oscilloscopes via USB/GPIB/Ethernet.\n"
                "Requires pyvisa, pyvisa-py, and a compatible VISA runtime."
            ),
            "conn_resource": (
                "VISA Resource — Connection Address\n\n"
                "Select the VISA resource string that identifies your device.\n"
                "Click 'Discover' to scan for available instruments.\n"
                "Format: USB0::vendor::product::serial::INSTR"
            ),
            "params_time_div": (
                "Time/Div — Horizontal Scale\n\n"
                "Sets the time per horizontal division on the display.\n"
                "Lower values = zoom in (see faster signals).\n"
                "Higher values = zoom out (see slower signals)."
            ),
            "params_offset": (
                "Start Offset — Horizontal Position\n\n"
                "Shifts the waveform left or right on screen.\n"
                "Positive values shift the trigger point to the right."
            ),
            "params_name": (
                "Channel Name — User Alias\n\n"
                "Assign a custom label to this channel for display.\n"
                "Useful for identifying signals (e.g., 'VIN', 'VOUT', 'CLK')."
            ),
            "params_switch": (
                "Channel Switch — Enable/Disable\n\n"
                "Turns the channel acquisition on or off.\n"
                "Disabled channels do not capture data."
            ),
            "params_visible": (
                "Channel Visibility — Show/Hide Trace\n\n"
                "Show or hide the channel trace on the preview.\n"
                "Hidden channels still acquire data but are not displayed."
            ),
            "params_bw": (
                "Bandwidth Limit — Signal Filtering\n\n"
                "Applies a low-pass filter to reduce high-frequency noise.\n"
                "FULL = no limit. Lower values = more filtering."
            ),
            "params_coupling": (
                "Input Coupling — Signal Connection Mode\n\n"
                "DC: Passes both AC and DC components.\n"
                "AC: Blocks DC component, passes only AC.\n"
                "GND: Disconnects input and grounds the channel."
            ),
            "params_vdiv": (
                "Volt/Div — Vertical Scale\n\n"
                "Sets the voltage represented by each vertical division.\n"
                "Adjust to match your signal amplitude."
            ),
            "params_probe": (
                "Probe Ratio — Attenuation Factor\n\n"
                "Set to match your physical probe (X1, X10, X100).\n"
                "Affects voltage readings and display scaling."
            ),
            "params_visible": (
                "Channel Visibility — Show/Hide Trace\n\n"
                "Show or hide the channel trace on the preview.\n"
                "Hidden channels still acquire data but are not displayed."
            ),
            "ctrl_type": (
                "Task Type — Execution Mode\n\n"
                "EDGE: Triggers when signal crosses a threshold.\n"
                "PULSE: Triggers on pulse width conditions.\n"
                "VIDEO: Triggers on video signal patterns."
            ),
            "ctrl_source": (
                "Task Source — Input Channel\n\n"
                "Select which channel provides the trigger signal."
            ),
            "ctrl_slope": (
                "Slope — Trigger Edge Direction\n\n"
                "RISE: Trigger on rising edge (low→high).\n"
                "FALL: Trigger on falling edge (high→low).\n"
                "EITHER: Trigger on either edge."
            ),
            "ctrl_level": (
                "Level — Trigger Threshold\n\n"
                "The voltage level at which the trigger fires.\n"
                "Set in volts relative to ground."
            ),
            "ctrl_mode": (
                "Mode — Trigger Behaviour\n\n"
                "AUTO: Sweeps even without a trigger (shows baseline).\n"
                "NORM: Waits for trigger before sweeping.\n"
                "SINGLE: Captures one sweep and stops."
            ),
            "ctrl_coupling": (
                "Trigger Coupling — Signal Conditioning\n\n"
                "DC: Uses the raw trigger signal.\n"
                "AC: High-pass filters the trigger signal.\n"
                "GND: No trigger signal passed."
            ),
            "ctrl_noise": (
                "Noise Reject — Trigger Stability\n\n"
                "ON: Increases hysteresis to reject noise.\n"
                "Use when triggering on noisy signals."
            ),
            "ctrl_holdoff": (
                "Holdoff — Trigger Dead Time\n\n"
                "Minimum time between triggers.\n"
                "Prevents premature re-triggering on complex waveforms."
            ),
            "metrics_source": (
                "Metric Source — Measurement Channel\n\n"
                "Select which channel to measure.\n"
                "All selected measurement items are read from this channel."
            ),
            "export_dir": (
                "Output Directory\n\n"
                "All exported files (screenshots, CSV data, plots)\n"
                "are saved to this directory. Timestamps are automatically\n"
                "appended to filenames to prevent overwrites."
            ),
            "export_screenshot": (
                "Screenshot Export\n\n"
                "Captures the current waveform display as an image.\n"
                "PNG: Compressed, good for reports.\n"
                "BMP: Uncompressed, good for further processing."
            ),
            "export_svg": (
                "SVG Vector Export\n\n"
                "Exports waveform as a true vector SVG graphic.\n"
                "SVG files are resolution-independent — zoom without pixelation.\n"
                "Ideal for reports, documentation, and publication figures.\n"
                "Options: scope grid overlay, dark/light background."
            ),
            "export_csv": (
                "Data Export (CSV)\n\n"
                "Exports waveform data as comma-separated values.\n"
                "Each enabled channel produces a separate CSV file.\n"
                "CSV columns: Time (s), Voltage (V)\n"
                "Files include timestamps in the filename."
            ),
            "console": (
                "Debug Console\n\n"
                "Send raw commands directly to the backend.\n"
                "Commands ending with '?' are treated as queries.\n"
                "Useful for debugging and exploring capabilities.\n"
                "Try: *IDN?, STATUS?, TEMP?"
            ),
        }

    def _build_help_sections(self):
        self.help_sections = {
            "Connection": ["conn_interface", "conn_resource"],
            "Channels": [
                "params_time_div", "params_offset", "params_name",
                "params_switch", "params_visible", "params_bw",
                "params_coupling", "params_vdiv", "params_probe",
            ],
            "Trigger": [
                "ctrl_type", "ctrl_source", "ctrl_slope", "ctrl_level",
                "ctrl_mode", "ctrl_coupling", "ctrl_noise", "ctrl_holdoff",
            ],
            "Measurements": ["metrics_source"],
            "Export": ["export_dir", "export_screenshot", "export_csv", "export_svg"],
            "Console": ["console"],
        }

    def _open_help_center(self, focus_key=None):
        win = tk.Toplevel(self)
        win.title("LabDesk Help Center")
        win.geometry("900x620")
        win.configure(bg=BG)
        win.transient(self)

        # Search
        search_frame = ttk.Frame(win, style="TFrame")
        search_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(search_frame, text="Search:", font=("Consolas", 11),
                  background=BG, foreground=FG).pack(side=tk.LEFT)
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        # Tree + Content split
        panes = ttk.PanedWindow(win, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left_pane = ttk.Frame(panes, style="Card.TFrame", width=250)
        panes.add(left_pane, weight=0)
        right_pane = ttk.Frame(panes, style="TFrame")
        panes.add(right_pane, weight=1)

        # Tree
        tree = ttk.Treeview(left_pane, show="tree", style="Help.Treeview",
                            selectmode="browse", height=24)
        tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        scroll_tree = ttk.Scrollbar(left_pane, orient=tk.VERTICAL, command=tree.yview)
        scroll_tree.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scroll_tree.set)

        for section, keys in self.help_sections.items():
            node = tree.insert("", tk.END, text=section, open=True)
            for k in keys:
                tree.insert(node, tk.END, text=k.replace("_", " ").title(), values=(k,))

        # Content
        content_frame = ttk.Frame(right_pane, style="Card.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=(6, 0))
        content_text = tk.Text(content_frame, bg=DARK_BG, fg=FG, relief="flat",
                               font=("Consolas", 11), wrap="word", padx=12, pady=12)
        content_text.pack(fill=tk.BOTH, expand=True)

        def _populate_tree(filter_text=""):
            tree.delete(*tree.get_children())
            for section, keys in self.help_sections.items():
                visible_keys = keys
                if filter_text:
                    visible_keys = [k for k in keys
                                    if filter_text.lower() in k.lower()
                                    or filter_text.lower() in self.help_map.get(k, "").lower()
                                    or filter_text.lower() in section.lower()]
                if visible_keys or (filter_text and filter_text.lower() in section.lower()):
                    node = tree.insert("", tk.END, text=section, open=bool(filter_text))
                    for k in visible_keys:
                        tree.insert(node, tk.END, text=k.replace("_", " ").title(),
                                    values=(k,))

        def _show_content(key):
            content_text.delete("1.0", tk.END)
            if key in self.help_map:
                content_text.insert("1.0", self.help_map[key])

        def _on_tree_select(event):
            sel = tree.selection()
            if sel:
                item = tree.item(sel[0])
                if item["values"]:
                    _show_content(item["values"][0])

        tree.bind("<<TreeviewSelect>>", _on_tree_select)
        search_var.trace_add("write", lambda *_: _populate_tree(search_var.get()))

        if focus_key:
            _show_content(focus_key)
        else:
            content_text.insert("1.0",
                                "LabDesk Help Center\n"
                                "====================\n\n"
                                "Select a topic from the left panel or use the search bar.\n"
                                "Each parameter in the main window has a '?' button\n"
                                "that opens this help center with context.\n\n"
                                "The help center is searchable — type keywords to filter.")

        search_entry.focus_set()

    def _add_help_button(self, parent, row, col, key, pack=False):
        btn = ttk.Button(parent, text="?", style="Help.TButton", width=3,
                         command=lambda k=key: self._open_help_center(focus_key=k))
        if pack:
            btn.pack(side=tk.LEFT, padx=(4, 0))
        else:
            btn.grid(row=row, column=col, padx=(4, 0), sticky="w")

    # ==================================================================
    # Actions — Connection
    # ==================================================================

    def _make_engine(self) -> BaseEngine:
        if self.interface_var.get() == "VISA (pyvisa)":
            return VisaScpiEngine()
        return SimulatedEngine()

    def _ensure_engine_for_interface(self, log_change=True):
        wants_visa = self.interface_var.get() == "VISA (pyvisa)"
        has_visa = isinstance(self.engine, VisaScpiEngine)
        if wants_visa == has_visa:
            return

        self._acquisition.stop()
        try:
            self.engine.disconnect()
        except Exception:
            pass

        self.engine = self._make_engine()
        self._frame_queue = queue.Queue()
        self._acquisition = LiveAcquisition(self.engine, self._frame_queue, fps=10)
        self._last_frame.clear()
        self.idn_var.set("Disconnected")
        self.status_var.set("Idle")
        if log_change:
            self._log(f"Interface switched to {self.interface_var.get()}.")

    def _discover(self):
        self._ensure_engine_for_interface()
        self._log("Discovering devices...")
        resources = self.engine.discover()
        if resources:
            self.resource_var.set(resources[0])
            self._log(f"Found {len(resources)} device(s): {', '.join(resources)}")
        else:
            self._log("No devices found.")

    def _connect(self):
        self._ensure_engine_for_interface()
        resource = self.resource_var.get()
        if not resource:
            raise ValueError("Select a resource first (click Discover).")
        self._log(f"Connecting to {resource} ...")
        idn = self.engine.connect(resource)
        self.idn_var.set(idn)
        self.status_var.set("Connected")
        self._log(f"Connected: {idn}")

    def _disconnect(self):
        self.engine.disconnect()
        self.idn_var.set("Disconnected")
        self.status_var.set("Idle")
        self._log("Disconnected from device.")

    # ==================================================================
    # Actions — Parameters
    # ==================================================================

    def _apply_channel(self, ch):
        eng = self.engine
        eng.set_channel_enabled(ch, self.ch_enable_vars[ch].get())
        eng.set_channel_visible(ch, self.ch_visible_vars[ch].get())
        eng.set_channel_bandwidth(ch, self.ch_bw_vars[ch].get())
        eng.set_channel_coupling(ch, self.ch_coupling_vars[ch].get())
        eng.set_channel_volt_div(ch, self._parse_voltage(self.ch_vdiv_vars[ch].get()))
        eng.set_channel_vert_offset(ch, self._parse_voltage(self.ch_offset_vars[ch].get()))
        eng.set_channel_name(ch, self.ch_name_vars[ch].get())

        probe_str = self.ch_probe_vars[ch].get().lstrip("Xx")
        eng.set_channel_probe(ch, int(probe_str) if probe_str.isdigit() else 1)

        self._log(f"CH{ch} parameters applied — "
                  f"Name={eng.channels[ch]['name']}, "
                  f"Switch={'ON' if eng.channels[ch]['enabled'] else 'OFF'}, "
                  f"Coupling={eng.channels[ch]['coupling']}")

    def _set_time_div(self):
        val = self._parse_time(self.time_div_var.get())
        self.engine.set_time_div(val)
        self._log(f"Time/Div set to {val:.2e}s")

    def _set_time_offset(self):
        val = self._parse_time(self.time_offset_var.get())
        self.engine.set_time_offset(val)
        self._log(f"Time Offset set to {val:.2e}s")

    def _set_probe_all(self):
        self.engine.set_probe_all(10)
        for ch in self.ch_ids:
            self.ch_probe_vars[ch].set("X10")
        self._log("All channels probe ratio set to X10")

    # ==================================================================
    # Actions — Control
    # ==================================================================

    def _apply_control(self):
        eng = self.engine
        eng.set_trigger(
            type=self.trig_type_var.get(),
            source=self.trig_source_var.get(),
            slope=self.trig_slope_var.get(),
            level=self._parse_voltage(self.trig_level_var.get()),
            mode=self.trig_mode_var.get(),
            coupling=self.trig_coupling_var.get(),
            noise_reject=self.trig_noise_var.get(),
            holdoff_time=self._parse_time(self.trig_holdoff_var.get()),
        )
        self._log("Control configuration applied.")
        self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Configuration applied\n"
                                f"  Type={self.trig_type_var.get()}, "
                                f"Source={self.trig_source_var.get()}, "
                                f"Mode={self.trig_mode_var.get()}\n")
        self.ctrl_output.see(tk.END)

    def _run_task(self):
        if not self.engine.connected:
            raise RuntimeError("Not connected. Connect a device first.")
        if not self.engine.start_task("run", steps=15):
            raise RuntimeError("A task is already running.")

        self._task_running = True
        self._log("Task started...")
        self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Task started\n")
        self._poll_task()

    def _poll_task(self):
        if not self._task_running:
            return
        progress = self.engine.poll_task_progress()
        if progress < 0:
            self._task_running = False
            self._log("Task cancelled.")
            self.ctrl_output.insert(tk.END, "Task cancelled.\n")
            self.ctrl_output.see(tk.END)
            return
        if progress >= 100:
            self._task_running = False
            self._log("Task completed successfully.")
            self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Task completed (100%)\n")
            self.ctrl_output.see(tk.END)
        else:
            self.after(120, self._poll_task)

    def _cancel_task(self):
        self.engine.cancel_task()
        self._log("Cancelling task...")

    def _query_status(self):
        if not self.engine.connected:
            raise RuntimeError("Not connected.")
        status = self.engine.get_trigger_status()
        self._log(f"Status: {status}")
        self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Status: {status}\n")
        self.ctrl_output.see(tk.END)

    def _reset_control(self):
        self.ctrl_output.delete("1.0", tk.END)
        self._log("Control output cleared.")

    # -- Acquisition control -------------------------------------------

    def _acq_run(self):
        self._acquisition.start_run()
        self._log("Acquisition RUN")
        self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Acquisition RUN\n")
        self.ctrl_output.see(tk.END)

    def _acq_stop(self):
        self._acquisition.stop()
        self._log("Acquisition STOP")
        self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Acquisition STOP\n")
        self.ctrl_output.see(tk.END)

    def _acq_single(self):
        self._acquisition.start_single()
        self._log("Acquisition SINGLE — capturing one frame")
        self.ctrl_output.insert(tk.END, f"[{datetime.now():%H:%M:%S}] Acquisition SINGLE\n")
        self.ctrl_output.see(tk.END)

    # ==================================================================
    # Actions — Metrics
    # ==================================================================

    def _get_selected_metrics(self) -> list[str]:
        selected = self.metrics_listbox.curselection()
        return [METRIC_OPTIONS[i] for i in selected]

    def _select_common_metrics(self):
        self.metrics_listbox.selection_clear(0, tk.END)
        for i, item in enumerate(METRIC_OPTIONS):
            if item in DEFAULT_METRICS:
                self.metrics_listbox.selection_set(i)
        self._log("Common metrics selected.")

    def _select_all_metrics(self):
        self.metrics_listbox.selection_set(0, tk.END)
        self._log("All metrics selected.")

    def _clear_metrics(self):
        self.metrics_listbox.selection_clear(0, tk.END)
        self._log("Metric selection cleared.")

    def _read_metrics(self):
        if not self.engine.connected:
            raise RuntimeError("Not connected.")
        items = self._get_selected_metrics()
        if not items:
            raise ValueError("No measurement items selected.")
        source = int(self.metrics_source_var.get())
        results = self.engine.read_metrics(source, items)

        self.metrics_output.delete("1.0", tk.END)
        self.metrics_output.insert(tk.END, f"  CH{source} Measurements\n")
        self.metrics_output.insert(tk.END, f"  {'─' * 40}\n")
        for item, value in sorted(results.items()):
            self.metrics_output.insert(tk.END, f"  {item:<16s} {value:>15.6f}\n")
        self._log(f"Read {len(results)} metrics from CH{source}")

    def _read_frequency(self):
        if not self.engine.connected:
            raise RuntimeError("Not connected.")
        source = int(self.metrics_source_var.get())
        freq = self.engine.read_frequency(source)
        self.metrics_output.insert(tk.END, f"\n  CH{source} Frequency: {freq:,.1f} Hz\n")
        self.metrics_output.see(tk.END)
        self._log(f"CH{source} Frequency: {freq:,.1f} Hz")

    # ==================================================================
    # Actions — Export
    # ==================================================================

    def _browse_output_dir(self):
        path = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)

    def _save_screenshot(self):
        out_dir = Path(self.output_dir_var.get())
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = self.screenshot_name_var.get() or "screenshot"
        fmt = self.screenshot_fmt_var.get()
        path = out_dir / f"{name}_{ts}.{fmt.lower()}"

        self._log(f"Saving screenshot to {path} ...")
        self.engine.save_screenshot(str(path), fmt=fmt)
        self._log(f"Screenshot saved: {path}")

    def _export_svg(self):
        """Export waveform as SVG vector graphic for each selected channel."""
        selected = [ch for ch in self.ch_ids if self.export_svg_ch_vars[ch].get()]
        if not selected:
            raise ValueError("Select at least one channel for SVG export.")
        out_dir = Path(self.output_dir_var.get())
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        scope_grid = self.svg_scope_grid_var.get()
        dark = self.svg_dark_bg_var.get()

        for ch in selected:
            name = self.screenshot_name_var.get() or "waveform"
            path = out_dir / f"{name}_CH{ch}_{ts}.svg"
            self._log(f"Exporting SVG CH{ch} → {path} ...")
            self.engine.save_waveform_svg(
                str(path), int(ch), scope_grid=scope_grid, dark=dark)
            self._log(f"SVG saved: {path}")

    def _export_data(self):
        if self._export_running:
            raise RuntimeError("Export already running.")
        selected = [ch for ch in self.ch_ids if self.export_ch_vars[ch].get()]
        if not selected:
            raise ValueError("Select at least one channel to export.")

        self._export_running = True
        self.export_progress["value"] = 0
        self.export_status_var.set("Exporting...")
        self._log(f"Starting data export for {len(selected)} channel(s)...")

        worker = threading.Thread(
            target=self._export_worker,
            args=(selected,),
            daemon=True,
        )
        worker.start()

    def _export_worker(self, channels):
        out_dir = Path(self.output_dir_var.get())
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        total = len(channels)

        for i, ch in enumerate(channels):
            if not self._export_running:
                break
            name = f"waveform_CH{ch}_{ts}.csv"
            path = out_dir / name
            self._post_ui(self._log, f"Exporting CH{ch} → {path} ...")
            self.engine.save_waveform_csv(int(ch), str(path))
            progress = (i + 1) / total * 100
            self._post_ui(self.export_progress.configure, **{"value": progress})
            self._post_ui(self.export_status_var.set, f"CH{ch} done ({i + 1}/{total})")

        # Auto-plot
        if self.export_plot_var.get():
            self._post_ui(self._plot_exported_data, channels)

        self._post_ui(self._finish_export)

    def _plot_exported_data(self, channels):
        self.raw_ax.clear()
        self.ds_ax.clear()

        out_dir = Path(self.output_dir_var.get())
        colors = ["#00E6FF", "#FFB800", "#FF5E5E", "#5EFF5E"]

        for ch in channels:
            # Find the CSV we just wrote
            csv_files = sorted(out_dir.glob(f"waveform_CH{ch}_*.csv"))
            if not csv_files:
                continue
            latest = csv_files[-1]
            try:
                t, v = self._read_csv(latest)
                c = colors[int(ch) - 1] if int(ch) <= len(colors) else "#FFFFFF"
                name = self.ch_name_vars[ch].get() or f"CH{ch}"

                self.raw_ax.plot(t, v, color=c, linewidth=1.0, label=name)
                self.ds_ax.plot(t, v, color=c, linewidth=1.5, label=name)
            except Exception as e:
                self._log(f"Plot error CH{ch}: {e}")

        self._style_plot(self.raw_ax, dark=True)
        self._style_plot(self.ds_ax, dark=False)
        self.raw_canvas.draw()
        self.ds_canvas.draw()
        self._log("Waveform plotted in preview panels.")

    def _finish_export(self):
        self._export_running = False
        self.export_progress["value"] = 100
        self.export_status_var.set("Export complete")
        self._log("Data export finished.")

    def _read_csv(self, path: Path) -> tuple[list[float], list[float]]:
        t, v = [], []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # header
            for row in reader:
                if len(row) >= 2:
                    t.append(float(row[0]))
                    v.append(float(row[1]))
        return t, v

    # ==================================================================
    # Actions — Console
    # ==================================================================

    def _send_command(self):
        cmd = self.console_entry.get().strip()
        if not cmd:
            return
        self.console_output.insert(tk.END, f">>> {cmd}\n")
        try:
            result = self.engine.exec_command(cmd)
            self.console_output.insert(tk.END, f"{result}\n\n")
            self._log(f"CMD: {cmd} → {result.split(chr(10))[0]}")
        except Exception as e:
            self.console_output.insert(tk.END, f"ERROR: {e}\n\n")
            self._log(f"CMD error: {e}")
        self.console_output.see(tk.END)
        self.console_entry.delete(0, tk.END)

    # ==================================================================
    # Plot helpers
    # ==================================================================

    def _draw_empty_preview(self, ax, dark=True):
        if dark:
            ax.text(0.5, 0.5, "No Data\n\nRun an export or task to see waveforms here.",
                    transform=ax.transAxes, ha="center", va="center",
                    color="#446688", fontsize=13, fontfamily="Consolas")
        else:
            ax.text(0.5, 0.5, "No Data\n\nRun an export or task to see waveforms here.",
                    transform=ax.transAxes, ha="center", va="center",
                    color="#AAAAAA", fontsize=13, fontfamily="Consolas")
        ax.get_figure().canvas.draw()

    def _style_plot(self, ax, dark=True):
        if dark:
            ax.set_facecolor("#0E2A45")
            ax.tick_params(colors="#A8DDFF", labelsize=8)
            ax.spines["bottom"].set_color("#1A3A5A")
            ax.spines["left"].set_color("#1A3A5A")
            ax.grid(True, alpha=0.15, color="#00E6FF")
            ax.set_xlabel("Time", color="#A8DDFF", fontfamily="Consolas")
            ax.set_ylabel("Voltage", color="#A8DDFF", fontfamily="Consolas")
            ax.legend(loc="upper right", facecolor="#0A1D33",
                      edgecolor="#1A3A5A", labelcolor="#A8DDFF",
                      fontsize=8)
        else:
            ax.set_facecolor("white")
            ax.tick_params(colors="#333333", labelsize=8)
            ax.spines["bottom"].set_color("#333333")
            ax.spines["left"].set_color("#333333")
            ax.grid(True, alpha=0.3, color="#AAAAAA", linestyle="--")
            ax.set_xlabel("Time", color="#333333", fontfamily="Consolas")
            ax.set_ylabel("Voltage", color="#333333", fontfamily="Consolas")
            ax.legend(loc="upper right", facecolor="white",
                      edgecolor="#AAAAAA", fontsize=8)

    # ==================================================================
    # Config persistence
    # ==================================================================

    def _save_ini(self, quiet=False):
        cfg = configparser.ConfigParser()
        cfg["Connection"] = {
            "resource": self.resource_var.get(),
            "interface": self.interface_var.get(),
        }
        cfg["Channel"] = {
            "time_div": self.time_div_var.get(),
            "time_offset": self.time_offset_var.get(),
        }
        for ch in self.ch_ids:
            cfg[f"CH{ch}"] = {
                "name": self.ch_name_vars[ch].get(),
                "enable": str(self.ch_enable_vars[ch].get()),
                "visible": str(self.ch_visible_vars[ch].get()),
                "bandwidth": self.ch_bw_vars[ch].get(),
                "coupling": self.ch_coupling_vars[ch].get(),
                "volt_div": self.ch_vdiv_vars[ch].get(),
                "vert_offset": self.ch_offset_vars[ch].get(),
                "probe": self.ch_probe_vars[ch].get(),
            }
        cfg["Trigger"] = {
            "type": self.trig_type_var.get(),
            "source": self.trig_source_var.get(),
            "slope": self.trig_slope_var.get(),
            "level": self.trig_level_var.get(),
            "mode": self.trig_mode_var.get(),
            "coupling": self.trig_coupling_var.get(),
            "noise": self.trig_noise_var.get(),
            "holdoff": self.trig_holdoff_var.get(),
        }
        cfg["Export"] = {
            "output_dir": self.output_dir_var.get(),
            "screenshot_name": self.screenshot_name_var.get(),
            "screenshot_format": self.screenshot_fmt_var.get(),
            "svg_scope_grid": str(self.svg_scope_grid_var.get()),
            "svg_dark_bg": str(self.svg_dark_bg_var.get()),
            "auto_plot": str(self.export_plot_var.get()),
        }
        cfg["Plot"] = {
            "filter": self.plot_filter_var.get(),
            "filter_window": str(self.plot_filter_win_var.get()),
            "linewidth": str(self.plot_linewidth_var.get()),
            "scope_grid": str(self.plot_scope_grid_var.get()),
            "show_legend": str(self.plot_show_legend_var.get()),
            "show_title": str(self.plot_show_title_var.get()),
            "show_tags": str(self.plot_show_tags_var.get()),
        }
        cfg["Metrics"] = {"source": self.metrics_source_var.get()}
        cfg["Window"] = {
            "width": str(self.winfo_width()),
            "height": str(self.winfo_height()),
        }
        with open(APP_INI, "w", encoding="utf-8") as f:
            cfg.write(f)
        if not quiet:
            self._log("Configuration saved.")

    def _load_ini(self):
        if not APP_INI.exists():
            return
        cfg = configparser.ConfigParser()
        cfg.read(APP_INI, encoding="utf-8")

        _get = lambda s, k, fallback="": cfg.get(s, k, fallback=fallback)
        _getbool = lambda s, k, fb=False: cfg.getboolean(s, k, fallback=fb)

        self.resource_var.set(_get("Connection", "resource"))
        self.interface_var.set(_get("Connection", "interface", "Simulated"))
        self.time_div_var.set(_get("Channel", "time_div", "10ms"))
        self.time_offset_var.set(_get("Channel", "time_offset", "30ms"))
        for ch in self.ch_ids:
            if f"CH{ch}" not in cfg:
                continue
            sc = cfg[f"CH{ch}"]
            self.ch_name_vars[ch].set(sc.get("name", f"CH{ch}"))
            self.ch_enable_vars[ch].set(sc.getboolean("enable", True))
            self.ch_visible_vars[ch].set(sc.getboolean("visible", True))
            self.ch_bw_vars[ch].set(sc.get("bandwidth", "FULL"))
            self.ch_coupling_vars[ch].set(sc.get("coupling", "DC"))
            self.ch_vdiv_vars[ch].set(sc.get("volt_div", "2V"))
            self.ch_offset_vars[ch].set(sc.get("vert_offset", "0V"))
            self.ch_probe_vars[ch].set(sc.get("probe", "X10"))

        self.trig_type_var.set(_get("Trigger", "type", "EDGE"))
        self.trig_source_var.set(_get("Trigger", "source", "CH1"))
        self.trig_slope_var.set(_get("Trigger", "slope", "RISE"))
        self.trig_level_var.set(_get("Trigger", "level", "0V"))
        self.trig_mode_var.set(_get("Trigger", "mode", "AUTO"))
        self.trig_coupling_var.set(_get("Trigger", "coupling", "DC"))
        self.trig_noise_var.set(_get("Trigger", "noise", "OFF"))
        self.trig_holdoff_var.set(_get("Trigger", "holdoff", "100ns"))

        self.output_dir_var.set(_get("Export", "output_dir", str(APP_DIR / "output")))
        self.screenshot_name_var.set(_get("Export", "screenshot_name", "screenshot"))
        self.screenshot_fmt_var.set(_get("Export", "screenshot_format", "PNG"))
        self.svg_scope_grid_var.set(_getbool("Export", "svg_scope_grid", True))
        self.svg_dark_bg_var.set(_getbool("Export", "svg_dark_bg", False))
        self.export_plot_var.set(_getbool("Export", "auto_plot", True))
        self.metrics_source_var.set(_get("Metrics", "source", "CH1"))
        self.plot_filter_var.set(_get("Plot", "filter", "OFF"))
        self.plot_filter_win_var.set(int(_get("Plot", "filter_window", "9")))

    def _init_autosave_watchers(self):
        all_vars = [
            self.resource_var, self.interface_var,
            self.time_div_var, self.time_offset_var,
            self.output_dir_var, self.screenshot_name_var, self.screenshot_fmt_var,
            self.trig_type_var, self.trig_source_var, self.trig_slope_var,
            self.trig_level_var, self.trig_mode_var, self.trig_coupling_var,
            self.trig_noise_var, self.trig_holdoff_var,
            self.metrics_source_var, self.export_plot_var,
            self.svg_scope_grid_var, self.svg_dark_bg_var,
            self.plot_filter_var, self.plot_filter_win_var, self.plot_linewidth_var,
            self.plot_scope_grid_var, self.plot_show_legend_var,
            self.plot_show_title_var, self.plot_show_tags_var,
        ]
        for ch in self.ch_ids:
            all_vars.extend([
                self.ch_name_vars[ch], self.ch_enable_vars[ch], self.ch_visible_vars[ch],
                self.ch_bw_vars[ch], self.ch_coupling_vars[ch],
                self.ch_vdiv_vars[ch], self.ch_offset_vars[ch], self.ch_probe_vars[ch],
            ])

        for var in all_vars:
            var.trace_add("write", lambda *_: self._schedule_autosave())

    _autosave_id = None

    def _schedule_autosave(self):
        if self._autosave_id is not None:
            self.after_cancel(self._autosave_id)
        self._autosave_id = self.after(1500, self._autosave_now)

    def _autosave_now(self):
        self._save_ini(quiet=True)
        self._autosave_id = None

    # ==================================================================
    # Thread-safe UI helpers
    # ==================================================================

    def _post_ui(self, fn, *args, **kwargs):
        self._ui_queue.put((fn, args, kwargs))

    def _drain_ui_queue(self):
        try:
            while True:
                fn, args, kwargs = self._ui_queue.get_nowait()
                fn(*args, **kwargs)
        except queue.Empty:
            pass
        self.after(80, self._drain_ui_queue)

    def _drain_frame_queue(self):
        """Consume acquisition frames and render live waveforms to preview."""
        try:
            while True:
                frame: AcquisitionFrame = self._frame_queue.get_nowait()
                self._last_frame[frame.channel] = frame
        except queue.Empty:
            pass

        # Render if we have any frames
        if self._last_frame:
            self._render_live_preview()
        self._update_acq_status()
        self.after(50, self._drain_frame_queue)

    def _render_live_preview(self):
        channels_to_plot = sorted(self._last_frame.keys())
        colors = {"1": "#00E6FF", "2": "#FFB800", "3": "#FF5E5E", "4": "#5EFF5E"}
        if not channels_to_plot:
            return

        # -- Raw preview (dark, scope-style) --
        self.raw_ax.clear()
        for ch in channels_to_plot:
            frame = self._last_frame[ch]
            c = colors.get(str(ch), "#FFFFFF")
            name = self.ch_name_vars.get(str(ch), tk.StringVar(value=f"CH{ch}")).get()
            self.raw_ax.plot(frame.time_data, frame.voltage_data,
                            color=c, linewidth=1.0, label=name)
        self._style_scope_plot(self.raw_ax, dark=True)
        self.raw_canvas.draw()

        # -- Datasheet preview (light) --
        self.ds_ax.clear()
        for ch in channels_to_plot:
            frame = self._last_frame[ch]
            c = colors.get(str(ch), "#000000")
            name = self.ch_name_vars.get(str(ch), tk.StringVar(value=f"CH{ch}")).get()
            self.ds_ax.plot(frame.time_data, frame.voltage_data,
                           color=c, linewidth=1.5, label=name)
        self._style_scope_plot(self.ds_ax, dark=False)
        self.ds_canvas.draw()

    def _style_scope_plot(self, ax, dark=True):
        """Apply oscilloscope-style graticule styling."""
        if dark:
            ax.set_facecolor("#0E2A45")
            ax.tick_params(colors="#A8DDFF", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#1A3A5A")
            ax.grid(True, alpha=0.15, color="#00E6FF", linestyle="-", linewidth=0.5)
            ax.minorticks_on()
            ax.grid(True, which="minor", alpha=0.08, color="#00E6FF",
                    linestyle=":", linewidth=0.3)
            ax.set_xlabel("Time (s)", color="#A8DDFF", fontfamily="monospace")
            ax.set_ylabel("Voltage (V)", color="#A8DDFF", fontfamily="monospace")
            ax.legend(loc="upper right", facecolor="#0A1D33",
                      edgecolor="#1A3A5A", labelcolor="#A8DDFF", fontsize=8)
        else:
            ax.set_facecolor("white")
            ax.tick_params(colors="#333333", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#333333")
            ax.grid(True, alpha=0.3, color="#AAAAAA", linestyle="-", linewidth=0.5)
            ax.minorticks_on()
            ax.grid(True, which="minor", alpha=0.15, color="#AAAAAA",
                    linestyle=":", linewidth=0.3)
            ax.set_xlabel("Time (s)", color="#333333", fontfamily="monospace")
            ax.set_ylabel("Voltage (V)", color="#333333", fontfamily="monospace")
            ax.legend(loc="upper right", facecolor="white",
                      edgecolor="#AAAAAA", fontsize=8)

    def _update_acq_status(self):
        status = self._acquisition.get_status()
        self.acq_fps_label.config(text=f"Acquisition: {status.mode} · {status.fps} fps")
        if status.mode in ("RUN", "SINGLE"):
            self.acq_fps_label.config(foreground=ACCENT)
        else:
            self.acq_fps_label.config(foreground=MUTED)

    # ==================================================================
    # Utilities
    # ==================================================================

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)

    def _safe_action(self, fn):
        try:
            fn()
        except Exception as e:
            messagebox.showerror("Operation Failed", str(e))
            self._log(traceback.format_exc())

    def _parse_time(self, text: str) -> float:
        text = text.strip().lower()
        multipliers = {"ps": 1e-12, "ns": 1e-9, "us": 1e-6,
                       "ms": 1e-3, "s": 1.0}
        for unit, mult in multipliers.items():
            if text.endswith(unit):
                return float(text.replace(unit, "")) * mult
        return float(text)

    def _parse_voltage(self, text: str) -> float:
        text = text.strip().lower()
        multipliers = {"uv": 1e-6, "mv": 1e-3, "v": 1.0, "kv": 1e3}
        for unit, mult in multipliers.items():
            if text.endswith(unit):
                return float(text.replace(unit, "")) * mult
        return float(text.replace("v", ""))

    def on_close(self):
        self._acquisition.stop()
        self._save_ini(quiet=True)
        self.destroy()


# ===================================================================
# Entry point
# ===================================================================

def main():
    app = LabDeskApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
