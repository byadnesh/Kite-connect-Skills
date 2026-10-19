import unittest
from datetime import date, datetime, timedelta

from _load import load

vo = load("kite-connect", "validate_order")
mh = load("kite-connect", "market_hours")
IST = mh.IST

TUESDAY_11AM = datetime(2026, 10, 20, 11, 0, tzinfo=IST)
SATURDAY = datetime(2026, 10, 24, 11, 0, tzinfo=IST)

EQ = {"tradingsymbol": "INFY", "exchange": "NSE", "segment": "NSE", "instrument_type": "EQ",
      "lot_size": 1, "tick_size": 0.05}
OPT = {"tradingsymbol": "NIFTY26OCT25000CE", "exchange": "NFO", "segment": "NFO-OPT",
       "instrument_type": "CE", "lot_size": 65, "tick_size": 0.05}


def eq_order(**kw):
    o = dict(variety="regular", exchange="NSE", tradingsymbol="INFY", transaction_type="BUY", quantity=1,
             product="CNC", order_type="LIMIT", price=1500.0, validity="DAY", tag="kiteskill")
    o.update(kw)
    return o


def opt_order(**kw):
    o = dict(variety="regular", exchange="NFO", tradingsymbol=OPT["tradingsymbol"], transaction_type="BUY",
             quantity=65, product="NRML", order_type="LIMIT", price=120.0, validity="DAY", tag="kiteskill")
    o.update(kw)
    return o


class ValidateOrderTests(unittest.TestCase):
    def check(self, order, inst=EQ, ltp=1500.0, now=TUESDAY_11AM, **kw):
        return vo.validate_order(order, instrument=inst, ltp=ltp, now=now, **kw)

    def test_clean_limit_order_passes(self):
        r = self.check(eq_order())
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["warnings"], [])

    def test_product_segment_rules(self):
        self.assertFalse(self.check(eq_order(product="NRML"))["ok"])
        self.assertFalse(self.check(opt_order(product="CNC"), inst=OPT, ltp=120)["ok"])
        self.assertTrue(self.check(opt_order(), inst=OPT, ltp=120)["ok"])

    def test_lot_size_multiple(self):
        r = self.check(opt_order(quantity=70), inst=OPT, ltp=120)
        self.assertFalse(r["ok"])
        self.assertTrue(any("lot size 65" in e for e in r["errors"]))

    def test_tick_size(self):
        r = self.check(eq_order(price=1500.03))
        self.assertTrue(any("tick size" in e for e in r["errors"]))

    def test_market_requires_protection(self):
        self.assertFalse(self.check(eq_order(order_type="MARKET", price=None))["ok"])
        self.assertFalse(self.check(eq_order(order_type="MARKET", price=None, market_protection=0))["ok"])
        r = self.check(eq_order(order_type="MARKET", price=None, market_protection=-1))
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["warnings"])  # still warns about MARKET

    def test_sl_price_relationship(self):
        r = self.check(eq_order(order_type="SL", transaction_type="SELL", price=1460.0, trigger_price=1450.0))
        self.assertFalse(r["ok"])
        r = self.check(eq_order(order_type="SL", transaction_type="SELL", price=1445.0, trigger_price=1450.0))
        self.assertTrue(r["ok"], r)

    def test_derivative_needs_instrument(self):
        r = vo.validate_order(opt_order(), instrument=None, ltp=120, now=TUESDAY_11AM)
        self.assertFalse(r["ok"])

    def test_bad_tag(self):
        self.assertFalse(self.check(eq_order(tag="has space"))["ok"])
        self.assertFalse(self.check(eq_order(tag="x" * 21))["ok"])

    def test_notional_and_deviation_warnings(self):
        r = self.check(eq_order(quantity=100, price=1600.0), ltp=1500.0)
        self.assertTrue(r["ok"])
        joined = " ".join(r["warnings"])
        self.assertIn("exceeds", joined)
        self.assertIn("away from LTP", joined)

    def test_short_option_warning(self):
        r = self.check(opt_order(transaction_type="SELL"), inst=OPT, ltp=120)
        self.assertTrue(any("Short option" in w for w in r["warnings"]))

    def test_market_closed_suggests_amo(self):
        r = self.check(eq_order(), now=SATURDAY)
        self.assertTrue(any("amo" in w for w in r["warnings"]))
        r = self.check(eq_order(variety="amo"), now=SATURDAY)
        self.assertFalse(any("amo" in w for w in r["warnings"]))

    def test_index_not_tradable(self):
        idx = {"tradingsymbol": "NIFTY 50", "exchange": "NSE", "segment": "INDICES", "lot_size": 0, "tick_size": 0}
        r = self.check(eq_order(tradingsymbol="NIFTY 50"), inst=idx)
        self.assertFalse(r["ok"])

    def test_preview_renders(self):
        o = eq_order()
        txt = vo.format_preview(o, self.check(o))
        self.assertIn("ORDER PREVIEW", txt)
        self.assertIn("READY", txt)


