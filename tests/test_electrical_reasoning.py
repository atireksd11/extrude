"""Topology regressions use invented components, independent of the acceptance repos."""

import json
import math
import pytest
from extrude.electrical_graph import build
from extrude.electrical_reasoning import analyze, resistance
from extrude.workspace_audit import Finding, Coverage


def design(parts, labels=(), wires=(), junctions=()):
    """Each pin has its own explicit sheet point (angle/mirror tested separately)."""
    libs = []
    placed = []
    for ref, symbol, value, pins, props in parts:
        definitions = []
        for number, name, kind, x, y in pins:
            definitions.append(
                f'(pin {kind} line (at {x} {-y} 0) (length 2.54) (name "{name}") (number "{number}"))'
            )
        libs.append(
            f'(symbol "{symbol}" (property "Description" "{props.get("_description", "")}") (symbol "X_1_1" {" ".join(definitions)}))'
        )
        fields = {
            "Reference": ref,
            "Value": value,
            **{k: v for k, v in props.items() if not k.startswith("_")},
        }
        properties = " ".join(
            f"(property {json.dumps(k)} {json.dumps(v)})" for k, v in fields.items()
        )
        placed.append(
            f'(symbol (lib_id "{symbol}") (at 0 0 0) (unit 1) (in_bom yes) (on_board yes) (uuid "{ref}") {properties})'
        )
    text = f'(kicad_sch (version 20250114) (generator "test") (uuid "root") (lib_symbols {" ".join(libs)}) {" ".join(placed)}'
    for name, x, y in labels:
        text += f' (label "{name}" (at {x} {y} 0) (uuid "label-{x}-{y}"))'
    for x1, y1, x2, y2 in wires:
        text += f" (wire (pts (xy {x1} {y1}) (xy {x2} {y2})))"
    for x, y in junctions:
        text += f" (junction (at {x} {y}))"
    return (text + ")").encode()


def resistor(ref, value, a, b):
    return (
        ref,
        "Device:" + ref,
        value,
        [("1", "~", "passive", *a), ("2", "~", "passive", *b)],
        {},
    )


def summaries(files):
    return [f["summary"] for f in analyze(files)[0]]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5k6", 5600),
        ("10k", 10000),
        ("4R7", 4.7),
        ("1M", 1e6),
        ("10m", 0.01),
        ("3.3 k", 3300),
        ("DNP", None),
        ("100foo", None),
        ("10kR 1%", 10000),
        ("22k1R 1%", 22100),
        ("5k1R 1%", 5100),
    ],
)
def test_resistor_units(value, expected):
    assert resistance(value) == expected


def test_crossing_requires_junction_and_t_junction_connects():
    parts = [
        resistor("R91", "1k", (-10, 0), (10, 0)),
        resistor("R92", "2k", (0, -10), (0, 10)),
    ]
    wires = [(-10, 0, 10, 0), (0, -10, 0, 10)]
    g = build({"c.kicad_sch": design(parts, wires=wires)})
    assert g.parts[0].pins[0].net != g.parts[1].pins[0].net
    g = build({"c.kicad_sch": design(parts, wires=wires, junctions=[(0, 0)])})
    assert g.parts[0].pins[0].net == g.parts[1].pins[0].net
    g = build({"c.kicad_sch": design(parts, wires=[(-10, 0, 10, 0), (0, -10, 0, 0)])})
    assert g.parts[0].pins[0].net == g.parts[1].pins[0].net


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", ["", "x", "y"])
def test_rotation_and_mirror(angle, mirror):
    # Asymmetric point; independently calculate rotation then reflection.
    data = design([resistor("R3", "1k", (3, 7), (9, 11))]).decode()
    replacement = f"(at 20 30 {angle})" + (f" (mirror {mirror})" if mirror else "")
    data = data.replace("(at 0 0 0) (unit 1)", replacement + " (unit 1)")
    p = build({"x.kicad_sch": data.encode()}).parts[0].pins[0]
    rad = math.radians(angle)
    x = 3 * math.cos(rad) + 7 * math.sin(rad)
    y = 3 * math.sin(rad) - 7 * math.cos(rad)
    if mirror == "x":
        y = -y
    if mirror == "y":
        x = -x
    assert p.net[1:] == pytest.approx((20 + x, 30 - y), abs=1e-5)


