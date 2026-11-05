"""Score a frozen 2D task fixture."""

from pathlib import Path

from eval.mechanical_2d.spec_card import TaskSpec
from extrude.verify.svg import score_openscad_2d


def score_task(task: TaskSpec, source: Path, out_dir: Path) -> dict:
    return score_openscad_2d(source, task.to_verify(), out_dir)
