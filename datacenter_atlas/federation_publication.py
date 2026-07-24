"""Fail-closed publication guard for staged federation definitions and bundles."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping

from . import federated_release as legacy
from . import federated_release_v3 as federation


def _utc_timestamp(value: str) -> datetime:
    canonical = legacy._timestamp(
        value, "federation generated_at", require_canonical_utc=True
    )
    return datetime.fromisoformat(canonical.replace("Z", "+00:00"))


def _definition_generated_at(path: Path) -> datetime:
    raw = legacy._regular_bytes(path, "staged federation definition")
    document = legacy._json_object(raw, "staged federation definition")
    if raw != legacy._canonical_json(document):
        raise federation.FederatedReleaseError(
            "staged federation definition is not canonical JSON"
        )
    if set(document) != {"children", "generated_at", "schema_version"}:
        raise federation.FederatedReleaseError(
            "staged federation definition schema is invalid"
        )
    return _utc_timestamp(document["generated_at"])


def validate_prepublication_boundary(
    staged_definition: str | Path,
    final_definition: str | Path,
    final_bundle: str | Path,
    *,
    staged_bundle: str | Path | None = None,
    wall_clock: datetime | None = None,
) -> datetime:
    """Require hidden staging and a live generation time before publication."""

    staged_definition_path = Path(staged_definition)
    final_definition_path = Path(final_definition)
    final_bundle_path = Path(final_bundle)
    generated_at = _definition_generated_at(staged_definition_path)
    now = wall_clock or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise federation.FederatedReleaseError("publication wall clock lacks timezone")
    now = now.astimezone(timezone.utc)

    definition_exposed = final_definition_path.exists() or final_definition_path.is_symlink()
    bundle_exposed = final_bundle_path.exists() or final_bundle_path.is_symlink()
    if now < generated_at and definition_exposed:
        raise federation.FederatedReleaseError(
            "final federation definition was exposed before generated_at"
        )
    if now < generated_at and bundle_exposed:
        raise federation.FederatedReleaseError(
            "final federation bundle was exposed before generated_at"
        )
    if definition_exposed or bundle_exposed:
        raise federation.FederatedReleaseError(
            "federation final path collision; refusing publication"
        )
    if now < generated_at:
        raise federation.FederatedReleaseError(
            "federation generated_at is not yet live"
        )

    stage_paths = [staged_definition_path]
    if staged_bundle is not None:
        staged_bundle_path = Path(staged_bundle)
        federation.validate_federated_release_index(staged_bundle_path)
        stage_paths.append(staged_bundle_path)
    for stage_path in stage_paths:
        stat_result = stage_path.stat()
        birth = datetime.fromtimestamp(
            getattr(stat_result, "st_birthtime", stat_result.st_ctime), timezone.utc
        )
        modified = datetime.fromtimestamp(stat_result.st_mtime, timezone.utc)
        if max(birth, modified) > generated_at:
            raise federation.FederatedReleaseError(
                "federation stage post-dates generated_at"
            )
    return generated_at


def publish_staged_federation(
    staged_definition: str | Path,
    staged_bundle: str | Path,
    final_definition: str | Path,
    final_bundle: str | Path,
    *,
    child_release_paths: Mapping[str, str | Path],
    wall_clock: datetime | None = None,
) -> Mapping[str, object]:
    """Atomically no-replace promote both frozen stages after preflight."""

    staged_definition_path = Path(staged_definition)
    staged_bundle_path = Path(staged_bundle)
    final_definition_path = Path(final_definition)
    final_bundle_path = Path(final_bundle)
    validate_prepublication_boundary(
        staged_definition_path,
        final_definition_path,
        final_bundle_path,
        staged_bundle=staged_bundle_path,
        wall_clock=wall_clock,
    )

    manifest = json.loads(
        (staged_bundle_path / federation.MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    definition_checkpoint = manifest["definition"]
    definition_raw = staged_definition_path.read_bytes()
    if (
        final_definition_path.name != definition_checkpoint["file"]
        or len(definition_raw) != definition_checkpoint["bytes"]
        or hashlib.sha256(definition_raw).hexdigest()
        != definition_checkpoint["sha256"]
    ):
        raise federation.FederatedReleaseError(
            "staged definition differs from the staged bundle checkpoint"
        )

    federation._promote_noreplace(staged_definition_path, final_definition_path)
    federation._promote_noreplace(staged_bundle_path, final_bundle_path)
    validated = federation.validate_federated_release_index(
        final_bundle_path, child_release_paths=child_release_paths
    )
    if final_definition_path.read_bytes() != definition_raw:
        raise federation.FederatedReleaseError(
            "published federation definition differs from its stage"
        )
    return validated


__all__ = [
    "publish_staged_federation",
    "validate_prepublication_boundary",
]
