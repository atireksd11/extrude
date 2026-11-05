"""Walk the rooms. The model proposes. The checks decide."""

import os
from pathlib import Path

from extrude.checks import preflight
from extrude.coverage.api import render
from extrude.eval.bom import design_bom_usd
from extrude.emit import emit_cir
from extrude.emit.netlist import emit_netlist
from extrude.harness.client import complete
from extrude.harness.causes import classify_miss, effective_cause
from extrude.harness.models import AttemptBudget, RunResult
from extrude.harness.passive import PASSIVE, build as build_passive, spice_miss
from extrude.harness.prompt import build_prompt
from extrude.harness.proposal import ProposalError, parse_proposal
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, NeedsInfo
from extrude.memory import design_rows, from_simulator_log, record
from extrude.memory.models import AttributionEvent, ElectricalIdentity, PrimaryCause
from extrude.physics import derive
from extrude.sim import run_allowed

_CIRCUIT_JOBS = {"buck", "ldo", "holdup_mlcc"}
_MECHANICAL_JOBS = {"mechanical_3d", "mechanical_2d"}
_JOBS = _CIRCUIT_JOBS | _MECHANICAL_JOBS
_FORMAT_MAX = 2
_GROUNDS = {"GND", "AGND", "PGND", "DGND"}
_HOLDUP_DISCONNECTED = (
    "the hold-up capacitor is not connected. "
    "Repair this before anything else: add one capacitor whose capacitance is at least c_min, "
    "and put two pin objects for that refdes in the top-level pins array. "
    "One pin net is the rail and the other pin net is GND. Both states are connected. "
    "A capacitor listed only inside parts, or with one pin, is still not connected."
)
_client = complete
_bound: list | None = None


def set_client(fn) -> None:
    global _client
    _client = fn


def clear_client() -> None:
    global _client
    _client = complete


def bind_constraints(blocks: list | None) -> None:
    global _bound
    _bound = blocks


