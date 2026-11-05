"""One mechanical repair loop. A checker fail is a number, not a paragraph."""

import hashlib
import json
import re

from pydantic import BaseModel, Field

from extrude.checks.models import ToleranceReport
from extrude.harness.registry import run_mechanical
from extrude.ir.mechanical import MechanicalIR
from extrude.memory.db import insert_violation
from extrude.parse.openscad import cylinder_spans, parse_openscad

_TRIES = 4


class FixResult(BaseModel):
    status: str
    code: str
    attempts: int
    violations: list[dict] = Field(default_factory=list)
    locked: list[dict] = Field(default_factory=list)
    detail: str | None = None


def repair_openscad(text: str, filament: str, prompt: str = "") -> FixResult:
    current = text
    seen: list[dict] = []
    locked: list[dict] = []
    plastic = filament.strip().upper()
    for attempt in range(1, _TRIES + 1):
        design = parse_openscad(current)
        dropped = [item for item in design.warnings if item.startswith("unparsed_")]
        if dropped:
            return FixResult(
                status="stopped",
                code=current,
                attempts=attempt,
                violations=[{"rule_id": item, "subsystem": item} for item in dropped],
                locked=locked,
                detail=dropped[0],
            )
        report = run_mechanical(design, plastic)
        if not report.blocking:
            return FixResult(
                status="checked",
                code=current,
                attempts=attempt,
                violations=seen,
                locked=locked or _passed(design, report),
            )
        payload = _payload(design, report, plastic, current)
        seen.extend(payload["MUST_FIX"][:1])
        locked = payload["DO_NOT_BREAK"]
        _remember(text, prompt, plastic, {**payload, "MUST_FIX": payload["MUST_FIX"][:1]})
        patched = _patch(current, report, plastic)
        if not locks_held(current, patched):
            return FixResult(
                status="stopped",
                code=current,
                attempts=attempt,
                violations=seen,
                locked=locked,
                detail="the repair deleted a locked feature",
            )
        if patched == current:
            return FixResult(
                status="stopped",
                code=current,
                attempts=attempt,
                violations=seen,
                locked=locked,
                detail=report.blocking[0],
            )
        current = patched
    design = parse_openscad(current)
    report = run_mechanical(design, plastic)
    return FixResult(
        status="checked" if not report.blocking else "stopped",
        code=current,
        attempts=_TRIES,
        violations=seen,
        locked=locked,
        detail=None if not report.blocking else report.blocking[0],
    )


def render_locks(code: str, facts: dict | None = None) -> list[dict]:
    measured = facts or _facts_for_code(code)
    if measured is not None:
        locks = []
        if measured.get("color_count", len(measured.get("colors", []))) >= 1:
            locks.append(
                {
                    "feature": "colors",
                    "status": "PASS",
                    "measured": measured.get("color_count", len(measured.get("colors", []))),
                }
            )
        if measured.get("links", 0) >= 1:
            locks.append({"feature": "link_shapes", "status": "PASS", "measured": measured["links"]})
        if measured.get("bends", 0) >= 1:
            locks.append({"feature": "joint_angles", "status": "PASS", "measured": measured["bends"]})
        if measured.get("holes"):
            locks.append({"feature": "pedestal_geometry", "status": "PASS", "measured": len(measured["holes"])})
        return locks
    locks = []
    if "color(" in code:
        locks.append({"feature": "colors", "status": "PASS"})
    if "rotate(" in code:
        locks.append({"feature": "joint_angles", "status": "PASS"})
    if "hull(" in code:
        locks.append({"feature": "link_shapes", "status": "PASS"})
    if "difference(" in code:
        locks.append({"feature": "pedestal_geometry", "status": "PASS"})
    return locks


