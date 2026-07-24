"""SQLite connection and migration management."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path


MIGRATION_PATTERN = re.compile(r"^(\d{4})_(.+)\.sql$")


def connect(path: str | Path) -> sqlite3.Connection:
    database_path = Path(path)
    if str(database_path) != ":memory:":
        database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def apply_migrations(connection: sqlite3.Connection) -> list[int]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    applied = {
        row["version"] for row in connection.execute("SELECT version FROM schema_migrations")
    }
    migration_dir = Path(__file__).with_name("migrations")
    installed: list[int] = []
    for path in sorted(migration_dir.glob("*.sql")):
        match = MIGRATION_PATTERN.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in applied:
            continue
        name = match.group(2)
        quoted_name = name.replace("'", "''")
        script = (
            "BEGIN IMMEDIATE;\n"
            + path.read_text(encoding="utf-8")
            + f"\nINSERT INTO schema_migrations(version, name) VALUES ({version}, '{quoted_name}');\n"
            + "COMMIT;\n"
        )
        try:
            connection.executescript(script)
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        installed.append(version)
    return installed


def initialize(path: str | Path) -> tuple[sqlite3.Connection, list[int]]:
    connection = connect(path)
    installed = apply_migrations(connection)
    return connection, installed


def schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
    return int(row["version"])
