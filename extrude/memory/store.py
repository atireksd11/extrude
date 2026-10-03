"""Three notebooks. Only a confirmed design miss can block a part."""

import math

from extrude.memory.models import AttributionEvent, ElectricalIdentity, NegativeConstraint, PrimaryCause

_design: list[NegativeConstraint] = []
_request: list[AttributionEvent] = []
_tool: list[AttributionEvent] = []
_aliases: dict[str, ElectricalIdentity] = {}


def reset() -> None:
    _design.clear()
    _request.clear()
    _tool.clear()
    _aliases.clear()


def remember_alias(orderable: str, identity: ElectricalIdentity) -> None:
    _aliases[orderable.strip()] = identity


def identity_for(orderable: str) -> ElectricalIdentity | None:
    return _aliases.get(orderable.strip())


def record(event: AttributionEvent) -> None:
    cause = effective_cause(event)
    if cause is PrimaryCause.model_design:
        identity = _identity_of(event)
        if identity is None:
            return
        _design.append(
            NegativeConstraint(
                identity=identity,
                check_id=event.check_id,
                checker_version=event.checker_version,
                v_fail=event.v_fail,
                i_fail=event.i_fail,
                measured=event.measured,
                limit=event.limit,
                spec_hash=event.spec_hash,
            )
        )
        return
    filed = event.model_copy(update={"cause": cause})
    if cause in {PrimaryCause.spec_gap, PrimaryCause.spec_conflict}:
        _request.append(filed)
        return
    _tool.append(filed)


def effective_cause(event: AttributionEvent) -> PrimaryCause:
    if not event.spec_confirmed:
        return PrimaryCause.spec_gap
    return event.cause


def design_tries_used(previous: int, event: AttributionEvent) -> int:
    if effective_cause(event) is PrimaryCause.model_design and _identity_of(event) is not None:
        return previous + 1
    return previous


def matching_blocks(
    identity: ElectricalIdentity,
    check_id: str,
    checker_version: str,
    spec_hash: str,
    v_new: float | None = None,
    i_new: float | None = None,
) -> list[NegativeConstraint]:
    found = [
        row
        for row in _design
        if row.check_id == check_id
        and row.checker_version == checker_version
        and row.spec_hash == spec_hash
        and _same_identity(row.identity, identity)
        and _severe_enough(row, v_new, i_new)
    ]
    found.sort(key=lambda row: row.measured, reverse=True)
    return found[:8]


def request_rows() -> list[AttributionEvent]:
    return list(_request)


def tool_rows() -> list[AttributionEvent]:
    return list(_tool)


def design_rows() -> list[NegativeConstraint]:
    return list(_design)


def from_simulator_log(log: str, spec_hash: str) -> AttributionEvent:
    return AttributionEvent(cause=PrimaryCause.tooling, spec_hash=spec_hash, detail=log)


def _identity_of(event: AttributionEvent) -> ElectricalIdentity | None:
    if event.orderable:
        known = _aliases.get(event.orderable.strip())
        if known is not None:
            return known
        if event.identity is None:
            return None
    return event.identity


def _same_identity(left: ElectricalIdentity, right: ElectricalIdentity) -> bool:
    return (
        left.manufacturer.strip().upper() == right.manufacturer.strip().upper()
        and left.dielectric.strip().upper() == right.dielectric.strip().upper()
        and left.case.strip().upper() == right.case.strip().upper()
        and math.isclose(left.capacitance, right.capacitance, rel_tol=1e-9, abs_tol=0)
        and math.isclose(left.voltage_rating, right.voltage_rating, rel_tol=1e-9, abs_tol=0)
    )


def _severe_enough(row: NegativeConstraint, v_new: float | None, i_new: float | None) -> bool:
    if row.check_id == "overcurrent":
        return row.i_fail is not None and i_new is not None and i_new >= row.i_fail
    if row.v_fail is None or v_new is None:
        return False
    return v_new >= 0.9 * row.v_fail
