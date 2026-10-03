"""Hand-written designs. The checker has to accept these as written."""

from extrude.ir.models import CircuitIR, Part, Pin


def _pin(refdes: str, name: str, net: str | None, **kwargs) -> Pin:
    state = "nc" if kwargs.get("state") == "nc" else "connected" if net else "open"
    return Pin(refdes=refdes, name=name, net=net, state=kwargs.get("state", state), **{k: v for k, v in kwargs.items() if k != "state"})


def good_mcu_rail() -> CircuitIR:
    """3V3 pin, local capacitor to GND, and the supply source down to ground."""
    return CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="V1", kind="ideal_voltage_source"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("C1", "A", "3V3"),
            _pin("C1", "B", "GND"),
            _pin("V1", "+", "3V3", role="positive"),
            _pin("V1", "-", "GND", role="negative"),
        ],
    )


def good_ac_coupled_uart() -> CircuitIR:
    """Series capacitor with a bias resistor on both sides. TX lands on RX, not on another TX."""
    return CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="U2", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
            Part(refdes="R1", kind="resistor"),
            Part(refdes="R2", kind="resistor"),
        ],
        pins=[
            _pin("U1", "TX", "TX_A", driver="uart_tx"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("U2", "RX", "RX_B"),
            _pin("U2", "GND", "GND", role="ground"),
            _pin("C1", "A", "TX_A"),
            _pin("C1", "B", "RX_B"),
            _pin("R1", "A", "TX_A"),
            _pin("R1", "B", "GND"),
            _pin("R2", "A", "RX_B"),
            _pin("R2", "B", "GND"),
        ],
    )


def bad_hanging_pin() -> CircuitIR:
    design = good_mcu_rail()
    design.pins.append(Pin(refdes="U1", name="GPIO1", state="open"))
    return design


def bad_two_sources() -> CircuitIR:
    design = good_mcu_rail()
    design.parts.append(Part(refdes="V2", kind="ideal_voltage_source"))
    design.pins.extend(
        [
            _pin("V2", "+", "3V3", role="positive"),
            _pin("V2", "-", "GND", role="negative"),
        ]
    )
    return design


def bad_power_without_ground_path() -> CircuitIR:
    """A capacitor to ground is not a DC path."""
    return CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="C1", kind="capacitor"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("C1", "A", "3V3"),
            _pin("C1", "B", "GND"),
        ],
    )


def bad_two_uart_drivers() -> CircuitIR:
    design = good_mcu_rail()
    design.parts.append(Part(refdes="U2", kind="ic"))
    design.pins.extend(
        [
            _pin("U1", "TX", "UART", driver="uart_tx"),
            _pin("U2", "TX", "UART", driver="uart_tx"),
        ]
    )
    return design


def bad_power_with_path_but_no_capacitor() -> CircuitIR:
    return CircuitIR(
        parts=[
            Part(refdes="U1", kind="ic"),
            Part(refdes="R1", kind="resistor"),
        ],
        pins=[
            _pin("U1", "VDD", "3V3", role="power"),
            _pin("U1", "GND", "GND", role="ground"),
            _pin("R1", "A", "3V3"),
            _pin("R1", "B", "GND"),
        ],
    )


def nc_pin_is_allowed() -> CircuitIR:
    design = good_mcu_rail()
    design.pins.append(Pin(refdes="U1", name="NC1", state="nc"))
    return design
