"""Raw vs harness compare session for the design studio UI."""

import os
import shutil
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from extrude.parse.sniff import validate_paste_filename

from eval.arm_benchmark.score import strip_fences
from extrude.checks import preflight
from extrude.copilot.fix_loop import repair_openscad
from extrude.copilot.router import route
from extrude.emit.netlist import emit_netlist
from extrude.harness.arm_kit import emit_articulated_arm, is_articulated_arm
from extrude.harness.mechanical import (  # noqa: PLC2701
    _complete,
    _openscad_suffix_2d,
    _openscad_suffix_3d,
    _within_spend,
)
from extrude.harness.mechanical_2d_repair import repair_code_2d
from extrude.harness.mechanical_repair import repair_code
from extrude.harness.passive import PASSIVE, build as build_passive
from extrude.harness.proposal import ProposalError, parse_proposal
from extrude.harness.registry import run_electrical, run_mechanical
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, NeedsInfo
from extrude.parse.kicad_netlist import parse_kicad_netlist
from extrude.parse.openscad import parse_openscad
from extrude.physics import derive
from extrude.tools import load_manifest, missing_required, tool_available
from extrude.verify.solid import score_openscad_text, spec_from_frozen
from extrude.verify.svg import score_openscad_2d_text, spec_from_frozen_2d
from extrude.runtime import data_dir

_EVAL = Path(__file__).resolve().parents[2] / "eval"
_SAMPLES_ONLINE = 1
_TEMPERATURE = 0.55


class CheckRow(BaseModel):
    id: str
    passed: bool | None
    detail: str | None = None


class CompareLane(BaseModel):
    label: str
    status: str
    percent: float | None = None
    passed: int = 0
    out_of: int = 0
    checks: list[CheckRow] = Field(default_factory=list)
    misses: list[dict] = Field(default_factory=list)
    code: str | None = None
    netlist: str | None = None
    preview_url: str | None = None
    svg_url: str | None = None
    detail: str | None = None


class CompareResponse(BaseModel):
    session_id: str
    status: str
    mode: str
    domain: str
    task_class: str
    question: str | None = None
    spec_card: dict | None = None
    tooling: dict[str, bool] = Field(default_factory=dict)
    missing_tools: list[str] = Field(default_factory=list)
    raw: CompareLane
    harness: CompareLane
    harness_edited: bool = False
    lift_points: float | None = None
    seconds: float = 0
    cost_usd: float | None = None
    notice: str | None = None


class CompareRequest(BaseModel):
    text: str | None = Field(default=None, max_length=16000)
    artifact: str | None = Field(default=None, max_length=512000)
    filename: str | None = Field(default=None, max_length=255)
    filament: str = Field(default="PETG", max_length=100)
    offline: bool = False

    _valid_filename = field_validator("filename")(validate_paste_filename)


def run_compare(body: CompareRequest) -> CompareResponse:
    started = time.perf_counter()
    session_id = uuid.uuid4().hex[:12]
    session_dir = data_dir() / "generated" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    tooling = {name: tool_available(name) for name in load_manifest()["tools"]}
    os.environ["EXTRUDE_STUDIO_RENDER"] = "1"
    body = _normalize_request(body)
    decision = route(text=body.text, filename=body.filename, content=body.artifact)

    if decision.artifact_kind == "ambiguous":
        return _empty_response(
            session_id,
            "needs_info",
            decision.mode,
            "ambiguous",
            "ambiguous",
            question="Is this a 3D print, a 2D flat plate, or an electrical circuit?",
            started=started,
            tooling=tooling,
        )

    if decision.mode == "audit":
        return _compare_audit(
            session_id,
            body,
            kind=decision.artifact_kind,
            started=started,
            tooling=tooling,
        )

    resolved = resolve(body.text or "")
    if isinstance(resolved, NeedsInfo):
        return _empty_response(
            session_id,
            "needs_info",
            "generate",
            "unknown",
            "unknown",
            question=resolved.question,
            started=started,
            tooling=tooling,
        )

    if resolved.task_class in {"mechanical_3d", "mechanical_2d"}:
        return _compare_mechanical_generate(
            session_id,
            session_dir,
            resolved,
            filament=body.filament,
            offline=body.offline,
            started=started,
            tooling=tooling,
        )
    if resolved.task_class in PASSIVE:
        return _compare_passive(session_id, resolved, started, tooling)
    return _compare_circuit_generate(
        session_id,
        body.text or "",
        resolved,
        offline=body.offline,
        started=started,
        tooling=tooling,
    )


