"""Small interface shared by file-based source adapters."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImportResult:
    source: str
    examined_elements: int = 0
    imported_elements: int = 0
    skipped_elements: int = 0
    entities_created: int = 0
    evidence_created: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


class SourceAdapter(Protocol):
    """Contract for bounded, explicit file imports; adapters do not fetch implicitly."""

    source_name: str

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
    ) -> ImportResult: ...
