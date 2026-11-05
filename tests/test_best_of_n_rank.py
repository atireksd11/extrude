"""Best-of-N ranks by compile plus shape score."""

from pathlib import Path

from extrude.harness import clear_client, run, set_client

_ROOT = Path(__file__).resolve().parents[1] / "eval" / "arm_benchmark"
_FIXTURES = [
    _ROOT / "off.scad",
    "cube([10,10,10]);",
    _ROOT / "on.scad",
    "sphere(5);",
]


def _fake_score(code: str, verify, out_dir):  # noqa: ANN001
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "preview.png"
    stl = out_dir / "part.stl"
    png.write_bytes(b"png")
    stl.write_bytes(b"stl")
    if "rounded_base" in code or "arm_link" in code:
        percent = 85.0
    elif "gripper" in code.lower():
        percent = 75.0
    elif "cube" in code:
        percent = 15.0
    else:
        percent = 5.0
    return {
        "percent": percent,
        "checks": {"compiles": True},
        "misses": [],
        "facts": {"links": 3, "colors": [(1, 0, 0)], "color_count": 1, "bends": 2, "holes": [4.2]},
        "render": {"png": str(png), "stl": str(stl)},
    }


def test_ranker_prefers_the_colored_arm(monkeypatch, tmp_path):
    monkeypatch.setenv("EXTRUDE_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setattr("extrude.harness.mechanical.score_openscad_text", _fake_score)
    monkeypatch.setattr("extrude.harness.mechanical.missing_required", lambda _domain: [])
    calls = {"n": 0}

    def fake_client(_prompt, _seat, **kwargs):  # noqa: ARG001
        code = _FIXTURES[calls["n"] % len(_FIXTURES)]
        calls["n"] += 1
        if isinstance(code, Path):
            code = code.read_text(encoding="utf-8")
        return code, {"cost_usd": 0.0}

    set_client(fake_client)
    try:
        result = run(
            "Build a desktop robotic arm in OpenSCAD with 3 links and a gripper. "
            "PETG base with 4 M3 inserts. 2mm joint walls.",
            filament="PETG",
        )
    finally:
        clear_client()

    assert result.code is not None
    assert "rounded_base" in result.code or "link" in result.code.lower()
    assert result.attempts >= 4
