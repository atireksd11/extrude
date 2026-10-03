"""Design-file entry. Saving and loading stay refused in Phase 0."""

from pathlib import Path

from extrude.ir.models import CircuitIR


def save(ir: CircuitIR, path: Path) -> None:
    raise NotImplementedError("not built")


def load(path: Path) -> CircuitIR:
    raise NotImplementedError("not built")
