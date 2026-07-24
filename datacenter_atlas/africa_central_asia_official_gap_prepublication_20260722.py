"""Build, but never publish, the Africa/Central Asia official-gap review.

The bounded first-party sweep found no exact data-centre project absent from
open seed v96 with sufficiently current, project-specific evidence of physical
construction.  The closest case is IT HUB DUSHANBE: Tajikistan's official
digital-agency page records a first-stone ceremony for a mixed-use technology
complex and names a data-centre component inside one of four objects.  It does
not establish that the data-centre component itself entered physical works.

This module therefore carries that exact component as review-only, with no
lifecycle, capacity, workload, operating-model, coordinate, geometry, or energy
observation.  It creates private deterministic stages and intentionally has no
publisher or promotion function.
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

ARTIFACT_ID = "africa-central-asia-official-gap-prepublication-2026-07-22-v1"
PROSPECTIVE_ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
SOURCE_FILENAME = (
    "curated-official-2026-07-22-it-hub-dushanbe-data-center-component-review-only.json"
)
PROSPECTIVE_SOURCE = SOURCES_ROOT / SOURCE_FILENAME

V96_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-22-v96.json"
V96_RELEASE = ROOT / "releases/2026-07-22-open-seed-v96"
V96_MANIFEST = V96_RELEASE / "manifest.json"
V96_ENTITIES = V96_RELEASE / "entities.csv"
V96_EVIDENCE = V96_RELEASE / "evidence.csv"
V96_PINS: Mapping[Path, tuple[int, str]] = {
    V96_DEFINITION: (
        121_029,
        "d49c9de9aaded6af7c103375b71d07f0904fe6cc7a24785a678e82bfe5e6d6c0",
    ),
    V96_MANIFEST: (
        21_007,
        "8407f11a8e414810cd7d56ee5fd6f7e95015771c72d3106e4ab96d1ddb41422e",
    ),
    V96_ENTITIES: (
        1_071_703,
        "fd33c2df011b63f57ca1dc3388b5d0925b5cc1a43017c94e1ceb849a49c47c68",
    ),
    V96_EVIDENCE: (
        270_624,
        "81c3dd7e95fc02aa99650abb605a93752a5d0581378fe95398b6a7079e9577b9",
    ),
}
V96_RELEASE_TREE_SHA256 = (
    "8fdd260892474febf2ac3dc7a368b68ecda419d53f97357b54142b1c40bca558"
)

CAPTURE_ORIGIN = Path("/Users/kian/.Trash/dc-africa-central-asia-gap-20260722.7bBxhP")
CAPTURE_BUNDLE_ID = CAPTURE_ORIGIN.name
CAPTURE_FILE_COUNT = 30
CAPTURE_TOTAL_BYTES = 2_174_673
CAPTURE_TREE_SHA256 = "9256e86810da25c5f8f58d380d3bf8a6788f10f007bab8db57b689e7ac6c1d5e"

CAPTURE_FILE_PINS: Mapping[str, tuple[int, str]] = {
    "dushanbe_it_hub.body": (
        2_285,
        "0402ba58e5aeed85daa3f33f39c34589b2f791b7f00d51770be31f88458a3207",
    ),
    "dushanbe_it_hub.facts": (
        234,
        "8db0f0c5bc4ee3a9e0859b5ae28b7fda7b1d3b4d0ed0de6973d6a29a529b09d9",
    ),
    "dushanbe_it_hub.headers": (
        357,
        "5dfb7f3316775f6063efb8c980c6da88b89fd60ce510da6858badfd6fb90452e",
    ),
    "kasi_current_home.body": (
        46_765,
        "433b3d2ba79525124ec92456efdea21a00c98de0b7ba08f4b2fcff6246e61bd8",
    ),
    "kasi_current_home.facts": (
        184,
        "5c7811da8e1af4af116b0caf1319b5b1b5a7305f8185354683dba1cd538b224e",
    ),
    "kasi_current_home.headers": (
        807,
        "e0e8a0ddb4092000b7f48bdf53273c55112bfa9179987cdaab281133222ff01e",
    ),
    "kazakhstan_200mw_mou.body": (
        836,
        "6e9cf6528c9e3159b6c53a92ebe5d03624ae0fc00eabba3f0d54d8ebe36fbdc9",
    ),
    "kazakhstan_200mw_mou.facts": (
        225,
        "eb866de23285ad81e4dc92b86fe0e808395505e2ccfae307772af1591d9f0597",
    ),
    "kazakhstan_200mw_mou.headers": (
        704,
        "7189e413db55b4645a7e4df0f5ba6a515b0e8250366e17e15302799b26e9c576",
    ),
    "kyrgyz_investment_meeting.body": (
        1_477_437,
        "727a5871275043effa3abac7cdcfc02f503c357137f19eb18ca9b2e3214a93eb",
    ),
    "kyrgyz_investment_meeting.facts": (
        196,
        "c06d8f4e3dca252104c79889c4e4f0b093c3a6b56f5d0e309d86c0da45cebdf1",
    ),
    "kyrgyz_investment_meeting.headers": (
        4_678,
        "38a4ef6b9e4cbc323f971a78e7d339849effd07bc06f355550825f4cc13ba72a",
    ),
    "mongolia_green_dc.body": (
        115_583,
        "2cd37dc5d412fbd38ea896feaa67f5777dc51ee6de91c3a0b1b6eb175e088669",
    ),
    "mongolia_green_dc.facts": (
        203,
        "191d8abea693087b369e3b3a39548c1fde640d170682b01a70f49298182732b3",
    ),
    "mongolia_green_dc.headers": (
        1_310,
        "afbef4a250f3ec61af07990537439c77c85cd1eade2289a8beb2a164cbc1f01c",
    ),
    "paix_djibouti_current_route.body": (
        162_765,
        "26056c136ed934799ed95be8e1bddf8eeb8e1e514766fc33520a2c6e5dac2c78",
    ),
    "paix_djibouti_current_route.facts": (
        206,
        "e8ec9d8165bff6ef3397402d047b80902b51dd863f457bb654ac48a51425d4a2",
    ),
    "paix_djibouti_current_route.headers": (
        1_158,
        "06d4071738d5eb535b905de6b47f4aa4cc4c4da684fc6e6fa87174157c7c5e71",
    ),
    "turkmen_muroosystems_mou.body": (
        27_537,
        "18c7e721f27635a2845e5ebb35f37528f8a8e83e98f0ce65eb85772c49157a97",
    ),
    "turkmen_muroosystems_mou.facts": (
        214,
        "0ebe8ad9235750671d09ebb87d7fa21a91382e8537a5846d86f1a8f03caf80e5",
    ),
    "turkmen_muroosystems_mou.headers": (
        1_847,
        "8e296bab9ec6e5b3de8dc073fc9063efa14c7cfec90ecb428d9549ab05a7d3bd",
    ),
    "uzbekistan_four_dc_plan.body": (
        149_554,
        "aa84095203924199c060dc7f6ea1175b60895da8f5d9d2dc82746ac18cd45039",
    ),
    "uzbekistan_four_dc_plan.facts": (
        217,
        "768b1b0ed5675d9596c07df844351e02ebcdc2439842fc84ebfbe3138e8d37c4",
    ),
    "uzbekistan_four_dc_plan.headers": (
        2_308,
        "d55b3703ca818cdcd893cbb287e29023b27f914b28131a44fac192d2532fcf4a",
    ),
    "wingu_tanzania_market.body": (
        95_919,
        "b8a1dfdeef8552be2e3ac9f540aa32cf2e2af89cb6b0055731c41b7e7d37bfd1",
    ),
    "wingu_tanzania_market.facts": (
        214,
        "0419d13fa39182ab9953c8ae768c90a4d45bd5dbaf6a5e12a362539ab0a0f7ee",
    ),
    "wingu_tanzania_market.headers": (
        1_144,
        "97f1e9e793b4b90a326ae2163b85a480b72735eb705f4168f346fc6ff488f9b0",
    ),
    "wingu_tanzania_sales_2026.body": (
        78_226,
        "6519f02ded998624224f40e8a89a4cecc4631a2425609d847613ac0745319c8c",
    ),
    "wingu_tanzania_sales_2026.facts": (
        346,
        "16772cac42321041b4f19af3e1c8dfe123785f4e74b1fe9905d68ba7163fef58",
    ),
    "wingu_tanzania_sales_2026.headers": (
        1_214,
        "ab7adff6c18c9978daf55e0aaca2618ff704fe04bff6f3a6c8c032d0e08fa027",
    ),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    stem: str
    publisher: str
    requested_url: str
    effective_url: str
    retrieved_at: str
    published_at: str | None
    content_type: str
    use: str


CAPTURES = (
    Capture(
        "dushanbe_it_hub",
        "dushanbe_it_hub",
        "Agency for Innovation and Digital Technologies under the President of Tajikistan",
        "https://egov.tj/site/innovation/press/news/details/6820?lang=ru",
        "https://egov.tj/site/innovation/press/news/details/6820?lang=ru",
        "2026-07-22T05:39:14Z",
        "2026-06-09",
        "text/html",
        "review_only_exact_identity_and_component_phase_ambiguity",
    ),
    Capture(
        "mongolia_green_dc",
        "mongolia_green_dc",
        "Government of Mongolia",
        "https://mongolia.gov.mn/news/view/27586",
        "https://mongolia.gov.mn/news/view/27586",
        "2026-07-22T05:39:16Z",
        "2026-05-13",
        "text/html; charset=UTF-8",
        "review_only_project_presentation_decision",
    ),
    Capture(
        "kyrgyz_investment_meeting",
        "kyrgyz_investment_meeting",
        "National Investment Agency under the President of the Kyrgyz Republic",
        "https://invest.gov.kg/ru/news/21026",
        "https://invest.gov.kg/ru/news/21026",
        "2026-07-22T05:39:19Z",
        "2026-06-04",
        "text/html; charset=utf-8",
        "review_only_investment_discussion",
    ),
    Capture(
        "turkmen_muroosystems_mou",
        "turkmen_muroosystems_mou",
        "Embassy of Turkmenistan in Japan",
        "https://japan.tmembassy.gov.tm/en/news/159251",
        "https://japan.tmembassy.gov.tm/en/news/159251",
        "2026-07-22T05:39:20Z",
        "2026-04-01",
        "text/html; charset=utf-8",
        "review_only_mou_legal_foundation",
    ),
    Capture(
        "uzbekistan_four_dc_plan",
        "uzbekistan_four_dc_plan",
        "Ministry of Digital Technologies of Uzbekistan",
        "https://digital.gov.uz/en/news/view/114575",
        "https://digital.gov.uz/en/news/view/114575",
        "2026-07-22T05:39:55Z",
        "2025-12-26",
        "text/html; charset=utf-8",
        "review_only_aggregate_regional_program",
    ),
    Capture(
        "kazakhstan_200mw_mou",
        "kazakhstan_200mw_mou",
        "Ministry of Artificial Intelligence and Digital Development of Kazakhstan",
        "https://www.gov.kz/memleket/entities/maidd/press/news/6",
        "https://www.gov.kz/memleket/entities/maidd/press/news/6",
        "2026-07-22T05:39:56Z",
        "2026-05-05",
        "application/json",
        "review_only_mou_and_site_selection",
    ),
    Capture(
        "wingu_tanzania_sales_2026",
        "wingu_tanzania_sales_2026",
        "Wingu Africa",
        "https://www.wingu.africa/latest-news/wingu-africa-appoints-"
        "prasad-acharya-as-director-of-sales-for-tanzania",
        "https://www.wingu.africa/latest-news/wingu-africa-appoints-"
        "prasad-acharya-as-director-of-sales-for-tanzania",
        "2026-07-22T05:39:57Z",
        "2026-03-16",
        "text/html",
        "review_only_non_phase_specific_capacity_expansion",
    ),
    Capture(
        "wingu_tanzania_market",
        "wingu_tanzania_market",
        "Wingu Africa",
        "https://www.wingu.africa/markets/tanzania",
        "https://www.wingu.africa/markets/tanzania",
        "2026-07-22T05:39:57Z",
        None,
        "text/html",
        "review_only_current_operational_facility_inventory",
    ),
    Capture(
        "kasi_current_home",
        "kasi_current_home",
        "Kasi Cloud Datacenters",
        "https://www.kasicloud.com/",
        "https://www.kasicloud.com/",
        "2026-07-22T05:39:57Z",
        None,
        "text/html",
        "collision_check_against_v96_commissioning_record",
    ),
    Capture(
        "paix_djibouti_current_route",
        "paix_djibouti_current_route",
        "PAIX Data Centres",
        "https://www.paix.io/fr-fr/locations/djibouti",
        "https://www.paix.io/contact-us",
        "2026-07-22T05:40:23Z",
        None,
        "text/html;charset=utf-8",
        "review_only_current_route_redirect_and_no_physical_update",
    ),
)

CAMPUS_KEY = "curated-review:central-asia-gap-it-hub-dushanbe-complex"
PROJECT_KEY = (
    "curated-review:central-asia-gap-it-hub-dushanbe-complex:"
    "regional-ai-center-data-center-component"
)
EVIDENCE_KEY = "it-hub-dushanbe-mixed-use-groundbreaking-2026-06-09-captured-2026-07-22"

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
    facts = CAPTURE_FILE_PINS[f"{capture.stem}.facts"]
    return {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_bundle_id": CAPTURE_BUNDLE_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": "credential_free_curl_location",
        "capture_use": capture.use,
        "requested_url": capture.requested_url,
        "effective_url": capture.effective_url,
        "http_status": 200,
        "content_type": capture.content_type,
        "request_credentials_supplied": False,
        "content_hash_scope": (
            f"SHA-256 of the exact {body[0]}-byte public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "response_body_bytes": body[0],
        "response_body_sha256": body[1],
        "response_headers_bytes": headers[0],
        "response_headers_sha256": headers[1],
        "response_facts_bytes": facts[0],
        "response_facts_sha256": facts[1],
        "raw_response_redistributed": False,
        "rights_scope": (
            "Compact factual extraction from a public all-rights-reserved "
            "first-party page; exact response bytes remain private."
        ),
    }


def expected_source_document() -> dict[str, Any]:
    metadata = _capture_metadata("dushanbe_it_hub")
    metadata.update(
        {
            "ceremony_as_reported": (
                "First-stone ceremony for construction of the modern mixed-use "
                "IT Hub Dushanbe complex."
            ),
            "complex_component_count_as_reported": 4,
            "data_center_component_as_reported": (
                "The Dushanbe Regional Artificial Intelligence Center is described "
                "as a research and innovation center with advanced computing "
                "infrastructure and a data center."
            ),
            "complex_investment_usd_as_reported": 100_000_000,
            "complex_construction_area_sqm_as_reported": 53_000,
            "component_phase_guardrail": (
                "The physical ceremony and construction wording apply to the full "
                "four-object mixed-use complex. The page gives no component-level "
                "work start, phase sequence, contractor mobilization, excavation, "
                "foundation, shell, MEP, commissioning, or operation evidence for "
                "the data-center component."
            ),
            "lifecycle_guardrail": (
                "No data-center lifecycle observation is created. A mixed-use "
                "complex groundbreaking is not normalized as physical construction "
                "of one constituent data-center component."
            ),
            "capacity_energy_guardrail": (
                "The investment and floor-area figures cover the full complex and "
                "are not allocated to the data center. The page supplies no MW, "
                "MVA, IT load, grid demand, generation, consumption, PUE, WUE, or "
                "annual-energy value."
            ),
            "classification_guardrail": (
                "AI and advanced-computing wording creates no normalized data-center "
                "type, workload, installed-accelerator, training, inference, HPC, "
                "tenant, customer, operator, or operating-model observation."
            ),
            "location_guardrail": (
                "Dushanbe supports city-and-country locality only. No address, point, "
                "parcel, footprint, building centroid, or geometry is inferred."
            ),
            "imagery_guardrail": (
                "Publisher images, satellite imagery, aerial imagery, maps, and "
                "computer vision contribute no normalized fact."
            ),
            "current_construction_seed_created": False,
        }
    )
    return {
        "schema_version": "1.1",
        "evidence": [
            {
                "key": EVIDENCE_KEY,
                "kind": "government_record",
                "title": (
                    "First stone laid for construction of Tajikistan's IT HUB "
                    "DUSHANBE technology and innovation complex"
                ),
                "source_url": _capture("dushanbe_it_hub").requested_url,
                "publisher": _capture("dushanbe_it_hub").publisher,
                "source_family": "tajikistan_digital_agency_news_review_only",
                "published_at": "2026-06-09",
                "retrieved_at": "2026-07-22T05:39:14Z",
                "license": "all-rights-reserved",
                "attribution": (
                    "Agency for Innovation and Digital Technologies under the "
                    "President of Tajikistan"
                ),
                "excerpt": (
                    "The official page records a first-stone ceremony for the "
                    "mixed-use IT Hub Dushanbe complex and lists a regional AI "
                    "center containing advanced computing infrastructure and a "
                    "data center among four objects."
                ),
                "content_hash": CAPTURE_FILE_PINS["dushanbe_it_hub.body"][1],
                "metadata": metadata,
            }
        ],
        "campus": {
            "stable_key": CAMPUS_KEY,
            "name": "IT Hub Dushanbe Complex (review only)",
            "country": "Tajikistan",
            "address": "Dushanbe, Tajikistan",
            "roles": {},
            "coordinates": None,
            "geometry": None,
            "evidence_key": EVIDENCE_KEY,
            "as_of_date": "2026-06-09",
            "method": "authoritative_locality",
            "confidence": 0.99,
        },
        "project": {
            "stable_key": PROJECT_KEY,
            "name": ("Dushanbe Regional AI Center Data Center Component (review only)"),
            "country": "Tajikistan",
            "address": "Dushanbe, Tajikistan",
            "roles": {},
            "coordinates": None,
            "geometry": None,
            "evidence_key": EVIDENCE_KEY,
            "as_of_date": "2026-06-09",
            "method": "authoritative_locality",
            "confidence": 0.99,
        },
        "lifecycle": [],
        "operating_models": [],
        "workloads": [],
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
    for path, expected in V96_PINS.items():
        _pin(path, expected)
    if tree_digest(V96_RELEASE) != V96_RELEASE_TREE_SHA256:
        raise RuntimeError("frozen v96 release tree differs")

    definition = json.loads(V96_DEFINITION.read_text(encoding="utf-8"))
    source_paths = [ROOT / row["path"] for row in definition["curated_inputs"]]
    proposal = expected_source_document()
    proposal_keys = _stable_keys(proposal)
    proposal_urls = {row["source_url"] for row in proposal["evidence"]}
    source_key_hits: list[dict[str, str]] = []
    source_url_hits: list[dict[str, str]] = []
    for path in source_paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        for key in sorted(proposal_keys & _stable_keys(document)):
            source_key_hits.append({"path": relative, "stable_key": key})
        for evidence in document.get("evidence", []):
            if evidence.get("source_url") in proposal_urls:
                source_url_hits.append(
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
    kasi_rows: list[dict[str, str]] = []
    with V96_ENTITIES.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["stable_key"] in proposal_keys:
                release_key_hits.append(row["stable_key"])
            if row["stable_key"].startswith("curated:kasi-lekki-data-centre-campus"):
                kasi_rows.append(
                    {
                        "stable_key": row["stable_key"],
                        "name": row["name"],
                        "status": row["status"],
                    }
                )
    if any(
        (
            source_key_hits,
            source_url_hits,
            later_key_hits,
            later_url_hits,
            release_key_hits,
        )
    ):
        raise RuntimeError(
            "Dushanbe review proposal collides with accepted source state"
        )
    manifest = json.loads(V96_MANIFEST.read_text(encoding="utf-8"))
    return {
        "v96_definition": {
            "bytes": V96_PINS[V96_DEFINITION][0],
            "sha256": V96_PINS[V96_DEFINITION][1],
            "curated_input_count": len(source_paths),
        },
        "v96_release": {
            "tree_sha256": V96_RELEASE_TREE_SHA256,
            "entity_count": manifest["entities"],
            "evidence_count": manifest["evidence_records"],
            "proposal_stable_key_collisions": release_key_hits,
        },
        "proposal": {
            "stable_keys": sorted(proposal_keys),
            "source_urls": sorted(proposal_urls),
        },
        "v96_source_stable_key_collisions": source_key_hits,
        "v96_source_url_collisions": source_url_hits,
        "later_source_stable_key_collisions": later_key_hits,
        "later_source_url_collisions": later_url_hits,
        "kasi_v96_rows": kasi_rows,
        "new_seed_eligible_entity_count": 0,
        "review_carrier_entity_count": 2,
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    candidates = [
        {
            "candidate_id": "it-hub-dushanbe-regional-ai-center-data-center-component",
            "country": "Tajikistan",
            "decision": "review_only_mixed_use_component_phase_ambiguous",
            "official_observation_date": "2026-06-09",
            "complex_physical_observation": "first-stone ceremony",
            "data_center_named_as_constituent_component": True,
            "data_center_component_physical_work_confirmed": False,
            "normalized_capacity_rows": 0,
            "normalized_energy_rows": 0,
            "normalized_workload_rows": 0,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "mongolia-green-data-center",
            "country": "Mongolia",
            "decision": "review_only_cop17_presentation_decision_no_physical_start",
            "official_observation_date": "2026-05-13",
            "site_identity_resolved": False,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "kyrgyzstan-unnamed-modern-data-centers",
            "country": "Kyrgyzstan",
            "decision": "review_only_investment_discussion_no_project_identity",
            "official_observation_date": "2026-06-04",
            "meeting_discussed_possibilities": True,
            "site_identity_resolved": False,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "turkmenistan-muroosystems-data-centers",
            "country": "Turkmenistan",
            "decision": "review_only_mou_legal_foundation_no_physical_start",
            "official_observation_date": "2026-03-31",
            "memorandum_scope": "legal foundation for future cooperation",
            "site_identity_resolved": False,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "uzbekistan-four-regional-data-centers-2026",
            "country": "Uzbekistan",
            "decision": "review_only_aggregate_program_no_exact_identity_or_physical_status",
            "official_observation_date": "2025-12-26",
            "regions_as_reported": [
                "Tashkent city",
                "Bukhara region",
                "Fergana region",
                "Tashkent region",
            ],
            "datavolt_tashkent_is_separate_and_already_in_v96": True,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "kazakhstan-jmot04-ample-50-to-200mw",
            "country": "Kazakhstan",
            "decision": "review_only_mou_and_location_selection",
            "official_observation_date": "2026-05-05",
            "reported_range_mw_metadata_only": [50, 200],
            "reported_gas_generation_mw_metadata_only": 250,
            "normalized_capacity_rows": 0,
            "data_center_valley_and_akashi_are_separate_v96_projects": True,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "wingu-dar-es-salaam-capacity-expansion",
            "country": "Tanzania",
            "decision": "review_only_current_portfolio_expansion_not_phase_specific_physical_status",
            "official_observation_date": "2026-03-16",
            "current_market_page_reports_operational_facility_features": True,
            "named_active_construction_phase": False,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "paix-jib1-djibouti",
            "country": "Djibouti",
            "decision": "review_only_old_collaboration_and_current_route_redirect",
            "old_announcement_date": "2024-05-14",
            "old_forecast": "phase one expected to open in 2026",
            "current_location_route_effective_url": "https://www.paix.io/contact-us",
            "current_project_specific_physical_update": False,
            "current_construction_seed_created": False,
        },
        {
            "candidate_id": "kasi-los1-lekki",
            "country": "Nigeria",
            "decision": "already_covered_in_v96_commissioning_not_a_gap",
            "v96_stable_key": (
                "curated:kasi-lekki-data-centre-campus:los1-first-building"
            ),
            "current_company_home_wording": "Coming Soon",
            "v96_lifecycle_status": "commissioning",
            "seed_created_by_this_artifact": False,
        },
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-gap-candidate-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "scope": ["Africa", "Central Asia"],
        "first_party_only": True,
        "physical_threshold": (
            "Project-specific current evidence of site activity; plans, permits, "
            "finance, land, aggregate portfolios, mixed-use component ambiguity, "
            "and stale starts do not qualify."
        ),
        "candidates": candidates,
        "prior_africa_review_boundary_preserved": {
            "teraco_jb7": (
                "Current 41 MW Teraco portfolio aggregate is not allocated to JB7."
            ),
            "africa_data_centres_accra": (
                "Old future-start and financing statements remain non-physical."
            ),
            "ixafrica_nbox_phase_2": (
                "Phase identity and current physical state remain unresolved."
            ),
        },
        "totals": {
            "screened_signals": len(candidates),
            "governed_prepublication_candidates": 0,
            "review_only_absent_signals": 8,
            "already_covered_in_v96": 1,
            "published": 0,
            "seeded": 0,
        },
    }


def _retrieval_inventory(recorded_at: str) -> dict[str, Any]:
    rows = []
    for capture in CAPTURES:
        body = CAPTURE_FILE_PINS[f"{capture.stem}.body"]
        headers = CAPTURE_FILE_PINS[f"{capture.stem}.headers"]
        facts = CAPTURE_FILE_PINS[f"{capture.stem}.facts"]
        rows.append(
            {
                "capture_id": capture.capture_id,
                "publisher": capture.publisher,
                "requested_url": capture.requested_url,
                "effective_url": capture.effective_url,
                "retrieved_at": capture.retrieved_at,
                "published_at": capture.published_at,
                "use": capture.use,
                "body": {"bytes": body[0], "sha256": body[1]},
                "headers": {"bytes": headers[0], "sha256": headers[1]},
                "facts": {"bytes": facts[0], "sha256": facts[1]},
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
        "country": "Tajikistan",
        "campus_stable_key": CAMPUS_KEY,
        "project_stable_key": PROJECT_KEY,
        "decision": "review_only_mixed_use_component_phase_ambiguous",
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
    readme = f"""# Africa and Central Asia official gap - prepublication only

