"""Deterministic field-completeness audit for federated atlas releases.

The audit measures source-scoped records.  It deliberately does not merge
children, resolve advisory relationships, promote review candidates, or infer
a count of unique physical sites.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .federated_release import validate_federated_release_index


AUDIT_FILENAME = "coverage-audit.json"
COVERAGE_CSV_FILENAME = "coverage.csv"
GAP_REGISTRY_FILENAME = "gap-registry.json"
REPORT_FILENAME = "REPORT.md"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
AUDIT_BUNDLE_FILES = frozenset(
    {
        AUDIT_FILENAME,
        COVERAGE_CSV_FILENAME,
        GAP_REGISTRY_FILENAME,
        REPORT_FILENAME,
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
)
AUDIT_FORMAT = "datacenter-atlas-coverage-audit-v1"
GAP_FORMAT = "datacenter-atlas-gap-registry-v1"
BUNDLE_FORMAT = "datacenter-atlas-coverage-audit-bundle-v1"
SCHEMA_VERSION = 1
ALL = "__ALL__"
UNRESOLVED = "__UNRESOLVED__"
PIPELINE_STATUSES = frozenset(
    {"announced", "expansion", "proposed", "under_construction"}
)
PUBLIC_CLAIM_IDS = frozenset(
    {
        "facility_scope_count",
        "evidence_methodology",
        "capacity_outputs",
        "temporal_granularity",
        "construction_timeline_pjm",
    }
)
METHODOLOGY_EVIDENCE_CATEGORIES = (
    "computer_vision",
    "foia",
    "permits",
    "property_records",
    "satellite_imagery",
)
MAP_FIELDS = (
    "administrative_assignment_status_counts",
    "annual_energy_method_counts",
    "annual_energy_provenance_counts",
    "capacity_confidence_counts",
    "capacity_method_counts",
    "capacity_metric_counts",
    "capacity_stage_counts",
    "non_review_source_declared_entity_kind_counts",
    "operating_model_counts",
    "pipeline_status_counts",
    "source_declared_entity_kind_counts",
    "status_counts",
    "status_freshness_counts",
    "workload_counts",
)


class CoverageAuditError(ValueError):
    """Raised when an audit definition, input, or output fails closed."""


@dataclass(frozen=True, slots=True)
class CoverageAuditBundle:
    """In-memory representation of the complete immutable audit bundle."""

    payloads: Mapping[str, bytes]
    audit: Mapping[str, Any]
    gaps: Mapping[str, Any]
    manifest: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _ChildInput:
    release_id: str
    release_path: Path
    expected_manifest_sha256: str


@dataclass(frozen=True, slots=True, order=True)
class _EvidenceReference:
    release_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class _AuditDefinition:
    raw: bytes
    filename: str
    audit_id: str
    generated_at: str
    generated_on: date
    federation_path: Path
    expected_federation_manifest_sha256: str
    children: tuple[_ChildInput, ...]
    public_benchmark: Mapping[str, Any]
    methodology_evidence_classification: (
        Mapping[str, tuple[_EvidenceReference, ...]] | None
    )


@dataclass(slots=True)
class _Stats:
    rows: int = 0
    coordinate_rows: int = 0
    country_rows: int = 0
    country_iso_a2_rows: int = 0
    country_iso_a3_rows: int = 0
    unresolved_country_rows: int = 0
    review_only_rows: int = 0
    non_review_rows: int = 0
    lifecycle_status_rows: int = 0
    informative_lifecycle_status_rows: int = 0
    unresolved_lifecycle_status_rows: int = 0
    status_as_of_rows: int = 0
    status_evidence_rows: int = 0
    status_method_rows: int = 0
    complete_lifecycle_claim_rows: int = 0
    under_construction_rows: int = 0
    under_construction_with_status_evidence_rows: int = 0
    non_review_under_construction_rows: int = 0
    review_only_under_construction_lead_rows: int = 0
    pipeline_rows: int = 0
    pipeline_with_status_evidence_rows: int = 0
    capacity_entity_rows: int = 0
    capacity_observations: int = 0
    capacity_observations_with_evidence: int = 0
    capacity_observations_with_resolved_evidence: int = 0
    annual_energy_entity_rows: int = 0
    annual_energy_observations: int = 0
    annual_energy_observations_with_evidence: int = 0
    annual_energy_observations_with_resolved_evidence: int = 0
    operating_model_rows: int = 0
    operating_model_evidence_rows: int = 0
    operating_model_resolved_evidence_rows: int = 0
    workload_rows: int = 0
    workload_observations: int = 0
    workload_observations_with_evidence: int = 0
    workload_observations_with_resolved_evidence: int = 0
    construction_evidence_ids: set[str] = field(default_factory=set)
    administrative_assignment_status_counts: Counter[str] = field(
        default_factory=Counter
    )
    annual_energy_method_counts: Counter[str] = field(default_factory=Counter)
    annual_energy_provenance_counts: Counter[str] = field(default_factory=Counter)
    capacity_confidence_counts: Counter[str] = field(default_factory=Counter)
    capacity_method_counts: Counter[str] = field(default_factory=Counter)
    capacity_metric_counts: Counter[str] = field(default_factory=Counter)
    capacity_stage_counts: Counter[str] = field(default_factory=Counter)
    non_review_source_declared_entity_kind_counts: Counter[str] = field(
        default_factory=Counter
    )
    operating_model_counts: Counter[str] = field(default_factory=Counter)
    pipeline_status_counts: Counter[str] = field(default_factory=Counter)
    source_declared_entity_kind_counts: Counter[str] = field(default_factory=Counter)
    status_counts: Counter[str] = field(default_factory=Counter)
    status_freshness_counts: Counter[str] = field(default_factory=Counter)
    workload_counts: Counter[str] = field(default_factory=Counter)

    def add(
        self,
        properties: Mapping[str, Any],
        *,
        evidence: Mapping[str, Mapping[str, str]],
        review_only: bool,
        generated_on: date,
        country: str | None,
        country_iso_a2: str | None,
        country_iso_a3: str | None,
    ) -> None:
        self.rows += 1
        if review_only:
            self.review_only_rows += 1
        else:
            self.non_review_rows += 1

        kind = _text_or_missing(properties.get("entity_kind"))
        self.source_declared_entity_kind_counts[kind] += 1
        if not review_only:
            self.non_review_source_declared_entity_kind_counts[kind] += 1

        latitude = properties.get("latitude")
        longitude = properties.get("longitude")
        if (
            _is_number(latitude)
            and _is_number(longitude)
            and -90 <= float(latitude) <= 90
            and -180 <= float(longitude) <= 180
        ):
            self.coordinate_rows += 1

        if country is None:
            self.unresolved_country_rows += 1
        else:
            self.country_rows += 1
        if country_iso_a2 is not None:
            self.country_iso_a2_rows += 1
        if country_iso_a3 is not None:
            self.country_iso_a3_rows += 1
        assignment_status = _optional_text(
            properties.get("administrative_assignment_status")
        )
        if assignment_status is None:
            assignment_status = "source_label_only" if country else "unresolved"
        self.administrative_assignment_status_counts[assignment_status] += 1

        status = _optional_text(properties.get("status"))
        status_as_of = _optional_text(properties.get("status_as_of"))
        status_evidence_id = _optional_text(properties.get("status_evidence_id"))
        status_method = _optional_text(properties.get("status_method"))
        if status is not None:
            self.lifecycle_status_rows += 1
            self.status_counts[status] += 1
        else:
            self.status_counts["__MISSING__"] += 1
        if status is not None and status not in {"lead", "unknown"}:
            self.informative_lifecycle_status_rows += 1
        else:
            self.unresolved_lifecycle_status_rows += 1
        if status_as_of is not None:
            self.status_as_of_rows += 1
        if status_evidence_id is not None:
            self.status_evidence_rows += 1
        if status_method is not None:
            self.status_method_rows += 1
        if all(
            value is not None
            for value in (status, status_as_of, status_evidence_id, status_method)
        ):
            self.complete_lifecycle_claim_rows += 1
        self.status_freshness_counts[
            _freshness_bucket(status_as_of, generated_on)
        ] += 1

        if status == "under_construction":
            self.under_construction_rows += 1
            if review_only:
                self.review_only_under_construction_lead_rows += 1
            else:
                self.non_review_under_construction_rows += 1
            if status_evidence_id is not None:
                self.under_construction_with_status_evidence_rows += 1
                self.construction_evidence_ids.add(status_evidence_id)
        if status in PIPELINE_STATUSES:
            self.pipeline_rows += 1
            self.pipeline_status_counts[status] += 1
            if status_evidence_id is not None:
                self.pipeline_with_status_evidence_rows += 1

        capacities = properties.get("capacity_estimates")
        if capacities is None:
            capacities = []
        if not isinstance(capacities, list):
            raise CoverageAuditError("capacity_estimates must be an array")
        if capacities:
            self.capacity_entity_rows += 1
        annual_entity = False
        for estimate in capacities:
            if not isinstance(estimate, Mapping):
                raise CoverageAuditError("capacity estimate must be an object")
            self.capacity_observations += 1
            metric = _text_or_missing(estimate.get("metric"))
            stage = _text_or_missing(estimate.get("stage"))
            method = _text_or_missing(estimate.get("method"))
            confidence = _number_key(estimate.get("confidence"))
            self.capacity_metric_counts[metric] += 1
            self.capacity_stage_counts[stage] += 1
            self.capacity_method_counts[method] += 1
            self.capacity_confidence_counts[confidence] += 1
            evidence_id = _optional_text(estimate.get("evidence_id"))
            evidence_record = evidence.get(evidence_id or "")
            if evidence_id is not None:
                self.capacity_observations_with_evidence += 1
            if evidence_record is not None:
                self.capacity_observations_with_resolved_evidence += 1
            if metric == "annual_energy_mwh":
                annual_entity = True
                self.annual_energy_observations += 1
                self.annual_energy_method_counts[method] += 1
                if evidence_id is not None:
                    self.annual_energy_observations_with_evidence += 1
                if evidence_record is not None:
                    self.annual_energy_observations_with_resolved_evidence += 1
                    provenance = "|".join(
                        (
                            method,
                            _text_or_missing(evidence_record.get("source_family")),
                            _text_or_missing(evidence_record.get("license")),
                        )
                    )
                else:
                    provenance = f"{method}|__UNRESOLVED_EVIDENCE__|__MISSING__"
                self.annual_energy_provenance_counts[provenance] += 1
        if annual_entity:
            self.annual_energy_entity_rows += 1

        operating_model = _optional_text(properties.get("operating_model"))
        if operating_model is not None:
            self.operating_model_rows += 1
            self.operating_model_counts[operating_model] += 1
            operating_evidence_id = _optional_text(
                properties.get("operating_model_evidence_id")
            )
            if operating_evidence_id is not None:
                self.operating_model_evidence_rows += 1
                if operating_evidence_id in evidence:
                    self.operating_model_resolved_evidence_rows += 1

        workloads = properties.get("workloads")
        if workloads is None:
            workloads = []
        if not isinstance(workloads, list):
            raise CoverageAuditError("workloads must be an array")
        normalized_workloads = [_text_or_missing(value) for value in workloads]
        if normalized_workloads:
            self.workload_rows += 1
            self.workload_counts.update(normalized_workloads)
        observations = properties.get("workload_observations")
        if observations is None:
            observations = []
        if not isinstance(observations, list):
            raise CoverageAuditError("workload_observations must be an array")
        for observation in observations:
            if not isinstance(observation, Mapping):
                raise CoverageAuditError("workload observation must be an object")
            self.workload_observations += 1
            evidence_id = _optional_text(observation.get("evidence_id"))
            if evidence_id is not None:
                self.workload_observations_with_evidence += 1
                if evidence_id in evidence:
                    self.workload_observations_with_resolved_evidence += 1

    def export(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_scoped_rows": self.rows,
            "coordinate_rows": self.coordinate_rows,
            "coordinate_coverage": _ratio(self.coordinate_rows, self.rows),
            "country_rows": self.country_rows,
            "country_coverage": _ratio(self.country_rows, self.rows),
            "country_iso_a2_rows": self.country_iso_a2_rows,
            "country_iso_a2_coverage": _ratio(self.country_iso_a2_rows, self.rows),
            "country_iso_a3_rows": self.country_iso_a3_rows,
            "country_iso_a3_coverage": _ratio(self.country_iso_a3_rows, self.rows),
            "unresolved_country_rows": self.unresolved_country_rows,
            "review_only_rows": self.review_only_rows,
            "non_review_rows": self.non_review_rows,
            "lifecycle_status_rows": self.lifecycle_status_rows,
            "lifecycle_status_coverage": _ratio(self.lifecycle_status_rows, self.rows),
            "informative_lifecycle_status_rows": self.informative_lifecycle_status_rows,
            "informative_lifecycle_status_coverage": _ratio(
                self.informative_lifecycle_status_rows, self.rows
            ),
            "unresolved_lifecycle_status_rows": self.unresolved_lifecycle_status_rows,
            "status_as_of_rows": self.status_as_of_rows,
            "status_as_of_coverage": _ratio(self.status_as_of_rows, self.rows),
            "status_evidence_rows": self.status_evidence_rows,
            "status_evidence_coverage": _ratio(self.status_evidence_rows, self.rows),
            "status_method_rows": self.status_method_rows,
            "status_method_coverage": _ratio(self.status_method_rows, self.rows),
            "complete_lifecycle_claim_rows": self.complete_lifecycle_claim_rows,
            "complete_lifecycle_claim_coverage": _ratio(
                self.complete_lifecycle_claim_rows, self.rows
            ),
            "under_construction_rows": self.under_construction_rows,
            "under_construction_with_status_evidence_rows": self.under_construction_with_status_evidence_rows,
            "non_review_under_construction_rows": self.non_review_under_construction_rows,
            "review_only_under_construction_lead_rows": self.review_only_under_construction_lead_rows,
            "construction_evidence_observations": len(self.construction_evidence_ids),
            "pipeline_rows": self.pipeline_rows,
            "pipeline_with_status_evidence_rows": self.pipeline_with_status_evidence_rows,
            "capacity_entity_rows": self.capacity_entity_rows,
            "capacity_entity_coverage": _ratio(self.capacity_entity_rows, self.rows),
            "capacity_observations": self.capacity_observations,
            "capacity_observations_with_evidence": self.capacity_observations_with_evidence,
            "capacity_observations_with_resolved_evidence": self.capacity_observations_with_resolved_evidence,
            "annual_energy_entity_rows": self.annual_energy_entity_rows,
            "annual_energy_entity_coverage": _ratio(
                self.annual_energy_entity_rows, self.rows
            ),
            "annual_energy_observations": self.annual_energy_observations,
            "annual_energy_observations_with_evidence": self.annual_energy_observations_with_evidence,
            "annual_energy_observations_with_resolved_evidence": self.annual_energy_observations_with_resolved_evidence,
            "operating_model_rows": self.operating_model_rows,
            "operating_model_coverage": _ratio(self.operating_model_rows, self.rows),
            "operating_model_evidence_rows": self.operating_model_evidence_rows,
            "operating_model_resolved_evidence_rows": self.operating_model_resolved_evidence_rows,
            "workload_rows": self.workload_rows,
            "workload_coverage": _ratio(self.workload_rows, self.rows),
            "workload_observations": self.workload_observations,
            "workload_observations_with_evidence": self.workload_observations_with_evidence,
            "workload_observations_with_resolved_evidence": self.workload_observations_with_resolved_evidence,
        }
        for field_name in MAP_FIELDS:
            value = getattr(self, field_name)
            result[field_name] = dict(sorted(value.items()))
        return result


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise CoverageAuditError(f"{label} must be non-empty trimmed text")
    return value


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _text_or_missing(value: Any) -> str:
    return _optional_text(value) or "__MISSING__"


def _sha256_text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CoverageAuditError(f"{label} must be lowercase SHA-256 hexadecimal")
    return value


def _audit_id(value: Any) -> str:
    result = _required_text(value, "audit_id")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
    if (
        len(result) > 96
        or any(character not in allowed for character in result)
        or not result[0].isalnum()
        or not result[-1].isalnum()
    ):
        raise CoverageAuditError("audit_id must be lowercase alphanumeric-hyphen text")
    return result


def _canonical_timestamp(value: Any, label: str) -> tuple[str, date]:
    text = _required_text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise CoverageAuditError(f"{label} is not a valid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CoverageAuditError(f"{label} must include a timezone")
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if text != canonical:
        raise CoverageAuditError(f"{label} must use canonical UTC seconds")
    return text, parsed.astimezone(UTC).date()


def _calendar_date(value: Any, label: str) -> str:
    text = _required_text(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise CoverageAuditError(f"{label} must use YYYY-MM-DD") from error
    if parsed.isoformat() != text:
        raise CoverageAuditError(f"{label} must use canonical YYYY-MM-DD")
    return text


def _regular_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CoverageAuditError(f"{label} must be a regular file: {path}")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    def reject_constant(token: str) -> None:
        raise CoverageAuditError(f"{label} contains non-finite number {token}")

    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CoverageAuditError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CoverageAuditError(f"{label} must be a JSON object")
    return value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number_key(value: Any) -> str:
    if not _is_number(value):
        return "__MISSING__"
    return format(float(value), ".12g")


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _freshness_bucket(value: str | None, generated_on: date) -> str:
    if value is None:
        return "missing"
    try:
        observed = date.fromisoformat(value[:10])
    except ValueError:
        return "invalid"
    age = (generated_on - observed).days
    if age < 0:
        return "future"
    if age <= 90:
        return "0_90_days"
    if age <= 365:
        return "91_365_days"
    return "366_plus_days"


def _country(properties: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    tags = properties.get("tags")
    if not isinstance(tags, Mapping):
        tags = {}
    country = (
        _optional_text(properties.get("country"))
        or _optional_text(properties.get("administrative_country_name"))
        or _optional_text(tags.get("country"))
    )
    iso_a2 = (
        _optional_text(properties.get("country_iso_a2"))
        or _optional_text(properties.get("administrative_country_iso_a2"))
    )
    iso_a3 = (
        _optional_text(properties.get("country_iso_a3"))
        or _optional_text(properties.get("administrative_country_iso_a3"))
    )
    return country, iso_a2, iso_a3


def _public_benchmark(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "name",
        "retrieved_on",
        "claims",
    }:
        raise CoverageAuditError("public_benchmark schema is invalid")
    name = _required_text(value.get("name"), "public benchmark name")
    retrieved_on = _calendar_date(
        value.get("retrieved_on"), "public benchmark retrieved_on"
    )
    claims_value = value.get("claims")
    if not isinstance(claims_value, list):
        raise CoverageAuditError("public benchmark claims must be an array")
    claims: list[dict[str, str]] = []
    for index, claim in enumerate(claims_value):
        label = f"public benchmark claim {index}"
        if not isinstance(claim, Mapping) or set(claim) != {
            "claim_id",
            "kind",
            "paraphrase",
            "source_url",
        }:
            raise CoverageAuditError(f"{label} schema is invalid")
        source_url = _required_text(claim.get("source_url"), f"{label} source_url")
        parsed = urlsplit(source_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            hostname == "semianalysis.com" or hostname.endswith(".semianalysis.com")
        ):
            raise CoverageAuditError(f"{label} must cite an official SemiAnalysis URL")
        claims.append(
            {
                "claim_id": _required_text(claim.get("claim_id"), f"{label} claim_id"),
                "kind": _required_text(claim.get("kind"), f"{label} kind"),
                "paraphrase": _required_text(
                    claim.get("paraphrase"), f"{label} paraphrase"
                ),
                "source_url": source_url,
            }
        )
    claim_ids = [claim["claim_id"] for claim in claims]
    if set(claim_ids) != PUBLIC_CLAIM_IDS or claim_ids != sorted(claim_ids):
        raise CoverageAuditError(
            "public benchmark claims must be the canonical supported claim set"
        )
    return {"name": name, "retrieved_on": retrieved_on, "claims": claims}


def _methodology_evidence_classification(
    value: Any,
) -> dict[str, tuple[_EvidenceReference, ...]]:
    if not isinstance(value, Mapping) or set(value) != set(
        METHODOLOGY_EVIDENCE_CATEGORIES
    ):
        raise CoverageAuditError(
            "methodology_evidence_classification schema is invalid"
        )
    result: dict[str, tuple[_EvidenceReference, ...]] = {}
    for category in METHODOLOGY_EVIDENCE_CATEGORIES:
        references_value = value.get(category)
        if not isinstance(references_value, list):
            raise CoverageAuditError(
                f"methodology evidence category {category} must be an array"
            )
        references: list[_EvidenceReference] = []
        for index, reference in enumerate(references_value):
            label = f"methodology evidence {category} reference {index}"
            if not isinstance(reference, Mapping) or set(reference) != {
                "release_id",
                "evidence_id",
            }:
                raise CoverageAuditError(f"{label} schema is invalid")
            references.append(
                _EvidenceReference(
                    release_id=_required_text(
                        reference.get("release_id"), f"{label} release_id"
                    ),
                    evidence_id=_required_text(
                        reference.get("evidence_id"), f"{label} evidence_id"
                    ),
                )
            )
        if references != sorted(set(references)):
            raise CoverageAuditError(
                f"methodology evidence category {category} references must be "
                "sorted and unique"
            )
        result[category] = tuple(references)
    return result


def _definition(path: Path) -> _AuditDefinition:
    raw = _regular_bytes(path, "coverage audit definition")
    document = _json_object(raw, "coverage audit definition")
    if raw != _canonical_json(document):
        raise CoverageAuditError("coverage audit definition must be canonical JSON")
    required_fields = {
        "schema_version",
        "audit_id",
        "generated_at",
        "federated_index",
        "children",
        "public_benchmark",
    }
    optional_fields = {"methodology_evidence_classification"}
    if not required_fields.issubset(document) or set(document) - (
        required_fields | optional_fields
    ):
        raise CoverageAuditError("coverage audit definition schema is invalid")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise CoverageAuditError("coverage audit definition version is unsupported")
    audit_id = _audit_id(document.get("audit_id"))
    generated_at, generated_on = _canonical_timestamp(
        document.get("generated_at"), "generated_at"
    )
    federation = document.get("federated_index")
    if not isinstance(federation, Mapping) or set(federation) != {
        "path",
        "expected_manifest_sha256",
    }:
        raise CoverageAuditError("federated_index definition is invalid")
    federation_path_value = _required_text(
        federation.get("path"), "federated_index path"
    )
    federation_path = Path(federation_path_value)
    if not federation_path.is_absolute():
        federation_path = path.parent / federation_path
    expected_federation_manifest_sha256 = _sha256_text(
        federation.get("expected_manifest_sha256"),
        "expected federated manifest SHA-256",
    )

    children_value = document.get("children")
    if not isinstance(children_value, list) or len(children_value) < 2:
        raise CoverageAuditError("coverage audit must contain at least two children")
    children: list[_ChildInput] = []
    for index, value in enumerate(children_value):
        label = f"coverage child {index}"
        if not isinstance(value, Mapping) or set(value) != {
            "release_id",
            "release_path",
            "expected_manifest_sha256",
        }:
            raise CoverageAuditError(f"{label} schema is invalid")
        release_id = _required_text(value.get("release_id"), f"{label} release_id")
        release_path_value = _required_text(
            value.get("release_path"), f"{label} release_path"
        )
        release_path = Path(release_path_value)
        if not release_path.is_absolute():
            release_path = path.parent / release_path
        children.append(
            _ChildInput(
                release_id=release_id,
                release_path=release_path,
                expected_manifest_sha256=_sha256_text(
                    value.get("expected_manifest_sha256"),
                    f"{label} expected_manifest_sha256",
                ),
            )
        )
    release_ids = [child.release_id for child in children]
    paths = [child.release_path.resolve() for child in children]
    if release_ids != sorted(set(release_ids)) or len(paths) != len(set(paths)):
        raise CoverageAuditError("coverage children must be sorted and unique")
    methodology_evidence_classification = None
    if "methodology_evidence_classification" in document:
        methodology_evidence_classification = _methodology_evidence_classification(
            document["methodology_evidence_classification"]
        )
        referenced_releases = {
            reference.release_id
            for references in methodology_evidence_classification.values()
            for reference in references
        }
        unknown_releases = referenced_releases - set(release_ids)
        if unknown_releases:
            raise CoverageAuditError(
                "methodology evidence references unknown coverage children: "
                + ", ".join(sorted(unknown_releases))
            )
    return _AuditDefinition(
        raw=raw,
        filename=path.name,
        audit_id=audit_id,
        generated_at=generated_at,
        generated_on=generated_on,
        federation_path=federation_path,
        expected_federation_manifest_sha256=expected_federation_manifest_sha256,
        children=tuple(children),
        public_benchmark=_public_benchmark(document.get("public_benchmark")),
        methodology_evidence_classification=methodology_evidence_classification,
    )


def _evidence(path: Path, expected_count: int) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"evidence_id", "source_family", "license"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise CoverageAuditError("evidence.csv schema is insufficient")
            for row in reader:
                evidence_id = _required_text(row.get("evidence_id"), "evidence_id")
                if evidence_id in result:
                    raise CoverageAuditError(f"duplicate evidence_id: {evidence_id}")
                result[evidence_id] = row
    except (UnicodeDecodeError, csv.Error) as error:
        raise CoverageAuditError("evidence.csv must be valid UTF-8 CSV") from error
    if len(result) != expected_count:
        raise CoverageAuditError("evidence.csv count does not match federation")
    return result


def _feature_properties(path: Path, expected_count: int) -> list[Mapping[str, Any]]:
    document = _json_object(_regular_bytes(path, "atlas.geojson"), "atlas.geojson")
    if document.get("type") != "FeatureCollection" or not isinstance(
        document.get("features"), list
    ):
        raise CoverageAuditError("atlas.geojson must be a FeatureCollection")
    features = document["features"]
    if len(features) != expected_count:
        raise CoverageAuditError("atlas.geojson count does not match federation")
    result: list[Mapping[str, Any]] = []
    entity_ids: set[str] = set()
    for position, feature in enumerate(features):
        if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
            raise CoverageAuditError(f"atlas feature {position} is invalid")
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise CoverageAuditError(f"atlas feature {position} properties are invalid")
        entity_id = _required_text(
            properties.get("entity_id"), f"atlas feature {position} entity_id"
        )
        if entity_id in entity_ids:
            raise CoverageAuditError(f"duplicate entity_id in atlas.geojson: {entity_id}")
        entity_ids.add(entity_id)
        result.append(properties)
    return result


def _group_record(
    *,
    scope_type: str,
    release_id: str,
    release_as_of: str,
    review_only: bool,
    source_family: str,
    country: str,
    country_iso_a2: str | None,
    country_iso_a3: str | None,
    stats: _Stats,
) -> dict[str, Any]:
    return {
        "scope_type": scope_type,
        "child_release": release_id,
        "child_release_as_of": release_as_of,
        "release_review_only": review_only,
        "source_family": source_family,
        "country": country,
        "country_iso_a2": country_iso_a2,
        "country_iso_a3": country_iso_a3,
        **stats.export(),
    }


def _inspect_release(
    child: _ChildInput,
    descriptor: Mapping[str, Any],
    generated_on: date,
) -> tuple[list[dict[str, Any]], _Stats, set[str]]:
    release_id = child.release_id
    manifest = descriptor["manifest"]
    counts = descriptor["counts"]
    review_only = bool(descriptor["scope"]["review_only"])
    expected_count = counts["source_scoped_entity_records"]
    evidence = _evidence(child.release_path / "evidence.csv", counts["evidence_records"])
    properties_list = _feature_properties(
        child.release_path / "atlas.geojson", expected_count
    )
    declared_sources = set(descriptor["source_families"])
    release_stats = _Stats()
    source_stats: dict[str, _Stats] = {
        source: _Stats() for source in descriptor["source_families"]
    }
    country_stats: dict[tuple[str, str, str, str], _Stats] = {}
    entity_sources: set[str] = set()
    for properties in properties_list:
        source_family = _required_text(
            properties.get("source_family"), "atlas source_family"
        )
        if source_family not in declared_sources:
            raise CoverageAuditError(
                f"{release_id} atlas source_family is not declared: {source_family}"
            )
        entity_sources.add(source_family)
        country, iso_a2, iso_a3 = _country(properties)
        key = (
            source_family,
            country or UNRESOLVED,
            iso_a2 or "",
            iso_a3 or "",
        )
        country_stats.setdefault(key, _Stats())
        for stats in (release_stats, source_stats[source_family], country_stats[key]):
            stats.add(
                properties,
                evidence=evidence,
                review_only=review_only,
                generated_on=generated_on,
                country=country,
                country_iso_a2=iso_a2,
                country_iso_a3=iso_a3,
            )
    if release_stats.capacity_observations != counts["capacity_estimates"]:
        raise CoverageAuditError(
            f"{release_id} GeoJSON capacity observations do not match federation"
        )

    rows = [
        _group_record(
            scope_type="release",
            release_id=release_id,
            release_as_of=manifest["as_of"],
            review_only=review_only,
            source_family=ALL,
            country=ALL,
            country_iso_a2=None,
            country_iso_a3=None,
            stats=release_stats,
        )
    ]
    for source_family, stats in sorted(source_stats.items()):
        rows.append(
            _group_record(
                scope_type="release_source",
                release_id=release_id,
                release_as_of=manifest["as_of"],
                review_only=review_only,
                source_family=source_family,
                country=ALL,
                country_iso_a2=None,
                country_iso_a3=None,
                stats=stats,
            )
        )
    for (source_family, country, iso_a2, iso_a3), stats in sorted(
        country_stats.items()
    ):
        rows.append(
            _group_record(
                scope_type="release_source_country",
                release_id=release_id,
                release_as_of=manifest["as_of"],
                review_only=review_only,
                source_family=source_family,
                country=country,
                country_iso_a2=iso_a2 or None,
                country_iso_a3=iso_a3 or None,
                stats=stats,
            )
        )
    return rows, release_stats, entity_sources


def _merge_stats(target: _Stats, source: _Stats) -> None:
    for field_name in _Stats.__dataclass_fields__:
        target_value = getattr(target, field_name)
        source_value = getattr(source, field_name)
        if isinstance(target_value, Counter):
            target_value.update(source_value)
        elif isinstance(target_value, set):
            target_value.update(source_value)
        else:
            setattr(target, field_name, target_value + source_value)


def _resolve_methodology_evidence(
    classification: Mapping[str, tuple[_EvidenceReference, ...]] | None,
    *,
    children: tuple[_ChildInput, ...],
    descriptors: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]] | None:
    if classification is None:
        return None
    child_by_release = {child.release_id: child for child in children}
    evidence_by_release: dict[str, dict[str, dict[str, str]]] = {}
    result: dict[str, dict[str, Any]] = {}
    for category in METHODOLOGY_EVIDENCE_CATEGORIES:
        resolved_references: list[dict[str, str]] = []
        for reference in classification[category]:
            child = child_by_release[reference.release_id]
            descriptor = descriptors[reference.release_id]
            evidence = evidence_by_release.get(reference.release_id)
            if evidence is None:
                evidence = _evidence(
                    child.release_path / "evidence.csv",
                    descriptor["counts"]["evidence_records"],
                )
                evidence_by_release[reference.release_id] = evidence
            record = evidence.get(reference.evidence_id)
            if record is None:
                raise CoverageAuditError(
                    "methodology evidence reference does not exist in exact child: "
                    f"{reference.release_id}/{reference.evidence_id}"
                )
            source_family = _required_text(
                record.get("source_family"),
                "methodology evidence source_family",
            )
            if source_family not in descriptor["source_families"]:
                raise CoverageAuditError(
                    "methodology evidence source_family is not declared by child: "
                    f"{reference.release_id}/{reference.evidence_id}"
                )
            resolved_references.append(
                {
                    "evidence_id": reference.evidence_id,
                    "release_id": reference.release_id,
                    "source_family": source_family,
                }
            )
        if category == "permits" and resolved_references:
            status = "permitting_process_evidence_present"
        elif resolved_references:
            status = "classified_evidence_present"
        else:
            status = "absent_from_audited_children"
        category_evidence: dict[str, Any] = {
            "status": status,
            "evidence_reference_count": len(resolved_references),
            "evidence_ids": sorted(
                reference["evidence_id"] for reference in resolved_references
            ),
            "release_ids": sorted(
                {reference["release_id"] for reference in resolved_references}
            ),
            "source_families": sorted(
                {reference["source_family"] for reference in resolved_references}
            ),
            "evidence_references": resolved_references,
        }
        if category == "permits":
            category_evidence["scope_guardrail"] = (
                "References document permitting processes only; classification does "
                "not assert a granted permit, project approval, or physical "
                "construction."
            )
        result[category] = category_evidence
    return result


def _benchmark_comparison(
    benchmark: Mapping[str, Any],
    totals: Mapping[str, Any],
    methodology_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    fields = totals["field_totals"]
    capacity_metrics = fields["capacity_metric_counts"]
    annual_methods = fields["annual_energy_method_counts"]
    comparisons: list[dict[str, Any]] = []
    for claim in benchmark["claims"]:
        claim_id = claim["claim_id"]
        if claim_id == "facility_scope_count":
            status = "not_comparable"
            atlas_evidence = {
                "source_scoped_rows": totals["source_scoped_entity_records"],
                "non_review_source_scoped_rows": totals[
                    "non_review_source_scoped_entity_records"
                ],
                "review_only_rows": totals[
                    "review_only_source_scoped_entity_records"
                ],
                "unique_physical_sites": None,
                "reason": "Atlas rows span source versions and entity kinds and are not cross-source-deduplicated.",
            }
        elif claim_id == "evidence_methodology":
            status = "material_public_method_gaps"
            if methodology_evidence is None:
                atlas_evidence = {
                    "permits": "absent_from_audited_children",
                    "property_records": "absent_from_audited_children",
                    "foia": "absent_from_audited_children",
                    "power_data": "partial_capacity_observations_present",
                    "satellite_imagery": "absent_from_audited_children",
                    "computer_vision": "absent_from_audited_children",
                }
            else:
                capacity_observations = fields["capacity_observations"]
                atlas_evidence = {
                    **methodology_evidence,
                    "power_data": {
                        "status": (
                            "partial_capacity_observations_present"
                            if capacity_observations
                            else "absent_from_audited_children"
                        ),
                        "capacity_observation_count": capacity_observations,
                        "capacity_observations_with_resolved_evidence": fields[
                            "capacity_observations_with_resolved_evidence"
                        ],
                    },
                }
        elif claim_id == "capacity_outputs":
            status = "partial"
            atlas_evidence = {
                "critical_it_power_observations": capacity_metrics.get(
                    "critical_it_mw", 0
                ),
                "pue_observations": capacity_metrics.get("pue", 0),
                "utility_or_grid_connection_observations": capacity_metrics.get(
                    "grid_connection_mw", 0
                ),
                "annual_energy_observations": fields[
                    "annual_energy_observations"
                ],
                "annual_energy_methods": annual_methods,
                "operating_model_rows": fields["operating_model_rows"],
            }
        elif claim_id == "temporal_granularity":
            status = "partial_current_view_only"
            atlas_evidence = {
                "capacity_stage_counts": fields["capacity_stage_counts"],
                "status_freshness_counts": fields["status_freshness_counts"],
                "quarterly_2017_2032_panel": "absent",
            }
        else:
            status = "partial_status_observations_not_timelines"
            atlas_evidence = {
                "under_construction_rows": fields["under_construction_rows"],
                "non_review_under_construction_rows": fields[
                    "non_review_under_construction_rows"
                ],
                "review_only_under_construction_lead_rows": fields[
                    "review_only_under_construction_lead_rows"
                ],
                "status_as_of_rows": fields["status_as_of_rows"],
                "multi_milestone_construction_timelines": "absent",
            }
        comparisons.append(
            {
                **claim,
                "atlas_status": status,
                "atlas_evidence": atlas_evidence,
                "parity_status": "pending",
            }
        )
    return {
        "benchmark": benchmark,
        "comparisons": comparisons,
        "licensed_row_level_benchmark": {
            "status": "pending",
            "reason": "No licensed SemiAnalysis row-level export was available to this audit.",
        },
        "overall_parity": {
            "status": "pending",
            "reason": "Public claims are not a row-level benchmark, and Atlas unique physical sites remain unknown.",
        },
    }


def _gap_id(parts: list[str]) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"gap-{digest}"


def _gap(
    *,
    audit_id: str,
    scope_type: str,
    field_name: str,
    severity: str,
    child_release: str | None,
    source_family: str | None,
    country: str | None,
    affected_records: int | None,
    denominator_records: int | None,
    detail: str,
) -> dict[str, Any]:
    identity = [
        audit_id,
        scope_type,
        child_release or "",
        source_family or "",
        country or "",
        field_name,
    ]
    return {
        "gap_id": _gap_id(identity),
        "status": "open",
        "severity": severity,
        "scope_type": scope_type,
        "child_release": child_release,
        "source_family": source_family,
        "country": country,
        "field": field_name,
        "affected_records": affected_records,
        "denominator_records": denominator_records,
        "coverage": (
            None
            if affected_records is None
            or denominator_records in (None, 0)
            else round(1 - affected_records / denominator_records, 6)
        ),
        "detail": detail,
    }


def _gap_registry(
    audit_id: str,
    generated_at: str,
    groups: list[Mapping[str, Any]],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    gaps: list[dict[str, Any]] = []
    checks = (
        ("coordinate_rows", "coordinates", "high"),
        ("country_rows", "country", "high"),
        ("country_iso_a2_rows", "country_iso_a2", "medium"),
        ("lifecycle_status_rows", "lifecycle_status", "medium"),
        (
            "informative_lifecycle_status_rows",
            "informative_lifecycle_status",
            "medium",
        ),
        ("status_as_of_rows", "status_as_of", "medium"),
        ("status_evidence_rows", "status_evidence", "medium"),
        ("capacity_entity_rows", "capacity", "low"),
        ("annual_energy_entity_rows", "annual_energy", "low"),
        ("operating_model_rows", "operating_model", "low"),
        ("workload_rows", "workload", "low"),
    )
    for group in groups:
        if group["scope_type"] == "release_source" and group["source_scoped_rows"] == 0:
            gaps.append(
                _gap(
                    audit_id=audit_id,
                    scope_type="release_source",
                    field_name="source_scoped_rows",
                    severity="info",
                    child_release=group["child_release"],
                    source_family=group["source_family"],
                    country=None,
                    affected_records=0,
                    denominator_records=0,
                    detail="Declared evidence source family has no entity rows; it remains visible for provenance.",
                )
            )
        if group["scope_type"] != "release_source_country":
            continue
        denominator = group["source_scoped_rows"]
        for count_field, field_name, base_severity in checks:
            missing = denominator - group[count_field]
            if missing <= 0:
                continue
            severity = base_severity
            if group["release_review_only"] and severity == "high":
                severity = "medium"
            gaps.append(
                _gap(
                    audit_id=audit_id,
                    scope_type="release_source_country",
                    field_name=field_name,
                    severity=severity,
                    child_release=group["child_release"],
                    source_family=group["source_family"],
                    country=(
                        None if group["country"] == UNRESOLVED else group["country"]
                    ),
                    affected_records=missing,
                    denominator_records=denominator,
                    detail="Aggregate field-completeness gap; absence is not evidence that the real-world attribute is negative.",
                )
            )
        construction_missing = (
            group["under_construction_rows"]
            - group["under_construction_with_status_evidence_rows"]
        )
        if construction_missing > 0:
            gaps.append(
                _gap(
                    audit_id=audit_id,
                    scope_type="release_source_country",
                    field_name="under_construction_status_evidence",
                    severity="high",
                    child_release=group["child_release"],
                    source_family=group["source_family"],
                    country=(
                        None if group["country"] == UNRESOLVED else group["country"]
                    ),
                    affected_records=construction_missing,
                    denominator_records=group["under_construction_rows"],
                    detail="Under-construction source rows lack a status evidence identifier.",
                )
            )
        stale = group["status_freshness_counts"].get("366_plus_days", 0)
        if stale > 0:
            gaps.append(
                _gap(
                    audit_id=audit_id,
                    scope_type="release_source_country",
                    field_name="status_stale_366_plus_days",
                    severity=("low" if group["release_review_only"] else "medium"),
                    child_release=group["child_release"],
                    source_family=group["source_family"],
                    country=(
                        None if group["country"] == UNRESOLVED else group["country"]
                    ),
                    affected_records=stale,
                    denominator_records=denominator,
                    detail="Lifecycle status date is more than 366 days older than the audit reference date.",
                )
            )
        invalid_or_future = sum(
            group["status_freshness_counts"].get(bucket, 0)
            for bucket in ("future", "invalid")
        )
        if invalid_or_future > 0:
            gaps.append(
                _gap(
                    audit_id=audit_id,
                    scope_type="release_source_country",
                    field_name="status_date_invalid_or_future",
                    severity="high",
                    child_release=group["child_release"],
                    source_family=group["source_family"],
                    country=(
                        None if group["country"] == UNRESOLVED else group["country"]
                    ),
                    affected_records=invalid_or_future,
                    denominator_records=denominator,
                    detail="Lifecycle status date is invalid or later than the audit reference date.",
                )
            )
    benchmark_severity = {
        "capacity_outputs": "high",
        "construction_timeline_pjm": "high",
        "evidence_methodology": "high",
        "facility_scope_count": "high",
        "temporal_granularity": "high",
    }
    for item in comparison["comparisons"]:
        gaps.append(
            _gap(
                audit_id=audit_id,
                scope_type="benchmark",
                field_name=f"semianalysis_public_{item['claim_id']}",
                severity=benchmark_severity[item["claim_id"]],
                child_release=None,
                source_family=None,
                country=None,
                affected_records=None,
                denominator_records=None,
                detail=(
                    f"Public-claim comparison status is {item['atlas_status']}; "
                    "licensed row-level parity remains pending."
                ),
            )
        )
    gaps.extend(
        [
            _gap(
                audit_id=audit_id,
                scope_type="federation",
                field_name="unique_physical_sites",
                severity="high",
                child_release=None,
                source_family=None,
                country=None,
                affected_records=None,
                denominator_records=None,
                detail="Unique physical-site count is unknown because cross-source deduplication has not occurred.",
            ),
            _gap(
                audit_id=audit_id,
                scope_type="benchmark",
                field_name="licensed_row_level_benchmark",
                severity="high",
                child_release=None,
                source_family=None,
                country=None,
                affected_records=None,
                denominator_records=None,
                detail=comparison["licensed_row_level_benchmark"]["reason"],
            ),
            _gap(
                audit_id=audit_id,
                scope_type="benchmark",
                field_name="parity",
                severity="high",
                child_release=None,
                source_family=None,
                country=None,
                affected_records=None,
                denominator_records=None,
                detail=comparison["overall_parity"]["reason"],
            ),
        ]
    )
    gaps.sort(
        key=lambda item: (
            item["scope_type"],
            item["child_release"] or "",
            item["source_family"] or "",
            item["country"] or "",
            item["field"],
        )
    )
    severity_counts = Counter(gap["severity"] for gap in gaps)
    field_counts = Counter(gap["field"] for gap in gaps)
    return {
        "schema_version": SCHEMA_VERSION,
        "format": GAP_FORMAT,
        "audit_id": audit_id,
        "generated_at": generated_at,
        "summary": {
            "open_gaps": len(gaps),
            "by_severity": dict(sorted(severity_counts.items())),
            "by_field": dict(sorted(field_counts.items())),
        },
        "gaps": gaps,
    }


def _coverage_csv(groups: list[Mapping[str, Any]]) -> bytes:
    identity_fields = [
        "scope_type",
        "child_release",
        "child_release_as_of",
        "release_review_only",
        "source_family",
        "country",
        "country_iso_a2",
        "country_iso_a3",
    ]
    fieldnames = (
        identity_fields
        + sorted(set(groups[0]) - set(identity_fields))
        if groups
        else []
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for group in groups:
        row = dict(group)
        for field_name in MAP_FIELDS:
            row[field_name] = _compact_json(row[field_name])
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _report(audit: Mapping[str, Any], gaps: Mapping[str, Any]) -> bytes:
    totals = audit["totals"]
    fields = totals["field_totals"]
    scope = audit["scope"]
    release_groups = [
        group for group in audit["groups"] if group["scope_type"] == "release"
    ]
    if scope["scrutica_included"]:
        coverage_boundary = (
            "- Coverage boundary: **hash-pinned federation layers including "
            "review-only Scrutica rows**"
        )
    else:
        coverage_boundary = (
            "- Coverage boundary: **provisional open layers only; Scrutica is not "
            "included**"
        )
    lines = [
        f"# Global coverage and field-completeness audit — {audit['generated_at'][:10]}",
        "",
        "This is an audit of source-scoped release rows, not a facility census. It does not merge child rows, resolve advisory relationships, promote review candidates, or estimate unique physical sites.",
        "",
        "## Boundary", "",
        f"- Source-scoped rows: **{totals['source_scoped_entity_records']:,}**",
        coverage_boundary,
        f"- Non-review rows: **{totals['non_review_source_scoped_entity_records']:,}**",
        f"- Review-only leads: **{totals['review_only_source_scoped_entity_records']:,}**",
        f"- Advisory resolution suggestions: **{totals['advisory_resolution_candidate_records']:,}** (not confirmed duplicates)",
        "- Confirmed duplicate relationships: **unknown**",
        "- Unique physical sites: **unknown**",
        "- SemiAnalysis licensed row-level benchmark: **pending**",
        "- SemiAnalysis parity determination: **pending**",
        "",
        "Review-only rows retain their source-declared entity-kind labels for schema auditing, but are excluded from non-review kind totals and are never counted as facilities here.",
        "",
        "## Child release coverage", "",
        "| Child release | Scope | Rows | Coordinates | Country | Status claim | Informative lifecycle | Capacity | Annual energy | Operating model | Workload |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in release_groups:
        scope = "review-only" if group["release_review_only"] else "non-review"
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_escape(group["child_release"]),
                    scope,
                    f"{group['source_scoped_rows']:,}",
                    _percentage(group["coordinate_coverage"]),
                    _percentage(group["country_coverage"]),
                    _percentage(group["complete_lifecycle_claim_coverage"]),
                    _percentage(group["informative_lifecycle_status_coverage"]),
                    _percentage(group["capacity_entity_coverage"]),
                    _percentage(group["annual_energy_entity_coverage"]),
                    _percentage(group["operating_model_coverage"]),
                    _percentage(group["workload_coverage"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Construction and capacity observations",
            "",
            f"There are {fields['non_review_under_construction_rows']:,} non-review source rows marked `under_construction` and {fields['review_only_under_construction_lead_rows']:,} review-only under-construction leads. Distinct construction status evidence IDs ({fields['construction_evidence_observations']:,}) are evidence observations, not sites.",
            "",
            f"Capacity observations: `{_compact_json(fields['capacity_metric_counts'])}`",
            "",
            f"Capacity stages: `{_compact_json(fields['capacity_stage_counts'])}`",
            "",
            f"Annual-energy methods: `{_compact_json(fields['annual_energy_method_counts'])}`. These method labels and the evidence-family/license joins in the JSON/CSV are provenance; no annual-energy row is treated as metered unless its source method says so.",
            "",
            "## SemiAnalysis public benchmark",
            "",
            "Only the cited public claims are compared. The licensed model was not accessed, so row-level coverage and parity remain pending.",
            "",
            "| Public claim | Atlas audit status | Source |",
            "|---|---|---|",
        ]
    )
    for comparison in audit["semianalysis_public_comparison"]["comparisons"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _markdown_escape(comparison["paraphrase"]),
                    _markdown_escape(comparison["atlas_status"]),
                    f"[public page]({comparison['source_url']})",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Machine-readable gaps",
            "",
            f"The gap registry contains **{gaps['summary']['open_gaps']:,}** deterministic open entries. Counts by severity: `{_compact_json(gaps['summary']['by_severity'])}`.",
            "",
            "Low-severity absence for capacity, energy, operating model, or workload is a completeness target, not an assertion that every row should have that attribute. Country and coordinate gaps are prioritized because they block geographic coverage analysis.",
            "",
            "See `coverage.csv`, `coverage-audit.json`, and `gap-registry.json` for exact release/source/country measurements. `manifest.json` and `manifest.sha256` bind every byte in this bundle.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def build_coverage_audit(definition_path: str | Path) -> CoverageAuditBundle:
    """Validate exact inputs and construct the complete audit in memory."""
    definition_path = Path(definition_path)
    definition = _definition(definition_path)
    federation_manifest_raw = _regular_bytes(
        definition.federation_path / MANIFEST_FILENAME,
        "federated index manifest",
    )
    federation_manifest_sha256 = hashlib.sha256(federation_manifest_raw).hexdigest()
    if federation_manifest_sha256 != definition.expected_federation_manifest_sha256:
        raise CoverageAuditError("federated index manifest SHA-256 does not match")
    child_paths = {
        child.release_id: child.release_path for child in definition.children
    }
    try:
        federation = validate_federated_release_index(
            definition.federation_path, child_release_paths=child_paths
        )
    except ValueError as error:
        raise CoverageAuditError(f"federated input validation failed: {error}") from error
    descriptors = {release["release_id"]: release for release in federation["releases"]}
    if set(descriptors) != set(child_paths):
        raise CoverageAuditError("audit children do not exactly match federation")
    for child in definition.children:
        if descriptors[child.release_id]["manifest"]["sha256"] != child.expected_manifest_sha256:
            raise CoverageAuditError(
                f"{child.release_id} manifest SHA-256 does not match audit definition"
            )
    methodology_evidence = _resolve_methodology_evidence(
        definition.methodology_evidence_classification,
        children=definition.children,
        descriptors=descriptors,
    )

    groups: list[dict[str, Any]] = []
    total_stats = _Stats()
    input_children: list[dict[str, Any]] = []
    entity_source_families: set[str] = set()
    for child in definition.children:
        descriptor = descriptors[child.release_id]
        release_groups, release_stats, entity_sources = _inspect_release(
            child, descriptor, definition.generated_on
        )
        groups.extend(release_groups)
        _merge_stats(total_stats, release_stats)
        entity_source_families.update(entity_sources)
        input_children.append(
            {
                "release_id": child.release_id,
                "reference": descriptor["reference"],
                "review_only": descriptor["scope"]["review_only"],
                "manifest": descriptor["manifest"],
                "atlas_geojson": descriptor["files"]["atlas.geojson"],
                "evidence_csv": descriptor["files"]["evidence.csv"],
                "declared_source_families": descriptor["source_families"],
            }
        )
    groups.sort(
        key=lambda group: (
            group["child_release"],
            {"release": 0, "release_source": 1, "release_source_country": 2}[
                group["scope_type"]
            ],
            group["source_family"],
            group["country"],
            group["country_iso_a2"] or "",
            group["country_iso_a3"] or "",
        )
    )
    federated_counts = federation["counts"]
    totals = {
        "source_scoped_entity_records": federated_counts[
            "source_scoped_entity_records"
        ],
        "non_review_source_scoped_entity_records": federated_counts[
            "non_review_source_scoped_entity_records"
        ],
        "review_only_source_scoped_entity_records": federated_counts[
            "review_only_source_scoped_entity_records"
        ],
        "advisory_resolution_candidate_records": federated_counts[
            "resolution_candidates"
        ],
        "confirmed_duplicate_relationships": None,
        "unique_physical_sites": None,
        "field_totals": total_stats.export(),
    }
    if totals["source_scoped_entity_records"] != total_stats.rows:
        raise CoverageAuditError("audit rows do not reconcile with federation")
    scrutica_included = any(
        source_family == "scrutica" or source_family.startswith("scrutica:")
        for child in input_children
        for source_family in child["declared_source_families"]
    )
    comparison = _benchmark_comparison(
        definition.public_benchmark,
        totals,
        methodology_evidence,
    )
    audit = {
        "schema_version": SCHEMA_VERSION,
        "format": AUDIT_FORMAT,
        "audit_id": definition.audit_id,
        "generated_at": definition.generated_at,
        "scope": {
            "unit": "source_scoped_release_row",
            "provisional_open_layer_audit": not scrutica_included,
            "scrutica_included": scrutica_included,
            "children_merged": False,
            "cross_source_deduplication": False,
            "review_candidates_promoted": False,
            "review_only_rows_separately_counted": True,
            "source_declared_entity_kind_is_not_a_physical_site_count": True,
            "advisory_resolution_candidates_are_confirmed_duplicates": False,
            "confirmed_duplicate_relationships": None,
            "unique_physical_sites": None,
            "candidate_rows_counted_as_facilities": False,
        },
        "freshness_buckets": {
            "reference_date": definition.generated_on.isoformat(),
            "buckets": [
                "0_90_days",
                "91_365_days",
                "366_plus_days",
                "future",
                "invalid",
                "missing",
            ],
        },
        "inputs": {
            "federated_index": {
                "format": federation["format"],
                "generated_at": federation["generated_at"],
                "manifest": {
                    "bytes": len(federation_manifest_raw),
                    "sha256": federation_manifest_sha256,
                },
                "index": {
                    "bytes": (definition.federation_path / "federated-index.json").stat().st_size,
                    "sha256": hashlib.sha256(
                        (definition.federation_path / "federated-index.json").read_bytes()
                    ).hexdigest(),
                },
            },
            "children": input_children,
        },
        "entity_source_families": sorted(entity_source_families),
        "totals": totals,
        "groups": groups,
        "semianalysis_public_comparison": comparison,
    }
    gaps = _gap_registry(
        definition.audit_id, definition.generated_at, groups, comparison
    )
    audit_bytes = _canonical_json(audit)
    gaps_bytes = _canonical_json(gaps)
    csv_bytes = _coverage_csv(groups)
    report_bytes = _report(audit, gaps)
    artifacts = {
        AUDIT_FILENAME: audit_bytes,
        COVERAGE_CSV_FILENAME: csv_bytes,
        GAP_REGISTRY_FILENAME: gaps_bytes,
        REPORT_FILENAME: report_bytes,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": BUNDLE_FORMAT,
        "audit_id": definition.audit_id,
        "generated_at": definition.generated_at,
        "definition": {
            "file": definition.filename,
            "bytes": len(definition.raw),
            "sha256": hashlib.sha256(definition.raw).hexdigest(),
        },
        "inputs": {
            "federated_manifest_sha256": federation_manifest_sha256,
            "child_manifest_sha256": {
                child.release_id: child.expected_manifest_sha256
                for child in definition.children
            },
        },
        "scope": audit["scope"],
        "counts": {
            "source_scoped_entity_records": totals[
                "source_scoped_entity_records"
            ],
            "non_review_source_scoped_entity_records": totals[
                "non_review_source_scoped_entity_records"
            ],
            "review_only_source_scoped_entity_records": totals[
                "review_only_source_scoped_entity_records"
            ],
            "coverage_groups": len(groups),
            "open_gaps": gaps["summary"]["open_gaps"],
            "confirmed_duplicate_relationships": None,
            "unique_physical_sites": None,
        },
        "artifacts": {
            filename: {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for filename, raw in sorted(artifacts.items())
        },
    }
    manifest_bytes = _canonical_json(manifest)
    sidecar_bytes = (
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    payloads = {
        **artifacts,
        MANIFEST_FILENAME: manifest_bytes,
        MANIFEST_HASH_FILENAME: sidecar_bytes,
    }
    return CoverageAuditBundle(
        payloads=payloads, audit=audit, gaps=gaps, manifest=manifest
    )


def validate_coverage_audit(
    directory_path: str | Path,
    *,
    definition_path: str | Path | None = None,
) -> Mapping[str, Any]:
    """Validate the closed audit bundle and optionally recheck exact inputs."""
    directory = Path(directory_path)
    if directory.is_symlink() or not directory.is_dir():
        raise CoverageAuditError(f"audit bundle must be a regular directory: {directory}")
    entries = list(directory.iterdir())
    names = {entry.name for entry in entries}
    if names != AUDIT_BUNDLE_FILES or len(entries) != len(AUDIT_BUNDLE_FILES):
        raise CoverageAuditError("audit bundle file set is invalid")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise CoverageAuditError(f"audit entry must be a regular file: {entry.name}")
    payloads = {entry.name: entry.read_bytes() for entry in entries}
    manifest_raw = payloads[MANIFEST_FILENAME]
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if payloads[MANIFEST_HASH_FILENAME] != expected_sidecar:
        raise CoverageAuditError("audit manifest sidecar does not match")
    manifest = _json_object(manifest_raw, "audit manifest")
    audit = _json_object(payloads[AUDIT_FILENAME], "coverage audit")
    gaps = _json_object(payloads[GAP_REGISTRY_FILENAME], "gap registry")
    for value, raw, label in (
        (manifest, manifest_raw, "audit manifest"),
        (audit, payloads[AUDIT_FILENAME], "coverage audit"),
        (gaps, payloads[GAP_REGISTRY_FILENAME], "gap registry"),
    ):
        if raw != _canonical_json(value):
            raise CoverageAuditError(f"{label} is not canonical JSON")
    if manifest.get("format") != BUNDLE_FORMAT or manifest.get("schema_version") != SCHEMA_VERSION:
        raise CoverageAuditError("audit manifest identity is invalid")
    if audit.get("format") != AUDIT_FORMAT or audit.get("schema_version") != SCHEMA_VERSION:
        raise CoverageAuditError("coverage audit identity is invalid")
    if gaps.get("format") != GAP_FORMAT or gaps.get("schema_version") != SCHEMA_VERSION:
        raise CoverageAuditError("gap registry identity is invalid")
    if not (
        manifest.get("audit_id") == audit.get("audit_id") == gaps.get("audit_id")
        and manifest.get("generated_at")
        == audit.get("generated_at")
        == gaps.get("generated_at")
    ):
        raise CoverageAuditError("audit bundle identities do not reconcile")
    artifacts = manifest.get("artifacts")
    expected_artifacts = AUDIT_BUNDLE_FILES - {
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }
    if not isinstance(artifacts, Mapping) or set(artifacts) != expected_artifacts:
        raise CoverageAuditError("audit artifact inventory is invalid")
    for filename, checkpoint in artifacts.items():
        if not isinstance(checkpoint, Mapping) or set(checkpoint) != {"bytes", "sha256"}:
            raise CoverageAuditError(f"audit checkpoint schema is invalid: {filename}")
        raw = payloads[filename]
        if checkpoint.get("bytes") != len(raw) or checkpoint.get("sha256") != hashlib.sha256(raw).hexdigest():
            raise CoverageAuditError(f"audit artifact checkpoint mismatch: {filename}")
    groups = audit.get("groups")
    if not isinstance(groups, list) or not groups:
        raise CoverageAuditError("coverage groups must be a non-empty array")
    group_order = [
        (
            group.get("child_release"),
            {"release": 0, "release_source": 1, "release_source_country": 2}.get(
                group.get("scope_type"), 99
            ),
            group.get("source_family"),
            group.get("country"),
            group.get("country_iso_a2") or "",
            group.get("country_iso_a3") or "",
        )
        for group in groups
        if isinstance(group, Mapping)
    ]
    if len(group_order) != len(groups) or group_order != sorted(set(group_order)):
        raise CoverageAuditError("coverage groups must be sorted and unique")
    scope = audit.get("scope")
    inputs = audit.get("inputs")
    input_children = inputs.get("children") if isinstance(inputs, Mapping) else None
    if not isinstance(input_children, list):
        raise CoverageAuditError("coverage audit inputs are invalid")
    expected_scrutica_included = any(
        isinstance(source_family, str)
        and (
            source_family == "scrutica"
            or source_family.startswith("scrutica:")
        )
        for child in input_children
        if isinstance(child, Mapping)
        for source_family in child.get("declared_source_families", [])
    )
    if not isinstance(scope, Mapping) or (
        scope.get("unit") != "source_scoped_release_row"
        or scope.get("scrutica_included") is not expected_scrutica_included
        or scope.get("provisional_open_layer_audit")
        is not (not expected_scrutica_included)
        or scope.get("children_merged") is not False
        or scope.get("cross_source_deduplication") is not False
        or scope.get("review_candidates_promoted") is not False
        or scope.get("candidate_rows_counted_as_facilities") is not False
        or scope.get("confirmed_duplicate_relationships") is not None
        or scope.get("unique_physical_sites") is not None
    ):
        raise CoverageAuditError("coverage audit scope policy is invalid")
    totals = audit.get("totals")
    release_groups = [group for group in groups if group["scope_type"] == "release"]
    if not isinstance(totals, Mapping) or (
        totals.get("source_scoped_entity_records")
        != sum(group["source_scoped_rows"] for group in release_groups)
        or totals.get("non_review_source_scoped_entity_records")
        != sum(group["non_review_rows"] for group in release_groups)
        or totals.get("review_only_source_scoped_entity_records")
        != sum(group["review_only_rows"] for group in release_groups)
        or totals.get("confirmed_duplicate_relationships") is not None
        or totals.get("unique_physical_sites") is not None
    ):
        raise CoverageAuditError("coverage totals do not reconcile")
    gap_values = gaps.get("gaps")
    gap_summary = gaps.get("summary")
    if not isinstance(gap_values, list) or not isinstance(gap_summary, Mapping):
        raise CoverageAuditError("gap registry payload is invalid")
    if not all(isinstance(gap, Mapping) for gap in gap_values):
        raise CoverageAuditError("gap registry entries must be objects")
    gap_ids = [
        gap.get("gap_id") for gap in gap_values
    ]
    expected_gap_order = sorted(
        gap_values,
        key=lambda item: (
            item["scope_type"],
            item["child_release"] or "",
            item["source_family"] or "",
            item["country"] or "",
            item["field"],
        ),
    )
    severity_counts = Counter(gap["severity"] for gap in gap_values)
    field_counts = Counter(gap["field"] for gap in gap_values)
    if (
        len(gap_ids) != len(gap_values)
        or len(set(gap_ids)) != len(gap_ids)
        or gap_values != expected_gap_order
        or gap_summary.get("open_gaps") != len(gap_values)
        or gap_summary.get("by_severity") != dict(sorted(severity_counts.items()))
        or gap_summary.get("by_field") != dict(sorted(field_counts.items()))
    ):
        raise CoverageAuditError("gap registry counts or ordering do not reconcile")
    if payloads[COVERAGE_CSV_FILENAME] != _coverage_csv(groups):
        raise CoverageAuditError("coverage CSV does not reconcile with JSON")
    if payloads[REPORT_FILENAME] != _report(audit, gaps):
        raise CoverageAuditError("audit report does not reconcile with JSON")
    manifest_counts = manifest.get("counts")
    if not isinstance(manifest_counts, Mapping) or (
        manifest_counts.get("coverage_groups") != len(groups)
        or manifest_counts.get("open_gaps") != gaps.get("summary", {}).get("open_gaps")
        or manifest_counts.get("source_scoped_entity_records")
        != audit.get("totals", {}).get("source_scoped_entity_records")
        or manifest_counts.get("non_review_source_scoped_entity_records")
        != audit.get("totals", {}).get("non_review_source_scoped_entity_records")
        or manifest_counts.get("review_only_source_scoped_entity_records")
        != audit.get("totals", {}).get("review_only_source_scoped_entity_records")
        or manifest_counts.get("confirmed_duplicate_relationships") is not None
        or manifest_counts.get("unique_physical_sites") is not None
    ):
        raise CoverageAuditError("audit manifest counts do not reconcile")
    if definition_path is not None:
        rebuilt = build_coverage_audit(definition_path)
        if dict(rebuilt.payloads) != payloads:
            raise CoverageAuditError("audit bytes drifted from exact source inputs")
    return audit


def _write_bytes(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_coverage_audit(
    definition_path: str | Path, output_directory: str | Path
) -> Mapping[str, Any]:
    """Atomically publish an immutable audit bundle."""
    bundle = build_coverage_audit(definition_path)
    output = Path(output_directory)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        validate_coverage_audit(output, definition_path=definition_path)
        existing = {path.name: path.read_bytes() for path in output.iterdir()}
        if existing != dict(bundle.payloads):
            raise CoverageAuditError("existing valid audit differs from requested bytes")
        return bundle.audit
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        for filename, raw in sorted(bundle.payloads.items()):
            _write_bytes(staging / filename, raw)
        _fsync_directory(staging)
        validate_coverage_audit(staging)
        if output.exists() or output.is_symlink():
            raise CoverageAuditError(
                f"coverage audit output appeared during publication: {output}"
            )
        os.rename(staging, output)
        _fsync_directory(parent)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return bundle.audit
