import queue
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone

from _load import load

tu = load("kite-websocket", "tick_utils")
bars = load("kite-websocket", "bars")
rec = load("kite-websocket", "recorder")
ts_mod = load("kite-websocket", "tick_stream")
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc


def tick(token, price, ts=None, volume=None, depth=None, oi=None):
    t = {"instrument_token": token, "last_price": price, "mode": "full", "tradable": True}
    if ts is not None:
        t["exchange_timestamp"] = ts
    if volume is not None:
        t["volume_traded"] = volume
    if depth is not None:
        t["depth"] = depth
    if oi is not None:
        t["oi"] = oi
    return t


def at(h, m, s=0):
    return datetime(2026, 10, 20, h, m, s, tzinfo=IST)


class TickUtilsTests(unittest.TestCase):
    def test_to_ist(self):
        aware_utc = datetime(2026, 10, 20, 3, 45, tzinfo=UTC)
        self.assertEqual(tu.to_ist(aware_utc), at(9, 15))
        naive_local = datetime(2026, 10, 20, 9, 15)          # host-local, as the SDK produces
        self.assertEqual(tu.to_ist(naive_local), naive_local.astimezone().astimezone(IST))
        self.assertEqual(tu.to_ist(naive_local).utcoffset(), timedelta(hours=5, minutes=30))
        self.assertIsNone(tu.to_ist(None))

    def test_tick_time_fallbacks(self):
        recv = at(10, 0, 5)
        self.assertEqual(tu.tick_time(tick(1, 10, ts=at(10, 0)), recv), at(10, 0))
        self.assertEqual(tu.tick_time({"last_trade_time": at(9, 59)}, recv), at(9, 59))
        self.assertEqual(tu.tick_time({}, recv), recv)

    def test_depth_helpers(self):
        depth = {"buy": [{"price": 99.5, "quantity": 300, "orders": 3}] * 5,
                 "sell": [{"price": 100.5, "quantity": 100, "orders": 1}] * 5}
        t = tick(1, 100, depth=depth)
        self.assertEqual(tu.best_bid_ask(t), (99.5, 100.5))
        self.assertEqual(tu.mid(t), 100.0)
        self.assertAlmostEqual(tu.spread_bps(t), 100.0)
        self.assertAlmostEqual(tu.book_imbalance(t), 0.5)
        empty = tick(1, 100, depth={"buy": [{"price": 0, "quantity": 0}], "sell": []})
        self.assertEqual(tu.best_bid_ask(empty), (None, None))
        self.assertIsNone(tu.spread_bps(empty))
        self.assertEqual(tu.mid(empty), 100)

    def test_flatten(self):
        row = tu.flatten(tick(5, 101.5, ts=at(9, 20), volume=10), at(9, 20, 1))
        self.assertEqual(row["token"], 5)
        self.assertEqual(row["ts"], at(9, 20).isoformat())
        self.assertEqual(row["volume"], 10)