Built at {recorded_at}; never published or integrated. The bounded first-party sweep found zero exact, absent-v96 data-centre projects meeting the current project-specific physical-construction threshold.

IT HUB DUSHANBE is the closest case. Tajikistan's official digital-agency page records a first-stone ceremony for a four-object mixed-use technology complex and explicitly names a regional AI center with advanced compute infrastructure and a data center. The page does not prove that the data-center component itself entered physical works, so the exact identity is carried review-only with no lifecycle row.

Mongolia, Kyrgyzstan, Turkmenistan, Uzbekistan, and the separate Kazakhstan JMOT04/Ample signal remain plans, discussions, memoranda, aggregate programs, or site-selection work. Wingu Tanzania lacks a named phase-specific current physical update; PAIX Djibouti lacks a current physical update and its current location route redirects to contact; Kasi LOS1 is already represented in v96 as commissioning.

No MW, MVA, generation, demand, consumption, PUE, WUE, annual energy, data-centre type, workload, role, coordinate, geometry, satellite, aerial, or computer-vision claim is normalized. This builder contains no publisher or promotion function and changes no final source, source artifact, open seed, release, map, identity, federation, construction, or coverage product.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-22",
        "source_records": [source_record],
        "totals": {
            "screened_signals": 9,
            "source_records": 1,
            "governed_prepublication_candidates": 0,
            "review_only_absent_signals": 8,
            "already_covered_in_v96": 1,
            "review_carrier_entity_snapshots": 2,
            "new_seed_eligible_entities_against_v96": 0,
            "evidence_records": 1,
            "lifecycle_observations": 0,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "energy_consumption_observations": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
            "computer_vision_normalized_claims": 0,
        },
        "v96_and_later_collision_witness": witness,
        "integration": {
            "published": False,
            "final_source_path_created": False,
            "final_artifact_path_created": False,
            "open_seed_successor_created": False,
            "v96_mutated": False,
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
        "source_rights": (
            "Public government and company pages treated as all-rights-reserved."
        ),
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
        prefix="africa-central-asia-gap-import-", dir="/private/tmp"
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
            "evidence": 1,
            "lifecycle_observations": 0,
            "operating_model_observations": 0,
            "workload_observations": 0,
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
        "screened_signals": 9,
        "review_source_records": 1,
        "governed_prepublication_candidates": 0,
        "review_only_absent_signals": 8,
        "already_covered_in_v96": 1,
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
    first = _offline_import(source_path, "2026-07-22T06:00:00Z")
    second = _offline_import(source_path, "2026-07-22T06:00:00Z")
    if first != second:
        raise RuntimeError("Africa/Central Asia offline replay differs")

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
        or manifest.get("governed_prepublication_candidates") != 0
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
    serialized = b"".join(entries[name].read_bytes() for name in CONTENT_FILES)
    if b"/Users/" in serialized or b"/private/" in serialized:
        raise RuntimeError("candidate artifact leaks a private filesystem path")
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
            prefix=".africa-central-asia-gap-prepublication-sources.",
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
        "status": "PREPUBLICATION_REVIEW_CARRIER_BUILT_NOT_PUBLISHED",
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
        "screened_signals": manifest["screened_signals"],
        "governed_prepublication_candidates": 0,
        "review_only_absent_signals": manifest["review_only_absent_signals"],
        "already_covered_in_v96": manifest["already_covered_in_v96"],
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
