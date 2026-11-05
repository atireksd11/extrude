"""Verifier-facing mechanical spec. Thresholds live here, not in csg_read."""

from pydantic import BaseModel, Field


class SolidVerifySpec(BaseModel):
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
    require_colors: bool = False
    link_span_mm: float = 40.0
    finger_length_min_mm: float = 12.0
    finger_length_max_mm: float = 40.0
    hull_link_span_mm: float = 50.0
    min_wall_mm_threshold: float = 2.0
    checks: list[str] = Field(default_factory=list)

    def enabled(self, name: str) -> bool:
        if not self.checks:
            return name == "compiles"
        return name in self.checks


class SvgVerifySpec(BaseModel):
    sentence: str
    plate_width_mm: float | None = None
    plate_height_mm: float | None = None
    plate_diameter_mm: float | None = None
    hole: str | None = None
    hole_count: int = 0
    hole_min_mm: float | None = None
    hole_max_mm: float | None = None
    hole_positions: list[tuple[float, float]] = Field(default_factory=list)
    position_tolerance_mm: float = 0.5
    min_edge_distance_mm: float = 2.0
    checks: list[str] = Field(default_factory=list)

    def enabled(self, name: str) -> bool:
        if not self.checks:
            return name == "compiles"
        return name in self.checks
