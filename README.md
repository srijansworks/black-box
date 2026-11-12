# black-box

Flight recorder, safety watchdog and failure analysis for the Tello follower (`~/Documents/Projects/dronefollow`).
Plan and reasoning: Obsidian vault, `Claude/New Focus Project/Research Report.md`.

**Status (2026-11-12): software built and tested on existing logs. Not flown. Not published.** See [docs/RESULTS.md](docs/RESULTS.md).

## What is here
- `blackbox/log.py`: one-line-per-event JSON logger on a monotonic clock; also reads old dronefollow log formats.
- `blackbox/timing.py`, `analyze.py`: gap, stall and stalls-per-minute statistics with exact 95% confidence intervals; threshold suggestions; gap plot.
- `blackbox/watchdog.py`: NORMAL / DEGRADED / HOVER / LAND state machine, with a reverse-command limit.
- `blackbox/faults.py`: freeze, latency step, drop and jitter fault injection.
- `blackbox/replay.py`: deterministic replay of recorded frame arrivals through the watchdog.
- `blackbox/regress.py`: pass/fail table (10 checks + real stream-stop check).
- `data/dronefollow_frames/`: frame-arrival times copied from your dronefollow logs (no video).

```bash
pip install -r requirements.txt
python3 -m blackbox.regress
python3 -m unittest discover -s tests
python3 -m blackbox.analyze data/dronefollow_frames/*.jsonl --skip-start 2 --suggest
```

## Rules
- Week 1 to 2 are grounded or hover-only. Never rerun the old `follow_person.py --backend yolo --tello --auto --fly`.
- No pre-registered predictions (dropped to save time). Baseline: the Oct 10 grounded test had stalls over 300 ms about 10 times a minute and one full stream stop at 148.6 s.
- Log every run in EXPERIMENT_LOG.md.

## Not done yet
Live logging on the drone, a hover flight, one-variable stall experiments, the offline Kalman filter, a write-up and video. See the plan in the vault report.
