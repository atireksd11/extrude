"""Plain-language view of a frozen card."""

from extrude.intake.models import FrozenSpec, SlotOrigin

_SCALE = {
    "vin": ("V", 1.0),
    "vout": ("V", 1.0),
    "v_rail": ("V", 1.0),
    "i_load": ("A", 1.0),
    "i_led": ("mA", 1e3),
    "ripple_pp": ("mV", 1e3),
}

_HOW = {
    SlotOrigin.user_span: "you typed this",
    SlotOrigin.default: "assumed default",
    SlotOrigin.waived: "waived",
}


def describe(spec: FrozenSpec) -> str:
    lines = [
        f"Task: {spec.task_class}",
        f"Defaults version: {spec.defaults_version}",
    ]
    order = ("vin", "vout", "i_load", "i_led", "v_rail", "t_hold", "c_min", "ripple_pp")
    keys = [key for key in order if key in spec.values_si]
    keys.extend(key for key in spec.values_si if key not in keys)
    for key in keys:
        unit, scale = _SCALE.get(key, ("", 1.0))
        shown = format(spec.values_si[key] * scale, ".12g")
        how = _HOW[spec.origins[key]]
        snippet = spec.evidence.get(key, "")
        source = f", from {snippet!r}" if snippet else ""
        gap = " " if unit else ""
        lines.append(f"{key}: {shown}{gap}{unit} ({how}{source})")
    for key in sorted(spec.labels):
        lines.append(f"{key}: {spec.labels[key]} (you typed this)")
    lines.append(f"Hash: {spec.spec_hash}")
    return "\n".join(lines)
