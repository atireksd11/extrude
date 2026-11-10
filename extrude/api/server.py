"""One design request. An open card does not call the model."""

import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from extrude.api.security import SecurityMiddleware, hosted
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from extrude.coverage.api import render
from extrude.harness import bind_constraints, run
from extrude.harness.envfile import load_env
from extrude.intake import resolve
from extrude.intake.models import FrozenSpec, NeedsInfo
from extrude.api.compare import CompareRequest, CompareResponse, run_compare
from extrude.api.github import router as github_router
from extrude.copilot.api import CopilotRequest, CopilotResponse, handle
from extrude.tools import load_manifest, tool_available
from extrude.copilot.budget import clear_inflight
from extrude.memory.db import database_path, insert_telemetry
from extrude.memory.rag import remember_run, retrieve
from extrude.project_map import (
    add_pin_rule, advance_demo_project, create_demo_project, create_project,
    delete_pin_rule, list_projects, preview_project_file, project_handoff, review_finding, scan_project,
)
from extrude.runtime import data_dir

_ROOT = Path(__file__).resolve().parents[2]
if not hosted() and os.environ.get("EXTRUDE_LOAD_ENV") != "0":
    load_env(_ROOT / ".env")
_openscad = Path(r"C:\Program Files\OpenSCAD\openscad.exe")
if not os.environ.get("OPENSCAD_PATH", "").strip() and _openscad.is_file():
    os.environ["OPENSCAD_PATH"] = str(_openscad)

app = FastAPI(debug=False, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityMiddleware)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": "Invalid request."}, status_code=422)

app.include_router(github_router)
_STATIC = Path(__file__).resolve().parent / "static"
_PAGE = _STATIC / "index.html"
_PROJECT_PAGE = _STATIC / "projects.html"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(_PAGE, headers={"Cache-Control": "no-store"})


@app.get("/projects")
def projects_page() -> FileResponse:
    return FileResponse(_PROJECT_PAGE, headers={"Cache-Control": "no-store"})


@app.get("/projects/github")
def github_page() -> FileResponse:
    return FileResponse(_STATIC / "github.html", headers={"Cache-Control": "no-store"})


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=1024)
    onshape_url: str | None = Field(default=None, max_length=2048)


@app.get("/v1/projects")
def project_list() -> list[dict]:
    return list_projects()


