"""Decide generate or audit before any checker runs."""

from pydantic import BaseModel

from extrude.intake.classify import classify
from extrude.parse.sniff import sniff


class RouteDecision(BaseModel):
    mode: str
    artifact_kind: str


_MECHANICAL = {"mechanical_3d", "mechanical_2d"}


def route(*, text: str | None, filename: str | None, content: str | None) -> RouteDecision:
    body = content if content is not None else ""
    if filename or body.strip():
        kind = sniff(filename=filename, content=body or (text or ""))
        if kind == "circuit" and not filename:
            return RouteDecision(mode="generate", artifact_kind="circuit")
        return RouteDecision(mode="audit", artifact_kind=kind)
    sentence = (text or "").strip()
    kind = classify(sentence) if sentence else "unknown"
    if kind == "ambiguous":
        return RouteDecision(mode="generate", artifact_kind="ambiguous")
    if kind in _MECHANICAL:
        return RouteDecision(mode="generate", artifact_kind=kind)
    return RouteDecision(mode="generate", artifact_kind="circuit")
