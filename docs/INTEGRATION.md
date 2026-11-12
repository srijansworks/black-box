# Attaching black-box to the follower (untested on hardware)

I did not edit `dronefollow`. This is what to add, and the order to test it in.

1. **Log**, in the main loop of `follow_person.py` (or `follow_tello.py`):
```python
from blackbox.log import EventLogger
from blackbox.watchdog import Watchdog, Config

lg = EventLogger("logs/run-YYYYMMDD-HHMM.jsonl", {"battery": battery, "room": "...", "note": "..."})
wd = Watchdog(Config())
last_frame_t = None
# each loop iteration, with t = time.monotonic():
#   if status.new:            lg.log("frame");  last_frame_t = t
#   after each state read:    lg.log("state", **raw_state_fields)
#   after computing cmd:      d = wd.step(t, last_frame_t, cmd, battery); cmd = d.cmd
#   on mode change:           lg.log("wd", mode=d.mode.value, reason=d.reason)
#   when sending rc:          lg.log("cmd", lr=cmd[0], fb=cmd[1], ud=cmd[2], yaw=cmd[3])
#   if d.mode.value == "LAND": call the existing landing routine
```
`last_frame_t` and `t` must come from the same clock (`time.monotonic()`), not `time.time()`.

2. **Order of testing:** (a) ground only, drone on a table, props off the path, watch `wd` lines in the log; (b) one hover flight (takeoff, 30 s hover about 1 m up, land) with an adult present; (c) only then a follow run. Do not use the old `--auto --fly` command until the reverse limit has been seen to trigger in (a).
2b. **Reverse check on the ground:** feed `cmd = (0, -30, 0, 0)` for 3 s with fresh video and confirm the log shows HOVER with reason `reverse_limit` near 1 s.
3. **Re-derive thresholds** from your own logs: `python3 -m blackbox.analyze logs/*.jsonl --suggest`, then change `Config` and rerun `python3 -m blackbox.regress`.
