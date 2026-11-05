"""Wiring-check result. Phase 0 never marks a design good."""

from typing import Literal

from pydantic import BaseModel, Field


class PreflightReport(BaseModel):
    blocking: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ToleranceMeasurement(BaseModel):
    check_id: str
    feature: str
    measured_mm: float
    limit_mm: float
    delta_mm: float
    severity: Literal["block", "warn"] = "block"


class ToleranceReport(BaseModel):
    blocking: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    measurements: list[ToleranceMeasurement] = Field(default_factory=list)


class VerifierMiss(BaseModel):
    """One measured miss from a compiler-backed checker."""

    check_id: str
    measured: float
    limit: float
    delta: float
    feature_ref: str = ""
    detail: str = ""
    cause: str = "model_design"