def walk(raw_text: str, *, filament: str = "PETG") -> RunResult:
    sentence = raw_text.strip()
    resolved = resolve(raw_text)
    if isinstance(resolved, NeedsInfo):
        return RunResult(status="needs_info", detail=resolved.question, notice=render(None, []))
    if resolved.task_class in PASSIVE:
        return _passive(resolved)
    if resolved.task_class in _MECHANICAL_JOBS:
        return _mechanical_walk(resolved, sentence, filament)
    if resolved.task_class not in _CIRCUIT_JOBS:
        return RunResult(
            status="stopped",
            spec_hash=resolved.spec_hash,
            detail="this seat only designs a buck, regulator, or hold-up",
            notice=render(resolved, []),
        )
    passed: list[str] = []
    budget = AttemptBudget()
    design_tries = 0
    format_tries = 0
    seat = "primary"
    escalated = False
    prompt_tokens = 0
    completion_tokens = 0
    cost_usd = None
    last_error = ""
    while True:
        blocks = _prompt_blocks(resolved)
        prompt = build_prompt(resolved, blocks, passed, last_error)
        if not _within_spend():
            return _finish(
                "stopped",
                resolved,
                design_tries,
                prompt_tokens,
                completion_tokens,
                cost_usd,
                "the Luna spend cap was reached",
            )
        try:
            text, usage = _client(prompt, seat)
        except ProposalError as exc:
            _note(resolved, "tool", exc.detail, None, user_prompt=sentence)
            return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, exc.detail)
        except Exception as exc:
            _note(resolved, "tool", str(exc), None, user_prompt=sentence)
            return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, "the model call failed")
        prompt_tokens, completion_tokens, cost_usd = _add_bill(
            prompt_tokens, completion_tokens, cost_usd, usage
        )
        if usage.get("cost_usd") is not None:
            _note_spend(float(usage["cost_usd"]))
        _keep_reply(text)
        design = None
        identity = None
        try:
            design, identity = parse_proposal(text, resolved)
        except ProposalError as exc:
            if exc.kind == "tool":
                _note(resolved, "tool", exc.detail, None, tool_failed=True, user_prompt=sentence)
                return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, exc.detail)
            if exc.kind == "format":
                format_tries += 1
                last_error = exc.detail
                if format_tries <= _FORMAT_MAX:
                    continue
                return _finish(
                    "stopped",
                    resolved,
                    design_tries,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    exc.detail,
                )
            design_tries += 1
            budget.model_design_used = design_tries
            last_error = exc.detail
            _note(resolved, "design", exc.detail, identity, user_prompt=sentence)
            nxt = _after_design_miss(design_tries, escalated, budget)
            if nxt is None:
                return _finish("stopped", resolved, design_tries, prompt_tokens, completion_tokens, cost_usd, exc.detail)
            seat, escalated = nxt
            continue
        report = preflight(design)
        if report.blocking:
            design_tries += 1
            budget.model_design_used = design_tries
            last_error = "; ".join(report.blocking)
            _note(resolved, "design", last_error, identity, user_prompt=sentence)
            nxt = _after_design_miss(design_tries, escalated, budget)
            if nxt is None:
                return _finish(
                    "stopped",
                    resolved,
                    design_tries,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    report.blocking[0],
                    ran=["wiring"],
                    stopped="wiring",
                )
            seat, escalated = nxt
            continue
        if "preflight" not in passed:
            passed.append("preflight")
        values = derive(design, resolved)
        failures = [item for item in values.findings if item.severity == "fail"]
        if failures:
            design_tries += 1
            budget.model_design_used = design_tries
            last_error = failures[0].detail
            _note(resolved, "design", last_error, identity, check_id=failures[0].code, user_prompt=sentence)
            nxt = _after_design_miss(design_tries, escalated, budget)
            if nxt is None:
                return _finish(
                    "stopped",
                    resolved,
                    design_tries,
                    prompt_tokens,
                    completion_tokens,
                    cost_usd,
                    failures[0].detail,
                    ran=_after_physics(resolved, values),
                    stopped=_failed_physics(resolved.task_class, failures[0].code),
                )
            seat, escalated = nxt
            continue
        if resolved.task_class == "holdup_mlcc":
            if not _holdup_cap_is_connected(design):
                design_tries += 1
                budget.model_design_used = design_tries
                last_error = _HOLDUP_DISCONNECTED
                _note(resolved, "design", last_error, identity, check_id="holdup_connection", user_prompt=sentence)
                nxt = _after_design_miss(design_tries, escalated, budget)
                if nxt is None:
                    return _finish(
                        "stopped",
                        resolved,
                        design_tries,
                        prompt_tokens,
                        completion_tokens,
                        cost_usd,
                        _HOLDUP_DISCONNECTED,
                        ran=_after_physics(resolved, values),
                        stopped="hold-up connection",
                    )
                seat, escalated = nxt
                continue
            simulated = run_allowed(emit_cir(design, values))
            if simulated.status == "refused":
                design_tries += 1
                budget.model_design_used = design_tries
                last_error = simulated.detail or "the deck was refused"
                _note(resolved, "design", last_error, identity, check_id="holdup_fade", user_prompt=sentence)
                nxt = _after_design_miss(design_tries, escalated, budget)
                if nxt is None:
                    return _finish(
                        "stopped",
                        resolved,
                        design_tries,
                        prompt_tokens,
                        completion_tokens,
                        cost_usd,
                        simulated.detail or "the deck was refused",
                        ran=[*_after_physics(resolved, values), "hold-up fade"],
                        stopped="hold-up fade",
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
                    ran=[*_after_physics(resolved, values), "hold-up fade"],
                    stopped="hold-up fade",
                )
        return _finish(
            "checked",
            resolved,
            design_tries,
            prompt_tokens,
            completion_tokens,
            cost_usd,
            "checked",
            design_bom_usd(design, resolved.task_class),
            ran=_passed(resolved, values),
            netlist=emit_netlist(design),
        )


def _passive(spec: FrozenSpec) -> RunResult:
    design, deck = build_passive(spec)
    report = preflight(design)
    ran = ["wiring"]
    if report.blocking:
        return _finish("stopped", spec, 0, 0, 0, None, report.blocking[0], ran=ran, stopped="wiring")
    family = {
        "divider": "divider ratio",
        "pullup": "pull-up voltage",
        "series": "series resistor",
        "indicator": "lamp current",
        "led": "lamp current",
    }[spec.task_class]
    if deck:
        simulated = run_allowed(deck)
        if simulated.status == "refused":
            return _finish(
                "stopped",
                spec,
                0,
                0,
                0,
                None,
                simulated.detail or "the deck was refused",
                ran=[*ran, family],
                stopped=family,
            )
        if simulated.status == "measured":
            ran.append(family)
            miss = spice_miss(spec, simulated)
            if miss:
                return _finish("stopped", spec, 0, 0, 0, None, miss, ran=ran, stopped=family)
    else:
        ran.append(family)
    return _finish(
        "checked",
        spec,
        0,
        0,
        0,
        None,
        "checked",
        design_bom_usd(design, spec.task_class),
        ran=[*ran, "parts-cost"],
        netlist=emit_netlist(design),
    )


