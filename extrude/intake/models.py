"""Doorway shapes for the requirement card. No parsing and no defaults logic."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class SlotOrigin(str, Enum):
    user_span = "user_span"
    default = "default"
    waived = "waived"


class FrozenSpec(BaseModel):
    task_class: Literal["buck", "ldo", "holdup_mlcc", "led", "mcu_swap"]
    values_si: dict[str, float]
    origins: dict[str, SlotOrigin]
    defaults_version: str
    spec_hash: str


class NeedsInfo(BaseModel):
    missing: list[str]
    question: str
