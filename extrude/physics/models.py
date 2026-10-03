"""Shared physical numbers. Phase 0 does not compute them."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CurveSource(str, Enum):
    vendor_table = "vendor_table"
    same_mfr_series = "same_mfr_series"
    generic_screen = "generic_screen"
    not_class_ii = "not_class_ii"


class CapValue(BaseModel):
    refdes: str
    c_nominal: float
    c_eff: float
    c_use: float
    curve_source: CurveSource
    v_dc: float


class PhysicsValues(BaseModel):
    caps: list[CapValue] = Field(default_factory=list)
    vout_dc: float | None = None
    ripple_pp: float | None = None
    conduction: Literal["ccm", "dcm", "not_a_switcher"] | None = None
    p_diss_w: float | None = None
    tj_estimate_c: float | None = None
