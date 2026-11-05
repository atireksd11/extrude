"""Front door. The model proposes. The earlier rooms judge."""

from extrude.harness.loop import bind_constraints, clear_client, set_client, walk
from extrude.harness.models import RunResult


def run(raw_text: str, *, filament: str = "PETG") -> RunResult:
    return walk(raw_text, filament=filament)


__all__ = ["bind_constraints", "clear_client", "run", "set_client"]
