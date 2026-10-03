"""Wiring-check result. Phase 0 never marks a design good."""

from pydantic import BaseModel, Field


class PreflightReport(BaseModel):
    blocking: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
