"""Spend cap applies per request, not lifetime telemetry."""

from extrude.copilot.budget import begin_request, note_spend, request_spent_usd, under_cap


def test_request_cap_resets_each_call():
    begin_request()
    note_spend(4.0)
    assert request_spent_usd() == 4.0
    assert under_cap() is True
    note_spend(1.5)
    assert under_cap() is False
    begin_request()
    assert request_spent_usd() == 0.0
    assert under_cap() is True
