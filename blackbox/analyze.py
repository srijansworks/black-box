"""Analyze frame-arrival logs.

    python -m blackbox.analyze data/dronefollow_frames/*.jsonl
    python -m blackbox.analyze data/dronefollow_frames/*.jsonl --suggest
    python -m blackbox.analyze data/dronefollow_frames/*.jsonl --plot docs/figures/gaps.png
"""

import argparse
import os
import sys

from .log import frame_times, read_events
from .timing import gaps, percentile, stalls, summarize


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--stall", type=float, default=0.3, help="stall threshold in seconds")
    ap.add_argument("--skip-start", type=float, default=0.0, help="ignore the first N seconds (startup)")
    ap.add_argument("--suggest", action="store_true", help="suggest watchdog thresholds from the data")
    ap.add_argument("--plot", help="write a gap histogram PNG here")
    a = ap.parse_args(argv)

    all_gaps, all_stall_d = [], []
    print("| Log | Frames | Seconds | FPS | Gap p50 / p90 / p99 / max (ms) | Stalls >%d ms | Stalls/min (95%% CI) |" % (a.stall * 1000))
    print("|---|---|---|---|---|---|---|")
    for p in a.logs:
        ts = frame_times(read_events(p))
        ts = [t for t in ts if t >= ts[0] + a.skip_start]
        s = summarize(ts, a.stall)
        all_gaps += gaps(ts)
        all_stall_d += [d for _, d in stalls(ts, a.stall)]
        lo, hi = s["stalls_per_min_ci95"]
        print(f"| {os.path.basename(p)} | {s['frames']} | {s['seconds']} | {s['fps']} | "
              f"{s['gap_ms_p50']} / {s['gap_ms_p90']} / {s['gap_ms_p99']} / {s['gap_ms_max']} | "
              f"{s['stalls']} | {s['stalls_per_min']} ({lo} to {hi}) |")

    if a.suggest and all_gaps:
        worst = max(all_gaps)
        print("\nSuggested thresholds from these logs (check them against your safety margin):")
        print(f"  degraded_s >= p99 gap       = {percentile(all_gaps, 99):.3f}  (so normal jitter does not slow the drone)")
        print(f"  hover_s    = {a.stall:.2f}  (current dronefollow stale limit; {len(all_stall_d)} stalls exceed it)")
        print(f"  land_s     > longest gap    = {worst:.2f} s; with margin x2 = {2*worst:.2f} s")
        print("  Raising land_s tolerates longer stalls; lowering it lands sooner. That is a safety decision, not a data one.")

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
        ms = [1000 * g for g in all_gaps]
        ax[0].hist(ms, bins=60, color="#1f6feb")
        ax[0].set_yscale("log")
        ax[0].set_xlabel("gap between new frames (ms)")
        ax[0].set_ylabel("count (log)")
        ax[0].axvline(1000 * a.stall, color="#d1242f", ls="--", label="stall limit")
        ax[0].legend()
        ax[1].hist(sorted(all_stall_d), bins=15, color="#d1242f")
        ax[1].set_xlabel("stall duration (s)")
        ax[1].set_ylabel("count")
        fig.tight_layout()
        os.makedirs(os.path.dirname(a.plot) or ".", exist_ok=True)
        fig.savefig(a.plot, dpi=140)
        print(f"\nwrote {a.plot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
