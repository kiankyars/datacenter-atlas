"""Build and validate the public Verified Construction Core preview.

The preview is intentionally separate from the historical publication-carrier
chain.  It selects only manually reviewed project/site pairs from open-seed
v97 and refuses to describe the small cohort as the final 100-site product.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import UUID

from .repository import stable_id as atlas_stable_id


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RELEASE_ID = "2026-07-22-open-seed-v97"
SOURCE_RELEASE = ROOT / "releases" / SOURCE_RELEASE_ID
GEOMETRY_RELEASES = {
    "global-open-v3": ROOT / "releases" / "2026-07-18-global-open-v3",
}
LEGACY_PREVIEW_V01_DIR = (
    ROOT / "verified_construction_core" / "2026-08-19-preview-v0.1"
)
LEGACY_PREVIEW_V01_MANIFEST_SHA256 = (
    "50c37999d6e14156910cdd0c66fb973c554414dcc29917226746afc15dc673b7"
)
LEGACY_PREVIEW_V02_DIR = (
    ROOT / "verified_construction_core" / "2026-08-20-preview-v0.2"
)
LEGACY_PREVIEW_V02_MANIFEST_SHA256 = (
    "e69b6d0570710dd3ef4802601652852d24047fb19f1e9bf6ebd5dad9ac29ae8d"
)
REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.3-reviewed-sites.json"
)
IMAGERY_REVIEW_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.3-imagery-reviews.json"
)
PROVENANCE_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-v0.3-provenance.json"
)
OVERLAY_DEFINITION = (
    ROOT / "definitions" / "verified-construction-core-reviewed-overlays-v1.json"
)
V03_REVIEW_DEFINITION_SHA256 = (
    "ee56ff41dc6ea59df67de6ab462540c8a3fe3747ca3e1504cb9228481c25c06b"
)
V03_IMAGERY_REVIEW_DEFINITION_SHA256 = (
    "eec896bd0c1b26fe95110ab3023e3d713c9ff4c6965412683b4d5e945ad09d7a"
)
V03_PROVENANCE_DEFINITION_SHA256 = (
    "50c3e82d2a9ae6a759b36344e34556ed527027b5c6397153d051adf61dce6561"
)
V03_OVERLAY_DEFINITION_SHA256 = (
    "57540f73c5cac475bd8e9e64fc5d8eb2188158ef977b477a0c0e8d7158caf1b7"
)
PREVIEW_ID = "2026-08-20-preview-v0.3"
PREVIEW_DIR = ROOT / "verified_construction_core" / PREVIEW_ID
REVIEW_DATE = date(2026, 8, 20)
MAX_STATUS_AGE_DAYS = 90
V03_DELTA_COUNTRY_ISO_A2 = {
    "Chile": "CL",
    "United Kingdom": "GB",
}

PHYSICAL_STATUSES = {
    "civil_works",
    "commissioning",
    "expansion",
    "foundations",
    "mep_electrical",
    "shell",
    "site_preparation",
    "under_construction",
}
AUTHORITATIVE_STATUS_METHODS = {
    "authoritative_construction_start",
    "authoritative_physical_status_update",
    "government_record",
    "physical_observation",
}
POWER_METRICS = {
    "grid_connection_mw",
    "gross_facility_mw",
    "critical_it_mw",
    "generation_nameplate_mw",
}
ENERGY_METRICS = {"annual_energy_mwh"}
EFFICIENCY_METRICS = {"pue"}
METRIC_UNITS = {
    "grid_connection_mw": "MW",
    "gross_facility_mw": "MW",
    "critical_it_mw": "MW",
    "generation_nameplate_mw": "MW",
    "annual_energy_mwh": "MWh/year",
    "pue": "ratio",
}
ESTIMATE_METHODS = {
    "reported",
    "calculated",
    "permit_inference",
    "equipment_inference",
    "imagery_inference",
    "modeled",
    "unknown",
}
CAPACITY_STAGES = {
    "requested",
    "contracted",
    "design",
    "planned",
    "installed",
    "energized",
    "operational",
    "measured",
    "forecast",
    "unknown",
}
FINAL_REQUIREMENTS = {
    "site_count": 100,
    "country_count": 40,
    "non_us_site_count": 50,
    "maximum_single_country_share": 0.40,
    "blind_review_sample_size": 20,
    "blind_review_minimum_agreements": 19,
}
PREVIEW_SOURCE_PIPELINE_ROW_COUNT = 531
PREVIEW_SELECTION_FIRST_FAILURE_COUNTS = {
    "entity_kind_not_project": 49,
    "not_in_reviewed_site_geometry_allowlist": 128,
    "selected": 15,
    "status_not_physical": 12,
    "status_outside_90_day_window": 327,
}
CLEAN_CLONE_REBUILD_REASON = (
    "v97 source payloads remain local-only; the preview is clean-clone validatable "
    "but not clean-clone rebuildable"
)
SEMANTIC_GUARDRAILS = {
    "legacy_construction_verified_changed": False,
    "current_status_inferred": False,
    "imagery_creates_lifecycle_claim": False,
    "campus_geometry_misrepresented_as_project_footprint": False,
    "locality_centroids_accepted": False,
    "model_only_status_accepted": False,
    "unadjudicated_imagery_conflict_resolved": False,
}

PROJECT_FIELDS = (
    "project_id",
    "project_stable_key",
    "site_id",
    "physical_site_stable_key",
    "name",
    "country",
    "country_iso_a2",
    "latitude",
    "longitude",
    "geometry_json",
    "geometry_type",
    "geometry_source_entity_kind",
    "geometry_derivation",
    "geometry_method",
    "geometry_scope_class",
    "geometry_precision_scope",
    "horizontal_uncertainty_metres",
    "horizontal_uncertainty_unknown_reason",
    "geometry_evidence_id",
    "last_observed_physical_status",
    "status_as_of",
    "status_age_days_at_review",
    "status_method",
    "status_evidence_id",
    "verification_posture",
    "independent_imagery_verification",
    "imagery_review_outcome",
    "development_type",
    "development_type_unknown_reason",
    "operating_model",
    "operating_model_unknown_reason",
    "operating_model_evidence_id",
    "workloads_json",
    "workload_unknown_reason",
    "role_claims_json",
    "power_observations_json",
    "power_unknown_reason",
    "annual_energy_observations_json",
    "annual_energy_unknown_reason",
    "efficiency_observations_json",
    "efficiency_unknown_reason",
    "owner",
    "operator",
    "users",
    "tenants",
    "customers",
    "status_source_url",
    "geometry_source_url",
)

SITE_FIELDS = (
    "site_id",
    "physical_site_stable_key",
    "name",
    "country",
    "country_iso_a2",
    "latitude",
    "longitude",
    "geometry_json",
    "geometry_type",
    "geometry_source_entity_kinds_json",
    "geometry_derivations_json",
    "geometry_methods_json",
    "geometry_scope_classes_json",
    "geometry_precision_scopes_json",
    "horizontal_uncertainty_metres",
    "horizontal_uncertainty_unknown_reason",
    "geometry_evidence_ids_json",
    "project_count",
    "project_ids_json",
    "project_stable_keys_json",
    "statuses_json",
    "oldest_status_as_of",
    "newest_status_as_of",
    "verification_posture",
    "independent_imagery_verification",
    "imagery_review_outcomes_json",
)

EVIDENCE_FIELDS = (
    "evidence_id",
    "roles_json",
    "project_ids_json",
    "kind",
    "title",
    "source_url",
    "publisher",
    "source_family",
    "license",
    "attribution",
    "published_at",
    "retrieved_at",
    "content_hash",
)


class VerifiedConstructionCoreError(ValueError):
    """Raised when a source, review decision, or preview violates the contract."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _v03_definition_pins() -> tuple[tuple[str, Path, str], ...]:
    return (
        (
            "review_definition_sha256",
            REVIEW_DEFINITION,
            V03_REVIEW_DEFINITION_SHA256,
        ),
        (
            "imagery_review_definition_sha256",
            IMAGERY_REVIEW_DEFINITION,
            V03_IMAGERY_REVIEW_DEFINITION_SHA256,
        ),
        (
            "provenance_definition_sha256",
            PROVENANCE_DEFINITION,
            V03_PROVENANCE_DEFINITION_SHA256,
        ),
        (
            "overlay_definition_sha256",
            OVERLAY_DEFINITION,
            V03_OVERLAY_DEFINITION_SHA256,
        ),
    )


def _validate_v03_definition_pins() -> None:
    for field, definition, expected_sha256 in _v03_definition_pins():
        if (
            definition.is_symlink()
            or not definition.is_file()
            or _sha256_file(definition) != expected_sha256
        ):
            raise VerifiedConstructionCoreError(
                f"preview {field} source hash differs"
            )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fields})
    return buffer.getvalue().encode("utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerifiedConstructionCoreError(f"cannot read canonical JSON {path}") from error


def _load_csv(
    path: Path, expected_fields: Sequence[str] | None = None
) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if expected_fields is not None and tuple(reader.fieldnames or ()) != tuple(
                expected_fields
            ):
                raise VerifiedConstructionCoreError(
                    f"CSV field order differs: {path}"
                )
            return list(reader)
    except OSError as error:
        raise VerifiedConstructionCoreError(f"cannot read CSV {path}") from error


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise VerifiedConstructionCoreError(f"cannot read JSONL {path}") from error
    if any(not isinstance(row, dict) for row in rows):
        raise VerifiedConstructionCoreError(f"JSONL row differs: {path}")
    return rows


def _calendar_date(value: str, field: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise VerifiedConstructionCoreError(f"{field} must be YYYY-MM-DD") from error
    return parsed


def _stable_id(prefix: str, key: str) -> str:
    return f"{prefix}-{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def _parse_json_field(value: str, field: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise VerifiedConstructionCoreError(f"invalid {field} JSON") from error


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _validate_typed_observation(
    observation: Any, allowed_metrics: set[str]
) -> dict[str, Any]:
    fields = {
        "as_of_date",
        "base",
        "confidence",
        "evidence_id",
        "high",
        "low",
        "method",
        "metric",
        "notes",
        "stage",
        "target_date",
        "unit",
    }
    if not isinstance(observation, dict) or set(observation) != fields:
        raise VerifiedConstructionCoreError("typed-metric observation schema differs")
    metric = observation["metric"]
    if metric not in allowed_metrics or observation["unit"] != METRIC_UNITS[metric]:
        raise VerifiedConstructionCoreError("typed-metric metric/unit differs")
    low = observation["low"]
    base = observation["base"]
    high = observation["high"]
    if not all(_finite_number(value) for value in (low, base, high)):
        raise VerifiedConstructionCoreError("typed-metric interval is not finite")
    if low < 0 or not low <= base <= high or (metric == "pue" and low <= 0):
        raise VerifiedConstructionCoreError("typed-metric interval differs")
    confidence = observation["confidence"]
    if not _finite_number(confidence) or not 0 <= confidence <= 1:
        raise VerifiedConstructionCoreError("typed-metric confidence differs")
    if observation["method"] not in ESTIMATE_METHODS:
        raise VerifiedConstructionCoreError("typed-metric method differs")
    if observation["stage"] not in CAPACITY_STAGES:
        raise VerifiedConstructionCoreError("typed-metric stage differs")
    if not isinstance(observation["evidence_id"], str) or not observation[
        "evidence_id"
    ]:
        raise VerifiedConstructionCoreError("typed-metric evidence id differs")
    if not isinstance(observation["notes"], str):
        raise VerifiedConstructionCoreError("typed-metric notes differ")
    _calendar_date(observation["as_of_date"], "typed-metric as_of_date")
    target_date = observation["target_date"]
    if target_date is not None:
        _calendar_date(target_date, "typed-metric target_date")
    return observation


SOURCE_WORKLOAD_FIELDS = {
    "as_of_date",
    "confidence",
    "evidence_id",
    "method",
    "workload",
}


def _validate_source_workload_observation(observation: Any) -> dict[str, Any]:
    if not isinstance(observation, dict) or set(observation) != SOURCE_WORKLOAD_FIELDS:
        raise VerifiedConstructionCoreError("workload observation schema differs")
    confidence = observation["confidence"]
    if not _finite_number(confidence) or not 0 <= confidence <= 1:
        raise VerifiedConstructionCoreError("workload confidence differs")
    for field in ("evidence_id", "method", "workload"):
        if not isinstance(observation[field], str) or not observation[field]:
            raise VerifiedConstructionCoreError(f"workload {field} differs")
    _calendar_date(observation["as_of_date"], "workload as_of_date")
    return observation


def _validate_workload_observation(observation: Any) -> dict[str, Any]:
    fields = SOURCE_WORKLOAD_FIELDS | {"deployment_scope"}
    if not isinstance(observation, dict) or set(observation) != fields:
        raise VerifiedConstructionCoreError("workload observation schema differs")
    _validate_source_workload_observation(
        {field: observation[field] for field in SOURCE_WORKLOAD_FIELDS}
    )
    if observation["deployment_scope"] not in {
        "intended",
        "operational",
        "unknown",
    }:
        raise VerifiedConstructionCoreError("workload deployment scope differs")
    return observation


def _validate_role_claim(claim: Any) -> dict[str, Any]:
    fields = {"evidence_id", "party", "relationship_scope", "role"}
    if not isinstance(claim, dict) or set(claim) != fields:
        raise VerifiedConstructionCoreError("role claim schema differs")
    for field in ("evidence_id", "party", "relationship_scope", "role"):
        if not isinstance(claim[field], str) or not claim[field]:
            raise VerifiedConstructionCoreError(f"role claim {field} differs")
    if claim["role"] not in ROLE_COLUMNS or claim["relationship_scope"] not in {
        "intended",
        "current",
        "unknown",
    }:
        raise VerifiedConstructionCoreError("role claim semantics differ")
    return claim


def _verify_source_release() -> dict[str, Any]:
    manifest_path = SOURCE_RELEASE / "manifest.json"
    manifest = _load_json(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("source release manifest has no files map")
    for name in ("entities.csv", "construction_pipeline.csv", "evidence.csv"):
        metadata = files.get(name)
        if not isinstance(metadata, dict):
            raise VerifiedConstructionCoreError(f"source manifest does not bind {name}")
        path = SOURCE_RELEASE / name
        if not path.is_file():
            raise VerifiedConstructionCoreError(f"source payload is not hydrated: {path}")
        if path.stat().st_size != metadata.get("bytes"):
            raise VerifiedConstructionCoreError(f"source payload byte count differs: {name}")
        if _sha256_file(path) != metadata.get("sha256"):
            raise VerifiedConstructionCoreError(f"source payload hash differs: {name}")
    return manifest


def _geometry_release_manifest(
    release_id: str, expected_sha256: str
) -> tuple[Path, dict[str, Any]]:
    release = GEOMETRY_RELEASES.get(release_id)
    if release is None:
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry release is unknown: {release_id}"
        )
    manifest_path = release / "manifest.json"
    manifest = _load_json(manifest_path)
    if _sha256_file(manifest_path) != expected_sha256:
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry release manifest differs: {release_id}"
        )
    files = manifest.get("files")
    if not isinstance(files, dict) or not isinstance(files.get("entities.csv"), dict):
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry release does not bind entities.csv: {release_id}"
        )
    return release, manifest


def _geometry_release_entities(
    release_id: str,
    expected_manifest_sha256: str,
    cache: dict[tuple[str, str], dict[str, dict[str, str]]],
) -> dict[str, dict[str, str]]:
    cache_key = (release_id, expected_manifest_sha256)
    if cache_key in cache:
        return cache[cache_key]
    release, manifest = _geometry_release_manifest(
        release_id, expected_manifest_sha256
    )
    entities_path = release / "entities.csv"
    metadata = manifest["files"]["entities.csv"]
    if not entities_path.is_file():
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry payload is not hydrated: {entities_path}"
        )
    if entities_path.stat().st_size != metadata.get("bytes") or _sha256_file(
        entities_path
    ) != metadata.get("sha256"):
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry payload differs: {release_id}"
        )
    entities = _load_csv(entities_path)
    entities_by_key = {row["stable_key"]: row for row in entities}
    if len(entities_by_key) != len(entities):
        raise VerifiedConstructionCoreError(
            f"reviewed overlay geometry stable keys are not unique: {release_id}"
        )
    cache[cache_key] = entities_by_key
    return entities_by_key


REVIEWED_SITE_LEGACY_FIELDS = {
    "project_stable_key",
    "physical_site_stable_key",
    "source_input_path",
    "source_input_sha256",
    "geometry_evidence_key",
    "geometry_method",
    "geometry_scope_class",
    "horizontal_uncertainty_metres",
    "precision_scope",
    "decision_basis",
}
REVIEWED_SITE_FIELDS = REVIEWED_SITE_LEGACY_FIELDS | {
    "geometry_entity",
    "geometry_derivation",
}


