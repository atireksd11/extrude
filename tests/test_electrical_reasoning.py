"""Topology regressions use invented components, independent of the acceptance repos."""

import json
import math
import pytest
from extrude.electrical_graph import build
from extrude.electrical_reasoning import analyze, capacitance, resistance
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
            f"(property {json.dumps(k)} {json.dumps(v, ensure_ascii=False)})" for k, v in fields.items()
        )
        dnp = " (dnp yes)" if props.get("_dnp") else ""
        placed.append(
            f'(symbol (lib_id "{symbol}") (at 0 0 0) (unit 1) (in_bom yes) (on_board yes){dnp} (uuid "{ref}") {properties})'
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
    "value,vdd,regin_floating,vbus,dnp,expected_finding,expected_coverage",
    [
        ("CP2102-GMR_NRND", "5V", False, "VBUS", False,
         "U3: pin 6 VDD is on a 5 V net; CP2102 VDD is rated 3–3.6 V "
         "(absolute maximum 4.2 V). Move the pin to a 3.6 V rail or fit a regulator; "
         "verify against the datasheet.", None),
        ("CP2102-GMR_NRND", "3V3", False, "sense", False, None, None),
        ("CP2102-GMR_NRND", "3V3", True, "VBUS", False,
         "U3: pin 7 REGIN is floating; tie REGIN to the 3.6 V rail when VDD is "
         "externally powered to disable the internal regulator, per the datasheet.", None),
        ("CP2102-GMR_NRND", "3V3", False, "5V", False, None, None),
        ("CP2102N-Axx-xQFN28", "5V", True, "VBUS", False, None,
         "Not checked: U3 CP2102N-Axx-xQFN28 supply limits are not tabulated; "
         "pin voltages not judged."),
        ("CP2102-GMR_NRND", "sense", False, "VBUS", False, None,
         "Not checked: U3 VDD net voltage is unknown; overvoltage cannot be judged."),
        ("CP2102-GMR_NRND", "5V", True, "VBUS", True, None, None),
        ("CH340X", "5V", True, "VBUS", False, None, None),
    ],
    ids=["vdd-5v", "vdd-3v3", "regin-floating", "vbus-5v",
         "cp2102n", "vdd-unknown", "dnp", "unrelated-part"],
)
def test_pin_supply_overvoltage(
    value, vdd, regin_floating, vbus, dnp, expected_finding, expected_coverage
):
    parts = [
        ("U3", "Interface:Bridge", value, [
            ("6", "VDD", "passive", 0, 0),
            ("7", "REGIN", "power_in", 10, 0),
            ("8", "VBUS", "input", 20, 0),
        ], {"_dnp": dnp}),
    ]
    labels = [(vdd, 0, 0), (vbus, 20, 0)]
    if not regin_floating:
        parts.append(resistor("R1", "1k", (10, 0), (30, 0)))
        labels.append(("3V3", 10, 0))

    path = "board.kicad_sch"
    findings, coverage = analyze({path: design(parts, labels)})
    assert [(f["rule_id"], f["summary"]) for f in findings] == (
        [("electrical.overvoltage", expected_finding)] if expected_finding else []
    )
    assert [row for row in coverage if row[1] == "overvoltage"] == (
        [(path, "overvoltage", expected_coverage)] if expected_coverage else []
    )


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


