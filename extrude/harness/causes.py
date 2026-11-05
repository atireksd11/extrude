"""Three-way miss attribution before memory writes."""

from extrude.memory.db import insert_prompt_note, insert_telemetry, insert_violation
from extrude.memory.models import PrimaryCause


def classify_miss(
    *,
    check_id: str,
    spec_on_card: bool,
    tool_failed: bool,
) -> PrimaryCause:
    if tool_failed:
        return PrimaryCause.tooling
    if not spec_on_card:
        return PrimaryCause.spec_gap
    return PrimaryCause.model_design


def effective_cause(cause: PrimaryCause, spec_confirmed: bool) -> PrimaryCause:
    if not spec_confirmed and cause is PrimaryCause.model_design:
        return PrimaryCause.spec_gap
    return cause


def store_miss(
    *,
    cause: PrimaryCause,
    prompt: str,
    check_id: str,
    detail: str,
    feature_ref: str,
    measured: float,
    limit: float,
    spec_hash: str,
    domain: str = "mechanical",
    artifact_kind: str = "openscad",
    filament: str | None = None,
    printer_profile: str | None = None,
) -> None:
    if cause is PrimaryCause.spec_gap:
        insert_prompt_note(prompt=prompt, check_id=check_id, detail=detail)
        return
    if cause is PrimaryCause.tooling:
        insert_telemetry(
            model="",
            prompt=prompt,
            status="tooling",
            attempts=0,
            cost_usd=None,
            seconds=0,
            harness_on=True,
        )
        return
    if cause is not PrimaryCause.model_design:
        return
    insert_violation(
        domain=domain,
        artifact_kind=artifact_kind,
        spec_hash=spec_hash,
        prompt=prompt,
        check_id=check_id,
        detail=detail,
        feature_ref=feature_ref,
        filament=filament,
        printer_profile=printer_profile,
        measured=measured,
        limit=limit,
        error_trace_json='{"cause": "model_design"}',
        checker_version="2026-10-04",
    )
