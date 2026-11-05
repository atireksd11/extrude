"""Frozen 2D mechanical task cards for the lift benchmark."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from extrude.spec import SpecCard
from extrude.verify.models import SvgVerifySpec

_ROOT = Path(__file__).resolve().parent / "tasks"


class TaskSpec(BaseModel):
    task_id: str
    sentence: str
    plate_width_mm: float | None = None
    plate_height_mm: float | None = None
    plate_diameter_mm: float | None = None
    hole: str | None = None
    hole_count: int = 0
    hole_min_mm: float | None = None
    hole_max_mm: float | None = None
    hole_positions: list[tuple[float, float]] = Field(default_factory=list)
    min_edge_distance_mm: float = 2.0
    checks: list[str] = Field(default_factory=list)
    negative_control: bool = False

    def prompt(self) -> str:
        card = SpecCard(
            sentence=self.sentence,
            domain="mechanical_2d",
            plate_width_mm=self.plate_width_mm,
            plate_height_mm=self.plate_height_mm,
            plate_diameter_mm=self.plate_diameter_mm,
            hole=self.hole,
            hole_count=self.hole_count,
            hole_min_mm=self.hole_min_mm,
            hole_max_mm=self.hole_max_mm,
        )
        return (
            card.prompt()
            + "\nUse millimeters. Output only OpenSCAD 2D code with square/circle/difference — no linear_extrude."
        )

    def to_verify(self) -> SvgVerifySpec:
        return SvgVerifySpec(
            sentence=self.sentence,
            plate_width_mm=self.plate_width_mm,
            plate_height_mm=self.plate_height_mm,
            plate_diameter_mm=self.plate_diameter_mm,
            hole=self.hole,
            hole_count=self.hole_count,
            hole_min_mm=self.hole_min_mm,
            hole_max_mm=self.hole_max_mm,
            hole_positions=self.hole_positions,
            min_edge_distance_mm=self.min_edge_distance_mm,
            checks=self.checks,
        )

    def task_dir(self) -> Path:
        return _ROOT / self.task_id


def load_task(task_id: str) -> TaskSpec:
    path = _ROOT / task_id / "spec.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["task_id"] = task_id
    if "hole_positions" in raw:
        raw["hole_positions"] = [tuple(item) for item in raw["hole_positions"]]
    return TaskSpec.model_validate(raw)


def all_tasks() -> list[str]:
    return sorted(path.name for path in _ROOT.iterdir() if path.is_dir() and (path / "spec.json").is_file())
