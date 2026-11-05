"""The note the model sees. Limits in it are not suggestions."""

from extrude.intake.models import FrozenSpec
from extrude.memory.models import NegativeConstraint


_STATIC = (
    "EMIT one JSON object. Numbers are SI. "
    "spec_hash is SPEC_HASH. limits is BOUNDS_SI copied unchanged. "
    "When BOUNDS_SI has i_load, set i_load to that same number. "
    "Each part is an object with refdes and kind. "
    "kind is ic, resistor, capacitor, inductor, ferrite, or ideal_voltage_source. "
    "A capacitor has capacitance in farads. An inductor has inductance in henries. "
    "Each pin is an object with refdes, name, net, and state connected. "
    "Name the ground net GND. Every pin is connected. "
    "A power pin reaches GND through a resistor, inductor, ferrite, or ideal voltage source, "
    "and a capacitor sits on that same net. A capacitor does not conduct DC. "
    "Do not put two ideal voltage sources on one net other than GND. "
    "A hold-up capacitor connects the rail to GND, its capacitance is at least c_min, "
    "and its dielectric is not X5R, X7R, X6S, Y5V, or Z5U. "
    "A buck includes f_sw in hertz and an inductor. "
    "Do not change a limit. Do not omit the spec load."
)


def build_prompt(
    spec: FrozenSpec,
    blocks: list[NegativeConstraint],
    passed: list[str],
    last_error: str = "",
) -> str:
    shown = blocks[:8]
    lines = [
        _STATIC,
        f"SPEC_HASH: {spec.spec_hash}",
        f"TASK: {spec.task_class}",
        f"BOUNDS_SI (immutable): {spec.values_si}",
        f"ORIGINS: { {key: origin.value for key, origin in spec.origins.items()} }",
        "DO_NOT_REPEAT:",
    ]
    if not shown:
        lines.append("- none")
    for block in shown:
        lines.append(
            "- "
            f"{block.identity.manufacturer} {block.identity.capacitance} F "
            f"{block.identity.dielectric} {block.identity.case} "
            f"failed {block.check_id} at v_dc={block.v_fail}: "
            f"measured {block.measured}, limit {block.limit}"
        )
    lines.append("PASSED_AND_LOCKED: " + (", ".join(passed) if passed else "none"))
    if last_error.strip():
        lines.append("LAST_REJECTED: " + " ".join(last_error.split())[:400])
    return "\n".join(lines)
