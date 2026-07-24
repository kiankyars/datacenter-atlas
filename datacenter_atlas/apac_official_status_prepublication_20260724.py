"""Build a private APAC official-status candidate, without publishing it.

The candidate normalizes three sparse, date-bounded observations:

* Converge Angeles Data Center was serving as an operating strategic hub on
  2026-07-24;
* GULF's GSA02 project in Chonburi was currently under construction; and
* GULF's GEDC01 project in Rayong was currently under construction.

All other findings remain in a compact discovery ledger.  The builder has no
publisher and never mutates the frozen v97 release or any downstream product.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database

ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"

ARTIFACT_ID = "apac-official-status-prepublication-2026-07-24-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID

CONVERGE_SOURCE_FILENAME = (
    "curated-official-2026-07-24-converge-angeles-operational.json"
)
GSA02_SOURCE_FILENAME = (
    "curated-official-2026-07-24-gulf-gsa02-current-build.json"
)
GEDC01_SOURCE_FILENAME = (
    "curated-official-2026-07-24-gulf-gedc01-current-build.json"
)
SOURCE_FILENAMES = (
    CONVERGE_SOURCE_FILENAME,
    GSA02_SOURCE_FILENAME,
    GEDC01_SOURCE_FILENAME,
)

CAPTURE_ORIGIN = Path(
    "/private/tmp/dc-apac-official-discovery-20260724.Dcf64Z"
)
CAPTURE_FILE_COUNT = 8
CAPTURE_TOTAL_BYTES = 289_922
CAPTURE_TREE_SHA256 = (
    "c5ac7def3f309ea03b8c5c7862a649dba725d79d3941ee0623691b4331236a2e"
)
CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "converge.body": (
        82_928,
        "7c287f16527866b3ad9180db93663b6e69c3f710c08d83d4da7c680a76bf0d9c",
    ),
    "converge.headers": (
        958,
        "411996cf00897da4e559d1d3573aeaa2edce1b083aa342696fc5c6c6ca8ea182",
    ),
    "gulf-filing.body": (
        193_328,
        "2fd2abb47c4179ae2e38ae3828cdc2886992af8041796dbf8f6bbee1f4f4c66a",
    ),
    "gulf-filing.headers": (
        690,
        "b303613e56138dbdcc8f7370659bb11709f63bd6894e27e99b13c7acc004cc95",
    ),
    "gulf-viewer.body": (
        6_072,
        "998b1e0b3317ad9f51cf2a868d83da6efc0bea0ca541538dbed5580a2551ba2e",
    ),
    "gulf-viewer.headers": (
        2_028,
        "b4a441482c13e2d186e888190886f15a4712cc6ae22119a4067f03b26a278580",
    ),
    "gulf-wrapper.body": (
        2_744,
        "f1564d58deadb3c4ad6943a41c1353b4fe825f67a4af8d836fd6278febc8bd89",
    ),
    "gulf-wrapper.headers": (
        1_174,
        "97ea4dc177395fe0d9c197613e143c74584aa39bbe7ebd67e20613fbc16fa449",
    ),
}

CONVERGE_URL = (
    "https://corporate.convergeict.com/newsroom/"
    "converge-data-center-ready-to-support-government-data-residency-"
    "under-president-marcos-eo-119"
)
GULF_URL = (
    "https://investor.gulf.co.th/en/document/viewer/197866/"
    "establishment-of-gulf-edge-data-center-03-company-limited-and-"
    "gulf-edge-data-center-04-company-limited"
)
GULF_WRAPPER_URL = (
    "https://hub.optiwise.io/en/documents/225428/"
    "644370581ADCC73C2A43725E1ADAC538670F702F1DDCC63E663170566BADB14B"
    "6144735912A9CC4C154477566CA8B33961466C1E4E8DCF3A6243755C1AD9C339"
    "6440735C1FDFC03D66366C1E4E8D_240720261231254550E.pdf"
)
GULF_PDF_URL = (
    "https://optiwise.infoquest.io/v2/setnews/view?doc_id="
    "644370581ADCC73C2A43725E1ADAC538670F702F1DDCC63E663170566BADB14B"
    "6144735912A9CC4C154477566CA8B33961466C1E4E8DCF3A6243755C1AD9C339"
    "6440735C1FDFC03D66366C1E4E8D_240720261231254550E.pdf"
    "&action=inline&viewer=office"
)
CONVERGE_RETRIEVED_AT = "2026-07-24T21:59:56Z"
GULF_VIEWER_RETRIEVED_AT = "2026-07-24T21:59:57Z"
GULF_WRAPPER_RETRIEVED_AT = "2026-07-24T21:59:57Z"
GULF_PDF_RETRIEVED_AT = "2026-07-24T21:59:58Z"

V97_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v97.json"
V97_RELEASE = ROOT / "releases/2026-07-22-open-seed-v97"
V97_MANIFEST = V97_RELEASE / "manifest.json"
V97_ENTITIES = V97_RELEASE / "entities.csv"
V97_EVIDENCE = V97_RELEASE / "evidence.csv"
V97_SOURCE_INPUTS = V97_RELEASE / "source_inputs.json"
V97_DEFINITION_PIN = (
    120_979,
    "32f22ccc74ec6ec33dc9bc7377a83bfee83f88dff3555555fc89cb43a27d673f",
)
V97_MANIFEST_PIN = (
    20_402,
    "0a6f41f4239944df27f2ce70e81a089b91cec401f154bbae28412b27a4d00fdd",
)
V97_ENTITIES_PIN = (
    1_076_359,
    "7950a4e871d4afd0fd877e6e4f3ba9f9cbc1ffd664a611bc036896fbdba46fa1",
)
V97_EVIDENCE_PIN = (
    271_797,
    "c73263c3b27f984c8bebf76f9db31b63a22059a3774dbec9ed944ceee344f2d1",
)
V97_RELEASE_TREE_SHA256 = (
    "5136ad66f56b7474053ff3b8cbbffca1f3df3479d8a30745a1502917fa0e7954"
)
V97_CURATED_INPUT_COUNT = 519
V97_ENTITY_COUNT = 1_053
V97_EVIDENCE_COUNT = 693

DAYONE_SOURCE = (
    SOURCES_ROOT / "curated-official-2026-07-19-dayone-chonburi-ctp1.json"
)
DIGITAL_EDGE_SOURCE = (
    SOURCES_ROOT
    / "curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json"
)
NEARBY_SOURCE_PINS = {
    "sources/curated-official-2026-07-19-dayone-chonburi-ctp1.json": (
        11_915,
        "42cf9d67828563e92cc0b80ae30cfdf0d3a9849f19612b3ff7eaee4ee54889d4",
    ),
    (
        "sources/curated-official-2026-07-20-"
        "digital-edge-bgrimm-chonburi-eec.json"
    ): (
        11_187,
        "c31ecbe7fb4b8e47de2683c0b321d5dd3e59dda1fbf596218ceab0ef7e191f94",
    ),
}
DAYONE_SOURCE_PIN = NEARBY_SOURCE_PINS[
    "sources/curated-official-2026-07-19-dayone-chonburi-ctp1.json"
]
DIGITAL_EDGE_SOURCE_PIN = NEARBY_SOURCE_PINS[
    "sources/curated-official-2026-07-20-"
    "digital-edge-bgrimm-chonburi-eec.json"
]
DAYONE_SOURCE_RETRIEVED_AT = "2026-07-19T19:48:32Z"
DIGITAL_EDGE_SOURCE_RETRIEVED_AT = "2026-07-20T19:58:23Z"

CONVERGE_CAMPUS_KEY = "curated:converge-angeles-data-center"
CONVERGE_PROJECT_KEY = f"{CONVERGE_CAMPUS_KEY}:current-facility"
GSA02_CAMPUS_KEY = "curated:gulf-gsa02-chonburi-eec-data-center"
GSA02_PROJECT_KEY = f"{GSA02_CAMPUS_KEY}:current-build"
GEDC01_CAMPUS_KEY = "curated:gulf-gedc01-rayong-eec-data-center"
GEDC01_PROJECT_KEY = f"{GEDC01_CAMPUS_KEY}:current-build"
CONVERGE_EVIDENCE_KEY = (
    "converge-angeles-operational-observed-2026-07-24"
)
GSA02_EVIDENCE_KEY = "gulf-gsa02-status-disclosure-2026-07-24"
GEDC01_EVIDENCE_KEY = "gulf-gedc01-status-disclosure-2026-07-24"

DAYONE_CAMPUS_KEY = "curated:dayone-chonburi-tech-park-campus"
DAYONE_PROJECT_KEY = f"{DAYONE_CAMPUS_KEY}:ctp1-current-development"
DIGITAL_EDGE_CAMPUS_KEY = (
    "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus"
)
DIGITAL_EDGE_PROJECT_KEY = f"{DIGITAL_EDGE_CAMPUS_KEY}:current-development"

CONTENT_FILES = (
    "README.md",
    "discovery-ledger.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


@dataclass(frozen=True)
class PreparedCandidate:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


@dataclass(frozen=True)
class SourceSpec:
    filename: str
    evidence_key: str
    campus_key: str
    project_key: str
    campus_name: str
    project_name: str
    country: str
    address: str
    lifecycle: str
    evidence_kind: str
    title: str
    source_url: str
    publisher: str
    source_family: str
    retrieved_at: str
    content_hash: str
    excerpt: str
    metadata: Mapping[str, Any]


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _pin(path: Path, expected: tuple[int, str]) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"missing or unsafe pinned file: {path}")
    actual = (path.stat().st_size, _sha256(path))
    if actual != expected:
        raise RuntimeError(
            f"pinned file differs: {path}: expected {expected!r}, got {actual!r}"
        )


def _normalization_guardrail() -> str:
    return (
        "No coordinate, geometry, map-derived location, satellite or aerial "
        "interpretation, computer-vision claim, role, facility type, "
        "operating model, workload, capacity, load, energy, generation, PUE, "
        "building count, or phase crosswalk is normalized."
    )


def _source_specs() -> tuple[SourceSpec, ...]:
    gulf_capture = {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": "gulf-official-filing-pdf",
        "capture_method": (
            "credential_free_curl_viewer_to_wrapper_to_pdf_chain"
        ),
        "requested_url": GULF_URL,
        "effective_document_url": GULF_PDF_URL,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": "application/pdf",
        "content_hash_scope": (
            "SHA-256 of the exact 193328-byte public PDF response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": (
            "SHA-256 of the exact 690-byte raw PDF response-header capture"
        ),
        "capture_headers_sha256": CAPTURE_FILE_PINS[
            "gulf-filing.headers"
        ][1],
        "viewer_capture_sha256": CAPTURE_FILE_PINS["gulf-viewer.body"][1],
        "wrapper_capture_sha256": CAPTURE_FILE_PINS["gulf-wrapper.body"][1],
        "filing_reference": "CS23/2026",
        "status_semantics": (
            "dated_last_observed_status_current_status_after_observation_unknown"
        ),
        "capacity_rows_created": False,
        "commercial_operation_schedule_rows_created": False,
        "normalization_guardrail": _normalization_guardrail(),
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official "
            "bytes; raw bodies, headers, telemetry, cookies, and publisher "
            "media are not redistributed."
        ),
    }
    return (
        SourceSpec(
            filename=CONVERGE_SOURCE_FILENAME,
            evidence_key=CONVERGE_EVIDENCE_KEY,
            campus_key=CONVERGE_CAMPUS_KEY,
            project_key=CONVERGE_PROJECT_KEY,
            campus_name="Converge Angeles Data Center",
            project_name="Converge Angeles Data Center Current Facility",
            country="Philippines",
            address="Angeles City, Pampanga, Philippines",
            lifecycle="operational",
            evidence_kind="company_disclosure",
            title=(
                "Converge data center ready to support government data "
                "residency under President Marcos' EO 119"
            ),
            source_url=CONVERGE_URL,
            publisher="Converge ICT Solutions Inc.",
            source_family="converge_corporate_newsroom",
            retrieved_at=CONVERGE_RETRIEVED_AT,
            content_hash=CAPTURE_FILE_PINS["converge.body"][1],
            excerpt=(
                "Converge reports that the President inspected its Angeles "
                "Data Center and describes the facility as serving as a "
                "strategic hub on July 24, 2026."
            ),
            metadata={
                "capture_artifact_id": ARTIFACT_ID,
                "capture_request_id": "converge-angeles-newsroom",
                "capture_method": (
                    "credential_free_curl_location_compressed"
                ),
                "requested_url": CONVERGE_URL,
                "effective_url": CONVERGE_URL,
                "request_credentials_supplied": False,
                "http_status": 200,
                "content_type": "text/html; charset=utf-8",
                "content_hash_scope": (
                    "SHA-256 of the exact 82928-byte content-decoded public "
                    "response body"
                ),
                "content_hash_verification": "fetched_bytes_sha256",
                "capture_headers_scope": (
                    "SHA-256 of the exact 958-byte raw HTTP response-header "
                    "capture"
                ),
                "capture_headers_sha256": CAPTURE_FILE_PINS[
                    "converge.headers"
                ][1],
                "page_date": "Friday, July 24th 2026",
                "reported_observation": (
                    "President Ferdinand R. Marcos Jr. inspected the Angeles "
                    "Data Center on Friday, July 24."
                ),
                "reported_status_wording": (
                    "the Angeles Data Center serving as a strategic hub"
                ),
                "phase_assignment": None,
                "status_semantics": (
                    "dated_last_observed_status_current_status_after_"
                    "observation_unknown"
                ),
                "normalization_guardrail": _normalization_guardrail(),
                "rights_scope": (
                    "Compact factual extraction from all-rights-reserved "
                    "official bytes; raw bodies, headers, publisher media, "
                    "and embedded scripts are not redistributed."
                ),
            },
        ),
        SourceSpec(
            filename=GSA02_SOURCE_FILENAME,
            evidence_key=GSA02_EVIDENCE_KEY,
            campus_key=GSA02_CAMPUS_KEY,
            project_key=GSA02_PROJECT_KEY,
            campus_name="GULF GSA02 Chonburi EEC Data Center",
            project_name="GULF GSA02 Chonburi EEC Current Build",
            country="Thailand",
            address=(
                "Eastern Economic Corridor, Chonburi Province, Thailand"
            ),
            lifecycle="under_construction",
            evidence_kind="company_disclosure",
            title=(
                "Establishment of Gulf Edge Data Center 03 Company Limited "
                "and Gulf Edge Data Center 04 Company Limited"
            ),
            source_url=GULF_URL,
            publisher="Gulf Development Public Company Limited",
            source_family="gulf_investor_regulatory_disclosures",
            retrieved_at=GULF_PDF_RETRIEVED_AT,
            content_hash=CAPTURE_FILE_PINS["gulf-filing.body"][1],
            excerpt=(
                "GULF's July 24, 2026 issuer filing states that GSA02 in the "
                "Eastern Economic Corridor in Chonburi Province is currently "
                "under construction."
            ),
            metadata={
                **gulf_capture,
                "reported_project_code": "GSA02",
                "reported_locality": (
                    "Eastern Economic Corridor (EEC), Chonburi Province"
                ),
                "reported_status_wording": "currently under construction",
                "other_filing_projects_normalized_in_this_source": False,
            },
        ),
        SourceSpec(
            filename=GEDC01_SOURCE_FILENAME,
            evidence_key=GEDC01_EVIDENCE_KEY,
            campus_key=GEDC01_CAMPUS_KEY,
            project_key=GEDC01_PROJECT_KEY,
            campus_name="GULF GEDC01 Rayong EEC Data Center",
            project_name="GULF GEDC01 Rayong EEC Current Build",
            country="Thailand",
            address=(
                "Eastern Economic Corridor, Rayong Province, Thailand"
            ),
            lifecycle="under_construction",
            evidence_kind="company_disclosure",
            title=(
                "Establishment of Gulf Edge Data Center 03 Company Limited "
                "and Gulf Edge Data Center 04 Company Limited"
            ),
            source_url=GULF_URL,
            publisher="Gulf Development Public Company Limited",
            source_family="gulf_investor_regulatory_disclosures",
            retrieved_at=GULF_PDF_RETRIEVED_AT,
            content_hash=CAPTURE_FILE_PINS["gulf-filing.body"][1],
            excerpt=(
                "GULF's July 24, 2026 issuer filing states that GEDC01 in the "
                "Eastern Economic Corridor in Rayong Province is currently "
                "under construction."
            ),
            metadata={
                **gulf_capture,
                "reported_project_code": "GEDC01",
                "reported_locality": (
                    "Eastern Economic Corridor (EEC), Rayong Province"
                ),
                "reported_status_wording": "currently under construction",
                "other_filing_projects_normalized_in_this_source": False,
            },
        ),
    )


def _evidence(spec: SourceSpec) -> dict[str, Any]:
    return {
        "key": spec.evidence_key,
        "kind": spec.evidence_kind,
        "title": spec.title,
        "source_url": spec.source_url,
        "publisher": spec.publisher,
        "source_family": spec.source_family,
        "published_at": "2026-07-24",
        "retrieved_at": spec.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": spec.publisher,
        "excerpt": spec.excerpt,
        "content_hash": spec.content_hash,
        "metadata": dict(spec.metadata),
    }


def _entity(spec: SourceSpec, *, project: bool) -> dict[str, Any]:
    return {
        "stable_key": spec.project_key if project else spec.campus_key,
        "name": spec.project_name if project else spec.campus_name,
        "country": spec.country,
        "address": spec.address,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": spec.evidence_key,
        "as_of_date": "2026-07-24",
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _source_document(spec: SourceSpec) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": [_evidence(spec)],
        "campus": _entity(spec, project=False),
        "project": _entity(spec, project=True),
        "lifecycle": [
            {
                "entity": "project",
                "value": spec.lifecycle,
                "evidence_key": spec.evidence_key,
                "as_of_date": "2026-07-24",
                "method": "authoritative_physical_status_update",
                "confidence": 0.99,
            }
        ],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {spec.filename: _source_document(spec) for spec in _source_specs()}


def _validate_capture_directory(directory: Path = CAPTURE_ORIGIN) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("private capture directory is unsafe")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise RuntimeError("private capture directory is not frozen")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("private capture inventory differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(entries[name], pin)
        if stat.S_IMODE(entries[name].stat().st_mode) != 0o444:
            raise RuntimeError(f"private capture is not frozen: {name}")
    if sum(pin[0] for pin in CAPTURE_FILE_PINS.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("private capture byte total differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("private capture tree differs")


def _v97_witness() -> dict[str, Any]:
    _pin(V97_DEFINITION, V97_DEFINITION_PIN)
    _pin(V97_MANIFEST, V97_MANIFEST_PIN)
    _pin(V97_ENTITIES, V97_ENTITIES_PIN)
    _pin(V97_EVIDENCE, V97_EVIDENCE_PIN)
    for path, pin in (
        (DAYONE_SOURCE, DAYONE_SOURCE_PIN),
        (DIGITAL_EDGE_SOURCE, DIGITAL_EDGE_SOURCE_PIN),
    ):
        _pin(path, pin)
    if tree_digest(V97_RELEASE) != V97_RELEASE_TREE_SHA256:
        raise RuntimeError("v97 release tree differs")

    definition = json.loads(V97_DEFINITION.read_text(encoding="utf-8"))
    manifest = json.loads(V97_MANIFEST.read_text(encoding="utf-8"))
    source_inputs = json.loads(V97_SOURCE_INPUTS.read_text(encoding="utf-8"))
    with V97_ENTITIES.open(encoding="utf-8", newline="") as handle:
        entity_rows = list(csv.DictReader(handle))
    with V97_EVIDENCE.open(encoding="utf-8", newline="") as handle:
        evidence_rows = list(csv.DictReader(handle))
    if (
        definition["release_id"] != "2026-07-22-open-seed-v97"
        or manifest["recorded_at"] != "2026-07-22T06:06:40Z"
        or len(definition["curated_inputs"]) != V97_CURATED_INPUT_COUNT
        or len(entity_rows) != V97_ENTITY_COUNT
        or len(evidence_rows) != V97_EVIDENCE_COUNT
    ):
        raise RuntimeError("v97 cardinality witness differs")

    selected = {
        row["path"]: row["sha256"] for row in definition["curated_inputs"]
    }
    for path, pin in NEARBY_SOURCE_PINS.items():
        if selected.get(path) != pin[1]:
            raise RuntimeError(f"v97 nearby-source selection differs: {path}")

    by_stable = {row["stable_key"]: row for row in entity_rows}
    planned_keys = sorted(
        {
            CONVERGE_CAMPUS_KEY,
            CONVERGE_PROJECT_KEY,
            GSA02_CAMPUS_KEY,
            GSA02_PROJECT_KEY,
            GEDC01_CAMPUS_KEY,
            GEDC01_PROJECT_KEY,
        }
    )
    planned_collisions = sorted(set(planned_keys) & set(by_stable))
    if planned_collisions:
        raise RuntimeError("planned stable key collides with v97")

    source_urls = {row["source_url"] for row in evidence_rows}
    url_collisions = sorted({CONVERGE_URL, GULF_URL} & source_urls)
    if url_collisions:
        raise RuntimeError("official discovery URL already exists in v97")

    base_evidence_keys = {
        row.get("provenance", {}).get("curated_record_key")
        for row in source_inputs.get("sources", [])
        if isinstance(row, dict)
    }
    evidence_keys = {
        CONVERGE_EVIDENCE_KEY,
        GSA02_EVIDENCE_KEY,
        GEDC01_EVIDENCE_KEY,
    }
    evidence_collisions = sorted(evidence_keys & base_evidence_keys)
    if evidence_collisions:
        raise RuntimeError("planned evidence key collides with v97")

    expected_nearby = {
        DAYONE_CAMPUS_KEY: (
            "DayOne Chonburi Tech Park Campus",
            "Amata City, Chonburi, Thailand",
        ),
        DAYONE_PROJECT_KEY: (
            "DayOne Chonburi CTP1 Current Development",
            "Amata City, Chonburi, Thailand",
        ),
        DIGITAL_EDGE_CAMPUS_KEY: (
            "Digital Edge B.Grimm Chonburi EEC Data Center Campus",
            "Chonburi, Eastern Economic Corridor, Thailand",
        ),
        DIGITAL_EDGE_PROJECT_KEY: (
            "Digital Edge B.Grimm Chonburi EEC Current Data Center Development",
            "Chonburi, Eastern Economic Corridor, Thailand",
        ),
    }
    nearby_rows = []
    for key, (name, address) in expected_nearby.items():
        row = by_stable.get(key)
        if row is None or row["name"] != name or row["address"] != address:
            raise RuntimeError(f"v97 nearby identity witness differs: {key}")
        nearby_rows.append(
            {
                "stable_key": key,
                "name": name,
                "address": address,
                "merge_decision": (
                    "reject_merge_different_named_operator_project"
                ),
            }
        )

    converge_semantic_matches = [
        row["stable_key"]
        for row in entity_rows
        if (
            "converge" in f"{row['name']} {row['address']}".lower()
            or "pampanga" in f"{row['name']} {row['address']}".lower()
            or "angeles data center" in row["name"].lower()
        )
    ]
    gulf_code_matches = [
        row["stable_key"]
        for row in entity_rows
        if "gsa02" in row["name"].lower()
        or "gedc01" in row["name"].lower()
    ]
    rayong_rows = [
        row["stable_key"]
        for row in entity_rows
        if row["country"] == "Thailand"
        and "rayong" in row["address"].lower()
    ]
    if converge_semantic_matches or gulf_code_matches or rayong_rows:
        raise RuntimeError("v97 semantic no-match witness differs")

    return {
        "release_id": definition["release_id"],
        "recorded_at": manifest["recorded_at"],
        "curated_input_count": len(definition["curated_inputs"]),
        "entity_count": len(entity_rows),
        "evidence_count": len(evidence_rows),
        "release_tree_sha256": V97_RELEASE_TREE_SHA256,
        "planned_stable_key_collisions": planned_collisions,
        "planned_new_stable_keys": planned_keys,
        "planned_evidence_key_collisions": evidence_collisions,
        "planned_source_url_collisions": url_collisions,
        "converge_semantic_matches": converge_semantic_matches,
        "gulf_project_code_matches": gulf_code_matches,
        "rayong_thailand_rows": rayong_rows,
        "chonburi_semantic_nearby_rejected": sorted(
            nearby_rows, key=lambda row: row["stable_key"]
        ),
    }


def _discovery_ledger(recorded_at: str) -> dict[str, Any]:
    candidates = [
        {
            "candidate_id": "converge-angeles-data-center",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "Converge ICT Solutions Inc.",
            "source_urls": [CONVERGE_URL],
            "factual_extract": (
                "The President inspected the Angeles Data Center; Converge "
                "describes it as serving as a strategic hub."
            ),
            "v97_match": "no_stable_key_name_address_url_or_semantic_match",
            "decision": "governed_prepublication_operational_observation",
            "why": "Explicit present-tense physical facility use.",
            "source_paths": [
                f"prospective-sources/{CONVERGE_SOURCE_FILENAME}"
            ],
        },
        {
            "candidate_id": "gulf-gsa02-chonburi",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "Gulf Development Public Company Limited",
            "source_urls": [GULF_URL],
            "factual_extract": (
                "The issuer filing says GSA02 in Chonburi's EEC is currently "
                "under construction."
            ),
            "v97_match": (
                "no_exact_match_chonburi_rows_are_different_named_projects"
            ),
            "decision": "governed_prepublication_under_construction",
            "why": "Explicit current physical-construction wording.",
            "source_paths": [
                f"prospective-sources/{GSA02_SOURCE_FILENAME}"
            ],
        },
        {
            "candidate_id": "gulf-gedc01-rayong",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "Gulf Development Public Company Limited",
            "source_urls": [GULF_URL],
            "factual_extract": (
                "The issuer filing says GEDC01 in Rayong's EEC is currently "
                "under construction."
            ),
            "v97_match": "no_stable_key_name_address_url_or_semantic_match",
            "decision": "governed_prepublication_under_construction",
            "why": "Explicit current physical-construction wording.",
            "source_paths": [
                f"prospective-sources/{GEDC01_SOURCE_FILENAME}"
            ],
        },
        {
            "candidate_id": "gulf-gsa01-samut-prakan",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "Gulf Development Public Company Limited",
            "source_urls": [GULF_URL],
            "factual_extract": (
                "The filing restates that GSA01 has been in commercial "
                "operation since the second quarter of 2025."
            ),
            "v97_match": "no_exact_match_found",
            "decision": "review_only_historical_operation_context",
            "why": (
                "Fresh filing, but a historical operational restatement; "
                "kept outside this bounded physical-update tranche."
            ),
            "source_paths": [],
        },
        {
            "candidate_id": "gulf-gedc03-gedc04",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "Gulf Development Public Company Limited",
            "source_urls": [GULF_URL],
            "factual_extract": (
                "GEDC03 and GEDC04 were incorporated to prepare for future "
                "development and operation."
            ),
            "v97_match": "no_exact_match_found",
            "decision": "review_only_incorporation_and_future_preparation",
            "why": "No site or physical construction is reported.",
            "source_paths": [],
        },
        {
            "candidate_id": "humboldt-tennessee-unnamed-data-center",
            "region": "North America",
            "published_at": "2026-07-23",
            "publisher": "Humboldt Chamber of Commerce and local officials",
            "source_urls": [
                (
                    "https://humboldtchamber.com/"
                    "local-officials-release-details-on-humboldt-data-center/"
                )
            ],
            "factual_extract": (
                "Local officials report an unnamed data center currently "
                "under construction near the Gibson County Industrial Park."
            ),
            "v97_match": "no_v97_match_private_same_day_candidate_exists",
            "decision": (
                "already_governed_in_separate_same_day_prepublication_"
                "candidate_do_not_duplicate"
            ),
            "why": "A separate retained candidate already owns this identity.",
            "source_paths": [],
        },
        {
            "candidate_id": "hcltech-bhubaneswar-ai-data-center",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "HCLTech",
            "source_urls": [
                (
                    "https://www.hcltech.com/press-releases/"
                    "hcltech-announces-ai-data-center-bhubaneswar-partnership-"
                    "sarvam-and-government"
                )
            ],
            "factual_extract": (
                "HCLTech says it plans to set up a data center under an MoU."
            ),
            "v97_match": "no_exact_match_found",
            "decision": "review_only_proposal_and_mou",
            "why": "No component-specific physical construction evidence.",
            "source_paths": [],
        },
        {
            "candidate_id": "polar-dra02-drangedal",
            "region": "Europe",
            "published_at": "2026-07-23",
            "publisher": "Polar Data Centers",
            "source_urls": [
                (
                    "https://www.polardc.com/post/"
                    "polar-announces-dra02-expansion-at-flagship-ai-ready-data-"
                    "center-campus-in-norway"
                )
            ],
            "factual_extract": (
                "Polar announces DRA02 as designed and engineered and says "
                "what the campus will provide once complete."
            ),
            "v97_match": "no_exact_dra02_match_found",
            "decision": "review_only_announced_future_facility",
            "why": (
                "The release does not say construction has started or is "
                "currently underway."
            ),
            "source_paths": [],
        },
        {
            "candidate_id": "datagrid-north-makarewa-southland",
            "region": "Asia-Pacific",
            "published_at": "2026-07-23",
            "publisher": "Mercury NZ Limited via NZX",
            "source_urls": [
                "https://new.nzx.com/announcements/476540",
            ],
            "factual_extract": (
                "Mercury reports that final investment decision is expected "
                "later in 2026 and funding lets Datagrid begin horizontal "
                "construction works."
            ),
            "v97_match": "no_exact_match_found",
            "decision": "review_only_financing_and_future_start_language",
            "why": "No completed or ongoing physical work is observed.",
            "source_paths": [],
        },
        {
            "candidate_id": "anonymous-klang-valley-data-center-grid-works",
            "region": "Asia-Pacific",
            "published_at": "2026-07-23",
            "publisher": "Kerjaya Prospek Group Berhad via Bursa Malaysia",
            "source_urls": [
                (
                    "https://www.bursamalaysia.com/market_information/"
                    "announcements/company_announcement/announcement_details"
                    "?ann_id=3687711"
                )
            ],
            "factual_extract": (
                "A subcontract covers works for a proposed 275 kV consumer "
                "landing station serving an unnamed Klang Valley data center."
            ),
            "v97_match": "unresolvable_anonymous_project",
            "decision": "review_only_power_infrastructure_and_unknown_identity",
            "why": (
                "The physical scope is power infrastructure; the data center "
                "itself is unnamed and only proposed."
            ),
            "source_paths": [],
        },
        {
            "candidate_id": "blackpool-silicon-sands-first-data-center",
            "region": "Europe",
            "published_at": "2026-07-24",
            "publisher": "Blackpool Council",
            "source_urls": [
                (
                    "https://www.blackpool.gov.uk/news/"
                    "plans-for-firstenergy-efficientdata-centre-as-part-"
                    "ofsiliconsandsmoving-forward.aspx?date=24-07-2026"
                )
            ],
            "factual_extract": (
                "Procurement is being finalized; intended award remains "
                "subject to standstill and final governance approval."
            ),
            "v97_match": "no_exact_match_found",
            "decision": "review_only_procurement_and_approval",
            "why": (
                "The only reported construction underway is a substation, "
                "not the data center."
            ),
            "source_paths": [],
        },
        {
            "candidate_id": "aws-bharat-future-city",
            "region": "Asia-Pacific",
            "published_at": "2026-07-24",
            "publisher": "Amazon",
            "source_urls": [
                "https://www.aboutamazon.in/news/aws/aws-data-centre-hyderabad"
            ],
            "factual_extract": (
                "Amazon says AWS broke ground on a new data center in "
                "Hyderabad at Bharat Future City."
            ),
            "v97_match": (
                "exact_semantic_project_match_curated_aws_bharat_future_city_"
                "initial_data_center_project"
            ),
            "decision": "exact_v97_match_no_new_entity",
            "why": (
                "v97 already records the July 15 government groundbreaking "
                "for the same named project."
            ),
            "source_paths": [],
        },
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-date-bounded-official-discovery-ledger-v1",
        "research_window": {
            "published_on_or_after": "2026-07-23",
            "published_on_or_before": "2026-07-24",
        },
        "recorded_at": recorded_at,
        "candidate_count": len(candidates),
        "governed_source_candidate_count": 3,
        "review_only_count": 7,
        "already_governed_count": 1,
        "exact_v97_match_count": 1,
        "published": False,
        "candidates": candidates,
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    rows = [
        (
            "converge-angeles-newsroom",
            CONVERGE_URL,
            CONVERGE_URL,
            CONVERGE_RETRIEVED_AT,
            "text/html; charset=utf-8",
            "converge",
            "normalized_operational_observation",
        ),
        (
            "gulf-official-viewer",
            GULF_URL,
            GULF_URL,
            GULF_VIEWER_RETRIEVED_AT,
            "text/html; charset=UTF-8",
            "gulf-viewer",
            "official_viewer_and_canonical_url_witness",
        ),
        (
            "gulf-document-wrapper",
            GULF_WRAPPER_URL,
            GULF_WRAPPER_URL,
            GULF_WRAPPER_RETRIEVED_AT,
            "text/html; charset=UTF-8",
            "gulf-wrapper",
            "document_delivery_chain_witness",
        ),
        (
            "gulf-official-filing-pdf",
            GULF_PDF_URL,
            GULF_PDF_URL,
            GULF_PDF_RETRIEVED_AT,
            "application/pdf",
            "gulf-filing",
            "normalized_gsa02_gedc01_and_review_context",
        ),
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v4",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 4,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "private_capture_directory": str(CAPTURE_ORIGIN),
        "private_capture_directory_frozen": True,
        "controlled_captures": [
            {
                "capture_id": capture_id,
                "url": url,
                "effective_url": effective_url,
                "retrieved_at": retrieved_at,
                "http_status": 200,
                "content_type": content_type,
                "claim_use": claim_use,
                "body": {
                    "path": f"{stem}.body",
                    "bytes": CAPTURE_FILE_PINS[f"{stem}.body"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{stem}.body"][1],
                    "retained_in_artifact": False,
                },
                "headers": {
                    "path": f"{stem}.headers",
                    "bytes": CAPTURE_FILE_PINS[f"{stem}.headers"][0],
                    "sha256": CAPTURE_FILE_PINS[f"{stem}.headers"][1],
                    "retained_in_artifact": False,
                },
            }
            for (
                capture_id,
                url,
                effective_url,
                retrieved_at,
                content_type,
                stem,
                claim_use,
            ) in rows
        ],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _write_sources(
    directory: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        path = directory / name
        path.write_bytes(_canonical(documents[name]))
        path.chmod(0o600)


def _table_counts(connection: Any) -> dict[str, int]:
    tables = (
        "entities",
        "entity_snapshots",
        "evidence",
        "lifecycle_observations",
        "operating_model_observations",
        "workload_observations",
        "capacity_estimates",
    )
    return {
        table: connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in tables
    }


def _offline_import(
    paths: Mapping[str, Path],
    recorded_at: str,
) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="apac-official-status-prepublication-import-",
        dir="/private/tmp",
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(
                    connection,
                    paths[name],
                    recorded_at=recorded_at,
                )
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(
                f"offline database validation failed: {errors!r}"
            )
        counts = _table_counts(connection)
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
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _compatibility_import(
    paths: Mapping[str, Path],
    recorded_at: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix="apac-official-status-v97-compatibility-",
        dir="/private/tmp",
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        adapter.import_file(
            connection,
            DAYONE_SOURCE,
            recorded_at=DAYONE_SOURCE_RETRIEVED_AT,
        )
        adapter.import_file(
            connection,
            DIGITAL_EDGE_SOURCE,
            recorded_at=DIGITAL_EDGE_SOURCE_RETRIEVED_AT,
        )
        for name in SOURCE_FILENAMES:
            adapter.import_file(
                connection,
                paths[name],
                recorded_at=recorded_at,
            )
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(
                f"compatibility database validation failed: {errors!r}"
            )
        counts = _table_counts(connection)
        expected = {
            "entities": 10,
            "entity_snapshots": 10,
            "evidence": 6,
            "lifecycle_observations": 5,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(
                f"compatibility import counts differ: {counts!r}"
            )
        planned = {
            row[0]
            for row in connection.execute(
                "SELECT stable_key FROM entities WHERE stable_key IN "
                "(?, ?, ?, ?, ?, ?)",
                (
                    CONVERGE_CAMPUS_KEY,
                    CONVERGE_PROJECT_KEY,
                    GSA02_CAMPUS_KEY,
                    GSA02_PROJECT_KEY,
                    GEDC01_CAMPUS_KEY,
                    GEDC01_PROJECT_KEY,
                ),
            )
        }
        nearby = {
            row[0]
            for row in connection.execute(
                "SELECT stable_key FROM entities WHERE stable_key IN "
                "(?, ?, ?, ?)",
                (
                    DAYONE_CAMPUS_KEY,
                    DAYONE_PROJECT_KEY,
                    DIGITAL_EDGE_CAMPUS_KEY,
                    DIGITAL_EDGE_PROJECT_KEY,
                ),
            )
        }
        if len(planned) != 6 or len(nearby) != 4:
            raise RuntimeError("compatibility identity boundary differs")
        return {
            "counts": counts,
            "planned_entity_rows": len(planned),
            "nearby_preserved_entity_rows": len(nearby),
            "merged_entity_rows": 0,
        }


def _validate_sources(
    paths: Mapping[str, Path],
    recorded_at: str,
) -> tuple[dict[str, int], dict[str, Any]]:
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("staged source inventory differs")
    documents = expected_source_documents()
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or unsafe staged source: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"staged source mode differs: {name}")
        if path.read_bytes() != _canonical(documents[name]):
            raise RuntimeError(f"staged source differs: {name}")
    first = _offline_import(paths, recorded_at)
    second = _offline_import(paths, recorded_at)
    if first != second:
        raise RuntimeError("offline import replay differs")
    return first, _compatibility_import(paths, recorded_at)


def _artifact_documents(
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    witness = _v97_witness()
    source_records = []
    for spec in _source_specs():
        payload = _canonical(documents[spec.filename])
        source_records.append(
            {
                "path": f"prospective-sources/{spec.filename}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "campus_stable_key": spec.campus_key,
                "project_stable_key": spec.project_key,
                "evidence_records": 1,
                "lifecycle_observations": 1,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 0,
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": "prepublication_candidate_not_published",
            }
        )
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v4",
        "research_date": "2026-07-24",
        "recorded_at": recorded_at,
        "published": False,
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 12,
            "governed_source_candidates": 3,
            "review_only_candidates": 7,
            "already_governed_candidates": 1,
            "exact_v97_match_candidates": 1,
            "source_records": 3,
            "distinct_entity_snapshots": 6,
            "new_entities_against_v97": 6,
            "unique_evidence_records": 3,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v97_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-22-v97.json",
                "bytes": V97_DEFINITION_PIN[0],
                "sha256": V97_DEFINITION_PIN[1],
            },
            "manifest": {
                "path": "releases/2026-07-22-open-seed-v97/manifest.json",
                "bytes": V97_MANIFEST_PIN[0],
                "sha256": V97_MANIFEST_PIN[1],
            },
            "entities": {
                "path": "releases/2026-07-22-open-seed-v97/entities.csv",
                "bytes": V97_ENTITIES_PIN[0],
                "sha256": V97_ENTITIES_PIN[1],
            },
            "evidence": {
                "path": "releases/2026-07-22-open-seed-v97/evidence.csv",
                "bytes": V97_EVIDENCE_PIN[0],
                "sha256": V97_EVIDENCE_PIN[1],
            },
            **witness,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v97_mutated": False,
            "release_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "construction_master_integration": "none",
            "map_integration": "none",
            "ledger_integration": "none",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-and-disposition-v3",
        "recorded_at": recorded_at,
        "publishers": [
            "Converge ICT Solutions Inc.",
            "Gulf Development Public Company Limited",
        ],
        "source_license": "all-rights-reserved",
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "private_capture_directory": str(CAPTURE_ORIGIN),
        "private_capture_directory_frozen": True,
        "private_capture_file_count": CAPTURE_FILE_COUNT,
        "private_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "private_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "publication_performed": False,
    }
    readme = f"""# APAC official-status discovery — prepublication only

