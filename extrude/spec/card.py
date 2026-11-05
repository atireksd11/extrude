"""Typed predicates on a spec card. A check not on the card does not run."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RequirementKind(str, Enum):
    compiles = "compiles"
    bbox_mm = "bbox_mm"
    hole_band = "hole_band"
    wall_mm = "wall_mm"
    net_connected = "net_connected"
    ripple_pp = "ripple_pp"
    component_count = "component_count"
    feature_count = "feature_count"


_FORBIDDEN = frozenset(
    {
        "link1",
        "link2",
        "link3",
        "module base",
        "module gripper",
        "module link",
        "checker",
        "score",
        "you are inside a checker",
    }
)


class Requirement(BaseModel):
    id: str
    kind: RequirementKind
    predicate: dict[str, Any] = Field(default_factory=dict)
    limit: float | None = None
    lock_on_pass: bool = True


class SpecCard(BaseModel):
    """User-facing sentence plus optional manufacturing numbers."""

    sentence: str
    domain: str
    requirements: list[Requirement] = Field(default_factory=list)
    material: str | None = None
    insert: str | None = None
    insert_count: int = 0
    insert_min_mm: float | None = None
    insert_max_mm: float | None = None
    min_wall_mm: float | None = None
    plate_width_mm: float | None = None
    plate_height_mm: float | None = None
    plate_diameter_mm: float | None = None
    hole: str | None = None
    hole_count: int = 0
    hole_min_mm: float | None = None
    hole_max_mm: float | None = None

    def prompt(self) -> str:
        lines = [self.sentence.strip()]
        if self.domain == "mechanical_2d":
            if self.plate_width_mm and self.plate_height_mm:
                lines.append(f"The flat outline is {self.plate_width_mm:g}×{self.plate_height_mm:g} mm.")
            if self.plate_diameter_mm:
                lines.append(f"The circular outline is {self.plate_diameter_mm:g} mm diameter.")
            if self.hole and self.hole_count and self.hole_min_mm is not None and self.hole_max_mm is not None:
                lines.append(
                    f"Cut {self.hole_count} {self.hole} clearance holes between "
                    f"{self.hole_min_mm:g} and {self.hole_max_mm:g} mm diameter."
                )
            text = "\n".join(lines)
            lowered = text.lower()
            for token in _FORBIDDEN:
                if token in lowered:
                    raise ValueError(f"spec card prompt contains forbidden token: {token}")
            return text
        if self.material and self.insert and self.insert_count:
            lines.append(
                f"The base is printed in {self.material} and mounted with "
                f"{self.insert_count} {self.insert} heat-set inserts."
            )
        if self.min_wall_mm is not None:
            lines.append(f"Walls at the joints are at least {self.min_wall_mm:g} mm thick.")
        text = "\n".join(lines)
        lowered = text.lower()
        for token in _FORBIDDEN:
            if token in lowered:
                raise ValueError(f"spec card prompt contains forbidden token: {token}")
        return text

    def requirement_ids(self) -> set[str]:
        return {item.id for item in self.requirements}


def forbidden_prompt_tokens() -> frozenset[str]:
    return _FORBIDDEN
