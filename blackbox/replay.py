"""Deterministic replay: run recorded frame arrivals through the watchdog.

The watchdog is ticked at a fixed rate (the follower's loop rate). At each
tick it is told the arrival time of the newest frame seen so far. Same log,
same config, same tick: identical decisions, byte for byte.
"""

import bisect
import hashlib
import json
from typing import Callable, List, Optional, Sequence

from .watchdog import Cmd, Config, Decision, Mode, Watchdog, ZERO


def replay(frame_ts: Sequence[float], tick_s: float = 0.05, config: Config = Config(),
           cmd_fn: Optional[Callable[[float], Cmd]] = None,
           end: Optional[float] = None) -> List[dict]:
    wd = Watchdog(config)
    end = frame_ts[-1] if end is None else end
    start = frame_ts[0]
    trace = []
    k = 0
    while True:
        now = round(start + k * tick_s, 9)
        if now > end:
            break
        i = bisect.bisect_right(frame_ts, now) - 1
        last = frame_ts[i] if i >= 0 else None
        d: Decision = wd.step(now, last, cmd_fn(now) if cmd_fn else ZERO)
        trace.append({"t": now, "mode": d.mode.value, "reason": d.reason,
                      "cmd": list(d.cmd), "age": round(d.age_s, 6)})
        k += 1
    return trace


def trace_hash(trace: List[dict]) -> str:
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest()


def first_time(trace: List[dict], mode: Mode, after: float = 0.0) -> Optional[float]:
    for r in trace:
        if r["t"] >= after and r["mode"] == mode.value:
            return r["t"]
    return None


def mode_entries(trace: List[dict], mode: Mode) -> List[float]:
    """Times at which the watchdog newly entered `mode`."""
    out, prev = [], None
    for r in trace:
        if r["mode"] == mode.value and prev != mode.value:
            out.append(r["t"])
        prev = r["mode"]
    return out
