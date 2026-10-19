"""Helper scripts for this skill (UNOFFICIAL — not affiliated with Zerodha)."""

import sys as _sys

# Output uses ₹ and box-drawing characters; legacy Windows consoles default to cp1252.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
