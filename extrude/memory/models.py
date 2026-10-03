"""Notebook rows. Phase 0 does not write a ban."""

from enum import Enum

from pydantic import BaseModel


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
