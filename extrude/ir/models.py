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
    capacitance: float | None = None
    tolerance: float | None = None
    dielectric: str | None = None
    voltage_rating: float | None = None
    manufacturer: str | None = None
    series: str | None = None
    case: str | None = None
    esr: float | None = None
    inductance: float | None = None
    theta_ja: float | None = None
    bias_v: float | None = None
    curve_id: str | None = None


class CircuitIR(BaseModel):
    spec_hash: str = ""
    components: list[str] = Field(default_factory=list)
    nets: list[str] = Field(default_factory=list)
    pins: list[Pin] = Field(default_factory=list)
    parts: list[Part] = Field(default_factory=list)
    tied_nets: list[list[str]] = Field(default_factory=list)
    f_sw: float | None = None
