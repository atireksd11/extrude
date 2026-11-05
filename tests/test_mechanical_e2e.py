"""Product mechanical path with real OpenSCAD scoring."""

from pathlib import Path

from extrude.harness import clear_client, run, set_client

_ARM = (
    "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. "
    "PETG base with 4 M3 inserts. 2mm joint walls."
)
_FIXTURE = Path(__file__).resolve().parents[1] / "eval" / "arm_benchmark" / "off.scad"


def test_real_openscad_emits_preview_and_stl(monkeypatch, tmp_path):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setattr("extrude.harness.mechanical.missing_required", lambda _domain: [])
    monkeypatch.setattr("extrude.harness.mechanical._SAMPLES", 1)
    code = _FIXTURE.read_text(encoding="utf-8")

    def fake_client(_prompt, _seat, **kwargs):  # noqa: ARG001
        return code, {"cost_usd": 0.0}

    set_client(fake_client)
    try:
        result = run(_ARM, filament="PETG")
    finally:
        clear_client()
    assert result.code is not None
    assert result.preview_png is not None
    assert result.stl_path is not None
    assert Path(result.stl_path).is_file()
