"""Regression suite: does the watchdog still do what it promises?

Run:  python -m blackbox.regress
Prints a pass/fail table and exits non-zero if anything fails. Run it after
every change to the watchdog or its thresholds.
"""

import glob
import os
import random
import sys
from typing import List, Tuple

from . import faults
from .log import frame_times, read_events
from .replay import first_time, mode_entries, replay, trace_hash
from .timing import percentile
from .watchdog import Config, Mode

TICK = 0.05
CFG = Config()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = sorted(glob.glob(os.path.join(ROOT, "data", "dronefollow_frames", "*.jsonl")))

Row = Tuple[str, bool, str]


def _last_before(ts: List[float], t: float) -> float:
    return max(x for x in ts if x < t)


def freeze_hover_latency(trials: int = 40, seed: int = 1) -> Row:
    rng = random.Random(seed)
    base = faults.synthetic_stream(60)
    lat = []
    for _ in range(trials):
        start = rng.uniform(5, 50)
        dur = rng.uniform(0.35, 1.5)  # all shorter than land_s
        ts = faults.freeze(base, start, dur)
        tr = replay(ts, TICK, CFG, end=base[-1])
        last_good = _last_before(base, start)
        t_hover = first_time(tr, Mode.HOVER, after=last_good)
        lat.append(float("inf") if t_hover is None else t_hover - last_good)
    limit = CFG.hover_s + TICK + 1e-9
    ok = sum(l <= limit for l in lat)
    return ("stall >= 0.35 s -> HOVER within hover_s + 1 tick (40 trials)", ok == trials,
            f"{ok}/{trials} pass; latency p50 {1000*percentile(lat,50):.0f} ms, max {1000*max(lat):.0f} ms, limit {1000*limit:.0f} ms")


def freeze_land_latency(trials: int = 10, seed: int = 2) -> Row:
    rng = random.Random(seed)
    base = faults.synthetic_stream(60)
    lat = []
    for _ in range(trials):
        start = rng.uniform(5, 40)
        ts = faults.freeze(base, start, 4.0)
        tr = replay(ts, TICK, CFG, end=base[-1])
        last_good = _last_before(base, start)
        t_land = first_time(tr, Mode.LAND, after=last_good)
        lat.append(float("inf") if t_land is None else t_land - last_good)
    limit = CFG.land_s + TICK + 1e-9
    ok = sum(l <= limit for l in lat)
    return ("stall of 4 s -> LAND within land_s + 1 tick (10 trials)", ok == trials,
            f"{ok}/{trials} pass; max {1000*max(lat):.0f} ms, limit {1000*limit:.0f} ms")


def land_is_latched() -> Row:
    base = faults.synthetic_stream(30)
    tr = replay(faults.freeze(base, 10, 3.0), TICK, CFG, end=base[-1])
    t_land = first_time(tr, Mode.LAND)
    after = [r for r in tr if t_land is not None and r["t"] >= t_land]
    ok = t_land is not None and all(r["mode"] == "LAND" for r in after)
    return ("LAND stays latched after video returns", ok, f"landed at {t_land}")


def recovery_after_short_stall() -> Row:
    base = faults.synthetic_stream(30)
    ts = faults.freeze(base, 10, 0.5)
    tr = replay(ts, TICK, CFG, end=base[-1])
    resume = min(t for t in ts if t > 10)
    back = first_time(tr, Mode.NORMAL, after=resume)
    limit = CFG.recover_s + 2 * TICK + 0.2
    ok = back is not None and back - resume <= limit and not mode_entries(tr, Mode.LAND)
    return ("0.5 s stall -> HOVER then back to NORMAL, never LAND", ok,
            f"back to NORMAL {None if back is None else round(back-resume,2)} s after video resumed (limit {limit:.2f})")


def clean_stream_no_trips() -> Row:
    base = faults.synthetic_stream(60)
    tr = replay(base, TICK, CFG)
    bad = mode_entries(tr, Mode.HOVER) + mode_entries(tr, Mode.LAND)
    return ("clean 20 fps stream -> no HOVER or LAND", not bad, f"{len(bad)} trips")


