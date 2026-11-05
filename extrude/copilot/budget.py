"""Luna spend cap per request. Lifetime telemetry is logged separately."""

import os

from extrude.memory.db import load_telemetry

_inflight = 0.0
_request_spent = 0.0


def spend_cap_usd() -> float:
    raw = os.environ.get("EXTRUDE_SPEND_CAP_USD", "5").strip()
    try:
        return float(raw)
    except ValueError:
        return 5.0


def begin_request() -> None:
    global _request_spent
    _request_spent = 0.0


def note_spend(amount: float) -> None:
    global _inflight, _request_spent
    if amount > 0:
        _inflight += amount
        _request_spent += amount


def clear_inflight() -> None:
    global _inflight
    _inflight = 0.0


def request_spent_usd() -> float:
    return _request_spent


def lifetime_spent_usd() -> float:
    total = _inflight
    for row in load_telemetry():
        if row.get("cost_usd") is not None:
            total += float(row["cost_usd"])
    return total


def spent_usd() -> float:
    """Eval scripts: current request plus inflight batch."""
    return _request_spent + _inflight


def under_cap() -> bool:
    return _request_spent < spend_cap_usd()
