"""Arm benchmark card — thin wrapper over extrude.spec.SpecCard."""

import json
from pathlib import Path

from pydantic import BaseModel

from extrude.spec import Requirement, RequirementKind, SpecCard

_PATH = Path(__file__).resolve().parent / "spec.json"


class ArmSpec(BaseModel):
    sentence: str
    material: str | None = None
    insert: str | None = None
    insert_count: int = 0
    insert_min_mm: float | None = None
    insert_max_mm: float | None = None
    min_wall_mm: float | None = None
    print_direction: str | None = None

    def to_spec_card(self) -> SpecCard:
        requirements: list[Requirement] = []
        if self.insert_min_mm is not None and self.insert_max_mm is not None:
            requirements.append(
                Requirement(
                    id="insert_diameter",
                    kind=RequirementKind.hole_band,
                    predicate={"insert": self.insert, "count": self.insert_count},
                    limit=self.insert_max_mm,
                )
            )
        if self.min_wall_mm is not None:
            requirements.append(
                Requirement(
                    id="joint_wall",
                    kind=RequirementKind.wall_mm,
                    predicate={},
                    limit=self.min_wall_mm,
                )
            )
        return SpecCard(
            sentence=self.sentence,
            domain="mechanical_3d",
            requirements=requirements,
            material=self.material,
            insert=self.insert,
            insert_count=self.insert_count,
            insert_min_mm=self.insert_min_mm,
            insert_max_mm=self.insert_max_mm,
            min_wall_mm=self.min_wall_mm,
        )

    def prompt(self) -> str:
        text = self.to_spec_card().prompt()
        if self.print_direction:
            text = f"{text}\nThe print direction is {self.print_direction}."
        return text

    def shape_only(self) -> "ArmSpec":
        return self.model_copy(
            update={
                "insert": None,
                "insert_count": 0,
                "insert_min_mm": None,
                "insert_max_mm": None,
                "min_wall_mm": None,
                "print_direction": None,
            }
        )

    def requirement_ids(self) -> set[str]:
        return self.to_spec_card().requirement_ids()


def load_spec(path: Path | None = None) -> ArmSpec:
    raw = json.loads((path or _PATH).read_text(encoding="utf-8"))
    return ArmSpec.model_validate(raw)
