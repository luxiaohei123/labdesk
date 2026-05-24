import csv
import math
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ======================================================================
# Base Engine — abstract interface for any oscilloscope backend
# ======================================================================

class BaseEngine(ABC):
    """Abstract base class for oscilloscope backends.

    Subclass this to add real VISA hardware support — the UI never
    calls any hardware-specific code directly.
    """

    def __init__(self):
        self._connected = False
        self._device_id = ""
        self._device_name = ""
        self.channels: dict = {}
        self.time_div: float = 0.01
        self.time_offset: float = 0.03
        self.trigger: dict = {}

    # -- connection ---------------------------------------------------

    @abstractmethod
    def discover(self) -> list[str]:
        """Return a list of available VISA resource strings."""
        ...

    @abstractmethod
    def connect(self, resource: str) -> str:
        """Connect to the instrument. Returns *IDN? response."""
        ...

    @abstractmethod
    def disconnect(self):
        """Disconnect from the instrument."""
        ...

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def device_name(self) -> str:
        return self._device_name or "Disconnected"

    # -- channel ------------------------------------------------------

    @abstractmethod
    def set_channel_enabled(self, ch: str, state: bool): ...
    @abstractmethod
    def set_channel_visible(self, ch: str, state: bool): ...
    @abstractmethod
    def set_channel_bandwidth(self, ch: str, bw: str): ...
    @abstractmethod
    def set_channel_coupling(self, ch: str, mode: str): ...
    @abstractmethod
    def set_channel_volt_div(self, ch: str, vdiv: float): ...
    @abstractmethod
    def set_channel_vert_offset(self, ch: str, offset: float): ...
    @abstractmethod
    def set_channel_name(self, ch: str, name: str): ...
    @abstractmethod
    def set_channel_probe(self, ch: str, ratio: int): ...
    @abstractmethod
    def set_probe_all(self, ratio: int): ...
    @abstractmethod
    def set_time_div(self, value: float): ...
    @abstractmethod
    def set_time_offset(self, value: float): ...

    # -- trigger ------------------------------------------------------

    @abstractmethod
    def set_trigger(self, **kwargs): ...
    @abstractmethod
    def trigger_single(self): ...
    @abstractmethod
    def trigger_force(self): ...
    @abstractmethod
    def set_trigger_mode(self, mode: str): ...
    @abstractmethod
    def get_trigger_status(self) -> str: ...

    # -- measurement --------------------------------------------------

    AVAILABLE_METRICS = [
        "Vpp", "Vmax", "Vmin", "Vavg", "Vrms",
        "Freq", "Period", "RiseTime", "FallTime",
        "PosWidth", "NegWidth", "DutyCycle",
        "Overshoot", "Undershoot", "PulseCount",
    ]

    @abstractmethod
    def read_metrics(self, channel: int, items: list[str]) -> dict[str, float]: ...
    @abstractmethod
    def read_frequency(self, channel: int) -> float: ...

    # -- task ---------------------------------------------------------

    @abstractmethod
    def start_task(self, task_type: str, steps: int = 10) -> bool: ...
    @abstractmethod
    def cancel_task(self): ...
    @abstractmethod
    def poll_task_progress(self) -> float: ...

    @property
    @abstractmethod
    def task_running(self) -> bool: ...

    # -- waveform -----------------------------------------------------

    @abstractmethod
    def generate_waveform(self, channel: int, num_points: int = 2000) -> tuple:
        """Return (time_list_s, voltage_list_v) for a single channel."""
        ...

    # -- SVG export ---------------------------------------------------

    def save_waveform_csv(self, channel: int, save_path: str,
                          num_points: int = 2000) -> str:
        """Save a single-channel waveform as CSV."""
        t, v = self.generate_waveform(channel, num_points)
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Time (s)", "Voltage (V)"])
            for ti, vi in zip(t, v):
                writer.writerow([f"{ti:.10f}", f"{vi:.8f}"])
        return str(path)

    def save_screenshot(self, save_path: str, fmt: str = "PNG") -> str:
        """Render enabled waveform channels to an image file."""
        fig, ax = plt.subplots(figsize=(12, 7), facecolor="#0A1D33")
        ax.set_facecolor("#0E2A45")

        colors = ["#00E6FF", "#FFB800", "#FF5E5E", "#5EFF5E"]
        plotted = False
        for ch_str, info in self.channels.items():
            if not (info.get("enabled", True) and info.get("visible", True)):
                continue
            ch = int(ch_str)
            t, v = self.generate_waveform(ch)
            color = colors[(ch - 1) % len(colors)]
            ax.plot(t, v, color=color, linewidth=1.2,
                    label=info.get("name") or f"CH{ch}")
            plotted = True

        if not plotted:
            t, v = self.generate_waveform(1)
            ax.plot(t, v, color=colors[0], linewidth=1.2, label="CH1")

        ax.set_xlabel("Time (s)", color="#A8DDFF")
        ax.set_ylabel("Voltage (V)", color="#A8DDFF")
        ax.tick_params(colors="#A8DDFF")
        ax.grid(True, alpha=0.2, color="#00E6FF")
        ax.legend(loc="upper right")
        ax.set_title("Oscilloscope Waveform", color="#00E6FF", fontsize=14)
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, facecolor=fig.get_facecolor(), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def save_waveform_svg(self, save_path: str, channel: int,
                          num_points: int = 2000, scope_grid: bool = True,
                          dark: bool = False) -> str:
        """Generate a single-channel waveform as a vector SVG file.

        Uses Matplotlib's SVG backend so the output is true vector —
        zoomable without pixelation, ideal for reports and documentation.
        """
        t, v = self.generate_waveform(channel, num_points)

        bg_color = "#0A1D33" if dark else "#FFFFFF"
        ax_bg = "#0E2A45" if dark else "#FFFFFF"
        fg_color = "#A8DDFF" if dark else "#333333"
        accent = "#00E6FF" if dark else "#0066CC"
        grid_alpha = 0.15 if dark else 0.25

        fig, ax = plt.subplots(figsize=(12, 6), facecolor=bg_color)
        ax.set_facecolor(ax_bg)

        # Determine voltage range for graticule
        v_min, v_max = min(v), max(v)
        v_margin = (v_max - v_min) * 0.15 or 1.0
        ax.set_ylim(v_min - v_margin, v_max + v_margin)
        ax.set_xlim(t[0], t[-1])

        ax.plot(t, v, color=accent, linewidth=1.5,
                label=f"CH{channel}")

        if scope_grid:
            ax.grid(True, alpha=grid_alpha, color=accent, linestyle="-", linewidth=0.5)
            ax.minorticks_on()
            ax.grid(True, which="minor", alpha=grid_alpha * 0.5, color=accent,
                    linestyle=":", linewidth=0.3)

        ax.set_xlabel("Time (s)", color=fg_color, fontfamily="monospace")
        ax.set_ylabel("Voltage (V)", color=fg_color, fontfamily="monospace")
        ax.tick_params(colors=fg_color, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(fg_color)

        if v:
            ax.legend(loc="upper right", facecolor=bg_color,
                      edgecolor=fg_color, labelcolor=fg_color, fontsize=9)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ax.set_title(f"CH{channel} — {ts}",
                     color=accent, fontsize=13, fontfamily="monospace")

        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, format="svg", facecolor=fig.get_facecolor(),
                    bbox_inches="tight", dpi=150)
        plt.close(fig)
        return str(path)

    # -- console ------------------------------------------------------

    @abstractmethod
    def exec_command(self, cmd: str) -> str: ...


