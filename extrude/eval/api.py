"""Score entry. The body stays refused until Phase 7."""

from extrude.eval.models import ScoreCard
from extrude.harness.models import RunResult


def score(result: RunResult) -> ScoreCard:
    raise NotImplementedError("not built")
