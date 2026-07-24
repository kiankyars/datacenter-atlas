"""Typed canonical entities and evidence-backed observation models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class EntityKind(StrEnum):
    CAMPUS = "campus"
    FACILITY = "facility"
    BUILDING = "building"
    PROJECT = "project"


class LifecycleStatus(StrEnum):
    LEAD = "lead"
    CANDIDATE = "candidate"
    ANNOUNCED = "announced"
    PROPOSED = "proposed"
    SITE_CONTROL = "site_control"
    PERMITTING = "permitting"
    PERMITTED = "permitted"
    SITE_PREPARATION = "site_preparation"
    CLEARING = "clearing"
    CIVIL_WORKS = "civil_works"
    FOUNDATIONS = "foundations"
    SHELL = "shell"
    MEP_ELECTRICAL = "mep_electrical"
    UNDER_CONSTRUCTION = "under_construction"
    COMMISSIONING = "commissioning"
    OPERATIONAL = "operational"
    EXPANSION = "expansion"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    REPURPOSED = "repurposed"
    DECOMMISSIONED = "decommissioned"
    DEMOLISHED = "demolished"
    UNKNOWN = "unknown"


ACTIVE_PIPELINE_STATUSES = frozenset(
    {
        LifecycleStatus.LEAD.value,
        LifecycleStatus.CANDIDATE.value,
        LifecycleStatus.ANNOUNCED.value,
        LifecycleStatus.PROPOSED.value,
        LifecycleStatus.SITE_CONTROL.value,
        LifecycleStatus.PERMITTING.value,
        LifecycleStatus.PERMITTED.value,
        LifecycleStatus.SITE_PREPARATION.value,
        LifecycleStatus.CLEARING.value,
        LifecycleStatus.CIVIL_WORKS.value,
        LifecycleStatus.FOUNDATIONS.value,
        LifecycleStatus.SHELL.value,
        LifecycleStatus.MEP_ELECTRICAL.value,
        LifecycleStatus.UNDER_CONSTRUCTION.value,
        LifecycleStatus.COMMISSIONING.value,
        LifecycleStatus.EXPANSION.value,
    }
)


class AdministrativeResolutionStatus(StrEnum):
    ASSIGNED = "assigned"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    BOUNDARY = "boundary"


class OperatingModel(StrEnum):
    HYPERSCALER = "hyperscaler"
    HYPERSCALE_SELF_BUILD = "hyperscale_self_build"
    HYPERSCALE_LEASE = "hyperscale_lease"
    COLOCATION = "colocation"
    WHOLESALE_COLOCATION = "wholesale_colocation"
    RETAIL_COLOCATION = "retail_colocation"
    NEOCLOUD = "neocloud"
    ENTERPRISE_PRIVATE = "enterprise_private"
    GOVERNMENT_RESEARCH = "government_research"
    SOVEREIGN_RESEARCH = "sovereign_research"
    EDGE = "edge"
    TELECOM_EDGE = "telecom_edge"
    UNKNOWN = "unknown"


class Workload(StrEnum):
    AI_SPECIALIZED_UNSPECIFIED = "ai_specialized_unspecified"
    AI_TRAINING = "ai_training"
    AI_INFERENCE = "ai_inference"
    HPC = "hpc"
    GENERAL_CLOUD = "general_cloud"
    ENTERPRISE_IT = "enterprise_it"
    CONTENT_DELIVERY = "content_delivery"
    CRYPTO_MINING = "crypto_mining"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class CapacityMetric(StrEnum):
    GRID_CONNECTION_MW = "grid_connection_mw"
    GROSS_FACILITY_MW = "gross_facility_mw"
    CRITICAL_IT_MW = "critical_it_mw"
    GENERATION_NAMEPLATE_MW = "generation_nameplate_mw"
    ANNUAL_ENERGY_MWH = "annual_energy_mwh"
    PUE = "pue"

    @property
    def unit(self) -> str:
        if self is CapacityMetric.ANNUAL_ENERGY_MWH:
            return "MWh/year"
        if self is CapacityMetric.PUE:
            return "ratio"
        return "MW"


class EstimateMethod(StrEnum):
    REPORTED = "reported"
    CALCULATED = "calculated"
    PERMIT_INFERENCE = "permit_inference"
    EQUIPMENT_INFERENCE = "equipment_inference"
    IMAGERY_INFERENCE = "imagery_inference"
    MODELED = "modeled"
    UNKNOWN = "unknown"


class CapacityStage(StrEnum):
    REQUESTED = "requested"
    CONTRACTED = "contracted"
    DESIGN = "design"
    PLANNED = "planned"
    INSTALLED = "installed"
    ENERGIZED = "energized"
    OPERATIONAL = "operational"
    MEASURED = "measured"
    FORECAST = "forecast"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    GOVERNMENT_RECORD = "government_record"
    COMPANY_DISCLOSURE = "company_disclosure"
    UTILITY_RECORD = "utility_record"
    EQUIPMENT_ORDER = "equipment_order"
    SATELLITE_IMAGERY = "satellite_imagery"
    OPENSTREETMAP = "openstreetmap"
    THIRD_PARTY_DATASET = "third_party_dataset"
    NEWS = "news"
    OTHER = "other"


def _required(value: str, field: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field} is required")


def _confidence(value: float) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    kind: EvidenceKind
    title: str
    source_url: str
    retrieved_at: str
    publisher: str | None = None
    source_family: str | None = None
    license: str | None = None
    attribution: str | None = None
    published_at: str | None = None
    excerpt: str | None = None

    def __post_init__(self) -> None:
        for field in ("id", "title", "source_url", "retrieved_at"):
            _required(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class Campus:
    id: str
    stable_key: str
    created_from_evidence_id: str


@dataclass(frozen=True, slots=True)
class Facility:
    id: str
    stable_key: str
    created_from_evidence_id: str
    campus_id: str | None = None


@dataclass(frozen=True, slots=True)
class Building:
    id: str
    stable_key: str
    created_from_evidence_id: str
    facility_id: str = ""

    def __post_init__(self) -> None:
        _required(self.facility_id, "facility_id")


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    stable_key: str
    created_from_evidence_id: str
    target_entity_id: str

    def __post_init__(self) -> None:
        _required(self.target_entity_id, "target_entity_id")


@dataclass(frozen=True, slots=True)
class LifecycleObservation:
    id: str
    entity_id: str
    status: LifecycleStatus
    evidence_id: str
    as_of_date: str
    recorded_at: str
    method: str
    confidence: float

    def __post_init__(self) -> None:
        for field in ("id", "entity_id", "evidence_id", "as_of_date", "recorded_at", "method"):
            _required(getattr(self, field), field)
        _confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class CapacityEstimate:
    id: str
    entity_id: str
    metric: CapacityMetric
    low: float
    base: float
    high: float
    method: EstimateMethod
    confidence: float
    evidence_id: str
    as_of_date: str
    recorded_at: str
    stage: CapacityStage = CapacityStage.UNKNOWN
    target_date: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        for field in ("id", "entity_id", "evidence_id", "as_of_date", "recorded_at"):
            _required(getattr(self, field), field)
        if not all(isfinite(value) for value in (self.low, self.base, self.high)):
            raise ValueError("capacity estimate values must be finite")
        if self.low < 0 or not self.low <= self.base <= self.high:
            raise ValueError("capacity estimate must satisfy 0 <= low <= base <= high")
        if self.metric is CapacityMetric.PUE and self.low <= 0:
            raise ValueError("PUE must be greater than zero")
        _confidence(self.confidence)


@dataclass(frozen=True, slots=True)
class AdministrativeAssignment:
    id: str
    entity_id: str
    resolution_status: AdministrativeResolutionStatus
    country_name: str | None
    iso_a2: str | None
    iso_a3: str | None
    source_admin: str | None
    source_sovereignt: str | None
    source_type: str | None
    source_note_adm0: str | None
    source_note_brk: str | None
    source_feature_id: str | None
    match_feature_ids_json: str
    source_country_tag: str | None
    coordinate_snapshot_id: str
    boundary_evidence_id: str
    as_of_date: str
    recorded_at: str
    method: str
    confidence: float
    notes: str | None = None

    def __post_init__(self) -> None:
        for field in (
            "id",
            "entity_id",
            "match_feature_ids_json",
            "coordinate_snapshot_id",
            "boundary_evidence_id",
            "as_of_date",
            "recorded_at",
            "method",
        ):
            _required(getattr(self, field), field)
        if self.iso_a2 is not None and len(self.iso_a2) != 2:
            raise ValueError("iso_a2 must contain two characters")
        if self.iso_a3 is not None and len(self.iso_a3) != 3:
            raise ValueError("iso_a3 must contain three characters")
        if self.resolution_status is AdministrativeResolutionStatus.ASSIGNED:
            _required(self.country_name or "", "country_name")
            _required(self.source_feature_id or "", "source_feature_id")
        elif any(
            value is not None
            for value in (
                self.country_name,
                self.iso_a2,
                self.iso_a3,
                self.source_feature_id,
            )
        ):
            raise ValueError("unresolved assignments cannot contain a selected country")
        _confidence(self.confidence)