def _looks_like_source(text: str) -> bool:
    lowered = text.lower()
    if "(export" in lowered or lowered.strip().startswith("(kicad"):
        return True
    markers = (
        "cube(",
        "sphere(",
        "cylinder(",
        "square(",
        "circle(",
        "difference(",
        "union(",
        "module ",
        "linear_extrude",
        "polygon(",
        "hull(",
        "color(",
    )
    return any(marker in lowered for marker in markers)


def _normalize_request(body: CompareRequest) -> CompareRequest:
    """A sentence in the file box is a prompt, not an OpenSCAD audit."""
    text = (body.text or "").strip()
    artifact = (body.artifact or "").strip()
    if artifact and not _looks_like_source(artifact):
        sentence = text or artifact
        return body.model_copy(update={"text": sentence, "artifact": None, "filename": None})
    if artifact and _looks_like_source(artifact) and not body.filename:
        filename = "board.net" if "(export" in artifact.lower() else "part.scad"
        return body.model_copy(update={"filename": filename})
    return body


def _compare_mechanical_generate(
    session_id: str,
    session_dir: Path,
    spec: FrozenSpec,
    *,
    filament: str,
    offline: bool,
    started: float,
    tooling: dict[str, bool],
) -> CompareResponse:
    is_2d = spec.task_class == "mechanical_2d"
    verify = spec_from_frozen_2d(spec) if is_2d else spec_from_frozen(spec, filament)
    score_fn = score_openscad_2d_text if is_2d else score_openscad_text
    repair_fn = repair_code_2d if is_2d else repair_code
    missing = missing_required(spec.task_class)

    samples: list[tuple[str, dict]] = []
    cost_usd = 0.0
    notice = None
    sentence = spec.evidence.get("sentence", "")
    if missing:
        notice = f"Missing tooling: {', '.join(missing)}. Using offline reference design."
        stub = _offline_raw_stub(spec.task_class, sentence)
        samples.append((stub, score_fn(stub, verify, session_dir / "raw-sample-1")))
    elif offline:
        notice = "Offline demo — left is a first-draft reference; right runs the full harness repair loop."
        stub = _offline_raw_stub(spec.task_class, sentence)
        samples.append((stub, score_fn(stub, verify, session_dir / "raw-sample-1")))
    else:
        prompt = _mechanical_prompt(spec, filament)
        model_error = None
        for index in range(_SAMPLES_ONLINE):
            if not _within_spend():
                model_error = "spend cap reached before a sample finished"
                break
            try:
                text, bill = _complete(prompt, "primary", temperature=_TEMPERATURE)
            except ProposalError as exc:
                model_error = exc.detail
                break
            if bill.get("cost_usd"):
                cost_usd += float(bill["cost_usd"])
            code = strip_fences(text)
            scored = score_fn(code, verify, session_dir / f"raw-sample-{index + 1}")
            samples.append((code, scored))
        if not samples:
            stub = _offline_raw_stub(spec.task_class, sentence)
            notice = f"Model call failed ({model_error or 'no sample'}). Showing a local reference design."
            samples.append((stub, score_fn(stub, verify, session_dir / "fallback")))

    raw_code, _raw_probe = samples[0]
    raw_score = score_fn(raw_code, verify, session_dir / "raw-lane")
    best_code, _best_score = max(samples, key=lambda item: item[1].get("percent", 0))
    if not is_2d and is_articulated_arm(sentence):
        kit = emit_articulated_arm(verify)
        harness_code, harness_score, repaired = repair_code(
            kit,
            verify,
            session_dir / "harness-repair",
            llm_repair=False,
            complete=None,
        )
        if notice is None:
            notice = "Right panel is a standing serial arm built from the spec. Left is the unconstrained first draft."
    else:
        harness_code, harness_score, repaired = repair_fn(
            best_code,
            verify,
            session_dir / "harness-repair",
            llm_repair=not offline and not missing,
            complete=_complete,
        )
    harness_score = score_fn(harness_code, verify, session_dir / "harness-lane")
    edited = harness_code.strip() != raw_code.strip() or (harness_score.get("percent", 0) > raw_score.get("percent", 0))
    if not edited and not offline and raw_score.get("out_of", 0) and raw_score.get("percent") == 100:
        notice = (
            "The model's first try already passed every check, so both panels match."
            + (f" {notice}" if notice else "")
        )
    elif repaired and not notice:
        notice = "Harness repaired the best sample — left shows the model's first try."
    raw_lane = _lane_from_score("raw", raw_code, raw_score, session_id, session_dir)
    harness_lane = _lane_from_score("harness", harness_code, harness_score, session_id, session_dir)
    lift = round((harness_lane.percent or 0) - (raw_lane.percent or 0), 1)
    status = "checked" if harness_lane.status == "checked" else raw_lane.status
    return CompareResponse(
        session_id=session_id,
        status=status,
        mode="generate",
        domain="mechanical",
        task_class=spec.task_class,
        spec_card=spec.model_dump(mode="json"),
        tooling=tooling,
        missing_tools=missing,
        raw=raw_lane,
        harness=harness_lane,
        harness_edited=edited,
        lift_points=lift,
        seconds=time.perf_counter() - started,
        cost_usd=cost_usd or None,
        notice=notice,
    )