def _reviewed_acceptances_from(
    path: Path, seen: frozenset[Path] = frozenset()
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = path.resolve()
    definitions_root = (ROOT / "definitions").resolve()
    if path.parent != definitions_root or path in seen:
        raise VerifiedConstructionCoreError("reviewed-site contract path or cycle differs")
    if not path.is_file():
        raise VerifiedConstructionCoreError("reviewed-site contract is absent")
    reviewed = _load_json(path)
    if not isinstance(reviewed, dict):
        raise VerifiedConstructionCoreError("reviewed-site contract differs")
    contract_id = reviewed.get("contract_id")
    expected_id = path.stem
    if contract_id != expected_id:
        raise VerifiedConstructionCoreError("reviewed-site contract id differs")
    reviewed_as_of = _calendar_date(
        reviewed.get("reviewed_as_of"), "reviewed-site reviewed_as_of"
    )
    if reviewed_as_of > REVIEW_DATE:
        raise VerifiedConstructionCoreError("reviewed-site contract date differs")
    acceptances = reviewed.get("acceptances")
    if not isinstance(acceptances, list) or not acceptances:
        raise VerifiedConstructionCoreError("reviewed-site acceptances are empty")

    if "base_contract" not in reviewed:
        if set(reviewed) != {
            "contract_id",
            "review_scope",
            "reviewed_as_of",
            "acceptances",
        } or contract_id != "verified-construction-core-v0.1-reviewed-sites":
            raise VerifiedConstructionCoreError("reviewed-site leaf contract differs")
        normalized: list[dict[str, Any]] = []
        for index, acceptance in enumerate(acceptances):
            if not isinstance(acceptance, dict) or set(acceptance) != REVIEWED_SITE_LEGACY_FIELDS:
                raise VerifiedConstructionCoreError(
                    f"reviewed-site leaf acceptance {index} has unexpected fields"
                )
            normalized.append(
                {
                    **acceptance,
                    "geometry_entity": "project",
                    "geometry_derivation": "direct_geometry",
                }
            )
        return normalized, normalized

    if set(reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "acceptances",
    }:
        raise VerifiedConstructionCoreError("reviewed-site successor fields differ")
    base = reviewed["base_contract"]
    if not isinstance(base, dict) or set(base) != {
        "path",
        "sha256",
        "default_geometry_entity",
        "default_geometry_derivation",
    }:
        raise VerifiedConstructionCoreError("reviewed-site base contract differs")
    if base.get("default_geometry_entity") != "project" or base.get(
        "default_geometry_derivation"
    ) != "direct_geometry":
        raise VerifiedConstructionCoreError("reviewed-site base defaults differ")
    relative = Path(base.get("path", ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise VerifiedConstructionCoreError("reviewed-site base path differs")
    base_path = (ROOT / relative).resolve()
    if (
        base_path.parent != definitions_root
        or not base_path.is_file()
        or _sha256_file(base_path) != base.get("sha256")
    ):
        raise VerifiedConstructionCoreError("reviewed-site base hash differs")
    inherited, _ = _reviewed_acceptances_from(base_path, seen | {path})
    delta: list[dict[str, Any]] = []
    for index, acceptance in enumerate(acceptances):
        if not isinstance(acceptance, dict) or set(acceptance) != REVIEWED_SITE_FIELDS:
            raise VerifiedConstructionCoreError(
                f"reviewed-site delta acceptance {index} has unexpected fields"
            )
        delta.append(dict(acceptance))
    flattened = [*inherited, *delta]
    keys = [row["project_stable_key"] for row in flattened]
    if len(set(keys)) != len(keys):
        raise VerifiedConstructionCoreError("reviewed-site project keys are not unique")
    for acceptance in flattened:
        if acceptance["geometry_entity"] not in {"project", "campus"}:
            raise VerifiedConstructionCoreError("reviewed-site geometry entity differs")
        if acceptance["geometry_derivation"] not in {
            "direct_geometry",
            "coordinates_to_point",
        }:
            raise VerifiedConstructionCoreError("reviewed-site geometry derivation differs")
    return flattened, delta


def _reviewed_acceptances() -> list[dict[str, Any]]:
    acceptances, _ = _reviewed_acceptances_from(REVIEW_DEFINITION)
    if REVIEW_DEFINITION.stem != "verified-construction-core-v0.3-reviewed-sites":
        raise VerifiedConstructionCoreError("current reviewed-site contract differs")
    reviewed = _load_json(REVIEW_DEFINITION)
    if reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat():
        raise VerifiedConstructionCoreError("current reviewed-site date differs")
    return acceptances


ROLE_COLUMNS = {
    "owner": "owner",
    "operator": "operator",
    "user": "users",
    "tenant": "tenants",
    "customer": "customers",
}


def _repository_input(path_text: str, expected_sha256: str, field: str) -> Path:
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise VerifiedConstructionCoreError(f"{field} path escapes the repository")
    path = ROOT / relative
    if (
        path.is_symlink()
        or not path.is_file()
        or _sha256_file(path) != expected_sha256
    ):
        raise VerifiedConstructionCoreError(f"{field} source hash differs")
    return path


def _evidence_from_pinned_source(
    binding: Mapping[str, Any], *, evidence_key_field: str, evidence_id_field: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _repository_input(
        str(binding["source_input_path"]),
        str(binding["source_input_sha256"]),
        "provenance",
    )
    source = _load_json(path)
    project = source.get("project")
    if not isinstance(project, dict) or project.get("stable_key") != binding.get(
        "project_stable_key"
    ):
        raise VerifiedConstructionCoreError("provenance project identity differs")
    evidence = source.get("evidence")
    if not isinstance(evidence, list):
        raise VerifiedConstructionCoreError("provenance source evidence differs")
    key = binding[evidence_key_field]
    matches = [row for row in evidence if isinstance(row, dict) and row.get("key") == key]
    if len(matches) != 1:
        raise VerifiedConstructionCoreError("provenance evidence key differs")
    pinned = matches[0]
    evidence_id = binding[evidence_id_field]
    if evidence_id != atlas_stable_id(
        "evidence", "curated-official", key, pinned.get("content_hash")
    ):
        raise VerifiedConstructionCoreError("provenance evidence id differs")
    required = {
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "retrieved_at",
        "content_hash",
    }
    if any(not isinstance(pinned.get(field), str) or not pinned[field] for field in required):
        raise VerifiedConstructionCoreError("provenance evidence fields differ")
    published_at = pinned.get("published_at")
    if published_at is not None and not isinstance(published_at, str):
        raise VerifiedConstructionCoreError("provenance evidence publication date differs")
    row = {
        "evidence_id": evidence_id,
        "kind": pinned["kind"],
        "title": pinned["title"],
        "source_url": pinned["source_url"],
        "publisher": pinned["publisher"],
        "source_family": pinned["source_family"],
        "license": pinned["license"],
        "attribution": pinned["attribution"],
        "published_at": published_at or "",
        "retrieved_at": pinned["retrieved_at"],
        "content_hash": pinned["content_hash"],
    }
    return row, pinned


def _provenance_contract() -> dict[str, Any]:
    validate_frozen_v02(LEGACY_PREVIEW_V02_DIR)
    reviewed = _load_json(PROVENANCE_DEFINITION)
    expected_fields = {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "workload_scope_bindings",
        "role_bindings",
        "excluded_source_roles",
    }
    if not isinstance(reviewed, dict) or set(reviewed) != expected_fields:
        raise VerifiedConstructionCoreError("provenance contract fields differ")
    if (
        reviewed.get("contract_id") != "verified-construction-core-v0.3-provenance"
        or reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat()
    ):
        raise VerifiedConstructionCoreError("provenance contract identity differs")
    base = reviewed.get("base_contract")
    if not isinstance(base, dict) or set(base) != {
        "preview_manifest",
        "reviewed_sites_definition",
    }:
        raise VerifiedConstructionCoreError("provenance base contract differs")
    expected_base = {
        "preview_manifest": (
            "verified_construction_core/2026-08-20-preview-v0.2/manifest.json",
            LEGACY_PREVIEW_V02_MANIFEST_SHA256,
        ),
        "reviewed_sites_definition": (
            "definitions/verified-construction-core-v0.2-reviewed-sites.json",
            "13f4d6e82c9057b1dd95319e19e30c2bae0ac0f1848d6e6dee2bbc10b5dde1d0",
        ),
    }
    for name, (expected_path, expected_sha256) in expected_base.items():
        item = base.get(name)
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise VerifiedConstructionCoreError("provenance base item differs")
        if item != {"path": expected_path, "sha256": expected_sha256}:
            raise VerifiedConstructionCoreError("provenance base pin differs")
        _repository_input(expected_path, expected_sha256, "provenance base")

    workload_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "evidence_key",
        "evidence_id",
        "workload",
        "as_of_date",
        "method",
        "confidence",
        "deployment_scope",
        "semantic_scope",
    }
    role_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "evidence_key",
        "evidence_id",
        "relationship_scope",
        "semantic_scope",
    }
    excluded_fields = {
        "project_stable_key",
        "source_input_path",
        "source_input_sha256",
        "role",
        "party",
        "candidate_evidence_key",
        "candidate_evidence_id",
        "relationship_scope",
        "semantic_scope",
        "reason",
    }
    workload_bindings = reviewed.get("workload_scope_bindings")
    role_bindings = reviewed.get("role_bindings")
    exclusions = reviewed.get("excluded_source_roles")
    if not all(isinstance(rows, list) for rows in (workload_bindings, role_bindings, exclusions)):
        raise VerifiedConstructionCoreError("provenance binding collections differ")
    evidence_rows: dict[str, dict[str, Any]] = {}
    workload_keys: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(workload_bindings):
        if not isinstance(binding, dict) or set(binding) != workload_fields:
            raise VerifiedConstructionCoreError(
                f"workload provenance binding {index} differs"
            )
        key = (
            binding["project_stable_key"],
            binding["evidence_id"],
            binding["workload"],
        )
        if key in workload_keys or binding["deployment_scope"] != "intended":
            raise VerifiedConstructionCoreError("workload provenance identity differs")
        workload_keys.add(key)
        _calendar_date(binding["as_of_date"], "workload provenance as_of_date")
        if not _finite_number(binding["confidence"]) or not 0 <= binding["confidence"] <= 1:
            raise VerifiedConstructionCoreError("workload provenance confidence differs")
        evidence_row, pinned = _evidence_from_pinned_source(
            binding,
            evidence_key_field="evidence_key",
            evidence_id_field="evidence_id",
        )
        metadata = pinned.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("workload_scope") != binding[
            "semantic_scope"
        ]:
            raise VerifiedConstructionCoreError("workload provenance scope differs")
        evidence_rows[evidence_row["evidence_id"]] = evidence_row

    role_keys: set[tuple[str, str, str]] = set()
    for index, binding in enumerate(role_bindings):
        if not isinstance(binding, dict) or set(binding) != role_fields:
            raise VerifiedConstructionCoreError(f"role provenance binding {index} differs")
        key = (
            binding["project_stable_key"],
            binding["role"],
            binding["party"],
        )
        if (
            key in role_keys
            or binding["role"] not in ROLE_COLUMNS
            or binding["relationship_scope"] != "intended"
        ):
            raise VerifiedConstructionCoreError("role provenance identity differs")
        role_keys.add(key)
        evidence_row, pinned = _evidence_from_pinned_source(
            binding,
            evidence_key_field="evidence_key",
            evidence_id_field="evidence_id",
        )
        metadata = pinned.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("role_scope") != binding[
            "semantic_scope"
        ]:
            raise VerifiedConstructionCoreError("role provenance scope differs")
        existing = evidence_rows.get(evidence_row["evidence_id"])
        if existing is not None and existing != evidence_row:
            raise VerifiedConstructionCoreError("provenance evidence collision")
        evidence_rows[evidence_row["evidence_id"]] = evidence_row

    excluded_keys: set[tuple[str, str, str]] = set()
    for index, exclusion in enumerate(exclusions):
        if not isinstance(exclusion, dict) or set(exclusion) != excluded_fields:
            raise VerifiedConstructionCoreError(f"role exclusion {index} differs")
        key = (
            exclusion["project_stable_key"],
            exclusion["role"],
            exclusion["party"],
        )
        if (
            key in excluded_keys
            or key in role_keys
            or exclusion["role"] not in ROLE_COLUMNS
            or exclusion["relationship_scope"] != "not_established"
            or not isinstance(exclusion["reason"], str)
            or not exclusion["reason"]
        ):
            raise VerifiedConstructionCoreError("role exclusion identity differs")
        excluded_keys.add(key)
        _evidence_from_pinned_source(
            exclusion,
            evidence_key_field="candidate_evidence_key",
            evidence_id_field="candidate_evidence_id",
        )
    base_projects = {
        row["project_stable_key"]: row
        for row in _load_csv(LEGACY_PREVIEW_V02_DIR / "projects.csv")
    }
    base_workloads: set[tuple[str, str, str, str, str, float]] = set()
    base_roles: set[tuple[str, str, str]] = set()
    for project_key, project in base_projects.items():
        workloads = _parse_json_field(project["workloads_json"], "base workloads")
        if not isinstance(workloads, list):
            raise VerifiedConstructionCoreError("provenance base workloads differ")
        for workload in workloads:
            _validate_source_workload_observation(workload)
            base_workloads.add(
                (
                    project_key,
                    workload["evidence_id"],
                    workload["workload"],
                    workload["as_of_date"],
                    workload["method"],
                    workload["confidence"],
                )
            )
        for role, column in ROLE_COLUMNS.items():
            for party in project[column].split(";"):
                if party.strip():
                    base_roles.add((project_key, role, party.strip()))
    bound_workloads = {
        (
            row["project_stable_key"],
            row["evidence_id"],
            row["workload"],
            row["as_of_date"],
            row["method"],
            row["confidence"],
        )
        for row in workload_bindings
    }
    if bound_workloads != base_workloads:
        raise VerifiedConstructionCoreError(
            "provenance workload bindings differ from frozen v0.2"
        )
    if role_keys | excluded_keys != base_roles:
        raise VerifiedConstructionCoreError(
            "provenance role decisions differ from frozen v0.2"
        )
    return {
        "workload_scope_bindings": workload_bindings,
        "role_bindings": role_bindings,
        "excluded_source_roles": exclusions,
        "evidence_rows": evidence_rows,
    }


def _portable_source_inputs() -> list[dict[str, Any]]:
    _, delta = _reviewed_acceptances_from(REVIEW_DEFINITION)
    rows: list[dict[str, Any]] = []
    for acceptance in delta:
        path_text = acceptance["source_input_path"]
        path = _repository_input(
            path_text, acceptance["source_input_sha256"], "portable reviewed-site"
        )
        row: dict[str, Any] = {
            "path": path_text,
            "bytes": path.stat().st_size,
            "sha256": acceptance["source_input_sha256"],
            "parent_manifest_path": None,
            "parent_manifest_sha256": None,
        }
        relative = Path(path_text)
        if relative.parts and relative.parts[0] == "source_artifacts":
            if len(relative.parts) < 4:
                raise VerifiedConstructionCoreError(
                    "portable source-artifact path differs"
                )
            parent = ROOT / relative.parts[0] / relative.parts[1]
            manifest_path = parent / "manifest.json"
            checksum_path = parent / "manifest.sha256"
            manifest_sha256 = _sha256_file(manifest_path)
            expected_parent_sha256 = (
                "acb675580c993e3af150f8a3e25f53a8d66a6d7b595b644088a84f1294acd43d"
            )
            if (
                manifest_sha256 != expected_parent_sha256
                or checksum_path.read_text(encoding="utf-8")
                != f"{expected_parent_sha256}  manifest.json\n"
            ):
                raise VerifiedConstructionCoreError(
                    "portable source parent manifest differs"
                )
            manifest = _load_json(manifest_path)
            member_path = str(relative.relative_to(Path(*relative.parts[:2])))
            members = manifest.get("files")
            matches = [
                member
                for member in members
                if isinstance(member, dict) and member.get("path") == member_path
            ] if isinstance(members, list) else []
            if len(matches) != 1 or matches[0] != {
                "path": member_path,
                "bytes": path.stat().st_size,
                "sha256": acceptance["source_input_sha256"],
            }:
                raise VerifiedConstructionCoreError(
                    "portable source parent membership differs"
                )
            row["parent_manifest_path"] = str(
                manifest_path.relative_to(ROOT)
            )
            row["parent_manifest_sha256"] = expected_parent_sha256
        rows.append(row)
    return sorted(rows, key=lambda row: row["path"])


def _validate_v03_inheritance(
    projects: Sequence[Mapping[str, str]],
    sites: Sequence[Mapping[str, str]],
    evidence: Sequence[Mapping[str, str]],
) -> None:
    validate_frozen_v02(LEGACY_PREVIEW_V02_DIR)
    base_projects = {
        row["project_stable_key"]: row
        for row in _load_csv(LEGACY_PREVIEW_V02_DIR / "projects.csv")
    }
    current = {row["project_stable_key"]: row for row in projects}
    if not set(base_projects) < set(current):
        raise VerifiedConstructionCoreError("preview v0.2 inheritance cohort differs")
    intentionally_changed = {
        "workloads_json",
        "owner",
        "operator",
        "users",
        "tenants",
        "customers",
    }
    for key, base in base_projects.items():
        inherited = current[key]
        for field, value in base.items():
            if field not in intentionally_changed and inherited.get(field) != value:
                raise VerifiedConstructionCoreError(
                    f"preview inherited project field differs: {field}"
                )
        base_workloads = _parse_json_field(base["workloads_json"], "base workloads")
        current_workloads = _parse_json_field(
            inherited["workloads_json"], "current workloads"
        )
        stripped = [
            {field: workload[field] for field in SOURCE_WORKLOAD_FIELDS}
            for workload in current_workloads
        ]
        if stripped != base_workloads:
            raise VerifiedConstructionCoreError(
                "preview inherited workload observations differ"
            )

    base_sites = {
        row["site_id"]: row
        for row in _load_csv(LEGACY_PREVIEW_V02_DIR / "sites.csv", SITE_FIELDS)
    }
    current_sites = {row["site_id"]: row for row in sites}
    if not set(base_sites) < set(current_sites):
        raise VerifiedConstructionCoreError("preview v0.2 site inheritance differs")
    for site_id, base in base_sites.items():
        if current_sites[site_id] != base:
            raise VerifiedConstructionCoreError(
                "preview inherited site fields differ"
            )

    base_evidence = {
        row["evidence_id"]: row
        for row in _load_csv(
            LEGACY_PREVIEW_V02_DIR / "evidence.csv", EVIDENCE_FIELDS
        )
    }
    current_evidence = {row["evidence_id"]: row for row in evidence}
    if not set(base_evidence) < set(current_evidence):
        raise VerifiedConstructionCoreError("preview v0.2 evidence inheritance differs")
    mutable_usage_fields = {"roles_json", "project_ids_json"}
    for evidence_id, base in base_evidence.items():
        inherited = current_evidence[evidence_id]
        if any(
            inherited[field] != value
            for field, value in base.items()
            if field not in mutable_usage_fields
        ):
            raise VerifiedConstructionCoreError(
                "preview inherited evidence content differs"
            )


def _validate_v03_delta_project(
    row: Mapping[str, str],
    acceptance: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, str]],
    expected_imagery_outcome: str,
) -> None:
    source_path = _repository_input(
        acceptance["source_input_path"],
        acceptance["source_input_sha256"],
        "current reviewed-site",
    )
    source = _load_json(source_path)
    project = source.get("project")
    campus = source.get("campus")
    source_evidence = source.get("evidence")
    if not all(isinstance(value, dict) for value in (project, campus)) or not isinstance(
        source_evidence, list
    ):
        raise VerifiedConstructionCoreError("current reviewed-site source differs")
    if (
        project["stable_key"] != row["project_stable_key"]
        or campus["stable_key"] != row["physical_site_stable_key"]
        or project["name"] != row["name"]
        or project["country"] != row["country"]
    ):
        raise VerifiedConstructionCoreError("current reviewed-site identity differs")
    geometry_source = project if acceptance["geometry_entity"] == "project" else campus
    if acceptance["geometry_derivation"] == "direct_geometry":
        expected_geometry = geometry_source.get("geometry")
    else:
        coordinates = geometry_source.get("coordinates")
        if not isinstance(coordinates, dict):
            raise VerifiedConstructionCoreError("current reviewed-site coordinates differ")
        expected_geometry = {
            "type": "Point",
            "coordinates": [coordinates.get("longitude"), coordinates.get("latitude")],
        }
    if (
        _parse_json_field(row["geometry_json"], "geometry") != expected_geometry
        or float(row["latitude"]) != float(geometry_source["coordinates"]["latitude"])
        or float(row["longitude"])
        != float(geometry_source["coordinates"]["longitude"])
    ):
        raise VerifiedConstructionCoreError("current reviewed-site geometry differs")

    evidence_by_key = {
        item["key"]: item
        for item in source_evidence
        if isinstance(item, dict) and isinstance(item.get("key"), str)
    }

    def verify_evidence(key: str, evidence_id: str) -> None:
        pinned = evidence_by_key.get(key)
        if pinned is None or evidence_id != atlas_stable_id(
            "evidence", "curated-official", key, pinned.get("content_hash")
        ):
            raise VerifiedConstructionCoreError(
                "current reviewed-site evidence identity differs"
            )
        expected = {
            "evidence_id": evidence_id,
            "kind": pinned["kind"],
            "title": pinned["title"],
            "source_url": pinned["source_url"],
            "publisher": pinned["publisher"],
            "source_family": pinned["source_family"],
            "license": pinned["license"],
            "attribution": pinned["attribution"],
            "published_at": pinned.get("published_at") or "",
            "retrieved_at": pinned["retrieved_at"],
            "content_hash": pinned["content_hash"],
        }
        actual = evidence_by_id.get(evidence_id)
        if actual is None or any(actual.get(field) != value for field, value in expected.items()):
            raise VerifiedConstructionCoreError(
                "current reviewed-site evidence content differs"
            )

    geometry_evidence_key = acceptance["geometry_evidence_key"]
    verify_evidence(geometry_evidence_key, row["geometry_evidence_id"])
    if row["geometry_source_url"] != evidence_by_key[geometry_evidence_key]["source_url"]:
        raise VerifiedConstructionCoreError("current reviewed-site geometry URL differs")
    lifecycle = [
        item
        for item in source.get("lifecycle", [])
        if isinstance(item, dict) and item.get("entity") == "project"
    ]
    if not lifecycle:
        raise VerifiedConstructionCoreError("current reviewed-site lifecycle differs")
    latest = max(lifecycle, key=lambda item: item["as_of_date"])
    status_evidence = evidence_by_key.get(latest["evidence_key"])
    expected_status_id = atlas_stable_id(
        "evidence",
        "curated-official",
        latest["evidence_key"],
        status_evidence.get("content_hash") if status_evidence else None,
    )
    if (
        row["last_observed_physical_status"] != latest["value"]
        or row["status_as_of"] != latest["as_of_date"]
        or row["status_method"] != latest["method"]
        or row["status_evidence_id"] != expected_status_id
    ):
        raise VerifiedConstructionCoreError("current reviewed-site status differs")
    verify_evidence(latest["evidence_key"], expected_status_id)
    if row["status_source_url"] != evidence_by_key[latest["evidence_key"]]["source_url"]:
        raise VerifiedConstructionCoreError("current reviewed-site status URL differs")

    expected_capacity: list[dict[str, Any]] = []
    for observation in source.get("capacities", []):
        if not isinstance(observation, dict) or observation.get("entity") != "project":
            continue
        evidence_key = observation["evidence_key"]
        pinned = evidence_by_key[evidence_key]
        evidence_id = atlas_stable_id(
            "evidence", "curated-official", evidence_key, pinned["content_hash"]
        )
        verify_evidence(evidence_key, evidence_id)
        expected_capacity.append(
            {
                **{
                    field: (
                        float(value)
                        if field in {"low", "base", "high"} and value is not None
                        else value
                    )
                    for field, value in observation.items()
                    if field not in {"entity", "evidence_key"}
                },
                "evidence_id": evidence_id,
            }
        )
    actual_capacity = []
    for field in (
        "power_observations_json",
        "annual_energy_observations_json",
        "efficiency_observations_json",
    ):
        actual_capacity.extend(_parse_json_field(row[field], field))
    if actual_capacity != expected_capacity:
        raise VerifiedConstructionCoreError(
            "current reviewed-site typed metrics differ"
        )
    if source.get("workloads") or source.get("operating_models"):
        raise VerifiedConstructionCoreError(
            "current reviewed-site unsupported normalized claims differ"
        )

    country_iso_a2 = V03_DELTA_COUNTRY_ISO_A2.get(project["country"])
    if country_iso_a2 is None:
        raise VerifiedConstructionCoreError(
            "current reviewed-site country code differs"
        )
    power = [item for item in expected_capacity if item["metric"] in POWER_METRICS]
    energy = [item for item in expected_capacity if item["metric"] in ENERGY_METRICS]
    efficiency = [
        item for item in expected_capacity if item["metric"] in EFFICIENCY_METRICS
    ]
    uncertainty = acceptance["horizontal_uncertainty_metres"]
    expected_row = {
        "project_id": atlas_stable_id(
            "entity", project["stable_key"], "project"
        ),
        "project_stable_key": project["stable_key"],
        "site_id": _stable_id("vcc-site", campus["stable_key"]),
        "physical_site_stable_key": campus["stable_key"],
        "name": project["name"],
        "country": project["country"],
        "country_iso_a2": country_iso_a2,
        "latitude": str(geometry_source["coordinates"]["latitude"]),
        "longitude": str(geometry_source["coordinates"]["longitude"]),
        "geometry_json": _json_bytes(expected_geometry).decode().strip(),
        "geometry_type": expected_geometry["type"],
        "geometry_source_entity_kind": acceptance["geometry_entity"],
        "geometry_derivation": acceptance["geometry_derivation"],
        "geometry_method": acceptance["geometry_method"],
        "geometry_scope_class": acceptance["geometry_scope_class"],
        "geometry_precision_scope": acceptance["precision_scope"],
        "horizontal_uncertainty_metres": (
            "" if uncertainty is None else str(uncertainty)
        ),
        "horizontal_uncertainty_unknown_reason": (
            "official source does not state positional accuracy"
            if uncertainty is None
            else ""
        ),
        "geometry_evidence_id": row["geometry_evidence_id"],
        "last_observed_physical_status": latest["value"],
        "status_as_of": latest["as_of_date"],
        "status_age_days_at_review": str(
            (REVIEW_DATE - _calendar_date(latest["as_of_date"], "status_as_of")).days
        ),
        "status_method": latest["method"],
        "status_evidence_id": expected_status_id,
        "verification_posture": _verification_posture(expected_geometry["type"]),
        "independent_imagery_verification": "false",
        "imagery_review_outcome": expected_imagery_outcome,
        "development_type": "unknown",
        "development_type_unknown_reason": (
            "source evidence does not distinguish greenfield, expansion, or retrofit"
        ),
        "operating_model": "unknown",
        "operating_model_unknown_reason": "not established by selected evidence",
        "operating_model_evidence_id": "",
        "workloads_json": "[]",
        "workload_unknown_reason": "not established by selected evidence",
        "role_claims_json": "[]",
        "power_observations_json": _json_bytes(power).decode().strip(),
        "power_unknown_reason": (
            "" if power else "no typed project power observation; not estimated"
        ),
        "annual_energy_observations_json": _json_bytes(energy).decode().strip(),
        "annual_energy_unknown_reason": (
            "" if energy else "no scoped annual-energy inputs; not estimated"
        ),
        "efficiency_observations_json": _json_bytes(efficiency).decode().strip(),
        "efficiency_unknown_reason": (
            "" if efficiency else "no scoped PUE or WUE observation"
        ),
        "owner": "",
        "operator": "",
        "users": "",
        "tenants": "",
        "customers": "",
        "status_source_url": evidence_by_key[latest["evidence_key"]]["source_url"],
        "geometry_source_url": evidence_by_key[geometry_evidence_key]["source_url"],
    }
    if dict(row) != expected_row:
        differing = sorted(
            field for field in PROJECT_FIELDS if row.get(field) != expected_row[field]
        )
        raise VerifiedConstructionCoreError(
            f"current reviewed-site project projection differs: {differing}"
        )


