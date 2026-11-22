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
    "ldo",
    "clock",
    "assembly",
    "switch",
    "pullup",
    "protection",
    "polarity",
    "models",
    "undriven",
)


def _designator(ref):
    """Reference without an optional lowercase sheet prefix."""
    return re.sub(r"^[a-z]+", "", ref or "")


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


def capacitance(value):
    """Return farads from a capacitor value with optional rating and tolerance."""
    match = re.fullmatch(
        r"(?i)\s*(\d+(?:\.\d+)?)\s*(?:([µunp])F?|(m)F)"
        r"(?:\s*/?\s*\d+(?:\.\d+)?\s*V)?"
        r"(?:\s*(?:\(\s*)?(?:±|\+/-)?\s*\d+(?:\.\d+)?\s*%(?:\s*\))?)?\s*",
        value,
    )
    if not match:
        return None
    amount, small_unit, milli = match.groups()
    exponent = {"µ": -6, "μ": -6, "u": -6, "n": -9, "p": -12, "m": -3}
    return float(f"{amount}e{exponent[(small_unit or milli).lower()]}")


def _capacitor_dielectric(footprint):
    library, _, name = footprint.rpartition(":")
    if name.startswith("CP_") or library == "Capacitor_Tantalum_SMD":
        return "polarized"
    if library in {"Capacitor_SMD", "Capacitor_THT"} and name.startswith("C_"):
        return "ceramic"
    return "unknown"


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


