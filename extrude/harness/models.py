"""Front-door result. The walk across rooms is not built."""

from pydantic import BaseModel


class AttemptBudget(BaseModel):
    model_design_used: int = 0
    model_design_max: int = 2


class RunResult(BaseModel):
    spec_hash: str = ""
    status: str = "not_built"
    detail: str | None = None
    attempts: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    bom_usd: float | None = None
    reference_bom_usd: float | None = None
    notice: str | None = None
    netlist: str | None = None
    code: str | None = None
    preview_png: str | None = None
    stl_path: str | None = None
    svg_path: str | None = None
