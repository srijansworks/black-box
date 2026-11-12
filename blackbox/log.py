"""Flight recorder: one JSON line per event, one monotonic clock.

Why monotonic: time.monotonic() only moves forward and never jumps when the
computer corrects its clock. Wall-clock time is stored once in the meta line
so a run can still be matched to a calendar date.

Event types the follower should log:
    frame  a NEW video frame reached the loop          (fields: any extras)
    state  a Tello state packet arrived                (fields: raw values)
    cmd    an rc command was sent                      (fields: lr, fb, ud, yaw)
    det    detector output                             (fields: free-form)
    wd     watchdog mode change                        (fields: mode, reason)
"""

import json
import time
from typing import Iterator, List


class EventLogger:
    def __init__(self, path: str, meta: dict | None = None):
        self._f = open(path, "a", buffering=1)  # line buffered: survives a crash
        self._t0 = time.monotonic()
        self._write({"type": "meta", "t": 0.0, "wall": time.time(), **(meta or {})})

    def _write(self, d: dict) -> None:
        self._f.write(json.dumps(d, separators=(",", ":")) + "\n")

    def log(self, type_: str, **fields) -> None:
        self._write({"type": type_, "t": round(time.monotonic() - self._t0, 6), **fields})

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_events(path: str) -> Iterator[dict]:
    """Yield events. Also reads two older dronefollow formats: frames.jsonl
    (lines like {"i": 3, "t": 0.5787}) and runs/*.jsonl loop rows (new frames
    are rows whose video.new is true). Both become frame events."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue  # a crash can leave a half-written last line
            if "_meta" in d:
                continue
            if "type" not in d and "t" in d and "i" in d:
                d = {"type": "frame", "t": d["t"], "i": d["i"]}
            if "type" not in d and "video" in d and "t" in d:
                # dronefollow runs/*.jsonl: one row per loop; video.new marks a new frame
                if not (isinstance(d["video"], dict) and d["video"].get("new")):
                    continue
                d = {"type": "frame", "t": d["t"]}
            if "type" in d and "t" in d:
                yield d


def frame_times(events) -> List[float]:
    return sorted(e["t"] for e in events if e["type"] == "frame")
