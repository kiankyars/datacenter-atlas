"""Build a bounded, provenance-first Europe and Central America source tranche."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import discard_release_stage, promote_noreplace, tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "europe-latam-official-discovery-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".europe-latam-official-discovery-20260721.lock"
CAPTURE_ORIGIN = Path("/tmp/dc-europe-latam-official-20260721.eA43A2")
CAPTURE_TRASH = Path(
    "/Users/kian/.Trash/dc-europe-latam-official-20260721.eA43A2"
)

V69_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v69.json"
V69_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v69/manifest.json"
V69_ENTITIES = ROOT / "releases/2026-07-21-open-seed-v69/entities.csv"
V69_PINS = {
    V69_DEFINITION: (86041, "d72275d4d0c37f90bffa694ae15f2b58fc1c03d70f69501e2c16abde425748ff"),
    V69_MANIFEST: (12432, "1708696cb999baa00fba2f97b05277bb0156e6eebf878bd16cc8ad6cfe6153f0"),
    V69_ENTITIES: (874687, "2063df8e053d1391078368a26f10577901b8a9e8e1cf7e7ca67225c8c937425f"),
}

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-21-arnes-maribor-construction-start.json": {
        "bytes": 8971,
        "sha256": "24be5cec5cdb1df39a4287a65e39f41053bc40976a06fa77fa45be3a717d6dac",
        "campus": "curated:arnes-maribor-data-center-site",
        "project": "curated:arnes-maribor-data-center-site:source-scoped-development",
        "evidence_keys": [
            "slovenia-arnes-maribor-construction-start-2025-05-06-captured-2026-07-21",
            "slovenia-arnes-maribor-current-project-page-captured-2026-07-21",
        ],
        "lifecycle": [
            "under_construction",
            "2025-05-06",
            "authoritative_construction_start",
        ],
        "capacity_estimates": 0,
    },
    "curated-official-2026-07-21-kio-second-guatemala-construction-start.json": {
        "bytes": 7862,
        "sha256": "5265afc6c6c3ed8947eee54de73f31328accd1badf513500b39acf65278bad4f",
        "campus": "curated:kio-tec-guatemala-campus",
        "project": "curated:kio-tec-guatemala-campus:second-data-center",
        "evidence_keys": [
            "guatemala-kio-second-data-center-construction-start-2025-09-25-captured-2026-07-21"
        ],
        "lifecycle": [
            "under_construction",
            "2025-09-25",
            "authoritative_construction_start",
        ],
        "capacity_estimates": 2,
    },
}

CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    "arnes_government_start": {
        "requested_url": "https://www.gov.si/en/news/2025-05-06-foundation-stone-unveiled-for-arnes-data-centre/",
        "retrieved_at": "2026-07-21T09:47:50Z",
        "response_http_date": "2026-07-21T09:47:48Z",
        "http_status": 200,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 7125,
        "header_count": 16,
        "body": (27297, "6b5055e992e3da2a53ae3e4af8a9e99d6fe10be14605d6187edc30812e2ac2c7"),
        "headers": (733, "ff078061f84dc56c060f7d33c2f157d895033478b181eced8360cb1704663fe1"),
        "writeout": (19036, "eac4cd409b2e80c49ce74a5b77afa4f7ad3821721c66441f46ab401892b4b3d6"),
        "evidence_keys": [
            "slovenia-arnes-maribor-construction-start-2025-05-06-captured-2026-07-21"
        ],
    },
    "arnes_project_page": {
        "requested_url": "https://www.arnes.si/vzpostavitev-podatkovnega-centra-maribor/",
        "retrieved_at": "2026-07-21T09:47:51Z",
        "response_http_date": "2026-07-21T09:47:50Z",
        "http_status": 200,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding_as_received": None,
        "wire_download_bytes": 219856,
        "header_count": 9,
        "body": (219856, "50a56d47914b2a37f2b87609eb2380d7b6e6eaf518e2266ffcf670f6b77bc381"),
        "headers": (649, "871f70c574659ec71bef11fc1c4373dec56e50bbeb20a3158be0bd4a36d5401d"),
        "writeout": (13155, "7b6496872a569b2f8a2ab4fb3e02d839332f6c21fed2fada0ceff8e5984a3472"),
        "evidence_keys": [
            "slovenia-arnes-maribor-current-project-page-captured-2026-07-21"
        ],
    },
    "kio_gtm2_start": {
        "requested_url": "https://kiodatacenters.com/en/newsroom/expansion/kio-data-centers-will-invest-more-than-400-million-in-capex-in-the-region-and-quadruple-its-capacity-in-guatemala",
        "retrieved_at": "2026-07-21T09:47:52Z",
        "response_http_date": "2026-07-21T03:57:50Z",
        "http_status": 200,
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "content_encoding_as_received": "gzip",
        "wire_download_bytes": 23023,
        "header_count": 16,
        "body": (90398, "fb51bca41741462937c17104bf7884a45330fac58e3caa93e44fcfafb16ec6dd"),
        "headers": (591, "53ec8da0ae8eb2e34da8c11b0592cce86893734427b0f66de22fecb0d7963556"),
        "writeout": (16690, "4b8a2eca2fefadfc7b98a7e9f92b0844d4d3b592fa7334e2cc51eeca6360e428"),
        "evidence_keys": [
            "guatemala-kio-second-data-center-construction-start-2025-09-25-captured-2026-07-21"
        ],
    },
}

CONTENT_FILES = (
    "README.md",
    "identity-and-capacity-guardrails.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

EXCLUDED_NON_ACCEPTED_LINEAGE = [
    "sources/open-seed-2026-07-21-v68.json",
    "releases/2026-07-21-open-seed-v68",
    "sources/construction-timeline-2026-07-21-public-open-v4.json",
    "construction_timelines/2026-07-21-public-open-v4",
    "sources/federation-2026-07-21-public-open-v29.json",
    "federated_indexes/2026-07-21-public-open-v29",
    "sources/exact-identity-decisions-2026-07-21-public-open-v7.json",
    "exact_identity_decisions/2026-07-21-public-open-v7",
    "source_artifacts/site-coordinate-assessment-2026-07-21-v1",
    "source_artifacts/gap-region-official-discovery-2026-07-21-v1",
    "source_artifacts/global-underrepresented-official-discovery-2026-07-21-v1",
    "source_artifacts/second-underrepresented-official-discovery-2026-07-21-v1",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(document: object) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _file_tree(rows: list[dict[str, Any]]) -> str:
    payload = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"pinned ordinary file is absent: {path}")
    actual = (len(path.read_bytes()), _sha256(path))
    if actual != expected:
        raise SystemExit(f"pinned file differs: {path}: {actual!r}")


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise SystemExit(f"active publication lock exists: {PUBLICATION_LOCK}") from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            PUBLICATION_LOCK.unlink()
        except FileNotFoundError:
            pass


def _validate_sources() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    claimed_stable: set[str] = set()
    claimed_evidence: set[str] = set()
    for name, spec in SOURCE_SPECS.items():
        source = ROOT / "sources" / name
        _pin(source, (spec["bytes"], spec["sha256"]))
        raw = source.read_bytes()
        document = json.loads(raw)
        if raw != _canonical(document) or document.get("schema_version") != "1.1":
            raise SystemExit(f"curated source is not canonical schema 1.1: {name}")
        stable = {document["campus"]["stable_key"], document["project"]["stable_key"]}
        evidence = {row["key"] for row in document["evidence"]}
        if stable != {spec["campus"], spec["project"]} or evidence != set(
            spec["evidence_keys"]
        ):
            raise SystemExit(f"curated source identity differs: {name}")
        if document["lifecycle"] != [
            {
                "entity": "project",
                "value": spec["lifecycle"][0],
                "evidence_key": document["lifecycle"][0]["evidence_key"],
                "as_of_date": spec["lifecycle"][1],
                "method": spec["lifecycle"][2],
                "confidence": 0.99,
            }
        ]:
            raise SystemExit(f"curated source lifecycle differs: {name}")
        if len(document["capacities"]) != spec["capacity_estimates"]:
            raise SystemExit(f"curated source capacity count differs: {name}")
        if document["campus"]["coordinates"] is not None or document["project"]["coordinates"] is not None:
            raise SystemExit(f"curated source invented coordinates: {name}")
        if document["campus"]["geometry"] is not None or document["project"]["geometry"] is not None:
            raise SystemExit(f"curated source invented geometry: {name}")
        claimed_stable.update(stable)
        claimed_evidence.update(evidence)
        records.append(
            {
                "path": f"sources/{name}",
                "bytes": spec["bytes"],
                "sha256": spec["sha256"],
                "schema_version": "1.1",
                "country": document["project"]["country"],
                "campus_stable_key": spec["campus"],
                "project_stable_key": spec["project"],
                "lifecycle_status": spec["lifecycle"][0],
                "lifecycle_as_of_date": spec["lifecycle"][1],
                "lifecycle_method": spec["lifecycle"][2],
                "current_status_as_of_research_date": "unknown",
                "capacity_estimate_count": spec["capacity_estimates"],
                "seeded": False,
            }
        )

    new_names = set(SOURCE_SPECS)
    collisions: dict[str, dict[str, list[str]]] = {}
    for other in (ROOT / "sources").glob("*.json"):
        if other.name in new_names:
            continue
        try:
            document = json.loads(other.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        other_stable = {
            item["stable_key"]
            for item in (document.get("campus"), document.get("project"))
            if isinstance(item, dict) and isinstance(item.get("stable_key"), str)
        }
        other_evidence = {
            row["key"]
            for row in document.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("key"), str)
        }
        stable_overlap = sorted(claimed_stable & other_stable)
        evidence_overlap = sorted(claimed_evidence & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[other.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise SystemExit(f"curated source collision: {collisions!r}")

    for path, expected in V69_PINS.items():
        _pin(path, expected)
    definition = json.loads(V69_DEFINITION.read_text(encoding="utf-8"))
    selected = {row["path"] for row in definition["curated_inputs"]}
    if selected & {record["path"] for record in records}:
        raise SystemExit("new artifact-only sources were unexpectedly selected by v69")
    entities_text = V69_ENTITIES.read_text(encoding="utf-8")
    if any(value in entities_text for value in claimed_stable):
        raise SystemExit("new project keys collide with frozen v69 entities")
    return records


def _validate_captures(capture_directory: Path) -> None:
    if not capture_directory.is_dir() or capture_directory.is_symlink():
        raise SystemExit(f"capture directory is absent or unsafe: {capture_directory}")
    if stat.S_IMODE(capture_directory.stat().st_mode) != 0o700:
        raise SystemExit("capture directory mode differs")
    packaged_capture = capture_directory not in (CAPTURE_ORIGIN, CAPTURE_TRASH)
    expected_names = {
        f"{request_id}.{suffix}"
        for request_id in CAPTURE_SPECS
        for suffix in ("body", "headers", "writeout")
    }
    actual_names = {path.name for path in capture_directory.iterdir()}
    if actual_names != expected_names:
        raise SystemExit("capture directory file closure differs")
    for request_id, spec in CAPTURE_SPECS.items():
        for suffix in ("body", "headers", "writeout"):
            carrier = capture_directory / f"{request_id}.{suffix}"
            _pin(carrier, spec[suffix])
            if stat.S_IMODE(carrier.stat().st_mode) != 0o644:
                raise SystemExit(f"capture carrier mode differs: {carrier.name}")
        writeout = json.loads(
            (capture_directory / f"{request_id}.writeout").read_text(encoding="utf-8")
        )
        expected_writeout = (
            spec["requested_url"],
            spec["http_status"],
            spec["http_version"].removeprefix("HTTP/"),
            spec["content_type"],
            spec["wire_download_bytes"],
            spec["headers"][0],
            spec["header_count"],
            0,
        )
        actual_writeout = (
            writeout["url_effective"],
            writeout["response_code"],
            writeout["http_version"],
            writeout["content_type"],
            writeout["size_download"],
            writeout["size_header"],
            writeout["num_headers"],
            writeout["num_redirects"],
        )
        if actual_writeout != expected_writeout:
            raise SystemExit(f"capture writeout differs: {request_id}")
        body = capture_directory / f"{request_id}.body"
        if not packaged_capture:
            completion = datetime.fromtimestamp(
                body.stat().st_birthtime,
                timezone.utc,
            )
            if completion.replace(microsecond=0) != _parse_utc(spec["retrieved_at"]):
                raise SystemExit(f"capture completion timestamp differs: {request_id}")


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    requests = []
    for request_id, spec in CAPTURE_SPECS.items():
        requests.append(
            {
                "request_id": request_id,
                "use": "evidence",
                "evidence_keys": spec["evidence_keys"],
                "contributes_evidence": True,
                "requested_url": spec["requested_url"],
                "effective_url": spec["requested_url"],
                "retrieved_at": spec["retrieved_at"],
                "retrieval_timestamp_basis": "UTC filesystem birth second of the completed content-decoded response body",
                "curl_exit_code": 0,
                "http_status": spec["http_status"],
                "http_version": spec["http_version"],
                "content_type": spec["content_type"],
                "content_encoding_as_received": spec["content_encoding_as_received"],
                "response_http_date": spec["response_http_date"],
                "response_http_date_used_as_retrieved_at": False,
                "wire_download_bytes": spec["wire_download_bytes"],
                "curl_header_bytes": spec["headers"][0],
                "curl_num_headers": spec["header_count"],
                "redirect_count": 0,
                "body": {
                    "bytes": spec["body"][0],
                    "sha256": spec["body"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "headers": {
                    "bytes": spec["headers"][0],
                    "sha256": spec["headers"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
                "curl_writeout": {
                    "bytes": spec["writeout"][0],
                    "sha256": spec["writeout"][1],
                    "retained_in_artifact": False,
                    "moved_to_trash": True,
                },
            }
        )
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v1",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": "Credential-free public curl GETs with HTTPS redirects, content decoding, a transparent research User-Agent, separate exact response bodies, raw response-header streams, and newline-terminated curl JSON writeouts.",
        "direct_request_attempts": 3,
        "completed_response_requests": 3,
        "successful_http_requests": 3,
        "evidence_supporting_captures": 3,
        "request_credentials_supplied": False,
        "browser_session_used": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "curl_writeouts_retained_in_artifact": False,
        "response_cookies_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_http_requests": requests,
    }


def _country_screen() -> list[dict[str, str]]:
    return [
        {
            "country": "Slovenia",
            "candidate": "Arnes Maribor Data Center",
            "decision": "promoted_last_observed_construction_start",
            "basis": "A dated Slovenian government release says construction began and the foundation stone was unveiled on 2025-05-06; July 2026 current status remains unknown.",
        },
        {
            "country": "Guatemala",
            "candidate": "KIO second Guatemala data center",
            "decision": "promoted_last_observed_construction_start",
            "basis": "KIO's dated release explicitly announces a construction start on 2025-09-25 and types 2 MW as design IT load; July 2026 current status remains unknown.",
        },
        {
            "country": "Poland",
            "candidate": "DATA4 Poland, Atman WAW-3 later buildings, and KCPD",
            "decision": "not_promoted",
            "basis": "Current official material found operational facilities or planning, design, and contracting language without a distinct qualifying physical start for an unrepresented current project.",
        },
        {
            "country": "Romania",
            "candidate": "ClusterPower expansion",
            "decision": "identity_or_milestone_date_insufficient",
            "basis": "The official contractor chronology says design and works started in 2024 but provides no day or month and does not identify a distinct phase boundary suitable for a new record.",
        },
        {
            "country": "Hungary",
            "candidate": "Szeged mixed-use industry and research development",
            "decision": "milestone_scope_not_data_center_specific",
            "basis": "The physical milestone applied to a broader mixed-use development that includes a data-center component, not to a separately identified data-center project.",
        },
        {
            "country": "Bulgaria",
            "candidate": "Neterra SDC-2",
            "decision": "historical_only_current_unknown",
            "basis": "The official groundbreaking was in 2021 and the bounded screen found no later official evidence establishing that an unrepresented project remains physically under construction.",
        },
        {
            "country": "Serbia",
            "candidate": "Kragujevac State Data Center Block 2",
            "decision": "not_promoted",
            "basis": "Official material remained planned; no dated site preparation, civil works, foundations, shell, MEP, or commissioning milestone was found for Block 2.",
        },
        {
            "country": "Croatia",
            "candidate": "Pantheon data-center proposal",
            "decision": "not_promoted",
            "basis": "Official material was an MOU or letter of intent with a future 2027 construction horizon, not a completed physical milestone.",
        },
        {
            "country": "Costa Rica",
            "candidate": "bounded official-source screen",
            "decision": "no_qualifying_candidate_found",
            "basis": "No current, distinct, primary-source data-center project with a dated qualifying physical milestone was found in the bounded screen.",
        },
        {
            "country": "Panama",
            "candidate": "bounded KIO and government screen",
            "decision": "no_qualifying_candidate_found",
            "basis": "The bounded official-source screen found operational infrastructure but no unrepresented project with a dated qualifying physical milestone.",
        },
        {
            "country": "Dominican Republic",
            "candidate": "KIO SDO1 and government facilities",
            "decision": "not_current_build",
            "basis": "The screened official facilities were operational or inaugurated; no unrepresented current project with a dated qualifying physical milestone was found.",
        },
    ]


def _write_stage(stage: Path, recorded_at: str, source_records: list[dict[str, Any]]) -> None:
    readme = f"""# Europe and Central America official-source discovery tranche

