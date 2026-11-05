"""Top constraints for this card. Keyed retrieval — no token overlap."""

import re

from extrude.intake.models import FrozenSpec
from extrude.memory.db import (
    constraint_from_row,
    insert_constraint,
    load_constraints,
    load_violations,
    violation_from_row,
)
from extrude.memory.models import NegativeConstraint, ViolationRecord
from extrude.memory.store import design_rows

_VOLTS = ("v_rail", "v_bus", "v_supply", "vin", "vout")


def retrieve_violations(domain: str, prompt: str, spec_hash: str) -> list[ViolationRecord]:
    wanted = domain.strip().lower()
    ranked: list[tuple[float, int, ViolationRecord]] = []
    for row in load_violations():
        if str(row["domain"]).lower() != wanted:
            continue
        if row["spec_hash"] != spec_hash:
            continue
        overlap = _overlap(prompt, f"{row['prompt']} {row['detail']} {row['check_id']}")
        ranked.append((overlap, int(row["id"]), violation_from_row(row)))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:3]]


def retrieve(spec: FrozenSpec, prompt: str) -> list[NegativeConstraint]:
    ranked: list[tuple[int, NegativeConstraint]] = []
    for row in load_constraints():
        if row["spec_hash"] != spec.spec_hash:
            continue
        if row["task_class"] != spec.task_class:
            continue
        ranked.append((int(row["id"]), constraint_from_row(row)))
    ranked.sort(key=lambda item: item[0])
    return [item[1] for item in ranked[:3]]


def remember_run(spec: FrozenSpec, prompt: str) -> None:
    voltage = _voltage(spec.values_si)
    for row in design_rows():
        if row.spec_hash != spec.spec_hash:
            continue
        insert_constraint(
            task_class=spec.task_class,
            spec_hash=row.spec_hash,
            prompt=prompt,
            check_id=row.check_id,
            detail=(
                f"{row.identity.manufacturer} {row.identity.dielectric} {row.identity.case} "
                f"failed {row.check_id}: measured {row.measured}, limit {row.limit}"
            ),
            voltage=row.v_fail if row.v_fail is not None else voltage,
            identity=row.identity,
            checker_version=row.checker_version,
            v_fail=row.v_fail,
            i_fail=row.i_fail,
            measured=row.measured,
            limit=row.limit,
        )


def _voltage(values: dict[str, float]) -> float | None:
    for key in _VOLTS:
        if key in values:
            return float(values[key])
    return None


def _overlap(left: str, right: str) -> float:
    shared = _tokens(left) & _tokens(right)
    return float(len(shared))


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}
