"""Shared bootstrap for the examples (UNOFFICIAL — not affiliated with Zerodha)."""

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

import scripts  # noqa: E402,F401  (UTF-8 console setup)


def confirm(prompt: str = "Place this order? Type 'yes' to proceed: ") -> bool:
    """Explicit typed confirmation. Anything other than 'yes' aborts."""
    try:
        return input(prompt).strip().lower() == "yes"
    except EOFError:
        return False


def tick_round(x: float, tick: float) -> float:
    """Round a price to the instrument's tick size."""
    return round(round(x / tick) * tick, 2)
