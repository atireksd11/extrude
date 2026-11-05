"""Local notebooks on disk. The process lists stay the test path."""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from extrude.memory.models import ElectricalIdentity, MechanicalIdentity, NegativeConstraint, ViolationRecord


def database_path() -> Path | None:
    raw = os.environ.get("EXTRUDE_MEMORY_DB", "").strip()
    if not raw:
        return None
    return Path(raw)


def insert_constraint(
    *,
    task_class: str,
    spec_hash: str,
    prompt: str,
    check_id: str,
    detail: str,
    voltage: float | None,
    identity: ElectricalIdentity,
    checker_version: str,
    v_fail: float | None,
    i_fail: float | None,
    measured: float,
    limit: float,
) -> None:
    path = database_path()
    if path is None:
        return
    with _connect(path) as db:
        existing = db.execute(
            """
            SELECT 1 FROM constraints
            WHERE spec_hash = ? AND check_id = ? AND manufacturer = ? AND capacitance = ?
            """,
            (spec_hash, check_id, identity.manufacturer, identity.capacitance),
        ).fetchone()
        if existing is not None:
            return
        db.execute(
            """
            INSERT INTO constraints (
                task_class, spec_hash, prompt, check_id, detail, voltage,
                manufacturer, capacitance, dielectric, case_size, voltage_rating,
                checker_version, v_fail, i_fail, measured, limit_value, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_class,
                spec_hash,
                prompt,
                check_id,
                detail,
                voltage,
                identity.manufacturer,
                identity.capacitance,
                identity.dielectric,
                identity.case,
                identity.voltage_rating,
                checker_version,
                v_fail,
                i_fail,
                measured,
                limit,
                _now(),
            ),
        )


def load_constraints() -> list[dict]:
    path = database_path()
    if path is None or not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute("SELECT * FROM constraints ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def insert_prompt_note(*, prompt: str, check_id: str, detail: str) -> None:
    path = database_path()
    if path is None:
        return
    with _connect(path) as db:
        db.execute(
            """
            INSERT INTO prompt_notes (prompt, check_id, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (prompt, check_id, detail, _now()),
        )


def load_prompt_notes() -> list[dict]:
    path = database_path()
    if path is None or not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute("SELECT * FROM prompt_notes ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def insert_telemetry(
    *,
    model: str,
    prompt: str,
    status: str,
    attempts: int,
    cost_usd: float | None,
    seconds: float,
    harness_on: bool,
) -> None:
    path = database_path()
    if path is None:
        return
    with _connect(path) as db:
        db.execute(
            """
            INSERT INTO telemetry (
                model, prompt, status, attempts, cost_usd, seconds, harness_on, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (model, prompt, status, attempts, cost_usd, seconds, int(harness_on), _now()),
        )


def load_telemetry() -> list[dict]:
    path = database_path()
    if path is None or not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute("SELECT * FROM telemetry ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def insert_violation(
    *,
    domain: str,
    artifact_kind: str,
    spec_hash: str,
    prompt: str,
    check_id: str,
    detail: str,
    feature_ref: str,
    filament: str | None,
    printer_profile: str | None,
    measured: float,
    limit: float,
    error_trace_json: str,
    checker_version: str,
) -> bool:
    path = database_path()
    if path is None:
        return False
    record = _violation_record(
        domain=domain,
        artifact_kind=artifact_kind,
        spec_hash=spec_hash,
        prompt=prompt,
        check_id=check_id,
        detail=detail,
        feature_ref=feature_ref,
        filament=filament,
        printer_profile=printer_profile,
        measured=measured,
        limit=limit,
        error_trace_json=error_trace_json,
        checker_version=checker_version,
    )
    with _connect(path) as db:
        existing = db.execute(
            """
            SELECT 1 FROM violations
            WHERE domain = ? AND spec_hash = ? AND check_id = ? AND feature_ref = ?
              AND IFNULL(filament, '') = ?
            """,
            (
                record.domain,
                record.spec_hash,
                record.check_id,
                record.identity.feature_ref,
                record.identity.filament or "",
            ),
        ).fetchone()
        if existing is not None:
            return False
        db.execute(
            """
            INSERT INTO violations (
                domain, artifact_kind, spec_hash, prompt, check_id, detail, feature_ref,
                filament, printer_profile, measured, limit_value, error_trace_json,
                checker_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.domain,
                record.identity.artifact_kind,
                record.spec_hash,
                record.prompt,
                record.check_id,
                record.detail,
                record.identity.feature_ref,
                record.identity.filament,
                record.identity.printer_profile,
                record.measured,
                record.limit,
                record.error_trace_json,
                record.checker_version,
                _now(),
            ),
        )
    return True


def load_violations() -> list[dict]:
    path = database_path()
    if path is None or not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute("SELECT * FROM violations ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def violation_from_row(row: dict) -> ViolationRecord:
    return ViolationRecord(
        domain=row["domain"],
        identity=MechanicalIdentity(
            feature_ref=row["feature_ref"],
            artifact_kind=row["artifact_kind"],
            filament=row["filament"],
            printer_profile=row["printer_profile"],
        ),
        spec_hash=row["spec_hash"],
        prompt=row["prompt"],
        check_id=row["check_id"],
        detail=row["detail"],
        measured=row["measured"],
        limit=row["limit_value"],
        error_trace_json=row["error_trace_json"],
        checker_version=row["checker_version"],
    )


def _violation_record(**fields) -> ViolationRecord:
    return ViolationRecord(
        domain=fields["domain"],
        identity=MechanicalIdentity(
            feature_ref=fields["feature_ref"],
            artifact_kind=fields["artifact_kind"],
            filament=fields["filament"],
            printer_profile=fields["printer_profile"],
        ),
        spec_hash=fields["spec_hash"],
        prompt=fields["prompt"],
        check_id=fields["check_id"],
        detail=fields["detail"],
        measured=fields["measured"],
        limit=fields["limit"],
        error_trace_json=fields["error_trace_json"],
        checker_version=fields["checker_version"],
    )


def constraint_from_row(row: dict) -> NegativeConstraint:
    return NegativeConstraint(
        identity=ElectricalIdentity(
            manufacturer=row["manufacturer"],
            capacitance=row["capacitance"],
            dielectric=row["dielectric"],
            case=row["case_size"],
            voltage_rating=row["voltage_rating"],
        ),
        check_id=row["check_id"],
        checker_version=row["checker_version"],
        v_fail=row["v_fail"],
        i_fail=row["i_fail"],
        measured=row["measured"],
        limit=row["limit_value"],
        spec_hash=row["spec_hash"],
    )


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS constraints (
            id INTEGER PRIMARY KEY,
            task_class TEXT NOT NULL,
            spec_hash TEXT NOT NULL,
            prompt TEXT NOT NULL,
            check_id TEXT NOT NULL,
            detail TEXT NOT NULL,
            voltage REAL,
            manufacturer TEXT NOT NULL,
            capacitance REAL NOT NULL,
            dielectric TEXT NOT NULL,
            case_size TEXT NOT NULL,
            voltage_rating REAL NOT NULL,
            checker_version TEXT NOT NULL,
            v_fail REAL,
            i_fail REAL,
            measured REAL NOT NULL,
            limit_value REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY,
            domain TEXT NOT NULL,
            artifact_kind TEXT NOT NULL,
            spec_hash TEXT NOT NULL,
            prompt TEXT NOT NULL,
            check_id TEXT NOT NULL,
            detail TEXT NOT NULL,
            feature_ref TEXT NOT NULL,
            filament TEXT,
            printer_profile TEXT,
            measured REAL NOT NULL,
            limit_value REAL NOT NULL,
            error_trace_json TEXT NOT NULL,
            checker_version TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS prompt_notes (
            id INTEGER PRIMARY KEY,
            prompt TEXT NOT NULL,
            check_id TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY,
            model TEXT,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL,
            cost_usd REAL,
            seconds REAL NOT NULL,
            harness_on INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    return db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
