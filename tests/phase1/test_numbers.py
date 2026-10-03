"""A number counts only when that exact text is in the sentence."""

from extrude.intake.parse import find_quantities


def test_units_become_si_and_the_snippet_is_in_the_sentence():
    text = "5 V to 3.3 V at 2 A, ripple 30 mV, and 2000 mA elsewhere"
    hits = find_quantities(text)
    snippets = [hit.snippet for hit in hits]
    assert "5 V" in snippets
    assert "3.3 V" in snippets
    assert "2 A" in snippets
    assert "30 mV" in snippets
    assert "2000 mA" in snippets
    by_snippet = {hit.snippet: hit for hit in hits}
    assert by_snippet["5 V"].si == 5
    assert by_snippet["3.3 V"].si == 3.3
    assert by_snippet["2 A"].si == 2
    assert by_snippet["30 mV"].si == 0.03
    assert by_snippet["2000 mA"].si == 2
    for hit in hits:
        assert text[hit.start : hit.end] == hit.snippet


def test_scientific_notation_and_part_numbers_are_not_voltages():
    hits = find_quantities("5e0 V from an ESP32, not 2APPLE")
    assert hits == []


def test_tight_units_still_match():
    text = "5V to 3.3V at 2A ripple 1mV"
    hits = find_quantities(text)
    values = sorted(hit.si for hit in hits)
    assert values == [0.001, 2, 3.3, 5]
