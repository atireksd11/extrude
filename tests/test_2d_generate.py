"""2D mechanical generate path gates."""

from pathlib import Path

import pytest

from extrude.harness import clear_client, run, set_client

_PLATE = (
    "Laser-cut an 80x60 mm acrylic mounting plate with 4 M3 clearance holes inset 10 mm from each corner."
)
_FIXTURE = Path(__file__).resolve().parents[1] / "eval" / "mechanical_2d" / "tasks" / "mount_plate" / "off.scad"


def test_2d_route_does_not_return_phase_stub():
    result = run(_PLATE)
    assert result.detail != "2D plate generate ships in Phase 3"


def _fake_score(code: str, verify, out_dir):  # noqa: ANN001
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = out_dir / "preview.svg"
    png = out_dir / "preview.png"
    svg.write_text('<svg width="80mm" height="60mm" viewBox="0 -60 80 60"><path d="M0,0"/></svg>', encoding="utf-8")
    png.write_bytes(b"png")
    return {
        "percent": 85.0,
        "checks": {"compiles": True, "hole_diameter": False},
        "misses": [
            {
                "check_id": "hole_diameter",
                "measured_mm": 2.5,
                "detail": "hole too small",
            }
        ],
        "facts": {"holes": [{"cx": 10, "cy": 10, "diameter": 2.5}]},
        "render": {"svg": str(svg), "png": str(png)},
    }


def test_2d_generate_returns_code_with_mock_client(monkeypatch, tmp_path):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setattr("extrude.harness.mechanical.score_openscad_2d_text", _fake_score)
    monkeypatch.setattr("extrude.harness.mechanical.missing_required", lambda _domain: [])
    code = _FIXTURE.read_text(encoding="utf-8")

    def fake_client(_prompt, _seat, **kwargs):  # noqa: ARG001
        return code, {"cost_usd": 0.0}

    set_client(fake_client)
    try:
        result = run(_PLATE)
    finally:
        clear_client()
    assert result.code is not None
    assert "buck" not in (result.detail or "").lower()
