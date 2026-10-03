"""The design file. Fields only. Nothing here rewires a net."""

from typing import Literal

from pydantic import BaseModel, Field


class Pin(BaseModel):
    refdes: str
    name: str
    net: str | None = None
    state: Literal["open", "nc", "connected"] = "open"
    role: Literal["signal", "power", "ground", "positive", "negative"] = "signal"
    driver: str | None = None


class Part(BaseModel):
    refdes: str
    kind: Literal[
        "ic",
        "resistor",
        "capacitor",
        "inductor",
        "ferrite",
        "ideal_voltage_source",
    ]


class CircuitIR(BaseModel):
    spec_hash: str = ""
    components: list[str] = Field(default_factory=list)
    nets: list[str] = Field(default_factory=list)
    pins: list[Pin] = Field(default_factory=list)
    parts: list[Part] = Field(default_factory=list)
    tied_nets: list[list[str]] = Field(default_factory=list)
