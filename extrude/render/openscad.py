"""Write an STL, a PNG, and the evaluated CSG. No drive letter is stored."""

import os
import shutil
import subprocess
from contextvars import ContextVar
from pathlib import Path

from pydantic import BaseModel


# Compare previews must not change rendering in other requests or harness runs.
STUDIO_RENDER = ContextVar("studio_render", default=False)


def studio_render_enabled() -> bool:
    return STUDIO_RENDER.get() or os.environ.get("EXTRUDE_STUDIO_RENDER") == "1"


class RenderResult(BaseModel):
    status: str
    detail: str | None = None
    stl: str | None = None
    png: str | None = None
    csg: str | None = None
    svg: str | None = None
    cause: str = "tooling"


def render_source(source: Path, out_dir: Path, stem: str) -> RenderResult:
    exe = _executable()
    if exe is None:
        return RenderResult(status="stopped", detail="openscad was not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    studio = studio_render_enabled()
    stl = out_dir / f"{stem}.stl"
    png = out_dir / f"{stem}.png"
    csg = out_dir / f"{stem}.csg"
    csg_run = _run(exe, source, csg)
    if csg_run is not None:
        return csg_run
    png_extra = (
        [
            "--imgsize=1100,720",
            "--preview",
            "--projection=perspective",
            "--camera=0,0,0,62,0,28,1",
            "--autocenter",
            "--viewall",
        ]
        if studio
        else ["--imgsize=1100,760", "--autocenter", "--viewall"]
    )
    png_run = _run(exe, source, png, extra=png_extra)
    if png_run is not None and not studio:
        return png_run
    if not studio:
        stl_run = _run(exe, source, stl)
        if stl_run is not None:
            return stl_run
        return RenderResult(status="checked", stl=str(stl), png=str(png), csg=str(csg), cause="")
    if png_run is not None:
        return RenderResult(status="checked", png=None, csg=str(csg), detail=png_run.detail, cause="")
    return RenderResult(status="checked", png=str(png), csg=str(csg), cause="")


def render_2d(source: Path, out_dir: Path, stem: str) -> RenderResult:
    exe = _executable()
    if exe is None:
        return RenderResult(status="stopped", detail="openscad was not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = out_dir / f"{stem}.svg"
    png = out_dir / f"{stem}.png"
    svg_run = _run(exe, source, svg)
    if svg_run is not None:
        return svg_run
    png_run = _run(exe, source, png, extra=["--imgsize=1100,760", "--autocenter", "--viewall"])
    if png_run is not None:
        return png_run
    return RenderResult(status="checked", svg=str(svg), png=str(png), cause="")


def _executable() -> str | None:
    chosen = os.environ.get("OPENSCAD_PATH", "").strip()
    if chosen:
        return chosen if Path(chosen).is_file() else None
    return shutil.which("openscad")


def _run(exe: str, source: Path, dest: Path, extra: list[str] | None = None) -> RenderResult | None:
    command = [exe, "-o", str(dest), *(extra or []), str(source)]
    try:
        limit = 25 if studio_render_enabled() else 90
        completed = subprocess.run(command, capture_output=True, text=True, timeout=limit, check=False)
    except subprocess.TimeoutExpired:
        return RenderResult(status="stopped", detail="openscad timed out")
    except OSError as exc:
        return RenderResult(status="stopped", detail=str(exc))
    if completed.returncode != 0 or not dest.is_file():
        tail = (completed.stderr or completed.stdout or "openscad failed").strip().splitlines()
        return RenderResult(status="stopped", detail=tail[-1][:240] if tail else "openscad failed")
    return None
