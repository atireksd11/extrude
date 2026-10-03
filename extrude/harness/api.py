"""Front door. The model proposes. The earlier rooms judge."""

from extrude.harness.loop import clear_client, set_client, walk
from extrude.harness.models import RunResult


def run(raw_text: str) -> RunResult:
    return walk(raw_text)


__all__ = ["clear_client", "run", "set_client"]
