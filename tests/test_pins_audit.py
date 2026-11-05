"""Pin rules and netlist audit. No model."""

from extrude.checks.api import inspect_electrical
from extrude.checks.pins import lint_control_pins
from extrude.emit.netlist import emit_netlist
from extrude.ir.models import CircuitIR, Part, Pin
from extrude.parse.kicad_netlist import parse_kicad_netlist

_FLOATING = """
(export (version "E")
  (components
    (comp (ref "U1")
      (value "MCU")
      (libsource (lib "Connector") (part "Conn") (description ""))
    )
  )
  (nets
    (net (code "1") (name "nRST")
      (node (ref "U1") (pin "NRST"))
    )
  )
)
"""

_HELD = """
(export (version "E")
  (components
    (comp (ref "U1")
      (value "MCU")
      (libsource (lib "Connector") (part "Conn") (description ""))
    )
    (comp (ref "R1")
      (value "10k")
      (libsource (lib "Device") (part "R") (description ""))
    )
  )
  (nets
    (net (code "1") (name "nRST")
      (node (ref "U1") (pin "NRST"))
      (node (ref "R1") (pin "1"))
    )
    (net (code "2") (name "3V3")
      (node (ref "R1") (pin "2"))
    )
  )
)
"""


def test_a_reset_pin_with_no_resistor_fails():
    design = parse_kicad_netlist(_FLOATING)
    report = inspect_electrical(design)
    assert "control_pin_floating:U1.NRST" in report.blocking


def test_a_reset_pin_with_a_pull_resistor_passes_the_pin_rule():
    design = parse_kicad_netlist(_HELD)
    assert lint_control_pins(design).blocking == []


def test_an_nc_pin_tied_to_a_net_fails():
    design = CircuitIR(
        parts=[Part(refdes="U1", kind="ic")],
        pins=[Pin(refdes="U1", name="NC", net="GPIO1", state="connected")],
    )
    assert "nc_tied:U1.NC" in lint_control_pins(design).blocking


def test_a_netlist_round_trip_keeps_the_parts():
    design = parse_kicad_netlist(_HELD)
    assert {part.refdes: part.kind for part in design.parts} == {"U1": "ic", "R1": "resistor"}
    assert "nRST" in design.nets


_NUMBERED = """
(export (version "E")
  (components
    (comp (ref "U1")
      (value "MCU")
      (libsource (lib "MCU") (part "STM32") (description ""))
    )
    (comp (ref "R1")
      (value "10k")
      (libsource (lib "Device") (part "R_Small") (description ""))
    )
    (comp (ref "C1")
      (value "100n")
      (libsource (lib "Device") (part "C") (description ""))
    )
  )
  (nets
    (net (code "1") (name "nRST")
      (node (ref "U1") (pin "14") (pinfunction "NRST"))
      (node (ref "C1") (pin "1"))
    )
    (net (code "2") (name "GND")
      (node (ref "C1") (pin "2"))
    )
  )
)
"""


def test_a_numbered_pin_uses_its_function_and_a_capacitor_is_not_a_pull():
    design = parse_kicad_netlist(_NUMBERED)
    assert design.pins[0].name == "NRST"
    assert {part.refdes: part.kind for part in design.parts}["R1"] == "resistor"
    assert "control_pin_floating:U1.NRST" in inspect_electrical(design).blocking


def test_a_resistor_to_a_signal_is_not_a_pull_and_a_rail_tie_is():
    to_gpio = CircuitIR(
        parts=[Part(refdes="U1", kind="ic"), Part(refdes="R1", kind="resistor")],
        pins=[
            Pin(refdes="U1", name="RESET#", net="RST", state="connected"),
            Pin(refdes="R1", name="1", net="RST", state="connected"),
            Pin(refdes="R1", name="2", net="GPIO1", state="connected"),
        ],
    )
    to_rail = CircuitIR(
        parts=[Part(refdes="U1", kind="ic")],
        pins=[Pin(refdes="U1", name="EN1", net="VDD_3V3", state="connected")],
    )
    assert "control_pin_floating:U1.RESET#" in lint_control_pins(to_gpio).blocking
    assert lint_control_pins(to_rail).blocking == []


def test_our_own_netlist_keeps_the_reset_name():
    design = CircuitIR(
        parts=[Part(refdes="U1", kind="ic")],
        pins=[Pin(refdes="U1", name="NRST", net="nRST", state="connected")],
    )
    parsed = parse_kicad_netlist(emit_netlist(design))
    assert parsed.pins[0].name == "NRST"
    assert "control_pin_floating:U1.NRST" in lint_control_pins(parsed).blocking