@app.post("/v1/projects")
def project_create(body: ProjectRequest) -> dict:
    try:
        return create_project(body.name, body.path, body.onshape_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/projects/demo")
def project_demo() -> dict:
    try:
        return create_demo_project()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PinRuleRequest(BaseModel):
    firmware_file: str = Field(min_length=1, max_length=1024)
    firmware_symbol: str = Field(min_length=1, max_length=1024)
    netlist_file: str = Field(min_length=1, max_length=1024)
    schematic_net: str = Field(min_length=1, max_length=1024)
    mcu_ref: str = Field(min_length=1, max_length=1024)


@app.post("/v1/projects/{project_id}/pin-rules")
def project_pin_rule_add(project_id: int, body: PinRuleRequest) -> dict:
    try:
        return add_pin_rule(project_id, body.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/v1/projects/{project_id}/pin-rules/{rule_id}")
def project_pin_rule_delete(project_id: int, rule_id: int) -> dict:
    try:
        return delete_pin_rule(project_id, rule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pin rule not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class FindingReviewRequest(BaseModel):
    outcome: str = Field(default="reviewed", max_length=32)
    note: str = Field(default="", max_length=4000)
    target_file: str | None = Field(default=None, max_length=1024)


@app.post("/v1/projects/{project_id}/findings/{finding_id}/review")
def project_finding_review(project_id: int, finding_id: int,
                           body: FindingReviewRequest | None = None) -> dict:
    try:
        request = body or FindingReviewRequest()
        return review_finding(project_id, finding_id, request.outcome, request.note, request.target_file)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Finding not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/projects/{project_id}/preview")
def project_file_preview(project_id: int, path: str) -> dict:
    try:
        return preview_project_file(project_id, path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/projects/{project_id}/demo-change")
def project_demo_change(project_id: int) -> dict:
    try:
        return advance_demo_project(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/projects/{project_id}/scan")
def project_scan(project_id: int) -> dict:
    try:
        return scan_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/projects/{project_id}/handoff.md")
def project_handoff_download(project_id: int) -> PlainTextResponse:
    try:
        content = project_handoff(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlainTextResponse(content, media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=extrude-handoff.md"})


@app.get("/artifacts/{run_id}/{path:path}")
def artifact(run_id: str, path: str) -> FileResponse:
    root = (data_dir() / "generated").resolve()
    run_root = (root / run_id).resolve()
    if not run_root.is_relative_to(root) or run_root == root or "/" in run_id or "\\" in run_id:
        raise HTTPException(status_code=404, detail="artifact not found")
    target = (run_root / path).resolve()
    if not target.is_relative_to(run_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(target, headers={"Content-Disposition": "attachment",
                                        "Content-Security-Policy": "sandbox; default-src 'none'"})


class DesignRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    mode: str = Field(default="interactive", pattern="^interactive$")


class DesignResponse(BaseModel):
    status: str
    detail: str | None = None
    question: str | None = None
    card: dict | None = None
    notice: str | None = None
    netlist: str | None = None
    attempts: int = 0
    cost_usd: float | None = None
    seconds: float
    constraints: list[dict] = Field(default_factory=list)


@app.get("/v1/status")
def status() -> dict:
    manifest = load_manifest()
    tools = {name: tool_available(name) for name in manifest["tools"]}
    return {
        "ok": True,
        "tools": tools,
        "model_configured": bool(os.environ.get("EXTRUDE_MODEL_KEY", "").strip() or os.environ.get("OPENAI_API_KEY", "").strip()),
        "model": os.environ.get("EXTRUDE_MODEL", "").strip() or None,
        "domains": ["mechanical_3d", "mechanical_2d", "circuit"],
    }


@app.post("/v1/compare", response_model=CompareResponse)
def compare(body: CompareRequest) -> CompareResponse:
    return run_compare(body)


@app.post("/v1/copilot", response_model=CopilotResponse)
def copilot(body: CopilotRequest) -> CopilotResponse:
    return handle(body)


@app.post("/v1/design", response_model=DesignResponse)
def design(body: DesignRequest) -> DesignResponse:
    started = time.perf_counter()
    resolved = resolve(body.prompt)
    if isinstance(resolved, NeedsInfo):
        seconds = time.perf_counter() - started
        _log(body.prompt, "needs_info", 0, None, seconds)
        return DesignResponse(
            status="needs_info",
            detail=resolved.question,
            question=resolved.question,
            notice=render(None, []),
            seconds=seconds,
        )
    constraints = _constraints(resolved, body.prompt)
    bind_constraints(constraints if database_path() is not None else None)
    try:
        result = run(body.prompt)
        if database_path() is not None and isinstance(resolved, FrozenSpec):
            remember_run(resolved, body.prompt)
    finally:
        bind_constraints(None)
    seconds = time.perf_counter() - started
    _log(body.prompt, result.status, result.attempts, result.cost_usd, seconds)
    return DesignResponse(
        status=result.status,
        detail=result.detail,
        card=resolved.model_dump(mode="json"),
        notice=result.notice,
        netlist=result.netlist if result.status == "checked" else None,
        attempts=result.attempts,
        cost_usd=result.cost_usd,
        seconds=seconds,
        constraints=[
            {"check_id": row.check_id, "spec_hash": row.spec_hash} for row in constraints
        ],
    )


def _constraints(spec: FrozenSpec, prompt: str) -> list:
    if database_path() is None:
        return []
    return retrieve(spec, prompt)


def _log(prompt: str, status: str, attempts: int, cost_usd: float | None, seconds: float) -> None:
    insert_telemetry(
        model=os.environ.get("EXTRUDE_MODEL", "").strip(),
        prompt=prompt,
        status=status,
        attempts=attempts,
        cost_usd=cost_usd,
        seconds=seconds,
        harness_on=True,
    )
    if database_path() is not None:
        clear_inflight()
