"""Whole-design topology checks. No chip catalogue and no inferred clean bill.

Numerical limits come from explicit fields, named supply/reference nets, or
protocol specifications. Unknown silicon capabilities remain not checked.
"""

import csv
import io
import re
import posixpath
from extrude.electrical_graph import build
from extrude.workspace_checks import evidence

FAMILIES = (
    "usb",
    "divider",
    "capacitor",
    "clock",
    "assembly",
    "switch",
    "pullup",
    "protection",
    "polarity",
    "models",
)


def resistance(value):
    value = value.strip().replace("Ω", "").replace("ohm", "")
    m = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*([RrKkMm]?)(\d*)(?:[Rr])?(?:\s*(?:±|\+/-)?\s*\d+(?:\.\d+)?\s*%)?",
        value,
    )
    if not m:
        return None
    a, scale, b = m.groups()
    return (
        float(a + ("." + b if b else ""))
        * {"": 1, "r": 1, "R": 1, "k": 1000, "K": 1000, "m": 1e-3, "M": 1e6}[scale]
    )


def volts(text):
    m = re.search(r"(?i)(\d+(?:\.\d+)?)\s*V(\d*)", text)
    return float(m[1] + ("." + m[2] if m[2] else "")) if m else None


def output_voltage(description):
    """Only an explicitly described output, never input/absolute maximum."""
    patterns = (
        r"(?i)(\d+(?:\.\d+)?\s*V\d*)\s+(?:fixed\s+)?output",
        r"(?i)(?:fixed\s+)?output\s+(\d+(?:\.\d+)?\s*V\d*)",
    )
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return volts(match[1])
    return None