def reverse_limit() -> Row:
    base = faults.synthetic_stream(10)
    tr = replay(base, TICK, CFG, cmd_fn=lambda t: (0, -30, 0, 0))
    t = first_time(tr, Mode.HOVER)
    ok = t is not None and t <= CFG.max_reverse_s + 2 * TICK + 1e-9
    zeros = all(r["cmd"] == [0, 0, 0, 0] for r in tr if t is not None and r["t"] >= t)
    return ("sustained backward command -> HOVER within max_reverse_s", ok and zeros,
            f"HOVER at {t} s (limit {CFG.max_reverse_s + 2*TICK:.2f})")


def reverse_releases() -> Row:
    base = faults.synthetic_stream(10)
    tr = replay(base, TICK, CFG, cmd_fn=lambda t: (0, -30, 0, 0) if t < 3 else (0, 20, 0, 0))
    late = [r for r in tr if r["t"] > 3.2]
    ok = all(r["mode"] == "NORMAL" and r["cmd"] == [0, 20, 0, 0] for r in late)
    return ("forward command after reverse limit -> NORMAL again", ok, "")


def latency_step_triggers_hover() -> Row:
    base = faults.synthetic_stream(30)
    ts = faults.delay_step(base, 10, 0.6)
    tr = replay(ts, TICK, CFG, end=base[-1] + 1)
    return ("0.6 s latency step -> HOVER", bool(mode_entries(tr, Mode.HOVER)), "")


def determinism() -> Row:
    if not REAL:
        return ("replay is deterministic on real logs", False, "no real logs found in data/")
    same = 0
    for p in REAL:
        ts, _ = _load(p)
        a = trace_hash(replay(ts, TICK, CFG))
        b = trace_hash(replay(ts, TICK, CFG))
        same += a == b
    return ("replay is deterministic (identical hash) on real logs", same == len(REAL), f"{same}/{len(REAL)} logs")


def _load(p):
    ev = list(read_events(p))
    end = next((e["loop_end"] for e in ev if e["type"] == "meta" and "loop_end" in e), None)
    return frame_times(ev), end


def real_logs_never_land() -> Row:
    lands = 0
    hovers = 0
    for p in REAL:
        ts, end = _load(p)
        if end is not None:
            continue  # the stream-stop log is checked separately
        tr = replay(ts, TICK, CFG)
        lands += len(mode_entries(tr, Mode.LAND))
        hovers += len(mode_entries(tr, Mode.HOVER))
    return ("real Tello logs: no LAND at default land_s (stalls survived)", lands == 0,
            f"{lands} LAND, {hovers} HOVER entries across the logs with no stream stop")


def real_stream_stop_lands() -> Row:
    """Oct 10 grounded test: the stream stopped for good at about 148.6 s while the loop ran on."""
    for p in REAL:
        ts, end = _load(p)
        if end is None:
            continue
        tr = replay(ts, TICK, CFG, end=end)
        t_land = first_time(tr, Mode.LAND)
        lat = None if t_land is None else t_land - ts[-1]
        ok = lat is not None and lat <= CFG.land_s + TICK + 1e-9
        return ("real stream stop (ladder log, no frames for 34 s) -> LAND within land_s + 1 tick", ok,
                f"last frame {ts[-1]:.1f} s, LAND after {None if lat is None else round(lat,2)} s")
    return ("real stream stop -> LAND", False, "ladder log missing")


def run() -> List[Row]:
    return [clean_stream_no_trips(), freeze_hover_latency(), freeze_land_latency(), land_is_latched(),
            recovery_after_short_stall(), reverse_limit(), reverse_releases(),
            latency_step_triggers_hover(), determinism(), real_logs_never_land(), real_stream_stop_lands()]


def main() -> int:
    rows = run()
    print("| Check | Result | Detail |\n|---|---|---|")
    for name, ok, detail in rows:
        print(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    return 0 if all(ok for _, ok, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
