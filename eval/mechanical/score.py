"""Score a task candidate with the solid verifier."""

from pathlib import Path

from eval.mechanical.spec_card import TaskSpec
from extrude.verify.solid import score_openscad


def score_task(task: TaskSpec, source: Path, out_dir: Path | None = None) -> dict:
    folder = out_dir or source.parent / "render" / source.stem
    return score_openscad(source, task.to_verify(), folder)
