"""Govern and publish the official-source GDH DSO4-6 current-build artifact.

The first-party Dubai page labels DSO4, DSO5, and DSO6 under construction at
the response-date observation.  Its 4.2-16 MW text is a range across six Dubai
locations and is not allocated to any individual site.  This module therefore
creates three source-scoped identity/lifecycle records with no capacity,
coordinate, geometry, operating-model, workload, PUE, or persistence claim.

Private prepublication remains the safe default.  Final publication additionally
requires ``publication_authorized=True`` and crosses a live timestamp barrier
through unique same-filesystem stages, no-replace promotion, rollback, and
recursive chronology checks.
"""

from __future__ import annotations

import csv
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import html
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .open_seed_v69 import promote_noreplace
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "gulf-data-hub-dubai-dso456-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".gdh-dubai-dso456-official-current-build-gap.lock"

CAPTURE_ROOT = Path("/private/tmp/dc-gdh-dubai-20260722.y70kIO")
CAPTURE_STARTED_AT = "2026-07-22T04:26:42Z"
RETRIEVED_AT = "2026-07-22T04:26:43Z"
CAPTURE_FILE_COUNT = 3
CAPTURE_TOTAL_BYTES = 80_499
CAPTURE_TREE_SHA256 = "dc6f3f94e1f56b328be19afdd48ffc9c022dc8c216e70f32f6b7756c0758f6d7"
CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "gdh_dubai.body": (
        80_027,
        "206496676380841bb0250953101fcbd6f9d0f68a2693317442db840892a3d5f5",
    ),
    "gdh_dubai.headers": (
        250,
        "7964fa5dd3998a1d837b045357c020b63279f98d677da58055f364708995d8c1",
    ),
    "gdh_dubai.writeout": (
        222,
        "73fe6dded47df16eed005fd1c3342adb04d0a62fe84747f02a5b7e775a40cb7b",
    ),
}

SOURCE_URL = "https://www.gulfdatahub.ae/dubai"
STATUS_WORDING = "DSO 4, DSO 5 and DSO 6 are under construction."
CAPACITY_WORDING = "the capacity ranges between 4.2 to 16 MW."

SOURCE_FILENAMES = tuple(
    f"curated-official-2026-07-22-gulf-data-hub-dubai-dso{number}-current-build.json"
    for number in (4, 5, 6)
)
SOURCE_PATHS = tuple(f"sources/{name}" for name in SOURCE_FILENAMES)

V95_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v95.json"
V95_RELEASE = ROOT / "releases/2026-07-22-open-seed-v95"
V95_MANIFEST = V95_RELEASE / "manifest.json"
V95_ENTITIES = V95_RELEASE / "entities.csv"
V95_SOURCE_INPUTS = V95_RELEASE / "source_inputs.json"
V95_PINS: Mapping[Path, tuple[int, str]] = {
    V95_DEFINITION: (
        117_088,
        "e28cc9ad10229cbf718314f1bd1a4306e02faee1166dcbfbf93c01a1c82e8e15",
    ),
    V95_MANIFEST: (
        19_195,
        "1181fa215be08c130bf237107c68a461a4762e020b7120041f19cd705b6b7af6",
    ),
    V95_ENTITIES: (
        1_058_933,
        "038bfa4ef15e4e6494ac91fa835671105d45662c0acd6b6f5c3a5e750ad3e09d",
    ),
    V95_SOURCE_INPUTS: (
        432_685,
        "30572edcc50ecf82c5de57abf7a7e10275a09b879189334834a512d9280860d0",
    ),
}
V95_TREE_SHA256 = "752593650007f602f2bd13f2bd0c3ac8702cdd74c4b6103ec2bdaa348c6ef17a"
V95_RELEASE_ID = "2026-07-22-open-seed-v95"
V95_INPUT_COUNT = 507
V95_ENTITY_COUNT = 1_029

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


class GulfDataHubDubaiGapError(RuntimeError):
    """Raised when a capture, semantic, collision, or prepublication fuse fails."""


def _canonical(value: Any, *, sort_keys: bool = False) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _content_tree_sha256(root: Path) -> str:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat(follow_symlinks=False).st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ]
    return _sha256_bytes(_canonical(rows, sort_keys=True))


