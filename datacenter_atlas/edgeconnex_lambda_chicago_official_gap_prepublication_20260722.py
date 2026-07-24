"""Build, but never publish, the EdgeConneX/Lambda Chicago gap candidate.

The August 2025 EdgeConneX release directly says the company is building and
developing a single-tenant 23 MW Chicago data center with Lambda.  The value is
left as untyped source metadata because the release does not call it IT load,
gross facility demand, grid capacity, generation, or current consumption.
Lambda, HPC, AI training, and AI inference are retained only where the release
ties them to the Chicago facility.

The May 2025 Construction Safety Week page is corroboration that EdgeConneX
had physical work at a Chicago data-center site.  It is not an identity bridge
to the later Lambda project and creates no lifecycle observation.  Other sites
named by that page remain review-only because later first-party pages leave
the relevant phase, identity, or current physical status unresolved.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Mapping

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"

ARTIFACT_ID = "edgeconnex-lambda-chicago-official-gap-prepublication-2026-07-22-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
SOURCE_FILENAME = (
    "curated-official-2026-07-22-edgeconnex-lambda-chicago-23mw-current-build.json"
)
PROSPECTIVE_SOURCE = SOURCES_ROOT / SOURCE_FILENAME

V95_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v95.json"
V95_ENTITIES = ROOT / "releases/2026-07-22-open-seed-v95/entities.csv"
V95_RELEASE = ROOT / "releases/2026-07-22-open-seed-v95"
V95_DEFINITION_PIN = (
    117_088,
    "e28cc9ad10229cbf718314f1bd1a4306e02faee1166dcbfbf93c01a1c82e8e15",
)
V95_ENTITIES_PIN = (
    1_058_933,
    "038bfa4ef15e4e6494ac91fa835671105d45662c0acd6b6f5c3a5e750ad3e09d",
)
V95_RELEASE_TREE_SHA256 = (
    "752593650007f602f2bd13f2bd0c3ac8702cdd74c4b6103ec2bdaa348c6ef17a"
)

CAPTURE_ORIGIN = Path("/private/tmp/dc-edgeconnex-lambda-gap-20260722.4vjUB9")
CAPTURE_BUNDLE_ID = CAPTURE_ORIGIN.name
CAPTURE_FILE_COUNT = 28
CAPTURE_TOTAL_BYTES = 6_524_603
CAPTURE_TREE_SHA256 = "2704a07148f01c3e027fe7208331cc6d6072df5a462c4d3cb6ae679ad5ba8c33"

CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "americas_index.body": (
        542_792,
        "ae299a658fa06f60e8c3b02d44bd2f62a01d1fde49db219e3b20ec920d3b3565",
    ),
    "americas_index.headers": (
        1_464,
        "01253af13c67fbfbc351d9e3706167e4c5235f4cd90d129eb0ff1f38bfabbca8",
    ),
    "amsterdam_location.body": (
        486_750,
        "c2db561469dff5a1cb6db4054d42c7884bf8d136a0845a385673ce942f3aa814",
    ),
    "amsterdam_location.headers": (
        1_346,
        "5a021c51aa099fad058c2891d09fddd67587397e211467b408043ac166ddcce1",
    ),
    "apac_index.body": (
        538_062,
        "a119ace06a9ba548874b2839302522d27774aaed5206bed6bdead6fef3a4754c",
    ),
    "apac_index.headers": (
        1_464,
        "92313ac6e6c1cce0a2b80d233af8091230effaeb865c61c966bab230976b068b",
    ),
    "atlanta_location.body": (
        186_318,
        "3fdad5d519c40174da33369e31e10eabaae8a69e8defc5df345a680caca330f7",
    ),
    "atlanta_location.headers": (
        1_346,
        "243e5e22f6aa9136a2efc19910298c57d083d244673a2c2c9608d2f545542e57",
    ),
    "chicago_lambda.body": (
        437_448,
        "c7ce604ac1f5e921ce1c290df7c3ae460575967a4be992da350eabb951db1e00",
    ),
    "chicago_lambda.headers": (
        1_348,
        "68b125f199f2f81bc1ef20fa9c5ed07b1d2b4d9b7237b79342a20b8c1b544c92",
    ),
    "chicago_location.body": (
        494_877,
        "c1b3b175900d1b14f7d807b5324c4228b53633b5192b6a4be600882e78d85d4b",
    ),
    "chicago_location.headers": (
        1_347,
        "168b8446d2b4759870b20ec0fc78b061e2f0ad201fef7147bd7421ae2403ad6e",
    ),
    "construction_safety_week.body": (
        442_320,
        "9d746b10846dd586d1521a4f086aab5618b950a5bf2913047db15c52a54c8c3b",
    ),
    "construction_safety_week.headers": (
        1_463,
        "9848537738a54d3a0c796f50b38963c919729a11cef043b8cf45b5cd99278ebd",
    ),
    "cyberjaya_current.body": (
        439_829,
        "5d6ed2a32aee2335fb400b82338a09845a491a31fba62133a2417dea76b8167e",
    ),
    "cyberjaya_current.headers": (
        1_464,
        "a419f9302bd2b6fd5a870ac919b45e32515bcc78d15678b7369507040db39e3f",
    ),
    "dublin_location.body": (
        491_377,
        "8bd9f2a7c997647dc90b094cfa2f4ecaa3a232764f899468339935a802f6f8b0",
    ),
    "dublin_location.headers": (
        1_343,
        "af62fec0534565c67ce38693c9c46f035599e31a31ce067dc35bf208252f4228",
    ),
    "emea_index.body": (
        533_660,
        "76bb244c1fc7b467bbf71e7b89f41d4820f5e101331d0188486001d603d1697c",
    ),
    "emea_index.headers": (
        1_463,
        "42625cff4d4102ee69d5cc70b6b0fd54adfe4e59cacc8791db0e06b190520c0a",
    ),
    "jakarta_location.body": (
        490_494,
        "f11b22cfb50e5785ac4ffa517c5b9a3e92cb844943eb217777502b87e4cefd44",
    ),
    "jakarta_location.headers": (
        1_345,
        "ca747cdce08b9f0d04424bbd291ac99458f052b93836f92bf18deb225949ef56",
    ),
    "kuala_milestone.body": (
        437_956,
        "45abc6fa748d37804f2f0af89c854a155c6d717a5ce874bd0d57b3affae7c757",
    ),
    "kuala_milestone.headers": (
        1_464,
        "d7881551fe491e845e4e83fc1989ad972c16a4c0933cbb1c3cb25a5c2d864f84",
    ),
    "malaysia_location.body": (
        490_762,
        "3de119a67f29a06ecaa1a01962ea417bcee11a6b1915004f5729ea75cab3388b",
    ),
    "malaysia_location.headers": (
        1_348,
        "cc156df09c5c44df5ca0430267c0566d60e9ac99f1065e9003503dd8b8469207",
    ),
    "santiago_location.body": (
        492_406,
        "02d3a2b2fcda7b94f911a3d55f42adf9d4a8b71db601fbae0887ef7c74871c6a",
    ),
    "santiago_location.headers": (
        1_347,
        "dbf5fb4e7b09347806db04ca4e66aa7106c93850b97b901b4b0a9b430428e5b4",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    requested_url: str
    retrieved_at: str
    published_at: str | None
    use: str


CAPTURES = (
    Capture(
        "chicago_lambda",
        "chicago_lambda",
        "https://www.edgeconnex.com/news/press-releases/"
        "edgeconnex-and-lambda-to-build-ai-factory-in-chicago-with-"
        "industry-leading-high-density-data-center-infrastructure/",
        "2026-07-22T05:03:41Z",
        "2025-08-21T10:20:06Z",
        "normalized_identity_physical_status_roles_and_workloads",
    ),
    Capture(
        "construction_safety_week",
        "construction_safety_week",
        "https://www.edgeconnex.com/news/edge-blog/"
        "edgeconnex-champions-safety-excellence-construction-safety-week-2025/",
        "2026-07-22T05:03:43Z",
        "2025-05-18T22:24:06Z",
        "corroborative_city_level_physical_site_evidence_only",
    ),
    Capture(
        "chicago_location",
        "chicago_location",
        "https://www.edgeconnex.com/locations/americas/chicago-il/",
        "2026-07-22T05:03:43Z",
        None,
        "review_only_no_lambda_to_chi03_identity_bridge",
    ),
    Capture(
        "cyberjaya_current",
        "cyberjaya_current",
        "https://www.edgeconnex.com/news/edge-blog/"
        "cyberjaya-scales-as-a-regional-data-center-hub/",
        "2026-07-22T05:03:44Z",
        "2025-06-25T09:55:47Z",
        "review_only_stale_physical_status_and_elapsed_forecast",
    ),
    Capture(
        "kuala_milestone",
        "kuala_milestone",
        "https://www.edgeconnex.com/news/edge-blog/"
        "building-safely-together-celebrating-a-major-milestone-at-"
        "edgeconnex-kuala-lumpur-project/",
        "2026-07-22T05:03:45Z",
        "2025-01-04T16:41:41Z",
        "review_only_old_malaysia_physical_status",
    ),
    Capture(
        "malaysia_location",
        "malaysia_location",
        "https://www.edgeconnex.com/locations/asia-pacific/kl-malaysia/",
        "2026-07-22T05:03:45Z",
        None,
        "review_only_current_design_inventory_without_physical_status",
    ),
    Capture(
        "americas_index",
        "americas_index",
        "https://www.edgeconnex.com/americas/",
        "2026-07-22T05:03:45Z",
        None,
        "review_only_market_index",
    ),
    Capture(
        "emea_index",
        "emea_index",
        "https://www.edgeconnex.com/emea/",
        "2026-07-22T05:03:45Z",
        None,
        "review_only_market_index_and_frankfurt_coming_soon",
    ),
    Capture(
        "apac_index",
        "apac_index",
        "https://www.edgeconnex.com/asia-pacific/",
        "2026-07-22T05:03:45Z",
        None,
        "review_only_market_index",
    ),
    Capture(
        "atlanta_location",
        "atlanta_location",
        "https://www.edgeconnex.com/locations/americas/atlanta-ga/",
        "2026-07-22T05:03:45Z",
        None,
        "review_only_current_operational_inventory",
    ),
    Capture(
        "santiago_location",
        "santiago_location",
        "https://www.edgeconnex.com/locations/americas/santiago/",
        "2026-07-22T05:03:46Z",
        None,
        "review_only_planned_phases_without_physical_status",
    ),
    Capture(
        "amsterdam_location",
        "amsterdam_location",
        "https://www.edgeconnex.com/locations/emea/amsterdam-nl/",
        "2026-07-22T05:03:46Z",
        None,
        "review_only_current_inventory_without_phase_status",
    ),
    Capture(
        "dublin_location",
        "dublin_location",
        "https://www.edgeconnex.com/locations/emea/dublin-ie/",
        "2026-07-22T05:03:49Z",
        None,
        "review_only_operational_landbank_and_planned_phase",
    ),
    Capture(
        "jakarta_location",
        "jakarta_location",
        "https://www.edgeconnex.com/locations/asia-pacific/jakarta/",
        "2026-07-22T05:03:49Z",
        None,
        "review_only_operational_site_and_landbank",
    ),
)

CAMPUS_KEY = "curated:edgeconnex-lambda-chicago-23mw-site"
PROJECT_KEY = f"{CAMPUS_KEY}:2025-2026-single-tenant-build"
STATUS_EVIDENCE_KEY = "edgeconnex-lambda-chicago-build-2025-08-21"
SAFETY_EVIDENCE_KEY = "edgeconnex-construction-safety-week-2025-05-18"
LOCATION_EVIDENCE_KEY = "edgeconnex-chicago-location-page-captured-2026-07-22"

CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _pin(path: Path, expected: tuple[int, str]) -> None:
    observed = (path.stat().st_size, _sha256(path))
    if observed != expected:
        raise RuntimeError(
            f"frozen dependency differs: {path.name}: {observed!r} != {expected!r}"
        )


def _capture(capture_id: str) -> Capture:
    return next(row for row in CAPTURES if row.capture_id == capture_id)


def _capture_metadata(capture_id: str) -> dict[str, Any]:
    capture = _capture(capture_id)
    body = CAPTURE_FILE_PINS[f"{capture.stem}.body"]
    headers = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
    return {
        "requested_url": capture.requested_url,
        "effective_url": capture.requested_url,
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "content_hash_scope": (
            f"SHA-256 of the exact {body[0]}-byte content-decoded public "
            "EdgeConneX HTML response body captured with curl --compressed"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "response_body_bytes": body[0],
        "response_body_sha256": body[1],
        "response_headers_bytes": headers[0],
        "response_headers_sha256": headers[1],
        "retrieved_at_semantics": (
            "Exact whole-second UTC Date from the captured HTTP response; "
            "retrieval does not refresh the page's lifecycle observation."
        ),
        "capture_use": capture.use,
        "raw_response_redistributed": False,
        "rights_scope": (
            "Compact factual extraction from a public all-rights-reserved "
            "first-party page; exact response bytes remain private."
        ),
    }


def expected_source_document() -> dict[str, Any]:
    status_metadata = _capture_metadata("chicago_lambda")
    status_metadata.update(
        {
            "physical_status_as_reported": [
                "announces it is building 30+ Megawatts of infrastructure in "
                "Chicago and Atlanta with Lambda",
                "EdgeConneX is developing a build-to-density, single-tenant "
                "23MW data center in Chicago",
            ],
            "reported_chicago_value_mw": 23,
            "reported_chicago_value_type": "untyped",
            "capacity_guardrail": (
                "23 MW is source metadata only. The page does not identify it "
                "as critical IT load, gross facility demand, grid connection, "
                "generation, installed capacity, current load, or current consumption."
            ),
            "dual_city_guardrail": (
                "The headline 30+ MW covers Chicago and Atlanta and is not "
                "allocated, normalized, or summed into the Chicago project."
            ),
            "forecast_as_reported": "Ready for Service in 2026",
            "forecast_guardrail": (
                "RFS in 2026 is a year-level forecast, not an exact target date "
                "or evidence of completion, commissioning, occupancy, or operation."
            ),
            "role_scope": (
                "The release identifies EdgeConneX as developer and Lambda as "
                "the single tenant for this Chicago build. It does not establish "
                "an owner, current operator, occupier, or legal lease terms."
            ),
            "workload_scope": (
                "The release explicitly engineers the Chicago infrastructure for "
                "HPC, AI training, and AI inferencing. These are intended design "
                "workloads, not proof of installed accelerators or live compute."
            ),
            "operating_model_guardrail": (
                "Build-to-density and single-tenant are retained as exact source "
                "metadata. No schema operating model is inferred without explicit "
                "lease, colocation, or self-build semantics."
            ),
            "cooling_energy_guardrail": (
                "Hybrid direct-to-chip and air cooling creates no PUE, WUE, annual "
                "energy, demand, efficiency, or current-consumption observation."
            ),
            "identity_scope": (
                "One city-level Chicago project is retained. The source provides no "
                "facility code, street address, parcel, building, or campus bridge."
            ),
            "currentness_scope": (
                "Under construction is a last-observed status dated 2025-08-21. "
                "The 2026 retrieval does not assert that construction is still "
                "current on the retrieval date."
            ),
            "imagery_guardrail": (
                "Publisher imagery, maps, satellite imagery, aerial imagery, and "
                "computer vision contribute no normalized fact."
            ),
        }
    )

    safety_metadata = _capture_metadata("construction_safety_week")
    safety_metadata.update(
        {
            "site_list_as_reported": [
                "Atlanta",
                "Amsterdam",
                "Chicago",
                "Cyberjaya",
                "Dublin",
                "Frankfurt",
                "Jakarta",
                "Santiago",
            ],
            "corroboration_scope": (
                "This first-party page establishes that EdgeConneX had physical "
                "construction-site activity somewhere in Chicago during Safety "
                "Week 2025. It does not name Lambda, 23 MW, CHI03, an address, or a phase."
            ),
            "identity_bridge_created": False,
            "lifecycle_observation_created": False,
            "capacity_observation_created": False,
            "location_observation_created": False,
        }
    )

    location_metadata = _capture_metadata("chicago_location")
    location_metadata.update(
        {
            "reported_codes": ["CHI01", "CHI02", "CHI03"],
            "reported_chi03_value_mw": 22.4,
            "reported_chi03_value_type": "untyped",
            "identity_guardrail": (
                "The page does not connect Lambda or the 23 MW release to CHI03. "
                "The 22.4 MW page value differs from 23 MW and has no stated type; "
                "rounding or asset identity is not inferred."
            ),
            "current_status_guardrail": (
                "The location page markets current Chicago facilities but gives no "
                "dated physical status for the Lambda build. It creates no lifecycle row."
            ),
            "coordinates_geometry_guardrail": (
                "The city page and any embedded maps create no point, parcel, "
                "footprint, building centroid, or geometry."
            ),
        }
    )

    return {
        "schema_version": "1.1",
        "evidence": [
            {
                "key": STATUS_EVIDENCE_KEY,
                "kind": "company_disclosure",
                "title": (
                    "EdgeConneX and Lambda To Build AI Factory In Chicago With "
                    "Industry-Leading High-Density Data Center Infrastructure"
                ),
                "source_url": _capture("chicago_lambda").requested_url,
                "publisher": "EdgeConneX",
                "source_family": "edgeconnex_press_releases",
                "published_at": "2025-08-21T10:20:06Z",
                "retrieved_at": "2026-07-22T05:03:41Z",
                "license": "all-rights-reserved",
                "attribution": "EdgeConneX",
                "excerpt": (
                    "EdgeConneX says it is developing a single-tenant 23 MW "
                    "Chicago data center with Lambda, engineered for HPC, AI "
                    "training, and AI inference, with RFS forecast in 2026."
                ),
                "content_hash": CAPTURE_FILE_PINS["chicago_lambda.body"][1],
                "metadata": status_metadata,
            },
            {
                "key": SAFETY_EVIDENCE_KEY,
                "kind": "company_disclosure",
                "title": (
                    "EdgeConneX Champions Safety Excellence: Construction "
                    "Safety Week 2025"
                ),
                "source_url": _capture("construction_safety_week").requested_url,
                "publisher": "EdgeConneX",
                "source_family": "edgeconnex_edge_blog",
                "published_at": "2025-05-18T22:24:06Z",
                "retrieved_at": "2026-07-22T05:03:43Z",
                "license": "all-rights-reserved",
                "attribution": "EdgeConneX",
                "excerpt": (
                    "EdgeConneX lists Chicago among its data-center construction "
                    "sites during Construction Safety Week 2025."
                ),
                "content_hash": CAPTURE_FILE_PINS["construction_safety_week.body"][1],
                "metadata": safety_metadata,
            },
            {
                "key": LOCATION_EVIDENCE_KEY,
                "kind": "company_disclosure",
                "title": "Chicago Data Centers",
                "source_url": _capture("chicago_location").requested_url,
                "publisher": "EdgeConneX",
                "source_family": "edgeconnex_location_pages",
                "published_at": None,
                "retrieved_at": "2026-07-22T05:03:43Z",
                "license": "all-rights-reserved",
                "attribution": "EdgeConneX",
                "excerpt": (
                    "The current location page lists CHI01, CHI02, and an "
                    "untyped 22.4 MW CHI03 value, but does not connect CHI03 to Lambda."
                ),
                "content_hash": CAPTURE_FILE_PINS["chicago_location.body"][1],
                "metadata": location_metadata,
            },
        ],
        "campus": {
            "stable_key": CAMPUS_KEY,
            "name": "EdgeConneX Lambda Chicago 23 MW Data Center Site",
            "country": "United States",
            "address": "Chicago, Illinois, United States",
            "roles": {
                "developer": ["EdgeConneX"],
                "tenant": ["Lambda"],
            },
            "coordinates": None,
            "geometry": None,
            "evidence_key": STATUS_EVIDENCE_KEY,
            "as_of_date": "2025-08-21",
            "method": "authoritative_locality",
            "confidence": 0.98,
        },
        "project": {
            "stable_key": PROJECT_KEY,
            "name": "EdgeConneX Lambda Chicago 2025-2026 Single-Tenant Build",
            "country": "United States",
            "address": "Chicago, Illinois, United States",
            "roles": {
                "developer": ["EdgeConneX"],
                "tenant": ["Lambda"],
            },
            "coordinates": None,
            "geometry": None,
            "evidence_key": STATUS_EVIDENCE_KEY,
            "as_of_date": "2025-08-21",
            "method": "authoritative_locality",
            "confidence": 0.98,
        },
        "lifecycle": [
            {
                "entity": "project",
                "value": "under_construction",
                "evidence_key": STATUS_EVIDENCE_KEY,
                "as_of_date": "2025-08-21",
                "method": "authoritative_physical_status_update",
                "confidence": 0.98,
            }
        ],
        "operating_models": [],
        "workloads": [
            {
                "entity": "project",
                "value": "hpc",
                "evidence_key": STATUS_EVIDENCE_KEY,
                "as_of_date": "2025-08-21",
                "method": "company_disclosure",
                "confidence": 0.99,
            },
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": STATUS_EVIDENCE_KEY,
                "as_of_date": "2025-08-21",
                "method": "company_disclosure",
                "confidence": 0.99,
            },
            {
                "entity": "project",
                "value": "ai_inference",
                "evidence_key": STATUS_EVIDENCE_KEY,
                "as_of_date": "2025-08-21",
                "method": "company_disclosure",
                "confidence": 0.99,
            },
        ],
        "capacities": [],
    }


def _validate_capture_directory(directory: Path = CAPTURE_ORIGIN) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("frozen capture bundle is missing or unsafe")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise RuntimeError("frozen capture bundle directory mode differs")
    entries = {path.name: path for path in directory.iterdir()}
    if set(entries) != set(CAPTURE_FILE_PINS):
        raise RuntimeError("frozen capture bundle closed file set differs")
    for name, expected in CAPTURE_FILE_PINS.items():
        path = entries[name]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"frozen capture member is unsafe: {name}")
        if stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise RuntimeError(f"frozen capture mode differs: {name}")
        _pin(path, expected)
    if len(entries) != CAPTURE_FILE_COUNT:
        raise RuntimeError("frozen capture file count differs")
    if sum(path.stat().st_size for path in entries.values()) != CAPTURE_TOTAL_BYTES:
        raise RuntimeError("frozen capture byte count differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("frozen capture tree differs")


def _stable_keys(document: Mapping[str, Any]) -> set[str]:
    return {
        document[kind]["stable_key"]
        for kind in ("campus", "project")
        if isinstance(document.get(kind), Mapping)
    }


def _collision_witness() -> dict[str, Any]:
    _pin(V95_DEFINITION, V95_DEFINITION_PIN)
    _pin(V95_ENTITIES, V95_ENTITIES_PIN)
    if tree_digest(V95_RELEASE) != V95_RELEASE_TREE_SHA256:
        raise RuntimeError("frozen v95 release tree differs")

    definition = json.loads(V95_DEFINITION.read_text(encoding="utf-8"))
    v95_sources = [ROOT / row["path"] for row in definition["curated_inputs"]]
    proposal = expected_source_document()
    proposal_keys = _stable_keys(proposal)
    proposal_urls = {row["source_url"] for row in proposal["evidence"]}

    v95_key_hits: list[dict[str, str]] = []
    v95_url_hits: list[dict[str, str]] = []
    selected_edgeconnex_paths: list[str] = []
    for path in v95_sources:
        document = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        if "edgeconnex" in json.dumps(document).lower():
            selected_edgeconnex_paths.append(relative)
        for key in sorted(proposal_keys & _stable_keys(document)):
            v95_key_hits.append({"path": relative, "stable_key": key})
        for evidence in document.get("evidence", []):
            if evidence.get("source_url") in proposal_urls:
                v95_url_hits.append(
                    {"path": relative, "source_url": evidence["source_url"]}
                )

    later_key_hits: list[dict[str, str]] = []
    later_url_hits: list[dict[str, str]] = []
    for path in sorted(SOURCES_ROOT.glob("curated-official-2026-07-22-*.json")):
        if path == PROSPECTIVE_SOURCE:
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        for key in sorted(proposal_keys & _stable_keys(document)):
            later_key_hits.append({"path": relative, "stable_key": key})
        for evidence in document.get("evidence", []):
            if evidence.get("source_url") in proposal_urls:
                later_url_hits.append(
                    {"path": relative, "source_url": evidence["source_url"]}
                )

    release_key_hits: list[str] = []
    release_edgeconnex_rows: list[dict[str, str]] = []
    with V95_ENTITIES.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["stable_key"] in proposal_keys:
                release_key_hits.append(row["stable_key"])
            if "edgeconnex" in row["name"].lower():
                release_edgeconnex_rows.append(
                    {
                        "stable_key": row["stable_key"],
                        "name": row["name"],
                        "country": row["country"],
                    }
                )

    if any(
        (v95_key_hits, v95_url_hits, later_key_hits, later_url_hits, release_key_hits)
    ):
        raise RuntimeError(
            "EdgeConneX/Lambda proposal collides with accepted source state"
        )

    return {
        "v95_definition": {
            "bytes": V95_DEFINITION_PIN[0],
            "sha256": V95_DEFINITION_PIN[1],
            "curated_input_count": len(v95_sources),
        },
        "v95_release": {
            "tree_sha256": V95_RELEASE_TREE_SHA256,
            "entity_count": 1_029,
            "proposal_stable_key_collisions": release_key_hits,
        },
        "proposal": {
            "stable_keys": sorted(proposal_keys),
            "source_urls": sorted(proposal_urls),
        },
        "v95_selected_edgeconnex_sources": sorted(selected_edgeconnex_paths),
        "v95_edgeconnex_release_rows": release_edgeconnex_rows,
        "v95_source_stable_key_collisions": v95_key_hits,
        "v95_source_url_collisions": v95_url_hits,
        "later_final_source_scan_rule": (
            "sources/curated-official-2026-07-22-*.json excluding the proposal"
        ),
        "later_source_stable_key_collisions": later_key_hits,
        "later_source_url_collisions": later_url_hits,
        "chi03_identity_asserted": False,
        "edged_chicago_identity_asserted": False,
        "new_entity_candidate_count": 2,
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-gap-candidate-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "first_party_only": True,
        "candidates": [
            {
                "candidate_id": "edgeconnex-lambda-chicago-23mw",
                "decision": "governed_prepublication_current_build_candidate",
                "physical_status_date": "2025-08-21",
                "physical_status_wording": ["is building", "is developing"],
                "status_is_last_observed_not_retrieval_date_current": True,
                "single_tenant_as_reported": True,
                "reported_untyped_mw": 23,
                "normalized_capacity_rows": 0,
                "normalized_workloads": ["hpc", "ai_training", "ai_inference"],
                "roles": {"developer": ["EdgeConneX"], "tenant": ["Lambda"]},
                "safety_week_corroboration_only": True,
                "chi03_identity_asserted": False,
                "published": False,
                "seeded": False,
            },
            {
                "candidate_id": "edgeconnex-cyberjaya-initial-campus",
                "decision": "review_only_stale_status_and_elapsed_forecast",
                "last_site_specific_physical_observation": "2025-06-25",
                "last_physical_detail": "first phase reported 70 percent complete",
                "elapsed_forecast": "Q1 2026 go-live",
                "retrieval_refreshes_status": False,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-downtown-kuala-lumpur",
                "decision": "review_only_old_generic_build_and_phase_unresolved",
                "last_physical_wording_date": "2025-06-25",
                "location_page_has_current_design_inventory_only": True,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-bukit-jalil",
                "decision": "review_only_old_generic_build_and_phase_unresolved",
                "last_physical_wording_date": "2025-06-25",
                "location_page_has_current_design_inventory_only": True,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-atlanta-unspecified-site",
                "decision": "review_only_identity_ambiguous_and_current_page_operational",
                "safety_week_site_date": "2025-05-18",
                "current_page_reports": "ATL01 and ATL02 with completed shells",
                "lambda_release_reports": "two air-cooled sites already operated",
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-amsterdam-unspecified-site",
                "decision": "review_only_phase_and_identity_ambiguous",
                "safety_week_site_date": "2025-05-18",
                "current_page_has_dated_physical_update": False,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-dublin-unspecified-site",
                "decision": "review_only_operational_landbank_and_planned_phase",
                "safety_week_site_date": "2025-05-18",
                "current_page_reports": (
                    "two operational data centers, land bank, and DUB03 planned"
                ),
                "current_page_has_phase_specific_physical_update": False,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-frankfurt-unspecified-site",
                "decision": "review_only_identity_ambiguous_and_coming_soon",
                "safety_week_site_date": "2025-05-18",
                "current_emea_index_status": "coming-soon",
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-jakarta-unspecified-expansion",
                "decision": "review_only_operational_site_landbank_and_phase_unresolved",
                "safety_week_site_date": "2025-05-18",
                "current_page_reports": "2 MW operational and land banked expansion",
                "current_page_has_phase_specific_physical_update": False,
                "current_construction_seed_created": False,
            },
            {
                "candidate_id": "edgeconnex-santiago-unspecified-expansion",
                "decision": "review_only_planned_phases_without_current_physical_status",
                "safety_week_site_date": "2025-05-18",
                "current_page_reports": "SCL03 and SCL04 planned",
                "current_page_has_phase_specific_physical_update": False,
                "current_construction_seed_created": False,
            },
        ],
        "totals": {
            "candidates": 10,
            "governed_prepublication_candidates": 1,
            "review_only_candidates": 9,
            "published": 0,
            "seeded": 0,
        },
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    rows = []
    for capture in CAPTURES:
        body = CAPTURE_FILE_PINS[f"{capture.stem}.body"]
        headers = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
        rows.append(
            {
                "capture_id": capture.capture_id,
                "publisher": "EdgeConneX",
                "requested_url": capture.requested_url,
                "effective_url": capture.requested_url,
                "retrieved_at": capture.retrieved_at,
                "published_at": capture.published_at,
                "use": capture.use,
                "body": {"bytes": body[0], "sha256": body[1]},
                "headers": {"bytes": headers[0], "sha256": headers[1]},
            }
        )
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-private-retrieval-inventory-v1",
        "recorded_at": recorded_at,
        "first_party_only": True,
        "capture_bundle_id": CAPTURE_BUNDLE_ID,
        "captures": rows,
        "capture_count": len(rows),
        "file_count": CAPTURE_FILE_COUNT,
        "total_bytes": CAPTURE_TOTAL_BYTES,
        "tree_sha256": CAPTURE_TREE_SHA256,
        "raw_capture_redistributed": False,
        "credentials_supplied": False,
    }


def _source_record(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = _canonical(document)
    return {
        "path": f"prospective-sources/{SOURCE_FILENAME}",
        "bytes": len(payload),
        "sha256": _sha256_bytes(payload),
        "schema_version": "1.1",
        "country": "United States",
        "campus_stable_key": CAMPUS_KEY,
        "project_stable_key": PROJECT_KEY,
        "evidence_records": len(document["evidence"]),
        "lifecycle_observations": len(document["lifecycle"]),
        "operating_model_observations": len(document["operating_models"]),
        "workload_observations": len(document["workloads"]),
        "capacity_estimates": len(document["capacities"]),
        "coordinates_present": 0,
        "geometry_present": 0,
        "published": False,
        "seeded": False,
    }


def _artifact_documents(
    recorded_at: str, document: Mapping[str, Any]
) -> dict[str, bytes]:
    witness = _collision_witness()
    assessment = _candidate_assessment(recorded_at)
    source_record = _source_record(document)
    readme = f"""# EdgeConneX/Lambda Chicago gap - prepublication only

