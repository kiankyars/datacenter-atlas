"""Dispatch legacy releases and the explicitly manifested v4 contract."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .release import (
    SUPPORTED_PUBLICATION_CONTRACT_VERSIONS as LEGACY_CONTRACT_VERSIONS,
)
from .release import build_release_documents as build_legacy_release_documents
from .release import write_release as write_legacy_release
from .release_contract_v4 import (
    PUBLICATION_CONTRACT_VERSION,
    build_release_documents_v4,
)
from .timestamps import canonical_read_cutoff


SUPPORTED_PUBLICATION_CONTRACT_VERSIONS = frozenset(
    {*LEGACY_CONTRACT_VERSIONS, PUBLICATION_CONTRACT_VERSION}
)


def _validated_publication_contract_version(value: int) -> int:
    if type(value) is not int or value not in SUPPORTED_PUBLICATION_CONTRACT_VERSIONS:
        supported = ", ".join(
            str(version)
            for version in sorted(SUPPORTED_PUBLICATION_CONTRACT_VERSIONS)
        )
        raise ValueError(
            f"publication_contract_version must be one of: {supported}"
        )
    return value


def build_release_documents(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    recorded_at: str,
    readme: str | None = None,
    publication_contract_version: int = 1,
) -> dict[str, str]:
    publication_contract_version = _validated_publication_contract_version(
        publication_contract_version
    )
    recorded_at = canonical_read_cutoff(recorded_at)
    if publication_contract_version == PUBLICATION_CONTRACT_VERSION:
        return build_release_documents_v4(
            connection,
            as_of=as_of,
            recorded_at=recorded_at,
            readme=readme,
        )
    return build_legacy_release_documents(
        connection,
        as_of=as_of,
        recorded_at=recorded_at,
        readme=readme,
        publication_contract_version=publication_contract_version,
    )


def write_release(
    connection: sqlite3.Connection,
    output_dir: str | Path,
    *,
    as_of: str,
    recorded_at: str,
    readme: str | None = None,
    publication_contract_version: int = 1,
) -> dict[str, Any]:
    publication_contract_version = _validated_publication_contract_version(
        publication_contract_version
    )
    recorded_at = canonical_read_cutoff(recorded_at)
    if publication_contract_version != PUBLICATION_CONTRACT_VERSION:
        return write_legacy_release(
            connection,
            output_dir,
            as_of=as_of,
            recorded_at=recorded_at,
            readme=readme,
            publication_contract_version=publication_contract_version,
        )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    documents = build_release_documents(
        connection,
        as_of=as_of,
        recorded_at=recorded_at,
        readme=readme,
        publication_contract_version=publication_contract_version,
    )
    for name, text in documents.items():
        (destination / name).write_text(text, encoding="utf-8")
    manifest = json.loads(documents["manifest.json"])
    return {"output_dir": str(destination.resolve()), **manifest}