This private candidate is the result of a date-bounded official-source sweep
for releases published on July 23–24, 2026. Three sparse observations are
staged: Converge Angeles Data Center operational on July 24, and GULF GSA02
and GEDC01 currently under construction on July 24.

The twelve-row discovery ledger also preserves every strong no-action
decision. Permits, MoUs, financing, procurement, incorporation, future-start
language, and power-infrastructure work are not treated as data-center
physical construction. AWS Bharat Future City is an exact semantic v97 match,
and Humboldt is governed by a separate same-day candidate.

Each status is a dated last-observed fact; status after the observation is
unknown. No coordinate, geometry, role, type, operating model, workload,
capacity, load, energy, generation, PUE, satellite, aerial, map-derived, or
computer-vision claim is added. Raw all-rights-reserved captures are
represented only by hashes and compact factual extracts.

Status: `PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED` as of {recorded_at}.
"""
    return {
        "README.md": readme.encode(),
        "discovery-ledger.json": _canonical(_discovery_ledger(recorded_at)),
        "retrieval-inventory.json": _canonical(
            _retrieval_inventory(recorded_at)
        ),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _write_artifact(
    directory: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        path = directory / name
        path.write_bytes(payloads[name])
        path.chmod(0o600)
    rows = [
        {
            "path": name,
            "bytes": (directory / name).stat().st_size,
            "sha256": _sha256(directory / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-prepublication-manifest-v1",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _sha256_bytes(_canonical(rows)),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 12,
        "curated_source_candidates": 3,
        "review_only_candidates": 7,
        "already_governed_candidates": 1,
        "exact_v97_match_candidates": 1,
        "raw_capture_redistributed": False,
        "published": False,
        "publisher_function_present": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "ledger_integration": "none",
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    sidecar = directory / "manifest.sha256"
    sidecar.write_text(
        f"{_sha256(manifest_path)}  manifest.json\n",
        encoding="utf-8",
    )
    sidecar.chmod(0o600)


def _assert_no_publication() -> None:
    paths = (
        PROSPECTIVE_ARTIFACT,
        *(SOURCES_ROOT / name for name in SOURCE_FILENAMES),
    )
    collisions = [
        str(path) for path in paths if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(
            f"prospective final-path collision: {collisions!r}"
        )


def validate_candidate(
    artifact_stage: Path,
    source_stage: Path,
    recorded_at: str,
) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    witness = _v97_witness()
    if (
        witness["planned_stable_key_collisions"]
        or witness["planned_evidence_key_collisions"]
        or witness["planned_source_url_collisions"]
    ):
        raise RuntimeError("expected v97 no-collision boundary differs")
    for stage_name, stage in (
        ("artifact", artifact_stage),
        ("source", source_stage),
    ):
        if stage.is_symlink() or not stage.is_dir():
            raise RuntimeError(f"{stage_name} stage is missing or unsafe")
        if stat.S_IMODE(stage.stat().st_mode) != 0o700:
            raise RuntimeError(f"{stage_name} stage mode differs")

    source_counts, compatibility = _validate_sources(
        _source_paths(source_stage),
        recorded_at,
    )
    artifact_entries = {
        path.name: path for path in artifact_stage.iterdir()
    }
    if set(artifact_entries) != CLOSED_FILES:
        raise RuntimeError("candidate artifact closed file set differs")
    for name, path in artifact_entries.items():
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"unsafe artifact member: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise RuntimeError(f"artifact member mode differs: {name}")

    manifest_path = artifact_entries["manifest.json"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest["published"] is not False
        or manifest["publisher_function_present"] is not False
        or manifest["curated_source_candidates"] != 3
        or manifest["review_only_candidates"] != 7
        or manifest["identity_integration"] != "none"
        or manifest["ledger_integration"] != "none"
    ):
        raise RuntimeError("prepublication manifest boundary differs")
    sidecar = artifact_entries["manifest.sha256"].read_text(encoding="utf-8")
    if sidecar != f"{_sha256(manifest_path)}  manifest.json\n":
        raise RuntimeError("manifest sidecar differs")
    listed = {row["path"]: row for row in manifest["files"]}
    if set(listed) != set(CONTENT_FILES):
        raise RuntimeError("manifest file inventory differs")
    for name, row in listed.items():
        path = artifact_entries[name]
        if (
            row["bytes"] != path.stat().st_size
            or row["sha256"] != _sha256(path)
        ):
            raise RuntimeError(f"manifest member pin differs: {name}")

    ledger = json.loads(
        artifact_entries["discovery-ledger.json"].read_text(encoding="utf-8")
    )
    if (
        ledger["candidate_count"] != 12
        or ledger["governed_source_candidate_count"] != 3
        or ledger["review_only_count"] != 7
        or ledger["published"] is not False
    ):
        raise RuntimeError("discovery-ledger counts differ")
    _assert_no_publication()
    return {
        **manifest,
        "offline_import_counts": source_counts,
        "v97_compatibility_import": compatibility,
        "v97_witness": witness,
    }


def prepare_candidate(*, recorded_at: str | None = None) -> PreparedCandidate:
    _assert_no_publication()
    _validate_capture_directory()
    timestamp = recorded_at or datetime.now(UTC).isoformat().replace(
        "+00:00",
        "Z",
    )
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".apac-official-status-prepublication-sources.",
            dir=SOURCES_ROOT,
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(
            prefix=".apac-official-status-prepublication-artifact.",
            dir=ARTIFACT_ROOT,
        )
    )
    source_stage.chmod(0o700)
    artifact_stage.chmod(0o700)
    try:
        documents = expected_source_documents()
        _write_sources(source_stage, documents)
        _write_artifact(artifact_stage, timestamp, documents)
        validate_candidate(artifact_stage, source_stage, timestamp)
    except BaseException:
        shutil.rmtree(source_stage, ignore_errors=True)
        shutil.rmtree(artifact_stage, ignore_errors=True)
        raise
    return PreparedCandidate(source_stage, artifact_stage, timestamp)


def candidate_result(prepared: PreparedCandidate) -> dict[str, Any]:
    manifest = validate_candidate(
        prepared.artifact_stage,
        prepared.source_stage,
        prepared.recorded_at,
    )
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "artifact_id": ARTIFACT_ID,
        "recorded_at": prepared.recorded_at,
        "source_stage": str(prepared.source_stage),
        "artifact_stage": str(prepared.artifact_stage),
        "source_stage_tree_sha256": tree_digest(prepared.source_stage),
        "artifact_stage_tree_sha256": tree_digest(prepared.artifact_stage),
        "candidate_assessments": manifest["candidate_assessments"],
        "curated_source_candidates": manifest["curated_source_candidates"],
        "review_only_candidates": manifest["review_only_candidates"],
        "already_governed_candidates": manifest[
            "already_governed_candidates"
        ],
        "exact_v97_match_candidates": manifest[
            "exact_v97_match_candidates"
        ],
        "offline_import_counts": manifest["offline_import_counts"],
        "v97_compatibility_import": manifest["v97_compatibility_import"],
        "planned_stable_key_collisions": manifest["v97_witness"][
            "planned_stable_key_collisions"
        ],
        "planned_new_stable_keys": manifest["v97_witness"][
            "planned_new_stable_keys"
        ],
        "published": False,
        "prospective_final_artifact_exists": PROSPECTIVE_ARTIFACT.exists(),
        "prospective_final_sources_exist": {
            name: (SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES
        },
        "open_seed_successor_created": False,
        "release_integration": "none",
        "federation_integration": "none",
        "identity_integration": "none",
        "construction_master_integration": "none",
        "map_integration": "none",
        "ledger_integration": "none",
    }


def main() -> int:
    prepared = prepare_candidate()
    print(json.dumps(candidate_result(prepared), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
