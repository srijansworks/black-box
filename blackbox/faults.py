"""Fault injection: damage a list of frame-arrival times in software.

Each function takes sorted arrival times (seconds) and returns a new list.
This tests the watchdog on the ground, with no drone and no risk.
"""

import random
from typing import List, Sequence


def freeze(ts: Sequence[float], start: float, dur: float) -> List[float]:
    """No new frames in [start, start + dur): a stall."""
    return [t for t in ts if not (start <= t < start + dur)]


def delay_step(ts: Sequence[float], start: float, d: float) -> List[float]:
    """From `start` on, every frame arrives d seconds later (a latency step).
    Creates one gap of about d, then normal flow resumes."""
    return sorted(t + d if t >= start else t for t in ts)


def drop_every(ts: Sequence[float], n: int) -> List[float]:
    """Drop every n-th frame."""
    return [t for i, t in enumerate(ts) if (i + 1) % n]


def jitter(ts: Sequence[float], sigma: float, seed: int = 0) -> List[float]:
    """Add Gaussian timing noise (kept in order)."""
    rng = random.Random(seed)
    return sorted(max(0.0, t + rng.gauss(0, sigma)) for t in ts)


def synthetic_stream(seconds: float, fps: float = 20.0) -> List[float]:
    n = int(seconds * fps)
    return [i / fps for i in range(n + 1)]