def _instant(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GulfDataHubDubaiGapError(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GulfDataHubDubaiGapError(f"{label} is invalid") from error
    if parsed.microsecond:
        raise GulfDataHubDubaiGapError(f"{label} must use whole seconds")
    return parsed.astimezone(UTC)


def _pin(path: Path, expected: tuple[int, str], label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GulfDataHubDubaiGapError(f"{label} is not an ordinary file")
    raw = path.read_bytes()
    if (len(raw), _sha256_bytes(raw)) != expected:
        raise GulfDataHubDubaiGapError(f"{label} pin differs")
    return raw


def _rendered_text(raw: bytes) -> str:
    text = raw.decode("utf-8")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def validate_private_capture() -> dict[str, Any]:
    if (
        CAPTURE_ROOT.is_symlink()
        or not CAPTURE_ROOT.is_dir()
        or stat.S_IMODE(CAPTURE_ROOT.stat().st_mode) != 0o555
    ):
        raise GulfDataHubDubaiGapError("private capture root is absent or unfrozen")
    entries = {path.name: path for path in CAPTURE_ROOT.iterdir()}
    if (
        set(entries) != set(CAPTURE_FILE_PINS)
        or len(entries) != CAPTURE_FILE_COUNT
        or any(
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
            for path in entries.values()
        )
    ):
        raise GulfDataHubDubaiGapError("private capture closed set differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin, f"private capture {name}")
    if (
        sum(path.stat().st_size for path in entries.values()) != CAPTURE_TOTAL_BYTES
        or tree_digest(CAPTURE_ROOT) != CAPTURE_TREE_SHA256
    ):
        raise GulfDataHubDubaiGapError("private capture aggregate differs")

    headers = entries["gdh_dubai.headers"].read_text(encoding="utf-8")
    writeout = json.loads(entries["gdh_dubai.writeout"].read_text())
    rendered = _rendered_text(entries["gdh_dubai.body"].read_bytes())
    if (
        "HTTP/1.1 200 OK" not in headers
        or "Date: Wed, 22 Jul 2026 04:26:43 GMT" not in headers
        or "Content-Type: text/html; charset=utf-8" not in headers
        or writeout
        != {
            "http_code": 200,
            "url_effective": SOURCE_URL,
            "content_type": "text/html; charset=utf-8",
            "remote_ip": "13.207.136.21",
            "ssl_verify_result": 0,
            "num_redirects": 0,
            "size_download": 8178,
            "time_total": 1.102911,
        }
        or STATUS_WORDING not in rendered
        or CAPACITY_WORDING not in rendered
    ):
        raise GulfDataHubDubaiGapError("official response semantics differ")
    return {
        "headers": headers,
        "rendered_text": rendered,
        "writeout": writeout,
    }


def _keys(number: int) -> tuple[str, str, str]:
    campus = f"curated:gulf-data-hub-dubai-dso{number}-data-center"
    project = f"{campus}:official-under-construction-build"
    evidence = (
        f"gulf-data-hub-dubai-dso{number}-official-status-page-captured-2026-07-22"
    )
    return campus, project, evidence


CAMPUS_KEYS = frozenset(_keys(number)[0] for number in (4, 5, 6))
PROJECT_KEYS = frozenset(_keys(number)[1] for number in (4, 5, 6))
EVIDENCE_KEYS = frozenset(_keys(number)[2] for number in (4, 5, 6))
COLLISION_ALIASES = (
    "gulf data hub",
    "gulfdatahub",
    "dso4",
    "dso 4",
    "dso5",
    "dso 5",
    "dso6",
    "dso 6",
)


def _evidence(number: int) -> dict[str, Any]:
    _campus, _project, evidence_key = _keys(number)
    return {
        "key": evidence_key,
        "kind": "company_disclosure",
        "title": f"Gulf Data Hub Dubai DSO{number} official status page",
        "source_url": SOURCE_URL,
        "publisher": "Gulf Data Hub",
        "source_family": "gulf_data_hub_official_location_pages",
        "published_at": None,
        "retrieved_at": RETRIEVED_AT,
        "license": "all-rights-reserved",
        "attribution": "Gulf Data Hub",
        "excerpt": (
            "Gulf Data Hub's Dubai page labels DSO4, DSO5, and DSO6 under "
            "construction. It gives a 4.2-16 MW range across six Dubai locations "
            "without allocating a value to an individual DSO site."
        ),
        "content_hash": CAPTURE_FILE_PINS["gdh_dubai.body"][1],
        "metadata": {
            "capture_artifact_id": ARTIFACT_ID,
            "capture_request_id": "gdh_dubai",
            "capture_method": (
                "credential_free_single_curl_location_compressed_no_retry"
            ),
            "requested_url": SOURCE_URL,
            "effective_url": SOURCE_URL,
            "request_credentials_supplied": False,
            "http_status": 200,
            "content_type": "text/html; charset=utf-8",
            "capture_started_at": CAPTURE_STARTED_AT,
            "response_date_and_retrieved_at": RETRIEVED_AT,
            "capture_body_bytes": CAPTURE_FILE_PINS["gdh_dubai.body"][0],
            "capture_body_sha256": CAPTURE_FILE_PINS["gdh_dubai.body"][1],
            "capture_headers_bytes": CAPTURE_FILE_PINS["gdh_dubai.headers"][0],
            "capture_headers_sha256": CAPTURE_FILE_PINS["gdh_dubai.headers"][1],
            "content_hash_scope": (
                "SHA-256 of the exact 80027-byte content-decoded official HTML body"
            ),
            "content_hash_verification": "fetched_bytes_sha256",
            "official_status_wording": STATUS_WORDING,
            "official_capacity_wording": CAPACITY_WORDING,
            "site_scope": f"DSO{number}, Dubai, United Arab Emirates",
            "status_semantics": (
                "retrieval_date_official_under_construction_label; later persistence "
                "and present status are unknown"
            ),
            "lifecycle_mapping": (
                "The publisher's under-construction label maps only to the schema's "
                "under_construction state; no physical substage is inferred."
            ),
            "capacity_exclusion": (
                "The page gives a 4.2-16 MW range across six Dubai locations and "
                f"does not allocate any MW value to DSO{number}; no capacity row."
            ),
            "classification_guardrail": (
                "No site-specific operating model, workload, customer, or tenant is "
                "normalized from general company/service language."
            ),
            "efficiency_guardrail": (
                "No PUE, WUE, consumption, annual energy, generation, grid, or load "
                "value is reported or inferred."
            ),
            "geospatial_guardrail": (
                "Dubai locality only; no map image, address, coordinate, parcel, "
                "footprint, geometry, satellite image, aerial image, or CV inference."
            ),
            "rights_scope": (
                "Compact factual extraction from an all-rights-reserved official "
                "page; exact body and headers remain in the frozen private capture."
            ),
        },
    }


def _entity(number: int, *, project: bool) -> dict[str, Any]:
    campus_key, project_key, evidence_key = _keys(number)
    return {
        "stable_key": project_key if project else campus_key,
        "name": (
            f"Gulf Data Hub Dubai DSO{number} Official Under-Construction Build"
            if project
            else f"Gulf Data Hub Dubai DSO{number} Data Center"
        ),
        "country": "United Arab Emirates",
        "address": "Dubai, United Arab Emirates",
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": "2026-07-22",
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    validate_private_capture()
    documents: dict[str, dict[str, Any]] = {}
    for number, filename in zip((4, 5, 6), SOURCE_FILENAMES, strict=True):
        _campus, _project, evidence_key = _keys(number)
        documents[filename] = {
            "schema_version": "1.1",
            "evidence": [_evidence(number)],
            "campus": _entity(number, project=False),
            "project": _entity(number, project=True),
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": evidence_key,
                    "as_of_date": "2026-07-22",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
            "operating_models": [],
            "workloads": [],
            "capacities": [],
        }
    return documents


def _current_source_documents() -> list[tuple[Path, dict[str, Any]]]:
    documents: list[tuple[Path, dict[str, Any]]] = []
    candidates = [*SOURCES_ROOT.glob("*.json"), *ARTIFACT_ROOT.glob("**/*.json")]
    for path in candidates:
        if path.is_symlink() or not path.is_file():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if (
            isinstance(document, dict)
            and document.get("schema_version") == "1.1"
            and isinstance(document.get("campus"), dict)
            and isinstance(document.get("evidence"), list)
        ):
            documents.append((path, document))
    return documents


def _collision_witness(
    *, allow_published_sources: bool | None = None
) -> dict[str, Any]:
    if allow_published_sources is None:
        complete, present = _final_presence()
        if present and not complete:
            raise GulfDataHubDubaiGapError(
                f"GDH partial final-path collision during scan: {present!r}"
            )
        allow_published_sources = complete
    for path, pin in V95_PINS.items():
        _pin(path, pin, f"accepted v95 {path.name}")
    definition = json.loads(V95_DEFINITION.read_text(encoding="utf-8"))
    manifest = json.loads(V95_MANIFEST.read_text(encoding="utf-8"))
    with V95_ENTITIES.open(encoding="utf-8", newline="") as stream:
        v95_keys = {row["stable_key"] for row in csv.DictReader(stream)}
    v95_text = V95_ENTITIES.read_text(encoding="utf-8").lower()
    v95_alias_hits = [alias for alias in COLLISION_ALIASES if alias in v95_text]
    if (
        definition.get("release_id") != V95_RELEASE_ID
        or len(definition.get("curated_inputs", [])) != V95_INPUT_COUNT
        or manifest.get("entities") != V95_ENTITY_COUNT
        or tree_digest(V95_RELEASE) != V95_TREE_SHA256
        or v95_keys & (CAMPUS_KEYS | PROJECT_KEYS)
        or v95_alias_hits
    ):
        raise GulfDataHubDubaiGapError("accepted v95 collision witness differs")

    identity_hits: list[str] = []
    evidence_hits: list[str] = []
    alias_hits: list[str] = []
    scanned = 0
    final_documents = expected_source_documents() if allow_published_sources else {}
    final_paths = _final_source_paths() if allow_published_sources else {}
    final_by_path = {path: name for name, path in final_paths.items()}
    for path, document in _current_source_documents():
        if path in final_by_path:
            name = final_by_path[path]
            if document != final_documents[name]:
                raise GulfDataHubDubaiGapError(
                    f"GDH published source content differs: {name}"
                )
            continue
        scanned += 1
        stable = {
            entity.get("stable_key")
            for entity in (document.get("campus", {}), document.get("project", {}))
            if isinstance(entity, dict)
        }
        evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        if stable & (CAMPUS_KEYS | PROJECT_KEYS):
            identity_hits.append(str(path.relative_to(ROOT)))
        if evidence & EVIDENCE_KEYS:
            evidence_hits.append(str(path.relative_to(ROOT)))
        serialized = json.dumps(document, ensure_ascii=False).lower()
        matched = [alias for alias in COLLISION_ALIASES if alias in serialized]
        if matched:
            alias_hits.append(f"{path.relative_to(ROOT)}:{','.join(matched)}")
    if identity_hits or evidence_hits or alias_hits:
        raise GulfDataHubDubaiGapError(
            "GDH source collision: "
            f"identities={identity_hits!r}, evidence={evidence_hits!r}, "
            f"aliases={alias_hits!r}"
        )
    return {
        "accepted_base_release_id": V95_RELEASE_ID,
        "accepted_base_definition_bytes": V95_PINS[V95_DEFINITION][0],
        "accepted_base_definition_sha256": V95_PINS[V95_DEFINITION][1],
        "accepted_base_manifest_bytes": V95_PINS[V95_MANIFEST][0],
        "accepted_base_manifest_sha256": V95_PINS[V95_MANIFEST][1],
        "accepted_base_tree_sha256": V95_TREE_SHA256,
        "accepted_base_entities": V95_ENTITY_COUNT,
        "current_source_documents_scanned": scanned,
        "stable_key_collision_count": 0,
        "evidence_key_collision_count": 0,
        "alias_collision_count": 0,
        "alias_search_terms": list(COLLISION_ALIASES),
    }


def _validate_semantics(documents: Mapping[str, Mapping[str, Any]]) -> None:
    if tuple(documents) != SOURCE_FILENAMES:
        raise GulfDataHubDubaiGapError("GDH source order differs")
    stable_keys = {
        document[entity]["stable_key"]
        for document in documents.values()
        for entity in ("campus", "project")
    }
    evidence_keys = {
        row["key"] for document in documents.values() for row in document["evidence"]
    }
    lifecycle = {
        (
            document[row["entity"]]["stable_key"],
            row["value"],
            row["as_of_date"],
            row["method"],
        )
        for document in documents.values()
        for row in document["lifecycle"]
    }
    expected_lifecycle = {
        (
            _keys(number)[1],
            "under_construction",
            "2026-07-22",
            "authoritative_physical_status_update",
        )
        for number in (4, 5, 6)
    }
    if (
        stable_keys != CAMPUS_KEYS | PROJECT_KEYS
        or evidence_keys != EVIDENCE_KEYS
        or lifecycle != expected_lifecycle
        or any(
            document[section]
            for document in documents.values()
            for section in ("operating_models", "workloads", "capacities")
        )
    ):
        raise GulfDataHubDubaiGapError("GDH normalized semantic contract differs")
    for document in documents.values():
        for entity in ("campus", "project"):
            row = document[entity]
            if (
                row["country"] != "United Arab Emirates"
                or row["address"] != "Dubai, United Arab Emirates"
                or row["roles"]
                or row["coordinates"] is not None
                or row["geometry"] is not None
            ):
                raise GulfDataHubDubaiGapError("GDH entity scope differs")
        evidence = document["evidence"][0]
        if (
            evidence["source_url"] != SOURCE_URL
            or evidence["retrieved_at"] != RETRIEVED_AT
            or evidence["published_at"] is not None
            or evidence["license"] != "all-rights-reserved"
            or evidence["content_hash"] != CAPTURE_FILE_PINS["gdh_dubai.body"][1]
            or evidence["metadata"]["official_status_wording"] != STATUS_WORDING
            or evidence["metadata"]["official_capacity_wording"] != CAPACITY_WORDING
            or "no capacity row" not in evidence["metadata"]["capacity_exclusion"]
        ):
            raise GulfDataHubDubaiGapError("GDH evidence boundary differs")


def _write_sources(
    root: Path, documents: Mapping[str, Mapping[str, Any]]
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name in SOURCE_FILENAMES:
        path = root / name
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(documents[name]))
            stream.flush()
            os.fsync(stream.fileno())
        paths[name] = path
    return paths


def _validate_sources(
    paths: Mapping[str, Path], *, frozen: bool
) -> list[dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    wanted_mode = 0o444 if frozen else 0o600
    if tuple(paths) != SOURCE_FILENAMES:
        raise GulfDataHubDubaiGapError("GDH staged source inventory differs")
    records: list[dict[str, Any]] = []
    for number, name in zip((4, 5, 6), SOURCE_FILENAMES, strict=True):
        path = paths[name]
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != wanted_mode
        ):
            raise GulfDataHubDubaiGapError(f"GDH source mode differs: {name}")
        raw = path.read_bytes()
        document = json.loads(raw)
        if raw != _canonical(document):
            raise GulfDataHubDubaiGapError(f"GDH source is not canonical: {name}")
        documents[name] = document
        campus, project, _evidence_key = _keys(number)
        records.append(
            {
                "path": f"sources/{name}",
                "bytes": len(raw),
                "sha256": _sha256_bytes(raw),
                "schema_version": "1.1",
                "country": "United Arab Emirates",
                "campus_stable_key": campus,
                "project_stable_key": project,
                "evidence_records": 1,
                "lifecycle_observations": 1,
                "capacity_estimates": 0,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
                "seed_eligible": True,
                "seeded": False,
            }
        )
    if documents != expected_source_documents():
        raise GulfDataHubDubaiGapError("GDH source bytes differ from expected")
    _validate_semantics(documents)
    return records


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="gdh-dubai-dso456-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        errors = validate_database(connection)
        if errors:
            raise GulfDataHubDubaiGapError(
                f"GDH offline database validation failed: {errors!r}"
            )
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "entity_snapshots",
                "evidence",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            )
        }
        expected = {
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 3,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise GulfDataHubDubaiGapError(f"GDH offline import differs: {counts}")
        connection.close()
        return counts


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for number, filename in zip((4, 5, 6), SOURCE_FILENAMES, strict=True):
        campus, project, evidence = _keys(number)
        candidates.append(
            {
                "candidate_id": f"gulf-data-hub-dubai-dso{number}",
                "decision": "accepted_source_record_prepublication",
                "source_path": f"sources/{filename}",
                "site_label": f"DSO {number}",
                "campus_stable_key": campus,
                "project_stable_key": project,
                "evidence_key": evidence,
                "official_status_label": "under construction",
                "normalized_lifecycle": "under_construction",
                "as_of_date": "2026-07-22",
                "current_status_after_retrieval": "unknown",
                "page_capacity_range_mw": {
                    "minimum": 4.2,
                    "maximum": 16.0,
                    "scope": "six_Dubai_locations_not_individual_site",
                    "allocated_to_candidate": False,
                },
                "capacity_claim_created": False,
                "energy_consumption_claim_created": False,
                "pue_claim_created": False,
                "operating_model_claim_created": False,
                "workload_claim_created": False,
                "coordinate_claim_created": False,
                "geometry_claim_created": False,
                "imagery_or_cv_claim_created": False,
                "published": False,
                "seeded": False,
            }
        )
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-candidate-assessment-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "candidate_count": 3,
        "accepted_source_record_prepublication_count": 3,
        "regional_completeness_claimed": False,
        "candidates": candidates,
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    capture_rows = [
        {"path": name, "bytes": pin[0], "sha256": pin[1]}
        for name, pin in sorted(CAPTURE_FILE_PINS.items())
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "controlled_request_count": 1,
        "successful_http_200_body_captures": 1,
        "normalized_source_record_count": 3,
        "request_credentials_supplied": False,
        "capture_retry_count": 0,
        "raw_capture_redistributed": False,
        "capture_directory": str(CAPTURE_ROOT),
        "capture_directory_retained_private": True,
        "capture_directory_frozen": True,
        "capture_directory_mode": "0555",
        "capture_file_mode": "0444",
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "captures": [
            {
                "capture_id": "gdh_dubai",
                "publisher": "Gulf Data Hub",
                "requested_url": SOURCE_URL,
                "effective_url": SOURCE_URL,
                "capture_started_at": CAPTURE_STARTED_AT,
                "published_at": None,
                "retrieved_at": RETRIEVED_AT,
                "http_status": 200,
                "content_type": "text/html; charset=utf-8",
                "remote_ip": "13.207.136.21",
                "ssl_verify_result": 0,
                "redirect_count": 0,
                "request_method": (
                    "credential_free_single_curl_location_compressed_no_retry"
                ),
                "claim_use": (
                    "DSO4_DSO5_DSO6_identity_and_retrieval_date_official_"
                    "under_construction_status_only"
                ),
                "body": capture_rows[0],
                "headers": capture_rows[1],
                "writeout": capture_rows[2],
            }
        ],
        "complete_private_file_inventory": capture_rows,
    }


def _rights_and_disposition(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "source_rights": (
            "The captured first-party response is treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_and_compact_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_body_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "private_capture_directory": str(CAPTURE_ROOT),
        "private_capture_directory_retained": True,
        "private_capture_directory_frozen": True,
        "private_capture_file_count": CAPTURE_FILE_COUNT,
        "private_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "private_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "publication_performed": False,
    }


def _source_snapshot(
    recorded_at: str,
    source_records: list[dict[str, Any]],
    collision: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "research_date": "2026-07-22",
        "recorded_at": recorded_at,
        "regional_completeness_claimed": False,
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 3,
            "source_records": 3,
            "seed_eligible_candidates": 3,
            "distinct_campuses": 3,
            "projects": 3,
            "distinct_entity_snapshots": 6,
            "evidence_records": 3,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
            "computer_vision_observations": 0,
        },
        "accepted_base_and_collision_witness": dict(collision),
        "claim_boundary": {
            "official_status_is_retrieval_date_label_only": True,
            "current_status_after_retrieval": "unknown",
            "per_site_capacity_allocated": False,
            "energy_consumption_inferred": False,
            "pue_inferred": False,
            "operating_model_inferred": False,
            "workload_inferred": False,
            "coordinates_inferred": False,
            "geometry_inferred": False,
            "imagery_or_cv_used": False,
        },
        "integration": {
            "published": False,
            "accepted": False,
            "final_source_paths_created": False,
            "final_artifact_path_created": False,
            "open_seed_successor_created": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "timeline_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "coverage_integration": "none",
            "v95_files_touched": [],
        },
        "prepublication_contract": {
            "version": 1,
            "publisher_function_present": False,
            "promotion_function_present": False,
            "staging_only": True,
            "staged_source_file_mode": "0444",
            "staged_source_directory_mode": "0555",
            "staged_artifact_file_mode": "0444",
            "staged_artifact_directory_mode": "0555",
            "raw_capture_file_mode": "0444",
            "raw_capture_directory_mode": "0555",
            "raw_capture_retained_private": True,
        },
    }


def _artifact_payloads(
    recorded_at: str,
    source_records: list[dict[str, Any]],
    collision: Mapping[str, Any],
) -> dict[str, bytes]:
    readme = f"""# Gulf Data Hub Dubai DSO4-DSO6 — prepublication only

This governed artifact was rendered for preflight at {recorded_at} and was not published. One exact first-party Dubai page response supports three source-scoped candidates: DSO4, DSO5, and DSO6. The page labels all three under construction at the 2026-07-22 retrieval observation. Later persistence and present status are unknown.

The page's 4.2-16 MW range covers six Dubai locations and is not allocated to any individual DSO site. Accordingly, the three records contain six identity snapshots and three `under_construction` lifecycle observations, with zero capacity, annual-energy, consumption, PUE, operating-model, workload, coordinate, geometry, satellite, aerial, or computer-vision observations. The locality is only Dubai, United Arab Emirates; no street address or expansion of the publisher's DSO labels is inferred.

The exact all-rights-reserved HTML response, headers, and transfer metadata remain frozen in the private capture directory. This artifact carries only hashes, retrieval metadata, compact factual paraphrases, and the two short evidence strings needed to verify extraction.

The safe workflow validates exact prospective source and accepted-format artifact bytes in a temporary private stage, freezes them, imports the sources twice into fresh offline databases, records their hashes, and discards the stage. No final source path, final source-artifact path, open-seed successor, release, federation, identity, timeline, construction-master, map, coverage, or v95 file is created or changed. Publication is intentionally unavailable without a later code change and explicit root authorization.
"""
    return {
        "README.md": readme.encode("utf-8"),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(_rights_and_disposition(recorded_at)),
        "source-snapshot.json": _canonical(
            _source_snapshot(recorded_at, source_records, collision)
        ),
    }


def _file_rows(payloads: Mapping[str, bytes]) -> list[dict[str, Any]]:
    if tuple(payloads) != CONTENT_FILES:
        raise GulfDataHubDubaiGapError("GDH artifact content inventory differs")
    return [
        {
            "path": name,
            "bytes": len(payloads[name]),
            "sha256": _sha256_bytes(payloads[name]),
        }
        for name in CONTENT_FILES
    ]


def _artifact_manifest(
    recorded_at: str, payloads: Mapping[str, bytes]
) -> dict[str, Any]:
    rows = _file_rows(payloads)
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _sha256_bytes(_canonical(rows)),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 3,
        "curated_source_records": 3,
        "seed_eligible_candidates": 3,
        "distinct_entities": 6,
        "unique_evidence_records": 3,
        "lifecycle_observations": 3,
        "operating_model_observations": 0,
        "workload_observations": 0,
        "capacity_estimates": 0,
        "successful_http_200_body_captures": 1,
        "raw_capture_redistributed": False,
        "raw_capture_frozen_private": True,
        "regional_completeness_claimed": False,
        "current_status_inferred": False,
        "accepted": False,
        "published": False,
        "publication_status": "prepublication_only",
        "publisher_function_present": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def _accepted_source_records(
    source_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [{**row, "accepted": True, "published": True} for row in source_records]


def _accepted_candidate_assessment(recorded_at: str) -> dict[str, Any]:
    document = _candidate_assessment(recorded_at)
    document.pop("accepted_source_record_prepublication_count")
    document["accepted_source_record_count"] = 3
    document["published_source_record_count"] = 3
    for row in document["candidates"]:
        row["decision"] = "accepted_official_current_build"
        row["accepted"] = True
        row["published"] = True
    return document


def _accepted_retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    document = _retrieval_inventory(recorded_at)
    document.pop("capture_directory")
    document["capture_storage_path_redacted"] = True
    return document


def _accepted_rights_and_disposition(recorded_at: str) -> dict[str, Any]:
    document = _rights_and_disposition(recorded_at)
    document.pop("private_capture_directory")
    document["private_capture_storage_path_redacted"] = True
    document["publication_performed"] = True
    return document


def _accepted_source_snapshot(
    recorded_at: str,
    source_records: list[dict[str, Any]],
    collision: Mapping[str, Any],
) -> dict[str, Any]:
    document = _source_snapshot(
        recorded_at,
        _accepted_source_records(source_records),
        collision,
    )
    document["integration"] = {
        "published": True,
        "accepted": True,
        "final_source_paths_created": True,
        "final_artifact_path_created": True,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "timeline_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "coverage_integration": "none",
        "v95_files_touched": [],
    }
    document.pop("prepublication_contract")
    document["publication_contract"] = {
        "version": 1,
        "explicit_authorization_required": True,
        "same_filesystem_unique_stages": True,
        "future_barrier_required": True,
        "no_replace_promotion": True,
        "rollback_on_failure": True,
        "all_recursive_stage_birthtimes_and_mtimes_at_or_before_recorded_at": True,
        "all_recursive_final_ctimes_at_or_after_recorded_at": True,
        "source_file_mode": "0444",
        "artifact_file_mode": "0444",
        "artifact_directory_mode": "0555",
        "raw_capture_file_mode": "0444",
        "raw_capture_directory_mode": "0555",
        "raw_capture_retained_private": True,
    }
    return document


def _accepted_artifact_payloads(
    recorded_at: str,
    source_records: list[dict[str, Any]],
    collision: Mapping[str, Any],
) -> dict[str, bytes]:
    readme = f"""# Gulf Data Hub Dubai DSO4-DSO6 — accepted official-source artifact

This immutable artifact was accepted and published at {recorded_at}. One exact first-party Dubai page response supports three source-scoped records: DSO4, DSO5, and DSO6. The page labels all three under construction at the 2026-07-22 retrieval observation. Later persistence and present status are unknown.

The page's 4.2-16 MW range covers six Dubai locations and is not allocated to any individual DSO site. Accordingly, the three records contain six identity snapshots and three `under_construction` lifecycle observations, with zero capacity, annual-energy, consumption, PUE, operating-model, workload, coordinate, geometry, satellite, aerial, or computer-vision observations. The locality is only Dubai, United Arab Emirates; no street address or expansion of the publisher's DSO labels is inferred.

The exact all-rights-reserved HTML response, headers, and transfer metadata remain frozen in private storage. This artifact carries only hashes, retrieval metadata, compact factual paraphrases, and the two short evidence strings needed to verify extraction.

Publication used unique same-filesystem stages, two offline import replays, a live timestamp barrier, recursive birth/mtime and ctime checks, no-replace promotion, rollback protection, and an existing-identical validator. No open-seed successor, release, federation, identity, timeline, construction-master, map, coverage, or v95 file was created or changed by this artifact publication.
"""
    return {
        "README.md": readme.encode("utf-8"),
        "candidate-assessment.json": _canonical(
            _accepted_candidate_assessment(recorded_at)
        ),
        "retrieval-inventory.json": _canonical(
            _accepted_retrieval_inventory(recorded_at)
        ),
        "rights-and-disposition.json": _canonical(
            _accepted_rights_and_disposition(recorded_at)
        ),
        "source-snapshot.json": _canonical(
            _accepted_source_snapshot(recorded_at, source_records, collision)
        ),
    }


def _accepted_artifact_manifest(
    recorded_at: str, payloads: Mapping[str, bytes]
) -> dict[str, Any]:
    document = _artifact_manifest(recorded_at, payloads)
    document.update(
        {
            "accepted": True,
            "published": True,
            "publication_status": "accepted",
            "publisher_function_present": True,
        }
    )
    return document


def _write_artifact(
    root: Path, payloads: Mapping[str, bytes], recorded_at: str
) -> None:
    for name in CONTENT_FILES:
        path = root / name
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payloads[name])
            stream.flush()
            os.fsync(stream.fileno())
    manifest_path = root / "manifest.json"
    manifest_raw = _canonical(_artifact_manifest(recorded_at, payloads))
    descriptor = os.open(manifest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(manifest_raw)
        stream.flush()
        os.fsync(stream.fileno())
    sidecar = root / "manifest.sha256"
    descriptor = os.open(sidecar, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(f"{_sha256_bytes(manifest_raw)}  manifest.json\n".encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())


def _write_accepted_artifact(
    root: Path, payloads: Mapping[str, bytes], recorded_at: str
) -> None:
    for name in CONTENT_FILES:
        path = root / name
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payloads[name])
            stream.flush()
            os.fsync(stream.fileno())
    manifest_path = root / "manifest.json"
    manifest_raw = _canonical(_accepted_artifact_manifest(recorded_at, payloads))
    descriptor = os.open(manifest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(manifest_raw)
        stream.flush()
        os.fsync(stream.fileno())
    sidecar = root / "manifest.sha256"
    descriptor = os.open(sidecar, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(f"{_sha256_bytes(manifest_raw)}  manifest.json\n".encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())


def _freeze_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise GulfDataHubDubaiGapError("GDH staging root is absent or unsafe")
    entries = [root, *root.rglob("*")]
    if any(path.is_symlink() for path in entries):
        raise GulfDataHubDubaiGapError("GDH staging tree contains a symlink")
    if any(not path.is_file() and not path.is_dir() for path in entries):
        raise GulfDataHubDubaiGapError("GDH staging tree has an unsupported member")
    for path in entries:
        if path.is_file():
            path.chmod(0o444)
    for path in sorted(
        (path for path in entries if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o555)


def _thaw_tree(root: Path) -> None:
    if root.is_symlink() or not root.exists():
        return
    entries = [root, *root.rglob("*")]
    for path in entries:
        if path.is_file() and not path.is_symlink():
            path.chmod(0o600)
    for path in sorted(
        (path for path in entries if path.is_dir() and not path.is_symlink()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        path.chmod(0o700)


def _assert_tree_before(root: Path, target: datetime) -> None:
    for path in (root, *root.rglob("*")):
        metadata = path.stat(follow_symlinks=False)
        times = [metadata.st_mtime, metadata.st_ctime]
        birth = getattr(metadata, "st_birthtime", None)
        if birth is not None:
            times.append(birth)
        if max(times) >= target.timestamp():
            raise GulfDataHubDubaiGapError(
                f"GDH staged member is not earlier than recorded_at: {path.name}"
            )


def _identity(path: Path, *, directory: bool | None = None) -> tuple[int, int]:
    if path.is_symlink():
        raise GulfDataHubDubaiGapError(f"GDH symlink is not allowed: {path}")
    metadata = path.stat(follow_symlinks=False)
    if directory is True and not stat.S_ISDIR(metadata.st_mode):
        raise GulfDataHubDubaiGapError(f"GDH expected directory: {path}")
    if directory is False and not stat.S_ISREG(metadata.st_mode):
        raise GulfDataHubDubaiGapError(f"GDH expected ordinary file: {path}")
    return metadata.st_dev, metadata.st_ino


def _has_identity(
    path: Path, expected: tuple[int, int], *, directory: bool | None = None
) -> bool:
    try:
        return _identity(path, directory=directory) == expected
    except (FileNotFoundError, GulfDataHubDubaiGapError):
        return False


def _tree_identities(root: Path) -> dict[str, tuple[int, int, str]]:
    if root.is_symlink() or not root.is_dir():
        raise GulfDataHubDubaiGapError(f"GDH unsafe tree root: {root}")
    identities: dict[str, tuple[int, int, str]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        if path.is_symlink():
            raise GulfDataHubDubaiGapError(f"GDH governed tree has a symlink: {path}")
        metadata = path.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
        else:
            raise GulfDataHubDubaiGapError(
                f"GDH governed tree has a special member: {path}"
            )
        relative = "." if path == root else path.relative_to(root).as_posix()
        identities[relative] = (metadata.st_dev, metadata.st_ino, kind)
    return identities


def _assert_tree_identities(
    root: Path, expected: Mapping[str, tuple[int, int, str]]
) -> None:
    if _tree_identities(root) != dict(expected):
        raise GulfDataHubDubaiGapError(f"GDH tree identity changed: {root}")


def _assert_birth_mtime_at_or_before(root: Path, target: datetime) -> None:
    for path in (root, *root.rglob("*")):
        metadata = path.stat(follow_symlinks=False)
        birth = getattr(metadata, "st_birthtime", metadata.st_mtime)
        if max(birth, metadata.st_mtime) > target.timestamp() + 1e-6:
            raise GulfDataHubDubaiGapError(
                f"GDH final member birth/mtime post-dates recorded_at: {path}"
            )


def _assert_ctime_at_or_after(root: Path, target: datetime) -> None:
    for path in (root, *root.rglob("*")):
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_ctime + 1e-6 < target.timestamp():
            raise GulfDataHubDubaiGapError(
                f"GDH final member ctime predates recorded_at: {path}"
            )


def _discard_owned_tree(root: Path) -> None:
    identities = _tree_identities(root)
    directories = [
        path
        for path in (root, *root.rglob("*"))
        if path.is_dir() and not path.is_symlink()
    ]
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        if not _has_identity(directory, identities[relative][:2], directory=True):
            raise GulfDataHubDubaiGapError(
                f"GDH refusing identity-mismatched cleanup: {directory}"
            )
        directory.chmod(0o700)
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if not _has_identity(path, identities[relative][:2], directory=False):
            raise GulfDataHubDubaiGapError(
                f"GDH refusing identity-mismatched cleanup: {path}"
            )
        path.unlink()
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        relative = "." if directory == root else directory.relative_to(root).as_posix()
        if not _has_identity(directory, identities[relative][:2], directory=True):
            raise GulfDataHubDubaiGapError(
                f"GDH refusing identity-mismatched cleanup: {directory}"
            )
        directory.rmdir()


def _final_source_paths() -> dict[str, Path]:
    return {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}


def _final_presence() -> tuple[bool, list[str]]:
    paths = {"artifact": ARTIFACT, **_final_source_paths()}
    present = [
        name for name, path in paths.items() if path.exists() or path.is_symlink()
    ]
    return len(present) == len(paths), present


def _assert_final_absent() -> None:
    complete, present = _final_presence()
    if complete or present:
        raise GulfDataHubDubaiGapError(f"GDH final-path collision: {present!r}")


def _assert_no_publication() -> None:
    paths = [
        ARTIFACT,
        PUBLICATION_LOCK,
        *(SOURCES_ROOT / name for name in SOURCE_FILENAMES),
    ]
    present = [str(path) for path in paths if path.exists() or path.is_symlink()]
    if present:
        raise GulfDataHubDubaiGapError(f"GDH final-path collision: {present!r}")


def _input_state() -> dict[str, Any]:
    validate_private_capture()
    for path, pin in V95_PINS.items():
        _pin(path, pin, f"accepted v95 {path.name}")
    paths = [CAPTURE_ROOT, *sorted(CAPTURE_ROOT.iterdir()), *V95_PINS]
    identities: dict[str, list[int]] = {}
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        identities[str(path)] = [
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ]
    return {
        "identities": identities,
        "capture_tree_sha256": tree_digest(CAPTURE_ROOT),
        "v95_tree_sha256": tree_digest(V95_RELEASE),
    }


def _validate_collision_snapshot(
    recorded: Mapping[str, Any], current: Mapping[str, Any]
) -> None:
    fixed = (
        "accepted_base_release_id",
        "accepted_base_definition_bytes",
        "accepted_base_definition_sha256",
        "accepted_base_manifest_bytes",
        "accepted_base_manifest_sha256",
        "accepted_base_tree_sha256",
        "accepted_base_entities",
        "stable_key_collision_count",
        "evidence_key_collision_count",
        "alias_collision_count",
    )
    if any(recorded.get(key) != current.get(key) for key in fixed):
        raise GulfDataHubDubaiGapError("GDH collision witness snapshot differs")
    for label, witness in (("recorded", recorded), ("current", current)):
        scanned = witness.get("current_source_documents_scanned")
        if not isinstance(scanned, int) or scanned < 0:
            raise GulfDataHubDubaiGapError(
                f"GDH {label} collision scan count is invalid"
            )


def validate_prepublication_artifact(
    source_root: Path,
    artifact_root: Path,
    *,
    recorded_at: str,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Validate exact staged source/artifact bytes without publishing them."""

    validate_private_capture()
    current_collision = _collision_witness()
    root_mode = 0o555 if require_frozen else 0o700
    file_mode = 0o444 if require_frozen else 0o600
    for label, root in (("source", source_root), ("artifact", artifact_root)):
        if (
            root.is_symlink()
            or not root.is_dir()
            or stat.S_IMODE(root.stat().st_mode) != root_mode
        ):
            raise GulfDataHubDubaiGapError(f"GDH {label} stage mode differs")

    source_entries = {path.name: path for path in source_root.iterdir()}
    if set(source_entries) != set(SOURCE_FILENAMES):
        raise GulfDataHubDubaiGapError("GDH source stage closed set differs")
    source_paths = {name: source_entries[name] for name in SOURCE_FILENAMES}
    source_records = _validate_sources(source_paths, frozen=require_frozen)

    artifact_entries = {path.name: path for path in artifact_root.iterdir()}
    if set(artifact_entries) != CLOSED_FILES:
        raise GulfDataHubDubaiGapError("GDH artifact closed set differs")
    if any(
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != file_mode
        for path in artifact_entries.values()
    ):
        raise GulfDataHubDubaiGapError("GDH artifact member mode differs")
    manifest_raw = artifact_entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise GulfDataHubDubaiGapError("GDH manifest is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("format")
        != "datacenter-atlas-official-source-artifact-manifest-v3"
        or manifest.get("recorded_at") != recorded_at
        or manifest.get("accepted") is not False
        or manifest.get("published") is not False
        or manifest.get("publication_status") != "prepublication_only"
        or manifest.get("publisher_function_present") is not False
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise GulfDataHubDubaiGapError("GDH prepublication manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise GulfDataHubDubaiGapError("GDH manifest file inventory differs")
    for row in rows:
        raw = artifact_entries[row["path"]].read_bytes()
        if (len(raw), _sha256_bytes(raw)) != (row["bytes"], row["sha256"]):
            raise GulfDataHubDubaiGapError(f"GDH manifest pin differs: {row['path']}")
    if manifest.get("tree_sha256") != _sha256_bytes(_canonical(rows)):
        raise GulfDataHubDubaiGapError("GDH logical artifact tree differs")
    if artifact_entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise GulfDataHubDubaiGapError("GDH manifest sidecar differs")

    snapshot = json.loads(
        artifact_entries["source-snapshot.json"].read_text(encoding="utf-8")
    )
    if snapshot.get("source_records") != source_records:
        raise GulfDataHubDubaiGapError("GDH source snapshot pins differ")
    recorded_collision = snapshot.get("accepted_base_and_collision_witness")
    if not isinstance(recorded_collision, dict):
        raise GulfDataHubDubaiGapError("GDH collision witness is absent")
    _validate_collision_snapshot(recorded_collision, current_collision)
    expected_payloads = _artifact_payloads(
        recorded_at, source_records, recorded_collision
    )
    if manifest != _artifact_manifest(recorded_at, expected_payloads):
        raise GulfDataHubDubaiGapError("GDH manifest content differs from expected")
    for name in CONTENT_FILES:
        if artifact_entries[name].read_bytes() != expected_payloads[name]:
            raise GulfDataHubDubaiGapError(f"GDH artifact content differs: {name}")

    target = _instant(recorded_at, "recorded_at")
    if target <= _instant(RETRIEVED_AT, "retrieved_at"):
        raise GulfDataHubDubaiGapError("GDH recorded_at does not follow retrieval")
    _assert_tree_before(source_root, target)
    _assert_tree_before(artifact_root, target)
    first = _offline_import(source_paths, recorded_at)
    second = _offline_import(source_paths, recorded_at)
    if first != second:
        raise GulfDataHubDubaiGapError("GDH offline import replay differs")
    return {"manifest": manifest, "database_counts": first}


def validate_published_gdh_dubai_dso456(
    source_paths: Mapping[str, Path] | None = None,
    artifact_root: Path | None = None,
    *,
    recorded_at: str | None = None,
    require_live: bool = True,
    require_final_chronology: bool = True,
    require_frozen: bool = True,
    allow_published_sources_in_collision_scan: bool = True,
    collision_witness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate accepted source and artifact bytes, replay, and chronology."""

    source_paths = dict(source_paths or _final_source_paths())
    artifact_root = artifact_root or ARTIFACT
    if tuple(source_paths) != SOURCE_FILENAMES:
        raise GulfDataHubDubaiGapError("GDH accepted source inventory differs")
    source_records = _validate_sources(source_paths, frozen=require_frozen)
    if artifact_root.is_symlink() or not artifact_root.is_dir():
        raise GulfDataHubDubaiGapError("GDH accepted artifact is absent or unsafe")
    artifact_root_mode = 0o555 if require_frozen else 0o700
    artifact_file_mode = 0o444 if require_frozen else 0o600
    if stat.S_IMODE(artifact_root.stat().st_mode) != artifact_root_mode:
        raise GulfDataHubDubaiGapError("GDH accepted artifact root mode differs")
    artifact_entries = {path.name: path for path in artifact_root.iterdir()}
    if set(artifact_entries) != CLOSED_FILES:
        raise GulfDataHubDubaiGapError("GDH accepted artifact closed set differs")
    if any(
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) != artifact_file_mode
        for path in artifact_entries.values()
    ):
        raise GulfDataHubDubaiGapError("GDH accepted artifact member mode differs")

    manifest_raw = artifact_entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise GulfDataHubDubaiGapError("GDH accepted manifest is not canonical")
    manifest_recorded_at = manifest.get("recorded_at")
    if not isinstance(manifest_recorded_at, str):
        raise GulfDataHubDubaiGapError("GDH accepted recorded_at is absent")
    if recorded_at is not None and manifest_recorded_at != recorded_at:
        raise GulfDataHubDubaiGapError("GDH accepted recorded_at differs")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("format")
        != "datacenter-atlas-official-source-artifact-manifest-v3"
        or manifest.get("accepted") is not True
        or manifest.get("published") is not True
        or manifest.get("publication_status") != "accepted"
        or manifest.get("publisher_function_present") is not True
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise GulfDataHubDubaiGapError("GDH accepted manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise GulfDataHubDubaiGapError("GDH accepted manifest inventory differs")
    for row in rows:
        raw = artifact_entries[row["path"]].read_bytes()
        if (len(raw), _sha256_bytes(raw)) != (row["bytes"], row["sha256"]):
            raise GulfDataHubDubaiGapError(
                f"GDH accepted manifest pin differs: {row['path']}"
            )
    if manifest.get("tree_sha256") != _sha256_bytes(_canonical(rows)):
        raise GulfDataHubDubaiGapError("GDH accepted logical tree differs")
    if artifact_entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise GulfDataHubDubaiGapError("GDH accepted manifest sidecar differs")

    snapshot = json.loads(
        artifact_entries["source-snapshot.json"].read_text(encoding="utf-8")
    )
    recorded_collision = snapshot.get("accepted_base_and_collision_witness")
    if not isinstance(recorded_collision, dict):
        raise GulfDataHubDubaiGapError("GDH accepted collision witness is absent")
    current_collision = dict(
        collision_witness
        or _collision_witness(
            allow_published_sources=allow_published_sources_in_collision_scan
        )
    )
    _validate_collision_snapshot(recorded_collision, current_collision)
    expected_payloads = _accepted_artifact_payloads(
        manifest_recorded_at, source_records, recorded_collision
    )
    if manifest != _accepted_artifact_manifest(manifest_recorded_at, expected_payloads):
        raise GulfDataHubDubaiGapError("GDH accepted manifest content differs")
    for name in CONTENT_FILES:
        if artifact_entries[name].read_bytes() != expected_payloads[name]:
            raise GulfDataHubDubaiGapError(
                f"GDH accepted artifact content differs: {name}"
            )
    if snapshot.get("source_records") != _accepted_source_records(source_records):
        raise GulfDataHubDubaiGapError("GDH accepted source snapshot differs")

    target = _instant(manifest_recorded_at, "recorded_at")
    if require_live and datetime.now(UTC) < target:
        raise GulfDataHubDubaiGapError("GDH accepted recorded_at is not live")
    if require_final_chronology:
        _assert_birth_mtime_at_or_before(artifact_root, target)
        _assert_ctime_at_or_after(artifact_root, target)
        for path in source_paths.values():
            _assert_birth_mtime_at_or_before(path, target)
            _assert_ctime_at_or_after(path, target)
    counts = _offline_import(source_paths, manifest_recorded_at)
    return {
        "manifest": manifest,
        "database_counts": counts,
        "source_records": _accepted_source_records(source_records),
    }


@dataclass(frozen=True)
class PreparedGdhPublication:
    """Exact accepted bytes staged on the destination filesystems."""

    source_stage: Path
    artifact_stage: Path
    recorded_at: str
    documents: Mapping[str, Mapping[str, Any]]
    collision_witness: Mapping[str, Any]
    immutable_input_state: Mapping[str, Any]
    source_identities: Mapping[str, tuple[int, int, str]]
    artifact_identities: Mapping[str, tuple[int, int, str]]
    source_tree_sha256: str
    artifact_tree_sha256: str


def _stage_source_paths(root: Path) -> dict[str, Path]:
    return {name: root / name for name in SOURCE_FILENAMES}


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepare_publication(recorded_at: str) -> PreparedGdhPublication:
    """Render and replay the exact accepted-format bytes without publishing."""

    _assert_final_absent()
    target = _instant(recorded_at, "recorded_at")
    if datetime.now(UTC) >= target:
        raise GulfDataHubDubaiGapError(
            "GDH recorded_at must be future before publication staging"
        )
    immutable_inputs = _input_state()
    collision = _collision_witness()
    documents = expected_source_documents()
    source_stage = Path(
        tempfile.mkdtemp(prefix=".gdh-dubai-dso456-source-stage-", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.stage-", dir=ARTIFACT_ROOT)
    )
    source_root_identity = _identity(source_stage, directory=True)
    artifact_root_identity = _identity(artifact_stage, directory=True)
    try:
        source_paths = _write_sources(source_stage, documents)
        source_records = _validate_sources(source_paths, frozen=False)
        payloads = _accepted_artifact_payloads(recorded_at, source_records, collision)
        _write_accepted_artifact(artifact_stage, payloads, recorded_at)
        _fsync_directory(source_stage)
        _fsync_directory(artifact_stage)
        _assert_birth_mtime_at_or_before(source_stage, target)
        _assert_birth_mtime_at_or_before(artifact_stage, target)

        first = validate_published_gdh_dubai_dso456(
            source_paths,
            artifact_stage,
            recorded_at=recorded_at,
            require_live=False,
            require_final_chronology=False,
            require_frozen=False,
            allow_published_sources_in_collision_scan=False,
            collision_witness=collision,
        )
        second = validate_published_gdh_dubai_dso456(
            source_paths,
            artifact_stage,
            recorded_at=recorded_at,
            require_live=False,
            require_final_chronology=False,
            require_frozen=False,
            allow_published_sources_in_collision_scan=False,
            collision_witness=collision,
        )
        if first["database_counts"] != second["database_counts"]:
            raise GulfDataHubDubaiGapError(
                "GDH accepted-format offline import replay differs"
            )
        source_identities = _tree_identities(source_stage)
        artifact_identities = _tree_identities(artifact_stage)
        if _input_state() != immutable_inputs:
            raise GulfDataHubDubaiGapError(
                "GDH immutable inputs changed during publication staging"
            )
        return PreparedGdhPublication(
            source_stage=source_stage,
            artifact_stage=artifact_stage,
            recorded_at=recorded_at,
            documents=documents,
            collision_witness=collision,
            immutable_input_state=immutable_inputs,
            source_identities=source_identities,
            artifact_identities=artifact_identities,
            source_tree_sha256=_content_tree_sha256(source_stage),
            artifact_tree_sha256=_content_tree_sha256(artifact_stage),
        )
    except BaseException:
        if _has_identity(source_stage, source_root_identity, directory=True):
            _discard_owned_tree(source_stage)
        if _has_identity(artifact_stage, artifact_root_identity, directory=True):
            _discard_owned_tree(artifact_stage)
        raise


def _assert_prepared_exact(
    prepared: PreparedGdhPublication, *, frozen: bool
) -> dict[str, Any]:
    _assert_tree_identities(prepared.source_stage, prepared.source_identities)
    _assert_tree_identities(prepared.artifact_stage, prepared.artifact_identities)
    if _content_tree_sha256(prepared.source_stage) != prepared.source_tree_sha256:
        raise GulfDataHubDubaiGapError("GDH prepared source tree differs")
    if _content_tree_sha256(prepared.artifact_stage) != prepared.artifact_tree_sha256:
        raise GulfDataHubDubaiGapError("GDH prepared artifact tree differs")
    target = _instant(prepared.recorded_at, "recorded_at")
    _assert_birth_mtime_at_or_before(prepared.source_stage, target)
    _assert_birth_mtime_at_or_before(prepared.artifact_stage, target)
    if _input_state() != prepared.immutable_input_state:
        raise GulfDataHubDubaiGapError("GDH immutable inputs changed after staging")
    return validate_published_gdh_dubai_dso456(
        _stage_source_paths(prepared.source_stage),
        prepared.artifact_stage,
        recorded_at=prepared.recorded_at,
        require_live=False,
        require_final_chronology=False,
        require_frozen=frozen,
        allow_published_sources_in_collision_scan=False,
        collision_witness=prepared.collision_witness,
    )


def _freeze_publication_stages(prepared: PreparedGdhPublication) -> None:
    for path in _stage_source_paths(prepared.source_stage).values():
        path.chmod(0o444)
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    _fsync_directory(prepared.source_stage)
    for path in prepared.artifact_stage.iterdir():
        path.chmod(0o444)
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    prepared.artifact_stage.chmod(0o555)
    _fsync_directory(prepared.artifact_stage)


def _wait_until(target: datetime) -> None:
    while True:
        remaining = target.timestamp() - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _promote_noreplace(source: Path, destination: Path) -> None:
    try:
        promote_noreplace(source, destination)
    except SystemExit as error:
        raise GulfDataHubDubaiGapError(str(error)) from error


def _publish_prepared(prepared: PreparedGdhPublication) -> dict[str, Any]:
    target = _instant(prepared.recorded_at, "recorded_at")
    _assert_final_absent()
    _assert_prepared_exact(prepared, frozen=False)
    _wait_until(target)
    _assert_final_absent()
    if _input_state() != prepared.immutable_input_state:
        raise GulfDataHubDubaiGapError(
            "GDH immutable inputs changed across the live barrier"
        )
    current_collision = _collision_witness()
    _validate_collision_snapshot(prepared.collision_witness, current_collision)
    _assert_prepared_exact(prepared, frozen=False)
    _freeze_publication_stages(prepared)
    validated = _assert_prepared_exact(prepared, frozen=True)
    for path in _stage_source_paths(prepared.source_stage).values():
        _assert_ctime_at_or_after(path, target)
    _assert_ctime_at_or_after(prepared.artifact_stage, target)
    _assert_final_absent()

    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged = prepared.source_stage / name
            final = SOURCES_ROOT / name
            identity = _identity(staged, directory=False)
            _promote_noreplace(staged, final)
            if not _has_identity(final, identity, directory=False):
                raise GulfDataHubDubaiGapError(
                    f"GDH promoted source identity differs: {name}"
                )
            promoted.append((final, staged, identity, False))
        artifact_identity = _identity(prepared.artifact_stage, directory=True)
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        if not _has_identity(ARTIFACT, artifact_identity, directory=True):
            raise GulfDataHubDubaiGapError("GDH promoted artifact identity differs")
        _assert_tree_identities(ARTIFACT, prepared.artifact_identities)
        promoted.append((ARTIFACT, prepared.artifact_stage, artifact_identity, True))
        validated = validate_published_gdh_dubai_dso456(
            recorded_at=prepared.recorded_at,
            require_live=True,
            require_final_chronology=True,
            collision_witness=prepared.collision_witness,
        )
        if _input_state() != prepared.immutable_input_state:
            raise GulfDataHubDubaiGapError(
                "GDH immutable inputs changed during final validation"
            )
    except BaseException as error:
        for final, staged, identity, directory in reversed(promoted):
            try:
                if not _has_identity(final, identity, directory=directory):
                    raise GulfDataHubDubaiGapError(
                        f"GDH refusing identity-mismatched rollback: {final}"
                    )
                _promote_noreplace(final, staged)
                if not _has_identity(staged, identity, directory=directory):
                    raise GulfDataHubDubaiGapError(
                        f"GDH rolled-back identity differs: {staged}"
                    )
            except Exception as rollback_error:
                error.add_note(f"GDH rollback failed for {final}: {rollback_error}")
        raise
    return validated


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise GulfDataHubDubaiGapError("active GDH publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    os.fsync(descriptor)
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != identity
            ):
                raise GulfDataHubDubaiGapError(
                    "refusing substituted GDH publication-lock cleanup"
                )
            PUBLICATION_LOCK.unlink()


def preflight_gdh_dubai_dso456_publication(
    *, recorded_at: str | None = None
) -> dict[str, Any]:
    """Validate and discard exact accepted-format bytes without publication."""

    target = (
        _instant(recorded_at, "recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise GulfDataHubDubaiGapError(
            "GDH publication preflight recorded_at must be future"
        )
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    prepared = _prepare_publication(timestamp)
    try:
        _assert_prepared_exact(prepared, frozen=False)
        _freeze_publication_stages(prepared)
        validated = _assert_prepared_exact(prepared, frozen=True)
        result = {
            "status": "ACCEPTED_FORMAT_PREFLIGHT_VALIDATED_AND_DISCARDED",
            "artifact_id": ARTIFACT_ID,
            "recorded_at": timestamp,
            "artifact_manifest_sha256": _sha256(
                prepared.artifact_stage / "manifest.json"
            ),
            "artifact_tree_sha256": tree_digest(prepared.artifact_stage),
            "source_tree_sha256": tree_digest(prepared.source_stage),
            "source_pins": validated["source_records"],
            "database_counts": validated["database_counts"],
            "published": False,
            "accepted_format": True,
        }
    finally:
        if _has_identity(
            prepared.source_stage,
            prepared.source_identities["."][:2],
            directory=True,
        ):
            _discard_owned_tree(prepared.source_stage)
        if _has_identity(
            prepared.artifact_stage,
            prepared.artifact_identities["."][:2],
            directory=True,
        ):
            _discard_owned_tree(prepared.artifact_stage)
    _assert_final_absent()
    result["source_stage_discarded"] = not prepared.source_stage.exists()
    result["artifact_stage_discarded"] = not prepared.artifact_stage.exists()
    return result


def _existing_identical_publication(recorded_at: str | None) -> dict[str, Any]:
    manifest_path = ARTIFACT / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise GulfDataHubDubaiGapError(
            "GDH complete final set has no ordinary manifest"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing_recorded_at = manifest.get("recorded_at")
    if not isinstance(existing_recorded_at, str):
        raise GulfDataHubDubaiGapError("GDH existing recorded_at is absent")
    if recorded_at is not None and recorded_at != existing_recorded_at:
        raise GulfDataHubDubaiGapError("GDH existing recorded_at differs")
    immutable_inputs = _input_state()
    validated = validate_published_gdh_dubai_dso456(
        recorded_at=existing_recorded_at,
        require_live=True,
        require_final_chronology=True,
    )
    if _input_state() != immutable_inputs:
        raise GulfDataHubDubaiGapError(
            "GDH immutable inputs changed during existing validation"
        )
    return {
        "status": "existing-identical",
        "artifact": str(ARTIFACT),
        "recorded_at": existing_recorded_at,
        "manifest_sha256": _sha256(manifest_path),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": validated["source_records"],
        "database_counts": validated["database_counts"],
        "published": True,
        "accepted_source_records": 3,
        "raw_capture_retained_private": CAPTURE_ROOT.exists(),
    }


def prepare_gdh_dubai_dso456(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Preflight exact bytes, freeze and validate them, then discard the stage."""

    _assert_no_publication()
    input_before = _input_state()
    collision = _collision_witness()
    target = (
        _instant(recorded_at, "recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=90)
    )
    if target <= datetime.now(UTC) or target <= _instant(RETRIEVED_AT, "retrieved_at"):
        raise GulfDataHubDubaiGapError("GDH preflight recorded_at must be future")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    stage_path: Path | None = None
    result: dict[str, Any]
    with tempfile.TemporaryDirectory(
        prefix="gdh-dubai-dso456-prepublication-", dir="/private/tmp"
    ) as temporary:
        stage_path = Path(temporary)
        source_root = stage_path / "sources"
        artifact_root = stage_path / "artifact"
        source_root.mkdir(mode=0o700)
        artifact_root.mkdir(mode=0o700)
        try:
            documents = expected_source_documents()
            source_paths = _write_sources(source_root, documents)
            source_records = _validate_sources(source_paths, frozen=False)
            payloads = _artifact_payloads(timestamp, source_records, collision)
            _write_artifact(artifact_root, payloads, timestamp)
            validate_prepublication_artifact(
                source_root,
                artifact_root,
                recorded_at=timestamp,
                require_frozen=False,
            )
            _freeze_tree(source_root)
            _freeze_tree(artifact_root)
            validated = validate_prepublication_artifact(
                source_root,
                artifact_root,
                recorded_at=timestamp,
                require_frozen=True,
            )
            result = {
                "status": "PREFLIGHT_VALIDATED_AND_DISCARDED",
                "recorded_at": timestamp,
                "artifact_id": ARTIFACT_ID,
                "artifact_manifest_bytes": (artifact_root / "manifest.json")
                .stat()
                .st_size,
                "artifact_manifest_sha256": _sha256(artifact_root / "manifest.json"),
                "artifact_logical_tree_sha256": validated["manifest"]["tree_sha256"],
                "artifact_tree_sha256": tree_digest(artifact_root),
                "source_tree_sha256": tree_digest(source_root),
                "source_pins": source_records,
                "database_counts": validated["database_counts"],
                "candidate_assessments": 3,
                "published": False,
                "accepted": False,
                "open_seed_successor_created": False,
                "raw_capture_retained": True,
            }
        finally:
            _thaw_tree(stage_path)
    if stage_path is None or stage_path.exists():
        raise GulfDataHubDubaiGapError("GDH temporary prepublication stage persists")
    if _input_state() != input_before:
        raise GulfDataHubDubaiGapError("GDH immutable reviewed inputs changed")
    _assert_no_publication()
    result.update(
        {
            "source_stage_discarded": True,
            "artifact_stage_discarded": True,
            "final_source_paths_created": False,
            "final_artifact_path_created": False,
        }
    )
    return result


def publish_gdh_dubai_dso456(
    *,
    recorded_at: str | None = None,
    publication_authorized: bool = False,
) -> dict[str, Any]:
    """Publish exact accepted bytes only after explicit root authorization."""

    if not publication_authorized:
        raise GulfDataHubDubaiGapError(
            "GDH publication requires publication_authorized=True"
        )
    complete, present = _final_presence()
    if complete:
        return _existing_identical_publication(recorded_at)
    if present:
        raise GulfDataHubDubaiGapError(f"GDH partial final-path collision: {present!r}")
    target = (
        _instant(recorded_at, "recorded_at")
        if recorded_at is not None
        else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    )
    if datetime.now(UTC) >= target:
        raise GulfDataHubDubaiGapError(
            "GDH recorded_at must be future before publication"
        )
    if target <= _instant(RETRIEVED_AT, "retrieved_at"):
        raise GulfDataHubDubaiGapError("GDH recorded_at must follow retrieval")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with _publication_lock():
        prepared = _prepare_publication(timestamp)
        try:
            validated = _publish_prepared(prepared)
        except BaseException:
            if _has_identity(
                prepared.source_stage,
                prepared.source_identities["."][:2],
                directory=True,
            ):
                _discard_owned_tree(prepared.source_stage)
            if _has_identity(
                prepared.artifact_stage,
                prepared.artifact_identities["."][:2],
                directory=True,
            ):
                _discard_owned_tree(prepared.artifact_stage)
            raise
        if prepared.source_stage.exists():
            if any(prepared.source_stage.iterdir()):
                raise GulfDataHubDubaiGapError(
                    "GDH source stage is not empty after publication"
                )
            if not _has_identity(
                prepared.source_stage,
                prepared.source_identities["."][:2],
                directory=True,
            ):
                raise GulfDataHubDubaiGapError(
                    "GDH source stage identity differs after publication"
                )
            prepared.source_stage.rmdir()
        validated = validate_published_gdh_dubai_dso456(
            recorded_at=timestamp,
            require_live=True,
            require_final_chronology=True,
            collision_witness=prepared.collision_witness,
        )
    return {
        "status": "published",
        "artifact": str(ARTIFACT),
        "recorded_at": timestamp,
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": validated["source_records"],
        "database_counts": validated["database_counts"],
        "published": True,
        "accepted_source_records": 3,
        "raw_capture_retained_private": CAPTURE_ROOT.exists(),
    }


def main() -> int:
    print(json.dumps(prepare_gdh_dubai_dso456(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
