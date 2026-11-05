"""Qty-100 distributor prices. A bench source is not a purchased part."""

from extrude.ir.models import CircuitIR

# Captured 2026-10-03. The number is the distributor's quantity-100 unit price.
_MPN_USD = {
    "TPS54302DDCT": 1.14010,  # DigiKey, buck, 3 A
    "SRR1260-4R7Y": 0.833,  # Newark, 4.7 uH, 6.8 A
    "GRM21BR61E106KA73L": 0.1773,  # DigiKey 490-5523, 10 uF, 25 V
    "LM78M05CT/NOPB": 0.92267,  # DigiKey 45+ bracket, which covers qty 100, 2026-09-23
    "EKZE100ELL681MJC5S": 0.618,  # DigiKey 565-1644-ND, 680 uF, 10 V
    "CRCW08052R00FKEA": 0.02120,  # CRCW0805 1% qty-100 bracket
}
_MLCC_USD = _MPN_USD["GRM21BR61E106KA73L"]
_BULK_CAP_USD = _MPN_USD["EKZE100ELL681MJC5S"]
_INDUCTOR_USD = _MPN_USD["SRR1260-4R7Y"]
_RESISTOR_USD = _MPN_USD["CRCW08052R00FKEA"]
_LED_USD = 0.04  # practice-set indicator lamp; not a fresh distributor quote
_BUCK_IC_USD = _MPN_USD["TPS54302DDCT"]
_LDO_IC_USD = _MPN_USD["LM78M05CT/NOPB"]
_BULK_FARADS = 100e-6


def design_bom_usd(design: CircuitIR, task_class: str) -> float:
    total = 0.0
    for part in design.parts:
        if part.kind == "ideal_voltage_source":
            continue
        total += _unit_usd(part, task_class)
    return total


def _unit_usd(part, task_class: str) -> float:
    mpn = (part.mpn or "").strip().upper()
    if mpn in _MPN_USD:
        return _MPN_USD[mpn]
    if part.kind == "capacitor":
        if part.capacitance is not None and part.capacitance >= _BULK_FARADS:
            return _BULK_CAP_USD
        return _MLCC_USD
    if part.kind == "inductor":
        return _INDUCTOR_USD
    if part.kind == "resistor":
        return _RESISTOR_USD
    if part.kind == "led":
        return _LED_USD
    if part.kind == "ic":
        if task_class == "buck":
            return _BUCK_IC_USD
        return _LDO_IC_USD
    return _MLCC_USD