# ======================================================================
# VISA SCPI Engine - experimental real-instrument backend
# ======================================================================

class VisaScpiEngine(BaseEngine):
    """Generic pyvisa + SCPI backend for common oscilloscopes.

    This backend intentionally uses conservative, widely seen SCPI commands.
    Instrument vendors differ, so unsupported commands raise readable errors
    instead of silently falling back to simulated data.
    """

    MEASUREMENT_COMMANDS = {
        "Vpp": ":MEAS:VPP? CHAN{channel}",
        "Vmax": ":MEAS:VMAX? CHAN{channel}",
        "Vmin": ":MEAS:VMIN? CHAN{channel}",
        "Vavg": ":MEAS:VAVG? CHAN{channel}",
        "Vrms": ":MEAS:VRMS? CHAN{channel}",
        "Freq": ":MEAS:FREQ? CHAN{channel}",
        "Period": ":MEAS:PER? CHAN{channel}",
        "RiseTime": ":MEAS:RISE? CHAN{channel}",
        "FallTime": ":MEAS:FALL? CHAN{channel}",
        "PosWidth": ":MEAS:PWID? CHAN{channel}",
        "NegWidth": ":MEAS:NWID? CHAN{channel}",
        "DutyCycle": ":MEAS:DUTY? CHAN{channel}",
    }

    def __init__(self, resource_manager=None, timeout_ms: int = 5000):
        super().__init__()
        self._resource_manager = resource_manager
        self._instrument = None
        self._timeout_ms = timeout_ms
        self.channels = {
            str(ch): {"name": f"CH{ch}", "enabled": True, "visible": True,
                      "bandwidth": "FULL", "coupling": "DC",
                      "volt_div": 1.0, "vert_offset": 0.0, "probe": 10}
            for ch in range(1, 5)
        }
        self.trigger = {
            "type": "EDGE", "source": "CH1", "slope": "RISE",
            "level": 0.0, "mode": "AUTO",
            "coupling": "DC", "noise_reject": "OFF",
            "holdoff_time": 100e-9, "holdoff_event": 0,
        }
        self._task_running = False

    # -- connection ---------------------------------------------------

    def _manager(self):
        if self._resource_manager is None:
            try:
                import pyvisa
            except ImportError as exc:
                raise RuntimeError(
                    "pyvisa is not installed. Run: pip install -r requirements.txt"
                ) from exc
            self._resource_manager = pyvisa.ResourceManager()
        return self._resource_manager

    def _require_instrument(self):
        if self._instrument is None:
            raise RuntimeError("Not connected to a VISA instrument.")
        return self._instrument

    def discover(self) -> list[str]:
        try:
            return list(self._manager().list_resources())
        except Exception as exc:
            raise RuntimeError(f"VISA discovery failed: {exc}") from exc

    def connect(self, resource: str) -> str:
        if not resource:
            raise ValueError("No VISA resource selected")
        try:
            instrument = self._manager().open_resource(resource)
            instrument.timeout = self._timeout_ms
            try:
                instrument.clear()
            except Exception:
                pass
            idn = instrument.query("*IDN?").strip()
        except Exception as exc:
            raise RuntimeError(f"VISA connection failed for {resource}: {exc}") from exc

        self._instrument = instrument
        self._connected = True
        self._device_id = resource
        self._device_name = idn or resource
        return self._device_name

    def disconnect(self):
        if self._instrument is not None:
            try:
                self._instrument.close()
            except Exception:
                pass
        self._instrument = None
        self._connected = False
        self._device_id = ""
        self._device_name = ""

    # -- low-level SCPI helpers --------------------------------------

    def _write(self, command: str):
        self._require_instrument().write(command)

    def _query(self, command: str) -> str:
        return str(self._require_instrument().query(command)).strip()

    @staticmethod
    def _on_off(state: bool) -> str:
        return "ON" if state else "OFF"

    # -- channel ------------------------------------------------------

    def set_channel_enabled(self, ch: str, state: bool):
        self.channels[ch]["enabled"] = state
        self._write(f":CHAN{ch}:DISP {self._on_off(state)}")

    def set_channel_visible(self, ch: str, state: bool):
        self.channels[ch]["visible"] = state
        self._write(f":CHAN{ch}:DISP {self._on_off(state)}")

    def set_channel_bandwidth(self, ch: str, bw: str):
        self.channels[ch]["bandwidth"] = bw
        if bw == "FULL":
            self._write(f":CHAN{ch}:BWL OFF")
        else:
            self._write(f":CHAN{ch}:BWL ON")

    def set_channel_coupling(self, ch: str, mode: str):
        self.channels[ch]["coupling"] = mode
        self._write(f":CHAN{ch}:COUP {mode}")

    def set_channel_volt_div(self, ch: str, vdiv: float):
        self.channels[ch]["volt_div"] = vdiv
        self._write(f":CHAN{ch}:SCAL {vdiv}")

    def set_channel_vert_offset(self, ch: str, offset: float):
        self.channels[ch]["vert_offset"] = offset
        self._write(f":CHAN{ch}:OFFS {offset}")

    def set_channel_name(self, ch: str, name: str):
        self.channels[ch]["name"] = name

    def set_channel_probe(self, ch: str, ratio: int):
        self.channels[ch]["probe"] = ratio
        self._write(f":CHAN{ch}:PROB {ratio}")

    def set_probe_all(self, ratio: int):
        for ch in self.channels:
            self.set_channel_probe(ch, ratio)

    def set_time_div(self, value: float):
        self.time_div = value
        self._write(f":TIM:SCAL {value}")

    def set_time_offset(self, value: float):
        self.time_offset = value
        self._write(f":TIM:OFFS {value}")

    # -- trigger ------------------------------------------------------

    def set_trigger(self, **kwargs):
        self.trigger.update(kwargs)
        if "source" in kwargs:
            self._write(f":TRIG:EDGE:SOUR {kwargs['source']}")
        if "slope" in kwargs:
            self._write(f":TRIG:EDGE:SLOP {kwargs['slope']}")
        if "level" in kwargs:
            self._write(f":TRIG:EDGE:LEV {kwargs['level']}")
        if "mode" in kwargs:
            self.set_trigger_mode(kwargs["mode"])

    def trigger_single(self):
        self._write(":SING")

    def trigger_force(self):
        self._write(":TFOR")

    def set_trigger_mode(self, mode: str):
        self.trigger["mode"] = mode
        self._write(f":TRIG:SWE {mode}")

    def get_trigger_status(self) -> str:
        return self._query(":TRIG:STAT?")

    # -- measurement --------------------------------------------------

    def read_metrics(self, channel: int, items: list[str]) -> dict[str, float]:
        results = {}
        for item in items:
            template = self.MEASUREMENT_COMMANDS.get(item)
            if not template:
                continue
            raw = self._query(template.format(channel=channel))
            results[item] = float(raw)
        return results

    def read_frequency(self, channel: int) -> float:
        raw = self._query(f":MEAS:FREQ? CHAN{channel}")
        return float(raw)

    # -- task ---------------------------------------------------------

    def start_task(self, task_type: str, steps: int = 10) -> bool:
        self._task_running = True
        self._write(":RUN")
        return True

    def cancel_task(self):
        self._task_running = False
        self._write(":STOP")

    def poll_task_progress(self) -> float:
        self._task_running = False
        return 100.0

    @property
    def task_running(self) -> bool:
        return self._task_running

    # -- waveform -----------------------------------------------------

    def generate_waveform(self, channel: int, num_points: int = 2000) -> tuple:
        instrument = self._require_instrument()
        try:
            self._write(f":WAV:SOUR CHAN{channel}")
            self._write(":WAV:FORM BYTE")
            self._write(":WAV:MODE NORM")
            preamble = self._query(":WAV:PRE?")
            raw_values = instrument.query_binary_values(
                ":WAV:DATA?", datatype="B", container=list)
        except Exception as exc:
            raise RuntimeError(
                "Waveform acquisition failed. This generic backend expects "
                "SCPI commands :WAV:SOUR, :WAV:FORM BYTE, :WAV:PRE?, and "
                f":WAV:DATA?. Instrument error: {exc}"
            ) from exc

        return self._convert_waveform(preamble, raw_values)

    @staticmethod
    def _convert_waveform(preamble: str, raw_values: list[int]) -> tuple:
        fields = [field.strip() for field in preamble.split(",")]
        if len(fields) < 10:
            raise ValueError(
                "Unsupported waveform preamble. Expected at least 10 comma-separated fields."
            )
        try:
            x_increment = float(fields[4])
            x_origin = float(fields[5])
            x_reference = float(fields[6])
            y_increment = float(fields[7])
            y_origin = float(fields[8])
            y_reference = float(fields[9])
        except ValueError as exc:
            raise ValueError(f"Invalid waveform preamble values: {preamble}") from exc

        times = [
            round((index - x_reference) * x_increment + x_origin, 12)
            for index in range(len(raw_values))
        ]
        volts = [
            round((value - y_reference) * y_increment + y_origin, 12)
            for value in raw_values
        ]
        return times, volts

    # -- file export helpers ------------------------------------------

    def save_screenshot(self, save_path: str, fmt: str = "PNG") -> str:
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt.upper() == "PNG":
            try:
                data = self._require_instrument().query_binary_values(
                    ":DISP:DATA? PNG", datatype="B", container=bytes)
                path.write_bytes(data)
                return str(path)
            except Exception:
                pass
        return super().save_screenshot(save_path, fmt=fmt)

    # -- console ------------------------------------------------------

    def exec_command(self, cmd: str) -> str:
        command = cmd.strip()
        if not command:
            return ""
        if "?" in command:
            return self._query(command)
        self._write(command)
        return "OK"