class MarketHoursTests(unittest.TestCase):
    def test_sessions(self):
        self.assertTrue(mh.market_status("NSE", TUESDAY_11AM)["open"])
        self.assertEqual(mh.market_status("NSE", SATURDAY)["phase"], "weekend")
        self.assertEqual(mh.market_status("NSE", TUESDAY_11AM.replace(hour=9, minute=3))["phase"], "pre-open")
        self.assertFalse(mh.market_status("NSE", TUESDAY_11AM.replace(hour=16))["open"])
        self.assertTrue(mh.market_status("MCX", TUESDAY_11AM.replace(hour=21))["open"])

    def test_holiday(self):
        st = mh.market_status("NSE", TUESDAY_11AM, holidays={date(2026, 10, 20)})
        self.assertEqual(st["phase"], "holiday")

    def test_mis_warning(self):
        self.assertIsNone(mh.mis_square_off_warning("NSE", TUESDAY_11AM))
        self.assertIsNotNone(mh.mis_square_off_warning("NSE", TUESDAY_11AM.replace(hour=15, minute=10)))


class FakeKite:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def instruments(self, exchange):
        self.calls += 1
        return [dict(r) for r in self.rows if r["exchange"] == exchange]


class InstrumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ins = load("kite-connect", "instruments")
        today = cls.ins._today_ist()
        e1, e2 = today + timedelta(days=3), today + timedelta(days=10)
        rows = [
            {"instrument_token": 1, "tradingsymbol": "INFY", "name": "INFOSYS", "exchange": "NSE", "segment": "NSE",
             "instrument_type": "EQ", "expiry": None, "strike": 0.0, "lot_size": 1, "tick_size": 0.05},
            {"instrument_token": 2, "tradingsymbol": "NIFTY 50", "name": "NIFTY 50", "exchange": "NSE",
             "segment": "INDICES", "instrument_type": "EQ", "expiry": None, "strike": 0.0, "lot_size": 0,
             "tick_size": 0.0},
        ]
        tok = 10
        for e in (e1, e2):
            rows.append({"instrument_token": tok, "tradingsymbol": f"NIFTYFUT{e}", "name": "NIFTY", "exchange": "NFO",
                         "segment": "NFO-FUT", "instrument_type": "FUT", "expiry": e, "strike": 0.0,
                         "lot_size": 65, "tick_size": 0.1})
            tok += 1
            for k in (24900.0, 25000.0, 25100.0):
                for cp in ("CE", "PE"):
                    rows.append({"instrument_token": tok, "tradingsymbol": f"NIFTY{e}{int(k)}{cp}", "name": "NIFTY",
                                 "exchange": "NFO", "segment": "NFO-OPT", "instrument_type": cp, "expiry": e,
                                 "strike": k, "lot_size": 65, "tick_size": 0.05})
                    tok += 1
        cls.e1, cls.e2 = e1, e2
        cls.kite = FakeKite(rows)

    def test_lookups(self):
        ins, k = self.ins, self.kite
        self.assertEqual(ins.find_equity(k, "infy")["instrument_token"], 1)
        self.assertEqual(ins.find_equity(k, "NIFTY 50")["segment"], "INDICES")
        self.assertEqual(ins.list_expiries(k, "NIFTY"), [self.e1, self.e2])
        self.assertEqual(ins.find_future(k, "NIFTY")["expiry"], self.e1)
        opt = ins.find_option(k, "NIFTY", None, 25000, "pe")
        self.assertEqual((opt["expiry"], opt["strike"], opt["instrument_type"]), (self.e1, 25000.0, "PE"))
        self.assertEqual(ins.option_strikes(k, "NIFTY", self.e2), [24900.0, 25000.0, 25100.0])
        self.assertEqual(ins.quote_key(opt), f"NFO:{opt['tradingsymbol']}")
        with self.assertRaises(LookupError):
            ins.find_option(k, "NIFTY", None, 25050, "CE")
        self.assertEqual(ins.search(k, "infosys")[0]["tradingsymbol"], "INFY")

    def test_daily_cache_roundtrip(self):
        ins = self.ins
        ins._memory.clear()
        before = self.kite.calls
        ins.load_instruments(self.kite, "NFO", refresh=True)
        ins._memory.clear()
        rows = ins.load_instruments(self.kite, "NFO")  # from disk
        self.assertEqual(self.kite.calls, before + 1)
        self.assertIsInstance(next(r for r in rows if r["expiry"])["expiry"], date)

    def test_derivative_exchange(self):
        self.assertEqual(self.ins.derivative_exchange("SENSEX"), "BFO")
        self.assertEqual(self.ins.derivative_exchange("NIFTY"), "NFO")


class ClientTests(unittest.TestCase):
    def test_token_cutoff_and_mask(self):
        kc = load("kite-connect", "kite_client")
        self.assertEqual(kc.mask("abcdefghijkl"), "abcd…ijkl")
        self.assertEqual(kc.mask(None), "<missing>")
        early = datetime(2026, 10, 20, 5, 0, tzinfo=IST)
        self.assertEqual(kc._token_cutoff(early), datetime(2026, 10, 19, 6, 0, tzinfo=IST))
        self.assertEqual(kc._token_cutoff(TUESDAY_11AM), datetime(2026, 10, 20, 6, 0, tzinfo=IST))

    def test_journal_strips_secrets(self):
        tj = load("kite-connect", "trade_journal")
        e = tj.log_action("place", {"tradingsymbol": "INFY", "access_token": "SECRET", "api_secret": "S"})
        self.assertNotIn("access_token", e["params"])
        self.assertNotIn("SECRET", tj.JOURNAL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