def _analyze_design(
    files, paths=None, inventory_complete=True, instance_paths=None, root_schematics=()
):
    """Pure entry point used by production and pinned-repository evaluation."""
    paths = set(paths or files)
    g = build(files, instance_paths=instance_paths)
    findings = []
    coverage = []
    seen = set()

    def emit(family, part, message, pins=(), other=(), *, separator=": "):
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
                summary=f"{part.reference}{separator}{message}",
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
            re.fullmatch(r"(?i)(GND[A-Z]*|AGND|DGND|VSS)", n)
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
            board_footprints = parse_board(files[board_path]).footprints
            board_references = {p.reference for p in board_footprints}
            electrical_board_refs = {p.reference for p in board_footprints if p.pads}
        except ValueError as exc:
            coverage.append(_not_checked(
                board_path, "clock", f"PCB footprint inventory could not be parsed: {exc}"
            ))
    if board_references is not None:
        physical = [p for p in g.parts if not p.reference.startswith("#")
                    and p.properties.get("_on_board", "True") == "True"]
        for part in physical:
            if part.fitted and part.reference not in board_references:
                emit("assembly", part,
                     f"is in the schematic{' and marked for BOM inclusion' if part.in_bom else ''} but has no footprint on the paired board — {part.value or 'this component'} cannot be assembled, so its circuit function is absent. Restore the footprint or reconcile the schematic and assembly intent.",
                     other=[(board_path, "footprint inventory: reference absent")])
        # Missing library definitions must not become false PCB-only accusations.
        if not g.issues and inventory_complete:
            schematic_refs = {p.reference for p in g.parts}
            from extrude.electrical_graph import Part
            skipped_refs = []
            for ref in sorted(electrical_board_refs - schematic_refs - {None, ""}):
                if "**" in ref:
                    skipped_refs.append(ref)
                    continue
                emit("assembly", Part(ref, "", "", "", board_path, {}, True, True),
                     "has a PCB footprint but no symbol in the paired schematic — its connectivity and BOM intent are unrepresented. Reconcile the board and schematic.")
            if skipped_refs:
                coverage.append((
                    board_path,
                    "assembly",
                    f"Skipped {len(skipped_refs)} placeholder footprint(s) ({', '.join(skipped_refs)}): "
                    "un-annotated, no schematic symbol expected.",
                ))
        coverage.append((board_path, "assembly", "Compared paired schematic and PCB component inventories."))
    byref = {(p.path, p.reference): p for p in g.parts}
    resistors = [
        p
        for p in g.parts
        if _designator(p.reference).startswith("R")
        and len(p.pins) == 2
        and p.fitted
        and resistance(p.value) is not None
        and resistance(p.value) > 0
    ]

    resistor_keys = {(p.path, p.reference) for p in resistors}

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

    active_kinds = {
        "input", "output", "bidirectional", "tri_state", "open_collector", "open_emitter",
    }

    def bus_devices(net):
        return {
            (pin.path, pin.reference)
            for pin in g.nets.get(net, [])
            if pin.kind in active_kinds
        }

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
            net_names = "/".join(names(p.net))
            spi = re.search(r"(?i)(?:SPI|I2S|(?:^|[_/ -])(?:SCK|MOSI|MISO)(?:$|[_/ -]))", signal)
            protocol = re.search(r"(?i)(I2C|SMBUS|DDC|(?:^|[_/ -])SDA(?:$|[_/ -])|(?:^|[_/ -])SCL(?:$|[_/ -]))", net_names)
            open_drain = any(q.kind == "open_collector" for q in peers(p))
            if (protocol or open_drain) and not spi and re.search(
                r"(?i)(SDA|SCL|DATA|CLK|CLOCK)", signal
            ) and not pullup(p.net):
                # Only one report per physical net.
                key = ("pullup", p.net)
                if key not in seen:
                    seen.add(key)
                    devices = bus_devices(p.net)
                    if len(devices) < 2:
                        refs = ", ".join(ref for _, ref in sorted(devices)) or "none"
                        coverage.append(
                            (
                                part.path,
                                "pullup",
                                f"Not checked: {net_names or p.name} is not an on-board I2C bus "
                                f"({len(devices)} active device(s): {refs}); "
                                "pull-ups, if needed, live on the connected module.",
                            )
                        )
                        continue
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
            text = data.decode("utf-8-sig", errors="replace")
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
    # Trace series resistors; pull resistors to supplies establish bias, not a
    # protocol master. Passive connector pins and bidirectional pins are unknown
    # possible external sources, so report uncertainty rather than an absence.
    if g.issues or not inventory_complete:
        coverage.append(("", "undriven", "Not checked: incomplete schematic graph cannot establish absence of a driver."))
    for net, connected in ([] if g.issues or not inventory_complete else g.nets.items()):
        label = "/".join(names(net))
        loads = [p for p in connected if p.kind == "input"]
        bus_signal = re.search(r"(?i)(SPI|MOSI|MISO|(?:^|[_/ -])(?:SCK|SCLK|CS|DC)(?:$|[_/ -]))", label)
        if not loads or (len(loads) < 2 and not bus_signal) or ground(net) or supply(net):
            continue
        reached, pending, terminals = set(), [net], []
        biased = False
        while pending and len(reached) < 256:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            for pin in g.nets.get(current, []):
                owner = byref[(pin.path, pin.reference)]
                if (pin.path, pin.reference) in resistor_keys:
                    other = opposite(owner, current)
                    if other is not None:
                        if ground(other) or supply(other):
                            biased = True
                        else:
                            pending.append(other)
                else:
                    terminals.append(pin)
        if biased and not bus_signal:
            continue  # Static enable/strap/divider levels can be resistor driven.
        if pending or not terminals or any(p.kind != "input" for p in terminals):
            continue
        # Standalone multi-input nets and named bus control inputs are supported;
        # isolated generic inputs need design intent (NC/optional pins).
        part = byref[(loads[0].path, loads[0].reference)]
        emit("undriven", part,
             f"net {label or '(unnamed)'} has only input loads and no driver/master: "
             + ", ".join(f"{p.reference} pin {p.number} {p.name}" for p in terminals)
             + ". These inputs have no signal source. Connect a driver/master or document the external source.",
             loads, [(p.path, f"{p.reference} pin {p.number} {p.name}") for p in terminals])
    # BOM absence is only asserted for a recognized, explicit reference column.
    for path, data in files.items():
        if not re.search(r"(?i)bom[^/]*\.(csv|tsv)$", path):
            continue
        try:
            rows = list(
                csv.DictReader(
                    io.StringIO(data.decode("utf-8-sig", errors="replace")),
                    delimiter="\t" if path.endswith(".tsv") else ",",
                )
            )
        except csv.Error as exc:
            coverage.append(_not_checked(path, "assembly", exc))
            continue
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
        if board_references is not None:
            from extrude.electrical_graph import Part
            for ref in sorted(refs - assembly_refs - board_references):
                emit("assembly", Part(ref, "", "", "", path, {}, True, True),
                     "is listed in the scoped BOM but has no footprint on the paired board — the listed component cannot be assembled. Reconcile the BOM and PCB.",
                     other=[(board_path, "footprint inventory: reference absent")])
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
    # The inventory contains files, so infer library directories from their parents.
    model_files = {
        path: data
        for path, data in files.items()
        if not g.parts and path.endswith((".kicad_pcb", ".kicad_mod"))
    }
    if model_files:
        project_dirs = sorted({
            posixpath.dirname(path) for path in paths if path.endswith(".kicad_pro")
        })
        library_roots = set()
        paths_by_lowercase = {}
        for path in sorted(paths):
            paths_by_lowercase.setdefault(path.lower(), path)
            directory = posixpath.dirname(path)
            while directory:
                parent, _, name = directory.rpartition("/")
                if name == "kicad-packages3D" or name.endswith(".pretty"):
                    library_roots.add(parent)
                directory = parent
        library_dirs = sorted(library_roots)
    for path, data in model_files.items():
        containing_dir = posixpath.dirname(path)
        candidate_dirs = [
            *project_dirs,
            *(posixpath.dirname(root) for root in root_schematics),
            containing_dir,
        ]
        ancestor = containing_dir
        while ancestor:
            ancestor = ancestor.rpartition("/")[0]
            candidate_dirs.append(ancestor)
        candidate_dirs.extend(library_dirs)
        text = data.decode("utf-8-sig", errors="replace")
        for model in re.findall(r'\(model\s+"([^"]+\.(?:step|stp))"', text, re.I):
            colon_prefix = re.match(r"^:[A-Za-z0-9_]+:", model)
            kiprjmod = model.startswith("${KIPRJMOD}/")
            if colon_prefix:
                relative = model[colon_prefix.end():]
            elif "$" in model and not kiprjmod:
                coverage.append(
                    (path, "models", "Not checked: external library model " + model)
                )
                continue
            else:
                relative = model.removeprefix("${KIPRJMOD}/")
                if relative.startswith("/") or re.match(r"^[A-Za-z]:", relative):
                    coverage.append(
                        (path, "models", "Not checked: absolute external model " + model)
                    )
                    continue
            bases = candidate_dirs if kiprjmod or colon_prefix else [containing_dir]
            targets = [posixpath.normpath(posixpath.join(base, relative)) for base in bases]
            if any(target in paths for target in targets):
                continue
            for target in targets:
                actual_path = paths_by_lowercase.get(target.lower())
                if actual_path is not None:
                    coverage.append(
                        (path, "models", f"model {model} resolves as {actual_path} with different case")
                    )
                    break
            else:
                if colon_prefix:
                    coverage.append(
                        (path, "models", "Not checked: external library model " + model)
                    )
                    continue
                target = targets[0]
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
    bulk_by_net = {}
    for part in g.parts:
        if not (part.fitted and _designator(part.reference).startswith("C") and len(part.pins) == 2):
            continue
        if (capacitance(part.value) or 0) < 1e-6:
            continue
        a, b = (pin.net for pin in part.pins)
        if a != b and ground(b):
            bulk_by_net.setdefault(a, []).append(part)
        if a != b and ground(a):
            bulk_by_net.setdefault(b, []).append(part)

    for part in g.parts:
        identifier = f"{part.value} {part.symbol}"
        if "1117" not in identifier or re.search(r"LDL1117|TLV1117LV", identifier, re.I):
            continue
        outputs = {}
        for pin in part.pins:
            if re.fullmatch(r"VO|VOUT|OUTPUT(?:_\d+)?|OUT", pin.name, re.I):
                outputs.setdefault(pin.net, pin)
        device = f"{part.reference} {part.value}"
        if not outputs:
            coverage.append((
                part.path, "ldo",
                f"Not checked: {device} has no identifiable output pin (VO/VOUT/OUTPUT); "
                "LDO output capacitance cannot be evaluated.",
            ))
        emitted = False
        for net, pin in outputs.items():
            net_name = "/".join(names(net)) or f"unnamed ({pin.name})"
            rail = f"{part.value} output {net_name}"
            caps = sorted(bulk_by_net.get(net, []), key=lambda cap: (cap.reference, cap.path))
            if not caps:
                coverage.append((
                    part.path, "ldo",
                    f"Not checked: {part.reference} {rail} has no fitted bulk (≥1 µF) output "
                    "capacitor in this schematic; output capacitance cannot be evaluated.",
                ))
                continue
            dielectrics = [_capacitor_dielectric(cap.footprint) for cap in caps]
            unknown = ", ".join(cap.reference for cap, dielectric in zip(caps, dielectrics)
                                if dielectric == "unknown")
            if unknown:
                coverage.append((
                    part.path, "ldo",
                    f"Not checked: {part.reference} {rail} has a bulk output capacitor of "
                    f"unknown dielectric ({unknown}); ceramic-only cannot be established.",
                ))
                continue
            if emitted or "polarized" in dielectrics:
                continue
            cap_list = ", ".join(f"{cap.reference} {cap.value}" for cap in caps)
            emit(
                "ldo", part,
                f"{rail}: fitted bulk output capacitance is ceramic-only ({cap_list}) — "
                "the 1117 family needs tantalum/electrolytic output capacitance with ESR in the "
                "0.3–22 Ω window (AMS1117: 22 µF solid tantalum; LM1117: ≥10 µF tantalum, "
                "ESR 0.3–22 Ω). Ceramic MLCC ESR is a few mΩ, below the window, and the loop "
                "can oscillate. Fit a tantalum or aluminium electrolytic bulk capacitor on "
                "this rail, or add series resistance, or use an LDO designed for ceramics.",
                (pin,),
                other=[(cap.path, f"{cap.reference} {cap.value} ({cap.footprint})") for cap in caps],
                separator=" ",
            )
            emitted = True

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
        if not g.parts and family != "models":
            continue
        if family == "assembly" and board_references is not None:
            continue
        coverage.append(
            (
                "",
                family,
                "Not checked: full operating limits, module internals and design intent are not inferred. Findings cover only supported explicit topology and metadata.",
            )
        )
    return findings, coverage


