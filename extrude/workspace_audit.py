"""Run and persist local, revision-pinned workspace audits."""

import hashlib
import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from extrude import github_history as git, pcb_review, schematic_review, kicad_audit
from extrude.runtime import data_dir
from extrude.workspace import domain
from extrude import kicad_snapshot
from extrude import workspace_settings, workspace_checks, workspace_cad

SCHEMA_VERSION = 4
RULE_VERSION = 6
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="atlas-audit")
_LOCK = threading.RLock()
_ACTIVE: dict[tuple[Path, str], str] = {}
_MAX_PENDING = 4
_MAX_BOARDS = 12
_MAX_FILES = 1000
_MAX_BOARD_FINDINGS = 200
_IN_PROGRESS = {"queued", "running"}


class AuditBusy(RuntimeError):
    """The local audit worker cannot accept another run yet."""


class Evidence(BaseModel):
    id: str
    repo_id: str
    sha: str
    path: str
    locator: str


class RelatedFile(BaseModel):
    sha: str
    path: str
    basis: Literal["same_name", "configured", "confirmed", "possible"]


class Relationship(BaseModel):
    id: str
    kind: Literal["schematic_pcb_component", "bom_schematic_component", "firmware_hardware_pin", "board_enclosure"]
    status: Literal["confirmed", "configured", "possible", "unverified"]
    source: Evidence
    target: Evidence
    summary: str
    metadata: dict = Field(default_factory=dict)


class Finding(BaseModel):
    rule_id: str
    domain: str
    status: Literal["observed", "verified", "suggestion", "unverified"]
    severity: Literal["info", "warning", "error"]
    summary: str
    lifecycle: Literal["new", "existing", "resolved", "present_at_head"] | None = None
    consequence: str | None = None
    next_action: str | None = None
    before: object = None
    after: object = None
    evidence: list[Evidence] = Field(default_factory=list)
    related: list[RelatedFile] = Field(default_factory=list)


class Coverage(BaseModel):
    path: str
    domain: str
    check: str
    tool: str
    outcome: Literal["ran", "unsupported", "unavailable", "failed"]
    detail: str


class Audit(BaseModel):
    id: str
    repo_id: str
    base_sha: str | None
    head_sha: str
    schema_version: int = SCHEMA_VERSION
    rule_version: int = RULE_VERSION
    tool_versions: dict[str, str]
    config_hash: str
    project_settings: dict = Field(default_factory=dict)
    state: Literal["queued", "running", "complete", "partial", "failed"] = "queued"
    detail: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    coverage: list[Coverage] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


