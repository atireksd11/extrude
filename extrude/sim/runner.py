"""Start ngspice only after the deck is allowed. Crashes are tool problems."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from extrude.sim.models import SimResult
from extrude.sim.policy import refusal_reason

_TIMEOUT_S = 15
_MEAS = re.compile(
    r"(?im)^\s*([A-Za-z_][\w.]*)\s*=\s*([+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?)"
)


def ngspice_binary() -> str | None:
    chosen = os.environ.get("NGSPICE_PATH", "").strip()
    if chosen:
        return chosen if Path(chosen).is_file() else None
    return shutil.which("ngspice")


def run_deck(deck: str) -> SimResult:
    reason = refusal_reason(deck)
    if reason is not None:
        return SimResult(status="refused", cause="policy", detail=reason)
    binary = ngspice_binary()
    if binary is None:
        return SimResult(
            status="unavailable",
            cause="tooling",
            detail="ngspice was not found through NGSPICE_PATH or PATH",
        )
    try:
        log = _execute(binary, deck)
    except subprocess.TimeoutExpired:
        return SimResult(status="tooling", cause="tooling", detail="timeout")
    lowered = log.lower()
    if "singular matrix" in lowered or "timestep too small" in lowered:
        return SimResult(status="tooling", cause="tooling", detail="simulator_crash")
    measurements = {name: float(value) for name, value in _MEAS.findall(log)}
    if not measurements:
        return SimResult(status="tooling", cause="tooling", detail="no_measurement")
    return SimResult(status="measured", measurements=measurements, detail="ok")


def _execute(binary: str, deck: str) -> str:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "deck.cir"
        path.write_text(deck, encoding="utf-8")
        completed = subprocess.run(
            [binary, "-b", "-o", "run.log", str(path)],
            cwd=folder,
            timeout=_TIMEOUT_S,
            capture_output=True,
            check=False,
        )
        log_path = Path(folder) / "run.log"
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
        stderr = completed.stderr.decode("utf-8", errors="replace")
        return "\n".join((log, stderr, completed.stdout.decode("utf-8", errors="replace")))
