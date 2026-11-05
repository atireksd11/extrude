"""Upgrade the local project-map database without discarding existing rows."""

import sqlite3

SCHEMA_VERSION = 2

_TABLES = """
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
        onshape_url TEXT, created_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS files (
        project_id INTEGER NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL,
        digest TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0,
        modified_ns INTEGER NOT NULL DEFAULT 0, preview TEXT,
        PRIMARY KEY (project_id, path)
    );
    CREATE TABLE IF NOT EXISTS changes (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, path TEXT NOT NULL,
        kind TEXT NOT NULL, action TEXT NOT NULL, seen_at TEXT NOT NULL, diff TEXT
    );
    CREATE TABLE IF NOT EXISTS findings (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, source TEXT NOT NULL,
        target TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL,
        suggestion TEXT NOT NULL, seen_at TEXT NOT NULL, resolved_at TEXT,
        review_outcome TEXT, review_note TEXT, review_target TEXT
    );
    CREATE TABLE IF NOT EXISTS checks (
        project_id INTEGER NOT NULL, path TEXT NOT NULL, name TEXT NOT NULL,
        status TEXT NOT NULL, detail TEXT NOT NULL, seen_at TEXT NOT NULL,
        PRIMARY KEY (project_id, path, name)
    );
    CREATE TABLE IF NOT EXISTS pin_rules (
        id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
        firmware_file TEXT NOT NULL, firmware_symbol TEXT NOT NULL,
        netlist_file TEXT NOT NULL, schematic_net TEXT NOT NULL,
        mcu_ref TEXT NOT NULL
    );
"""

_COLUMNS = (
    ("projects", "demo", "INTEGER NOT NULL DEFAULT 0"),
    ("files", "size", "INTEGER NOT NULL DEFAULT 0"),
    ("files", "modified_ns", "INTEGER NOT NULL DEFAULT 0"),
    ("files", "preview", "TEXT"),
    ("changes", "diff", "TEXT"),
    ("findings", "resolved_at", "TEXT"),
    ("findings", "review_outcome", "TEXT"),
    ("findings", "review_note", "TEXT"),
    ("findings", "review_target", "TEXT"),
)


def migrate(db: sqlite3.Connection) -> None:
    if db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
        return
    # Take the write lock before re-reading the version. Two requests can
    # open the same unversioned database at the same time.
    db.execute("BEGIN IMMEDIATE")
    try:
        _upgrade(db)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _upgrade(db: sqlite3.Connection) -> None:
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"Project database version {version} is newer than this app")
    if version < 1:
        for statement in _TABLES.split(";"):
            if statement.strip():
                db.execute(statement)
        db.execute("PRAGMA user_version = 1")
    if version < 2:
        for table, column, declaration in _COLUMNS:
            names = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if column not in names:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        db.execute("PRAGMA user_version = 2")
