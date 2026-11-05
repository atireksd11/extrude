"""Mechanical generate routes to the solid verify path."""

from pathlib import Path

from extrude.harness import clear_client, run, set_client

_ARM = (
    "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. "
    "PETG base with 4 M3 inserts. 2mm joint walls."
)
_FIXTURE = Path(__file__).resolve().parents[2] / "eval" / "arm_benchmark" / "off.scad"


def test_mechanical_arm_does_not_return_buck_message():
    result = run(_ARM)
    assert "buck" not in (result.detail or "").lower()
    assert result.detail != "this seat only designs a buck, regulator, or hold-up"


def _fake_score(code: str, verify, out_dir):  # noqa: ANN001
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "preview.png"
    stl = out_dir / "part.stl"
    png.write_bytes(b"png")
    stl.write_bytes(b"stl")
    return {
        "percent": 80.0,
        "checks": {"compiles": True},
        "misses": [],
        "facts": {"links": 3, "colors": [(1, 0, 0)], "color_count": 1, "bends": 2, "holes": [6.4]},
        "render": {"png": str(png), "stl": str(stl)},
    }


def test_mechanical_arm_returns_code_with_mock_client(monkeypatch, tmp_path):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setattr("extrude.harness.mechanical.score_openscad_text", _fake_score)
    monkeypatch.setattr("extrude.harness.mechanical.missing_required", lambda _domain: [])
    code = _FIXTURE.read_text(encoding="utf-8")

    def fake_client(_prompt, _seat, **kwargs):  # noqa: ARG001
        return code, {"cost_usd": 0.0}

    set_client(fake_client)
    try:
        result = run(_ARM, filament="PETG")
    finally:
        clear_client()
    assert result.code is not None
    assert result.detail != "mechanical generate ships in Phase 1"