This immutable, hash-only artifact records a bounded 2026-07-21 screen of eleven countries absent or thin in frozen open seed v69. Exactly two records pass the physical-milestone boundary: the Arnes Maribor data centre in Slovenia and KIO's source-scoped second Guatemala data center. Both preserve the last observed construction-start date while declaring current July 2026 status unknown.

## Acceptance boundary

A record requires a current primary official operator, government, contractor, utility, filing, or project source and a dated milestone that explicitly applies to a distinct data-centre project: groundbreaking, site preparation, civil works, foundations, shell, MEP, or commissioning. Permits, financing, MOUs, site control, future starts, cloud regions, generic development labels, mixed-use milestones, and operational facilities do not qualify.

The KIO record normalizes only the source-typed 2 MW design IT load and 1.5 design target PUE. The Arnes record emits no power or energy value. Neither record has coordinates or geometry, and neither uses maps, publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation.

## Publication and lineage

The artifact was built in a unique sibling staging directory, assigned the real UTC timestamp `{recorded_at}` only after that staging directory existed, validated against staging birth and wall clock, frozen, and atomically promoted without replacement. It does not mutate or select into open seed v69 and is not integrated into a release, construction timeline, federation, identity bundle, coordinate successor, coverage ledger, or downstream product.

All rejected temporal v68/v1/timeline-v4/federation-v29/identity-v7 artifacts and the rejected coordinate-v1 artifact are explicit non-inputs. Raw all-rights-reserved captures are not redistributed; their complete nine-file directory was moved intact to the unique recoverable Trash path recorded in the rights inventory.

