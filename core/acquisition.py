"""Live waveform acquisition engine.

Runs in a background thread, continuously fetching waveform data from
the backend engine and pushing it to a thread-safe queue for the UI.
"""

import queue
import threading
import time
from dataclasses import dataclass, field


@dataclass
class AcquisitionFrame:
    """One frame of waveform data for a single channel."""
    channel: int
    time_data: list[float]
    voltage_data: list[float]
    timestamp: float = 0.0


@dataclass
class AcquisitionStatus:
    """Snapshot of acquisition state for the UI to display."""
    mode: str = "STOP"        # RUN, STOP, SINGLE
    fps: float = 0.0
    frame_count: int = 0


class LiveAcquisition:
    """Background waveform acquisition thread.

    Parameters
    ----------
    engine : BaseEngine
        The backend engine that provides ``generate_waveform()``.
    frame_queue : queue.Queue
        Thread-safe queue where acquired frames are placed.
    fps : int
        Target frames per second (default 10).
    """

    def __init__(self, engine, frame_queue: queue.Queue, fps: int = 10):
        self._engine = engine
        self._queue = frame_queue
        self._fps = fps
        self._interval = 1.0 / fps

        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._mode = "STOP"      # RUN | STOP | SINGLE
        self._running = False

        # stats
        self._frame_count = 0
        self._fps_smoothed = 0.0
        self._last_stats_time = time.monotonic()

    # -- public API ---------------------------------------------------

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start_run(self):
        """Begin continuous acquisition."""
        with self._lock:
            self._mode = "RUN"
            self._running = True
        self._ensure_thread()

    def start_single(self):
        """Capture exactly one frame then stop."""
        with self._lock:
            self._mode = "SINGLE"
            self._running = True
        self._ensure_thread()

    def stop(self):
        """Stop acquisition."""
        with self._lock:
            self._running = False
            self._mode = "STOP"

    def get_status(self) -> AcquisitionStatus:
        with self._lock:
            return AcquisitionStatus(
                mode=self._mode,
                fps=round(self._fps_smoothed, 1),
                frame_count=self._frame_count,
            )

    def set_fps(self, fps: int):
        with self._lock:
            self._fps = max(1, min(fps, 60))
            self._interval = 1.0 / self._fps

    # -- internals ----------------------------------------------------

    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def _run_loop(self):
        while True:
            with self._lock:
                if not self._running:
                    break
                mode = self._mode
                interval = self._interval

            # Acquire one frame per enabled/visible channel
            for ch_str, ch_info in self._engine.channels.items():
                if not (ch_info.get("enabled") and ch_info.get("visible")):
                    continue
                try:
                    ch = int(ch_str)
                    t, v = self._engine.generate_waveform(ch, num_points=2000)
                    frame = AcquisitionFrame(
                        channel=ch,
                        time_data=t,
                        voltage_data=v,
                        timestamp=time.monotonic(),
                    )
                    self._queue.put(frame)
                except Exception:
                    # Don't let one bad channel kill the loop
                    pass

            self._update_stats()

            # SINGLE mode: grab one frame then stop
            if mode == "SINGLE":
                with self._lock:
                    self._running = False
                    self._mode = "STOP"
                break

            time.sleep(interval)

    def _update_stats(self):
        self._frame_count += 1
        now = time.monotonic()
        elapsed = now - self._last_stats_time
        if elapsed >= 1.0:
            self._fps_smoothed = self._frame_count / elapsed
            self._frame_count = 0
            self._last_stats_time = now
