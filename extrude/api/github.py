"""Atlas endpoints for local repository import and inspection."""

from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict

from extrude import github_history as store
from extrude import pcb_review, schematic_review, workspace, workspace_audit
from extrude import workspace_settings, workspace_checks, workspace_cad
from extrude import workspace_explain, workspace_report

router = APIRouter(prefix="/v1/github/repositories")


@contextmanager
def _errors():
    try:
        yield
    except KeyError as exc:
        raise HTTPException(404, "Repository, commit, or file unavailable.") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except store.GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc
    except workspace_audit.AuditBusy as exc:
        raise HTTPException(409, str(exc)) from exc


class RepositoryRequest(BaseModel):
    source: str = Field(min_length=1, max_length=250)


class AuditRequest(BaseModel):
    revision: str
    base: str | None = None
    retry: bool = False


class CadInspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    path: str = Field(min_length=1, max_length=1024)
    include_preview: bool = False


class CadInspectionResponse(BaseModel):
    repo_id: str
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    path: str
    facts: dict
    evidence: list[workspace_audit.Evidence]


@router.post("/{repo_id}/cad/inspect", operation_id="inspect_project_cad")
def inspect_cad(repo_id: str, body: CadInspectionRequest) -> CadInspectionResponse:
    with _errors():
        return CadInspectionResponse.model_validate(workspace_cad.inspect_asset(repo_id, body.revision, body.path, body.include_preview))


@router.get("")
def repositories() -> list[dict]:
    with _errors():
        return store.repositories()


@router.post("")
def connect(body: RepositoryRequest) -> dict:
    with _errors():
        return store.connect(body.source)


@router.post("/{repo_id}/sync")
def sync(repo_id: str) -> dict:
    with _errors():
        return store.sync(repo_id)


@router.get("/{repo_id}/commits")
def commits(repo_id: str, revision: str | None = None, offset: int = Query(0, ge=0),
            limit: int = Query(30, ge=1, le=100)) -> dict:
    with _errors():
        return store.history(repo_id, revision, offset, limit)


@router.get("/{repo_id}/files")
def files(repo_id: str, revision: str, offset: int = Query(0, ge=0),
          limit: int = Query(100, ge=1, le=200)) -> dict:
    with _errors():
        return store.inventory(repo_id, revision, offset, limit)


@router.get("/{repo_id}/changes")
def changes(repo_id: str, revision: str, base: str | None = None, offset: int = Query(0, ge=0),
            limit: int = Query(100, ge=1, le=200)) -> dict:
    with _errors():
        return store.changes(repo_id, revision, base, offset, limit)


@router.get("/{repo_id}/preview")
def preview(repo_id: str, revision: str, path: str = Query(min_length=1, max_length=4096)) -> dict:
    with _errors():
        return store.preview(repo_id, revision, path)


@router.get("/{repo_id}/pcb")
def pcb(repo_id: str, revision: str, path: str = Query(min_length=1, max_length=4096),
        base: str | None = None, previous_path: str | None = Query(None, max_length=4096),
        offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> dict:
    with _errors():
        return pcb_review.review(repo_id, revision, path, base, previous_path, offset, limit)


@router.get("/{repo_id}/workspace")
def get_workspace(repo_id: str, revision: str, base: str | None = None, file_offset: int = Query(0, ge=0),
                  change_offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> dict:
    with _errors():
        result = workspace.view(repo_id, revision, base, file_offset, change_offset, limit)
        result["audit"] = workspace_audit.status(repo_id, result["head_sha"], result["base_sha"])
        return result


@router.get("/{repo_id}/settings")
def get_settings(repo_id: str) -> workspace_settings.Settings:
    with _errors():
        return workspace_settings.get(repo_id)


@router.put("/{repo_id}/settings")
def save_settings(repo_id: str, body: workspace_settings.Settings) -> workspace_settings.Settings:
    with _errors():
        return workspace_settings.save(repo_id, body)


@router.get("/{repo_id}/artifact")
def artifact(repo_id: str, revision: str, path: str = Query(min_length=1, max_length=1024),
             base: str | None = None, previous_path: str | None = None) -> dict:
    with _errors():
        return workspace_checks.review(repo_id, revision, path, base, previous_path)


@router.get("/{repo_id}/schematic")
def schematic(repo_id: str, revision: str, path: str = Query(min_length=1, max_length=4096),
              base: str | None = None, previous_path: str | None = Query(None, max_length=4096),
              offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> dict:
    with _errors():
        return schematic_review.review(repo_id, revision, path, base, previous_path, offset, limit)


@router.post("/{repo_id}/audits", status_code=202)
def start_audit(repo_id: str, body: AuditRequest) -> dict:
    with _errors():
        audit = workspace_audit.start(repo_id, body.revision, body.base, body.retry)
        return audit.model_dump(exclude={"findings", "coverage"})


@router.get("/{repo_id}/audits/{audit_id}")
def get_audit(repo_id: str, audit_id: str) -> dict:
    with _errors():
        audit = workspace_audit.get(repo_id, audit_id)
        return {**audit.model_dump(), "review": workspace_report.review(audit)}


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consent: Literal[True]


@router.get("/{repo_id}/audits/{audit_id}/explain")
def explanation_status(repo_id: str, audit_id: str) -> dict:
    with _errors():
        return workspace_explain.status(workspace_audit.get(repo_id, audit_id))


@router.post("/{repo_id}/audits/{audit_id}/explain", status_code=202)
def explain_audit(repo_id: str, audit_id: str, body: ExplainRequest) -> workspace_explain.Explanation:
    with _errors():
        return workspace_explain.start(workspace_audit.get(repo_id, audit_id), body.consent)