class BarBuilderTests(unittest.TestCase):
    def test_ohlcv_and_rollover(self):
        bb = bars.BarBuilder(60)
        self.assertEqual(bb.update(tick(1, 100, at(9, 15, 1), volume=1000)), [])
        bb.update(tick(1, 103, at(9, 15, 20), volume=1100))
        bb.update(tick(1, 99, at(9, 15, 40), volume=1150))
        bb.update(tick(1, 101, at(9, 15, 59), volume=1200))
        done = bb.update(tick(1, 102, at(9, 16, 2), volume=1260))
        self.assertEqual(len(done), 1)
        b = done[0]
        self.assertEqual((b["open"], b["high"], b["low"], b["close"]), (100, 103, 99, 101))
        self.assertEqual(b["volume"], 200)         # first tick contributes 0; diffs after that
        self.assertEqual((b["start"], b["end"]), (at(9, 15), at(9, 16)))
        self.assertEqual(b["ticks"], 4)
        self.assertEqual(bb.current[1]["volume"], 60)

    def test_session_anchor_for_30min(self):
        bb = bars.BarBuilder(1800)
        self.assertEqual(bb.bucket_start(at(9, 50)), at(9, 45))
        self.assertEqual(bb.bucket_start(at(9, 44, 59)), at(9, 15))
        self.assertEqual(bars.BarBuilder(1800, anchor=time(9, 0)).bucket_start(at(9, 50)), at(9, 30))
        self.assertEqual(bars.BarBuilder(3600).bucket_start(at(15, 29)), at(15, 15))

    def test_flush_late_ticks_and_multiple_tokens(self):
        got = []
        bb = bars.BarBuilder(60, on_bar=got.append)
        bb.update(tick(1, 10, at(9, 15, 5)))
        bb.update(tick(2, 20, at(9, 15, 6)))
        self.assertEqual(bb.flush(at(9, 15, 59)), [])
        out = bb.flush(at(9, 16, 0))
        self.assertEqual([b["token"] for b in out], [1, 2])
        self.assertEqual(len(got), 2)
        bb.update(tick(1, 11, at(9, 17, 0)))
        self.assertEqual(bb.update(tick(1, 9, at(9, 16, 30))), [])   # late tick ignored
        self.assertEqual(bb.late_ticks, 1)
        self.assertEqual(len(bb.flush(force=True)), 1)

    def test_receive_time_mode_and_volume_reset(self):
        bb = bars.BarBuilder(60, use_exchange_time=False)
        bb.update(tick(1, 10, ts=at(9, 0), volume=500), received_at=at(9, 30, 10))
        self.assertEqual(bb.current[1]["start"], at(9, 30))
        bb.update(tick(1, 10, volume=400), received_at=at(9, 30, 20))   # volume went down: no negative
        self.assertEqual(bb.current[1]["volume"], 0)
        with self.assertRaises(ValueError):
            bars.BarBuilder(0)


class RecorderTests(unittest.TestCase):
    def test_roundtrip_and_rotation(self):
        d = tempfile.mkdtemp()
        with rec.TickRecorder(d, flush_every=1) as r:
            r.write(at(15, 29), tick(1, 100, at(15, 29), volume=5))
            r.write(at(15, 29) + timedelta(days=1), tick(1, 101))
        files = sorted(p.name for p in __import__("pathlib").Path(d).iterdir())
        self.assertEqual(files, ["ticks_20261020.jsonl", "ticks_20261021.jsonl"])
        rows = list(rec.read_ticks(f"{d}/ticks_20261020.jsonl"))
        self.assertEqual(rows[0]["ltp"], 100)
        self.assertEqual(rows[0]["ts"], at(15, 29))
        self.assertEqual(r.rows_written, 2)


class FakeTicker:
    instances = []

    def __init__(self):
        self.subscribed_tokens = {}
        self.calls = []
        self.connected = False
        FakeTicker.instances.append(self)

    def connect(self, threaded=False):
        self.calls.append(("connect", threaded))

    def subscribe(self, toks):
        self.calls.append(("subscribe", list(toks)))
        for t in toks:
            self.subscribed_tokens[t] = "quote"

    def set_mode(self, mode, toks):
        self.calls.append(("set_mode", mode, list(toks)))
        for t in toks:
            self.subscribed_tokens[t] = mode

    def unsubscribe(self, toks):
        self.calls.append(("unsubscribe", list(toks)))
        for t in toks:
            self.subscribed_tokens.pop(t, None)

    def close(self):
        self.calls.append(("close",))


def make_stream(**kw):
    FakeTicker.instances.clear()
    return ts_mod.TickStream("key", "SECRET-TOKEN", ticker_factory=FakeTicker,
                             call_in_reactor=lambda fn, *a, **k: fn(*a, **k), **kw)


