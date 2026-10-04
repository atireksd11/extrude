"""The frozen eight. Written as the questions, not as a harness tuned to them."""

import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parents[2] / "eval" / "proxy_tasks"
_POWER = {
    "holdup": "holdup_mlcc",
    "buck": "buck",
    "regulator": "ldo",
}


class ReferencePart(BaseModel):
    item: str
    qty: int
    usd: float


class PracticeTask(BaseModel):
    id: str
    family: Literal["power", "other"]
    prompt: str
    reference_bom_usd: float
    reference_parts: list[ReferencePart]
    answer: str
    technical_check: str
    card_kind: Literal["frozen", "needs_info"]
    card: dict = Field(default_factory=dict)


def load_tasks() -> list[PracticeTask]:
    found = []
    for path in sorted(_ROOT.glob("*/task.json")):
        found.append(PracticeTask(**json.loads(path.read_text(encoding="utf-8"))))
    ids = [task.id for task in found]
    if len(found) != 8 or len(set(ids)) != 8:
        raise ValueError("the practice set must be eight unique tasks")
    if sum(task.family == "other" for task in found) != 5:
        raise ValueError("five tasks must sit outside the power seat")
    for task in found:
        if task.reference_bom_usd <= 0 or not task.technical_check.strip() or not task.answer.strip():
            raise ValueError(f"{task.id} is missing its answer, check, or reference cost")
        if not task.reference_parts or any(part.qty < 1 or part.usd <= 0 or not part.item.strip() for part in task.reference_parts):
            raise ValueError(f"{task.id} is missing a reference parts list")
        total = sum(part.qty * part.usd for part in task.reference_parts)
        if not math.isclose(total, task.reference_bom_usd, rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"{task.id} reference parts do not add up to the reference cost")
        expected = _POWER.get(task.id)
        if expected is None:
            if task.family != "other":
                raise ValueError(f"{task.id} is not one of the three power tasks")
            continue
        if task.family != "power" or task.card_kind != "frozen":
            raise ValueError(f"{task.id} must freeze a power card")
        if task.card.get("task_class") != expected:
            raise ValueError(f"{task.id} froze the wrong circuit")
    return found