def _not_checked(path, family, reason):
    detail = str(reason).removeprefix("Not checked: ").rstrip(".")
    return path, family, f"Not checked: {detail} — other files still analysed."


def analyze(files, paths=None):
    """Keep independent boards/variants isolated; traverse each hierarchy once.

    Repeated sheet instances are explicitly unsupported rather than shorted
    together. BOM association is only automatic for a single root design.
    """
    from extrude.parse.kicad_schematic import parse_schematic
    from extrude.kicad_snapshot import relative_dependency

    paths = set(paths or files)
    findings = []
    coverage = []
    sheets = {}
    children = {}
    for path, data in files.items():
        # Keep usable ASCII facts, but disclose that damaged text is unverified.
        text = data.decode("utf-8-sig", errors="replace")
        if text.encode("utf-8") != data.removeprefix(b"\xef\xbb\xbf"):
            coverage.append(_not_checked(
                path, "text", "invalid UTF-8 bytes were replaced; affected text cannot be verified"
            ))
        if not path.endswith(".kicad_sch"):
            continue
        try:
            sheet = parse_schematic(data)
            dependencies = [
                (uuid, relative_dependency(path, name)) for uuid, name in sheet.sheets
            ]
        except (ValueError, OSError, RecursionError) as exc:
            coverage.append(_not_checked(path, "graph", exc))
            continue
        sheets[path] = sheet
        children[path] = dependencies
    childpaths = {p for dependencies in children.values() for _, p in dependencies}
    roots = sorted(set(sheets) - childpaths)
    visited = set()
    for root in roots:
        selected = set()
        repeated = set()
        instance_paths = {}

        def visit(p, stack, instance_path):
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
            if instance_path:
                instance_paths[p] = instance_path
            for uuid, child in children[p]:
                child_instance_path = f"{instance_path}/{uuid}" if instance_path else ""
                visit(child, stack + (p,), child_instance_path)

        try:
            root_uuid = sheets[root].uuid
            visit(root, (), f"/{root_uuid}" if root_uuid else "")
        except (ValueError, OSError, RecursionError) as exc:
            coverage.append(_not_checked(root, "graph", exc))
            continue
        for p in repeated:
            selected.discard(p)
            instance_paths.pop(p, None)
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
        complete = not repeated and all(child in sheets for p in selected for _, child in children[p])
        try:
            f, c = _analyze_design(
                inputs, paths, inventory_complete=complete, instance_paths=instance_paths,
                root_schematics=(root,),
            )
        except (ValueError, OSError, RecursionError) as exc:
            coverage.append(_not_checked(root, "graph", exc))
            continue
        findings.extend(f)
        coverage.extend(c)
    # Shared footprints can belong to any root. A paired board has a known root.
    board_roots = {root.removesuffix(".kicad_sch") + ".kicad_pcb": (root,) for root in roots}
    for path, data in files.items():
        if not path.endswith((".kicad_pcb", ".kicad_mod")):
            continue
        try:
            f, c = _analyze_design(
                {path: data}, paths, root_schematics=board_roots.get(path, roots)
            )
        except (ValueError, OSError, RecursionError) as exc:
            coverage.append(_not_checked(path, "models", exc))
            continue
        findings.extend(f)
        coverage.extend(c)
    for path in sorted(set(sheets) - visited):
        coverage.append(_not_checked(path, "graph", "cyclic or unreachable schematic hierarchy"))
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
    skipped = []
    total = 0
    for path in candidates:
        try:
            limit = 32 * 1024 * 1024 if path.endswith(".kicad_pcb") else 8 * 1024 * 1024
            data = git.regular_blob(repo, sha, path, max_bytes=limit)
            if data is None:
                raise ValueError("input disappeared from the selected revision")
            if total + len(data) > 64 * 1024 * 1024:
                raise ValueError("electrical inputs exceed 64 MiB")
        except (ValueError, git.GitHubError, OSError) as exc:
            # BlobUnavailable is a ValueError. A bad blob must not erase peers.
            skipped.append(_not_checked(path, "input", exc))
            continue
        total += len(data)
        files[path] = data
    findings, coverage = analyze(files, paths)
    coverage = skipped + coverage
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