@pytest.mark.parametrize(
    "reference,value,ground_name,marker,dnp,attached",
    [
        ("rR1", "5.1k", "GNDR", "pin", False, None),
        ("R1", "5.1k", "GND", "label", False, None),
        ("lR1", "5.1kΩ", "GNDA", "label", False, None),
        ("R1", "5.1k", "GNDR", "label", False, None),
        ("R1", "5.1k", "GNDPWR", "label", False, None),
        ("R1", "5.1k", "GNDREF", "label", False, None),
        # 4.7 kΩ is within the preserved 4080–6120 Ω window.
        ("R1", "4.7k", "GND", "label", False, None),
        (None, None, None, "label", False, "no load"),
        ("R1", "3.9k", "GND", "label", False, "R1 ~"),
        ("R1", "5.1k", "SIGNAL", "label", False, "R1 ~"),
        ("R1", "5.1k", "GND_SENSE", "label", False, "R1 ~"),
        ("R1", "5.1k", "GND1", "label", False, "R1 ~"),
        ("rR1", "5.1k", "GND", "label", True, "rR1 ~"),
    ],
)
def test_usb_cc_pull_down_recognition(reference, value, ground_name, marker, dnp, attached):
    connector = (
        "J1",
        "Connector:USB_C",
        "USB-C",
        [("1", "D+", "passive", 0, 0), ("2", "CC1", "passive", 10, 0)],
        {},
    )
    parts = [connector]
    labels = []
    if reference:
        parts.append(resistor(reference, value, (10, 0), (20, 0)))
        if marker == "pin":
            parts.append(
                ("#PWR01", "Custom:Ground", ground_name,
                 [("1", ground_name, "power_in", 20, 0)], {})
            )
        else:
            labels.append((ground_name, 20, 0))
    schematic = design(parts, labels)
    if dnp:
        schematic = schematic.replace(
            f'(uuid "{reference}")'.encode(), f'(dnp yes) (uuid "{reference}")'.encode()
        )
    findings, _ = analyze({"usb.kicad_sch": schematic})
    usb_findings = [f for f in findings if f["rule_id"] == "electrical.usb"]
    if attached is None:
        assert usb_findings == []
    else:
        assert [(f["summary"], f["status"]) for f in usb_findings] == [
            (
                "J1: CC1 has no independent 5.1kΩ Rd to GND for a USB-C sink; "
                f"connected to {attached}. Fit separate Rd resistors and remove non-CC connections.",
                "verified",
            )
        ]


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
        and any("shield pins 5" in s for s in f)
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


@pytest.mark.parametrize(
    ("model", "actual_path"),
    [
        ("${KIPRJMOD}/models/part.step", "pcb/Models/Part.STEP"),
        (":MY_LIB:kicad-packages3D/part.step", "shared/kicad-packages3D/Part.STEP"),
        ("models/part.step", "pcb/Models/Part.STEP"),
    ],
)
def test_model_paths_resolve_case_insensitively(model, actual_path):
    path = "pcb/a.kicad_pcb"
    pcb = f'(kicad_pcb (footprint "X" (model "{model}")))'.encode()
    findings, coverage = analyze({path: pcb}, {path, actual_path})
    assert not findings
    assert (path, "models", f"model {model} resolves as {actual_path} with different case") in coverage


def test_model_exact_match_wins_over_case_fallback():
    path = "pcb/a.kicad_pcb"
    pcb = b'(kicad_pcb (footprint "X" (model "${KIPRJMOD}/models/part.step")))'
    inventory = {
        path,
        "another/a.kicad_pro",
        "another/models/Part.STEP",
        "pcb/models/Part.STEP",
        "pcb/models/part.step",
    }
    findings, coverage = analyze({path: pcb}, inventory)
    assert not findings
    assert not any("different case" in detail for _, _, detail in coverage)


@pytest.mark.parametrize(
    ("model", "model_path", "library_marker"),
    [
        (":MY_LIB:kicad-packages3D/part.step", "shared/kicad-packages3D/part.step", None),
        ("${KIPRJMOD}/kicad-packages3D/part.step", "shared/kicad-packages3D/part.step", None),
        ("${KIPRJMOD}/models/part.step", "shared/models/part.step", "shared/X.pretty/X.kicad_mod"),
    ],
)
def test_model_paths_resolve_from_sibling_library_root(model, model_path, library_marker):
    path = "pcb/a.kicad_pcb"
    pcb = f'(kicad_pcb (footprint "X" (model "{model}")))'.encode()
    inventory = {path, "pcb/a.kicad_pro", model_path}
    if library_marker:
        inventory.add(library_marker)
    findings, coverage = analyze({path: pcb}, inventory)
    assert not findings
    assert not any(coverage_path == path for coverage_path, _, _ in coverage)


def test_colon_model_variable_must_be_at_start():
    path = "pcb/a.kicad_pcb"
    model = "models/:MY_LIB:part.step"
    pcb = f'(kicad_pcb (footprint "X" (model "{model}")))'.encode()
    findings, coverage = analyze({path: pcb}, {path, "pcb/models/part.step"})
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "electrical.models"
    assert f"does not resolve at pcb/{model}." in findings[0]["summary"]
    assert not any(coverage_path == path for coverage_path, _, _ in coverage)


