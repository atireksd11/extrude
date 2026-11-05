"""One copilot request. Audit never calls a model."""

import hashlib
import json
import time

from pydantic import BaseModel, Field

from extrude.copilot.budget import begin_request, clear_inflight, under_cap
from extrude.intake.domain import ambiguous_question
from extrude.copilot.fix_loop import repair_openscad
from extrude.copilot.router import RouteDecision, route
from extrude.harness import bind_constraints, run
from extrude.harness.passive import PASSIVE
from extrude.harness.registry import run_electrical, run_mechanical
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, NeedsInfo
from extrude.memory.db import database_path, insert_telemetry, insert_violation
from extrude.memory.rag import remember_run, retrieve, retrieve_violations
from extrude.parse.featurescript import parse_featurescript
from extrude.parse.kicad_netlist import parse_kicad_netlist
from extrude.parse.openscad import parse_openscad


class CopilotRequest(BaseModel):
    text: str | None = None
    artifact: str | None = None
    filename: str | None = None
    printer: str = "generic"
    filament: str = "PLA"
    offline: bool = False
    repair: bool = False


class CopilotResponse(BaseModel):
    status: str
    mode: str
    artifact_kind: str
    detail: str | None = None
    question: str | None = None
    code: str | None = None
    notice: str | None = None
    netlist: str | None = None
    preview_png: str | None = None
    stl_path: str | None = None
    svg_path: str | None = None
    violations: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    locked: list[dict] = Field(default_factory=list)
    attempts: int = 0
    cost_usd: float | None = None
    seconds: float = 0
    constraints: list[dict] = Field(default_factory=list)


def handle(body: CopilotRequest) -> CopilotResponse:
    started = time.perf_counter()
    begin_request()
    decision = route(text=body.text, filename=body.filename, content=body.artifact)
    if decision.artifact_kind == "ambiguous":
        return _done(
            started,
            CopilotResponse(
                status="needs_info",
                mode="generate",
                artifact_kind="ambiguous",
                question=ambiguous_question(),
                detail=ambiguous_question(),
            ),
            body.text or "",
        )
    if decision.artifact_kind == "onshape":
        return _done(
            started,
            CopilotResponse(
                status="needs_info",
                mode="audit",
                artifact_kind="onshape",
                question="Export FeatureScript or OpenSCAD. A live Onshape link is not read in v0.1.",
                detail="Export FeatureScript or OpenSCAD. A live Onshape link is not read in v0.1.",
            ),
            body.text or body.artifact or "",
        )
    if decision.mode == "audit":
        if not (body.artifact or "").strip():
            return _done(
                started,
                CopilotResponse(
                    status="needs_info",
                    mode="audit",
                    artifact_kind=decision.artifact_kind,
                    question="Paste the file contents to audit.",
                    detail="Paste the file contents to audit.",
                ),
                body.filename or "",
            )
        audited = _audit(body, decision.artifact_kind)
        if body.repair and decision.artifact_kind != "openscad":
            note = "Repair only rewrites OpenSCAD."
            audited.detail = f"{audited.detail} {note}" if audited.detail else note
        _remember_audit(body, decision.artifact_kind, audited)
        audited.constraints = _recalled(body, decision.artifact_kind)
        return _done(started, audited, body.text or body.filename or "")
    return _done(started, _generate(body, decision), body.text or "")


def _generate_mechanical(body: CopilotRequest, decision: RouteDecision, resolved: FrozenSpec) -> CopilotResponse:
    if body.offline:
        return CopilotResponse(
            status="needs_info",
            mode="generate",
            artifact_kind=decision.artifact_kind,
            question="Offline mode does not call Luna. Mechanical generate needs the model.",
            detail="Offline mode does not call Luna. Mechanical generate needs the model.",
        )
    if not under_cap():
        return CopilotResponse(
            status="stopped",
            mode="generate",
            artifact_kind=decision.artifact_kind,
            detail="the Luna spend cap was reached",
        )
    constraints: list = []
    text = body.text or ""
    if database_path() is not None:
        constraints = retrieve(resolved, text)
        bind_constraints(constraints)
    try:
        result = run(text, filament=body.filament)
        if database_path() is not None:
            remember_run(resolved, text)
    finally:
        bind_constraints(None)
    return CopilotResponse(
        status=result.status,
        mode="generate",
        artifact_kind=decision.artifact_kind,
        detail=result.detail,
        notice=result.notice,
        code=result.code,
        preview_png=result.preview_png,
        stl_path=result.stl_path,
        svg_path=result.svg_path,
        attempts=result.attempts,
        cost_usd=result.cost_usd,
        constraints=[
            {"check_id": row.check_id, "spec_hash": row.spec_hash} for row in constraints
        ],
    )


def _audit(body: CopilotRequest, kind: str) -> CopilotResponse:
    content = body.artifact or ""
    if kind == "openscad":
        if body.repair:
            fixed = repair_openscad(content, body.filament, prompt=body.text or body.filename or "")
            return CopilotResponse(
                status=fixed.status,
                mode="audit",
                artifact_kind=kind,
                code=fixed.code,
                detail=fixed.detail,
                violations=fixed.violations,
                locked=fixed.locked,
                attempts=fixed.attempts,
            )
        return _mechanical(body, kind, parse_openscad(content))
    if kind == "featurescript":
        return _mechanical(body, kind, parse_featurescript(content))
    if kind == "netlist":
        report = run_electrical(parse_kicad_netlist(content))
        return CopilotResponse(
            status="checked" if not report.blocking else "stopped",
            mode="audit",
            artifact_kind=kind,
            detail=report.blocking[0] if report.blocking else None,
            violations=[{"check_id": item} for item in report.blocking],
            warnings=[{"check_id": item} for item in report.warnings],
        )
    return CopilotResponse(
        status="needs_info",
        mode="audit",
        artifact_kind=kind,
        question="Paste OpenSCAD, FeatureScript, or a KiCad netlist.",
        detail="Paste OpenSCAD, FeatureScript, or a KiCad netlist.",
    )