def _compare_circuit_generate(
    session_id: str,
    text: str,
    spec: FrozenSpec,
    *,
    offline: bool,
    started: float,
    tooling: dict[str, bool],
) -> CompareResponse:
    if offline:
        return _compare_passive(
            session_id,
            spec,
            started,
            tooling,
            notice="Offline mode — passive circuits only. Enable Luna for buck/LDO/hold-up.",
        )

    from extrude.harness.loop import _client, _prompt_blocks, walk  # noqa: PLC2701
    from extrude.harness.prompt import build_prompt

    cost_usd = 0.0
    raw_lane = CompareLane(label="raw", status="stopped", detail="Waiting for model")
    try:
        blocks = _prompt_blocks(spec)
        prompt = build_prompt(spec, blocks, [], "")
        text_out, usage = _client(prompt, "primary")
        if usage.get("cost_usd"):
            cost_usd = float(usage["cost_usd"])
        design, _identity = parse_proposal(text_out, spec)
        raw_lane = _lane_from_circuit("raw", design, spec)
    except Exception as exc:  # noqa: BLE001
        raw_lane = CompareLane(label="raw", status="stopped", detail=str(exc))

    result = walk(text)
    harness_checks = [
        CheckRow(id="harness_walk", passed=True if result.status == "checked" else None, detail=result.detail),
    ]
    harness_lane = CompareLane(
        label="harness",
        status=result.status,
        percent=100.0 if result.status == "checked" else None,
        passed=1 if result.status == "checked" else 0,
        out_of=1 if result.status == "checked" else 0,
        checks=harness_checks,
        netlist=result.netlist,
        detail=result.detail,
    )
    lift = (round(harness_lane.percent - raw_lane.percent, 1)
            if harness_lane.percent is not None and raw_lane.percent is not None else None)
    return CompareResponse(
        session_id=session_id,
        status=result.status,
        mode="generate",
        domain="electrical",
        task_class=spec.task_class,
        spec_card=spec.model_dump(mode="json"),
        tooling=tooling,
        raw=raw_lane,
        harness=harness_lane,
        lift_points=lift,
        seconds=time.perf_counter() - started,
        cost_usd=cost_usd or None,
    )


def _compare_passive(
    session_id: str,
    spec: FrozenSpec,
    started: float,
    tooling: dict[str, bool],
    notice: str | None = None,
) -> CompareResponse:
    built = build_passive(spec)
    design = built[0] if isinstance(built, tuple) else built
    deck = built[1] if isinstance(built, tuple) and len(built) > 1 else None
    lane = _lane_from_circuit("raw", design, spec, fallback_output=deck)
    harness = lane.model_copy(update={"label": "harness"})
    return CompareResponse(
        session_id=session_id,
        status=lane.status,
        mode="generate",
        domain="electrical",
        task_class=spec.task_class,
        spec_card=spec.model_dump(mode="json"),
        tooling=tooling,
        raw=lane,
        harness=harness,
        lift_points=0.0,
        seconds=time.perf_counter() - started,
        notice=notice,
    )


