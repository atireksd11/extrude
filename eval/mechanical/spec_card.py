"""Frozen mechanical task cards for the lift benchmark."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

from extrude.spec import SpecCard
from extrude.verify.models import SolidVerifySpec

_ROOT = Path(__file__).resolve().parent / "tasks"


class TaskSpec(BaseModel):
    task_id: str
    sentence: str
    material: str | None = None
    insert: str | None = None
    insert_count: int = 0
    insert_min_mm: float | None = None
    insert_max_mm: float | None = None
    min_wall_mm: float | None = None
    bbox_min_mm: float | None = None
    bbox_max_mm: float | None = None
    min_bends: int = 1
    checks: list[str] = Field(default_factory=list)
    negative_control: bool = False

    def prompt(self) -> str:
        card = SpecCard(
            sentence=self.sentence,
            domain="mechanical_3d",
            material=self.material,
            insert=self.insert,
            insert_count=self.insert_count,
            insert_min_mm=self.insert_min_mm,
            insert_max_mm=self.insert_max_mm,
            min_wall_mm=self.min_wall_mm,
        )
        return card.prompt() + "\nUse millimeters. Output only the OpenSCAD code."

    def to_verify(self) -> SolidVerifySpec:
        return SolidVerifySpec(
            sentence=self.sentence,
            material=self.material,
            insert=self.insert,
            insert_count=self.insert_count,
            insert_min_mm=self.insert_min_mm,
            insert_max_mm=self.insert_max_mm,
            min_wall_mm=self.min_wall_mm,
            bbox_min_mm=self.bbox_min_mm,
            bbox_max_mm=self.bbox_max_mm,
            min_bends=self.min_bends,
            checks=self.checks,
            min_wall_mm_threshold=float(self.min_wall_mm or 2.0),
        )

    def task_dir(self) -> Path:
        return _ROOT / self.task_id


def load_task(task_id: str) -> TaskSpec:
    path = _ROOT / task_id / "spec.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["task_id"] = task_id
    return TaskSpec.model_validate(raw)


def all_tasks() -> list[str]:
    return sorted(path.name for path in _ROOT.iterdir() if path.is_dir() and (path / "spec.json").is_file())