## Replay

Offline replay validates the closed file set, manifest hashes, canonical JSON, source hashes, collision isolation, schema-1.1 imports, temporal boundaries, v69 non-mutation pins, typed capacity stages, absent coordinates, and exclusion list. The compact source documents under `sources/` are the only promoted records.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "release_integration": "none",
        "open_seed_integration": "none",
        "construction_timeline_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "coordinate_integration": "none",
        "coverage_ledger_integration": "none",
        "downstream_product_integration": "none",
        "bounded_scope": {
            "countries_screened": [
                "Poland",
                "Romania",
                "Hungary",
                "Bulgaria",
                "Serbia",
                "Croatia",
                "Slovenia",
                "Costa Rica",
                "Panama",
                "Dominican Republic",
                "Guatemala",
            ],
            "country_count": 11,
            "maximum_promotions": 8,
            "accepted_records": 2,
            "zero_promotion_audit_required": False,
        },
        "source_records": source_records,
        "totals": {
            "source_records": 2,
            "distinct_campuses": 2,
            "projects": 2,
            "unique_evidence_records": 3,
            "entity_snapshots": 4,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
            "coordinates_present": 0,
            "geometry_present": 0,
            "current_status_unknown": 2,
        },
        "country_screen": _country_screen(),
        "frozen_v69_non_mutation_witness": {
            "definition_path": "sources/open-seed-2026-07-21-v69.json",
            "definition_bytes": V69_PINS[V69_DEFINITION][0],
            "definition_sha256": V69_PINS[V69_DEFINITION][1],
            "release_manifest_path": "releases/2026-07-21-open-seed-v69/manifest.json",
            "release_manifest_bytes": V69_PINS[V69_MANIFEST][0],
            "release_manifest_sha256": V69_PINS[V69_MANIFEST][1],
            "entities_path": "releases/2026-07-21-open-seed-v69/entities.csv",
            "entities_bytes": V69_PINS[V69_ENTITIES][0],
            "entities_sha256": V69_PINS[V69_ENTITIES][1],
            "v69_selected_input_count": 391,
            "new_source_paths_selected_by_v69": False,
            "new_project_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "excluded_non_accepted_lineage": EXCLUDED_NON_ACCEPTED_LINEAGE,
    }
    guardrails = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-identity-and-capacity-guardrails-v1",
        "recorded_at": recorded_at,
        "identity": {
            "no_centroids": True,
            "no_coordinates": True,
            "no_geometry": True,
            "no_satellite_inference": True,
            "no_computer_vision_inference": True,
            "no_analyst_geolocation": True,
            "no_unstated_phase_splits": True,
            "no_unsupported_gtm2_alias": True,
            "stable_key_collision_count": 0,
            "evidence_key_collision_count": 0,
        },
        "lifecycle": {
            "accepted_status": "under_construction",
            "accepted_methods": ["authoritative_construction_start"],
            "last_observed_not_current": True,
            "current_status_as_of_2026_07_21": "unknown",
            "future_start_not_accepted": True,
            "permit_or_mou_not_accepted": True,
            "operational_not_accepted_as_build": True,
        },
        "capacity": {
            "arnes_normalized_rows": 0,
            "kio_rows": [
                {
                    "metric": "critical_it_mw",
                    "stage": "design",
                    "unit": "MW",
                    "value": 2.0,
                },
                {
                    "metric": "pue",
                    "stage": "design",
                    "unit": "ratio",
                    "value": 1.5,
                },
            ],
            "no_installed_capacity_inference": True,
            "no_energized_capacity_inference": True,
            "no_operational_capacity_inference": True,
            "no_current_load_inference": True,
            "no_annual_energy_inference": True,
            "component_double_counting": False,
        },
        "roles_and_classification": {
            "arnes_operator_role_explicit": True,
            "kio_roles_emitted": 0,
            "operating_models_emitted": 0,
            "workloads_emitted": 0,
            "tenants_or_customers_emitted": 0,
        },
        "lineage": {
            "release_integration": "none",
            "v69_mutation": False,
            "excluded_non_accepted_lineage": EXCLUDED_NON_ACCEPTED_LINEAGE,
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v1",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": "All captured publisher response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "curl_writeouts_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "response_cookies_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "browser_session_used": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_move_scope": "The entire nine-file directory was atomically moved intact, including three response bodies, three raw response-header streams, and three curl JSON writeouts.",
        "deletion_performed": False,
    }
    documents = {
        "README.md": readme.encode(),
        "identity-and-capacity-guardrails.json": _canonical(guardrails),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }
    for name, payload in documents.items():
        (stage / name).write_bytes(payload)
    rows = []
    for name in CONTENT_FILES:
        payload = (stage / name).read_bytes()
        rows.append(
            {
                "bytes": len(payload),
                "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v1",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "curated_source_records": 2,
        "successful_raw_captures": 3,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "release_integration": "none",
        "open_seed_integration": "none",
        "downstream_product_integration": "none",
    }
    (stage / "manifest.json").write_bytes(_canonical(manifest))
    (stage / "manifest.sha256").write_text(
        f"{_sha256(stage / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    require_frozen: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    source_records = _validate_sources()
    if not path.is_dir() or path.is_symlink():
        raise ValueError("artifact must be an ordinary directory")
    if require_frozen and stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise ValueError("artifact directory is not frozen")
    entries = {item.name: item for item in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise ValueError("artifact closed file set differs")
    if any(item.is_symlink() or not item.is_file() for item in entries.values()):
        raise ValueError("artifact contains a non-ordinary file")
    if require_frozen and any(
        stat.S_IMODE(item.stat().st_mode) != 0o444 for item in entries.values()
    ):
        raise ValueError("artifact file mode differs")
    for name in CONTENT_FILES[1:]:
        raw = entries[name].read_bytes()
        if raw != _canonical(json.loads(raw)):
            raise ValueError(f"artifact JSON is not canonical: {name}")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise ValueError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("curated_source_records") != 2
        or manifest.get("release_integration") != "none"
        or manifest.get("open_seed_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise ValueError("manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), hashlib.sha256(payload).hexdigest()) != (
            row["bytes"],
            row["sha256"],
        ):
            raise ValueError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n"
    ):
        raise ValueError("manifest checksum differs")
    recorded_at = _parse_utc(manifest["recorded_at"])
    wall_clock = validation_wall_clock or datetime.now(timezone.utc)
    birth = datetime.fromtimestamp(path.stat().st_birthtime, timezone.utc)
    if birth > recorded_at or recorded_at > wall_clock:
        raise ValueError("artifact temporal boundary differs")
    for name in CONTENT_FILES[1:]:
        document = json.loads(entries[name].read_text(encoding="utf-8"))
        if document.get("recorded_at") != manifest["recorded_at"]:
            raise ValueError(f"artifact timestamp carrier differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text())
    if snapshot["source_records"] != source_records:
        raise ValueError("source snapshot pins differ")
    if snapshot["excluded_non_accepted_lineage"] != EXCLUDED_NON_ACCEPTED_LINEAGE:
        raise ValueError("non-accepted lineage exclusion differs")
    for name in SOURCE_SPECS:
        document = json.loads((ROOT / "sources" / name).read_text())
        for evidence in document["evidence"]:
            if _parse_utc(evidence["retrieved_at"]) > recorded_at:
                raise ValueError("evidence retrieval post-dates artifact recording")
    return manifest


def _capture_after_stage_birth(stage: Path) -> str:
    birth = stage.stat().st_birthtime
    deadline = time.time() + 1.1
    rollover = math.ceil(birth)
    while time.time() < rollover:
        if time.time() > deadline:
            raise SystemExit("filesystem rollover exceeded one second")
        time.sleep(0.005)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _offline_import(recorded_at: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        for name in SOURCE_SPECS:
            CuratedOfficialSourceAdapterV11().import_file(
                connection,
                ROOT / "sources" / name,
                recorded_at=recorded_at,
            )
        validate_database(connection)


def build() -> dict[str, Any]:
    if ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise SystemExit(f"artifact already exists; refusing replacement: {ARTIFACT}")
    source_records = _validate_sources()
    with publication_lock():
        stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
        published = False
        try:
            if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
                raise SystemExit("both capture origin and Trash destination exist")
            if CAPTURE_ORIGIN.exists():
                _validate_captures(CAPTURE_ORIGIN)
                promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
            _validate_captures(
                resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
            )
            recorded_at = _capture_after_stage_birth(stage)
            if any(
                _parse_utc(spec["retrieved_at"]) > _parse_utc(recorded_at)
                for spec in CAPTURE_SPECS.values()
            ):
                raise SystemExit("capture retrieval post-dates artifact recording")
            _offline_import(recorded_at)
            _write_stage(stage, recorded_at, source_records)
            for item in stage.iterdir():
                item.chmod(0o444)
            stage.chmod(0o555)
            validate_artifact(stage, validation_wall_clock=datetime.now(timezone.utc))
            promote_noreplace(stage, ARTIFACT)
            published = True
            manifest = validate_artifact(
                ARTIFACT, validation_wall_clock=datetime.now(timezone.utc)
            )
        finally:
            if not published:
                discard_release_stage(stage)
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "tree_sha256": tree_digest(ARTIFACT),
        "curated_source_records": 2,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
