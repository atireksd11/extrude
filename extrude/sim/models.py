"""Simulator result shape. Starting ngspice is a later phase."""

from pydantic import BaseModel, Field


class SimResult(BaseModel):
    status: str
    measurements: dict[str, float] = Field(default_factory=dict)
    cause: str | None = None
    detail: str | None = None
