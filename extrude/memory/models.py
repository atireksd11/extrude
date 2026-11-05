"""Notebook rows. Phase 0 does not write a ban."""

import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, field_validator


class PrimaryCause(str, Enum):
    spec_gap = "spec_gap"
    model_design = "model_design"
    tooling = "tooling"
    user_edit = "user_edit"
    physics_uncovered = "physics_uncovered"
    spec_conflict = "spec_conflict"


class ElectricalIdentity(BaseModel):
    manufacturer: str
    capacitance: float
    dielectric: str
    case: str
    voltage_rating: float


class NegativeConstraint(BaseModel):
    identity: ElectricalIdentity
    check_id: str
    checker_version: str
    v_fail: float | None = None
    i_fail: float | None = None
    measured: float
    limit: float
    spec_hash: str


class AttributionEvent(BaseModel):
    cause: PrimaryCause
    spec_hash: str
    detail: str
    spec_confirmed: bool = True
    identity: ElectricalIdentity | None = None
    orderable: str | None = None
    check_id: str = ""
    checker_version: str = ""
    v_fail: float | None = None
    i_fail: float | None = None
    measured: float = 0
    limit: float = 0


class MechanicalIdentity(BaseModel):
    feature_ref: str
    artifact_kind: Literal["circuit", "openscad", "featurescript", "netlist"]
    filament: str | None = None
    printer_profile: str | None = None

    @field_validator("feature_ref")
    @classmethod
    def _feature(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("feature_ref is empty")
        return text

    @field_validator("artifact_kind", mode="before")
    @classmethod
    def _kind(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("filament")
    @classmethod
    def _filament(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text or None

    @field_validator("printer_profile")
    @classmethod
    def _printer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class ViolationRecord(BaseModel):
    domain: Literal["electrical", "mechanical"]
    identity: MechanicalIdentity
    spec_hash: str
    prompt: str
    check_id: str
    detail: str
    measured: float
    limit: float
    error_trace_json: str
    checker_version: str

    @field_validator("domain", mode="before")
    @classmethod
    def _domain(cls, value: str) -> str:
        return str(value).strip().lower()

    @field_validator("spec_hash", "prompt", "check_id", "detail", "checker_version")
    @classmethod
    def _text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("empty field")
        return text

    @field_validator("error_trace_json")
    @classmethod
    def _trace(cls, value: str) -> str:
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("error trace must be a JSON object")
        return json.dumps(parsed, sort_keys=True)
