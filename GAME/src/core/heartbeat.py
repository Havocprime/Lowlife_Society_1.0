# GAME/src/core/heartbeat.py
from __future__ import annotations
import sys
import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from collections import deque

log = logging.getLogger("heartbeat")

# Safe in most terminals; for pure ASCII use: ("-","\\","|","/")
SPINNER = ("‹","™","¸","´","¦","‡")

@dataclass
class HeartbeatConfig:
    interval_s: float = 0.5           # how often to draw the spinner
    log_every_n: int = 10             # how many draws between INFO logs
    label: str = "HB"                 # short label at start of line
    enable_spinner: bool = True       # disable to silence the single-line spinner
    enable_logging: bool = True       # disable to silence periodic INFO logs

    # --- New options ---
    stall_warn_ms: int = 1000         # warn if event-loop lag exceeds this (ms); set 0 to disable
    work_window_s: int = 60           # rolling window for work-per-minute counter
    write_probe_every_n: int = 0      # write heartbeat probe file every N ticks; 0 = disabled
    probe_path: Optional[str] = None  # e.g., "status/heartbeat.txt" (dir must exist or be creatable)

class Heartbeat:
    """
    Terminal spinner + periodic logs + loop-lag detector + idle/work telemetry.
    Backward compatible with the original API (start/stop), with extra helpers:
      - mark_activity(): record "something meaningful just happened"
      - inc_work(n=1): bump rolling work counter (for commands/jobs finished)
      - set_label(str): change the spinner label at runtime
    """
    def __init__(self, config: HeartbeatConfig | None = None):
        self.cfg = config or HeartbeatConfig()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._tick = 0

        # --- Telemetry state ---
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        now = (loop.time() if loop else 0.0)
        self.last_activity = now                       # monotonic seconds
        self._work_ts = deque()                        # monotonic timestamps of completed work
        self._loop = loop                              # cached; refreshed in start()

    # -------- Public helpers --------
    def mark_activity(self) -> None:
        """Record that 'useful activity' just occurred (resets idle timer)."""
        try:
            loop = self._loop or asyncio.get_running_loop()
            self.last_activity = loop.time()
            self._loop = loop
        except RuntimeError:
            pass

    def inc_work(self, n: int = 1) -> None:
        """Increment rolling work counter (call when a command/job completes)."""
        try:
            loop = self._loop or asyncio.get_running_loop()
            now = loop.time()
            for _ in range(max(1, n)):
                self._work_ts.append(now)
            self._loop = loop
        except RuntimeError:
            pass

    def set_label(self, label: str) -> None:
        """Change the spinner label at runtime."""
        self.cfg.label = str(label)

    @property
    def tick(self) -> int:
        return self._tick

    # -------- Lifecycle --------
    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        # refresh loop reference
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._task = asyncio.create_task(self._runner(), name="heartbeat")

    async def stop(self):
        if not self._task:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=2)
        except asyncio.TimeoutError:
            log.warning("Heartbeat task didn't stop cleanly.")
        finally:
            self._task = None
            # ensure we end the spinner line cleanly
            if self.cfg.enable_spinner:
                try:
                    sys.stdout.write("\r" + " " * 120 + "\r")
                    sys.stdout.flush()
                except Exception:
                    pass

    # -------- Internal --------
    def _prune_work(self, now: float) -> int:
        """Prune work timestamps older than window; return count remaining."""
        window = max(1, int(self.cfg.work_window_s))
        cutoff = now - window
        dq = self._work_ts
        while dq and dq[0] < cutoff:
            dq.popleft()
        return len(dq)

    async def _runner(self):
        loop = asyncio.get_running_loop()
        self._loop = loop
        spinner_i = 0
        last = loop.time()

        # probe writer setup
        probe_every = int(self.cfg.write_probe_every_n or 0)
        probe_path = (self.cfg.probe_path or "").strip()
        probe_enabled = probe_every > 0 and bool(probe_path)

        while not self._stop.is_set():
            await asyncio.sleep(self.cfg.interval_s)
            now = loop.time()
            expected = last + self.cfg.interval_s
            loop_lag = max(0.0, now - expected)  # seconds
            last = now

            self._tick += 1

            # stall detector
            if self.cfg.stall_warn_ms and (loop_lag * 1000.0) >= self.cfg.stall_warn_ms:
                log.warning("heartbeat stall: event_loop_lag_ms=%d (tick=%d)",
                            int(loop_lag * 1000), self._tick)

            # metrics
            idle_s = int(max(0, now - (self.last_activity or now)))
            work_cnt = self._prune_work(now)

            # single-line spinner in the terminal
            if self.cfg.enable_spinner:
                glyph = SPINNER[spinner_i]
                spinner_i = (spinner_i + 1) % len(SPINNER)
                # Example line: LOWLIFE â³ 12s âŒ work/60s=3  â ™  tick=127  lag=2ms
                msg = (
                    f"{self.cfg.label} â³{idle_s:>3}s âŒ work/60s={work_cnt:<3d}  "
                    f"{glyph}  tick={self._tick}  lag={int(loop_lag*1000)}ms"
                )
                try:
                    sys.stdout.write("\r" + msg[:160])  # trim long lines
                    sys.stdout.flush()
                except Exception:
                    # If stdout is redirected or not a TTY, just skip drawing
                    pass

            # periodic structured log line
            if self.cfg.enable_logging and (self._tick % self.cfg.log_every_n == 0):
                log.info(
                    "heartbeat pulse | tick=%d | idle_s=%d | work_60s=%d | event_loop_lag_ms=%d",
                    self._tick, idle_s, work_cnt, int(loop_lag * 1000)
                )

            # optional probe file writer
            if probe_enabled and (self._tick % probe_every == 0):
                try:
                    from pathlib import Path
                    p = Path(probe_path)
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(f"{int(now)} {self._tick} idle={idle_s} work60={work_cnt} lag_ms={int(loop_lag*1000)}\n")
                except Exception:
                    # don't crash heartbeat for IO hiccups
                    pass
