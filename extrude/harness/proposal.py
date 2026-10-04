"""Read a proposal and refuse one that edits the frozen card."""

import json

from extrude.intake.models import FrozenSpec
from extrude.ir.models import CircuitIR, Part, Pin
from extrude.memory.models import ElectricalIdentity


class ProposalError(Exception):
    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def parse_proposal(text: str, spec: FrozenSpec) -> tuple[CircuitIR, ElectricalIdentity | None]:
    raw = _json_object(text)
    if not isinstance(raw, dict):
        raise ProposalError("tool", "the proposal was not a JSON object")
    if raw.get("spec_hash") != spec.spec_hash:
        raise ProposalError("design", "the proposal changed the frozen card")
    limits = raw.get("limits")
    if not isinstance(limits, dict):
        raise ProposalError("design", "the proposal omitted the frozen limits")
    for key, value in spec.values_si.items():
        got = limits.get(key)
        if isinstance(got, (int, float)) and isinstance(value, (int, float)):
            if float(got) != float(value):
                raise ProposalError("design", "the proposal changed a limit")
        elif got != value:
            raise ProposalError("design", "the proposal changed a limit")
    if "i_load" in spec.values_si:
        load = raw.get("i_load")
        if load is None or load == 0 or load != spec.values_si["i_load"]:
            raise ProposalError("design", "the proposal dropped the load")
    try:
        design = CircuitIR(
            spec_hash=spec.spec_hash,
            parts=[Part(**part) for part in raw.get("parts", [])],
            pins=[Pin(**pin) for pin in raw.get("pins", [])],
            tied_nets=raw.get("tied_nets", []),
            f_sw=raw.get("f_sw"),
        )
    except Exception as exc:
        raise ProposalError("tool", f"the proposal did not fit the design file: {exc}") from exc
    identity = None
    if isinstance(raw.get("identity"), dict):
        try:
            identity = ElectricalIdentity(**raw["identity"])
        except Exception as exc:
            raise ProposalError("tool", f"the part identity was unreadable: {exc}") from exc
    return design, identity


def _json_object(text: str) -> object:
    body = text.strip()
    if body.startswith("```"):
        lines = [line for line in body.splitlines() if not line.strip().startswith("```")]
        body = "\n".join(lines)
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end < start:
        raise ProposalError("tool", "the proposal was not JSON")
    try:
        return json.loads(body[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProposalError("tool", "the proposal was not JSON") from exc
