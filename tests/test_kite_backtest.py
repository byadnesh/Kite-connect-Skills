import unittest
from datetime import datetime, timedelta, timezone

from _load import load

ch = load("kite-backtest", "charges")
bt = load("kite-backtest", "backtest")
fh = load("kite-backtest", "fetch_history")
IST = timezone(timedelta(hours=5, minutes=30))


def daily(prices, start=datetime(2025, 1, 1, tzinfo=IST)):
    return [{"date": start + timedelta(days=i), "open": p, "high": p, "low": p, "close": p, "volume": 1}
            for i, p in enumerate(prices)]


def intraday(days, bars_per_day=4, price=100.0):
    out = []
    for d in range(days):
        base = datetime(2025, 1, 6 + d, 9, 15, tzinfo=IST)
        for b in range(bars_per_day):
            out.append({"date": base + timedelta(minutes=15 * b), "open": price, "high": price, "low": price,
                        "close": price, "volume": 1})
    return out


class ChargesTests(unittest.TestCase):
    def test_intraday_brokerage_cap(self):
        c = ch.trade_charges("intraday", 100_000, 100_500)
        self.assertEqual(c["brokerage"], 40.0)
        small = ch.trade_charges("intraday", 10_000, 10_000)
        self.assertEqual(small["brokerage"], 6.0)  # 0.03 % × 10k × 2

    def test_delivery_components(self):
        c = ch.trade_charges("delivery", 100_000, 100_000)
        self.assertEqual(c["brokerage"], 0.0)
        self.assertEqual(c["stt"], 200.0)
        self.assertEqual(c["stamp_duty"], 15.0)
        self.assertEqual(c["dp"], 15.34)
        self.assertAlmostEqual(c["total"], sum(v for k, v in c.items() if k not in ("total", "turnover")), places=2)

    def test_options_flat_and_stt_on_sell_premium(self):
        c = ch.trade_charges("options", 9_000, 11_250)
        self.assertEqual(c["brokerage"], 40.0)
        self.assertEqual(c["stt"], round(11_250 * 0.0015, 2))
        self.assertEqual(c["gst"], round(0.18 * (c["brokerage"] + c["exchange_txn"] + c["sebi"]), 2))

    def test_one_side_and_breakeven(self):
        buy_only = ch.trade_charges("futures", buy_value=1_625_000)
        self.assertEqual(buy_only["stt"], 0.0)
        self.assertGreater(ch.breakeven_move("futures", 25000, 65), 0)
        with self.assertRaises(ValueError):
            ch.trade_charges("crypto", 1, 1)


class BacktestTests(unittest.TestCase):
    def test_no_lookahead_and_next_open_fill(self):
        c = daily([100, 100, 110, 120])
        res = bt.run_backtest(c, [1, 0, 0, 0], segment="delivery", capital=10_000, slippage_bps=0)
        self.assertEqual(res["fills"][0]["date"], c[1]["date"])   # signal on bar 0 → fill on bar 1
        self.assertEqual(res["fills"][0]["price"], 100)
        self.assertEqual(res["fills"][1]["date"], c[2]["date"])   # exit at bar 2 open
        self.assertEqual(len(res["trades"]), 1)

        last_only = bt.run_backtest(c, [0, 0, 0, 1], segment="delivery", capital=10_000)
        self.assertEqual(last_only["fills"], [])                  # last-bar signal can't trade

    def test_delivery_cannot_short(self):
        c = daily([100, 90, 80, 70])
        res = bt.run_backtest(c, [-1, -1, -1, -1], segment="delivery")
        self.assertEqual(res["fills"], [])
        res = bt.run_backtest(c, [-1, -1, -1, -1], segment="futures", quantity=10)
        self.assertGreater(res["metrics"]["final_equity"], res["metrics"]["initial_capital"])

    def test_intraday_squares_off_and_does_not_carry(self):
        c = intraday(3)
        res = bt.run_backtest(c, [1] * len(c), segment="intraday", quantity=10, slippage_bps=0)
        reasons = [f["reason"] for f in res["fills"]]
        self.assertEqual(reasons.count("eod_squareoff"), 3)
        for f in res["fills"]:
            if f["side"] == "BUY":
                self.assertNotEqual(f["date"].time(), datetime(2025, 1, 1, 9, 15).time())  # no entry at day open
        self.assertEqual(len(res["trades"]), 3)

    def test_charges_reduce_equity_on_flat_prices(self):
        c = daily([100] * 10)
        res = bt.run_backtest(c, [1, 0] * 5, segment="delivery", capital=100_000, slippage_bps=0)
        m = res["metrics"]
        self.assertAlmostEqual(m["final_equity"], 100_000 - m["total_charges"], places=2)
        self.assertTrue(all(t["net_pnl"] < 0 for t in res["trades"]))

    def test_partial_exit_pnl_reconciles(self):
        c = daily([100, 100, 110, 120, 120])
        res = bt.run_backtest(c, [1, 0.5, 0, 0, 0], segment="delivery", capital=10_000, slippage_bps=0)
        self.assertEqual([f["side"] for f in res["fills"]], ["BUY", "SELL", "SELL"])
        self.assertEqual(len(res["trades"]), 1)
        m = res["metrics"]
        net = sum(t["net_pnl"] for t in res["trades"])
        self.assertAlmostEqual(net, m["final_equity"] - m["initial_capital"], places=2)
        t = res["trades"][0]
        self.assertAlmostEqual(t["gross_pnl"] - t["charges"], t["net_pnl"], places=6)

    def test_fno_requires_quantity(self):
        with self.assertRaises(ValueError):
            bt.run_backtest(daily([1, 2]), [1, 1], segment="options")
        with self.assertRaises(ValueError):
            bt.run_backtest(daily([1, 2]), [1, 1], segment="futures", quantity=10, lot_size=65)

    def test_metrics_drawdown(self):
        c = daily([100, 100, 50, 100])
        m = bt.buy_and_hold(c)["metrics"]
        self.assertLess(m["max_drawdown_pct"], -45)


class FetchHistoryTests(unittest.TestCase):
    def test_chunk_ranges(self):
        chunks = fh.chunk_ranges("2026-01-01", "2026-12-31", "minute")
        self.assertGreaterEqual(len(chunks), 7)
        for a, b in chunks:
            self.assertLessEqual((b - a).days, 60)
        self.assertEqual(chunks[0][0].date().isoformat(), "2026-01-01")
        self.assertEqual(chunks[-1][1].date().isoformat(), "2026-12-31")
        with self.assertRaises(ValueError):
            fh.chunk_ranges("2026-01-01", "2026-02-01", "2minute")

    def test_fetch_dedup_and_sort(self):
        fh.time.sleep = lambda s: None

        class K:
            def historical_data(self, token, a, b, interval, continuous=False, oi=False):
                d = a.replace(tzinfo=IST)
                return [{"date": d, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
                        {"date": d, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

        rows = fh.fetch_candles(K(), 1, "2020-01-01", "2026-01-01", "day", cache=False)
        self.assertEqual(len(rows), len(fh.chunk_ranges("2020-01-01", "2026-01-01", "day")))
        self.assertEqual(rows, sorted(rows, key=lambda r: r["date"]))


if __name__ == "__main__":
    unittest.main()