class TickStreamTests(unittest.TestCase):
    def test_sharding_and_capacity(self):
        s = make_stream(max_tokens_per_connection=3, max_connections=2)
        s.subscribe(range(1, 6), "ltp")
        self.assertEqual(len(FakeTicker.instances), 2)
        self.assertEqual(len(s._conns[0]["tokens"]), 3)
        self.assertEqual(len(s._conns[1]["tokens"]), 2)
        s.subscribe([1, 6], "full")                 # 1 re-moded in place, 6 fills shard 2
        self.assertEqual(s.subscribed[1], "full")
        self.assertEqual(len(s._conns[1]["tokens"]), 3)
        with self.assertRaises(ValueError):
            s.subscribe([7])
        with self.assertRaises(ValueError):
            s.subscribe([1], "depth")
        self.assertNotIn("SECRET", repr(s))

    def test_start_connects_and_syncs_on_connect(self):
        s = make_stream(max_tokens_per_connection=2)
        s.subscribe([1, 2, 3], "quote")
        s.start()
        k0, k1 = FakeTicker.instances
        self.assertIn(("connect", True), k0.calls)
        self.assertIn(("connect", True), k1.calls)
        self.assertEqual(k0.calls, [("connect", True)])   # nothing sent before the socket is up
        k0.on_connect(k0, {})
        self.assertIn(("subscribe", [1, 2]), k0.calls)
        self.assertIn(("set_mode", "quote", [1, 2]), k0.calls)
        k1.on_connect(k1, {})
        self.assertTrue(s.wait_connected(0.1))
        s.subscribe([1], "full")                           # live re-mode goes straight out
        self.assertIn(("set_mode", "full", [1]), k0.calls)
        s.unsubscribe([2, 99])
        self.assertIn(("unsubscribe", [2]), k0.calls)

    def test_orphans_removed_on_reconnect(self):
        s = make_stream()
        s.subscribe([1, 2])
        s.start()
        k0 = FakeTicker.instances[0]
        k0.on_connect(k0, {})
        k0.on_close(k0, 1006, "lost")
        s.unsubscribe([2])                                  # while disconnected: only recorded
        self.assertNotIn(("unsubscribe", [2]), k0.calls)
        k0.on_reconnect(k0, 1)
        k0.on_connect(k0, {})
        self.assertIn(("unsubscribe", [2]), k0.calls)
        self.assertEqual(s.health()["connections"][0]["reconnects"], 1)

    def test_ticks_queue_latest_and_drops(self):
        s = make_stream(queue_maxsize=2)
        s.subscribe([1, 2])
        s.start()
        k0 = FakeTicker.instances[0]
        k0.on_ticks(k0, [tick(1, 10), tick(2, 20), tick(1, 11)])
        self.assertEqual(s.stats["dropped"], 1)
        self.assertEqual(s.latest[1]["last_price"], 11)
        got = [t["last_price"] for _, t in s.drain()]
        self.assertEqual(got, [20, 11])                     # oldest dropped
        self.assertEqual(s.stale_tokens(60), [])
        self.assertEqual(s.health()["ticks"], 3)

    def test_order_updates_only_first_connection(self):
        s = make_stream(max_tokens_per_connection=1)
        s.subscribe([1, 2])
        k0, k1 = FakeTicker.instances
        self.assertTrue(hasattr(k0, "on_order_update"))
        self.assertFalse(hasattr(k1, "on_order_update"))
        k0.on_order_update(k0, {"order_id": "1", "status": "COMPLETE"})
        self.assertEqual(s.order_updates.get_nowait()["status"], "COMPLETE")
        with self.assertRaises(queue.Empty):
            s.order_updates.get_nowait()

    def test_start_without_tokens_and_close(self):
        s = make_stream()
        s.start()
        self.assertEqual(len(FakeTicker.instances), 1)      # one connection for order updates
        s.close()
        self.assertIn(("close",), FakeTicker.instances[0].calls)
        self.assertEqual(list(s.iter_ticks(timeout=0.01)), [])
        k0 = FakeTicker.instances[0]
        k0.on_error(k0, 0, "bad token")
        self.assertIn("bad token", s.health()["recent_errors"][0])


if __name__ == "__main__":
    unittest.main()
