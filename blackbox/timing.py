"""Frame-arrival timing: gaps, stalls, and honest uncertainty on stall rates."""

import math
from typing import Dict, List, Sequence, Tuple


def gaps(ts: Sequence[float]) -> List[float]:
    return [b - a for a, b in zip(ts, ts[1:])]


def percentile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    s = sorted(xs)
    if not s:
        raise ValueError("empty")
    k = (len(s) - 1) * q / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _poisson_cdf(k: int, lam: float) -> float:
    return sum(math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(k + 1)) if lam > 0 else 1.0


def poisson_ci(k: int, conf: float = 0.95) -> Tuple[float, float]:
    """Exact (Garwood) confidence interval for a Poisson count k.
    Returns (low, high) expected counts. Found by bisection so no scipy needed."""
    a = (1 - conf) / 2

    def bisect(f, lo, hi):
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    hi_bound = 10.0 + 10 * k
    low = 0.0 if k == 0 else bisect(lambda lam: 1 - _poisson_cdf(k - 1, lam) >= a, 0.0, hi_bound)
    high = bisect(lambda lam: _poisson_cdf(k, lam) <= a, 0.0, hi_bound)
    return low, high


def stalls(ts: Sequence[float], stall_s: float = 0.3) -> List[Tuple[float, float]]:
    """(start_time, duration) of every gap longer than stall_s."""
    return [(a, b - a) for a, b in zip(ts, ts[1:]) if b - a > stall_s]


def summarize(ts: Sequence[float], stall_s: float = 0.3) -> Dict:
    g = gaps(ts)
    dur = ts[-1] - ts[0] if len(ts) > 1 else 0.0
    st = stalls(ts, stall_s)
    lo, hi = poisson_ci(len(st))
    per_min = 60.0 / dur if dur > 0 else float("nan")
    return {
        "frames": len(ts),
        "seconds": round(dur, 2),
        "fps": round(len(ts) / dur, 2) if dur else None,
        "gap_ms_p50": round(1000 * percentile(g, 50), 1),
        "gap_ms_p90": round(1000 * percentile(g, 90), 1),
        "gap_ms_p99": round(1000 * percentile(g, 99), 1),
        "gap_ms_max": round(1000 * max(g), 1),
        "stalls": len(st),
        "stalls_per_min": round(len(st) * per_min, 2),
        "stalls_per_min_ci95": (round(lo * per_min, 2), round(hi * per_min, 2)),
        "stall_durations_s": [round(d, 3) for _, d in st],
    }
