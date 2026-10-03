"""Front-door result. The walk across rooms is not built."""

from pydantic import BaseModel


class AttemptBudget(BaseModel):
    model_design_used: int = 0
    model_design_max: int = 2


class RunResult(BaseModel):
    spec_hash: str = ""
    status: str = "not_built"
