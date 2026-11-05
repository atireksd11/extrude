"""Grade the rendered solid. Module names are not checks."""

from pathlib import Path

from eval.arm_benchmark.spec_card import ArmSpec
from extrude.verify.solid import score_openscad, spec_from_labels


def _arm_checks(spec: ArmSpec) -> list[str]:
    checks = [
        "compiles",
        "desktop_scale",
        "three_links",
        "two_fingers",
        "more_than_one_bend",
        "base_mounting_holes",
    ]
    if spec.insert and spec.insert_count:
        checks.append("insert_diameter")
    if spec.min_wall_mm is not None:
        checks.append("joint_wall")
    return checks


def score_solid(source: Path, spec: ArmSpec, out_dir: Path | None = None) -> dict:
    verify = spec_from_labels(
        spec.sentence,
        material=spec.material,
        insert=spec.insert,
        insert_count=spec.insert_count,
        insert_min_mm=spec.insert_min_mm,
        insert_max_mm=spec.insert_max_mm,
        min_wall_mm=spec.min_wall_mm,
    )
    verify = verify.model_copy(update={"require_colors": True, "checks": _arm_checks(spec)})
    return score_openscad(source, verify, out_dir)