def _key(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _audit_dir() -> Path:
    return data_dir() / "workspace-audits"


def _descriptor(repo_id: str, revision: str, base: str | None) -> Audit:
    head, base = git.comparison_revisions(repo_id, revision, base)
    tools = {"kicad-tools": version("kicad-tools"), "kicad-cli": kicad_audit.tool_version(),
             "trimesh": version("trimesh"),
             "pcb-inspector": version("pcb-inspector"),
             "git": git._text(git._git(git._repository(repo_id), "--version")).strip()}
    tools.update(workspace_cad.tool_versions())
    project_settings = workspace_settings.get(repo_id).model_dump(mode="json")
    settings = _key([project_settings, _MAX_FILES, _MAX_BOARDS, _MAX_BOARD_FINDINGS,
                     kicad_audit.TIMEOUT, kicad_audit.MAX_PROJECTS, kicad_audit.MAX_FINDINGS,
                     kicad_audit.AUDIT_SECONDS, kicad_audit.executable(),
                     kicad_snapshot.MAX_FILES, kicad_snapshot.MAX_TREE,
                     kicad_snapshot.MAX_FILE_BYTES, kicad_snapshot.MAX_BYTES,
                     workspace_checks.limit_profile()])
    audit_id = _key([repo_id, head, base, SCHEMA_VERSION, RULE_VERSION, tools, settings])
    return Audit(id=audit_id, repo_id=repo_id, head_sha=head, base_sha=base,
                 tool_versions=tools, config_hash=settings, project_settings=project_settings)


def _save(path: Path, audit: Audit) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pending.write_text(audit.model_dump_json(), encoding="utf-8")
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _read(path: Path) -> Audit:
    try:
        return Audit.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise KeyError(path.stem) from None


def get(repo_id: str, audit_id: str) -> Audit:
    if not re.fullmatch(r"[0-9a-f]{64}", audit_id):
        raise KeyError(audit_id)
    directory = _audit_dir()
    with _LOCK:
        audit = _read(directory / f"{audit_id}.json")
        if audit.repo_id != repo_id:
            raise KeyError(audit_id)
        if audit.state in _IN_PROGRESS and _ACTIVE.get((directory, repo_id)) != audit_id:
            audit.state = "failed"
            audit.detail = "The previous run was interrupted. Run the audit again to retry."
            _save(directory / f"{audit_id}.json", audit)
        return audit


def status(repo_id: str, head: str, base: str | None) -> dict | None:
    candidate = _descriptor(repo_id, head, base)
    try:
        return get(repo_id, candidate.id).model_dump(exclude={"findings", "coverage"})
    except KeyError:
        return None


def start(repo_id: str, revision: str, base: str | None, retry: bool = False) -> Audit:
    audit = _descriptor(repo_id, revision, base)
    directory = _audit_dir()
    active_key = (directory, repo_id)
    path = directory / f"{audit.id}.json"
    with _LOCK:
        try:
            previous = get(repo_id, audit.id)
        except KeyError:
            previous = None
        if previous and (previous.state in _IN_PROGRESS or
                         previous.state == "complete" or (previous.state == "partial" and not retry)):
            return previous
        if active_key in _ACTIVE or len(_ACTIVE) >= _MAX_PENDING:
            raise AuditBusy("An audit is already running. Try again after it finishes.")
        _save(path, audit)
        _ACTIVE[active_key] = audit.id
        try:
            _POOL.submit(_run, active_key, path, audit.model_copy(deep=True))
        except RuntimeError:
            del _ACTIVE[active_key]
            audit.state = "failed"
            audit.detail = "Could not start the audit worker. Run the audit again."
            _save(path, audit)
        return audit


def _run(active_key: tuple[Path, str], path: Path, audit: Audit) -> None:
    try:
        audit.state = "running"
        with _LOCK:
            _save(path, audit)
        _collect(audit)
        audit.state = "partial" if any(row.outcome != "ran" for row in audit.coverage) else "complete"
    except (git.GitHubError, KeyError, ValueError):
        audit.state = "failed"
        audit.detail = "The audit could not read the saved comparison. Sync or select another commit, then retry."
    except Exception:
        audit.state = "failed"
        audit.detail = "The audit stopped unexpectedly. Run the audit again to retry."
    finally:
        with _LOCK:
            try:
                _save(path, audit)
            finally:
                _ACTIVE.pop(active_key, None)


def _collect(audit: Audit) -> None:
    paths = git.changes(audit.repo_id, audit.head_sha, audit.base_sha, limit=_MAX_FILES)
    audit.coverage.append(Coverage(path="", domain="project", check="Git changes", tool="git",
                                   outcome="ran", detail=f"{paths['total']} changed paths."))
    if paths["next_offset"] is not None:
        audit.coverage.append(Coverage(path="", domain="project", check="Audit scope", tool="Atlas",
                                       outcome="unsupported", detail=f"Only the first {_MAX_FILES} changed paths were audited."))
    boards = 0
    for row in paths["files"]:
        path = row["path"]
        area = domain(path, row["kind"])
        old_path = row["previous_path"] or path
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in workspace_checks.ARTIFACT_SUFFIXES:
            continue  # Phase 3 supplies coverage and factual comparisons below.
        if suffix == ".kicad_sch" and PurePosixPath(old_path).suffix.lower() == suffix:
            try:
                _schematic(audit, path, old_path)
            except (git.GitHubError, KeyError, ValueError):
                audit.coverage.append(Coverage(path=path, domain="schematic", check="Placed symbol comparison",
                                              tool="kicad-tools", outcome="failed", detail="Could not read this schematic comparison."))
            continue
        if suffix != ".kicad_pcb" or PurePosixPath(old_path).suffix.lower() != ".kicad_pcb":
            audit.coverage.append(Coverage(path=path, domain=area, check="File analysis", tool="Atlas",
                                           outcome="unsupported", detail="Git change available. This file has no audit adapter yet."))
            continue
        boards += 1
        if boards > _MAX_BOARDS:
            audit.coverage.append(Coverage(path=path, domain=area, check="PCB placement and pad nets",
                                           tool="kicad-tools", outcome="unsupported", detail="PCB audit limit reached."))
            continue
        try:
            _board(audit, path, old_path)
        except (git.GitHubError, KeyError, ValueError):
            audit.coverage.append(Coverage(
                path=path, domain="pcb", check="PCB placement and pad nets", tool="kicad-tools",
                outcome="failed", detail="Could not read this board comparison. Retry or inspect the file.",
            ))
    findings, coverage = kicad_audit.collect(audit.repo_id, audit.head_sha, audit.base_sha)
    audit.findings.extend(Finding.model_validate(row) for row in findings)
    audit.coverage.extend(Coverage.model_validate(row) for row in coverage)
    findings, coverage = workspace_checks.collect(audit.repo_id, audit.head_sha, audit.base_sha,
        workspace_settings.Settings.model_validate(audit.project_settings), paths["files"])
    audit.findings.extend(Finding.model_validate(row) for row in findings)
    audit.coverage.extend(Coverage.model_validate(row) for row in coverage)
    from extrude import design_audit
    findings, coverage = design_audit.collect(audit.repo_id, audit.head_sha)
    audit.findings.extend(Finding.model_validate(row) for row in findings)
    audit.coverage.extend(Coverage.model_validate(row) for row in coverage)
    from extrude import workspace_links
    relationships, coverage = workspace_links.collect(audit)
    audit.relationships = [Relationship.model_validate(row) for row in relationships]
    audit.coverage.extend(Coverage.model_validate(row) for row in coverage)
    workspace_links.attach(audit)


def _schematic(audit: Audit, path: str, old_path: str) -> None:
    data = schematic_review.review(audit.repo_id, audit.head_sha, path, audit.base_sha, old_path,
                                   limit=_MAX_BOARD_FINDINGS)
    complete = data["status"] != "unverified" and data["next_offset"] is None
    audit.coverage.append(Coverage(path=path, domain="schematic", check="Placed symbol comparison",
                                  tool="kicad-tools", outcome="ran" if complete else "failed",
                                  detail=f"{data['total']} changes in references, values, footprints or units. "
                                  + ("Connectivity is checked separately by KiCad." if complete else "Unreadable or truncated comparison; review the input.")))
    for row in data["changes"]:
        locator = f"{row['reference']} unit {row['unit']} · UUID {row['uuid']}"
        evidence = [Evidence(id=_key([audit.repo_id, side["sha"], side["path"], locator])[:24],
                             repo_id=audit.repo_id, sha=side["sha"], path=side["path"], locator=locator)
                    for side in (data["before"], data["after"]) if side["status"] == "read"]
        audit.findings.append(Finding(rule_id="schematic." + row["kind"], domain="schematic",
                                      status="observed", severity="info",
                                      summary=f"{row['reference']}: {row['kind'].replace('_', ' ')}",
                                      before=row["before"], after=row["after"], evidence=evidence))


def _board(audit: Audit, path: str, old_path: str) -> None:
    data = pcb_review.review(audit.repo_id, audit.head_sha, path, audit.base_sha, old_path,
                             limit=_MAX_BOARD_FINDINGS)
    coverage = Coverage(path=path, domain="pcb", check="PCB placement and pad nets", tool="kicad-tools",
                        outcome="ran", detail=f"{data['total']} changes in the supported fields.")
    if data["status"] == "unverified":
        coverage.outcome = "failed"
        coverage.detail = " ".join(side["detail"] for side in (data["before"], data["after"]) if side.get("detail"))
    elif data["next_offset"] is not None:
        coverage.outcome = "unsupported"
        coverage.detail += f" Showing the first {_MAX_BOARD_FINDINGS}."
    audit.coverage.append(coverage)
    related = []
    if data["changes"] and data["after"]["status"] == "read":
        sibling = str(PurePosixPath(path).with_suffix(".kicad_sch"))
        if git.file_exists(audit.repo_id, audit.head_sha, sibling):
            related.append(RelatedFile(sha=audit.head_sha, path=sibling, basis="same_name"))
    for row in data["changes"]:
        locator = row["reference"] + (f" pad {row['pad']}" if "pad" in row else "")
        evidence = [
            Evidence(id=_key([audit.repo_id, side["sha"], side["path"], locator])[:24],
                     repo_id=audit.repo_id, sha=side["sha"], path=side["path"], locator=locator)
            for side in (data["before"], data["after"]) if side["status"] == "read"
        ]
        suggestion = row["kind"] == "pad_disconnected"
        audit.findings.append(Finding(
            rule_id="pcb." + row["kind"], domain="pcb", status="suggestion" if suggestion else "observed",
            severity="warning" if suggestion else "info", summary=f"{locator}: {row['kind'].replace('_', ' ')}",
            before=row["before"], after=row["after"], evidence=evidence, related=related,
        ))