def _prompt_blocks(spec: FrozenSpec) -> list:
    if os.environ.get("EXTRUDE_MEMORY_DB", "").strip() and _bound is not None:
        return list(_bound)[:3]
    return [row for row in design_rows() if row.spec_hash == spec.spec_hash][:8]


def _keep_reply(text: str) -> None:
    path = os.environ.get("EXTRUDE_SAVE_REPLY", "").strip()
    if not path:
        return
    target = Path(path)
    previous = target.read_text(encoding="utf-8") if target.is_file() else ""
    target.write_text(text if not previous else previous + "\n\n---\n\n" + text, encoding="utf-8")


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
        nets = {_net_id(pin.net) for pin in pins}
        if len(pins) >= 2 and len(nets) >= 2:
            return True
    return False


def _net_id(net: str) -> str:
    token = net.strip().upper()
    if token in _GROUNDS:
        return "GND"
    return token


def _mechanical_walk(spec: FrozenSpec, sentence: str, filament: str) -> RunResult:
    from extrude.harness.mechanical import walk_mechanical

    result = walk_mechanical(spec, sentence, filament)
    return result.model_copy(update={"notice": render(spec, ["solid verify"] if result.code else [])})


def _after_design_miss(
    design_tries: int,
    escalated: bool,
    budget: AttemptBudget,
) -> tuple[str, bool] | None:
    if design_tries < budget.model_design_max:
        return "primary", escalated
    if not escalated and os.environ.get("EXTRUDE_ESCALATION_KEY", "").strip():
        return "escalation", True
    return None


def _note(
    spec: FrozenSpec,
    kind: str,
    detail: str,
    identity: ElectricalIdentity | None,
    *,
    check_id: str = "proposal",
    spec_on_card: bool = True,
    tool_failed: bool = False,
    user_prompt: str = "",
) -> None:
    if kind == "tool" or tool_failed:
        record(from_simulator_log(detail, spec.spec_hash))
        return
    cause = effective_cause(
        classify_miss(check_id=check_id, spec_on_card=spec_on_card, tool_failed=False),
        spec_confirmed=True,
    )
    if cause is PrimaryCause.spec_gap:
        from extrude.memory.db import insert_prompt_note

        insert_prompt_note(prompt=user_prompt or detail, check_id=check_id, detail=detail)
        return
    if cause is PrimaryCause.tooling:
        record(from_simulator_log(detail, spec.spec_hash))
        return
    record(
        AttributionEvent(
            cause=cause,
            spec_hash=spec.spec_hash,
            detail=detail,
            spec_confirmed=True,
            identity=identity,
            check_id=check_id,
            checker_version="2026-10-04",
            measured=0,
            limit=0,
        )
    )


def _within_spend() -> bool:
    from extrude.copilot.budget import under_cap

    return under_cap()


def _note_spend(amount: float) -> None:
    from extrude.copilot.budget import note_spend

    note_spend(amount)


def _add_bill(prompt_tokens: int, completion_tokens: int, cost_usd: float | None, usage: dict) -> tuple[int, int, float | None]:
    if usage.get("prompt_tokens") is not None:
        prompt_tokens += int(usage["prompt_tokens"])
    if usage.get("completion_tokens") is not None:
        completion_tokens += int(usage["completion_tokens"])
    if usage.get("cost_usd") is not None:
        cost_usd = (cost_usd or 0) + float(usage["cost_usd"])
    return prompt_tokens, completion_tokens, cost_usd


def _after_physics(spec: FrozenSpec, values) -> list[str]:
    ran = ["wiring"]
    if spec.task_class in {"buck", "holdup_mlcc"} and values.caps:
        ran.append("capacitance")
    if spec.task_class == "buck" and values.ripple_pp is not None:
        ran.append("ripple")
    if values.heat_note:
        ran.append("still-air heat")
    return ran


def _failed_physics(task_class: str, code: str) -> str:
    if "ripple" in code:
        return "ripple"
    if task_class == "ldo":
        return "still-air heat"
    return "capacitance"


def _passed(spec: FrozenSpec, values) -> list[str]:
    ran = _after_physics(spec, values)
    if spec.task_class == "holdup_mlcc":
        ran.extend(["hold-up connection", "hold-up fade"])
    ran.append("parts-cost")
    return ran


def _finish(
    status,
    spec,
    tries,
    prompt_tokens,
    completion_tokens,
    cost_usd,
    detail,
    parts_usd=None,
    ran=None,
    stopped=None,
    netlist=None,
) -> RunResult:
    return RunResult(
        status=status,
        spec_hash=spec.spec_hash,
        detail=detail,
        bom_usd=parts_usd,
        notice=render(spec, list(ran or []), stopped),
        netlist=netlist,
        attempts=tries,
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        cost_usd=cost_usd,
    )
