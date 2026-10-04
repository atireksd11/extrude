"""Walk the rooms. The model proposes. The checks decide."""

import os

from extrude.checks import preflight
from extrude.emit import emit_cir
from extrude.harness.client import complete
from extrude.harness.models import RunResult
from extrude.harness.prompt import build_prompt
from extrude.harness.proposal import ProposalError, parse_proposal
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, NeedsInfo
from extrude.memory import design_rows, from_simulator_log, record
from extrude.memory.models import AttributionEvent, ElectricalIdentity, PrimaryCause
from extrude.physics import derive
from extrude.sim import run_allowed

_JOBS = {"buck", "ldo", "holdup_mlcc"}
_client = complete


def set_client(fn) -> None:
    global _client
    _client = fn


def clear_client() -> None:
    global _client
    _client = complete


def walk(raw_text: str) -> RunResult:
    resolved = resolve(raw_text)
    if isinstance(resolved, NeedsInfo):
        return RunResult(status="needs_info", detail=resolved.question)
    if resolved.task_class not in _JOBS:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail="this seat only designs a buck, regulator, or hold-up",
        )
    passed: list[str] = []
    design_tries = 0
    seat = "primary"
    escalated = False
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = None
    last_error = ""
    while True:
        blocks = [row for row in design_rows() if row.spec_hash == resolved.spec_hash][:8]
        prompt = build_prompt(resolved, blocks, passed, last_error)
        try:
            text, usage = _client(prompt, seat)
        except ProposalError as exc:
            _note(resolved, "tool", exc.detail, None)
            return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, exc.detail)
        except Exception as exc:
            _note(resolved, "tool", str(exc), None)
            return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, "the model call failed")
        prompt_tokens, completion_tokens, cost_usd = _add_bill(
            prompt_tokens, completion_tokens, cost_usd, usage
        )
        design = None
        identity = None
        try:
            design, identity = parse_proposal(text, resolved)
        except ProposalError as exc:
            if exc.kind == "tool":
                _note(resolved, "tool", exc.detail, None)
                return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, exc.detail)
            design_tries += 1
            last_error = exc.detail
            _note(resolved, "design", exc.detail, identity)
            nxt = _after_design_miss(design_tries, escalated)
            if nxt is None:
                return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, exc.detail)
            seat, escalated = nxt
            continue
        report = preflight(design)
        if report.blocking:
            design_tries += 1
            last_error = "; ".join(report.blocking)
            _note(resolved, "design", last_error, identity)
            nxt = _after_design_miss(design_tries, escalated)
            if nxt is None:
                return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, report.blocking[0])
            seat, escalated = nxt
            continue
        if "preflight" not in passed:
            passed.append("preflight")
        values = derive(design, resolved)
        failures = [item for item in values.findings if item.severity == "fail"]
        if failures:
            design_tries += 1
            last_error = failures[0].detail
            _note(resolved, "design", last_error, identity)
            nxt = _after_design_miss(design_tries, escalated)
            if nxt is None:
                return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, failures[0].detail)
            seat, escalated = nxt
            continue
        if resolved.task_class == "holdup_mlcc":
            if not _holdup_cap_is_connected(design):
                design_tries += 1
                last_error = "the hold-up capacitor is not connected"
                _note(resolved, "design", last_error, identity)
                nxt = _after_design_miss(design_tries, escalated)
                if nxt is None:
                    return _finish(
                        "stopped",
                        resolved,
                        design_tries,
                        prompt_tokens,
                        completion_tokens,
                        cost_usd,
                        "the hold-up capacitor is not connected",
                    )
                seat, escalated = nxt
                continue
            simulated = run_allowed(emit_cir(design, values))
            if simulated.status == "refused":
                design_tries += 1
                last_error = simulated.detail or "the deck was refused"
                _note(resolved, "design", last_error, identity)
                nxt = _after_design_miss(design_tries, escalated)
                if nxt is None:
                    return _finish(
                        "stopped",
                        resolved,
                        design_tries,
                        prompt_tokens,
                        completion_tokens,
                        cost_usd,
                        simulated.detail or "the deck was refused",
                    )
                seat, escalated = nxt
                continue
            if simulated.status != "measured":
                record(from_simulator_log(simulated.detail or simulated.status, resolved.spec_hash))
                return _finish(
                    "stopped",
                    resolved,
                    design_tries,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    simulated.detail or simulated.status,
                )
        return _finish("checked", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, "checked")


def _holdup_cap_is_connected(design) -> bool:
    capacitors = {
        part.refdes
        for part in design.parts
        if part.kind == "capacitor" and part.capacitance and part.capacitance > 0
    }
    for refdes in capacitors:
        pins = [
            pin
            for pin in design.pins
            if pin.refdes == refdes and pin.state == "connected" and pin.net and pin.net.strip()
        ]
        if len(pins) >= 2:
            return True
    return False


def _after_design_miss(design_tries: int, escalated: bool) -> tuple[str, bool] | None:
    if design_tries < 2:
        return "primary", escalated
    if not escalated and os.environ.get("EXTRUDE_ESCALATION_KEY", "").strip():
        return "escalation", True
    return None


def _note(spec: FrozenSpec, kind: str, detail: str, identity: ElectricalIdentity | None) -> None:
    if kind == "tool":
        record(from_simulator_log(detail, spec.spec_hash))
        return
    record(
        AttributionEvent(
            cause=PrimaryCause.model_design,
            spec_hash=spec.spec_hash,
            detail=detail,
            spec_confirmed=True,
            identity=identity,
            check_id="proposal",
            checker_version="2026-10-03",
            measured=0,
            limit=0,
        )
    )


def _add_bill(prompt_tokens: int, completion_tokens: int, cost_usd: float | None, usage: dict) -> tuple[int, int, float | None]:
    if usage.get("prompt_tokens") is not None:
        prompt_tokens += int(usage["prompt_tokens"])
    if usage.get("completion_tokens") is not None:
        completion_tokens += int(usage["completion_tokens"])
    if usage.get("cost_usd") is not None:
        cost_usd = (cost_usd or 0) + float(usage["cost_usd"])
    return prompt_tokens, completion_tokens, cost_usd


def _finish(status, spec, tries, prompt_tokens, completion_tokens, cost_usd, detail) -> RunResult:
    return RunResult(
        status=status,
        spec_hash=spec.spec_hash,
        detail=detail,
        attempts=tries,
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        cost_usd=cost_usd,
    )