def _analyze_design(files, paths=None):
    """Pure entry point used by production and pinned-repository evaluation."""
    paths = set(paths or files)
    g = build(files)
    findings = []
    coverage = []
    seen = set()

    def emit(family, part, message, pins=(), other=()):
        if len(findings) >= 500:
            item = (
                "",
                "graph",
                "Not checked: electrical finding limit of 500 reached.",
            )
            if item not in coverage:
                coverage.append(item)
            return
        key = (family, part.path, part.reference, message)
        if key in seen:
            return
        seen.add(key)
        findings.append(
            dict(
                rule_id="electrical." + family,
                domain="schematic",
                status="verified",
                severity="warning",
                summary=f"{part.reference}: {message}",
                lifecycle="present_at_head",
                sources=[
                    (
                        part.path,
                        f"{part.reference} ({part.value}) "
                        + ", ".join(f"pin {p.number} {p.name}" for p in pins),
                    ),
                    *other,
                ],
            )
        )

    def peers(pin):
        return g.nets.get(pin.net, [])

    def names(net):
        return sorted(g.names.get(net, set()))

    def ground(net):
        return any(
            re.fullmatch(r"(?i)(GND|AGND|DGND|VSS|GNDA)", n)
            for n in [*names(net), *(p.name for p in g.nets.get(net, []))]
        )

    def voltage(net):
        if ground(net):
            return 0.0
        candidates = [volts(n) for n in names(net)]
        candidates += [
            volts(p.name)
            for p in g.nets.get(net, [])
            if p.kind in {"power_in", "power_out"}
        ]
        vals = {v for v in candidates if v is not None}
        if len(vals) == 1:
            return vals.pop()
        if any(re.fullmatch(r"(?i)\+?VBUS(?:_.*)?", n) for n in names(net)) or any(
            p.name == "VBUS" for p in g.nets.get(net, [])
        ):
            return 5.0
        return None

    board_references = None
    board_path = next((p for p in files if p.endswith(".kicad_pcb")), None)
    if board_path and g.parts:
        from extrude.parse.kicad_pcb import parse_board

        try:
            board_references = {
                p.reference for p in parse_board(files[board_path]).footprints
            }
        except ValueError:
            coverage.append(
                (
                    board_path,
                    "clock",
                    "Not checked: PCB footprint inventory could not be parsed.",
                )
            )
    byref = {(p.path, p.reference): p for p in g.parts}
    resistors = [
        p
        for p in g.parts
        if p.reference.startswith("R")
        and len(p.pins) == 2
        and p.fitted
        and resistance(p.value) is not None
        and resistance(p.value) > 0
    ]

    def opposite(part, net):
        return next((p.net for p in part.pins if p.net != net), None)

    def supply(net):
        return (voltage(net) or 0) > 0 or any(
            re.fullmatch(r"(?i)(VCC|VDD|VDDA|VDDIO|VCCIO|VCCA|VSYS)", n)
            for n in [
                *names(net),
                *(
                    p.name
                    for p in g.nets.get(net, [])
                    if p.kind in {"power_in", "power_out"}
                ),
            ]
        )

    def pullup(net):
        return any(
            any(p.net == net for p in r.pins) and supply(opposite(r, net))
            for r in resistors
        )

    for part in g.parts:
        if part.reference.startswith("#"):
            continue
        pins = part.pins
        # Connector identities and pin functions are read from the embedded symbol.
        usb = "USB" in part.symbol.upper() and any(
            p.name in {"D+", "D-", "DP", "DM"} for p in pins
        )
        if usb:
            for p in pins:
                if p.name in {"CC1", "CC2"}:
                    rd = [
                        r
                        for r in resistors
                        if any(q.net == p.net for q in r.pins)
                        and ground(opposite(r, p.net))
                        and 4080 <= resistance(r.value) <= 6120
                    ]
                    if not rd:
                        attached = ", ".join(
                            f"{q.reference} {q.name}"
                            for q in peers(p)
                            if q.reference != part.reference
                        )
                        emit(
                            "usb",
                            part,
                            f'{p.name} has no independent 5.1kΩ Rd to GND for a USB-C sink; connected to {attached or "no load"}. Fit separate Rd resistors and remove non-CC connections.',
                            [p],
                        )
                if p.name in {"D+", "D-", "DP", "DM"}:
                    uart = [
                        q
                        for q in peers(p)
                        if re.search(
                            r"(?i)(U[0-9]?TXD|U[0-9]?RXD|UART|TXD[0-9]?|RXD[0-9]?)",
                            q.name,
                        )
                    ]
                    # A USB/UART bridge's USB pins are fine; its UART pins aren't.
                    for q in uart:
                        emit(
                            "usb",
                            part,
                            f"{p.name} routes to {q.reference} pin {q.number} {q.name}, a UART function rather than a USB data pin. Route the pair to documented native USB D+/D- pins or a USB bridge.",
                            [p, q],
                        )
            shield = [p for p in pins if p.name.upper() in {"SHIELD", "SH", "S"}]
            for p in shield:
                if len(peers(p)) == 1:
                    emit(
                        "protection",
                        part,
                        "SHIELD is unconnected. Provide an intentional chassis/ground termination.",
                        [p],
                    )
            data = [p for p in pins if p.name in {"D+", "D-", "DP", "DM"}]
            protected = any(
                re.search(
                    r"(?i)(ESD|TVS|transient.{0,20}suppress|surge.{0,20}protect)",
                    byref[q.path, q.reference].symbol
                    + " "
                    + byref[q.path, q.reference].value
                    + " "
                    + byref[q.path, q.reference].properties.get(
                        "_symbol_description", ""
                    ),
                )
                for p in data
                for q in peers(p)
                if q.reference != part.reference
            )
            if data and not protected:
                # Absence is a protection review, not proof of electrical failure.
                emit(
                    "protection",
                    part,
                    "D+/D- have no identifiable external ESD protection in this schematic. Add a suitable low-capacitance ESD array or document integrated protection.",
                    data,
                )
                findings[-1]["status"] = "suggestion"
        if (
            part.reference.startswith("J")
            and re.search(r"(?i)(TRRS|Jack|Connector)", part.symbol)
            and re.search(r"(?i)(Resistor|\bR_\d)", part.footprint)
        ):
            emit(
                "assembly",
                part,
                f"connector symbol has resistor footprint {part.footprint}; its pads/mechanics cannot implement this jack. Assign the connector footprint.",
                pins,
            )
        # Regulator symbol/value discrepancies are evidence, not guessed MPN limits.
        if (
            "Regulator" in part.symbol
            and part.value not in part.symbol
            and re.split(r"[-_0-9]", part.value)[0].upper()
            != re.split(r"[-_0-9]", part.symbol.split(":")[-1])[0].upper()
        ):
            emit(
                "assembly",
                part,
                f'symbol {part.symbol} ({part.properties.get("_symbol_description", "output unspecified")}) disagrees with fitted Value {part.value}; output voltage and pin compatibility are not established. Use the fitted regulator symbol and verify its documented output.',
                pins,
            )
        if part.reference.startswith("C") and len(pins) == 2 and part.fitted:
            rating = volts(
                " ".join(
                    [
                        part.value,
                        *[
                            v
                            for k, v in part.properties.items()
                            if re.sub(r"[^a-z]", "", k.lower())
                            in {"voltage", "voltagerating", "ratedvoltage"}
                        ],
                    ]
                )
            )
            a, b = (voltage(p.net) for p in pins)
            if rating and a is not None and b is not None and abs(a - b) > 0.7 * rating:
                emit(
                    "capacitor",
                    part,
                    f"{part.value} sees {abs(a-b):g}V ({100*abs(a-b)/rating:.1f}% of {rating:g}V rating), above the 70% derating limit. Select a higher voltage rating.",
                    pins,
                )
        if (
            "Regulator" in part.symbol
            and part.value not in part.symbol
            and re.split(r"[-_0-9]", part.value)[0].upper()
            != re.split(r"[-_0-9]", part.symbol.split(":")[-1])[0].upper()
        ):
            declared = output_voltage(part.properties.get("_symbol_description", ""))
            outputs = [p for p in pins if p.kind == "power_out"]
            for p in outputs:
                nominal = voltage(p.net)
                if declared and nominal and abs(declared - nominal) > 0.05:
                    emit(
                        "assembly",
                        part,
                        f"symbol specifies {declared:g}V output but fitted Value is {part.value} and output pin {p.number} {p.name} is on a {nominal:g}V net. The symbol and intended fitted output disagree. Select the fitted part symbol and verify its output and pinout.",
                        [p],
                    )
        if "Crystal" in part.symbol:
            if board_references is not None and part.reference not in board_references:
                emit(
                    "clock",
                    part,
                    "crystal is present in the schematic but its footprint is absent from the paired PCB. Add the crystal footprint or document the alternative clock source.",
                    pins,
                    [(board_path, part.reference)],
                )
            caps = [
                c
                for c in g.parts
                if c.reference.startswith("C")
                and any(ground(q.net) for q in c.pins)
                and any(
                    p.net == q.net and not ground(p.net) for p in pins for q in c.pins
                )
            ]
            absent = [
                c.reference
                for c in caps
                if not c.fitted or not re.search(r"\d", c.value)
            ]
            if not part.in_bom or not part.fitted or not part.footprint:
                emit(
                    "clock",
                    part,
                    f'crystal assembly is incomplete: BOM included={part.in_bom}, fitted={part.fitted}, footprint={part.footprint or "missing"}; missing/unvalued/DNP load capacitors: {", ".join(absent) or ("not both present" if len(caps)<2 else "none")}. Fit the crystal and specified load capacitors, or document an internal-clock configuration.',
                    pins,
                )
            elif absent or len(caps) < 2:
                coverage.append(
                    (
                        part.path,
                        "clock",
                        f"Not checked: {part.reference} has optional/unvalued external load capacitors; integrated load capacitance must be checked in the oscillator documentation before a defect verdict.",
                    )
                )
        roles = {p.name.upper(): p for p in pins}
        if {"B", "E", "C"} <= roles.keys():
            b, e = roles["B"], roles["E"]
            drivers = []
            for r in resistors:
                if any(p.net == e.net for p in r.pins):
                    drivers += [
                        p
                        for p in g.nets.get(opposite(r, e.net), [])
                        if p.kind in {"output", "bidirectional"}
                    ]
            if (
                ground(b.net)
                and drivers
                and "NPN" in part.properties.get("_symbol_description", "").upper()
            ):
                emit(
                    "switch",
                    part,
                    f'base B is grounded while emitter E is driven through a resistor by {", ".join(p.reference+" "+p.name for p in drivers)}. This reverses the usual low-side switch drive and cannot forward-bias an NPN base-emitter junction from a positive GPIO. Connect emitter to GND and drive base through the resistor after verifying transistor polarity.',
                    [b, e, *drivers],
                )
        for p in pins:
            signal = "/".join([p.name, *names(p.net)])
            if re.search(
                r"(?i)(\bSDA\b|\bSCL\b|DDC[_/ -]*(SDA|SCL|DATA|CLK|CLOCK))", signal
            ) and not pullup(p.net):
                # Only one report per physical net.
                key = ("pullup", p.net)
                if key not in seen:
                    seen.add(key)
                    emit(
                        "pullup",
                        part,
                        f"{p.name} ({signal}) has no external pull-up to a known supply. I2C/DDC open-drain signaling requires pull-ups; fit them or document pull-ups on the connected module.",
                        [p],
                    )
                    findings[-1]["status"] = "suggestion"
        # Reset/strap requirements are explicit semantics, not GPIO numbers.
        for p in pins:
            if p.kind == "input" and re.fullmatch(
                r"(?i)(?:~\{)?(?:N?RST|RESET_N|NRESET|BOOT)(?:\})?", p.name
            ):
                if not pullup(p.net) and part.properties.get(
                    "InternalPullup", ""
                ).lower() not in {"yes", "true", "1"}:
                    coverage.append(
                        (
                            part.path,
                            "pullup",
                            f"Not checked: {part.reference} pin {p.number} {p.name} has no external pull-up; datasheet/internal pull-up and strap polarity are required before a verdict.",
                        )
                    )
        # Shunt-reference/comparator polarity needs sourced operating limits.
        # Never substitute a familiar chip's threshold for absent metadata.
        if {"REF", "K", "A"} <= roles.keys():
            ref, k, a = roles["REF"], roles["K"], roles["A"]
            threshold = volts(part.properties.get("ReferenceVoltage", ""))
            healthy = volts(part.properties.get("HealthyVoltage", ""))
            low = volts(part.properties.get("LowVoltage", ""))
            active = part.properties.get("EnableActiveHigh", "").lower()
            branches = [r for r in resistors if any(p.net == ref.net for p in r.pins)]
            lower = [r for r in branches if ground(opposite(r, ref.net))]
            upper = [r for r in branches if not ground(opposite(r, ref.net))]
            if (
                all(v is not None for v in (threshold, healthy, low))
                and len(lower) == len(upper) == 1
                and ground(a.net)
                and active in {"yes", "true", "1", "no", "false", "0"}
            ):
                ratio = resistance(lower[0].value) / (
                    resistance(lower[0].value) + resistance(upper[0].value)
                )
                healthy_high = healthy * ratio < threshold
                low_high = low * ratio < threshold
                enabled_high = active in {"yes", "true", "1"}
                if healthy_high != enabled_high or low_high == enabled_high:
                    emit(
                        "polarity",
                        part,
                        f'REF divider ratio {ratio:.4g} with {threshold:g}V reference makes K {"released/high" if healthy_high else "sinking/low"} at healthy {healthy:g}V and {"released/high" if low_high else "sinking/low"} at low {low:g}V. This inverts the declared enable polarity. Reverse the sense/enable logic and verify sink and enable thresholds.',
                        [ref, k, a],
                        [
                            (
                                part.path,
                                "ReferenceVoltage, HealthyVoltage, LowVoltage, EnableActiveHigh",
                            )
                        ],
                    )
            else:
                coverage.append(
                    (
                        part.path,
                        "polarity",
                        f"Not checked: {part.reference} REF/K/A polarity requires ReferenceVoltage, HealthyVoltage, LowVoltage and EnableActiveHigh metadata plus a resolved divider. No cutoff verdict is inferred.",
                    )
                )
        # Functional clock/reference checks use pin names, never component IDs.
        for p in pins:
            if (
                p.name.upper() in {"SCKI", "MCLK", "MCLK_IN", "CLKIN"}
                and p.kind == "input"
                and len(peers(p)) == 1
            ):
                emit(
                    "clock",
                    part,
                    f"pin {p.number} {p.name} clock input is floating; there is no clock source connected. Connect the required clock or document an internal-clock mode.",
                    [p],
                )
            if (
                p.name.upper() in {"VREF", "REFIN", "VREF_IN"}
                and p.kind == "power_in"
                and len(peers(p)) == 1
            ):
                emit(
                    "clock",
                    part,
                    f"pin {p.number} {p.name} reference is floating with no reference source or bypass network. Connect the reference circuit required by the datasheet.",
                    [p],
                )
        # Read literal I2S pin assignments, retaining source lines and refusing
        # ambiguous declarations. This does not execute or preprocess firmware.
        audio_roles = {
            "LRCK": "ws_io_num",
            "LRCLK": "ws_io_num",
            "WS": "ws_io_num",
            "BCK": "bck_io_num",
            "BCLK": "bck_io_num",
        }
        for source, data in files.items():
            if not source.endswith((".ino", ".c", ".cpp", ".h")):
                continue
            text = data.decode("utf-8-sig")
            text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
            for p in pins:
                role = audio_roles.get(p.name.upper())
                if not role:
                    continue
                values = re.findall(
                    r"\." + role + r"\s*=\s*(?:GPIO_NUM_)?(\d+)\s*[,}]", text
                )
                gpios = [
                    (q, re.search(r"(?:GPIO|IO)(\d+)(?:/|$)", q.name))
                    for q in peers(p)
                    if q.reference != part.reference
                ]
                gpios = [(q, m[1]) for q, m in gpios if m]
                if len(values) == len(gpios) == 1 and values[0] != gpios[0][1]:
                    q, actual = gpios[0]
                    emit(
                        "firmware",
                        part,
                        f"{p.name} connects to {q.reference} {q.name} (GPIO{actual}), but firmware {role} selects GPIO{values[0]}. Set {role} to {actual} or correct the wiring.",
                        [p, q],
                        [(source, role)],
                    )
            clocks = [
                p for p in pins if p.name.upper() in {"LRCK", "LRCLK", "BCK", "BCLK"}
            ]
            if (
                len(clocks) >= 2
                and "I2S_MODE_SLAVE" in text
                and "I2S_MODE_MASTER" not in text
            ):
                if all(not any(q.kind == "output" for q in peers(p)) for p in clocks):
                    emit(
                        "clock",
                        part,
                        "BCK/LRCK have no established clock master: firmware explicitly configures I2S_MODE_SLAVE and the schematic shows no output-type clock driver. Configure and verify one clock master and its source.",
                        clocks,
                        [(source, "I2S_MODE_SLAVE")],
                    )
                    findings[-1]["status"] = "suggestion"
        # ADC divider limits use an explicitly connected reference/supply pin.
        for p in pins:
            if "ADC" not in p.name.upper() or "REF" in p.name.upper():
                continue
            branches = [r for r in resistors if any(q.net == p.net for q in r.pins)]
            lows = [r for r in branches if ground(opposite(r, p.net))]
            highs = [r for r in branches if (voltage(opposite(r, p.net)) or 0) > 0]
            refs = [
                voltage(q.net)
                for q in pins
                if re.search(r"(?i)(ADC.?VREF|VREF|3V3|VDDA)", q.name)
            ]
            refs += [
                volts(part.properties.get(k, ""))
                for k in ("ADCReferenceVoltage", "PinMaxVoltage")
            ]
            refs = [v for v in refs if v is not None and v > 0]
            if len(lows) == len(highs) == 1 and refs:
                lo, hi = lows[0], highs[0]
                source = opposite(hi, p.net)
                vin = voltage(source)
                if any("VBUS" in n.upper() for n in names(source)) or any(
                    q.name == "VBUS" for q in g.nets.get(source, [])
                ):
                    vin = 5.25
                out = (
                    vin
                    * resistance(lo.value)
                    / (resistance(lo.value) + resistance(hi.value))
                )
                if out > min(refs):
                    emit(
                        "divider",
                        part,
                        f"pin {p.number} {p.name} divider {hi.reference}={hi.value}/{lo.reference}={lo.value} produces {out:.2f}V at {vin:g}V input, above the declared {min(refs):g}V ADC reference/supply. Change the divider ratio and check pin absolute maximum in the datasheet.",
                        [p],
                        [(hi.path, hi.reference), (lo.path, lo.reference)],
                    )
    # BOM absence is only asserted for a recognized, explicit reference column.
    for path, data in files.items():
        if not re.search(r"(?i)bom[^/]*\.(csv|tsv)$", path):
            continue
        rows = list(
            csv.DictReader(
                io.StringIO(data.decode("utf-8-sig")),
                delimiter="\t" if path.endswith(".tsv") else ",",
            )
        )
        if not rows:
            continue
        col = next(
            (
                k
                for k in rows[0]
                if k
                and k.lower()
                in {"designator", "reference", "references", "ref", "refs"}
            ),
            None,
        )
        if not col:
            continue
        refs = set(
            re.findall(
                r"\b[A-Z]+\d+\b", " ".join(row.get(col, "") or "" for row in rows)
            )
        )
        assembly_refs = {
            p.reference for p in g.parts if not p.reference.startswith("#")
        }
        if not refs or len(refs & assembly_refs) / len(refs) < 0.8:
            coverage.append(
                (path, "assembly", "Not checked: BOM assembly scope is ambiguous.")
            )
            continue
        for part in g.parts:
            if (
                not part.reference.startswith("#")
                and part.in_bom
                and part.fitted
                and part.reference not in refs
            ):
                emit(
                    "assembly",
                    part,
                    f"is omitted from {path} reference column {col}. Add its fitted part or explicitly mark the assembly exclusion.",
                    other=[(path, col)],
                )
    # Resolve only project-relative paths. Standard-library variables need the
    # installation/library manifest; absence from this repo is not a missing file.
    for path, data in files.items():
        if g.parts or not path.endswith((".kicad_pcb", ".kicad_mod")):
            continue
        text = data.decode("utf-8-sig")
        for model in re.findall(r'\(model\s+"([^"]+\.(?:step|stp))"', text, re.I):
            if "$" in model and not model.startswith("${KIPRJMOD}/"):
                coverage.append(
                    (path, "models", "Not checked: external library model " + model)
                )
                continue
            relative = model.removeprefix("${KIPRJMOD}/")
            if relative.startswith("/") or re.match(r"^[A-Za-z]:", relative):
                coverage.append(
                    (path, "models", "Not checked: absolute external model " + model)
                )
                continue
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(path), relative)
            )
            if target not in paths:
                # PCB model blocks carry no ref directly; locate containing footprint.
                prefix = text[: text.find('(model "' + model)]
                refs = re.findall(
                    r'\((?:fp_text reference|property "Reference")\s+"([^"]+)"', prefix
                )
                ref = refs[-1] if refs else "model"
                from extrude.electrical_graph import Part

                emit(
                    "models",
                    Part(ref, "", "", "", path, {}, True, True),
                    f"referenced 3D STEP file {model} does not resolve at {target}. Correct the path/case or include the model.",
                    other=[(path, model)],
                )
    if g.parts:
        coverage.append(
            (
                "",
                "graph",
                f"Analyzed {len(g.parts)} placed symbols and {len(g.nets)} nets from embedded geometry; no kicad-cli used.",
            )
        )
    for path, issue in g.issues:
        coverage.append((path, "graph", issue))
    for family in FAMILIES:
        coverage.append(
            (
                "",
                family,
                "Not checked: full operating limits, module internals and design intent are not inferred. Findings cover only supported explicit topology and metadata.",
            )
        )
    return findings, coverage