def _imagery_contract() -> tuple[str, list[dict[str, Any]]]:
    reviewed = _load_json(IMAGERY_REVIEW_DEFINITION)
    if not isinstance(reviewed, dict) or set(reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "base_contract",
        "default_outcome",
        "records",
    }:
        raise VerifiedConstructionCoreError("imagery-review contract fields differ")
    if reviewed.get("contract_id") != "verified-construction-core-v0.3-imagery-reviews":
        raise VerifiedConstructionCoreError("imagery-review contract id differs")
    if reviewed.get("reviewed_as_of") != REVIEW_DATE.isoformat():
        raise VerifiedConstructionCoreError("imagery-review contract date differs")
    base = reviewed.get("base_contract")
    if not isinstance(base, dict) or set(base) != {"path", "sha256"}:
        raise VerifiedConstructionCoreError("imagery-review base contract differs")
    if base != {
        "path": "definitions/verified-construction-core-v0.2-imagery-reviews.json",
        "sha256": "0516a3281d0a3a1734a4bacb8f8d9e5419d0ae8dc22df36c098c5375f84ee613",
    }:
        raise VerifiedConstructionCoreError("imagery-review base pin differs")
    base_path = _repository_input(base["path"], base["sha256"], "imagery-review base")
    base_reviewed = _load_json(base_path)
    if not isinstance(base_reviewed, dict) or set(base_reviewed) != {
        "contract_id",
        "review_scope",
        "reviewed_as_of",
        "default_outcome",
        "records",
    }:
        raise VerifiedConstructionCoreError("imagery-review base fields differ")
    if (
        base_reviewed.get("contract_id")
        != "verified-construction-core-v0.2-imagery-reviews"
        or base_reviewed.get("default_outcome") != reviewed.get("default_outcome")
    ):
        raise VerifiedConstructionCoreError("imagery-review base identity differs")
    default_outcome = reviewed.get("default_outcome")
    if default_outcome != "not_reviewed_for_core_preview":
        raise VerifiedConstructionCoreError("imagery-review default differs")
    base_records = base_reviewed.get("records")
    delta_records = reviewed.get("records")
    if (
        not isinstance(base_records, list)
        or not base_records
        or not isinstance(delta_records, list)
        or not delta_records
    ):
        raise VerifiedConstructionCoreError("imagery-review records are empty")
    records = [*base_records, *delta_records]
    expected_delta_outcomes = {
        "curated:kao-data-harlow-campus:klon-03-building": (
            "tracked_identity_bound_uncertain_with_unadjudicated_later_clear_"
            "conflict_no_construction_claim"
        ),
    }
    required = {
        "project_stable_key",
        "project_entity_id",
        "outcome",
        "portable_identity_binding",
        "identity_binding_basis",
        "primary_review_source_path",
        "primary_review_source_sha256",
        "primary_review_id",
        "primary_blind_id",
        "primary_queue_id",
        "source_comparison_sha256",
        "primary_verdict",
        "local_identity_lineage",
        "later_review_conflict",
        "no_claim_guardrail",
    }
    keys: set[str] = set()
    delta_keys: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != required:
            raise VerifiedConstructionCoreError(
                f"imagery-review record {index} has unexpected fields"
            )
        key = record["project_stable_key"]
        if not isinstance(key, str) or not key or key in keys:
            raise VerifiedConstructionCoreError("imagery-review project key differs")
        keys.add(key)
        if index >= len(base_records):
            delta_keys.add(key)
            if record["outcome"] != expected_delta_outcomes.get(key):
                raise VerifiedConstructionCoreError(
                    "imagery-review delta outcome differs"
                )
        try:
            if str(UUID(record["project_entity_id"])) != record["project_entity_id"]:
                raise ValueError
        except (ValueError, AttributeError) as error:
            raise VerifiedConstructionCoreError(
                "imagery-review project entity id differs"
            ) from error
        if record["no_claim_guardrail"] is not True or not isinstance(
            record["portable_identity_binding"], bool
        ):
            raise VerifiedConstructionCoreError("imagery-review guardrail differs")
        for field in (
            "outcome",
            "identity_binding_basis",
            "primary_review_id",
            "primary_blind_id",
            "primary_queue_id",
            "source_comparison_sha256",
        ):
            if not isinstance(record[field], str) or not record[field]:
                raise VerifiedConstructionCoreError(
                    f"imagery-review {field} differs"
                )
        relative_path = Path(record["primary_review_source_path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise VerifiedConstructionCoreError("imagery-review source path escapes")
        source_path = ROOT / relative_path
        if not source_path.is_file() or _sha256_file(source_path) != record[
            "primary_review_source_sha256"
        ]:
            raise VerifiedConstructionCoreError("imagery-review source hash differs")
        source_review = _load_json(source_path)
        if source_review.get("review_id") != record["primary_review_id"]:
            raise VerifiedConstructionCoreError("imagery-review source id differs")
        blind_id = record["primary_blind_id"]
        decisions = source_review.get("decisions")
        lineage = source_review.get("lineage_records")
        if isinstance(decisions, list):
            matches = [row for row in decisions if row.get("blind_id") == blind_id]
            if len(matches) != 1 or any(
                matches[0].get(field) != value
                for field, value in record["primary_verdict"].items()
            ):
                raise VerifiedConstructionCoreError("imagery-review verdict differs")
        elif isinstance(lineage, list):
            matches = [row for row in lineage if row.get("blind_id") == blind_id]
            if len(matches) != 1:
                raise VerifiedConstructionCoreError("imagery-review lineage differs")
            match = matches[0]
            members = match.get("members")
            if not isinstance(members, list) or len(members) != 1:
                raise VerifiedConstructionCoreError("imagery-review member differs")
            member = members[0]
            semantics = source_review.get("decision_semantics", {}).get(
                match.get("visual_verdict")
            )
            expected_verdict = {
                "semantics": semantics,
                "visual_verdict": match.get("visual_verdict"),
            }
            if (
                member.get("stable_key") != key
                or member.get("entity_id") != record["project_entity_id"]
                or member.get("queue_id") != record["primary_queue_id"]
                or match.get("source_comparison_sha256")
                != record["source_comparison_sha256"]
                or expected_verdict != record["primary_verdict"]
            ):
                raise VerifiedConstructionCoreError(
                    "imagery-review identity-bound lineage differs"
                )
        else:
            raise VerifiedConstructionCoreError("imagery-review source format differs")
        local_lineage = record["local_identity_lineage"]
        if record["portable_identity_binding"]:
            if local_lineage is not None:
                raise VerifiedConstructionCoreError(
                    "portable imagery-review identity has local-only lineage"
                )
        else:
            if not isinstance(local_lineage, dict) or set(local_lineage) != {
                "analyst_review_path",
                "analyst_review_sha256",
                "queue_path",
                "queue_sha256",
            }:
                raise VerifiedConstructionCoreError(
                    "local imagery-review identity lineage differs"
                )
            analyst_path = ROOT / local_lineage["analyst_review_path"]
            queue_path = ROOT / local_lineage["queue_path"]
            if analyst_path.exists() != queue_path.exists():
                raise VerifiedConstructionCoreError(
                    "local imagery-review identity lineage is partially hydrated"
                )
            if analyst_path.exists():
                if (
                    _sha256_file(analyst_path)
                    != local_lineage["analyst_review_sha256"]
                    or _sha256_file(queue_path) != local_lineage["queue_sha256"]
                ):
                    raise VerifiedConstructionCoreError(
                        "local imagery-review identity lineage hash differs"
                    )
                analyst_matches = [
                    row
                    for row in _load_jsonl(analyst_path)
                    if row.get("blind_id") == blind_id
                ]
                queue_matches = [
                    row
                    for row in _load_jsonl(queue_path)
                    if row.get("queue_id") == record["primary_queue_id"]
                ]
                if len(analyst_matches) != 1 or len(queue_matches) != 1:
                    raise VerifiedConstructionCoreError(
                        "local imagery-review identity lineage is not unique"
                    )
                queue_entity = queue_matches[0].get("entity", {})
                if (
                    analyst_matches[0].get("queue_id")
                    != record["primary_queue_id"]
                    or analyst_matches[0]
                    .get("input_artifacts", {})
                    .get("comparison.png", {})
                    .get("sha256")
                    != record["source_comparison_sha256"]
                    or queue_entity.get("stable_key") != key
                    or queue_entity.get("id") != record["project_entity_id"]
                ):
                    raise VerifiedConstructionCoreError(
                        "local imagery-review identity lineage differs"
                    )
        conflict = record["later_review_conflict"]
        if conflict is not None:
            if not isinstance(conflict, dict) or set(conflict) != {
                "blind_id",
                "identity_binding_status",
                "local_analyst_review_path",
                "local_analyst_review_sha256",
                "local_queue_path",
                "local_queue_sha256",
                "queue_id",
                "review_source_path",
                "review_source_sha256",
                "source_comparison_sha256",
                "supersedes_primary",
                "verdict",
            }:
                raise VerifiedConstructionCoreError("imagery-review conflict differs")
            if conflict["supersedes_primary"] is not False:
                raise VerifiedConstructionCoreError(
                    "imagery-review conflict cannot supersede without adjudication"
                )
            conflict_path = ROOT / conflict["review_source_path"]
            if not conflict_path.is_file() or _sha256_file(conflict_path) != conflict[
                "review_source_sha256"
            ]:
                raise VerifiedConstructionCoreError("imagery-review conflict hash differs")
            conflict_source = _load_json(conflict_path)
            conflict_matches = [
                row
                for row in conflict_source.get("decisions", [])
                if row.get("blind_id") == conflict["blind_id"]
            ]
            if len(conflict_matches) != 1 or any(
                conflict_matches[0].get(field) != value
                for field, value in conflict["verdict"].items()
            ):
                raise VerifiedConstructionCoreError(
                    "imagery-review conflict verdict differs"
                )
            conflict_analyst_path = ROOT / conflict["local_analyst_review_path"]
            conflict_queue_path = ROOT / conflict["local_queue_path"]
            if conflict_analyst_path.exists() != conflict_queue_path.exists():
                raise VerifiedConstructionCoreError(
                    "imagery-review conflict lineage is partially hydrated"
                )
            if conflict_analyst_path.exists():
                if (
                    _sha256_file(conflict_analyst_path)
                    != conflict["local_analyst_review_sha256"]
                    or _sha256_file(conflict_queue_path)
                    != conflict["local_queue_sha256"]
                ):
                    raise VerifiedConstructionCoreError(
                        "imagery-review conflict lineage hash differs"
                    )
                conflict_analyst_matches = [
                    row
                    for row in _load_jsonl(conflict_analyst_path)
                    if row.get("blind_id") == conflict["blind_id"]
                ]
                conflict_queue_matches = [
                    row
                    for row in _load_jsonl(conflict_queue_path)
                    if row.get("queue_id") == conflict["queue_id"]
                ]
                if (
                    len(conflict_analyst_matches) != 1
                    or len(conflict_queue_matches) != 1
                ):
                    raise VerifiedConstructionCoreError(
                        "imagery-review conflict lineage is not unique"
                    )
                conflict_analyst = conflict_analyst_matches[0]
                conflict_entity = conflict_queue_matches[0].get("entity", {})
                if (
                    conflict_analyst.get("queue_id") != conflict["queue_id"]
                    or conflict_analyst.get("source_entity_lineage", {}).get("id")
                    != record["project_entity_id"]
                    or conflict_analyst
                    .get("input_artifacts", {})
                    .get("comparison.png", {})
                    .get("sha256")
                    != conflict["source_comparison_sha256"]
                    or conflict["source_comparison_sha256"]
                    != record["source_comparison_sha256"]
                    or conflict_entity.get("stable_key") != key
                    or conflict_entity.get("id") != record["project_entity_id"]
                ):
                    raise VerifiedConstructionCoreError(
                        "imagery-review conflict identity lineage differs"
                    )
    if delta_keys != set(expected_delta_outcomes):
        raise VerifiedConstructionCoreError("imagery-review delta cohort differs")
    return default_outcome, records


def _review_contracts() -> tuple[
    list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]
]:
    acceptances = _reviewed_acceptances()
    overlays = _load_json(OVERLAY_DEFINITION)
    required = {
        "project_stable_key",
        "physical_site_stable_key",
        "source_input_path",
        "source_input_sha256",
        "geometry_entity",
        "geometry_derivation",
        "geometry_evidence_key",
        "geometry_method",
        "geometry_scope_class",
        "horizontal_uncertainty_metres",
        "precision_scope",
        "decision_basis",
    }
    keys: set[str] = set()
    source_records: dict[str, dict[str, Any]] = {}
    for index, acceptance in enumerate(acceptances):
        if not isinstance(acceptance, dict) or set(acceptance) != required:
            raise VerifiedConstructionCoreError(
                f"reviewed-site acceptance {index} has unexpected fields"
            )
        key = acceptance["project_stable_key"]
        if key in keys:
            raise VerifiedConstructionCoreError(f"duplicate reviewed project: {key}")
        keys.add(key)
        relative_path = Path(acceptance["source_input_path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source path escapes the repository: {relative_path}"
            )
        source_path = ROOT / relative_path
        if not source_path.is_file():
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source is not hydrated: {source_path}"
            )
        if _sha256_file(source_path) != acceptance["source_input_sha256"]:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source hash differs: {source_path}"
            )
        source_record = _load_json(source_path)
        if not isinstance(source_record, dict):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source is not an object: {source_path}"
            )
        project = source_record.get("project")
        campus = source_record.get("campus")
        source_evidence = source_record.get("evidence")
        if not isinstance(project, dict) or not isinstance(campus, dict):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source lacks project/campus: {source_path}"
            )
        if not isinstance(source_evidence, list):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry source lacks evidence: {source_path}"
            )
        if project.get("stable_key") != key:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry project identity differs: {source_path}"
            )
        if campus.get("stable_key") != acceptance["physical_site_stable_key"]:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry campus identity differs: {source_path}"
            )
        geometry_source_record = (
            project if acceptance["geometry_entity"] == "project" else campus
        )
        if geometry_source_record.get("evidence_key") != acceptance[
            "geometry_evidence_key"
        ]:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry-source evidence differs: {source_path}"
            )
        matching_evidence = [
            row
            for row in source_evidence
            if isinstance(row, dict)
            and row.get("key") == acceptance["geometry_evidence_key"]
        ]
        if len(matching_evidence) != 1:
            raise VerifiedConstructionCoreError(
                f"reviewed geometry evidence is not unique: {source_path}"
            )
        uncertainty = acceptance["horizontal_uncertainty_metres"]
        if uncertainty is not None and (
            isinstance(uncertainty, bool)
            or not isinstance(uncertainty, (int, float))
            or uncertainty < 0
        ):
            raise VerifiedConstructionCoreError(
                f"reviewed geometry uncertainty is invalid: {source_path}"
            )
        source_records[key] = source_record
    if set(overlays) != {
        "contract_id",
        "purpose",
        "required_fields",
        "allowed_decisions",
        "overlays",
    }:
        raise VerifiedConstructionCoreError("reviewed-overlay contract fields differ")
    allowed = set(overlays.get("allowed_decisions", []))
    if overlays.get("contract_id") != "verified-construction-core-reviewed-overlays-v1":
        raise VerifiedConstructionCoreError("reviewed-overlay contract id differs")
    if allowed != {"queued", "accepted", "excluded"}:
        raise VerifiedConstructionCoreError("reviewed-overlay decisions differ")
    required_overlay_fields = {
        "overlay_id",
        "source_project_stable_key",
        "source_entity_id",
        "geometry_release_id",
        "geometry_release_manifest_sha256",
        "geometry_stable_key",
        "identity_basis",
        "decision",
        "decision_reason",
        "reviewed_at",
    }
    if set(overlays.get("required_fields", [])) != required_overlay_fields:
        raise VerifiedConstructionCoreError("reviewed-overlay required fields differ")
    overlay_rows = overlays.get("overlays")
    if not isinstance(overlay_rows, list):
        raise VerifiedConstructionCoreError("reviewed overlays are not a list")
    overlay_ids: set[str] = set()
    for overlay in overlay_rows:
        if not isinstance(overlay, dict) or set(overlay) != required_overlay_fields | {
            "geometry_scope",
            "satellite_review",
        }:
            raise VerifiedConstructionCoreError("reviewed overlay fields differ")
        overlay_id = overlay["overlay_id"]
        if not isinstance(overlay_id, str) or not overlay_id or overlay_id in overlay_ids:
            raise VerifiedConstructionCoreError("reviewed overlay id differs")
        overlay_ids.add(overlay_id)
        if overlay.get("decision") not in allowed:
            raise VerifiedConstructionCoreError("reviewed overlay has invalid decision")
        if overlay["decision"] == "accepted":
            raise VerifiedConstructionCoreError(
                "accepted reviewed overlays require selector integration"
            )
        for field in (
            "source_project_stable_key",
            "source_entity_id",
            "geometry_release_id",
            "geometry_release_manifest_sha256",
            "geometry_stable_key",
            "identity_basis",
            "decision_reason",
            "geometry_scope",
        ):
            if not isinstance(overlay[field], str) or not overlay[field]:
                raise VerifiedConstructionCoreError(
                    f"reviewed overlay {field} differs"
                )
        try:
            if str(UUID(overlay["source_entity_id"])) != overlay["source_entity_id"]:
                raise ValueError
        except (ValueError, AttributeError) as error:
            raise VerifiedConstructionCoreError(
                "reviewed overlay source entity id differs"
            ) from error
        reviewed_at = _calendar_date(overlay["reviewed_at"], "overlay reviewed_at")
        if reviewed_at > REVIEW_DATE:
            raise VerifiedConstructionCoreError("reviewed overlay date is in the future")
        satellite_review = overlay["satellite_review"]
        if not isinstance(satellite_review, dict) or not isinstance(
            satellite_review.get("outcome"), str
        ):
            raise VerifiedConstructionCoreError("reviewed overlay satellite outcome differs")
    return acceptances, overlays, source_records


