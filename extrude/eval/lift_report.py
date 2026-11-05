"""Validate harness lift JSON. String rubrics cannot quote as improvement."""

_ALLOWED_VERIFIER_KINDS = frozenset({"solid", "svg", "verifier"})


def validate_lift_report(report: dict) -> list[str]:
    errors: list[str] = []
    if not report.get("quote_as_improvement"):
        return errors
    kind = report.get("verifier_kind")
    if kind not in _ALLOWED_VERIFIER_KINDS:
        errors.append(
            f"quote_as_improvement requires verifier_kind in {_ALLOWED_VERIFIER_KINDS}, got {kind!r}"
        )
    if kind == "string" or report.get("rubric") == "string":
        errors.append("string rubric lift cannot be quoted as improvement")
    lift = report.get("lift_points")
    if lift is not None and lift > 0 and kind is None and "compiles" not in report.get("raw", {}).get("checks", {}):
        errors.append("positive lift without verifier_kind is not allowed")
    return errors


def assert_lift_report_valid(report: dict) -> None:
    errors = validate_lift_report(report)
    if errors:
        raise ValueError("; ".join(errors))
