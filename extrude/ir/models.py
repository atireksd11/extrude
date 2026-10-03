"""The design file. Fields only. Nothing here rewires a net."""

from typing import Literal

from pydantic import BaseModel, Field


class Pin(BaseModel):
    refdes: str
    name: str
    net: str | None = None
    state: Literal["open", "nc", "connected"] = "open"


class CircuitIR(BaseModel):
    spec_hash: str = ""
    components: list[str] = Field(default_factory=list)
    nets: list[str] = Field(default_factory=list)
    pins: list[Pin] = Field(default_factory=list)