def _compare_audit(
    session_id: str,
    body: CompareRequest,
    *,
    kind: str,
    started: float,
    tooling: dict[str, bool],
) -> CompareResponse:
    artifact = body.artifact or ""
    if kind == "openscad":
        design = parse_openscad(artifact)
        report = run_mechanical(design, body.filament)
        raw_checks = [
            CheckRow(id=item.feature, passed=False if item.severity == "block" else None, detail=item.detail)
            for item in report.measurements
        ]
        if not raw_checks:
            raw_checks = [CheckRow(id="parsed", passed=None, detail="Parsed; no design verification ran")]
        verified = [item for item in raw_checks if item.passed is not None]
        passed = sum(item.passed is True for item in verified)
        raw_lane = CompareLane(
            label="raw",
            status="stopped" if report.blocking else "unverified",
            percent=round(100 * passed / len(verified), 1) if verified else None,
            passed=passed,
            out_of=len(verified),
            checks=raw_checks,
            code=artifact,
            detail=report.blocking[0] if report.blocking else None,
        )
        fixed = repair_openscad(artifact, body.filament, prompt=body.text or body.filename or "")
        harness_checks = [CheckRow(id="repair", passed=None, detail="No independent design verification ran")]
        for violation in fixed.violations:
            harness_checks.append(
                CheckRow(
                    id=str(violation.get("rule_id") or "repair"),
                    passed=False if fixed.status != "checked" else None,
                    detail=str(violation.get("recommended_action") or violation),
                )
            )
        harness_verified = [item for item in harness_checks if item.passed is not None]
        harness_passed = sum(item.passed is True for item in harness_verified)
        harness_lane = CompareLane(
            label="harness",
            status="unverified" if fixed.status == "checked" and not harness_verified else fixed.status,
            percent=round(100 * harness_passed / len(harness_verified), 1) if harness_verified else None,
            passed=harness_passed,
            out_of=len(harness_verified),
            checks=harness_checks,
            code=fixed.code,
            detail=fixed.detail,
            misses=[{"check_id": v.get("rule_id"), "detail": v.get("recommended_action")}
                    for v in fixed.violations if fixed.status != "checked"],
        )
        lift = (round(harness_lane.percent - raw_lane.percent, 1)
                if harness_lane.percent is not None and raw_lane.percent is not None else None)
        return CompareResponse(
            session_id=session_id,
            status=harness_lane.status,
            mode="audit",
            domain="mechanical",
            task_class="mechanical_3d",
            tooling=tooling,
            raw=raw_lane,
            harness=harness_lane,
            lift_points=lift,
            seconds=time.perf_counter() - started,
        )

    if kind == "netlist":
        parsed = parse_kicad_netlist(artifact)
        report = run_electrical(parsed)
        has_wiring = bool(parsed.parts and parsed.pins)
        verdict = False if report.blocking else (True if has_wiring else None)
        detail = "; ".join(report.blocking) or (
            "No blocking electrical preflight finding" if has_wiring else "No component wiring to verify"
        )
        checks = [CheckRow(id="electrical_preflight", passed=verdict, detail=detail)]
        checks.extend(CheckRow(id=item, passed=None, detail=item) for item in report.warnings)
        passed = sum(item.passed is True for item in checks)
        lane = CompareLane(
            label="raw",
            status="unverified" if verdict is None else ("checked" if verdict else "stopped"),
            percent=100.0 * verdict if verdict is not None else None,
            passed=passed,
            out_of=int(verdict is not None),
            checks=checks,
            netlist=artifact,
            detail=report.blocking[0] if report.blocking else None,
        )
        return CompareResponse(
            session_id=session_id,
            status=lane.status,
            mode="audit",
            domain="electrical",
            task_class="circuit",
            tooling=tooling,
            raw=lane,
            harness=lane.model_copy(update={"label": "harness"}),
            lift_points=0.0 if lane.percent is not None else None,
            seconds=time.perf_counter() - started,
        )

    return _empty_response(
        session_id,
        "needs_info",
        "audit",
        kind,
        kind,
        question="Paste OpenSCAD or a KiCad netlist to audit.",
        started=started,
        tooling=tooling,
    )


def _lane_from_score(
    label: str,
    code: str,
    score: dict,
    session_id: str,
    session_dir: Path,
) -> CompareLane:
    checks = score.get("checks") or {}
    rows = [CheckRow(id=key, passed=bool(value)) for key, value in checks.items()]
    render = score.get("render") or {}
    preview, svg = _publish_preview(session_dir, label, render)
    misses = score.get("misses") or []
    for miss in misses:
        check_id = miss.get("check_id")
        if not check_id:
            continue
        for row in rows:
            if row.id == check_id:
                row.detail = miss.get("detail")
    compiles = checks.get("compiles", True)
    status = "checked" if compiles and not misses else "stopped"
    return CompareLane(
        label=label,
        status=status,
        percent=score.get("percent"),
        passed=score.get("passed", 0),
        out_of=score.get("out_of", 0),
        checks=rows,
        misses=misses,
        code=code,
        preview_url=preview,
        svg_url=svg,
        detail=score.get("detail") or (misses[0].get("detail") if misses else None),
    )


