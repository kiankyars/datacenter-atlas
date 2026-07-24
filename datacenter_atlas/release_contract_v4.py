"""Publication contract v4 layered on the frozen v3 release implementation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .release import build_release_documents as build_legacy_release_documents


PUBLICATION_CONTRACT_VERSION = 4


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_release_documents_v4(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    recorded_at: str,
    readme: str | None = None,
) -> dict[str, str]:
    """Build v4 without changing the byte-frozen v1-v3 implementation.

    Contract v4 deliberately inherits v3's role-safe CSV columns and nonadditive
    capacity summary. Its publication changes are an explicit manifest marker
    and generated-README contract, scope, and lifecycle-freshness wording.
    Non-empty caller-supplied README text remains verbatim, as it does in legacy
    releases. An empty string follows the legacy generated-README behavior.
    """
    legacy_readme = readme if readme else None
    documents = build_legacy_release_documents(
        connection,
        as_of=as_of,
        recorded_at=recorded_at,
        readme=legacy_readme,
        publication_contract_version=3,
    )

    if legacy_readme is None:
        legacy_readme = documents["README.md"]
        if legacy_readme.count("contract v3") != 2:
            raise RuntimeError("legacy v3 README contract text changed")
        current_view = "in the current release view."
        pipeline_view = (
            "`construction_pipeline.csv` is an entity-level active/pre-construction "
            "view with"
        )
        lifecycle_anchor = "distinct lifecycle evidence/source observations. "
        if (
            legacy_readme.count(current_view) != 1
            or legacy_readme.count(pipeline_view) != 1
            or legacy_readme.count(lifecycle_anchor) != 1
        ):
            raise RuntimeError("legacy v3 README lifecycle text changed")
        documents["README.md"] = (
            legacy_readme.replace("contract v3", "contract v4")
            .replace(current_view, "in this source-scoped release.")
            .replace(
                pipeline_view,
                "`construction_pipeline.csv` is an entity-level latest-recorded "
                "pipeline-status view with",
            )
            .replace(
                lifecycle_anchor,
                lifecycle_anchor
                + "A row's lifecycle is source-scoped as of its `status_as_of` value; "
                "inclusion does not confirm that the status persisted to the release date, "
                "and the project may since have opened, stalled, changed, or been cancelled. ",
            )
        )

    manifest: dict[str, Any] = json.loads(documents["manifest.json"])
    readme_text = documents["README.md"]
    manifest["files"]["README.md"] = {
        "bytes": len(readme_text.encode("utf-8")),
        "sha256": _sha256(readme_text),
    }
    manifest["publication_contract_version"] = PUBLICATION_CONTRACT_VERSION
    documents["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    return documents
