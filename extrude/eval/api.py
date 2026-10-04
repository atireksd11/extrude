"""Practice-set score. A failed circuit gets no credit for a cheap parts list."""

import math

from extrude.eval.models import ScoreCard
from extrude.harness.models import RunResult

UNCHECKED = "Not checked: heat-in-airflow, radios, and fast memory."
NOT_OFFICIAL = "This is not an official EEBench score."


def blend(technical: float, cost_efficiency: float) -> float:
    if technical != 1.0 or not math.isfinite(technical):
        return 0.0
    if not math.isfinite(cost_efficiency):
        cost_efficiency = 0.0
    cost_efficiency = min(1.0, max(0.0, cost_efficiency))
    return (0.65 * technical) + (0.35 * cost_efficiency)


def score(result: RunResult) -> ScoreCard:
    if result.status != "checked":
        return ScoreCard(technical=0.0, cost_efficiency=0.0, score=0.0)
    cost_efficiency = _cost_efficiency(result.bom_usd, result.reference_bom_usd)
    return ScoreCard(
        technical=1.0,
        cost_efficiency=cost_efficiency,
        score=blend(1.0, cost_efficiency),
    )


def export_note(result: RunResult) -> str:
    card = score(result)
    if card.technical == 1.0:
        checked = "Checked: the technical result, and parts cost against the reference list."
    else:
        checked = "Checked: the technical result. Parts cost was not credited."
    return "\n".join(
        [
            f"Status: {result.status}",
            f"Technical: {card.technical}",
            f"Cost efficiency: {card.cost_efficiency}",
            f"Score: {card.score}",
            checked,
            UNCHECKED,
            NOT_OFFICIAL,
        ]
    )


def _cost_efficiency(bom_usd: float | None, reference_bom_usd: float | None) -> float:
    if bom_usd is None or reference_bom_usd is None:
        return 0.0
    if not math.isfinite(bom_usd) or not math.isfinite(reference_bom_usd):
        return 0.0
    if bom_usd <= 0 or reference_bom_usd <= 0:
        return 0.0
    return min(1.0, reference_bom_usd / bom_usd)
