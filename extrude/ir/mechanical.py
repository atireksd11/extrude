"""Mechanical design file. The electrical IR stays in models.py."""

from typing import Literal

from pydantic import BaseModel, Field


class HoleFeature(BaseModel):
    name: str
    diameter_mm: float
    depth_mm: float | None = None
    position_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    intended_insert: Literal["M2", "M3", "M4", "none"] | None = None


class WallFeature(BaseModel):
    name: str
    thickness_mm: float
    normal_z: float | None = None


class MechanicalIR(BaseModel):
    holes: list[HoleFeature] = Field(default_factory=list)
    walls: list[WallFeature] = Field(default_factory=list)
    bounds_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    source: str
    warnings: list[str] = Field(default_factory=list)