def test_divider_and_corrected_design_have_no_flags():
    adc = (
        "U99",
        "Generic:Converter",
        "converter",
        [("1", "AIN_ADC", "input", 0, 0), ("2", "ADC_VREF", "power_in", 30, 0)],
        {},
    )
    parts = [
        adc,
        resistor("R9", "5k6", (10, 0), (0, 0)),
        resistor("R10", "10k", (0, 0), (20, 0)),
    ]
    labels = [("VBUS", 10, 0), ("GND", 20, 0), ("3V3", 30, 0)]
    files = {"board.kicad_sch": design(parts, labels)}
    assert any("3.37V" in s and "U99" in s and "AIN_ADC" in s for s in summaries(files))
    parts[1] = resistor("R9", "10k", (10, 0), (0, 0))
    assert summaries({"board.kicad_sch": design(parts, labels)}) == []


def test_variants_do_not_share_global_nets():
    adc = (
        "U99",
        "Generic:Converter",
        "converter",
        [("1", "AIN_ADC", "input", 0, 0), ("2", "ADC_VREF", "power_in", 30, 0)],
        {},
    )
    good = [
        adc,
        resistor("R9", "10k", (10, 0), (0, 0)),
        resistor("R10", "10k", (0, 0), (20, 0)),
    ]
    bad = [
        adc,
        resistor("R9", "5k6", (10, 0), (0, 0)),
        resistor("R10", "10k", (0, 0), (20, 0)),
    ]
    labels = [("VBUS", 10, 0), ("GND", 20, 0), ("3V3", 30, 0), ("sense", 0, 0)]
    f, c = analyze(
        {"good.kicad_sch": design(good, labels), "bad.kicad_sch": design(bad, labels)}
    )
    assert len(f) == 1 and f[0]["sources"][0][0] == "bad.kicad_sch"


def test_cap_derating_and_corrected_rating():
    part = (
        "C93",
        "Device:C",
        "100uF 6.3V",
        [("1", "~", "passive", 0, 0), ("2", "~", "passive", 10, 0)],
        {},
    )
    labels = [("VBUS_A", 0, 0), ("GND", 10, 0)]
    assert any("79.4%" in s for s in summaries({"a.kicad_sch": design([part], labels)}))
    corrected = (*part[:2], "100uF 16V", *part[3:])
    assert summaries({"a.kicad_sch": design([corrected], labels)}) == []


def test_usb_uart_cc_and_corrected_usb_sink():
    connector = (
        "J90",
        "Connector:USB_C",
        "USB-C",
        [
            ("1", "D+", "passive", 0, 0),
            ("2", "D-", "passive", 10, 0),
            ("3", "CC1", "passive", 20, 0),
            ("4", "CC2", "passive", 30, 0),
            ("5", "SHIELD", "passive", 40, 0),
        ],
        {},
    )
    uart = (
        "U91",
        "Generic:MCU",
        "MCU",
        [("1", "UART_TX", "output", 0, 0), ("2", "UART_RX", "input", 10, 0)],
        {},
    )
    f = summaries({"a.kicad_sch": design([connector, uart])})
    assert (
        any("UART_TX" in s for s in f)
        and any("CC1" in s for s in f)
        and any("SHIELD" in s for s in f)
    )
    usb = (
        *uart[:3],
        [
            ("1", "USB_D+", "bidirectional", 0, 0),
            ("2", "USB_D-", "bidirectional", 10, 0),
        ],
        {},
    )
    esd = (
        "D90",
        "Protection:TVS",
        "TVS",
        [
            ("1", "D+", "passive", 0, 0),
            ("2", "D-", "passive", 10, 0),
            ("3", "GND", "power_in", 40, 0),
        ],
        {},
    )
    parts = [
        connector,
        usb,
        esd,
        resistor("R90", "5.1k", (20, 0), (40, 0)),
        resistor("R91", "5.1k", (30, 0), (40, 0)),
    ]
    assert summaries({"a.kicad_sch": design(parts, [("GND", 40, 0)])}) == []


