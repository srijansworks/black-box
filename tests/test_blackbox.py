import io, json, os, tempfile, unittest
from blackbox import faults, regress
from blackbox.log import EventLogger, frame_times, read_events
from blackbox.replay import replay, trace_hash, mode_entries
from blackbox.timing import gaps, percentile, poisson_ci, stalls, summarize
from blackbox.watchdog import Config, Mode, Watchdog


class TestLog(unittest.TestCase):
    def test_roundtrip_and_partial_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.jsonl")
            with EventLogger(p, {"run": "t"}) as lg:
                lg.log("frame"); lg.log("cmd", lr=0, fb=10, ud=0, yaw=0); lg.log("frame")
            with open(p, "a") as f:
                f.write('{"type":"frame","t":9')  # crash mid-write
            ev = list(read_events(p))
            self.assertEqual([e["type"] for e in ev], ["meta", "frame", "cmd", "frame"])
            ts = frame_times(ev)
            self.assertTrue(ts[0] <= ts[1])

    def test_legacy_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.jsonl")
            open(p, "w").write('{"_meta":{}}\n{"i":0,"t":0.1}\n{"t":0.2,"video":{"new":false}}\n{"t":0.3,"video":{"new":true}}\n')
            self.assertEqual(frame_times(read_events(p)), [0.1, 0.3])


class TestTiming(unittest.TestCase):
    def test_percentile(self):
        self.assertAlmostEqual(percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(percentile([0, 10], 25), 2.5)

    def test_poisson_ci_known_values(self):
        lo, hi = poisson_ci(0)
        self.assertAlmostEqual(lo, 0.0); self.assertAlmostEqual(hi, 3.689, places=2)
        lo, hi = poisson_ci(10)
        self.assertAlmostEqual(lo, 4.795, places=2); self.assertAlmostEqual(hi, 18.39, places=1)

    def test_stalls(self):
        ts = [0, .1, .2, .9, 1.0]
        self.assertEqual(len(stalls(ts, 0.3)), 1)
        self.assertEqual(summarize(ts)["stalls"], 1)


class TestWatchdog(unittest.TestCase):
    def test_modes_by_age(self):
        w = Watchdog(); c = Config()
        self.assertEqual(w.step(0.0, 0.0).mode, Mode.NORMAL)
        self.assertEqual(w.step(c.degraded_s + .01, 0.0, (10, 20, 0, 30)).cmd, (5, 10, 0, 15))
        self.assertEqual(w.step(c.hover_s + .01, 0.0, (10, 20, 0, 0)).cmd, (0, 0, 0, 0))
        self.assertEqual(w.step(c.land_s + .01, 0.0).mode, Mode.LAND)

    def test_battery_lands(self):
        self.assertEqual(Watchdog().step(1.0, 1.0, battery=10).mode, Mode.LAND)

    def test_same_inputs_same_decisions(self):
        ts = faults.freeze(faults.synthetic_stream(30), 10, 0.7)
        self.assertEqual(trace_hash(replay(ts)), trace_hash(replay(ts)))


class TestFaults(unittest.TestCase):
    def test_freeze_and_drop(self):
        base = faults.synthetic_stream(10)
        self.assertTrue(all(not (3 <= t < 4) for t in faults.freeze(base, 3, 1)))
        self.assertEqual(len(faults.drop_every(base, 2)), len(base) - len(base) // 2)

    def test_delay_creates_gap(self):
        ts = faults.delay_step(faults.synthetic_stream(10), 5, 0.6)
        self.assertGreater(max(gaps(ts)), 0.6)


class TestRegression(unittest.TestCase):
    def test_all_checks_pass(self):
        rows = regress.run()
        failed = [r for r in rows if not r[1]]
        self.assertEqual(failed, [], failed)


if __name__ == "__main__":
    unittest.main()