def _first_failure(row: Mapping[str, str], accepted: set[str]) -> str:
    if row.get("entity_kind") != "project":
        return "entity_kind_not_project"
    if row.get("status") not in PHYSICAL_STATUSES:
        return "status_not_physical"
    if row.get("status_method") not in AUTHORITATIVE_STATUS_METHODS:
        return "status_method_not_authoritative"
    try:
        age = (REVIEW_DATE - date.fromisoformat(row["status_as_of"])).days
    except (KeyError, ValueError):
        return "invalid_status_date"
    if age < 0 or age > MAX_STATUS_AGE_DAYS:
        return "status_outside_90_day_window"
    if row.get("stable_key") not in accepted:
        return "not_in_reviewed_site_geometry_allowlist"
    return "selected"


def _imagery_outcome(
    project_key: str,
    default_outcome: str,
    records_by_key: Mapping[str, Mapping[str, Any]],
) -> str:
    record = records_by_key.get(project_key)
    return default_outcome if record is None else str(record["outcome"])


def _verification_posture(geometry_type: str) -> str:
    if geometry_type in {"Polygon", "MultiPolygon"}:
        return "recent_authoritative_physical_observation_plus_official_boundary"
    return "recent_authoritative_physical_observation_plus_reviewed_site_locator"


def _point_from_coordinates(coordinates: Any, project_key: str) -> dict[str, Any]:
    if not isinstance(coordinates, dict) or set(coordinates) != {
        "latitude",
        "longitude",
    }:
        raise VerifiedConstructionCoreError(
            f"reviewed coordinates differ: {project_key}"
        )
    latitude = coordinates["latitude"]
    longitude = coordinates["longitude"]
    for value, lower, upper in (
        (latitude, -90, 90),
        (longitude, -180, 180),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < lower
            or value > upper
        ):
            raise VerifiedConstructionCoreError(
                f"reviewed coordinates are invalid: {project_key}"
            )
    return {"type": "Point", "coordinates": [longitude, latitude]}


def _resolve_reviewed_geometry(
    acceptance: Mapping[str, Any],
    source_record: Mapping[str, Any],
    project_release_row: Mapping[str, str],
    campus_release_row: Mapping[str, str],
) -> tuple[dict[str, Any], Mapping[str, str]]:
    project_key = acceptance["project_stable_key"]
    entity_kind = acceptance["geometry_entity"]
    source_entity = source_record[entity_kind]
    release_entity = (
        project_release_row if entity_kind == "project" else campus_release_row
    )
    if release_entity.get("entity_kind") != entity_kind:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry release entity differs: {project_key}"
        )
    derivation = acceptance["geometry_derivation"]
    if derivation == "direct_geometry":
        geometry = source_entity.get("geometry")
        if not isinstance(geometry, dict):
            raise VerifiedConstructionCoreError(
                f"reviewed direct geometry is absent: {project_key}"
            )
        if geometry.get("type") == "Point":
            source_point = _point_from_coordinates(
                source_entity.get("coordinates"), project_key
            )
            if source_point != geometry:
                raise VerifiedConstructionCoreError(
                    f"reviewed point geometry and coordinates differ: {project_key}"
                )
    elif derivation == "coordinates_to_point":
        if source_entity.get("geometry") is not None:
            raise VerifiedConstructionCoreError(
                f"coordinate-derived geometry source is not null: {project_key}"
            )
        geometry = _point_from_coordinates(source_entity.get("coordinates"), project_key)
    else:  # The review-contract parser rejects this before geometry resolution.
        raise VerifiedConstructionCoreError(
            f"reviewed geometry derivation differs: {project_key}"
        )
    if geometry.get("type") not in {"Point", "Polygon", "MultiPolygon"}:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry type differs: {project_key}"
        )
    release_geometry = _parse_json_field(
        release_entity.get("geometry_json", ""), "geometry"
    )
    if release_geometry != geometry:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry no longer matches its pinned source: {project_key}"
        )
    try:
        release_latitude = float(release_entity["latitude"])
        release_longitude = float(release_entity["longitude"])
    except (KeyError, TypeError, ValueError) as error:
        raise VerifiedConstructionCoreError(
            f"reviewed geometry representative coordinates differ: {project_key}"
        ) from error
    if (
        not math.isfinite(release_latitude)
        or not math.isfinite(release_longitude)
        or not -90 <= release_latitude <= 90
        or not -180 <= release_longitude <= 180
    ):
        raise VerifiedConstructionCoreError(
            f"reviewed geometry representative coordinates differ: {project_key}"
        )
    if geometry["type"] == "Point" and geometry["coordinates"] != [
        release_longitude,
        release_latitude,
    ]:
        raise VerifiedConstructionCoreError(
            f"reviewed point coordinates no longer match their pinned source: {project_key}"
        )
    return geometry, release_entity