def test_model_paths_exact_case_and_external_library_unknown():
    pcb = b'(kicad_pcb (footprint "X" (property "Reference" "J90") (model "${KIPRJMOD}/Models/part.STEP")))'
    f, c = analyze({"pcb/a.kicad_pcb": pcb}, ["pcb/Models/part.step"])
    assert len(f) == 1 and "J90" in f[0]["summary"]
    assert not analyze({"pcb/a.kicad_pcb": pcb}, ["pcb/Models/part.STEP"])[0]
    f, c = analyze({"pcb/a.kicad_pcb": pcb.replace(b"KIPRJMOD", b"KICAD9_3DMODEL_DIR")})
    assert not f and any("external library model" in d for _, _, d in c)


def test_polarity_requires_limits_and_checks_declared_intent():
    ref = (
        "U90",
        "Generic:ShuntReference",
        "reference",
        [
            ("1", "REF", "input", 0, 0),
            ("2", "K", "open_collector", 30, 0),
            ("3", "A", "power_in", 20, 0),
        ],
        {},
    )
    parts = [
        ref,
        resistor("R90", "10k", (10, 0), (0, 0)),
        resistor("R91", "10k", (0, 0), (20, 0)),
    ]
    labels = [("GND", 20, 0)]
    f, c = analyze({"a.kicad_sch": design(parts, labels)})
    assert not f and any(
        "U90 REF/K/A" in d and d.startswith("Not checked:") for _, _, d in c
    )
    parts[0] = (
        *ref[:4],
        {
            "ReferenceVoltage": "1.25V",
            "HealthyVoltage": "4V",
            "LowVoltage": "2V",
            "EnableActiveHigh": "yes",
        },
    )
    assert any(
        "inverts the declared enable polarity" in s
        for s in summaries({"a.kicad_sch": design(parts, labels)})
    )
    parts[0] = (
        *ref[:4],
        {
            "ReferenceVoltage": "1.25V",
            "HealthyVoltage": "4V",
            "LowVoltage": "2V",
            "EnableActiveHigh": "no",
        },
    )
    assert summaries({"a.kicad_sch": design(parts, labels)}) == []


def test_production_collector_pinned_evidence_and_limits(monkeypatch):
    from extrude import electrical_reasoning as e

    data = design(
        [
            (
                "C99",
                "Device:C",
                "100uF 6.3V",
                [("1", "~", "passive", 0, 0), ("2", "~", "passive", 10, 0)],
                {},
            )
        ],
        [("VBUS", 0, 0), ("GND", 10, 0)],
    )
    calls = []
    monkeypatch.setattr(
        "extrude.github_history.inventory",
        lambda repo, sha, limit: {
            "files": [{"path": "a.kicad_sch", "type": "blob"}],
            "next_offset": None,
        },
    )

    def blob(repo, sha, path, **kwargs):
        calls.append((repo, sha, path))
        return data

    monkeypatch.setattr("extrude.github_history.regular_blob", blob)
    f, c = e.collect("repo", "a" * 40)
    assert calls == [("repo", "a" * 40, "a.kicad_sch")]
    assert f[0]["evidence"][0]["sha"] == "a" * 40
    for row in f:
        Finding.model_validate(row)
    for row in c:
        Coverage.model_validate(row)
    assert not any("passed" in row["detail"].lower() for row in c)
    monkeypatch.setattr(
        "extrude.github_history.inventory",
        lambda *a, **k: {"files": [], "next_offset": 10000},
    )
    with pytest.raises(ValueError, match="10,000"):
        e.collect("repo", "a" * 40)


def test_audit_runs_whole_design_even_with_no_changed_files(monkeypatch):
    from extrude import (
        workspace_audit as audit,
        electrical_reasoning as e,
        workspace_links,
    )

    monkeypatch.setattr(
        audit.git,
        "changes",
        lambda *a, **k: {"total": 0, "next_offset": None, "files": []},
    )
    monkeypatch.setattr(audit.kicad_audit, "collect", lambda *a: ([], []))
    monkeypatch.setattr(audit.workspace_checks, "collect", lambda *a: ([], []))
    monkeypatch.setattr(workspace_links, "collect", lambda *a: ([], []))
    monkeypatch.setattr(workspace_links, "attach", lambda *a: None)
    calls = []

    def collect(repo, sha):
        calls.append((repo, sha))
        return [
            dict(
                rule_id="electrical.example",
                domain="schematic",
                status="verified",
                severity="warning",
                summary="U90 pin 1: missing source",
                lifecycle="present_at_head",
            )
        ], []

    monkeypatch.setattr(e, "collect", collect)
    report = audit.Audit(
        id="audit",
        base_sha=None,
        repo_id="repo",
        head_sha="a" * 40,
        tool_versions={},
        config_hash="test",
    )
    audit._collect(report)
    assert calls == [("repo", "a" * 40)]
    assert report.findings[0].summary == "U90 pin 1: missing source"

    def fail(*a):
        raise ValueError("Not checked: bounded input failed")

    monkeypatch.setattr(e, "collect", fail)
    report.findings.clear()
    audit._collect(report)
    assert not report.findings
    assert report.coverage[-1].outcome == "unavailable"