def locks_held(
    before: str,
    after: str,
    before_facts: dict | None = None,
    after_facts: dict | None = None,
) -> bool:
    bf = before_facts or _facts_for_code(before)
    af = after_facts or _facts_for_code(after)
    if bf is not None and af is not None:
        return locks_held_facts(bf, af, render_locks(before, bf))
    after_features = {item["feature"] for item in render_locks(after)}
    return all(item["feature"] in after_features for item in render_locks(before))


def locks_held_facts(before: dict, after: dict, locks: list[dict], tolerance: float = 0.05) -> bool:
    for lock in locks:
        feature = lock["feature"]
        if feature == "colors":
            if after.get("color_count", len(after.get("colors", []))) < before.get(
                "color_count", len(before.get("colors", []))
            ):
                return False
        elif feature == "link_shapes":
            if after.get("links", 0) < before.get("links", 0):
                return False
            if not _held_numeric(before.get("links", 0), after.get("links", 0), lock.get("measured"), tolerance):
                return False
        elif feature == "joint_angles":
            if after.get("bends", 0) < before.get("bends", 0):
                return False
            if not _held_numeric(before.get("bends", 0), after.get("bends", 0), lock.get("measured"), tolerance):
                return False
        elif feature == "pedestal_geometry":
            if len(after.get("holes", [])) < len(before.get("holes", [])):
                return False
            if lock.get("measured") is not None and len(after.get("holes", [])) < int(lock["measured"]):
                return False
        elif feature == "joint_wall":
            before_thick = before.get("min_thickness")
            after_thick = after.get("min_thickness")
            if before_thick is not None and after_thick is not None and after_thick + tolerance < before_thick:
                return False
    return True


def _held_numeric(before: float, after: float, locked: float | None, tolerance: float) -> bool:
    if locked is None:
        return True
    return after + tolerance >= before


def _facts_for_code(code: str) -> dict | None:
    try:
        from extrude.verify.solid import geometric_facts

        return geometric_facts(code)
    except Exception:
        return None


def _payload(design: MechanicalIR, report: ToleranceReport, filament: str, code: str) -> dict:
    fixes = []
    failed: set[str] = set()
    for item in report.measurements:
        if item.severity != "block":
            continue
        if fixes:
            break
        target = _target_for(design, item.feature, filament) if item.check_id.startswith("hole_") else item.limit_mm
        fixes.append(_fix(item.check_id, item.feature, item.measured_mm, item.limit_mm, filament, target))
        failed.add(f"{item.check_id}:{item.feature}")
    for rule in report.blocking:
        if fixes:
            break
        if rule in failed or any(rule == f"{item.check_id}:{item.feature}" for item in report.measurements):
            continue
        fixes.append(_fix(rule, rule, 0, 0, filament, None))
        break
    return {
        "verification_status": "FAILED",
        "MUST_FIX": fixes[:1],
        "DO_NOT_BREAK": _passed(design, report) + render_locks(code),
    }


def _fix(rule_id: str, feature: str, measured: float, limit: float, filament: str, target: float | None) -> dict:
    action = f"{rule_id} on {feature}: measured {measured:g}, limit {limit:g}."
    if target is not None and rule_id.startswith("hole_"):
        action = f"Set {feature} from {measured:g} mm to {target:g} mm for {filament}."
    elif rule_id == "wall_below_min":
        action = f"Set wall {feature} from {measured:g} mm to at least {limit:g} mm."
    return {
        "rule_id": rule_id,
        "subsystem": feature,
        "measured_mm": measured,
        "required_mm": limit,
        "target_mm": target,
        "filament": filament,
        "recommended_action": action,
    }


def _passed(design: MechanicalIR, report: ToleranceReport) -> list[dict]:
    failed = {item.feature for item in report.measurements if item.severity == "block"}
    failed.update(code.split(":", 1)[-1] for code in report.blocking)
    locked = []
    for hole in design.holes:
        if not hole.intended_insert or hole.intended_insert == "none" or hole.name in failed:
            continue
        locked.append(
            {
                "requirement_id": "hole_diameter",
                "feature": hole.name,
                "status": "PASS",
                "measured_mm": hole.diameter_mm,
            }
        )
    for wall in design.walls:
        if wall.name in failed:
            continue
        locked.append(
            {
                "requirement_id": "wall_thickness",
                "feature": wall.name,
                "status": "PASS",
                "measured_mm": wall.thickness_mm,
            }
        )
    return locked