def _generate(body: CopilotRequest, decision: RouteDecision) -> CopilotResponse:
    text = body.text or ""
    artifact_kind = decision.artifact_kind
    resolved = resolve(text)
    if isinstance(resolved, NeedsInfo):
        return CopilotResponse(
            status="needs_info",
            mode="generate",
            artifact_kind=artifact_kind,
            question=resolved.question,
            detail=resolved.question,
        )
    if resolved.task_class in {"mechanical_3d", "mechanical_2d"}:
        return _generate_mechanical(body, decision, resolved)
    passive = resolved.task_class in PASSIVE
    mechanical = False
    if body.offline and not passive:
        return CopilotResponse(
            status="needs_info",
            mode="generate",
            artifact_kind=artifact_kind,
            question="Offline mode does not call Luna. This request needs the model, or use a passive circuit.",
            detail="Offline mode does not call Luna. This request needs the model, or use a passive circuit.",
        )
    if not passive and not under_cap():
        return CopilotResponse(
            status="stopped",
            mode="generate",
            artifact_kind=artifact_kind,
            detail="the Luna spend cap was reached",
        )
    constraints: list = []
    if database_path() is not None and isinstance(resolved, FrozenSpec):
        constraints = retrieve(resolved, text)
        bind_constraints(constraints)
    try:
        result = run(text, filament=body.filament)
        if database_path() is not None and isinstance(resolved, FrozenSpec):
            remember_run(resolved, text)
    finally:
        bind_constraints(None)
    return CopilotResponse(
        status=result.status,
        mode="generate",
        artifact_kind=artifact_kind,
        detail=result.detail,
        notice=result.notice,
        code=result.code,
        preview_png=result.preview_png,
        stl_path=result.stl_path,
        netlist=result.netlist if result.status == "checked" else None,
        attempts=result.attempts,
        cost_usd=result.cost_usd,
        constraints=[
            {"check_id": row.check_id, "spec_hash": row.spec_hash} for row in constraints
        ],
    )


def _remember_audit(body: CopilotRequest, kind: str, response: CopilotResponse) -> None:
    if response.status != "stopped" or database_path() is None:
        return
    domain = "mechanical" if kind in {"openscad", "featurescript"} else "electrical"
    prompt = (body.text or body.filename or kind).strip() or kind
    digest = hashlib.sha256((body.artifact or "").encode("utf-8")).hexdigest()
    for item in response.violations:
        check_id = str(item.get("check_id") or item.get("rule_id") or "audit")
        feature = str(item.get("feature") or item.get("subsystem") or check_id)
        measured = item.get("measured_mm", item.get("measured", 0))
        limit = item.get("limit_mm", item.get("required_mm", 0))
        insert_violation(
            domain=domain,
            artifact_kind=kind if kind in {"openscad", "featurescript", "netlist", "circuit"} else "circuit",
            spec_hash=digest,
            prompt=prompt,
            check_id=check_id,
            detail=str(item.get("recommended_action") or check_id),
            feature_ref=feature,
            filament=body.filament if domain == "mechanical" else None,
            printer_profile=body.printer if domain == "mechanical" else None,
            measured=float(measured or 0),
            limit=float(limit or 0),
            error_trace_json=json.dumps(item),
            checker_version="2026-10-04",
        )


def _recalled(body: CopilotRequest, kind: str) -> list[dict]:
    if database_path() is None:
        return []
    domain = "mechanical" if kind in {"openscad", "featurescript"} else "electrical"
    prompt = (body.text or body.filename or kind).strip() or kind
    digest = hashlib.sha256((body.artifact or "").encode("utf-8")).hexdigest()
    return [
        {"check_id": row.check_id, "spec_hash": row.spec_hash, "feature": row.identity.feature_ref}
        for row in retrieve_violations(domain, prompt, digest)
    ]


def _done(started: float, response: CopilotResponse, prompt: str) -> CopilotResponse:
    response.seconds = time.perf_counter() - started
    if database_path() is not None:
        insert_telemetry(
            model="offline" if response.cost_usd is None else "luna",
            prompt=prompt,
            status=response.status,
            attempts=response.attempts,
            cost_usd=response.cost_usd,
            seconds=response.seconds,
            harness_on=True,
        )
        clear_inflight()
    return response


def _mechanical(body: CopilotRequest, kind: str, design) -> CopilotResponse:
    report = run_mechanical(design, body.filament)
    blocking = [item.model_dump() for item in report.measurements if item.severity == "block"]
    warnings = [item.model_dump() for item in report.measurements if item.severity == "warn"]
    dropped = [item for item in design.warnings if item.startswith("unparsed_")]
    noted = [item for item in design.warnings if item not in dropped]
    blocking.extend({"check_id": item} for item in dropped)
    warnings.extend({"check_id": item} for item in noted)
    detail = report.blocking[0] if report.blocking else (dropped[0] if dropped else None)
    return CopilotResponse(
        status="checked" if not report.blocking and not dropped else "stopped",
        mode="audit",
        artifact_kind=kind,
        code=body.artifact,
        detail=detail,
        violations=blocking,
        warnings=warnings,
    )