# ======================================================================
# Simulated Engine — fully functional demo backend
# ======================================================================

class SimulatedEngine(BaseEngine):
    """Simulated oscilloscope backend for demo / development use.

    Generates realistic multi-harmonic waveforms so the app is fully
    functional without real hardware.
    """

    def __init__(self):
        super().__init__()
        self.channels = {
            "1": {"name": "CH1", "enabled": True, "visible": True,
                  "bandwidth": "FULL", "coupling": "DC",
                  "volt_div": 2.0, "vert_offset": 0.0, "probe": 10},
            "2": {"name": "CH2", "enabled": True, "visible": True,
                  "bandwidth": "FULL", "coupling": "DC",
                  "volt_div": 1.0, "vert_offset": 0.0, "probe": 10},
            "3": {"name": "CH3", "enabled": False, "visible": False,
                  "bandwidth": "FULL", "coupling": "DC",
                  "volt_div": 5.0, "vert_offset": -2.0, "probe": 1},
            "4": {"name": "CH4", "enabled": False, "visible": False,
                  "bandwidth": "FULL", "coupling": "DC",
                  "volt_div": 5.0, "vert_offset": -6.0, "probe": 1},
        }
        self.time_div = 0.01
        self.time_offset = 0.03
        self.trigger = {
            "type": "EDGE", "source": "CH1", "slope": "RISE",
            "level": 0.0, "mode": "AUTO",
            "coupling": "DC", "noise_reject": "OFF",
            "holdoff_time": 100e-9, "holdoff_event": 0,
        }
        self._task_running = False
        self._task_progress = 0.0
        self._task_cancelled = False

    # -- connection ---------------------------------------------------

    @staticmethod
    def discover() -> list[str]:
        time.sleep(0.3)
        return [
            "USB0::0x1234::0x5678::DEMO0001::INSTR",
            "USB0::0x1234::0x5678::DEMO0002::INSTR",
            "TCPIP::192.168.1.100::INSTR",
        ]

    def connect(self, resource: str) -> str:
        if not resource:
            raise ValueError("No resource selected")
        time.sleep(0.4)
        self._connected = True
        self._device_id = resource
        self._device_name = f"SimScope,{resource.split('::')[-2]},v2.0.0"
        return self._device_name

    def disconnect(self):
        self._connected = False
        self._device_id = ""
        self._device_name = ""

    # -- channel ------------------------------------------------------

    def set_channel_enabled(self, ch: str, state: bool):
        self.channels[ch]["enabled"] = state
    def set_channel_visible(self, ch: str, state: bool):
        self.channels[ch]["visible"] = state
    def set_channel_bandwidth(self, ch: str, bw: str):
        self.channels[ch]["bandwidth"] = bw
    def set_channel_coupling(self, ch: str, mode: str):
        self.channels[ch]["coupling"] = mode
    def set_channel_volt_div(self, ch: str, vdiv: float):
        self.channels[ch]["volt_div"] = vdiv
    def set_channel_vert_offset(self, ch: str, offset: float):
        self.channels[ch]["vert_offset"] = offset
    def set_channel_name(self, ch: str, name: str):
        self.channels[ch]["name"] = name
    def set_channel_probe(self, ch: str, ratio: int):
        self.channels[ch]["probe"] = ratio
    def set_probe_all(self, ratio: int):
        for ch in self.channels:
            self.channels[ch]["probe"] = ratio
    def set_time_div(self, value: float):
        self.time_div = value
    def set_time_offset(self, value: float):
        self.time_offset = value

    # -- trigger ------------------------------------------------------

    def set_trigger(self, **kwargs):
        self.trigger.update(kwargs)
    def trigger_single(self):
        pass
    def trigger_force(self):
        pass
    def set_trigger_mode(self, mode: str):
        self.trigger["mode"] = mode
    def get_trigger_status(self) -> str:
        modes = ["WAIT", "READY", "TRIG'D", "STOP"]
        return random.choice(modes) if self._connected else "DISCONNECTED"

    # -- measurement --------------------------------------------------

    @staticmethod
    def read_metrics(channel: int, items: list[str]) -> dict[str, float]:
        time.sleep(0.15 * len(items))
        results = {}
        base_values = {
            "Vpp": (0.5, 5.0), "Vmax": (0.0, 3.3), "Vmin": (-3.3, 0.0),
            "Vavg": (-0.5, 1.5), "Vrms": (0.1, 2.0),
            "Freq": (50, 10_000_000), "Period": (1e-7, 0.02),
            "RiseTime": (1e-9, 1e-6), "FallTime": (1e-9, 1e-6),
            "PosWidth": (1e-8, 0.01), "NegWidth": (1e-8, 0.01),
            "DutyCycle": (10, 90),
            "Overshoot": (0, 15), "Undershoot": (0, 15),
            "PulseCount": (1, 1000),
        }
        for item in items:
            if item in base_values:
                lo, hi = base_values[item]
                results[item] = round(random.uniform(lo, hi), 6)
        return results

    @staticmethod
    def read_frequency(channel: int) -> float:
        return round(random.uniform(100, 10_000_000), 3)

    # -- task ---------------------------------------------------------

    def start_task(self, task_type: str, steps: int = 10) -> bool:
        if self._task_running:
            return False
        self._task_running = True
        self._task_cancelled = False
        self._task_progress = 0.0
        return True

    def cancel_task(self):
        self._task_cancelled = True

    def poll_task_progress(self) -> float:
        if not self._task_running:
            return 0.0
        if self._task_cancelled:
            self._task_running = False
            return -1.0
        increment = random.uniform(2, 8)
        self._task_progress = min(self._task_progress + increment, 100.0)
        time.sleep(0.15)
        if self._task_progress >= 100.0:
            self._task_running = False
        return self._task_progress

    @property
    def task_running(self) -> bool:
        return self._task_running

    # -- waveform -----------------------------------------------------

    @staticmethod
    def generate_waveform(channel: int, num_points: int = 2000) -> tuple:
        """Generate simulated oscilloscope waveform data.

        Returns (time_list_s, voltage_list_v).
        """
        time_div = 0.01
        t_start = -(time_div * 10 / 2)
        t_end = time_div * 10 / 2
        t = [t_start + i * (t_end - t_start) / num_points for i in range(num_points)]

        freq_base = 100 + channel * 233
        amp = 0.5 + channel * 0.3
        v = []
        for ti in t:
            noise = random.gauss(0, 0.02)
            val = (amp * math.sin(2 * math.pi * freq_base * ti)
                   + amp * 0.3 * math.sin(2 * math.pi * freq_base * 3 * ti)
                   + amp * 0.15 * math.sin(2 * math.pi * freq_base * 5 * ti)
                   + noise)
            v.append(round(val, 8))
        return t, v

    # -- file export helpers ------------------------------------------

    @staticmethod
    def save_waveform_csv(channel: int, save_path: str,
                          num_points: int = 2000) -> str:
        t, v = SimulatedEngine.generate_waveform(channel, num_points)
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Time (s)", "Voltage (V)"])
            for ti, vi in zip(t, v):
                writer.writerow([f"{ti:.10f}", f"{vi:.8f}"])
        return str(path)

    @staticmethod
    def save_screenshot(save_path: str, fmt: str = "PNG") -> str:
        fig, ax = plt.subplots(figsize=(12, 7), facecolor="#0A1D33")
        ax.set_facecolor("#0E2A45")
        t = [i * 0.001 for i in range(1000)]
        for ch, color in enumerate(["#00E6FF", "#FFB800", "#FF5E5E", "#5EFF5E"], 1):
            amp = 0.5 + ch * 0.3
            freq = 100 + ch * 233
            v = [amp * math.sin(2 * math.pi * freq * ti) for ti in t]
            ax.plot(t, v, color=color, linewidth=1.2, label=f"CH{ch}")
        ax.set_xlabel("Time (s)", color="#A8DDFF")
        ax.set_ylabel("Voltage (V)", color="#A8DDFF")
        ax.tick_params(colors="#A8DDFF")
        ax.grid(True, alpha=0.2, color="#00E6FF")
        ax.legend(loc="upper right")
        ax.set_title("Simulated Screenshot", color="#00E6FF", fontsize=14)
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, facecolor=fig.get_facecolor(), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    # -- console ------------------------------------------------------

    def exec_command(self, cmd: str) -> str:
        cmd_upper = cmd.strip().upper()
        if "?" in cmd_upper:
            if "IDN" in cmd_upper:
                return self._device_name
            if "STATUS" in cmd_upper:
                return "OK"
            if "TEMP" in cmd_upper:
                return f"{random.uniform(25, 55):.1f}C"
            return "0.000"
        return "OK"
