"""Buck ripple from the shared use-value. Light load does not invent a number."""


def buck_ripple(
    vin: float | None,
    vout: float | None,
    i_load: float | None,
    f_sw: float | None,
    inductance: float | None,
    c_use: float | None,
    esr: float,
) -> tuple[float | None, str]:
    if (
        vin is None
        or vout is None
        or i_load is None
        or f_sw is None
        or inductance is None
        or c_use is None
        or vin <= 0
        or f_sw <= 0
        or inductance <= 0
        or c_use <= 0
        or not 0 < vout < vin
    ):
        return None, "not_a_switcher"
    duty_rest = 1.0 - (vout / vin)
    delta_i = vout * duty_rest / (f_sw * inductance)
    if delta_i > 2.0 * i_load:
        return None, "dcm"
    delta_v = delta_i * (esr + 1.0 / (8.0 * f_sw * c_use))
    return delta_v, "ccm"