@pytest.mark.parametrize(
    "model_dir",
    ["projects/second", "shared", "lib", "lib/footprints/X.pretty", ""],
    ids=["project", "root-schematic", "ancestor", "containing-file", "repo-root"],
)
def test_kiprjmod_model_resolves_from_candidate_base(model_dir):
    path = "lib/footprints/X.pretty/part.kicad_mod"
    files = {
        path: b'(footprint "X" (model "${KIPRJMOD}/models/part.step"))',
        "shared/root.kicad_sch": design([]),
    }
    model_path = "/".join(filter(None, (model_dir, "models/part.step")))
    inventory = {*files, "projects/first/a.kicad_pro", "projects/second/b.kicad_pro", model_path}
    findings, _ = analyze(files, inventory)
    assert not [finding for finding in findings if finding["rule_id"] == "electrical.models"]


def test_kiprjmod_typo_keeps_warning_and_reports_first_candidate():
    path = "lib/footprints/X.pretty/part.kicad_mod"
    files = {
        path: b'(footprint "X" (property "Reference" "J90") (model "${KIPRJMOD}/models/prat.step"))',
        "shared/root.kicad_sch": design([]),
    }
    inventory = {*files, "projects/board.kicad_pro", "projects/models/part.step"}
    findings, _ = analyze(files, inventory)
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "electrical.models"
    assert findings[0]["severity"] == "warning"
    assert findings[0]["summary"] == (
        "J90: referenced 3D STEP file ${KIPRJMOD}/models/prat.step does not resolve at "
        "projects/models/prat.step. Correct the path/case or include the model."
    )


@pytest.mark.parametrize(
    ("model", "coverage_detail"),
    [
        (":MY_LIB:part.step", "external library model"),
        ("${KICAD6_3DMODEL_DIR}/part.step", "external library model"),
        ("/opt/models/part.step", "absolute external model"),
        ("C:/models/part.step", "absolute external model"),
    ],
)
def test_external_model_paths_keep_coverage(model, coverage_detail):
    path = "pcb/a.kicad_pcb"
    pcb = f'(kicad_pcb (footprint "X" (model "{model}")))'.encode()
    findings, coverage = analyze({path: pcb})
    assert not findings
    assert (path, "models", f"Not checked: {coverage_detail} {model}") in coverage


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


