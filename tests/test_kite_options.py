import math
import unittest
from datetime import datetime, timedelta

from _load import load

g = load("kite-options", "greeks")


class GreeksTests(unittest.TestCase):
    def test_textbook_price(self):
        self.assertAlmostEqual(g.bs_price(100, 100, 1, 0.05, 0.2, "CE"), 10.4506, places=4)
        self.assertAlmostEqual(g.bs_price(100, 100, 1, 0.05, 0.2, "PE"), 5.5735, places=4)

    def test_put_call_parity_with_carry(self):
        S, K, T, r, q, v = 25000, 25200, 10 / 365, 0.06, 0.012, 0.13
        c, p = g.bs_price(S, K, T, r, v, "CE", q), g.bs_price(S, K, T, r, v, "PE", q)
        self.assertAlmostEqual(c - p, S * math.exp(-q * T) - K * math.exp(-r * T), places=6)

    def test_iv_roundtrip(self):
        for cp in ("CE", "PE"):
            for k in (24000, 25000, 26000):
                p = g.bs_price(25000, k, 7 / 365, 0.06, 0.14, cp)
                self.assertAlmostEqual(g.implied_vol(p, 25000, k, 7 / 365, 0.06, cp), 0.14, places=4)
        self.assertIsNone(g.implied_vol(0, 25000, 25000, 0.02, 0.06, "CE"))
        self.assertIsNone(g.implied_vol(0.01, 25000, 24000, 0.02, 0.06, "CE"))  # below intrinsic

    def test_greeks_signs_and_finite_difference(self):
        S, K, T, r, v = 25000, 25000, 14 / 365, 0.06, 0.12
        gc = g.bs_greeks(S, K, T, r, v, "CE")
        gp = g.bs_greeks(S, K, T, r, v, "PE")
        self.assertTrue(0 < gc["delta"] < 1 and -1 < gp["delta"] < 0)
        self.assertTrue(gc["theta"] < 0 and gc["vega"] > 0 and gc["gamma"] > 0)
        h = 1.0
        fd = (g.bs_price(S + h, K, T, r, v, "CE") - g.bs_price(S - h, K, T, r, v, "CE")) / (2 * h)
        self.assertAlmostEqual(gc["delta"], fd, places=4)
        fdv = g.bs_price(S, K, T, r, v + 0.01, "CE") - g.bs_price(S, K, T, r, v, "CE")
        self.assertAlmostEqual(gc["vega"], fdv, delta=abs(fdv) * 0.01)

    def test_time_to_expiry(self):
        now = datetime(2026, 10, 20, 15, 30, tzinfo=g.IST)
        self.assertAlmostEqual(g.time_to_expiry((now + timedelta(days=365)).date(), now), 1.0, places=6)

    def test_iron_condor_stats(self):
        q = 65
        legs = [
            {"strike": 24600, "option_type": "PE", "side": "BUY", "quantity": q, "premium": 10},
            {"strike": 25400, "option_type": "CE", "side": "BUY", "quantity": q, "premium": 8},
            {"strike": 24800, "option_type": "PE", "side": "SELL", "quantity": q, "premium": 30},
            {"strike": 25200, "option_type": "CE", "side": "SELL", "quantity": q, "premium": 25},
        ]
        st = g.strategy_stats(legs, 23000, 27000)
        credit = (30 + 25 - 10 - 8) * q
        self.assertAlmostEqual(st["net_premium"], credit)
        self.assertAlmostEqual(st["max_profit"], credit)
        self.assertAlmostEqual(st["max_loss"], -(200 * q - credit))
        self.assertEqual(len(st["breakevens"]), 2)
        self.assertAlmostEqual(st["breakevens"][0], 24800 - 37, places=1)
        self.assertAlmostEqual(st["breakevens"][1], 25200 + 37, places=1)

    def test_unbounded_detection(self):
        long_call = [{"strike": 25000, "option_type": "CE", "side": "BUY", "quantity": 1, "premium": 100}]
        short_call = [{**long_call[0], "side": "SELL"}]
        long_put = [{"strike": 25000, "option_type": "PE", "side": "BUY", "quantity": 1, "premium": 100}]
        self.assertEqual(g.strategy_stats(long_call, 20000, 30000)["max_profit"], "unlimited")
        self.assertEqual(g.strategy_stats(short_call, 20000, 30000)["max_loss"], "unlimited")
        st = g.strategy_stats(long_put, 20000, 30000)
        self.assertAlmostEqual(st["max_profit"], 24900)   # bounded: spot can only fall to 0
        self.assertAlmostEqual(st["max_loss"], -100)


class FakeKite:
    """Prices every option with BSM at 13 % vol so the chain's IV should come back ≈ 0.13."""

    def __init__(self, rows, spot, T, r=0.06, vol=0.13):
        self.rows, self.spot, self.T, self.r, self.vol = rows, spot, T, r, vol
        self.by_key = {f"{x['exchange']}:{x['tradingsymbol']}": x for x in rows}

    def instruments(self, exchange):
        return [dict(x) for x in self.rows if x["exchange"] == exchange]

    def ltp(self, *keys):
        return {k: {"last_price": self.spot} for k in keys}

    def quote(self, *keys):
        out = {}
        for k in keys:
            x = self.by_key[k]
            px = g.bs_price(self.spot, x["strike"], self.T, self.r, self.vol, x["instrument_type"])
            out[k] = {"last_price": round(px, 2), "oi": int(1e5 + x["strike"]) if x["instrument_type"] == "PE" else 100000,
                      "volume": 1000, "depth": {"buy": [{"price": px - 0.05}], "sell": [{"price": px + 0.05}]}}
        return out


class ChainTests(unittest.TestCase):
    def test_build_chain_recovers_iv(self):
        oc = load("kite-options", "option_chain")
        oc.time.sleep = lambda s: None  # don't actually wait for the rate limiter
        kc = load("kite-options", "kite_common")
        for f in (kc.HOME / "cache").glob("instruments_NFO_*.json"):  # cache is shared across skills
            f.unlink()
        expiry = oc.today_ist() + timedelta(days=7)
        rows, tok = [], 1
        for k in range(24500, 25550, 50):
            for cp in ("CE", "PE"):
                rows.append({"instrument_token": tok, "tradingsymbol": f"NIFTYX{k}{cp}", "name": "NIFTY",
                             "exchange": "NFO", "segment": "NFO-OPT", "instrument_type": cp, "expiry": expiry,
                             "strike": float(k), "lot_size": 65, "tick_size": 0.05})
                tok += 1
        T = g.time_to_expiry(expiry)
        kite = FakeKite(rows, 25010.0, T)
        chain = oc.build_chain(kite, "NIFTY", strikes_each_side=5)
        self.assertEqual(chain["atm_strike"], 25000.0)
        self.assertEqual(len(chain["rows"]), 11)
        self.assertAlmostEqual(oc.atm_iv(chain), 0.13, delta=0.003)
        self.assertGreater(oc.pcr(chain)["pcr_oi"], 1)
        self.assertIn(oc.max_pain(chain), [r["strike"] for r in chain["rows"]])
        self.assertAlmostEqual(abs(oc.find_by_delta(chain, "CE", 0.5)["ce_delta"]), 0.5, delta=0.1)
        self.assertIn("PCR(OI)", oc.format_chain(chain))


if __name__ == "__main__":
    unittest.main()