def _lane_from_circuit(
    label: str,
    design,
    spec: FrozenSpec,
    *,
    fallback_output: str | None = None,
) -> CompareLane:  # noqa: ANN001
    report = preflight(design)
    values = derive(design, spec)
    rows: list[CheckRow] = [CheckRow(id="preflight", passed=not report.blocking)]
    rows.extend(CheckRow(id=item, passed=False, detail=item) for item in report.blocking)
    for finding in values.findings:
        rows.append(CheckRow(id=finding.code, passed=False if finding.severity == "fail" else None, detail=finding.detail))
    verified = [row for row in rows if row.passed is not None]
    passed = sum(row.passed is True for row in verified)
    try:
        netlist = emit_netlist(design, values)
    except Exception:
        netlist = fallback_output
    if not netlist:
        netlist = fallback_output
    return CompareLane(
        label=label,
        status="checked" if all(row.passed for row in verified) else "stopped",
        percent=round(100 * passed / len(verified), 1),
        passed=passed,
        out_of=len(verified),
        checks=rows,
        netlist=netlist,
        detail=report.blocking[0] if report.blocking else None,
    )


def _publish_preview(session_dir: Path, label: str, render: dict) -> tuple[str | None, str | None]:
    session_dir.mkdir(parents=True, exist_ok=True)
    png_url = svg_url = None
    png_src = render.get("png")
    if png_src:
        src = Path(str(png_src))
        if src.is_file():
            dest = session_dir / f"{label}-preview.png"
            shutil.copy2(src, dest)
            png_url = f"/artifacts/{session_dir.name}/{label}-preview.png"
    svg_src = render.get("svg")
    if svg_src:
        src = Path(str(svg_src))
        if src.is_file():
            dest = session_dir / f"{label}-preview.svg"
            shutil.copy2(src, dest)
            svg_url = f"/artifacts/{session_dir.name}/{label}-preview.svg"
    return png_url, svg_url


def _mechanical_prompt(spec: FrozenSpec, filament: str) -> str:
    from extrude.spec import SpecCard

    if spec.task_class == "mechanical_2d":
        card = SpecCard(
            sentence=spec.evidence.get("sentence", ""),
            domain="mechanical_2d",
            material=spec.labels.get("material"),
            plate_width_mm=spec.values_si.get("plate_width_mm"),
            plate_height_mm=spec.values_si.get("plate_height_mm"),
            plate_diameter_mm=spec.values_si.get("plate_diameter_mm"),
            hole=spec.labels.get("hole"),
            hole_count=int(spec.values_si.get("hole_count", 0)),
            hole_min_mm=spec.values_si.get("hole_min_mm"),
            hole_max_mm=spec.values_si.get("hole_max_mm"),
        )
        return card.prompt() + _openscad_suffix_2d()
    card = SpecCard(
        sentence=spec.evidence.get("sentence", ""),
        domain=spec.task_class,
        material=spec.labels.get("material") or filament.upper(),
        insert=spec.labels.get("insert"),
        insert_count=int(spec.values_si.get("insert_count", 0)),
        insert_min_mm=spec.values_si.get("insert_min_mm"),
        insert_max_mm=spec.values_si.get("insert_max_mm"),
        min_wall_mm=spec.values_si.get("min_wall_mm"),
    )
    return card.prompt() + _openscad_suffix_3d()


def _offline_raw_stub(task_class: str, sentence: str) -> str:
    """Reference first-draft designs with deliberate spec misses for harness lift."""
    lowered = sentence.lower()
    if task_class == "mechanical_2d":
        if "80" in lowered and "60" in lowered:
            return (
                "$fn = 48;\n"
                "plate_w = 80;\n"
                "plate_h = 60;\n"
                "inset = 10;\n"
                "difference() {\n"
                "    square([plate_w, plate_h]);\n"
                "    for (xy = [[inset, inset], [plate_w - inset, inset], "
                "[inset, plate_h - inset], [plate_w - inset, plate_h - inset]])\n"
                "        translate(xy) circle(d = 2.5);\n"
                "}\n"
            )
        return "square([30, 30]);"
    arm_path = _EVAL / "arm_benchmark" / "off.scad"
    if ("arm" in lowered or "gripper" in lowered or "robot" in lowered) and arm_path.is_file():
        return arm_path.read_text(encoding="utf-8")
    if "cube" in lowered or "box" in lowered:
        return "cube([20, 20, 20]);"
    if "sphere" in lowered:
        return "sphere(12);"
    return "cube([15, 15, 15]);"


def _empty_response(
    session_id: str,
    status: str,
    mode: str,
    domain: str,
    task_class: str,
    *,
    question: str | None,
    started: float,
    tooling: dict[str, bool],
) -> CompareResponse:
    empty = CompareLane(label="raw", status=status, detail=question)
    return CompareResponse(
        session_id=session_id,
        status=status,
        mode=mode,
        domain=domain,
        task_class=task_class,
        question=question,
        tooling=tooling,
        raw=empty,
        harness=empty.model_copy(update={"label": "harness"}),
        seconds=time.perf_counter() - started,
    )
