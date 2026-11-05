"""Doorway shapes for the requirement card. No parsing and no defaults logic."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SlotOrigin(str, Enum):
    user_span = "user_span"
    default = "default"
    waived = "waived"


class FrozenSpec(BaseModel):
    task_class: Literal[
        "buck",
        "ldo",
        "holdup_mlcc",
        "led",
        "mcu_swap",
        "divider",
        "pullup",
        "series",
        "indicator",
        "mechanical_3d",
        "mechanical_2d",
        "ambiguous",
    ]
    values_si: dict[str, float]
    origins: dict[str, SlotOrigin]
    defaults_version: str
    spec_hash: str
    labels: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, str] = Field(default_factory=dict)


class NeedsInfo(BaseModel):
    missing: list[str]
    question: str
