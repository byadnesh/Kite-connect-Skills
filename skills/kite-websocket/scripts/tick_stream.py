"""Thread-safe wrapper around KiteTicker for agents and scripts.

UNOFFICIAL — not affiliated with Zerodha.

What it adds on top of pykiteconnect's KiteTicker:
- runs in the background (Twisted reactor thread) and never blocks your thread;
- subscribe / unsubscribe / set_mode from any thread (marshalled onto the reactor);
- shards instruments over up to 3 connections × 3,000 tokens;
- bounded tick queue that drops the *oldest* ticks when your consumer falls behind (counted);
- `latest` snapshot per token, a separate `order_updates` queue (first connection only, no duplicates);
- health / stale-feed checks.

    stream = TickStream(api_key, access_token)
    stream.subscribe([256265, 738561], mode="full")
    stream.start(); stream.wait_connected(10)
    for received_at, tick in stream.iter_ticks(timeout=1):
        ...
    stream.close()
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Iterator

IST = timezone(timedelta(hours=5, minutes=30))
MODES = ("ltp", "quote", "full")
MAX_TOKENS_PER_CONNECTION = 3000
MAX_CONNECTIONS = 3


def _reactor_call(fn: Callable, *args, **kwargs) -> None:
    """Run fn on the Twisted reactor thread (KiteTicker's socket APIs are not thread-safe)."""
    from twisted.internet import reactor

    reactor.callFromThread(fn, *args, **kwargs)


class TickStream:
    def __init__(self, api_key: str, access_token: str, *, queue_maxsize: int = 200_000,
                 max_tokens_per_connection: int = MAX_TOKENS_PER_CONNECTION,
                 max_connections: int = MAX_CONNECTIONS, reconnect_max_tries: int = 300,
                 reconnect_max_delay: int = 30, ticker_factory: Callable[[], Any] | None = None,
                 call_in_reactor: Callable[..., None] | None = None):
        self.api_key = api_key
        self._access_token = access_token
        self.max_per_conn = max_tokens_per_connection
        self.max_connections = max_connections
        self.reconnect_max_tries = reconnect_max_tries
        self.reconnect_max_delay = reconnect_max_delay
        self._factory = ticker_factory or self._default_factory
        self._call = call_in_reactor or _reactor_call

        self.ticks: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self.order_updates: queue.Queue = queue.Queue()
        self.latest: dict[int, dict[str, Any]] = {}
        self._last_seen: dict[int, float] = {}
        self._lock = threading.RLock()
        self._conns: list[dict[str, Any]] = []
        self._token_conn: dict[int, dict[str, Any]] = {}
        self.started = False
        self.closed = False
        self.errors: list[tuple[datetime, int, str]] = []
        self.stats = {"ticks": 0, "dropped": 0, "order_updates": 0}

    def __repr__(self) -> str:  # never show the access token
        return f"<TickStream connections={len(self._conns)} tokens={len(self._token_conn)}>"

    # ------------------------------------------------------------------ connections
    def _default_factory(self):
        from kiteconnect import KiteTicker

        return KiteTicker(self.api_key, self._access_token, reconnect=True,
                          reconnect_max_tries=self.reconnect_max_tries,
                          reconnect_max_delay=self.reconnect_max_delay)

    def _new_conn(self) -> dict[str, Any]:
        if len(self._conns) >= self.max_connections:
            raise RuntimeError(f"Kite allows at most {self.max_connections} WebSocket connections per api_key")
        kt = self._factory()
        conn = {"index": len(self._conns), "ticker": kt, "tokens": {}, "connected": threading.Event(),
                "reconnects": 0, "gave_up": False, "last_tick": None}
        kt.on_ticks = lambda ws, ticks, c=conn: self._on_ticks(c, ticks)
        kt.on_connect = lambda ws, resp, c=conn: self._on_connect(c)
        kt.on_close = lambda ws, code, reason, c=conn: c["connected"].clear()
        kt.on_error = lambda ws, code, reason, c=conn: self._on_error(c, code, reason)
        kt.on_reconnect = lambda ws, attempts, c=conn: self._on_reconnect(c, attempts)
        kt.on_noreconnect = lambda ws, c=conn: c.update(gave_up=True)
        if conn["index"] == 0:  # order updates arrive on every connection; listen once
            kt.on_order_update = lambda ws, data: self._on_order_update(data)
        self._conns.append(conn)
        if self.started:
            self._call(kt.connect, threaded=True)
        return conn

    def start(self) -> "TickStream":
        """Connect all shards in the background. Safe to call once."""
        with self._lock:
            if self.started:
                return self
            if not self._conns:
                self._new_conn()  # needed for order updates even with no subscriptions
            self.started = True
            first, rest = self._conns[0], self._conns[1:]
        first["ticker"].connect(threaded=True)
        for conn in rest:  # extra connections must be opened from the running reactor
            self._call(conn["ticker"].connect, threaded=True)
        return self

    def wait_connected(self, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        for conn in list(self._conns):
            if not conn["connected"].wait(max(0.0, end - time.monotonic())):
                return False
        return True

    def close(self) -> None:
        """Close sockets and stop retries. Does NOT stop the reactor (it can't be restarted)."""
        self.closed = True
        for conn in self._conns:
            if self.started:
                self._call(conn["ticker"].close)
            conn["connected"].clear()

    # ------------------------------------------------------------------ subscriptions
    def subscribe(self, tokens: Iterable[int], mode: str = "quote") -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        tokens = list(dict.fromkeys(int(t) for t in tokens))
        with self._lock:
            new = [t for t in tokens if t not in self._token_conn]
            free = sum(self.max_per_conn - len(c["tokens"]) for c in self._conns)
            free += (self.max_connections - len(self._conns)) * self.max_per_conn
            if len(new) > free:
                raise ValueError(f"{len(new)} new tokens exceed remaining capacity {free} "
                                 f"({self.max_connections} × {self.max_per_conn})")
            batches: dict[int, list[int]] = {}
            for t in tokens:
                conn = self._token_conn.get(t)
                if conn is None:
                    conn = next((c for c in self._conns if len(c["tokens"]) < self.max_per_conn), None) \
                        or self._new_conn()
                    self._token_conn[t] = conn
                conn["tokens"][t] = mode
                batches.setdefault(conn["index"], []).append(t)
            for idx, toks in batches.items():
                self._send(self._conns[idx], "subscribe", toks, mode)

    def set_mode(self, tokens: Iterable[int], mode: str) -> None:
        self.subscribe(tokens, mode)

    def unsubscribe(self, tokens: Iterable[int]) -> None:
        with self._lock:
            batches: dict[int, list[int]] = {}
            for t in (int(x) for x in tokens):
                conn = self._token_conn.pop(t, None)
                if conn is None:
                    continue
                conn["tokens"].pop(t, None)
                self.latest.pop(t, None)
                self._last_seen.pop(t, None)
                batches.setdefault(conn["index"], []).append(t)
            for idx, toks in batches.items():
                self._send(self._conns[idx], "unsubscribe", toks)

    @property
    def subscribed(self) -> dict[int, str]:
        return {t: c["tokens"][t] for t, c in self._token_conn.items()}

    def _send(self, conn: dict[str, Any], action: str, toks: list[int], mode: str | None = None) -> None:
        if not self.started or not conn["connected"].is_set():
            return  # recorded in conn["tokens"]; synced in _on_connect
        kt = conn["ticker"]

        def do():
            if action == "subscribe":
                kt.subscribe(toks)
                kt.set_mode(mode, toks)
            else:
                kt.unsubscribe(toks)

        self._call(do)

    # ------------------------------------------------------------------ callbacks (reactor thread)
    def _on_connect(self, conn: dict[str, Any]) -> None:
        conn["connected"].set()
        by_mode: dict[str, list[int]] = {}
        with self._lock:
            for t, m in conn["tokens"].items():
                by_mode.setdefault(m, []).append(t)
        kt = conn["ticker"]
        # Tokens dropped while disconnected would otherwise come back via KiteTicker's own resubscribe.
        orphans = [t for t in getattr(kt, "subscribed_tokens", {}) if t not in conn["tokens"]]
        if orphans:
            kt.unsubscribe(orphans)
        for m, toks in by_mode.items():  # already on the reactor thread: call directly
            kt.subscribe(toks)
            kt.set_mode(m, toks)

    def _on_ticks(self, conn: dict[str, Any], ticks: list[dict[str, Any]]) -> None:
        now = datetime.now(IST)
        mono = time.monotonic()
        conn["last_tick"] = mono
        for t in ticks:
            tok = t.get("instrument_token")
            self.latest[tok] = t
            self._last_seen[tok] = mono
            self.stats["ticks"] += 1
            try:
                self.ticks.put_nowait((now, t))
            except queue.Full:
                try:
                    self.ticks.get_nowait()
                except queue.Empty:
                    pass
                self.stats["dropped"] += 1
                self.ticks.put_nowait((now, t))

    def _on_order_update(self, data: dict[str, Any]) -> None:
        self.stats["order_updates"] += 1
        self.order_updates.put(data)

    def _on_error(self, conn: dict[str, Any], code: int, reason: Any) -> None:
        self.errors.append((datetime.now(IST), code, str(reason)))
        del self.errors[:-50]

    def _on_reconnect(self, conn: dict[str, Any], attempts: int) -> None:
        conn["reconnects"] += 1
        conn["connected"].clear()

    # ------------------------------------------------------------------ consumption & health
    def iter_ticks(self, timeout: float | None = 1.0) -> Iterator[tuple[datetime, dict[str, Any]]]:
        """Yield (received_at, tick) until close(). With a timeout, idles quietly when the feed is silent."""
        while not self.closed:
            try:
                yield self.ticks.get(timeout=timeout)
            except queue.Empty:
                continue

    def drain(self, max_items: int = 10_000) -> list[tuple[datetime, dict[str, Any]]]:
        out = []
        while len(out) < max_items:
            try:
                out.append(self.ticks.get_nowait())
            except queue.Empty:
                break
        return out

    def stale_tokens(self, max_age_s: float = 30.0) -> list[int]:
        now = time.monotonic()
        return [t for t in self._token_conn if now - self._last_seen.get(t, -1e18) > max_age_s]

    def health(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "connections": [{
                "index": c["index"], "connected": c["connected"].is_set(), "tokens": len(c["tokens"]),
                "reconnects": c["reconnects"], "gave_up": c["gave_up"],
                "last_tick_age_s": round(now - c["last_tick"], 1) if c["last_tick"] else None,
            } for c in self._conns],
            "queue_size": self.ticks.qsize(),
            **self.stats,
            "recent_errors": [f"{ts:%H:%M:%S} {code} {msg}" for ts, code, msg in self.errors[-5:]],
        }