def _preferred_site_geometry_member(
    members: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    geometry_rank = {"Point": 1, "Polygon": 2, "MultiPolygon": 3}
    try:
        highest_rank = max(geometry_rank[row["geometry_type"]] for row in members)
    except (KeyError, ValueError) as error:
        raise VerifiedConstructionCoreError("preview site geometry rank differs") from error
    candidates = [
        row
        for row in members
        if geometry_rank[row["geometry_type"]] == highest_rank
    ]
    signatures = {
        (row["geometry_json"], str(row["latitude"]), str(row["longitude"]))
        for row in candidates
    }
    if len(signatures) != 1:
        raise VerifiedConstructionCoreError(
            "preview site has conflicting highest-ranked reviewed geometries"
        )
    return candidates[0]


def _final_release_gates(
    sites: Sequence[Mapping[str, Any]], projects: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    country_counts = Counter(row["country"] for row in sites)
    site_count = len(sites)
    non_us_count = sum(row["country_iso_a2"] != "US" for row in sites)
    max_share = max(country_counts.values(), default=0) / site_count if site_count else 0
    imagery_count = sum(
        row["imagery_review_outcome"] != "not_reviewed_for_core_preview"
        for row in projects
    )
    return {
        "site_count": {
            "actual": site_count,
            "required": FINAL_REQUIREMENTS["site_count"],
            "passed": site_count == FINAL_REQUIREMENTS["site_count"],
        },
        "country_count": {
            "actual": len(country_counts),
            "required_minimum": FINAL_REQUIREMENTS["country_count"],
            "passed": len(country_counts) >= FINAL_REQUIREMENTS["country_count"],
        },
        "non_us_site_count": {
            "actual": non_us_count,
            "required_minimum": FINAL_REQUIREMENTS["non_us_site_count"],
            "passed": non_us_count >= FINAL_REQUIREMENTS["non_us_site_count"],
        },
        "maximum_single_country_share": {
            "actual": round(max_share, 6),
            "required_maximum": FINAL_REQUIREMENTS["maximum_single_country_share"],
            "passed": max_share <= FINAL_REQUIREMENTS["maximum_single_country_share"],
        },
        "imagery_outcomes_complete": {
            "actual": imagery_count,
            "required": len(projects),
            "passed": imagery_count == len(projects),
        },
        "blind_review": {
            "sample_size": 0,
            "agreements": 0,
            "required_sample_size": FINAL_REQUIREMENTS["blind_review_sample_size"],
            "required_agreements": FINAL_REQUIREMENTS[
                "blind_review_minimum_agreements"
            ],
            "passed": False,
        },
        "clean_clone_rebuild": {
            "passed": False,
            "reason": CLEAN_CLONE_REBUILD_REASON,
        },
    }


def _build_rows() -> dict[str, Any]:
    _validate_v03_definition_pins()
    source_manifest = _verify_source_release()
    acceptances, overlays, source_records = _review_contracts()
    default_imagery_outcome, imagery_records = _imagery_contract()
    provenance = _provenance_contract()
    pipeline = _load_csv(SOURCE_RELEASE / "construction_pipeline.csv")
    entities = _load_csv(SOURCE_RELEASE / "entities.csv")
    evidence_rows = _load_csv(SOURCE_RELEASE / "evidence.csv")

    pipeline_by_key = {row["stable_key"]: row for row in pipeline}
    entities_by_key = {row["stable_key"]: row for row in entities}
    evidence_by_id = {row["evidence_id"]: row for row in evidence_rows}
    if len(pipeline_by_key) != len(pipeline):
        raise VerifiedConstructionCoreError("source pipeline stable keys are not unique")
    if len(entities_by_key) != len(entities):
        raise VerifiedConstructionCoreError("source entity stable keys are not unique")
    if len(evidence_by_id) != len(evidence_rows):
        raise VerifiedConstructionCoreError("source evidence identifiers are not unique")
    for evidence_id, provenance_evidence in provenance["evidence_rows"].items():
        existing = evidence_by_id.get(evidence_id)
        if existing is not None and existing != provenance_evidence:
            raise VerifiedConstructionCoreError(
                "source and provenance evidence differ"
            )
        evidence_by_id[evidence_id] = provenance_evidence
    geometry_release_cache: dict[
        tuple[str, str], dict[str, dict[str, str]]
    ] = {}
    for overlay in overlays["overlays"]:
        source_overlay = pipeline_by_key.get(overlay["source_project_stable_key"])
        if source_overlay is None or source_overlay.get("entity_id") != overlay[
            "source_entity_id"
        ]:
            raise VerifiedConstructionCoreError(
                f"reviewed overlay source identity differs: {overlay['overlay_id']}"
            )
        geometry_entities = _geometry_release_entities(
            overlay["geometry_release_id"],
            overlay["geometry_release_manifest_sha256"],
            geometry_release_cache,
        )
        geometry_overlay = geometry_entities.get(overlay["geometry_stable_key"])
        if (
            geometry_overlay is None
            or geometry_overlay.get("entity_id") != overlay["source_entity_id"]
            or geometry_overlay.get("entity_kind") != "project"
        ):
            raise VerifiedConstructionCoreError(
                f"reviewed overlay geometry identity differs: {overlay['overlay_id']}"
            )
        geometry = _parse_json_field(
            geometry_overlay.get("geometry_json", ""), "overlay geometry"
        )
        if not isinstance(geometry, dict) or geometry.get("type") not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise VerifiedConstructionCoreError(
                f"reviewed overlay geometry is not a site boundary: {overlay['overlay_id']}"
            )
    accepted_keys = {row["project_stable_key"] for row in acceptances}
    imagery_by_key = {row["project_stable_key"]: row for row in imagery_records}
    if not set(imagery_by_key) <= accepted_keys:
        raise VerifiedConstructionCoreError(
            "imagery-review contract references a non-selected project"
        )
    reason_counts = Counter(_first_failure(row, accepted_keys) for row in pipeline)

    projects: list[dict[str, Any]] = []
    acceptance_by_key = {row["project_stable_key"]: row for row in acceptances}
    evidence_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    workload_bindings = {
        (
            row["project_stable_key"],
            row["evidence_id"],
            row["workload"],
        ): row
        for row in provenance["workload_scope_bindings"]
    }
    role_bindings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    role_exclusions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in provenance["role_bindings"]:
        role_bindings[row["project_stable_key"]].append(row)
    for row in provenance["excluded_source_roles"]:
        role_exclusions[row["project_stable_key"]].append(row)
    used_workload_bindings: set[tuple[str, str, str]] = set()
    used_role_bindings: set[tuple[str, str, str]] = set()
    used_role_exclusions: set[tuple[str, str, str]] = set()

    for project_key in sorted(accepted_keys):
        acceptance = acceptance_by_key[project_key]
        source = pipeline_by_key.get(project_key)
        if source is None:
            raise VerifiedConstructionCoreError(f"reviewed project is absent: {project_key}")
        failure = _first_failure(source, accepted_keys)
        if failure != "selected":
            raise VerifiedConstructionCoreError(
                f"reviewed project no longer passes {failure}: {project_key}"
            )
        site_key = acceptance["physical_site_stable_key"]
        site_source = entities_by_key.get(site_key)
        if site_source is None or site_source.get("entity_kind") != "campus":
            raise VerifiedConstructionCoreError(f"reviewed physical site is absent: {site_key}")
        source_record = source_records[project_key]
        geometry, geometry_release = _resolve_reviewed_geometry(
            acceptance, source_record, source, site_source
        )
        project_id = source["entity_id"]
        imagery_record = imagery_by_key.get(project_key)
        if imagery_record is not None and imagery_record["project_entity_id"] != project_id:
            raise VerifiedConstructionCoreError(
                f"imagery-review project identity differs: {project_key}"
            )
        site_id = _stable_id("vcc-site", site_key)
        status_evidence_id = source["status_evidence_id"]
        geometry_evidence_id = geometry_release["snapshot_evidence_id"]
        for evidence_id, role in (
            (status_evidence_id, "physical_status"),
            (geometry_evidence_id, "geometry"),
        ):
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"project references absent {role} evidence: {project_key}"
                )
            evidence_usage[evidence_id]["roles"].add(role)
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        pinned_geometry_evidence = next(
            row
            for row in source_record["evidence"]
            if row.get("key") == acceptance["geometry_evidence_key"]
        )
        published_geometry_evidence = evidence_by_id[geometry_evidence_id]
        for field in (
            "kind",
            "title",
            "source_url",
            "publisher",
            "source_family",
            "license",
            "attribution",
            "published_at",
            "retrieved_at",
            "content_hash",
        ):
            pinned_value = pinned_geometry_evidence.get(field)
            if pinned_value is None:
                pinned_value = ""
            if published_geometry_evidence.get(field, "") != pinned_value:
                raise VerifiedConstructionCoreError(
                    f"reviewed geometry evidence field {field} differs: {project_key}"
                )

        observations = _parse_json_field(
            source["capacity_estimates_json"], "capacity_estimates"
        )
        if not isinstance(observations, list):
            raise VerifiedConstructionCoreError("capacity observations are not a list")
        if any(not isinstance(row, dict) for row in observations):
            raise VerifiedConstructionCoreError("capacity observation is not an object")
        for observation in observations:
            _validate_typed_observation(
                observation, POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
            )
        unexpected_metrics = {
            row.get("metric")
            for row in observations
            if row.get("metric")
            not in POWER_METRICS | ENERGY_METRICS | EFFICIENCY_METRICS
        }
        if unexpected_metrics:
            raise VerifiedConstructionCoreError(
                f"unclassified typed metrics {sorted(unexpected_metrics)}: {project_key}"
            )
        power = [row for row in observations if row.get("metric") in POWER_METRICS]
        energy = [row for row in observations if row.get("metric") in ENERGY_METRICS]
        efficiency = [
            row for row in observations if row.get("metric") in EFFICIENCY_METRICS
        ]
        source_workloads = _parse_json_field(source["workloads_json"], "workloads")
        if not isinstance(source_workloads, list):
            raise VerifiedConstructionCoreError("workloads are not a list")
        if any(not isinstance(row, dict) for row in source_workloads):
            raise VerifiedConstructionCoreError("workload observation is not an object")
        for observation in observations:
            evidence_id = observation.get("evidence_id")
            metric = observation.get("metric")
            if not evidence_id or evidence_id not in evidence_by_id or not metric:
                raise VerifiedConstructionCoreError(
                    f"typed metric evidence is absent: {project_key}"
                )
            evidence_usage[evidence_id]["roles"].add(f"typed_metric:{metric}")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        workloads: list[dict[str, Any]] = []
        for source_workload in source_workloads:
            _validate_source_workload_observation(source_workload)
            binding_key = (
                project_key,
                source_workload["evidence_id"],
                source_workload["workload"],
            )
            binding = workload_bindings.get(binding_key)
            if binding is None or any(
                source_workload[field] != binding[field]
                for field in SOURCE_WORKLOAD_FIELDS
            ):
                raise VerifiedConstructionCoreError(
                    f"workload provenance is absent or differs: {project_key}"
                )
            workload = {
                **source_workload,
                "deployment_scope": binding["deployment_scope"],
            }
            _validate_workload_observation(workload)
            workloads.append(workload)
            used_workload_bindings.add(binding_key)
            evidence_id = workload["evidence_id"]
            if not evidence_id or evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"workload evidence is absent: {project_key}"
                )
            evidence_usage[evidence_id]["roles"].add("workload")
            evidence_usage[evidence_id]["roles"].add(
                f"workload_scope:{workload['deployment_scope']}"
            )
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        operating_model_evidence_id = source["operating_model_evidence_id"]
        if operating_model_evidence_id:
            if operating_model_evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"operating-model evidence is absent: {project_key}"
                )
            evidence_usage[operating_model_evidence_id]["roles"].add(
                "operating_model"
            )
            evidence_usage[operating_model_evidence_id]["project_ids"].add(
                project_id
            )
        source_role_keys: set[tuple[str, str, str]] = set()
        for role, column in ROLE_COLUMNS.items():
            parties = [
                party.strip()
                for party in source[column].split(";")
                if party.strip()
            ]
            if len(parties) != len(set(parties)):
                raise VerifiedConstructionCoreError(
                    f"source role parties are not unique: {project_key}"
                )
            source_role_keys.update((project_key, role, party) for party in parties)
        accepted_role_keys = {
            (project_key, row["role"], row["party"])
            for row in role_bindings.get(project_key, [])
        }
        excluded_role_keys = {
            (project_key, row["role"], row["party"])
            for row in role_exclusions.get(project_key, [])
        }
        if source_role_keys != accepted_role_keys | excluded_role_keys:
            raise VerifiedConstructionCoreError(
                f"source role provenance coverage differs: {project_key}"
            )
        role_claims: list[dict[str, str]] = []
        projected_roles: dict[str, list[str]] = {
            role: [] for role in ROLE_COLUMNS
        }
        for binding in role_bindings.get(project_key, []):
            binding_key = (project_key, binding["role"], binding["party"])
            used_role_bindings.add(binding_key)
            evidence_id = binding["evidence_id"]
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    f"role evidence is absent: {project_key}"
                )
            role_claims.append(
                {
                    "evidence_id": evidence_id,
                    "party": binding["party"],
                    "relationship_scope": binding["relationship_scope"],
                    "role": binding["role"],
                }
            )
            projected_roles[binding["role"]].append(binding["party"])
            evidence_usage[evidence_id]["roles"].add(f"role:{binding['role']}")
            evidence_usage[evidence_id]["project_ids"].add(project_id)
        used_role_exclusions.update(excluded_role_keys)
        role_claims.sort(key=lambda row: (row["role"], row["party"], row["evidence_id"]))
        role_projection = {
            column: "; ".join(sorted(projected_roles[role]))
            for role, column in ROLE_COLUMNS.items()
        }
        status_date = _calendar_date(source["status_as_of"], "status_as_of")
        geometry_type = geometry["type"]
        uncertainty = acceptance["horizontal_uncertainty_metres"]
        projects.append(
            {
                "project_id": project_id,
                "project_stable_key": project_key,
                "site_id": site_id,
                "physical_site_stable_key": site_key,
                "name": source["name"],
                "country": source["country"],
                "country_iso_a2": source["country_iso_a2"],
                "latitude": geometry_release["latitude"],
                "longitude": geometry_release["longitude"],
                "geometry_json": _json_bytes(geometry).decode().strip(),
                "geometry_type": geometry_type,
                "geometry_source_entity_kind": acceptance["geometry_entity"],
                "geometry_derivation": acceptance["geometry_derivation"],
                "geometry_method": acceptance["geometry_method"],
                "geometry_scope_class": acceptance["geometry_scope_class"],
                "geometry_precision_scope": acceptance["precision_scope"],
                "horizontal_uncertainty_metres": (
                    "" if uncertainty is None else uncertainty
                ),
                "horizontal_uncertainty_unknown_reason": (
                    "official source does not state positional accuracy"
                    if uncertainty is None
                    else ""
                ),
                "geometry_evidence_id": geometry_evidence_id,
                "last_observed_physical_status": source["status"],
                "status_as_of": source["status_as_of"],
                "status_age_days_at_review": (REVIEW_DATE - status_date).days,
                "status_method": source["status_method"],
                "status_evidence_id": status_evidence_id,
                "verification_posture": _verification_posture(geometry_type),
                "independent_imagery_verification": "false",
                "imagery_review_outcome": _imagery_outcome(
                    project_key, default_imagery_outcome, imagery_by_key
                ),
                "development_type": "unknown",
                "development_type_unknown_reason": (
                    "source evidence does not distinguish greenfield, expansion, or retrofit"
                ),
                "operating_model": source["operating_model"] or "unknown",
                "operating_model_unknown_reason": (
                    "" if source["operating_model"] else "not established by selected evidence"
                ),
                "operating_model_evidence_id": operating_model_evidence_id,
                "workloads_json": _json_bytes(workloads).decode().strip(),
                "workload_unknown_reason": (
                    "" if workloads else "not established by selected evidence"
                ),
                "role_claims_json": _json_bytes(role_claims).decode().strip(),
                "power_observations_json": _json_bytes(power).decode().strip(),
                "power_unknown_reason": (
                    "" if power else "no typed project power observation; not estimated"
                ),
                "annual_energy_observations_json": _json_bytes(energy).decode().strip(),
                "annual_energy_unknown_reason": (
                    "" if energy else "no scoped annual-energy inputs; not estimated"
                ),
                "efficiency_observations_json": _json_bytes(efficiency)
                .decode()
                .strip(),
                "efficiency_unknown_reason": (
                    "" if efficiency else "no scoped PUE or WUE observation"
                ),
                "owner": role_projection["owner"],
                "operator": role_projection["operator"],
                "users": role_projection["users"],
                "tenants": role_projection["tenants"],
                "customers": role_projection["customers"],
                "status_source_url": evidence_by_id[status_evidence_id]["source_url"],
                "geometry_source_url": evidence_by_id[geometry_evidence_id]["source_url"],
            }
        )

    if used_workload_bindings != set(workload_bindings):
        raise VerifiedConstructionCoreError("workload provenance has unused bindings")
    expected_role_bindings = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in provenance["role_bindings"]
    }
    expected_role_exclusions = {
        (row["project_stable_key"], row["role"], row["party"])
        for row in provenance["excluded_source_roles"]
    }
    if (
        used_role_bindings != expected_role_bindings
        or used_role_exclusions != expected_role_exclusions
    ):
        raise VerifiedConstructionCoreError("role provenance has unused decisions")

    by_site: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in projects:
        by_site[project["physical_site_stable_key"]].append(project)
    sites: list[dict[str, Any]] = []
    for site_key in sorted(by_site):
        members = sorted(by_site[site_key], key=lambda row: row["project_id"])
        site_source = entities_by_key[site_key]
        geometry_member = _preferred_site_geometry_member(members)
        sites.append(
            {
                "site_id": members[0]["site_id"],
                "physical_site_stable_key": site_key,
                "name": site_source["name"],
                "country": site_source["country"],
                "country_iso_a2": site_source["country_iso_a2"],
                "latitude": geometry_member["latitude"],
                "longitude": geometry_member["longitude"],
                "geometry_json": geometry_member["geometry_json"],
                "geometry_type": geometry_member["geometry_type"],
                "geometry_source_entity_kinds_json": _json_bytes(
                    sorted({row["geometry_source_entity_kind"] for row in members})
                ).decode().strip(),
                "geometry_derivations_json": _json_bytes(
                    sorted({row["geometry_derivation"] for row in members})
                ).decode().strip(),
                "geometry_methods_json": _json_bytes(
                    sorted({row["geometry_method"] for row in members})
                ).decode().strip(),
                "geometry_scope_classes_json": _json_bytes(
                    sorted({row["geometry_scope_class"] for row in members})
                ).decode().strip(),
                "geometry_precision_scopes_json": _json_bytes(
                    sorted({row["geometry_precision_scope"] for row in members})
                ).decode().strip(),
                "horizontal_uncertainty_metres": geometry_member[
                    "horizontal_uncertainty_metres"
                ],
                "horizontal_uncertainty_unknown_reason": geometry_member[
                    "horizontal_uncertainty_unknown_reason"
                ],
                "geometry_evidence_ids_json": _json_bytes(
                    sorted({row["geometry_evidence_id"] for row in members})
                ).decode().strip(),
                "project_count": len(members),
                "project_ids_json": _json_bytes(
                    [row["project_id"] for row in members]
                ).decode().strip(),
                "project_stable_keys_json": _json_bytes(
                    [row["project_stable_key"] for row in members]
                ).decode().strip(),
                "statuses_json": _json_bytes(
                    sorted({row["last_observed_physical_status"] for row in members})
                ).decode().strip(),
                "oldest_status_as_of": min(row["status_as_of"] for row in members),
                "newest_status_as_of": max(row["status_as_of"] for row in members),
                "verification_posture": geometry_member["verification_posture"],
                "independent_imagery_verification": "false",
                "imagery_review_outcomes_json": _json_bytes(
                    sorted({row["imagery_review_outcome"] for row in members})
                ).decode().strip(),
            }
        )

    selected_evidence: list[dict[str, Any]] = []
    for evidence_id in sorted(evidence_usage):
        source = evidence_by_id[evidence_id]
        usage = evidence_usage[evidence_id]
        selected_evidence.append(
            {
                **source,
                "roles_json": _json_bytes(sorted(usage["roles"])).decode().strip(),
                "project_ids_json": _json_bytes(
                    sorted(usage["project_ids"])
                ).decode().strip(),
            }
        )

    country_counts = Counter(row["country"] for row in sites)
    gates = _final_release_gates(sites, projects)
    selection_report = {
        "format": "datacenter-atlas-verified-construction-core-selection-v3",
        "release_status": "preview",
        "publishable_as_final": all(gate.get("passed", False) for gate in gates.values()),
        "source_release_id": SOURCE_RELEASE_ID,
        "reviewed_at": REVIEW_DATE.isoformat(),
        "maximum_status_age_days": MAX_STATUS_AGE_DAYS,
        "source_pipeline_row_count": len(pipeline),
        "selected_project_count": len(projects),
        "selected_physical_site_count": len(sites),
        "official_boundary_project_count": sum(
            row["geometry_type"] in {"Polygon", "MultiPolygon"} for row in projects
        ),
        "reviewed_site_locator_project_count": sum(
            row["geometry_type"] == "Point" for row in projects
        ),
        "non_selected_source_row_count": len(pipeline) - len(projects),
        "selection_first_failure_counts": dict(sorted(reason_counts.items())),
        "country_counts": dict(sorted(country_counts.items())),
        "final_release_gates": gates,
        "imagery_review_provenance": imagery_records,
        "provenance_decisions": {
            "workload_scope_bindings": provenance["workload_scope_bindings"],
            "role_bindings": provenance["role_bindings"],
            "excluded_source_roles": provenance["excluded_source_roles"],
        },
        "reviewed_overlay_queue": overlays.get("overlays", []),
        "semantic_guardrails": SEMANTIC_GUARDRAILS,
    }
    return {
        "source_manifest": source_manifest,
        "projects": projects,
        "sites": sites,
        "evidence": selected_evidence,
        "selection_report": selection_report,
    }