@pytest.mark.parametrize("prefix", ["", "r"])
def test_i2c_pullups_with_tolerance_notation_are_recognized(prefix):
    mcu = (
        "U90",
        "Generic:MCU",
        "controller",
        [("1", "SDA", "bidirectional", 0, 0), ("2", "SCL", "bidirectional", 10, 0)],
        {},
    )
    parts = [
        mcu,
        ("U91", "Generic:Sensor", "sensor", mcu[3], {}),
        resistor(f"{prefix}R90", "10kR 1%", (0, 0), (20, 0)),
        resistor(f"{prefix}R91", "10kR 1%", (10, 0), (20, 0)),
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


@pytest.mark.parametrize(
    "value,expected",
    [
        ("10u", 10e-6),
        ("10uf", 10e-6),
        ("2.2uF", 2.2e-6),
        ("10uF/25V(20%)", 10e-6),
        ("100n", 100e-9),
        ("0.1uf", 0.1e-6),
        ("18pF", 18e-12),
        ("1uF", 1e-6),
        ("1 μF", 1e-6),
        ("10mF", 10e-3),
        ("DNP", None),
        ("10m", None),
        ("100foo", None),
    ],
)
def test_capacitance_units(value, expected):
    assert capacitance(value) == expected


CERAMIC = "Capacitor_SMD:C_0805_2012Metric"
TANTALUM = "Capacitor_Tantalum_SMD:CP_Elec_3528"
ELECTROLYTIC = "Capacitor_SMD:CP_Elec_5x5.3"


def ldo_cap(ref, value="10uF", footprint=CERAMIC, *, dnp=False, return_y=10):
    return ref, f"Device:{ref}", value, [
        ("1", "~", "passive", 10, 0),
        ("2", "~", "passive", 10, return_y),
    ], {"Footprint": footprint, "_dnp": dnp}


def ldo_design(caps, *, ref="U1", value="AMS1117", symbol="Regulator_Linear:AMS1117",
               output_pins=(("2", "VO", "power_out", 10, 0),), extra_parts=()):
    regulator = ref, symbol, value, [
        ("1", "ADJ", "input", 20, 0),
        ("3", "VI", "power_in", 30, 0),
        *output_pins,
    ], {"Comment": "A property mentioning 1117"}
    findings, coverage = analyze({
        "ldo.kicad_sch": design([regulator, *caps, *extra_parts], [
            ("GND", 10, 10), ("+3V3", 10, 0),
        ]),
    })
    return [row for row in findings if row["rule_id"] == "electrical.ldo"], [
        detail for _, family, detail in coverage if family == "ldo"
    ]


def test_ldo_ceramic_bulk_message():
    findings, _ = ldo_design([ldo_cap("C11"), ldo_cap("C13", "2.2uF")])
    assert len(findings) == 1
    finding = findings[0]
    assert (finding["severity"], finding["status"]) == ("warning", "verified")
    assert finding["summary"] == (
        "U1 AMS1117 output +3V3: fitted bulk output capacitance is ceramic-only "
        "(C11 10uF, C13 2.2uF) — the 1117 family needs tantalum/electrolytic output "
        "capacitance with ESR in the 0.3–22 Ω window (AMS1117: 22 µF solid tantalum; "
        "LM1117: ≥10 µF tantalum, ESR 0.3–22 Ω). Ceramic MLCC ESR is a few mΩ, "
        "below the window, and the loop can oscillate. Fit a tantalum or aluminium "
        "electrolytic bulk capacitor on this rail, or add series resistance, or use "
        "an LDO designed for ceramics."
    )


@pytest.mark.parametrize("footprint,dnp", [(TANTALUM, False), (ELECTROLYTIC, False),
                                           (TANTALUM, True)])
def test_ldo_fitted_polarized_cap_prevents_warning(footprint, dnp):
    findings, _ = ldo_design([ldo_cap("C1", dnp=dnp), ldo_cap("C2", footprint=footprint)])
    assert not findings


@pytest.mark.parametrize("footprint", ["custom:Capacitor", ""])
def test_ldo_unknown_dielectric(footprint):
    findings, coverage = ldo_design([ldo_cap("C1"), ldo_cap("C2", footprint=footprint)])
    assert not findings
    assert (
        "Not checked: U1 AMS1117 output +3V3 has a bulk output capacitor of unknown "
        "dielectric (C2); ceramic-only cannot be established."
    ) in coverage


@pytest.mark.parametrize("cap", [ldo_cap("C1", dnp=True), ldo_cap("C1", "100n"),
                                 ldo_cap("C1", return_y=40)])
def test_ldo_no_fitted_bulk_output_cap(cap):
    findings, coverage = ldo_design([cap])
    assert not findings
    assert (
        "Not checked: U1 AMS1117 output +3V3 has no fitted bulk (≥1 µF) output "
        "capacitor in this schematic; output capacitance cannot be evaluated."
    ) in coverage


def test_ldo_deduplicates_passive_output_pins_and_accepts_unannotated_reference():
    findings, _ = ldo_design(
        [ldo_cap("C1")], ref="U?", value="NCP1117",
        symbol="Custom:Device",
        output_pins=(("2", "OUTPUT_1", "passive", 10, 0),
                     ("4", "OUTPUT_2", "passive", 10, 0)),
    )
    assert len(findings) == 1
    assert findings[0]["summary"].startswith("U? NCP1117 output +3V3:")


@pytest.mark.parametrize(
    "value,symbol,count",
    [
        ("Voltage Regulator", "Custom:ldl1117s30r", 0),
        ("tlv1117lv", "Custom:Device", 0),
        ("TLV1117", "Custom:Device", 1),
        ("LD1117", "Custom:Device", 1),
        ("LM1117-ADJ", "Custom:Device", 1),
        ("Other regulator", "Custom:Device", 0),
        ("Voltage Regulator", "Custom:NCP1117", 1),
    ],
)
def test_ldo_identifies_family_by_value_or_symbol(value, symbol, count):
    findings, _ = ldo_design([ldo_cap("C1")], value=value, symbol=symbol)
    assert len(findings) == count


def test_ldo_never_uses_pin_kind_to_identify_output():
    findings, coverage = ldo_design(
        [ldo_cap("C1")], output_pins=(("2", "SENSE", "power_out", 10, 0),),
    )
    assert not findings
    assert (
        "Not checked: U1 AMS1117 has no identifiable output pin (VO/VOUT/OUTPUT); "
        "LDO output capacitance cannot be evaluated."
    ) in coverage


def test_ldo_shared_rail_only_checks_regulator_on_output_side():
    downstream = "U2", "Custom:Downstream", "NCP1117", [
        ("1", "IN", "power_in", 10, 0),
        ("2", "OUT", "power_out", 40, 0),
    ], {}
    findings, _ = ldo_design([ldo_cap("C1")], extra_parts=[downstream])
    assert len(findings) == 1
    assert findings[0]["summary"].startswith("U1 AMS1117 output +3V3:")


@pytest.mark.parametrize(
    ("case", "floating", "missing"),
    [
        ("floating", ("SH1", "SH2"), False),
        ("grounded", (), False),
        ("rc", (), False),
        ("numbered name", ("SH1",), False),
        ("missing", (), True),
        ("dnp", (), False),
        ("dnp missing", (), False),
        ("omitted note", ("SH1", "SH2"), False),
        ("one cc pin", (), False),
        ("no-connect marker", ("SH1", "SH2"), False),
        ("split", ("SH2",), False),
        ("legacy USB", ("SH1", "SH2"), False),
    ],
)
def test_usb_shield_topology(case, floating, missing):
    symbol = "Connector:USB_B_Micro" if case == "legacy USB" else "Vendor:UJ32-C"
    pins = [("A5", "CC1", "passive", 0, 0), ("B12", "GND__3", "passive", 50, 0)]
    if case == "legacy USB":
        pins += [("A6", "D+", "passive", 10, 0), ("A7", "D-", "passive", 15, 0)]
    elif case != "one cc pin":
        pins.append(("B5", "CC2", "passive", 10, 0))
    if case == "numbered name":
        pins.append(("SH1", "SH1", "passive", 20, 0))
    elif case not in {"missing", "dnp missing"}:
        pins += [
            ("SH1", "SHIELD", "passive", 20, 0),
            ("SH2", "SHIELD__1", "passive", 30, 0),
        ]

    parts = [("J3", symbol, "Receptacle", pins, {"_dnp": case.startswith("dnp")})]
    labels = []
    wires = []
    if case in {"grounded", "split"}:
        ground = ("#PWR01", "power:GND", "GND", [("1", "GND", "power_in", 20, 0)], {})
        parts.append(ground)
        if case == "grounded":
            wires.append((20, 0, 30, 0))
    elif case == "rc":
        parts += [
            resistor("R3", "1M", (20, 0), (60, 0)),
            ("C4", "Device:C", "100n", [("1", "~", "passive", 20, 0),
                                       ("2", "~", "passive", 60, 0)], {}),
        ]
        labels.append(("GND", 60, 0))
        wires.append((20, 0, 30, 0))

    schematic = design(parts, labels=labels, wires=wires)
    if case == "omitted note":
        schematic = schematic[:-1] + b' (text "J3 Omitted, insufficient space" (at 0 1 0)))'
    if case == "no-connect marker":
        schematic = schematic[:-1] + b' (no_connect (at 20 0) (uuid "nc")))'
    findings, coverage = analyze({"shield.kicad_sch": schematic})
    shields = [f for f in findings if f["rule_id"] == "electrical.usb_shield"]
    assert len(shields) == bool(floating)
    if floating:
        connector = "USB" if case == "legacy USB" else "USB-C"
        assert shields[0]["summary"] == (
            f"J3: {connector} shield pins {', '.join(floating)} are unconnected — "
            "the connector shell has no ground path. Provide an intentional "
            "chassis/ground termination (direct GND, or an RC termination)."
        )
        assert (shields[0]["severity"], shields[0]["status"]) == ("warning", "verified")
    missing_shield = (
        "Not checked: J3 USB-C connector has no shield pin in its symbol; "
        "shield termination cannot be evaluated from the schematic."
    )
    assert (missing_shield in [detail for _, _, detail in coverage]) == missing
    if case == "legacy USB":
        assert any(
            f["rule_id"] == "electrical.protection" and "ESD" in f["summary"]
            for f in findings
        )


@pytest.mark.parametrize(
    "value, cap_values, crystal_dnp, cap_dnp, expected",
    [
        ("ABM7-12.000MHZ-D2Y-T", ("18pF", "18pF"), False, False, "12"),
        ("ABM7-12.000MHZ-D2Y-T", ("30pF", "30pF"), False, False, ""),
        ("ABM7-12.000MHZ-D2Y-T", ("27pF", "27pF"), False, False, ""),
        ("ABM7-12.000MHZ-D2Y-T", ("22pF", "22pF"), False, False, "14"),
        ("ABM7-12.000MHZ-D2Y-T", ("18pF", "27pF"), False, False, "13.8"),
        ("ABM7-12.000MHZ-D-2-Y-T", ("18pF", "18pF"), False, False, "12"),
        ("MAIN_XTAL", ("18pF", "18pF"), False, False, "unknown"),
        ("12 MHz", ("18pF", "18pF"), False, False, "unknown"),
        ("12MHz 18pF", ("18pF", "18pF"), False, False, "unknown"),
        ("ABM7-12.000MHZ-D2Y-T", ("18pF", "18pF"), True, False, "dnp"),
        ("ABM7-12.000MHZ-D2Y-T", ("18pF",), False, False, "optional"),
        ("ABM7-12.000MHZ-D2Y-T", ("18pF", "18pF"), False, True, "optional"),
        ("ABM7-12.000MHZ-D2Y-T", ("18pF", "18pF", "18pF"), False, False, "count"),
        ("ABM7-12.000MHZ-D2Y-T", ("18pF", "50V"), False, False, "unparseable"),
    ],
)
def test_crystal_load(value, cap_values, crystal_dnp, cap_dnp, expected):
    ref = "Y?" if value == "12MHz 18pF" else "X1"
    crystal = (
        ref,
        "Device:Crystal",
        value,
        [("1", "~", "passive", 0, 0), ("2", "~", "passive", 10, 0)],
        {"Footprint": "Crystal:generic", "_dnp": crystal_dnp},
    )
    caps = [
        (
            f"C{8 + i}",
            f"Device:C{i}",
            cap_value,
            [("1", "~", "passive", 10 * (i % 2), 0), ("2", "~", "passive", 20, 0)],
            {"_dnp": cap_dnp and i == 1},
        )
        for i, cap_value in enumerate(cap_values)
    ]
    findings, coverage = analyze(
        {"rtc.kicad_sch": design([crystal, *reversed(caps)], [("GND", 20, 0)])}
    )
    clock_coverage = [
        (check, detail)
        for path, check, detail in coverage
        if path == "rtc.kicad_sch" and check in {"clock", "clock_load"}
    ]
    if expected in {"12", "14", "13.8"}:
        assert [row["rule_id"] for row in findings] == ["electrical.clock_load"]
        assert f"effective load of ~{expected} pF" in findings[0]["summary"]
        assert findings[0]["severity"] == "warning"
        assert not clock_coverage
        if value == "ABM7-12.000MHZ-D2Y-T" and expected == "12":
            assert findings[0]["summary"] == (
                "X1 ABM7-12.000MHZ-D2Y-T: fitted load capacitors C8 18pF + C9 18pF "
                "give an effective load of ~12 pF (series 9 pF + 3 pF stray) against "
                "the crystal's specified 18 pF load capacitance — the crystal is underloaded "
                "and will run off-frequency, with reduced start-up margin. Fit ~30 pF "
                "load capacitors (2 × (CL − stray)) or a crystal specified for the fitted capacitance."
            )
    elif expected == "dnp":
        assert [row["rule_id"] for row in findings] == ["electrical.clock"]
        assert "crystal assembly is incomplete" in findings[0]["summary"]
        assert not clock_coverage
    else:
        assert not findings
        if expected == "unknown":
            assert clock_coverage == [
                (
                    "clock_load",
                    f"Not checked: {ref} crystal load capacitance cannot be evaluated — "
                    f"load capacitance (CL) is not known for {value}; add the part "
                    "to the crystal load-capacitance table with a datasheet reference.",
                )
            ]
        elif expected == "optional":
            assert len(clock_coverage) == 1
            assert clock_coverage[0][0] == "clock"
            assert "optional/unvalued external load capacitors" in clock_coverage[0][1]
        elif expected == "count":
            assert clock_coverage == [
                ("clock_load", "Not checked: X1 has 3 load capacitors on its nets; "
                 "the two-capacitor load calculation does not apply.")
            ]
        elif expected == "unparseable":
            assert len(clock_coverage) == 1
            assert clock_coverage[0][0] == "clock_load"
            assert "from the fitted capacitor values" in clock_coverage[0][1]
        else:
            assert not clock_coverage


@pytest.mark.parametrize(
    "case,pads,expected_count",
    [
        ("floating", '(pad "" thru_hole oval)' * 4, 4),
        ("grounded", '(pad "" thru_hole oval (net "GND"))' * 4, 0),
        ("mixed", '(pad "" thru_hole oval (net "GND")) (pad "" thru_hole oval)' * 2, 2),
        ("mounting", '(pad "" np_thru_hole circle)' * 2, 0),
        ("smd", '(pad "" smd rect)' * 11, 0),
        ("numbered", '(pad "0" thru_hole oval)', 0),
        ("dnp", '(pad "" thru_hole oval)', 0),
        ("missing footprint", "", 0),
        ("missing board", "", 0),
        ("pseudo-net", '(pad "" thru_hole oval (net "unconnected-(J1-SH)"))', 1),
        ("symbol gate", '(pad "" thru_hole oval)', 1),
        ("two connectors", '(pad "" thru_hole oval)', 1),
        ("non-usb", '(pad "" thru_hole oval)', 0),
    ],
)
def test_usb_shield_pcb(case, pads, expected_count):
    symbol = "Connector:USB_Test" if case == "symbol gate" else "Connector:Test"
    names = {
        "symbol gate": ("D+", "D-"),
        "non-usb": ("IN", "OUT"),
    }.get(case, ("CC1", "CC2"))
    pins = [(str(i), name, "passive", i * 10, 0) for i, name in enumerate(names, 1)]
    parts = [("J1", symbol, "connector", pins, {"_dnp": case == "dnp"})]

    def footprint(ref, rows):
        return f'(footprint "Test:A" (at 1 2) (layer "F.Cu") (property "Reference" "{ref}") {rows})'

    footprints = "" if case == "missing footprint" else footprint("J1", pads)
    if case == "two connectors":
        parts.append(("J2", "Connector:Second", "connector",
                      [(n, name, kind, x, 20) for n, name, kind, x, _ in pins], {}))
        footprints += footprint("J2", '(pad "" thru_hole oval (net "GND"))')

    files = {"test.kicad_sch": design(parts)}
    if case != "missing board":
        files["test.kicad_pcb"] = f"(kicad_pcb (version 20251028) {footprints})".encode()
    findings, coverage = analyze(files)
    rows = [row for row in findings if row["rule_id"] == "electrical.usb_shield_pcb"]
    if expected_count:
        row, = rows
        connector = "USB" if case == "symbol gate" else "USB-C"
        tabs = "tab has" if expected_count == 1 else "tabs have"
        assert row["summary"] == (
            f"J1: {connector} connector shell has no ground path on the PCB — "
            f"{expected_count} thru-hole shield {tabs} no net. Provide an intentional "
            "chassis/ground termination (direct GND, or an RC termination)."
        )
        assert (row["severity"], row["status"]) == ("warning", "verified")
    else:
        assert rows == []
    shield_coverage = [row for row in coverage if row[1] == "usb_shield_pcb"]
    if case == "missing footprint":
        assert shield_coverage == [(
            "test.kicad_pcb", "usb_shield_pcb",
            "Not checked: J1 USB connector has no paired PCB footprint; "
            "shield-tab termination cannot be evaluated from the board.",
        )]
    else:
        assert shield_coverage == []


def test_assembly_scope_guard_is_per_root():
    from test_trust_blockers import board, device

    findings, coverage = analyze({
        "split.kicad_sch": design([device(ref) for ref in ("U1", "U2", "U3", "U4")]),
        "split.kicad_pcb": board(["U1", "U9"]),
        "other.kicad_sch": design([device("U3")]),
        "other.kicad_pcb": board(["U3"]),
    })

    assert not [f for f in findings if f["rule_id"] == "electrical.assembly"]
    assert [row for row in coverage if row[0].endswith(".kicad_pcb") and row[1] == "assembly"] == [
        ("other.kicad_pcb", "assembly", "Compared paired schematic and PCB component inventories."),
        ("split.kicad_pcb", "assembly",
         "Not checked: split.kicad_sch schematic covers more hardware than the paired board "
         "(1 of 4 fitted references present on split.kicad_pcb); "
         "split/multi-board design — assembly comparison skipped."),
    ]


@pytest.mark.parametrize(
    "schematic_refs,pcb_refs,expected_findings",
    [
        pytest.param(["U1", "U2", "U3"], ["U1", "U2"], ["U3"], id="missing-footprint"),
        pytest.param(["U1", "U2"], ["U1"], ["U2"], id="exactly-half"),
        pytest.param(["U1", "U2"], [], [], id="empty-board"),
        pytest.param(["U1", "U1_r1", "U1_r2"], ["U1"], [], id="repeated-sheet-refs"),
    ],
)
def test_assembly_scope_guard_for_single_root(schematic_refs, pcb_refs, expected_findings):
    from test_trust_blockers import board, device

    schematic_path = "main.kicad_sch"
    board_path = "main.kicad_pcb"
    findings, coverage = analyze({
        schematic_path: design([device(ref) for ref in schematic_refs]),
        board_path: board(pcb_refs),
    })

    assembly = [f["summary"] for f in findings if f["rule_id"] == "electrical.assembly"]
    assert [summary.split(":")[0] for summary in assembly] == expected_findings
    assert all("has no footprint on the paired board" in summary for summary in assembly)

    if expected_findings:
        detail = "Compared paired schematic and PCB component inventories."
    else:
        detail = (
            f"Not checked: {schematic_path} schematic covers more hardware than the paired board "
            f"({len(pcb_refs)} of {len(schematic_refs)} fitted references present on {board_path}); "
            "split/multi-board design — assembly comparison skipped."
        )
    assert [row for row in coverage if row[1] == "assembly"] == [(board_path, "assembly", detail)]


@pytest.mark.parametrize(
    "fitted, dnp, present, missing",
    [
        pytest.param(["U1"], ["U2"], ["U1"], [], id="dnp-without-footprint"),
        pytest.param(["U1", "U2", "U3"], ["U4", "U5", "U6", "U7"],
                     ["U1", "U2"], ["U3"], id="dnp-heavy"),
        pytest.param([], ["U1", "U2", "U3"], ["U1"], [], id="all-dnp"),
        pytest.param(
            [f"J{i}" for i in range(1, 12)]
            + ["SW1", "SW3", "SW6", "R36", "R37", "R38", "C32", "C33", "C34", "U13", "UE1"],
            ["U99"], [f"J{i}" for i in range(1, 12)] + ["REF**"],
            ["SW1", "SW3", "SW6", "R36", "R37", "R38", "C32", "C33", "C34", "U13", "UE1"],
            id="astra-fitted-boundary",
        ),
    ],
)
def test_assembly_scope_guard_uses_fitted_parts(fitted, dnp, present, missing):
    from test_trust_blockers import board, device

    parts = [device(ref) for ref in fitted]
    parts.extend((*device(ref)[:-1], {"_dnp": True}) for ref in dnp)
    findings, coverage = analyze({
        "main.kicad_sch": design(parts),
        "main.kicad_pcb": board(present),
    })

    assembly = [f["summary"] for f in findings if f["rule_id"] == "electrical.assembly"]
    assert [summary.split(":")[0] for summary in assembly] == missing
    assert all("has no footprint on the paired board" in summary for summary in assembly)
    assembly_coverage = [detail for _, family, detail in coverage if family == "assembly"]
    if "REF**" in present:
        assert assembly_coverage.pop(0) == (
            "Skipped 1 placeholder footprint(s) (REF**): un-annotated, no schematic symbol expected."
        )
    assert assembly_coverage == ["Compared paired schematic and PCB component inventories."]
