"""A hold-up board is joined, unshorted, and inside the outline."""

import json

from extrude.checks.board import board_prompt, check_board


def _board(short: bool = False, outside: bool = False, unjoined: bool = False) -> str:
    rail_end = 5 if unjoined else 15
    traces = [{"x1_mm": 5, "y1_mm": 8, "x2_mm": rail_end, "y2_mm": 8}]
    if short:
        traces.append({"x1_mm": 5, "y1_mm": 8, "x2_mm": 5, "y2_mm": 12})
    y_gnd = 30 if outside else 12
    return json.dumps(
        {
            "parts": [
                {
                    "refdes": "C1",
                    "pads": [
                        {"name": "1", "net": "RAIL", "x_mm": 5, "y_mm": 8},
                        {"name": "2", "net": "GND", "x_mm": 5, "y_mm": y_gnd},
                    ],
                },
                {
                    "refdes": "R1",
                    "pads": [
                        {"name": "1", "net": "SRC", "x_mm": 12, "y_mm": 14},
                        {"name": "2", "net": "RAIL", "x_mm": 15, "y_mm": 8},
                    ],
                },
            ],
            "traces": traces,
        }
    )


def test_a_joined_board_passes_and_the_three_breaks_are_named():
    assert check_board(_board()) is None
    assert "shorts" in (check_board(_board(short=True)) or "")
    assert "outside" in (check_board(_board(outside=True)) or "")
    assert "not joined" in (check_board(_board(unjoined=True)) or "")
    assert "no pad" in (check_board(json.dumps({"parts": [], "traces": []})) or "")


def test_the_retry_quotes_the_fault():
    fault = check_board(_board(short=True)) or ""
    prompt = board_prompt(fault)
    assert "LAST_REJECTED:" in prompt
    assert fault in prompt
    assert "LAST_REJECTED:" not in board_prompt()
