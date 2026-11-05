"""Print-tolerance checks. No simulator and no model."""

import json
from pathlib import Path

from pydantic import BaseModel

from extrude.checks.models import ToleranceMeasurement, ToleranceReport

_TABLE = json.loads(
    (Path(__file__).resolve().parent / "data" / "heat_set_inserts.json").read_text(encoding="utf-8")
)


class HoleCheck(BaseModel):
    name: str
    diameter_mm: float
    intended_insert: str


class WallCheck(BaseModel):
    name: str
    thickness_mm: float
    normal_z: float | None = None


def check_tolerance(
    *,
    holes: list[HoleCheck],
    walls: list[WallCheck],
    filament: str,
) -> ToleranceReport:
    blocking: list[str] = []
    warnings: list[str] = []
    measurements: list[ToleranceMeasurement] = []
    plastic = filament.strip().upper()
    if plastic not in _TABLE["filaments"]:
        blocking.append(f"unknown_filament:{filament}")
        return ToleranceReport(blocking=blocking, warnings=warnings, measurements=measurements)

    band = float(_TABLE["band_mm"])
    seen: set[str] = set()
    for hole in holes:
        _hole(plastic, band, hole, seen, blocking, measurements)
    floor = _wall_floor(plastic, holes)
    warn_z = float(_TABLE["overhang_warn_z"])
    block_z = float(_TABLE["overhang_block_z"])
    seen_walls: set[str] = set()
    for wall in walls:
        _wall(floor, warn_z, block_z, wall, seen_walls, blocking, warnings, measurements)
    return ToleranceReport(
        blocking=sorted(set(blocking)),
        warnings=sorted(set(warnings)),
        measurements=measurements,
    )


def _wall_floor(plastic: str, holes: list[HoleCheck]) -> float:
    floor = float(_TABLE["filaments"][plastic]["min_wall_mm"])
    for hole in holes:
        row = _TABLE["inserts"].get(hole.intended_insert.strip().upper())
        if row is None:
            continue
        floor = max(floor, float(row["min_wall_mm"]))
    return floor


def _hole(
    plastic: str,
    band: float,
    hole: HoleCheck,
    seen: set[str],
    blocking: list[str],
    measurements: list[ToleranceMeasurement],
) -> None:
    name = hole.name.strip()
    if not name:
        blocking.append("unnamed_feature:hole")
        return
    if name in seen:
        blocking.append(f"duplicate_feature:{name}")
    seen.add(name)
    token = hole.intended_insert.strip().upper()
    row = _TABLE["inserts"].get(token)
    if row is None:
        blocking.append(f"unknown_insert:{name}")
        return
    if plastic not in row:
        blocking.append(f"insert_missing_target:{name}")
        return
    target = float(row[plastic])
    low = target - band
    high = target + band
    if hole.diameter_mm < low:
        blocking.append(f"hole_undersized_for_insert:{name}")
        measurements.append(
            ToleranceMeasurement(
                check_id="hole_undersized_for_insert",
                feature=name,
                measured_mm=hole.diameter_mm,
                limit_mm=low,
                delta_mm=hole.diameter_mm - low,
            )
        )
    elif hole.diameter_mm > high:
        blocking.append(f"hole_oversized_for_insert:{name}")
        measurements.append(
            ToleranceMeasurement(
                check_id="hole_oversized_for_insert",
                feature=name,
                measured_mm=hole.diameter_mm,
                limit_mm=high,
                delta_mm=hole.diameter_mm - high,
            )
        )


def _wall(
    floor: float,
    warn_z: float,
    block_z: float,
    wall: WallCheck,
    seen: set[str],
    blocking: list[str],
    warnings: list[str],
    measurements: list[ToleranceMeasurement],
) -> None:
    name = wall.name.strip()
    if not name:
        blocking.append("unnamed_feature:wall")
        return
    if name in seen:
        blocking.append(f"duplicate_feature:{name}")
    seen.add(name)
    if wall.thickness_mm < floor:
        blocking.append(f"wall_below_min:{name}")
        measurements.append(
            ToleranceMeasurement(
                check_id="wall_below_min",
                feature=name,
                measured_mm=wall.thickness_mm,
                limit_mm=floor,
                delta_mm=wall.thickness_mm - floor,
            )
        )
    if wall.normal_z is None:
        return
    if wall.normal_z < -1 or wall.normal_z > 1:
        blocking.append(f"overhang_normal_invalid:{name}")
        measurements.append(
            ToleranceMeasurement(
                check_id="overhang_normal_invalid",
                feature=name,
                measured_mm=wall.normal_z,
                limit_mm=1,
                delta_mm=abs(wall.normal_z) - 1,
            )
        )
        return
    if wall.normal_z < block_z:
        blocking.append(f"overhang_risk:{name}")
        measurements.append(
            ToleranceMeasurement(
                check_id="overhang_risk",
                feature=name,
                measured_mm=wall.normal_z,
                limit_mm=block_z,
                delta_mm=wall.normal_z - block_z,
            )
        )
    elif wall.normal_z < warn_z:
        warnings.append(f"overhang_risk:{name}")
        measurements.append(
            ToleranceMeasurement(
                check_id="overhang_risk",
                feature=name,
                measured_mm=wall.normal_z,
                limit_mm=warn_z,
                delta_mm=wall.normal_z - warn_z,
                severity="warn",
            )
        )