def analyze(files, paths=None):
    """Keep independent boards/variants isolated; traverse each hierarchy once.

    Repeated sheet instances are explicitly unsupported rather than shorted
    together. BOM association is only automatic for a single root design.
    """
    from extrude.parse.kicad_schematic import parse_schematic
    from extrude.kicad_snapshot import relative_dependency

    sheets = {
        p: parse_schematic(data)
        for p, data in files.items()
        if p.endswith(".kicad_sch")
    }
    children = {
        p: [relative_dependency(p, name) for _, name in sch.sheets]
        for p, sch in sheets.items()
    }
    childpaths = {p for v in children.values() for p in v}
    roots = sorted(set(sheets) - childpaths)
    findings = []
    coverage = []
    if sheets and not roots:
        raise ValueError("Not checked: cyclic schematic hierarchy.")
    visited = set()
    for root in roots:
        selected = set()
        repeated = set()

        def visit(p, stack):
            if p in stack:
                raise ValueError("Not checked: cyclic sheet placement " + p)
            if p in selected:
                repeated.add(p)
                return
            if p not in sheets:
                coverage.append(
                    (root, "graph", "Not checked: missing child sheet " + p)
                )
                return
            selected.add(p)
            for child in children[p]:
                visit(child, stack + (p,))

        try:
            visit(root, ())
        except ValueError as exc:
            coverage.append((root, "graph", str(exc)))
            continue
        for p in repeated:
            selected.discard(p)
            coverage.append(
                (
                    p,
                    "graph",
                    "Not checked: repeated sheet instances require placement-specific references. This sheet is excluded; other sheets are analyzed.",
                )
            )
        visited.update(selected)
        inputs = {
            p: data
            for p, data in files.items()
            if p in selected or not p.endswith(".kicad_sch")
        }
        if len(roots) > 1:
            inputs = {
                p: d
                for p, d in inputs.items()
                if not re.search(r"(?i)bom[^/]*\.(csv|tsv)$", p)
            }
            coverage.append(
                (
                    root,
                    "assembly",
                    "Not checked: multiple independent designs require explicit BOM scope.",
                )
            )
        # Model checks are repo-wide and are emitted once below.
        inputs = {
            p: d
            for p, d in inputs.items()
            if not p.endswith((".kicad_pcb", ".kicad_mod"))
        }
        paired_board = root.removesuffix(".kicad_sch") + ".kicad_pcb"
        if paired_board in files:
            inputs[paired_board] = files[paired_board]
        f, c = _analyze_design(inputs, paths)
        findings.extend(f)
        coverage.extend(c)
    # Even a PCB-only repo can have resolvable model references.
    f, c = _analyze_design(
        {p: d for p, d in files.items() if p.endswith((".kicad_pcb", ".kicad_mod"))},
        paths,
    )
    findings.extend(f)
    coverage.extend(c)
    if set(sheets) - visited:
        coverage.append(
            ("", "graph", "Not checked: some hierarchy could not be analyzed.")
        )
    return findings, list(dict.fromkeys(coverage))


