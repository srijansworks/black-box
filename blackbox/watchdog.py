"""Safety watchdog: a small state machine that overrides the follower's commands.

Modes
    NORMAL    video is fresh: commands pass through unchanged
    DEGRADED  video a bit late: commands are scaled down (slower, safer)
    HOVER     video stale or reverse limit hit: command forced to zero
    LAND      video gone for too long or battery low: land and stay landing (latched)

A state machine is a list of modes plus the exact conditions that switch
between them. This one is a pure function of its inputs and its own memory:
same inputs in the same order always give the same decisions, which is what
makes replay testing possible.

rc command = (lr, fb, ud, yaw), each -100..100 as the Tello expects.
fb < 0 means backward. This is the failure that put the follower into a wall
on Sep 28, so sustained reverse is limited.

Thresholds are starting values. Re-derive them from your own data with
`python -m blackbox.analyze --suggest`.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

Cmd = Tuple[int, int, int, int]
ZERO: Cmd = (0, 0, 0, 0)


class Mode(Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    HOVER = "HOVER"
    LAND = "LAND"


@dataclass(frozen=True)
class Config:
    degraded_s: float = 0.15   # video older than this: slow down
    hover_s: float = 0.30      # matches dronefollow's existing stale-frame limit
    land_s: float = 2.0        # video gone this long: land. Longest stall in the
                               # four real logs was about 1.1 s; see docs/RESULTS.md
    recover_s: float = 0.5     # video must stay fresh this long before leaving HOVER
    degraded_scale: float = 0.5
    max_reverse_s: float = 1.0  # sustained backward command limit
    reverse_min: int = 5        # fb below -reverse_min counts as "reversing"
    min_battery: int = 15


@dataclass(frozen=True)
class Decision:
    mode: Mode
    cmd: Cmd
    reason: str
    age_s: float


class Watchdog:
    def __init__(self, config: Config = Config()):
        self.cfg = config
        self.mode = Mode.NORMAL
        self._t_start: Optional[float] = None
        self._fresh_since: Optional[float] = None
        self._reverse_since: Optional[float] = None
        self._reverse_blocked = False

    def step(self, now: float, last_frame_t: Optional[float], cmd: Cmd = ZERO,
             battery: Optional[int] = None) -> Decision:
        c = self.cfg
        if self._t_start is None:
            self._t_start = now
        ref = last_frame_t if last_frame_t is not None else self._t_start
        age = max(0.0, now - ref)

        # LAND is latched: once decided, nothing brings the drone back.
        if self.mode is Mode.LAND:
            return Decision(Mode.LAND, ZERO, "latched", age)
        if battery is not None and battery <= c.min_battery:
            self.mode = Mode.LAND
            return Decision(Mode.LAND, ZERO, "battery", age)
        if age > c.land_s:
            self.mode = Mode.LAND
            return Decision(Mode.LAND, ZERO, "video_lost", age)

        # Track how long video has been fresh (for recovery).
        if age <= c.hover_s:
            if self._fresh_since is None:
                self._fresh_since = now
        else:
            self._fresh_since = None

        # Reverse limit: sustained backward command.
        lr, fb, ud, yaw = cmd
        if fb < -c.reverse_min:
            if self._reverse_since is None:
                self._reverse_since = now
            if now - self._reverse_since > c.max_reverse_s:
                self._reverse_blocked = True
        else:
            self._reverse_since = None
            self._reverse_blocked = False

        # Stale video: hover until it has been fresh for recover_s.
        if age > c.hover_s:
            self.mode = Mode.HOVER
            return Decision(Mode.HOVER, ZERO, "stale_video", age)
        if self.mode is Mode.HOVER and self._fresh_since is not None \
                and now - self._fresh_since < c.recover_s:
            return Decision(Mode.HOVER, ZERO, "recovering", age)

        if self._reverse_blocked:
            self.mode = Mode.HOVER
            return Decision(Mode.HOVER, ZERO, "reverse_limit", age)

        if age > c.degraded_s:
            self.mode = Mode.DEGRADED
            s = c.degraded_scale
            return Decision(Mode.DEGRADED, (int(lr * s), int(fb * s), int(ud * s), int(yaw * s)),
                            "late_video", age)

        self.mode = Mode.NORMAL
        return Decision(Mode.NORMAL, cmd, "ok", age)