def test_hierarchical_ports_and_local_label_scope():
    root = design([resistor("R1", "1k", (0, 0), (10, 0))], [("same", 10, 0)]).decode()
    sheet = """(sheet (at 0 0) (size 20 20) (uuid "child-instance")
        (property "Sheetname" "Child") (property "Sheetfile" "child.kicad_sch")
        (pin "port" input (at 0 0 0)))"""
    root = root[:-1] + sheet + ")"
    child = design([resistor("R2", "1k", (0, 0), (10, 0))], [("same", 10, 0)]).decode()
    child = child[:-1] + ' (hierarchical_label "port" (shape input) (at 0 0 0)))'
    g = build({"root.kicad_sch": root.encode(), "child.kicad_sch": child.encode()})
    r1 = next(p for p in g.parts if p.reference == "R1")
    r2 = next(p for p in g.parts if p.reference == "R2")
    assert r1.pins[0].net == r2.pins[0].net
    assert r1.pins[1].net != r2.pins[1].net
    repeated = root[:-1] + sheet.replace("child-instance", "other-instance") + ")"
    f, c = analyze(
        {"root.kicad_sch": repeated.encode(), "child.kicad_sch": child.encode()}
    )
    assert not f and any("repeated sheet instances" in d for _, _, d in c)


def test_input_voltage_is_not_output_and_optional_crystal_loads_are_not_defects():
    from extrude.electrical_reasoning import output_voltage

    assert output_voltage("Positive 1.5A 35V Linear Regulator, Fixed Output 12V") == 12
    assert output_voltage("250mA LDO, 1.2V output, SOT-89") == 1.2
    assert output_voltage("35V absolute maximum") is None
    crystal = (
        "Y90",
        "Device:Crystal",
        "32.768kHz",
        [("1", "1", "passive", 0, 0), ("2", "2", "passive", 10, 0)],
        {"Footprint": "Crystal:generic"},
    )
    caps = [
        (
            "C90",
            "Device:C",
            "DNF",
            [("1", "~", "passive", 0, 0), ("2", "~", "passive", 20, 0)],
            {},
        ),
        (
            "C91",
            "Device:C",
            "DNF",
            [("1", "~", "passive", 10, 0), ("2", "~", "passive", 20, 0)],
            {},
        ),
    ]
    f, c = analyze({"rtc.kicad_sch": design([crystal, *caps], [("GND", 20, 0)])})
    assert not f
    assert any("integrated load capacitance" in d for _, _, d in c)


def test_i2c_pullups_with_tolerance_notation_are_recognized():
    mcu = (
        "U90",
        "Generic:MCU",
        "controller",
        [("1", "SDA", "bidirectional", 0, 0), ("2", "SCL", "bidirectional", 10, 0)],
        {},
    )
    parts = [
        mcu,
        resistor("R90", "10kR 1%", (0, 0), (20, 0)),
        resistor("R91", "10kR 1%", (10, 0), (20, 0)),
    ]
    assert not summaries({"i2c.kicad_sch": design(parts, [("+3V3", 20, 0)])})


def test_crystal_footprint_must_exist_in_paired_pcb():
    crystal = (
        "Y90",
        "Device:Crystal",
        "8MHz",
        [("1", "1", "passive", 0, 0), ("2", "2", "passive", 10, 0)],
        {"Footprint": "Crystal:generic"},
    )
    files = {
        "board.kicad_sch": design([crystal]),
        "board.kicad_pcb": b"(kicad_pcb (version 20240108))",
    }
    assert any(
        "Y90: crystal is present in the schematic but its footprint is absent" in s
        for s in summaries(files)
    )
