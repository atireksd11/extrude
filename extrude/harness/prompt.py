"""The note the model sees. Limits in it are not suggestions."""

from extrude.intake.models import FrozenSpec
from extrude.memory.models import NegativeConstraint


def build_prompt(
    spec: FrozenSpec,
    blocks: list[NegativeConstraint],
    passed: list[str],
) -> str:
    shown = blocks[:8]
    lines = [
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
    lines.append(
        "EMIT JSON only. The object must contain spec_hash set to SPEC_HASH, "
        "limits set to BOUNDS_SI unchanged, and, when BOUNDS_SI has i_load, "
        "i_load set to that same number. Then parts and pins. "
        "Do not change a limit. Do not omit the spec load."
    )
    return "\n".join(lines)