Built at {recorded_at}; never published or integrated. One source document preserves EdgeConneX's August 21, 2025 last-observed physical status for a single-tenant 23 MW Chicago data center with Lambda. The 23 MW value remains untyped source metadata, while HPC, AI training, and AI inference are explicit intended project workloads.

The May 18, 2025 Safety Week page is Chicago city-level physical-site corroboration only. It does not bridge the Lambda project to CHI03, an address, a phase, or a particular construction site. The current Chicago page's untyped 22.4 MW CHI03 value is not treated as the same asset or rounded to 23 MW.

Cyberjaya, downtown Kuala Lumpur, Bukit Jalil, Atlanta, Amsterdam, Dublin, Frankfurt, Jakarta, and Santiago remain review-only because the available first-party record is stale, operational, phase-ambiguous, identity-ambiguous, planned, or otherwise lacks a sufficiently recent phase-specific physical update.

No normalized capacity, energy, PUE, operating model, coordinate, geometry, satellite, aerial, or computer-vision claim is emitted. This builder contains no publisher or promotion function and changes no final source, source artifact, open seed, release, map, identity, federation, construction, or coverage product.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": [source_record],
        "totals": {
            "candidate_assessments": 10,
            "source_records": 1,
            "governed_prepublication_candidates": 1,
            "review_only_candidates": 9,
            "distinct_entity_snapshots": 2,
            "new_entities_against_v95": 2,
            "evidence_records": 3,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 3,
            "capacity_estimates": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
            "computer_vision_normalized_claims": 0,
            "energy_consumption_observations": 0,
        },
        "v95_and_later_collision_witness": witness,
        "integration": {
            "published": False,
            "final_source_path_created": False,
            "final_artifact_path_created": False,
            "open_seed_successor_created": False,
            "v95_mutated": False,
            "release_integration": "none",
            "construction_integration": "none",
            "identity_integration": "none",
            "federation_integration": "none",
            "map_integration": "none",
            "coverage_integration": "none",
        },
        "prepublication_contract": {
            "version": 1,
            "publisher_function_present": False,
            "promotion_function_present": False,
            "source_stage_file_mode": "0600",
            "source_stage_directory_mode": "0700",
            "artifact_stage_file_mode": "0600",
            "artifact_stage_directory_mode": "0700",
            "raw_capture_file_mode": "0444",
            "raw_capture_directory_mode": "0555",
            "raw_capture_retained_private": True,
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "recorded_at": recorded_at,
        "source_rights": "EdgeConneX public pages treated as all-rights-reserved.",
        "artifact_is_hash_and_factual_extract_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "private_capture_bundle_id": CAPTURE_BUNDLE_ID,
        "private_capture_file_count": CAPTURE_FILE_COUNT,
        "private_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "private_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "publication_performed": False,
    }
    return {
        "README.md": readme.encode("utf-8"),
        "candidate-assessment.json": _canonical(assessment),
        "retrieval-inventory.json": _canonical(_retrieval_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _offline_import(path: Path, recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(
        prefix="edgeconnex-lambda-gap-import-", dir="/private/tmp"
    ) as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        adapter.import_file(connection, path, recorded_at=recorded_at)
        adapter.import_file(connection, path, recorded_at=recorded_at)
        errors = validate_database(connection)
        if errors:
            raise RuntimeError(f"offline database validation failed: {errors!r}")
        tables = (
            "entities",
            "entity_snapshots",
            "evidence",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
        expected = {
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 3,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 3,
            "capacity_estimates": 0,
        }
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _assert_no_publication() -> None:
    collisions = [
        path.name
        for path in (PROSPECTIVE_ARTIFACT, PROSPECTIVE_SOURCE)
        if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise RuntimeError(f"prospective final-path collision: {collisions!r}")


def _write_source(directory: Path, document: Mapping[str, Any]) -> Path:
    path = directory / SOURCE_FILENAME
    path.write_bytes(_canonical(document))
    path.chmod(0o600)
    return path


def _write_artifact(
    directory: Path, recorded_at: str, document: Mapping[str, Any]
) -> None:
    payloads = _artifact_documents(recorded_at, document)
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
        "candidate_assessments": 10,
        "curated_source_candidates": 1,
        "review_only_candidates": 9,
        "raw_capture_redistributed": False,
        "published": False,
        "publisher_function_present": False,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False,
        "release_integration": "none",
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    sidecar = directory / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o600)


def validate_candidate(artifact_stage: Path, source_stage: Path) -> dict[str, Any]:
    _assert_no_publication()
    _validate_capture_directory()
    if (
        artifact_stage.is_symlink()
        or source_stage.is_symlink()
        or not artifact_stage.is_dir()
        or not source_stage.is_dir()
    ):
        raise RuntimeError("candidate stage is missing or unsafe")
    if stat.S_IMODE(artifact_stage.stat().st_mode) != 0o700:
        raise RuntimeError("candidate artifact directory mode differs")
    if stat.S_IMODE(source_stage.stat().st_mode) != 0o700:
        raise RuntimeError("candidate source directory mode differs")

    source_entries = {path.name: path for path in source_stage.iterdir()}
    if set(source_entries) != {SOURCE_FILENAME}:
        raise RuntimeError("candidate source closed file set differs")
    source_path = source_entries[SOURCE_FILENAME]
    if source_path.is_symlink() or not source_path.is_file():
        raise RuntimeError("candidate source is missing or unsafe")
    if stat.S_IMODE(source_path.stat().st_mode) != 0o600:
        raise RuntimeError("candidate source mode differs")
    document = expected_source_document()
    if source_path.read_bytes() != _canonical(document):
        raise RuntimeError("staged source differs")
    first = _offline_import(source_path, "2026-07-22T05:10:00Z")
    second = _offline_import(source_path, "2026-07-22T05:10:00Z")
    if first != second:
        raise RuntimeError("EdgeConneX/Lambda offline replay differs")

    entries = {path.name: path for path in artifact_stage.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise RuntimeError("candidate artifact closed file set differs")
    if any(path.is_symlink() or not path.is_file() for path in entries.values()):
        raise RuntimeError("candidate artifact contains an unsafe member")
    if any(stat.S_IMODE(path.stat().st_mode) != 0o600 for path in entries.values()):
        raise RuntimeError("candidate artifact member mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or manifest.get("published") is not False
        or manifest.get("publisher_function_present") is not False
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
    ):
        raise RuntimeError("candidate manifest contract differs")
    rows = manifest.get("files")
    if not isinstance(rows, list) or [row.get("path") for row in rows] != list(
        CONTENT_FILES
    ):
        raise RuntimeError("candidate manifest file inventory differs")
    for row in rows:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise RuntimeError(f"candidate manifest pin differs: {row['path']}")
    if manifest["tree_sha256"] != _sha256_bytes(_canonical(rows)):
        raise RuntimeError("candidate manifest tree differs")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise RuntimeError("candidate manifest checksum differs")
    expected_payloads = _artifact_documents(manifest["recorded_at"], document)
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected_payloads[name]:
            raise RuntimeError(f"candidate artifact content differs: {name}")
    return manifest


@dataclass(frozen=True)
class PreparedCandidate:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def prepare_candidate(*, recorded_at: str | None = None) -> PreparedCandidate:
    """Create validated private stages; intentionally never promote them."""

    _assert_no_publication()
    _validate_capture_directory()
    _collision_witness()
    document = expected_source_document()
    instant = recorded_at or datetime.now(UTC).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    source_stage = Path(
        tempfile.mkdtemp(
            prefix=".edgeconnex-lambda-chicago-prepublication-sources.",
            dir=SOURCES_ROOT,
        )
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    try:
        _write_source(source_stage, document)
        _write_artifact(artifact_stage, instant, document)
        validate_candidate(artifact_stage, source_stage)
        return PreparedCandidate(source_stage, artifact_stage, instant)
    except BaseException:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            shutil.rmtree(artifact_stage)
        raise


def candidate_result(prepared: PreparedCandidate) -> dict[str, Any]:
    manifest = validate_candidate(prepared.artifact_stage, prepared.source_stage)
    source_path = prepared.source_stage / SOURCE_FILENAME
    return {
        "status": "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED",
        "recorded_at": prepared.recorded_at,
        "artifact_stage": str(prepared.artifact_stage),
        "artifact_manifest_sha256": _sha256(prepared.artifact_stage / "manifest.json"),
        "artifact_tree_sha256": tree_digest(prepared.artifact_stage),
        "source_stage": str(prepared.source_stage),
        "source_pin": {
            "path": str(source_path),
            "bytes": source_path.stat().st_size,
            "sha256": _sha256(source_path),
        },
        "candidate_assessments": manifest["candidate_assessments"],
        "curated_source_candidates": manifest["curated_source_candidates"],
        "review_only_candidates": manifest["review_only_candidates"],
        "raw_capture": {
            "bundle_id": CAPTURE_BUNDLE_ID,
            "files": CAPTURE_FILE_COUNT,
            "bytes": CAPTURE_TOTAL_BYTES,
            "tree_sha256": CAPTURE_TREE_SHA256,
        },
        "published": False,
        "prospective_final_artifact_exists": PROSPECTIVE_ARTIFACT.exists(),
        "prospective_final_source_exists": PROSPECTIVE_SOURCE.exists(),
    }


def main() -> int:
    prepared = prepare_candidate()
    print(json.dumps(candidate_result(prepared), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