def _geojson(sites: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "Data Center Atlas Verified Construction Core preview",
        "release_status": "preview",
        "features": [
            {
                "type": "Feature",
                "id": row["site_id"],
                "geometry": json.loads(row["geometry_json"]),
                "properties": {
                    "site_id": row["site_id"],
                    "physical_site_stable_key": row["physical_site_stable_key"],
                    "name": row["name"],
                    "country": row["country"],
                    "project_count": int(row["project_count"]),
                    "geometry_type": row["geometry_type"],
                    "geometry_scope_classes": json.loads(
                        row["geometry_scope_classes_json"]
                    ),
                    "geometry_precision_scopes": json.loads(
                        row["geometry_precision_scopes_json"]
                    ),
                    "horizontal_uncertainty_metres": (
                        None
                        if row["horizontal_uncertainty_metres"] == ""
                        else float(row["horizontal_uncertainty_metres"])
                    ),
                    "statuses": json.loads(row["statuses_json"]),
                    "newest_status_as_of": row["newest_status_as_of"],
                    "verification_posture": row["verification_posture"],
                    "independent_imagery_verification": False,
                },
            }
            for row in sites
        ],
    }


def _map_html(geojson: Mapping[str, Any]) -> bytes:
    data = json.dumps(geojson, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    site_count = len(geojson.get("features", []))
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Verified Construction Core preview</title>
<style>body{{font:14px system-ui;margin:0;color:#17202a}}header{{padding:18px 22px;background:#eef4f7}}main{{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:16px;padding:16px}}svg{{width:100%;height:auto;background:#f8fafb;border:1px solid #ccd6dc}}.grid{{stroke:#dce4e8;stroke-width:1}}circle{{fill:#b6412e;stroke:#fff;stroke-width:1.5;cursor:pointer}}circle:focus{{outline:2px solid #173b57}}table{{border-collapse:collapse;width:100%}}th,td{{padding:6px;border-bottom:1px solid #ddd;text-align:left}}code{{font-size:12px}}.warning{{color:#7b2d1d;font-weight:700}}@media(max-width:800px){{main{{grid-template-columns:1fr}}}}</style></head>
<body><header><h1>Verified Construction Core v0.3 preview</h1><p class="warning">{site_count} physical sites. This is not the 100-site final release and does not claim independent imagery verification.</p></header>
<main><section><svg id="map" viewBox="0 0 1000 500" role="img" aria-label="Global plot of selected sites"></svg></section><aside><h2 id="name">Select a site</h2><div id="detail"></div><h3>Sites</h3><table><tbody id="rows"></tbody></table></aside></main>
<script>const atlas={data};const svg=document.getElementById('map');const ns='http://www.w3.org/2000/svg';
for(let lon=-180;lon<=180;lon+=30){{const l=document.createElementNS(ns,'line');l.setAttribute('x1',(lon+180)/360*1000);l.setAttribute('x2',(lon+180)/360*1000);l.setAttribute('y1',0);l.setAttribute('y2',500);l.setAttribute('class','grid');svg.appendChild(l)}}
for(let lat=-60;lat<=60;lat+=30){{const l=document.createElementNS(ns,'line');l.setAttribute('x1',0);l.setAttribute('x2',1000);l.setAttribute('y1',(90-lat)/180*500);l.setAttribute('y2',(90-lat)/180*500);l.setAttribute('class','grid');svg.appendChild(l)}}
function point(g){{if(g.type==='Point')return g.coordinates;if(g.type==='Polygon'){{const a=g.coordinates[0];return [a.reduce((s,p)=>s+p[0],0)/a.length,a.reduce((s,p)=>s+p[1],0)/a.length]}}const a=g.coordinates[0][0];return [a.reduce((s,p)=>s+p[0],0)/a.length,a.reduce((s,p)=>s+p[1],0)/a.length]}}
function show(f){{document.getElementById('name').textContent=f.properties.name;const d=document.getElementById('detail');d.textContent='';for(const [k,v] of Object.entries(f.properties)){{const p=document.createElement('p');const b=document.createElement('b');b.textContent=k+': ';p.appendChild(b);p.appendChild(document.createTextNode(Array.isArray(v)?v.join(', '):String(v)));d.appendChild(p)}}}}
const tbody=document.getElementById('rows');for(const f of atlas.features){{const [lon,lat]=point(f.geometry);const c=document.createElementNS(ns,'circle');c.setAttribute('cx',(lon+180)/360*1000);c.setAttribute('cy',(90-lat)/180*500);c.setAttribute('r',6);c.setAttribute('tabindex',0);c.setAttribute('aria-label',f.properties.name);c.onclick=()=>show(f);c.onkeydown=e=>{{if(e.key==='Enter')show(f)}};svg.appendChild(c);const tr=document.createElement('tr');const td=document.createElement('td');const a=document.createElement('button');a.textContent=f.properties.name+' — '+f.properties.country;a.onclick=()=>show(f);td.appendChild(a);tr.appendChild(td);tbody.appendChild(tr)}}
</script></body></html>"""
    return document.encode("utf-8")


def _readme(report: Mapping[str, Any]) -> bytes:
    gates = report["final_release_gates"]
    boundary_count = report["official_boundary_project_count"]
    locator_count = report["reviewed_site_locator_project_count"]
    text = f"""# Verified Construction Core v0.3 preview

This tracked preview contains **{report['selected_physical_site_count']} physical sites** and
**{report['selected_project_count']} linked projects** selected from `{SOURCE_RELEASE_ID}`.
Every selected project has a physical-status observation no more than {MAX_STATUS_AGE_DAYS} days
old at the {REVIEW_DATE.isoformat()} review date. {boundary_count} project rows carry official
parcel or surveyed boundary geometry; this describes the geometry attached to the row, not a claim
that construction occupies the entire parcel. The other {locator_count} use explicitly labelled
site-, parcel-, address-, or first-party campus-location points with their precision limits preserved.
Locality centroids and model-only lifecycle states fail the selector.

This is **not** the final Verified Construction Core v1. It does not change the historical Atlas
`construction_verified=false` field, infer a continuously current state, claim independent imagery
verification, or claim completeness. The final release remains blocked at
{gates['site_count']['actual']}/{gates['site_count']['required']} sites,
{gates['country_count']['actual']}/{gates['country_count']['required_minimum']} countries, and
{gates['non_us_site_count']['actual']}/{gates['non_us_site_count']['required_minimum']} non-US sites.

Files:

- `sites.csv` and `projects.csv`: the reviewed physical-site/project cohort.
- `sites.geojson` and `map.html`: matching clean-clone-readable map products.
- `evidence.csv`: status, geometry, operating-model, workload, and typed-metric evidence.
- `schema.json`: machine-readable field, relationship, GeoJSON, and map contract.
- `selection-report.json`: accounting for every source pipeline row and every final gate.
- `manifest.json` and `manifest.sha256`: byte and SHA-256 bindings.

Missing power, annual energy, operating model, workload, and development type remain explicit
unknowns; the builder never converts missing values to zero. Existing satellite reviews remain
non-claiming analyst evidence. The selection report binds each non-default imagery outcome to its
exact tracked review source and preserves locally unsealed identity lineage and unadjudicated
conflicts explicitly. Two exact Canadian geometry overlays were reviewed but excluded: one recent
scene was unusable and one usable comparison showed no filtered recent-change component.

Every workload observation now carries a validator-bound `deployment_scope`; all three current
observations are `intended`, never operational. `role_claims_json` binds each published role to an
evidence ID and relationship scope. Five intended-operator claims pass that gate. Four prior
CDC/AST owner or operator strings lacked role-specific evidence, so v0.3 clears them and preserves
the rejected claims and reasons in the provenance contract rather than laundering status evidence
into role evidence.

The preview validates from a public clean clone. Rebuilding it still requires the locally hydrated
v97 payload, so clean-clone rebuildability is an explicit failed final-release gate rather than an
implied capability.
"""
    return text.encode("utf-8")


def _field_contract(name: str) -> dict[str, Any]:
    json_array_fields = {
        "workloads_json",
        "role_claims_json",
        "power_observations_json",
        "annual_energy_observations_json",
        "efficiency_observations_json",
        "geometry_source_entity_kinds_json",
        "geometry_derivations_json",
        "geometry_methods_json",
        "geometry_scope_classes_json",
        "geometry_precision_scopes_json",
        "geometry_evidence_ids_json",
        "project_ids_json",
        "project_stable_keys_json",
        "statuses_json",
        "imagery_review_outcomes_json",
        "roles_json",
    }
    logical_type = "string"
    if name in json_array_fields:
        logical_type = "json_array"
    elif name == "geometry_json":
        logical_type = "geojson_geometry"
    elif name in {"latitude", "longitude", "horizontal_uncertainty_metres"}:
        logical_type = "number"
    elif name in {"project_count", "status_age_days_at_review"}:
        logical_type = "integer"
    elif name == "independent_imagery_verification":
        logical_type = "boolean"
    elif name in {"status_as_of", "oldest_status_as_of", "newest_status_as_of"}:
        logical_type = "date"
    elif name in {"published_at", "retrieved_at"}:
        logical_type = "date_or_datetime"
    elif name in {"status_source_url", "geometry_source_url", "source_url"}:
        logical_type = "uri"
    elif name == "content_hash":
        logical_type = "sha256"
    allows_empty = name in {
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
        "operating_model_unknown_reason",
        "operating_model_evidence_id",
        "workload_unknown_reason",
        "power_unknown_reason",
        "annual_energy_unknown_reason",
        "efficiency_unknown_reason",
        "owner",
        "operator",
        "users",
        "tenants",
        "customers",
        "license",
        "attribution",
        "published_at",
    }
    contract: dict[str, Any] = {
        "name": name,
        "logical_type": logical_type,
        "allows_empty_string": allows_empty,
    }
    enumerations = {
        "geometry_type": ["Point", "Polygon", "MultiPolygon"],
        "geometry_source_entity_kind": ["project", "campus"],
        "geometry_derivation": ["direct_geometry", "coordinates_to_point"],
        "last_observed_physical_status": sorted(PHYSICAL_STATUSES),
        "status_method": sorted(AUTHORITATIVE_STATUS_METHODS),
        "independent_imagery_verification": [False],
    }
    if name in enumerations:
        contract["allowed_values"] = enumerations[name]
    return contract


def _schema() -> dict[str, Any]:
    return {
        "format": "datacenter-atlas-verified-construction-core-schema-v3",
        "preview_id": PREVIEW_ID,
        "csv_encoding": "UTF-8",
        "csv_dialect": {
            "delimiter": ",",
            "quote_character": '"',
            "line_terminator": "LF",
            "header": True,
        },
        "tables": {
            "projects.csv": {
                "fields": [_field_contract(name) for name in PROJECT_FIELDS],
                "primary_key": ["project_id"],
            },
            "sites.csv": {
                "fields": [_field_contract(name) for name in SITE_FIELDS],
                "primary_key": ["site_id"],
            },
            "evidence.csv": {
                "fields": [_field_contract(name) for name in EVIDENCE_FIELDS],
                "primary_key": ["evidence_id"],
            },
        },
        "foreign_keys": [
            {
                "from": ["projects.csv", "site_id"],
                "to": ["sites.csv", "site_id"],
            },
            {
                "from": ["projects.csv", "status_evidence_id"],
                "to": ["evidence.csv", "evidence_id"],
            },
            {
                "from": ["projects.csv", "geometry_evidence_id"],
                "to": ["evidence.csv", "evidence_id"],
            },
            {
                "from": ["projects.csv", "operating_model_evidence_id"],
                "to": ["evidence.csv", "evidence_id"],
                "allows_empty_string": True,
            },
        ],
        "json_embedded_evidence_fields": [
            ["projects.csv", "workloads_json", "evidence_id"],
            ["projects.csv", "role_claims_json", "evidence_id"],
            ["projects.csv", "power_observations_json", "evidence_id"],
            ["projects.csv", "annual_energy_observations_json", "evidence_id"],
            ["projects.csv", "efficiency_observations_json", "evidence_id"],
        ],
        "embedded_array_items": {
            "projects.csv:power_observations_json": {
                "item_type": "typed_metric_observation",
                "allowed_metrics": sorted(POWER_METRICS),
            },
            "projects.csv:annual_energy_observations_json": {
                "item_type": "typed_metric_observation",
                "allowed_metrics": sorted(ENERGY_METRICS),
            },
            "projects.csv:efficiency_observations_json": {
                "item_type": "typed_metric_observation",
                "allowed_metrics": sorted(EFFICIENCY_METRICS),
            },
            "projects.csv:workloads_json": {
                "item_type": "workload_observation"
            },
            "projects.csv:role_claims_json": {
                "item_type": "role_claim"
            },
        },
        "embedded_types": {
            "typed_metric_observation": {
                "required_fields": [
                    "as_of_date",
                    "base",
                    "confidence",
                    "evidence_id",
                    "high",
                    "low",
                    "method",
                    "metric",
                    "notes",
                    "stage",
                    "target_date",
                    "unit",
                ],
                "unit_by_metric": METRIC_UNITS,
                "allowed_methods": sorted(ESTIMATE_METHODS),
                "allowed_stages": sorted(CAPACITY_STAGES),
                "interval_constraint": "0 <= low <= base <= high",
                "confidence_constraint": "0 <= confidence <= 1",
                "target_date_allows_null": True,
            },
            "workload_observation": {
                "required_fields": [
                    "as_of_date",
                    "confidence",
                    "deployment_scope",
                    "evidence_id",
                    "method",
                    "workload",
                ],
                "allowed_deployment_scopes": [
                    "intended",
                    "operational",
                    "unknown",
                ],
                "confidence_constraint": "0 <= confidence <= 1",
            },
            "role_claim": {
                "required_fields": [
                    "evidence_id",
                    "party",
                    "relationship_scope",
                    "role",
                ],
                "allowed_relationship_scopes": [
                    "current",
                    "intended",
                    "unknown",
                ],
                "allowed_roles": sorted(ROLE_COLUMNS),
            },
        },
        "geojson": {
            "path": "sites.geojson",
            "feature_id_equals": ["sites.csv", "site_id"],
            "geometry_equals": ["sites.csv", "geometry_json"],
            "allowed_geometry_types": ["Point", "Polygon", "MultiPolygon"],
        },
        "map": {"path": "map.html", "derived_from": "sites.geojson"},
    }


def _attribution(
    evidence: Sequence[Mapping[str, Any]],
    overlays: Sequence[Mapping[str, Any]],
    imagery_records: Sequence[Mapping[str, Any]],
) -> bytes:
    rows = {
        (row["publisher"], row["license"], row["source_url"])
        for row in evidence
    }
    if any(
        str(row.get("geometry_stable_key", "")).startswith("osm:")
        for row in overlays
    ):
        rows.add(
            (
                "© OpenStreetMap contributors",
                "ODbL-1.0",
                "https://www.openstreetmap.org/copyright",
            )
        )
    lines = [
        "Data Center Atlas Verified Construction Core v0.3 preview",
        "",
        "Compact derived facts only; third-party terms remain controlling.",
        "",
    ]
    lines.extend(
        f"- {publisher} | {license_name} | {url}"
        for publisher, license_name, url in sorted(rows)
    )
    if imagery_records:
        lines.extend(
            [
                "",
                "Imagery review attribution:",
                "Contains modified Copernicus Sentinel data 2024 and 2026.",
                "Dataset: Copernicus Sentinel-2 Level-2A, accessed through Element 84 Earth Search.",
                "Sentinel Data Legal Notice: https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
            ]
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_preview(output_dir: Path = PREVIEW_DIR) -> dict[str, Any]:
    """Build the preview atomically and refuse to overwrite an existing path."""
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise VerifiedConstructionCoreError(f"refusing to overwrite {output_dir}")
    data = _build_rows()
    sites = data["sites"]
    projects = data["projects"]
    evidence = data["evidence"]
    report = data["selection_report"]
    geojson = _geojson(sites)
    payloads = {
        "ATTRIBUTION.txt": _attribution(
            evidence,
            report["reviewed_overlay_queue"],
            report["imagery_review_provenance"],
        ),
        "README.md": _readme(report),
        "evidence.csv": _csv_bytes(evidence, EVIDENCE_FIELDS),
        "map.html": _map_html(geojson),
        "projects.csv": _csv_bytes(projects, PROJECT_FIELDS),
        "schema.json": _json_bytes(_schema()),
        "selection-report.json": _json_bytes(report),
        "sites.csv": _csv_bytes(sites, SITE_FIELDS),
        "sites.geojson": _json_bytes(geojson),
    }
    manifest = {
        "format": "datacenter-atlas-verified-construction-core-preview-v3",
        "preview_id": PREVIEW_ID,
        "release_status": "preview",
        "publishable_as_final": report["publishable_as_final"],
        "source_release_id": SOURCE_RELEASE_ID,
        "source_release_manifest_path": str(
            (SOURCE_RELEASE / "manifest.json").relative_to(ROOT)
        ),
        "source_release_manifest_sha256": _sha256_file(SOURCE_RELEASE / "manifest.json"),
        "definition_paths": {
            "imagery_reviews": str(IMAGERY_REVIEW_DEFINITION.relative_to(ROOT)),
            "provenance": str(PROVENANCE_DEFINITION.relative_to(ROOT)),
            "reviewed_overlays": str(OVERLAY_DEFINITION.relative_to(ROOT)),
            "reviewed_sites": str(REVIEW_DEFINITION.relative_to(ROOT)),
        },
        "review_definition_sha256": _sha256_file(REVIEW_DEFINITION),
        "imagery_review_definition_sha256": _sha256_file(
            IMAGERY_REVIEW_DEFINITION
        ),
        "provenance_definition_sha256": _sha256_file(PROVENANCE_DEFINITION),
        "overlay_definition_sha256": _sha256_file(OVERLAY_DEFINITION),
        "portable_source_inputs": _portable_source_inputs(),
        "reviewed_at": REVIEW_DATE.isoformat(),
        "counts": {
            "physical_sites": len(sites),
            "projects": len(projects),
            "evidence": len(evidence),
            "countries": len({row["country"] for row in sites}),
            "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
            "official_boundary_projects": sum(
                row["geometry_type"] in {"Polygon", "MultiPolygon"}
                for row in projects
            ),
            "reviewed_site_locator_projects": sum(
                row["geometry_type"] == "Point" for row in projects
            ),
        },
        "files": {
            name: {"bytes": len(payload), "sha256": _sha256_bytes(payload)}
            for name, payload in sorted(payloads.items())
        },
    }
    manifest_bytes = _json_bytes(manifest)
    payloads["manifest.json"] = manifest_bytes
    payloads["manifest.sha256"] = (
        f"{_sha256_bytes(manifest_bytes)}  manifest.json\n".encode()
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, payload in payloads.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(payload)
        os.replace(stage, output_dir)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_preview(output_dir)
    return manifest


def validate_frozen_v01(
    path: Path = LEGACY_PREVIEW_V01_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.1 inventory without applying v0.2 semantics."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.1 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V01_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.1 manifest hash differs")
    manifest = _load_json(manifest_path)
    if (
        manifest.get("format")
        != "datacenter-atlas-verified-construction-core-preview-v1"
        or manifest.get("preview_id") != "2026-08-19-preview-v0.1"
        or manifest.get("reviewed_at") != "2026-08-19"
    ):
        raise VerifiedConstructionCoreError("frozen v0.1 identity differs")
    legacy_definition = (
        ROOT / "definitions" / "verified-construction-core-v0.1-reviewed-sites.json"
    )
    if not legacy_definition.is_file() or manifest.get(
        "review_definition_sha256"
    ) != _sha256_file(legacy_definition):
        raise VerifiedConstructionCoreError("frozen v0.1 review definition differs")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.1 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.1 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.1 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V01_MANIFEST_SHA256}  manifest.json\n"
    if (path / "manifest.sha256").read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.1 checksum differs")
    return manifest


def validate_frozen_v02(
    path: Path = LEGACY_PREVIEW_V02_DIR,
) -> dict[str, Any]:
    """Validate the byte-frozen v0.2 inventory using only immutable pins."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(
            f"frozen v0.2 preview is not a regular directory: {path}"
        )
    manifest_path = path / "manifest.json"
    if _sha256_file(manifest_path) != LEGACY_PREVIEW_V02_MANIFEST_SHA256:
        raise VerifiedConstructionCoreError("frozen v0.2 manifest hash differs")
    manifest = _load_json(manifest_path)
    expected_pins = {
        "format": "datacenter-atlas-verified-construction-core-preview-v2",
        "preview_id": "2026-08-20-preview-v0.2",
        "reviewed_at": "2026-08-20",
        "source_release_id": "2026-07-22-open-seed-v97",
        "source_release_manifest_sha256": (
            "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd"
        ),
        "review_definition_sha256": (
            "13f4d6e82c9057b1dd95319e19e30c2bae0ac0f1848d6e6dee2bbc10b5dde1d0"
        ),
        "imagery_review_definition_sha256": (
            "0516a3281d0a3a1734a4bacb8f8d9e5419d0ae8dc22df36c098c5375f84ee613"
        ),
        "overlay_definition_sha256": (
            "57540f73c5cac475bd8e9e64fc5d8eb2188158ef977b477a0c0e8d7158caf1b7"
        ),
    }
    if any(manifest.get(field) != value for field, value in expected_pins.items()):
        raise VerifiedConstructionCoreError("frozen v0.2 identity differs")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("frozen v0.2 files map is absent")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    if {item.name for item in path.iterdir()} != expected_names:
        raise VerifiedConstructionCoreError("frozen v0.2 inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or candidate.stat().st_size != metadata.get("bytes")
            or _sha256_file(candidate) != metadata.get("sha256")
        ):
            raise VerifiedConstructionCoreError(
                f"frozen v0.2 member differs: {name}"
            )
    expected_sum = f"{LEGACY_PREVIEW_V02_MANIFEST_SHA256}  manifest.json\n"
    if (path / "manifest.sha256").read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("frozen v0.2 checksum differs")
    return manifest


def validate_preview(path: Path = PREVIEW_DIR) -> dict[str, Any]:
    """Dispatch frozen previews by manifest identity and validate the current one."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(f"preview is not a regular directory: {path}")
    manifest = _load_json(path / "manifest.json")
    preview_id = manifest.get("preview_id")
    if preview_id == "2026-08-19-preview-v0.1":
        return validate_frozen_v01(path)
    if preview_id == "2026-08-20-preview-v0.2":
        return validate_frozen_v02(path)
    if preview_id != PREVIEW_ID:
        raise VerifiedConstructionCoreError("preview id differs")
    return _validate_current_preview(path)


def _validate_current_preview(path: Path) -> dict[str, Any]:
    """Validate the tracked preview without requiring the ignored source corpus."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise VerifiedConstructionCoreError(f"preview is not a regular directory: {path}")
    _validate_v03_definition_pins()
    manifest_path = path / "manifest.json"
    manifest = _load_json(manifest_path)
    expected_manifest_fields = {
        "format",
        "preview_id",
        "release_status",
        "publishable_as_final",
        "source_release_id",
        "source_release_manifest_path",
        "source_release_manifest_sha256",
        "definition_paths",
        "review_definition_sha256",
        "imagery_review_definition_sha256",
        "provenance_definition_sha256",
        "overlay_definition_sha256",
        "portable_source_inputs",
        "reviewed_at",
        "counts",
        "files",
    }
    if set(manifest) != expected_manifest_fields:
        raise VerifiedConstructionCoreError("preview manifest fields differ")
    if manifest.get("format") != "datacenter-atlas-verified-construction-core-preview-v3":
        raise VerifiedConstructionCoreError("preview format differs")
    if manifest.get("preview_id") != PREVIEW_ID:
        raise VerifiedConstructionCoreError("preview id differs")
    if manifest.get("release_status") != "preview" or manifest.get(
        "publishable_as_final"
    ) is not False:
        raise VerifiedConstructionCoreError("preview promotion posture differs")
    if manifest.get("source_release_id") != SOURCE_RELEASE_ID:
        raise VerifiedConstructionCoreError("preview source release differs")
    if manifest.get("reviewed_at") != REVIEW_DATE.isoformat():
        raise VerifiedConstructionCoreError("preview review date differs")
    for field, _, expected_sha256 in _v03_definition_pins():
        if manifest.get(field) != expected_sha256:
            raise VerifiedConstructionCoreError(f"preview {field} differs")
    expected_definition_paths = {
        "imagery_reviews": str(IMAGERY_REVIEW_DEFINITION.relative_to(ROOT)),
        "provenance": str(PROVENANCE_DEFINITION.relative_to(ROOT)),
        "reviewed_overlays": str(OVERLAY_DEFINITION.relative_to(ROOT)),
        "reviewed_sites": str(REVIEW_DEFINITION.relative_to(ROOT)),
    }
    if manifest.get("definition_paths") != expected_definition_paths:
        raise VerifiedConstructionCoreError("preview definition paths differ")
    source_manifest_path = SOURCE_RELEASE / "manifest.json"
    if (
        manifest.get("source_release_manifest_path")
        != str(source_manifest_path.relative_to(ROOT))
        or not source_manifest_path.is_file()
        or manifest.get(
        "source_release_manifest_sha256"
        )
        != _sha256_file(source_manifest_path)
    ):
        raise VerifiedConstructionCoreError("preview source manifest hash differs")
    if manifest.get("portable_source_inputs") != _portable_source_inputs():
        raise VerifiedConstructionCoreError("preview portable source inputs differ")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise VerifiedConstructionCoreError("preview files map is absent")
    required_payloads = {
        "ATTRIBUTION.txt",
        "README.md",
        "evidence.csv",
        "map.html",
        "projects.csv",
        "schema.json",
        "selection-report.json",
        "sites.csv",
        "sites.geojson",
    }
    if set(files) != required_payloads:
        raise VerifiedConstructionCoreError("preview payload inventory differs")
    expected_names = set(files) | {"manifest.json", "manifest.sha256"}
    actual_names = {item.name for item in path.iterdir()}
    if actual_names != expected_names:
        raise VerifiedConstructionCoreError("preview closed inventory differs")
    for name, metadata in files.items():
        candidate = path / name
        if candidate.is_symlink() or not candidate.is_file():
            raise VerifiedConstructionCoreError(f"preview member differs: {name}")
        if candidate.stat().st_size != metadata.get("bytes"):
            raise VerifiedConstructionCoreError(f"preview member byte count differs: {name}")
        if _sha256_file(candidate) != metadata.get("sha256"):
            raise VerifiedConstructionCoreError(f"preview member hash differs: {name}")
    expected_sum = f"{_sha256_file(manifest_path)}  manifest.json\n"
    if (path / "manifest.sha256").read_text(encoding="utf-8") != expected_sum:
        raise VerifiedConstructionCoreError("preview manifest checksum differs")

    sites = _load_csv(path / "sites.csv", SITE_FIELDS)
    projects = _load_csv(path / "projects.csv", PROJECT_FIELDS)
    evidence = _load_csv(path / "evidence.csv", EVIDENCE_FIELDS)
    schema = _load_json(path / "schema.json")
    geojson = _load_json(path / "sites.geojson")
    report = _load_json(path / "selection-report.json")
    if schema != _schema():
        raise VerifiedConstructionCoreError("preview machine-readable schema differs")
    counts = manifest.get("counts", {})
    if not isinstance(counts, dict) or set(counts) != {
        "physical_sites",
        "projects",
        "evidence",
        "countries",
        "non_us_sites",
        "official_boundary_projects",
        "reviewed_site_locator_projects",
    }:
        raise VerifiedConstructionCoreError("preview count fields differ")
    if counts.get("physical_sites") != len(sites) or counts.get("projects") != len(
        projects
    ) or counts.get("evidence") != len(evidence):
        raise VerifiedConstructionCoreError("preview manifest counts differ")
    site_ids = {row["site_id"] for row in sites}
    project_ids = {row["project_id"] for row in projects}
    evidence_ids = {row["evidence_id"] for row in evidence}
    if len(site_ids) != len(sites) or len(project_ids) != len(projects):
        raise VerifiedConstructionCoreError("preview identifiers are not unique")
    if any(row["site_id"] not in site_ids for row in projects):
        raise VerifiedConstructionCoreError("preview project references absent site")
    if {row["site_id"] for row in projects} != site_ids:
        raise VerifiedConstructionCoreError("preview contains a site without a project")
    site_by_id = {row["site_id"]: row for row in sites}
    reviewed_acceptances = _reviewed_acceptances()
    _, reviewed_delta = _reviewed_acceptances_from(REVIEW_DEFINITION)
    reviewed_delta_by_key = {
        row["project_stable_key"]: row for row in reviewed_delta
    }
    reviewed_by_key = {
        row["project_stable_key"]: row for row in reviewed_acceptances
    }
    reviewed_keys = set(reviewed_by_key)
    if {row["project_stable_key"] for row in projects} != reviewed_keys:
        raise VerifiedConstructionCoreError("preview reviewed-project cohort differs")
    default_imagery_outcome, imagery_records = _imagery_contract()
    imagery_by_key = {row["project_stable_key"]: row for row in imagery_records}
    provenance = _provenance_contract()
    workload_binding_by_key = {
        (
            row["project_stable_key"],
            row["evidence_id"],
            row["workload"],
        ): row
        for row in provenance["workload_scope_bindings"]
    }
    role_bindings_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in provenance["role_bindings"]:
        role_bindings_by_project[binding["project_stable_key"]].append(binding)
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    if len(evidence_by_id) != len(evidence):
        raise VerifiedConstructionCoreError("preview evidence identifiers are not unique")
    _validate_v03_inheritance(projects, sites, evidence)
    for row in projects:
        acceptance = reviewed_by_key[row["project_stable_key"]]
        if row["project_id"] != atlas_stable_id(
            "entity", row["project_stable_key"], "project"
        ):
            raise VerifiedConstructionCoreError("preview project id differs")
        expected_imagery_outcome = _imagery_outcome(
            row["project_stable_key"], default_imagery_outcome, imagery_by_key
        )
        if row["project_stable_key"] in reviewed_delta_by_key:
            _validate_v03_delta_project(
                row,
                reviewed_delta_by_key[row["project_stable_key"]],
                evidence_by_id,
                expected_imagery_outcome,
            )
        if (
            row["geometry_source_entity_kind"] != acceptance["geometry_entity"]
            or row["geometry_derivation"] != acceptance["geometry_derivation"]
            or row["geometry_method"] != acceptance["geometry_method"]
            or row["geometry_scope_class"] != acceptance["geometry_scope_class"]
            or row["geometry_precision_scope"] != acceptance["precision_scope"]
            or row["imagery_review_outcome"] != expected_imagery_outcome
        ):
            raise VerifiedConstructionCoreError(
                "preview reviewed geometry or imagery contract differs"
            )
        expected_uncertainty = acceptance["horizontal_uncertainty_metres"]
        if expected_uncertainty is None:
            if row["horizontal_uncertainty_metres"] or row[
                "horizontal_uncertainty_unknown_reason"
            ] != "official source does not state positional accuracy":
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry precision contract differs"
                )
        else:
            try:
                actual_uncertainty = float(row["horizontal_uncertainty_metres"])
            except ValueError as error:
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry precision contract differs"
                ) from error
            if (
                actual_uncertainty != float(expected_uncertainty)
                or row["horizontal_uncertainty_unknown_reason"]
            ):
                raise VerifiedConstructionCoreError(
                    "preview reviewed geometry precision contract differs"
                )
        imagery_record = imagery_by_key.get(row["project_stable_key"])
        if imagery_record is not None and imagery_record["project_entity_id"] != row[
            "project_id"
        ]:
            raise VerifiedConstructionCoreError("preview imagery identity differs")
        if row["status_evidence_id"] not in evidence_ids or row[
            "geometry_evidence_id"
        ] not in evidence_ids:
            raise VerifiedConstructionCoreError("preview evidence reference is absent")
        age = (REVIEW_DATE - _calendar_date(row["status_as_of"], "status_as_of")).days
        if int(row["status_age_days_at_review"]) != age:
            raise VerifiedConstructionCoreError("preview status age differs")
        if age < 0 or age > MAX_STATUS_AGE_DAYS:
            raise VerifiedConstructionCoreError("preview status freshness differs")
        if row["last_observed_physical_status"] not in PHYSICAL_STATUSES or row[
            "status_method"
        ] not in AUTHORITATIVE_STATUS_METHODS:
            raise VerifiedConstructionCoreError("preview physical-status gate differs")
        if row["independent_imagery_verification"] != "false":
            raise VerifiedConstructionCoreError("preview imagery claim differs")
        geometry = _parse_json_field(row["geometry_json"], "geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != row[
            "geometry_type"
        ] or row["geometry_type"] not in {"Point", "Polygon", "MultiPolygon"}:
            raise VerifiedConstructionCoreError("preview geometry type differs")
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
        except ValueError as error:
            raise VerifiedConstructionCoreError(
                "preview geometry representative coordinates differ"
            ) from error
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
            or (
                geometry["type"] == "Point"
                and geometry.get("coordinates") != [longitude, latitude]
            )
        ):
            raise VerifiedConstructionCoreError(
                "preview geometry representative coordinates differ"
            )
        if row["verification_posture"] != _verification_posture(row["geometry_type"]):
            raise VerifiedConstructionCoreError("preview verification posture differs")
        if row["site_id"] != _stable_id(
            "vcc-site", row["physical_site_stable_key"]
        ):
            raise VerifiedConstructionCoreError("preview physical-site id differs")
        site = site_by_id[row["site_id"]]
        if site["physical_site_stable_key"] != row["physical_site_stable_key"]:
            raise VerifiedConstructionCoreError("preview project/site identity differs")
        if row["horizontal_uncertainty_metres"]:
            if row["horizontal_uncertainty_unknown_reason"]:
                raise VerifiedConstructionCoreError("preview geometry precision conflicts")
            if float(row["horizontal_uncertainty_metres"]) < 0:
                raise VerifiedConstructionCoreError("preview geometry precision differs")
        elif not row["horizontal_uncertainty_unknown_reason"]:
            raise VerifiedConstructionCoreError("preview geometry precision reason is absent")
        if row["operating_model"] == "unknown":
            if not row["operating_model_unknown_reason"] or row[
                "operating_model_evidence_id"
            ]:
                raise VerifiedConstructionCoreError(
                    "preview operating-model unknown posture differs"
                )
        else:
            operating_evidence_id = row["operating_model_evidence_id"]
            if row["operating_model_unknown_reason"] or operating_evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    "preview operating-model evidence differs"
                )
            operating_evidence = evidence_by_id[operating_evidence_id]
            if "operating_model" not in _parse_json_field(
                operating_evidence["roles_json"], "roles"
            ) or row["project_id"] not in _parse_json_field(
                operating_evidence["project_ids_json"], "project_ids"
            ):
                raise VerifiedConstructionCoreError(
                    "preview operating-model evidence usage differs"
                )
        for evidence_id, role in (
            (row["status_evidence_id"], "physical_status"),
            (row["geometry_evidence_id"], "geometry"),
        ):
            evidence_row = evidence_by_id[evidence_id]
            source_url_field = (
                "status_source_url"
                if role == "physical_status"
                else "geometry_source_url"
            )
            if row[source_url_field] != evidence_row["source_url"]:
                raise VerifiedConstructionCoreError(
                    "preview evidence source URL differs"
                )
            if role not in _parse_json_field(evidence_row["roles_json"], "roles") or row[
                "project_id"
            ] not in _parse_json_field(
                evidence_row["project_ids_json"], "project_ids"
            ):
                raise VerifiedConstructionCoreError("preview evidence usage differs")
        typed_observations: list[dict[str, Any]] = []
        for field, reason_field, allowed_metrics in (
            ("power_observations_json", "power_unknown_reason", POWER_METRICS),
            (
                "annual_energy_observations_json",
                "annual_energy_unknown_reason",
                ENERGY_METRICS,
            ),
            (
                "efficiency_observations_json",
                "efficiency_unknown_reason",
                EFFICIENCY_METRICS,
            ),
        ):
            observations = _parse_json_field(row[field], field)
            if not isinstance(observations, list) or any(
                not isinstance(observation, dict)
                for observation in observations
            ):
                raise VerifiedConstructionCoreError(
                    "preview typed-metric category differs"
                )
            for observation in observations:
                _validate_typed_observation(observation, allowed_metrics)
            if bool(observations) == bool(row[reason_field]):
                raise VerifiedConstructionCoreError(
                    "preview typed-metric unknown posture differs"
                )
            typed_observations.extend(observations)
        for observation in typed_observations:
            evidence_id = observation.get("evidence_id")
            role = f"typed_metric:{observation.get('metric')}"
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    "preview typed-metric evidence usage differs"
                )
            metric_evidence = evidence_by_id[evidence_id]
            if role not in _parse_json_field(
                metric_evidence["roles_json"], "roles"
            ) or row["project_id"] not in _parse_json_field(
                metric_evidence["project_ids_json"], "project_ids"
            ):
                raise VerifiedConstructionCoreError(
                    "preview typed-metric evidence usage differs"
                )
        workloads = _parse_json_field(row["workloads_json"], "workloads")
        if not isinstance(workloads, list):
            raise VerifiedConstructionCoreError("preview workload list differs")
        for workload in workloads:
            _validate_workload_observation(workload)
            evidence_id = workload.get("evidence_id")
            binding = workload_binding_by_key.get(
                (row["project_stable_key"], evidence_id, workload.get("workload"))
            )
            if binding is None or any(
                workload[field] != binding[field]
                for field in SOURCE_WORKLOAD_FIELDS | {"deployment_scope"}
            ):
                raise VerifiedConstructionCoreError(
                    "preview workload provenance differs"
                )
            if evidence_id not in evidence_by_id:
                raise VerifiedConstructionCoreError(
                    "preview workload evidence usage differs"
                )
            workload_evidence = evidence_by_id[evidence_id]
            workload_roles = _parse_json_field(workload_evidence["roles_json"], "roles")
            if (
                "workload" not in workload_roles
                or f"workload_scope:{workload['deployment_scope']}" not in workload_roles
                or row["project_id"] not in _parse_json_field(
                workload_evidence["project_ids_json"], "project_ids"
                )
            ):
                raise VerifiedConstructionCoreError(
                    "preview workload evidence usage differs"
                )
        role_claims = _parse_json_field(row["role_claims_json"], "role claims")
        if not isinstance(role_claims, list):
            raise VerifiedConstructionCoreError("preview role claims differ")
        for claim in role_claims:
            _validate_role_claim(claim)
        if role_claims != sorted(
            role_claims,
            key=lambda claim: (claim["role"], claim["party"], claim["evidence_id"]),
        ) or len({(claim["role"], claim["party"]) for claim in role_claims}) != len(
            role_claims
        ):
            raise VerifiedConstructionCoreError("preview role claim ordering differs")
        expected_role_claims = sorted(
            [
                {
                    "evidence_id": binding["evidence_id"],
                    "party": binding["party"],
                    "relationship_scope": binding["relationship_scope"],
                    "role": binding["role"],
                }
                for binding in role_bindings_by_project.get(
                    row["project_stable_key"], []
                )
            ],
            key=lambda claim: (claim["role"], claim["party"], claim["evidence_id"]),
        )
        if role_claims != expected_role_claims:
            raise VerifiedConstructionCoreError("preview role provenance differs")
        projected: dict[str, list[str]] = {role: [] for role in ROLE_COLUMNS}
        for claim in role_claims:
            projected[claim["role"]].append(claim["party"])
            role_evidence = evidence_by_id.get(claim["evidence_id"])
            if role_evidence is None or (
                f"role:{claim['role']}"
                not in _parse_json_field(role_evidence["roles_json"], "roles")
                or row["project_id"]
                not in _parse_json_field(
                    role_evidence["project_ids_json"], "project_ids"
                )
            ):
                raise VerifiedConstructionCoreError(
                    "preview role evidence usage differs"
                )
        for role, column in ROLE_COLUMNS.items():
            if row[column] != "; ".join(sorted(projected[role])):
                raise VerifiedConstructionCoreError(
                    "preview role projection differs"
                )
    for evidence_id, expected in provenance["evidence_rows"].items():
        actual = evidence_by_id.get(evidence_id)
        if actual is None or any(
            actual.get(field) != value
            for field, value in expected.items()
            if field not in {"roles_json", "project_ids_json"}
        ):
            raise VerifiedConstructionCoreError(
                "preview provenance evidence content differs"
            )
    expected_usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "project_ids": set()}
    )
    for project in projects:
        project_id = project["project_id"]
        for evidence_id, role in (
            (project["status_evidence_id"], "physical_status"),
            (project["geometry_evidence_id"], "geometry"),
        ):
            expected_usage[evidence_id]["roles"].add(role)
            expected_usage[evidence_id]["project_ids"].add(project_id)
        if project["operating_model_evidence_id"]:
            evidence_id = project["operating_model_evidence_id"]
            expected_usage[evidence_id]["roles"].add("operating_model")
            expected_usage[evidence_id]["project_ids"].add(project_id)
        for field in (
            "power_observations_json",
            "annual_energy_observations_json",
            "efficiency_observations_json",
        ):
            for observation in _parse_json_field(project[field], field):
                evidence_id = observation["evidence_id"]
                expected_usage[evidence_id]["roles"].add(
                    f"typed_metric:{observation['metric']}"
                )
                expected_usage[evidence_id]["project_ids"].add(project_id)
        for workload in _parse_json_field(project["workloads_json"], "workloads"):
            evidence_id = workload["evidence_id"]
            expected_usage[evidence_id]["roles"].update(
                {"workload", f"workload_scope:{workload['deployment_scope']}"}
            )
            expected_usage[evidence_id]["project_ids"].add(project_id)
        for claim in _parse_json_field(project["role_claims_json"], "role claims"):
            evidence_id = claim["evidence_id"]
            expected_usage[evidence_id]["roles"].add(f"role:{claim['role']}")
            expected_usage[evidence_id]["project_ids"].add(project_id)
    if set(expected_usage) != evidence_ids:
        raise VerifiedConstructionCoreError("preview evidence closure differs")
    for evidence_id, usage in expected_usage.items():
        evidence_row = evidence_by_id[evidence_id]
        if (
            _parse_json_field(evidence_row["roles_json"], "roles")
            != sorted(usage["roles"])
            or _parse_json_field(
                evidence_row["project_ids_json"], "project_ids"
            )
            != sorted(usage["project_ids"])
        ):
            raise VerifiedConstructionCoreError("preview evidence usage closure differs")
    delta_site_names: dict[str, str] = {}
    for acceptance in reviewed_delta:
        source = _load_json(
            _repository_input(
                acceptance["source_input_path"],
                acceptance["source_input_sha256"],
                "current reviewed-site",
            )
        )
        campus = source.get("campus")
        if (
            not isinstance(campus, dict)
            or campus.get("stable_key") != acceptance["physical_site_stable_key"]
            or not isinstance(campus.get("name"), str)
            or not campus["name"]
        ):
            raise VerifiedConstructionCoreError(
                "current reviewed-site campus identity differs"
            )
        previous = delta_site_names.setdefault(campus["stable_key"], campus["name"])
        if previous != campus["name"]:
            raise VerifiedConstructionCoreError(
                "current reviewed-site campus name differs"
            )
    projects_by_site: dict[str, list[dict[str, str]]] = defaultdict(list)
    for project in projects:
        projects_by_site[project["site_id"]].append(project)
    for site in sites:
        members = sorted(
            projects_by_site[site["site_id"]], key=lambda row: row["project_id"]
        )
        geometry_member = _preferred_site_geometry_member(members)
        expected_arrays = {
            "geometry_source_entity_kinds_json": sorted(
                {row["geometry_source_entity_kind"] for row in members}
            ),
            "geometry_derivations_json": sorted(
                {row["geometry_derivation"] for row in members}
            ),
            "geometry_methods_json": sorted(
                {row["geometry_method"] for row in members}
            ),
            "geometry_scope_classes_json": sorted(
                {row["geometry_scope_class"] for row in members}
            ),
            "geometry_precision_scopes_json": sorted(
                {row["geometry_precision_scope"] for row in members}
            ),
            "geometry_evidence_ids_json": sorted(
                {row["geometry_evidence_id"] for row in members}
            ),
            "project_ids_json": [row["project_id"] for row in members],
            "project_stable_keys_json": [
                row["project_stable_key"] for row in members
            ],
            "statuses_json": sorted(
                {row["last_observed_physical_status"] for row in members}
            ),
            "imagery_review_outcomes_json": sorted(
                {row["imagery_review_outcome"] for row in members}
            ),
        }
        if any(
            _parse_json_field(site[field], field) != expected
            for field, expected in expected_arrays.items()
        ):
            raise VerifiedConstructionCoreError("preview site membership differs")
        if int(site["project_count"]) != len(members):
            raise VerifiedConstructionCoreError("preview site project count differs")
        expected_scalars = {
            "physical_site_stable_key": geometry_member[
                "physical_site_stable_key"
            ],
            "country": geometry_member["country"],
            "country_iso_a2": geometry_member["country_iso_a2"],
            "latitude": geometry_member["latitude"],
            "longitude": geometry_member["longitude"],
            "geometry_json": geometry_member["geometry_json"],
            "geometry_type": geometry_member["geometry_type"],
            "horizontal_uncertainty_metres": geometry_member[
                "horizontal_uncertainty_metres"
            ],
            "horizontal_uncertainty_unknown_reason": geometry_member[
                "horizontal_uncertainty_unknown_reason"
            ],
            "oldest_status_as_of": min(row["status_as_of"] for row in members),
            "newest_status_as_of": max(row["status_as_of"] for row in members),
            "verification_posture": geometry_member["verification_posture"],
            "independent_imagery_verification": "false",
        }
        if site["physical_site_stable_key"] in delta_site_names:
            expected_scalars["name"] = delta_site_names[
                site["physical_site_stable_key"]
            ]
        if any(site[field] != expected for field, expected in expected_scalars.items()):
            raise VerifiedConstructionCoreError("preview site projection differs")
        if site["site_id"] != _stable_id(
            "vcc-site", site["physical_site_stable_key"]
        ):
            raise VerifiedConstructionCoreError("preview site id differs")
    if geojson != _geojson(sites):
        raise VerifiedConstructionCoreError("preview GeoJSON and site table differ")
    if (path / "map.html").read_bytes() != _map_html(geojson):
        raise VerifiedConstructionCoreError("preview map and GeoJSON differ")
    report_fields = {
        "country_counts",
        "final_release_gates",
        "format",
        "imagery_review_provenance",
        "maximum_status_age_days",
        "non_selected_source_row_count",
        "official_boundary_project_count",
        "provenance_decisions",
        "publishable_as_final",
        "release_status",
        "reviewed_at",
        "reviewed_overlay_queue",
        "reviewed_site_locator_project_count",
        "selected_physical_site_count",
        "selected_project_count",
        "selection_first_failure_counts",
        "semantic_guardrails",
        "source_pipeline_row_count",
        "source_release_id",
    }
    if not isinstance(report, dict) or set(report) != report_fields:
        raise VerifiedConstructionCoreError("preview selection-report fields differ")
    expected_gates = _final_release_gates(sites, projects)
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    expected_values = {
        "format": "datacenter-atlas-verified-construction-core-selection-v3",
        "release_status": "preview",
        "publishable_as_final": all(
            gate.get("passed", False) for gate in expected_gates.values()
        ),
        "source_release_id": SOURCE_RELEASE_ID,
        "reviewed_at": REVIEW_DATE.isoformat(),
        "maximum_status_age_days": MAX_STATUS_AGE_DAYS,
        "source_pipeline_row_count": PREVIEW_SOURCE_PIPELINE_ROW_COUNT,
        "selected_project_count": len(projects),
        "selected_physical_site_count": len(sites),
        "official_boundary_project_count": sum(
            row["geometry_type"] in {"Polygon", "MultiPolygon"} for row in projects
        ),
        "reviewed_site_locator_project_count": sum(
            row["geometry_type"] == "Point" for row in projects
        ),
        "non_selected_source_row_count": PREVIEW_SOURCE_PIPELINE_ROW_COUNT
        - len(projects),
        "selection_first_failure_counts": PREVIEW_SELECTION_FIRST_FAILURE_COUNTS,
        "country_counts": country_counts,
        "final_release_gates": expected_gates,
        "imagery_review_provenance": imagery_records,
        "provenance_decisions": {
            "workload_scope_bindings": provenance["workload_scope_bindings"],
            "role_bindings": provenance["role_bindings"],
            "excluded_source_roles": provenance["excluded_source_roles"],
        },
        "semantic_guardrails": SEMANTIC_GUARDRAILS,
    }
    if any(report.get(field) != value for field, value in expected_values.items()):
        raise VerifiedConstructionCoreError("preview selection-report values differ")
    if (path / "README.md").read_bytes() != _readme(report):
        raise VerifiedConstructionCoreError("preview README differs")
    overlay_definition = _load_json(OVERLAY_DEFINITION)
    expected_overlays = overlay_definition.get("overlays")
    if report.get("reviewed_overlay_queue") != expected_overlays:
        raise VerifiedConstructionCoreError("preview reviewed-overlay queue differs")
    if not isinstance(expected_overlays, list):
        raise VerifiedConstructionCoreError("preview reviewed-overlay definition differs")
    if (path / "ATTRIBUTION.txt").read_bytes() != _attribution(
        evidence, expected_overlays, imagery_records
    ):
        raise VerifiedConstructionCoreError("preview attribution differs")
    for overlay in expected_overlays:
        _geometry_release_manifest(
            overlay.get("geometry_release_id", ""),
            overlay.get("geometry_release_manifest_sha256", ""),
        )
    derived_counts = {
        "physical_sites": len(sites),
        "projects": len(projects),
        "evidence": len(evidence),
        "countries": len({row["country"] for row in sites}),
        "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
        "official_boundary_projects": sum(
            row["geometry_type"] in {"Polygon", "MultiPolygon"}
            for row in projects
        ),
        "reviewed_site_locator_projects": sum(
            row["geometry_type"] == "Point" for row in projects
        ),
    }
    if counts != derived_counts:
        raise VerifiedConstructionCoreError("preview derived counts differ")
    if counts != {
        "physical_sites": 14,
        "projects": 15,
        "evidence": 36,
        "countries": 10,
        "non_us_sites": 11,
        "official_boundary_projects": 3,
        "reviewed_site_locator_projects": 12,
    }:
        raise VerifiedConstructionCoreError("preview expected cohort counts differ")
    return manifest


__all__ = [
    "IMAGERY_REVIEW_DEFINITION",
    "LEGACY_PREVIEW_V01_DIR",
    "LEGACY_PREVIEW_V02_DIR",
    "PREVIEW_DIR",
    "PROVENANCE_DEFINITION",
    "VerifiedConstructionCoreError",
    "build_preview",
    "validate_frozen_v01",
    "validate_frozen_v02",
    "validate_preview",
]
