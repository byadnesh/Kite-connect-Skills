"""Record ticks to daily-rotating JSON Lines files and read them back.

UNOFFICIAL — not affiliated with Zerodha. Standard library only.
Recorded exchange data is for your own use — don't redistribute or commit it.

    rec = TickRecorder("ticks")          # ticks/ticks_20261020.jsonl
    rec.write(received_at, tick)
    rec.close()
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.tick_utils import flatten, now_ist, to_ist  # noqa: E402


class TickRecorder:
    def __init__(self, directory: str | Path, prefix: str = "ticks", flush_every: int = 1000,
                 flush_seconds: float = 2.0):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.flush_every = flush_every
        self.flush_seconds = flush_seconds
        self._fh = None
        self._day = None
        self._pending = 0
        self._last_flush = time.monotonic()
        self.rows_written = 0

    def _file_for(self, received_at: datetime) -> Path:
        return self.dir / f"{self.prefix}_{received_at:%Y%m%d}.jsonl"

    def _rotate(self, received_at: datetime) -> None:
        day = received_at.date()
        if day != self._day:
            if self._fh:
                self._fh.close()
            self._fh = open(self._file_for(received_at), "a", encoding="utf-8")
            self._day = day

    def write(self, received_at: datetime | None, tick: dict[str, Any]) -> None:
        received_at = to_ist(received_at) if received_at else now_ist()
        self._rotate(received_at)
        self._fh.write(json.dumps(flatten(tick, received_at), separators=(",", ":")) + "\n")
        self._pending += 1
        self.rows_written += 1
        if self._pending >= self.flush_every or time.monotonic() - self._last_flush >= self.flush_seconds:
            self.flush()

    def flush(self) -> None:
        if self._fh:
            self._fh.flush()
        self._pending = 0
        self._last_flush = time.monotonic()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
        self._day = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_ticks(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield recorded rows with `ts`/`recv` parsed back to aware datetimes."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            for k in ("ts", "recv"):
                if row.get(k):
                    row[k] = datetime.fromisoformat(row[k])
            yield row
