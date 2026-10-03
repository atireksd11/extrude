"""Practice-set score. Phase 0 does not score a task."""

from pydantic import BaseModel


class ScoreCard(BaseModel):
    technical: float | None = None
    cost_efficiency: float | None = None
    score: float | None = None