def collect(repo, sha):
    from extrude import github_history as git

    inventory = git.inventory(repo, sha, limit=10000)
    if inventory["next_offset"] is not None:
        raise ValueError("Not checked: electrical inventory exceeds 10,000 files.")
    paths = {r["path"] for r in inventory["files"] if r["type"] == "blob"}
    candidates = sorted(
        p
        for p in paths
        if p.endswith(
            (".kicad_sch", ".kicad_pcb", ".kicad_mod", ".ino", ".c", ".cpp", ".h")
        )
        or re.search(r"(?i)bom[^/]*\.(csv|tsv)$", p)
    )
    if len(candidates) > 256:
        raise ValueError("Not checked: electrical input exceeds 256 files.")
    files = {}
    total = 0
    for path in candidates:
        data = git.regular_blob(repo, sha, path, max_bytes=8 * 1024 * 1024)
        if data is None:
            continue
        total += len(data)
        if total > 64 * 1024 * 1024:
            raise ValueError("Not checked: electrical inputs exceed 64 MiB.")
        files[path] = data
    findings, coverage = analyze(files, paths)
    for path in sorted(p for p in paths if p.endswith(".sch")):
        coverage.append(
            (
                path,
                "graph",
                "Not checked: legacy schematic geometry is unsupported; use a native .kicad_sch with embedded symbol definitions.",
            )
        )
    for row in findings:
        row["evidence"] = [
            evidence(repo, sha, path, locator) for path, locator in row.pop("sources")
        ]
    return findings, [
        dict(
            path=p,
            domain="schematic",
            check="Electrical " + f,
            tool="offline net graph",
            outcome="unavailable" if d.startswith("Not checked:") else "ran",
            detail=d,
        )
        for p, f, d in coverage
    ]