def _remember(source: str, prompt: str, filament: str, payload: dict) -> None:
    label = prompt.strip() or source.strip()[:120] or "openscad"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    for item in payload["MUST_FIX"]:
        insert_violation(
            domain="mechanical",
            artifact_kind="openscad",
            spec_hash=digest,
            prompt=label,
            check_id=item["rule_id"],
            detail=item["recommended_action"],
            feature_ref=item["subsystem"],
            filament=filament,
            printer_profile=None,
            measured=float(item["measured_mm"]),
            limit=float(item["required_mm"]),
            error_trace_json=json.dumps(item),
            checker_version="2026-10-04",
        )


def _patch(text: str, report: ToleranceReport, filament: str) -> str:
    design = parse_openscad(text)
    spans = cylinder_spans(text)
    edits: list[tuple[int, int, str]] = []
    for item in report.measurements:
        if item.severity != "block":
            continue
        if item.check_id.startswith("hole_"):
            index = _hole_index(item.feature)
            target = _target_for(design, item.feature, filament)
            if index is None or target is None or index >= len(spans):
                continue
            start, end, _diameter = spans[index]
            rewritten = _rewrite_call(text[start:end], target)
            if rewritten != text[start:end]:
                edits.append((start, end, rewritten))
        elif item.check_id == "wall_below_min":
            found = _wall_span(text, item.feature)
            if found is None:
                continue
            start, end, rewritten = found
            edits.append((start, end, rewritten.replace_thickness(item.limit_mm)))
    for start, end, rewritten in sorted(edits, key=lambda item: item[0], reverse=True):
        text = text[:start] + rewritten + text[end:]
    return text


def _target_for(design: MechanicalIR, feature: str, filament: str) -> float | None:
    from extrude.checks.tolerance import _TABLE

    hole = next((item for item in design.holes if item.name == feature), None)
    if hole is None or not hole.intended_insert or hole.intended_insert == "none":
        return None
    row = _TABLE["inserts"].get(hole.intended_insert)
    if row is None or filament not in row:
        return None
    return float(row[filament])


def _hole_index(feature: str) -> int | None:
    match = re.fullmatch(r"hole_(\d+)", feature)
    if match is None:
        return None
    index = int(match.group(1)) - 1
    return index if index >= 0 else None


def _rewrite_call(call: str, target: float) -> str:
    named_d = re.search(r"(d\s*=\s*)([0-9.]+)", call, re.IGNORECASE)
    if named_d:
        return _swap(call, named_d, target)
    named_r = re.search(r"(r\s*=\s*)([0-9.]+)", call, re.IGNORECASE)
    if named_r:
        return _swap(call, named_r, target / 2)
    numbers = list(re.finditer(r"[0-9.]+", call))
    if len(numbers) < 2:
        return call
    second = numbers[1]
    return call[: second.start()] + _num(target / 2) + call[second.end() :]


def _swap(call: str, match: re.Match[str], value: float) -> str:
    return call[: match.start(2)] + _num(value) + call[match.end(2) :]


def _num(value: float) -> str:
    return f"{value:g}"


class _WallEdit:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def replace_thickness(self, limit: float) -> str:
        return f"{self.prefix}{_num(limit)}"


def _wall_span(text: str, name: str) -> tuple[int, int, _WallEdit] | None:
    match = re.search(rf"//\s*extrude-wall\s+{re.escape(name)}\s+", text, re.IGNORECASE)
    if match is None:
        return None
    number = re.match(r"[0-9.]+", text[match.end() :])
    if number is None:
        return None
    return match.start(), match.end() + number.end(), _WallEdit(text[match.start() : match.end()])
