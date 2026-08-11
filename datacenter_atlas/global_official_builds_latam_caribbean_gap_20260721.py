"""Publish a bounded official LatAm and Caribbean build-gap assessment.

The artifact is independent of open-seed and downstream products. All source
and artifact bytes are staged privately before the declared recording instant,
then promoted without replacement with identity-checked rollback.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .external_captures import resolve_external_capture
from . import global_official_builds_next_tranche_20260721 as publication
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "global-official-builds-latam-caribbean-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".global-official-builds-latam-caribbean-gap-20260721.lock"
CAPTURE_ORIGIN = Path("/private/tmp/dc-official-latam-caribbean-20260721.pPqxte")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-official-latam-caribbean-20260721.pPqxte")
CAPTURE_TREE_SHA256 = (
    "2c635cbb2189faa992d4f8ac536dd3663843ac173751bbcf881390139f0be2e9"
)
CAPTURE_FILE_COUNT = 31
CAPTURE_TOTAL_BYTES = 16_208_486

V77_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v77.json"
V77_RELEASE = ROOT / "releases/2026-07-21-open-seed-v77"
V77_MANIFEST = V77_RELEASE / "manifest.json"
V77_ENTITIES = V77_RELEASE / "entities.csv"
V77_PINS = {
    V77_DEFINITION: (
        92_782,
        "7f228fc5b4cfd0beb2655519ffc28ac7a12d6185b81c61db3ef21ad9e6dce00a",
    ),
    V77_MANIFEST: (
        13_615,
        "a35f3c064aabda5598d336cda264e4b798a516afe96331074f51d33fada4b7bb",
    ),
    V77_ENTITIES: (
        916_052,
        "521263d704ff5d424c78e13fccb524838e8743cc0497ea74c2f1abbabd701dc4",
    ),
}
V77_TREE_SHA256 = (
    "7eebe5bb4f83c40cdc1f113fa6dc8f5e71337aee02818565e2d276f307c160ce"
)
V77_INPUT_COUNT = 416

SOURCE_FILENAMES = (
    "curated-official-2026-07-21-hive-yguazu-100mw-expansion-current-build.json",
    "curated-official-2026-07-21-puntonet-epicentro-quito-current-build.json",
    "curated-official-2026-07-21-telcosub-costa-del-este-review-only.json",
)
CONTENT_FILES = (
    "README.md",
    "candidate-assessment.json",
    "retrieval-inventory.json",
    "rights-and-disposition.json",
    "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))

OfficialLatamCaribbeanGapError = publication.OfficialTrancheError
_canonical = publication._canonical
_sha256 = publication._sha256
_sha256_bytes = publication._sha256_bytes
_instant = publication._instant
_pin = publication._pin
_fsync_regular = publication._fsync_regular
_fsync_directory = publication._fsync_directory
_identity = publication._identity
_has_identity = publication._has_identity
_promote_noreplace = publication._promote_noreplace
_discard_owned_directory = publication._discard_owned_directory
_assert_stage_precedes_target = publication._assert_stage_precedes_target
_assert_final_ctimes = publication._assert_final_ctimes
_require_finals_absent = publication._require_finals_absent
_wait_until = publication._wait_until
_rollback_promotions = publication._rollback_promotions


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "gualeguaychu_april.body": (
        1_590_218,
        "058dcc46c18fff7b3e0364803bd04a121b7cca35f9b82fd818acb64aa3f75d83",
    ),
    "gualeguaychu_april.headers": (
        242,
        "a6b1dee5f1169195f8d49f1c037c233ad045d1581ca7bd2282dd871d717de82e",
    ),
    "gualeguaychu_may.body": (
        1_884_510,
        "ee377bb9221ffef24cbf5645ea4e6545f451505e68fe5142295a81b86283c915",
    ),
    "gualeguaychu_may.headers": (
        259,
        "c0c3d96ba2d30ab766449c3dcf543f0eed64e461139f7b4a4cad484c6179f5cd",
    ),
    "hive_operations.body": (
        107,
        "f8201d4cf5d03cce8b071dd199cbbde9a3ee89db3b249c640982f50d2cde327b",
    ),
    "hive_operations.headers": (
        388,
        "3151a5cefd06be10190bbb2656a4cb5e3dd1a2380f6ff8955fd3ba69ce0d8c7e",
    ),
    "hive_operations_paraguay.body": (
        184_257,
        "f5be3512fb95ab11a36b5d869673e4bcf5c2cc1a016e0091981dc9b0136d9575",
    ),
    "hive_operations_paraguay.headers": (
        391,
        "1fa2ee33eae087ed15257b977043569ec77db36ec672b3ece010c2bef6320496",
    ),
    "hive_release.body": (
        32_543,
        "80ebf1e424e6d961cdc81e0b1a3227b93c5a8dee17e3818c0634e63c70fd0c57",
    ),
    "hive_release.headers": (
        390,
        "23bca652cd619f39dc8a4cf695d9cdc55732d56558704e9f11ccbc47c84ccc96",
    ),
    "hive_sec_10k.headers": (
        322,
        "db22ba0515a93c3966f57b79c3cf1388625c40d236966a6be61fa8812b940a7f",
    ),
    "hive_sec_10k_v2.body": (
        3_249_922,
        "a38b24d030854b3db94008adc14e3bf53c951052f205548daaed9d27a655d13f",
    ),
    "hive_sec_10k_v2.headers": (
        663,
        "72ce13c2cd5d7fdd9c0d6eee9bdafbb1f2e12297159a2b5032118beeb8f52656",
    ),
    "panama_permit.body": (
        1_435_327,
        "98cd4f8f270c7ab3e508f18982441fcbf0b7735819e2ada90d9c3af5fb196fa6",
    ),
    "panama_permit.headers": (
        670,
        "ca8746ece85d66442cd813fc70258b79b3516d31db88e9df36abe1a0d9fa5743",
    ),
    "propanama_facebook_embed.body": (
        73_436,
        "22cd1503057467c09bdfc23aa75bc867ca07e3121e77a5c613340b4045c24f0b",
    ),
    "propanama_facebook_embed.headers": (
        5_220,
        "ed4a1c16fcae19292967d03e762232be5b29842d09fb43d57e65b01c56186668",
    ),
    "propanama_x.body": (
        80_821,
        "60967612da14654538479ccfa4d49dd85aafc0392aaf6fcbbceaeb83f4ed6cfc",
    ),
    "propanama_x.headers": (
        4_506,
        "a2b7be51617b0da794f3276c2c0d60efb6c833f7a6f8ec39341cdda1d7b70c1e",
    ),
    "puntonet_linkedin_embed.body": (
        27_979,
        "6e1a4d95d55017322f56075a520accc5f909a34ee1ebe43dc5a35535458a6f23",
    ),
    "puntonet_linkedin_embed.headers": (
        3_870,
        "60c6f65b5158eee02ac16a4179313cd87b2d2796a2a90998f48c1966b55ef5f5",
    ),
    "puntonet_summit.body": (
        244_865,
        "97ff5aafe8ef0b298aa615cd9fb5fe1f3f93ee6255c08d09c230195d063bff59",
    ),
    "puntonet_summit.headers": (
        634,
        "10c40b95982bad9c9772158e1ea6c769c376b2123afaddbad2592906b2dc77c9",
    ),
    "telconet_2027.body": (
        73_261,
        "1b0643a3e68967412d6d2b78d7d85db11d9457569ccbeb37d4801c6ff6142f7c",
    ),
    "telconet_2027.headers": (
        676,
        "e9d8d3213a3cb2170ba95983fbd08dcb613d18c6807287c4def3fc1287f55da5",
    ),
    "trinidad_midyear_2026.body": (
        336_299,
        "e6e82ab5be7ad70dcdce897522a745f64314c7f14a68c0f513a09155e2bac324",
    ),
    "trinidad_midyear_2026.headers": (
        300,
        "8f7d012a2ac32ec1722c5f29bacd0dc783a55e72a5b1bf8f3400ba76a5b2d07a",
    ),
    "trinidad_psip_2025.body": (
        6_499_241,
        "544acebb14d42ed50abde90128c3d4dad94b7a6a2b9d061fe1d16ffaedc7c198",
    ),
    "trinidad_psip_2025.headers": (
        302,
        "e30e9af72830f162b2fb00e32e4426a41386358fb94b9a9787fa22e80439c374",
    ),
    "trinidad_udecott_schedule.body": (
        476_525,
        "1a31ecedb7b3d302d5d1aa452f480a16a5523d19fb5b1c9d1a212be68f48c14a",
    ),
    "trinidad_udecott_schedule.headers": (
        342,
        "c3495ac1aa8aec8528113b173a77f973b7962cabab25845c598956212eb2d886",
    ),
}


CAPTURES: dict[str, dict[str, Any]] = {
    "hive_sec_10k": {
        "filename": "hive_sec_10k_v2.body",
        "url": "https://www.sec.gov/Archives/edgar/data/1720424/000106299326002973/form10k.htm",
        "retrieved_at": "2026-07-21T16:24:32Z",
        "http_status": 200,
        "bytes": 3_249_922,
        "sha256": "a38b24d030854b3db94008adc14e3bf53c951052f205548daaed9d27a655d13f",
        "content_type": "text/html",
        "used_for_claims": True,
    },
    "hive_release": {
        "filename": "hive_release.body",
        "url": (
            "https://www.hivedigitaltechnologies.com/news/hive-digital-technologies-"
            "targets-35-ehs-in-2026-with-newly-signed-100-mw-hydroelectric-"
            "expansion-in-paraguay-and-a-5x-growth-in-hpc-and-ai-operations-through-"
            "strategic-partnerships-with-bell-canada/"
        ),
        "retrieved_at": "2026-07-21T16:24:32Z",
        "http_status": 200,
        "bytes": 32_543,
        "sha256": "80ebf1e424e6d961cdc81e0b1a3227b93c5a8dee17e3818c0634e63c70fd0c57",
        "content_type": "text/html",
        "used_for_claims": True,
    },
    "hive_operations_paraguay": {
        "filename": "hive_operations_paraguay.body",
        "url": "https://www.hivedigitaltechnologies.com/operations/paraguay/",
        "retrieved_at": "2026-07-21T16:24:52Z",
        "http_status": 200,
        "bytes": 184_257,
        "sha256": "f5be3512fb95ab11a36b5d869673e4bcf5c2cc1a016e0091981dc9b0136d9575",
        "content_type": "text/html",
        "used_for_claims": True,
    },
    "puntonet_summit": {
        "filename": "puntonet_summit.body",
        "url": "https://www.puntonet.ec/summit-2025/",
        "retrieved_at": "2026-07-21T16:24:14Z",
        "http_status": 200,
        "bytes": 244_865,
        "sha256": "97ff5aafe8ef0b298aa615cd9fb5fe1f3f93ee6255c08d09c230195d063bff59",
        "content_type": "text/html; charset=UTF-8",
        "used_for_claims": True,
    },
    "puntonet_linkedin": {
        "filename": "puntonet_linkedin_embed.body",
        "url": "https://www.linkedin.com/embed/feed/update/urn:li:activity:7452362141820518400",
        "retrieved_at": "2026-07-21T16:24:33Z",
        "http_status": 200,
        "bytes": 27_979,
        "sha256": "6e1a4d95d55017322f56075a520accc5f909a34ee1ebe43dc5a35535458a6f23",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": True,
    },
    "panama_permit": {
        "filename": "panama_permit.body",
        "url": "https://doyc.mupa.gob.pa/wp-content/uploads/2025/09/INF_-_C_AGO_25.pdf",
        "retrieved_at": "2026-07-21T16:24:15Z",
        "http_status": 200,
        "bytes": 1_435_327,
        "sha256": "98cd4f8f270c7ab3e508f18982441fcbf0b7735819e2ada90d9c3af5fb196fa6",
        "content_type": "application/pdf",
        "used_for_claims": True,
    },
    "propanama_facebook": {
        "filename": "propanama_facebook_embed.body",
        "url": (
            "https://www.facebook.com/plugins/post.php?href=https%3A%2F%2Fwww."
            "facebook.com%2FAutoridadPROPANAMA%2Fposts%2F757885873604929%2F&"
            "show_text=true&width=500"
        ),
        "retrieved_at": "2026-07-21T16:24:33Z",
        "http_status": 200,
        "bytes": 73_436,
        "sha256": "22cd1503057467c09bdfc23aa75bc867ca07e3121e77a5c613340b4045c24f0b",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": True,
    },
    "telconet_2027": {
        "filename": "telconet_2027.body",
        "url": "https://www.telconet.net/noticias/item/408-inversion2027",
        "retrieved_at": "2026-07-21T16:24:00Z",
        "http_status": 200,
        "bytes": 73_261,
        "sha256": "1b0643a3e68967412d6d2b78d7d85db11d9457569ccbeb37d4801c6ff6142f7c",
        "content_type": "text/html; charset=utf-8",
        "used_for_claims": True,
    },
    "gualeguaychu_april": {
        "filename": "gualeguaychu_april.body",
        "url": "https://ws.gualeguaychu.gov.ar/adjuntos/transparencia/boletines/boletin_oficial_abril_2026.pdf",
        "retrieved_at": "2026-07-21T16:24:34Z",
        "http_status": 200,
        "bytes": 1_590_218,
        "sha256": "058dcc46c18fff7b3e0364803bd04a121b7cca35f9b82fd818acb64aa3f75d83",
        "content_type": "application/pdf",
        "used_for_claims": False,
    },
    "gualeguaychu_may": {
        "filename": "gualeguaychu_may.body",
        "url": "https://gualeguaychu.gov.ar/adjuntos/transparencia/boletines/boletin_oficial_mayo_2026.pdf",
        "retrieved_at": "2026-07-21T16:24:36Z",
        "http_status": 200,
        "bytes": 1_884_510,
        "sha256": "ee377bb9221ffef24cbf5645ea4e6545f451505e68fe5142295a81b86283c915",
        "content_type": "application/pdf",
        "used_for_claims": False,
    },
    "trinidad_midyear": {
        "filename": "trinidad_midyear_2026.body",
        "url": "https://www.finance.gov.tt/wp-content/uploads/2026/06/Mid-Year-Review-2026-1-1.pdf",
        "retrieved_at": "2026-07-21T16:25:30Z",
        "http_status": 200,
        "bytes": 336_299,
        "sha256": "e6e82ab5be7ad70dcdce897522a745f64314c7f14a68c0f513a09155e2bac324",
        "content_type": "application/pdf",
        "used_for_claims": False,
    },
    "trinidad_psip": {
        "filename": "trinidad_psip_2025.body",
        "url": "https://www.finance.gov.tt/wp-content/uploads/2025/08/PSIP-Trinidad2025-Final-Digital.pdf",
        "retrieved_at": "2026-07-21T16:25:31Z",
        "http_status": 200,
        "bytes": 6_499_241,
        "sha256": "544acebb14d42ed50abde90128c3d4dad94b7a6a2b9d061fe1d16ffaedc7c198",
        "content_type": "application/pdf",
        "used_for_claims": False,
    },
    "trinidad_udecott": {
        "filename": "trinidad_udecott_schedule.body",
        "url": (
            "https://udecott.com/wp-content/uploads/UDeCOTTs-Annual-Procurement-"
            "Schedule-2024-2025-%E2%80%93-Version-2.pdf"
        ),
        "retrieved_at": "2026-07-21T16:25:31Z",
        "http_status": 200,
        "bytes": 476_525,
        "sha256": "1a31ecedb7b3d302d5d1aa452f480a16a5523d19fb5b1c9d1a212be68f48c14a",
        "content_type": "application/pdf",
        "used_for_claims": False,
    },
}


def _evidence(
    capture_id: str,
    *,
    key: str,
    kind: str,
    title: str,
    publisher: str,
    source_family: str,
    published_at: str | None,
    excerpt: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    common = {
        "content_hash_scope": (
            f"SHA-256 of the exact {capture['bytes']}-byte content-decoded "
            "credential-free public response body"
        ),
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "http_status": 200,
        "content_type": capture["content_type"],
        "request_credentials_supplied": False,
        "rights_scope": (
            "Compact factual extraction from all-rights-reserved official bytes; "
            "response bodies, headers, telemetry, and publisher media are not redistributed."
        ),
        "imagery_guardrail": (
            "No publisher image, satellite image, aerial image, computer vision, "
            "or analyst geolocation contributes to this record."
        ),
    }
    common.update(metadata)
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "source_url": capture["url"],
        "publisher": publisher,
        "source_family": source_family,
        "published_at": published_at,
        "retrieved_at": capture["retrieved_at"],
        "license": "all-rights-reserved",
        "attribution": publisher,
        "excerpt": excerpt,
        "content_hash": capture["sha256"],
        "metadata": common,
    }


def _entity(
    *,
    stable_key: str,
    name: str,
    country: str,
    address: str,
    roles: Mapping[str, list[str]],
    evidence_key: str,
    as_of_date: str,
    confidence: float = 0.99,
) -> dict[str, Any]:
    return {
        "stable_key": stable_key,
        "name": name,
        "country": country,
        "address": address,
        "roles": dict(roles),
        "coordinates": None,
        "geometry": None,
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_locality",
        "confidence": confidence,
    }


def _lifecycle(evidence_key: str, as_of_date: str) -> dict[str, Any]:
    return {
        "entity": "project",
        "value": "under_construction",
        "evidence_key": evidence_key,
        "as_of_date": as_of_date,
        "method": "authoritative_physical_status_update",
        "confidence": 0.99,
    }


def _hive_source() -> dict[str, Any]:
    filing_key = "hive-yguazu-fy2026-10k-construction-captured-2026-07-21"
    agreement_key = "hive-yguazu-100mw-agreement-captured-2026-07-21"
    operations_key = "hive-yguazu-current-operations-page-captured-2026-07-21"
    publisher = "HIVE Digital Technologies Ltd."
    evidence = [
        _evidence(
            "hive_sec_10k",
            key=filing_key,
            kind="company_disclosure",
            title="HIVE Digital Technologies Ltd. Form 10-K for fiscal 2026",
            publisher=publisher,
            source_family="sec_edgar_hive_annual_filings",
            published_at="2026-06-02",
            excerpt=(
                "The filing reports that physical construction had commenced for "
                "HIVE's planned 100 MW Yguazú hashrate-infrastructure expansion."
            ),
            metadata={
                "sec_accession": "0001062993-26-002973",
                "period_end": "2026-03-31",
                "filing_date": "2026-06-02",
                "information_current_through": "2026-06-01",
                "status_wording_scope": (
                    "Construction activities had commenced and key infrastructure "
                    "components had been ordered as of the report date."
                ),
                "physical_status_scope": (
                    "This supports generic under_construction as of 2026-06-01. It "
                    "does not establish commissioning, energization, completion, or operation."
                ),
                "workload_scope": (
                    "The filing directly identifies the expansion as hashrate-services "
                    "infrastructure and describes HIVE's digital-asset mining model."
                ),
                "capacity_guardrail": (
                    "The 100 MW construction scope is not normalized from this sentence "
                    "as IT load, gross facility demand, generation, draw, or energy."
                ),
            },
        ),
        _evidence(
            "hive_release",
            key=agreement_key,
            kind="company_disclosure",
            title="HIVE announces a 100 MW hydroelectric expansion at Yguazú",
            publisher=publisher,
            source_family="hive_company_news_releases",
            published_at="2025-10-21",
            excerpt=(
                "HIVE reports a definitive agreement for an additional hydroelectric "
                "data-center campus expansion at Yguazú."
            ),
            metadata={
                "announcement_date": "2025-10-21",
                "lifecycle_guardrail": (
                    "Agreement and target wording alone create no construction observation."
                ),
                "capacity_guardrail": (
                    "This release supplies agreement context; the contracted grid row "
                    "uses the later audited filing's ANDE power-supply disclosure."
                ),
            },
        ),
        _evidence(
            "hive_operations_paraguay",
            key=operations_key,
            kind="company_disclosure",
            title="HIVE Paraguay operations",
            publisher=publisher,
            source_family="hive_current_operations_pages",
            published_at=None,
            excerpt=(
                "The current operator page identifies the Yguazú expansion and targets "
                "full commissioning in the third calendar quarter of 2026."
            ),
            metadata={
                "status_date_basis": "retrieval_date_of_current_operator_page",
                "target_period_as_reported": "calendar Q3 2026",
                "reported_label": "Consumption 100 MW",
                "lifecycle_guardrail": (
                    "A commissioning target is not proof of completion, commissioning, "
                    "energization, operation, or ongoing physical activity on retrieval date."
                ),
                "capacity_guardrail": (
                    "The page's consumption label is preserved as narrative and is not "
                    "treated as current draw, IT load, gross demand, or annual energy."
                ),
            },
        ),
    ]
    campus_key = "curated:hive-yguazu-paraguay-campus"
    project_key = f"{campus_key}:2026-100mw-expansion"
    address = "Yguazú, Paraguay"
    roles = {"operator": [publisher]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="HIVE Yguazú Paraguay Campus",
            country="Paraguay",
            address=address,
            roles=roles,
            evidence_key=filing_key,
            as_of_date="2026-06-01",
        ),
        "project": _entity(
            stable_key=project_key,
            name="HIVE Yguazú 2026 100 MW Expansion",
            country="Paraguay",
            address=address,
            roles=roles,
            evidence_key=filing_key,
            as_of_date="2026-06-01",
        ),
        "lifecycle": [_lifecycle(filing_key, "2026-06-01")],
        "operating_models": [],
        "workloads": [
            {
                "entity": "project",
                "value": "crypto_mining",
                "evidence_key": filing_key,
                "as_of_date": "2026-06-01",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ],
        "capacities": [
            {
                "entity": "project",
                "metric": "grid_connection_mw",
                "stage": "contracted",
                "unit": "MW",
                "low": 100,
                "base": 100,
                "high": 100,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": filing_key,
                "as_of_date": "2026-06-01",
                "target_date": None,
                "notes": (
                    "The audited filing discloses an additional 100 MW ANDE power-supply "
                    "agreement for the Yguazú expansion. Contracted utility supply only: "
                    "not IT load, gross facility demand, generation nameplate, current draw, "
                    "consumption, annual energy, PUE, or evidence of energization. Existing "
                    "200 MW available and 193.4 MW utilized campus context is excluded."
                ),
            }
        ],
    }


def _puntonet_source() -> dict[str, Any]:
    design_key = "puntonet-epicentro-summit-specification-captured-2026-07-21"
    status_key = "puntonet-epicentro-ceo-construction-update-captured-2026-07-21"
    evidence = [
        _evidence(
            "puntonet_summit",
            key=design_key,
            kind="company_disclosure",
            title="Puntonet Summit 2025: Epicentro",
            publisher="Puntonet",
            source_family="puntonet_epicentro_pages",
            published_at="2025-10-30",
            excerpt=(
                "Puntonet describes Epicentro as a phased Quito data-center project "
                "designed for high-density and AI-ready infrastructure."
            ),
            metadata={
                "date_modified": "2025-11-25",
                "floor_area_square_metres_as_reported": 8_460,
                "rack_count_as_reported": 1_008,
                "phases_as_reported": 2,
                "stages_as_reported": 4,
                "racks_per_stage_as_reported": 252,
                "power_label_as_reported": "6MWATTS de energía",
                "capacity_guardrail": (
                    "The publisher labels 6 MW as energy without a technical boundary. "
                    "It remains untyped narrative and creates no normalized capacity, "
                    "current-load, consumption, or annual-energy row. Rack counts are not "
                    "converted to MW."
                ),
                "workload_guardrail": (
                    "AI-ready and high-density design capability creates no active AI workload."
                ),
            },
        ),
        _evidence(
            "puntonet_linkedin",
            key=status_key,
            kind="company_disclosure",
            title="Epicentro construction update by Puntonet CEO Katherin Miño Sánchez",
            publisher="Katherin Miño Sánchez, CEO of Puntonet",
            source_family="puntonet_executive_official_updates",
            published_at="2026-04-21",
            excerpt=(
                "Puntonet's CEO reports active Epicentro site work involving concrete, "
                "formwork, masonry, structural plans, cooling, and high-voltage systems."
            ),
            metadata={
                "canonical_post_url": (
                    "https://es.linkedin.com/posts/katherin-mi%C3%B1o-s%C3%A1nchez_"
                    "infraestructuradigital-ecuadordigital-epicentro-liderazgo-"
                    "activity-7452362141820518400-f62B"
                ),
                "linkedin_activity_id": "7452362141820518400",
                "activity_timestamp_utc": "2026-04-21T14:26:32.803Z",
                "capture_surface": "unauthenticated_public_linkedin_embed",
                "author_role_visible_in_capture": "CEO, Puntonet",
                "physical_status_scope": (
                    "Explicit current work topics support generic under_construction on "
                    "the post date. They do not establish a finer stage or completion."
                ),
                "location_guardrail": (
                    "Only Quito is normalized. A north-Quito description from secondary "
                    "reporting supplies no address or coordinate."
                ),
            },
        ),
    ]
    campus_key = "curated:puntonet-epicentro-quito-campus"
    project_key = f"{campus_key}:current-build"
    address = "Quito, Ecuador"
    roles = {"developer": ["Puntonet"]}
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="Puntonet Epicentro Quito Campus",
            country="Ecuador",
            address=address,
            roles=roles,
            evidence_key=design_key,
            as_of_date="2025-10-30",
        ),
        "project": _entity(
            stable_key=project_key,
            name="Puntonet Epicentro Quito Current Build",
            country="Ecuador",
            address=address,
            roles=roles,
            evidence_key=status_key,
            as_of_date="2026-04-21",
        ),
        "lifecycle": [_lifecycle(status_key, "2026-04-21")],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def _telcosub_source() -> dict[str, Any]:
    permit_key = "telcosub-costa-del-este-municipal-permit-captured-2026-07-21"
    start_key = "telcosub-costa-del-este-propanama-start-captured-2026-07-21"
    current_key = "telconet-panama-edge-network-current-page-captured-2026-07-21"
    evidence = [
        _evidence(
            "panama_permit",
            key=permit_key,
            kind="government_record",
            title="Panama City construction-permit report for August 2025",
            publisher="Dirección de Obras y Construcciones, Municipio de Panamá",
            source_family="panama_city_monthly_construction_permit_reports",
            published_at="2025-09-02",
            excerpt=(
                "The municipal report identifies TELCOSUB, IBUILD, Calle Primera in "
                "Costa del Este, and a building for a data center and offices."
            ),
            metadata={
                "report_page": 57,
                "permit_id": "ATC-101",
                "owner_as_reported": "TELCONET SUBMARINE NETWORKS S.A. (TELCOSUB)",
                "contractor_as_reported": "IBUILD INC.",
                "location_as_reported": "COSTA DEL ESTE, CALLE PRIMERA",
                "project_description_as_reported": "EDIFICIO PARA DATA CENTER Y OFICINAS",
                "permit_value_balboa_as_reported": 587_610,
                "lifecycle_guardrail": (
                    "A permit report supplies identity and regulatory context, not proof "
                    "that physical work continued after the last direct status update."
                ),
            },
        ),
        _evidence(
            "propanama_facebook",
            key=start_key,
            kind="government_record",
            title="PROPANAMA reports Telconet's first Panama data-center construction",
            publisher="Autoridad para la Atracción de Inversiones y Promoción de Exportaciones (PROPANAMA)",
            source_family="propanama_official_social_updates",
            published_at="2025-07-29",
            excerpt=(
                "PROPANAMA reports that Telconet started construction of its first "
                "Panama data center, with a 160-rack first phase."
            ),
            metadata={
                "canonical_post_url": "https://www.facebook.com/AutoridadPROPANAMA/posts/757885873604929/",
                "facebook_data_utime": 1_753_843_518,
                "post_timestamp_utc": "2025-07-30T02:45:18Z",
                "phase_one_racks_as_reported": 160,
                "investment_usd_lower_bound_as_reported": 10_000_000,
                "tier_goal_as_reported": "seek Tier 3 classification",
                "power_label_as_reported": "1.5 megas",
                "capacity_guardrail": (
                    "The unit boundary of '1.5 megas' is absent. It remains untyped and "
                    "creates no MW, IT-load, gross-demand, generation, energy, or draw row."
                ),
                "lifecycle_guardrail": (
                    "The July 2025 start is retained as historical evidence but creates "
                    "no lifecycle row because no later direct physical-status source was found."
                ),
            },
        ),
        _evidence(
            "telconet_2027",
            key=current_key,
            kind="company_disclosure",
            title="Telconet investment plan through 2027",
            publisher="Telconet Latam",
            source_family="telconet_company_news",
            published_at="2026-04-13",
            excerpt=(
                "Telconet says it develops an edge-data-center network across the United "
                "States, Colombia, Panama, and Ecuador."
            ),
            metadata={
                "page_last_modified": "2026-04-10",
                "identity_scope": (
                    "This establishes current Panama program continuity but does not name "
                    "a later Costa del Este physical status."
                ),
                "lifecycle_guardrail": (
                    "Network-development language is not direct evidence of continuing "
                    "site work, completion, commissioning, or operation."
                ),
                "alias_guardrail": (
                    "The third-party alias CSN-1 is omitted because no selected first-party "
                    "or regulatory source uses it."
                ),
            },
        ),
    ]
    campus_key = "curated:telcosub-telconet-costa-del-este-edge-data-center"
    project_key = f"{campus_key}:phase-1-review"
    address = "Costa del Este, Calle Primera, Panama City, Panama"
    roles = {
        "owner": ["TELCONET SUBMARINE NETWORKS S.A. (TELCOSUB)"],
        "developer": ["Telconet Latam"],
        "contractor": ["IBUILD INC."],
    }
    return {
        "schema_version": "1.1",
        "evidence": evidence,
        "campus": _entity(
            stable_key=campus_key,
            name="TELCOSUB/Telconet Costa del Este Edge Data Center",
            country="Panama",
            address=address,
            roles=roles,
            evidence_key=permit_key,
            as_of_date="2025-09-02",
            confidence=0.99,
        ),
        "project": _entity(
            stable_key=project_key,
            name="TELCOSUB/Telconet Costa del Este Phase 1 (review only)",
            country="Panama",
            address=address,
            roles=roles,
            evidence_key=start_key,
            as_of_date="2025-07-29",
            confidence=0.98,
        ),
        "lifecycle": [],
        "operating_models": [],
        "workloads": [],
        "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    """Return the exact schema-1.1 source documents."""

    builders = (_hive_source, _puntonet_source, _telcosub_source)
    return {
        name: builder() for name, builder in zip(SOURCE_FILENAMES, builders, strict=True)
    }


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for index, name in enumerate(SOURCE_FILENAMES):
        document = documents[name]
        payload = _canonical(document)
        seed_eligible = index < 2
        records.append(
            {
                "path": f"sources/{name}",
                "bytes": len(payload),
                "sha256": _sha256_bytes(payload),
                "schema_version": "1.1",
                "country": document["project"]["country"],
                "campus_stable_key": document["campus"]["stable_key"],
                "project_stable_key": document["project"]["stable_key"],
                "evidence_records": len(document["evidence"]),
                "lifecycle_observations": len(document["lifecycle"]),
                "operating_model_observations": len(document["operating_models"]),
                "workload_observations": len(document["workloads"]),
                "capacity_estimates": len(document["capacities"]),
                "coordinates_present": 0,
                "geometry_present": 0,
                "disposition": (
                    "seed_eligible_official_physical_update"
                    if seed_eligible
                    else "review_only_stale_physical_start"
                ),
                "seed_eligible": seed_eligible,
                "seeded": False,
            }
        )
    return records


def _capture_reference(capture_id: str) -> dict[str, Any]:
    capture = CAPTURES[capture_id]
    return {
        "source_url": capture["url"],
        "http_status": capture["http_status"],
        "body_bytes": capture["bytes"],
        "body_sha256": capture["sha256"],
    }


def _candidate_assessments(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-five-candidate-latam-caribbean-official-gap-assessment-v1",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "candidate_count": 5,
        "seed_eligible_count": 2,
        "review_only_count": 3,
        "candidates": [
            {
                "candidate_id": "hive-yguazu-2026-100mw-expansion",
                "country": "Paraguay",
                "decision": "seed_eligible_regulatory_physical_construction",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "The filed 2026 Form 10-K directly reports commenced construction "
                    "and ordered infrastructure for the Yguazú expansion."
                ),
                "capacity_disposition": {
                    "100_mw_expansion": "grid_connection_mw_contracted_only",
                    "existing_200_mw_available": "operational_context_excluded",
                    "existing_193_4_mw_utilized": "operational_context_excluded",
                },
                "workload_disposition": "crypto_mining from direct hashrate-services disclosure",
                "coordinate_created": False,
            },
            {
                "candidate_id": "puntonet-epicentro-quito",
                "country": "Ecuador",
                "decision": "seed_eligible_first_party_physical_update",
                "source_record_created": True,
                "seed_eligible": True,
                "basis": (
                    "Puntonet's CEO directly describes contemporaneous concrete, formwork, "
                    "masonry, structural, cooling, and high-voltage construction work."
                ),
                "capacity_disposition": (
                    "The 6MWATTS energy label and rack counts remain untyped narrative."
                ),
                "workload_disposition": (
                    "AI-ready design creates no active AI workload observation."
                ),
                "coordinate_created": False,
            },
            {
                "candidate_id": "telcosub-telconet-costa-del-este-edge-dc",
                "country": "Panama",
                "decision": "review_only_stale_physical_start_no_later_site_status",
                "source_record_created": True,
                "seed_eligible": False,
                "lifecycle_observation_created": False,
                "basis": (
                    "PROPANAMA reported construction started in July 2025, but the April "
                    "2026 Telconet network statement gives no later site-level physical status."
                ),
                "capacity_disposition": "The official '1.5 megas' label is untyped and unnormalized.",
                "alias_disposition": "Third-party CSN-1 alias omitted.",
                "captured_sources": [
                    _capture_reference("panama_permit"),
                    _capture_reference("propanama_facebook"),
                    _capture_reference("telconet_2027"),
                ],
            },
            {
                "candidate_id": "gualeguaychu-municipal-cpd-finishing-stage",
                "country": "Argentina",
                "decision": "review_only_historical_completed_by_2026_05_22",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "April records describe a finishing-stage contract, while the May 22 "
                    "decree uses completed/past-tense certification wording."
                ),
                "captured_sources": [
                    _capture_reference("gualeguaychu_april"),
                    _capture_reference("gualeguaychu_may"),
                ],
                "status_disposition": "historical completed context, not a current build seed",
            },
            {
                "candidate_id": "gortt-tier-iv-rated-4-modular-data-center",
                "country": "Trinidad and Tobago",
                "decision": "review_watch_cutoff_state_and_location_unresolved",
                "source_record_created": False,
                "seed_eligible": False,
                "basis": (
                    "Official budget and procurement records describe construction and "
                    "outfitting, but the current physical state and site are unresolved."
                ),
                "captured_sources": [
                    _capture_reference("trinidad_midyear"),
                    _capture_reference("trinidad_psip"),
                    _capture_reference("trinidad_udecott"),
                ],
                "capacity_disposition": "Tier IV/Rated 4 is a resilience goal, not power capacity.",
                "location_disposition": "No location normalized.",
            },
        ],
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    controlled = [
        {
            "capture_id": capture_id,
            "requested_url": spec["url"],
            "effective_url": spec["url"],
            "retrieved_at": spec["retrieved_at"],
            "http_status": spec["http_status"],
            "content_type": spec["content_type"],
            "body": {
                "bytes": spec["bytes"],
                "sha256": spec["sha256"],
                "retained_in_artifact": False,
                "moved_to_trash": True,
            },
            "capture_method": "credential_free_curl_location_compressed",
            "request_credentials_supplied": False,
            "used_for_normalized_claims": spec["used_for_claims"],
        }
        for capture_id, spec in sorted(CAPTURES.items())
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "capture_protocol": (
            "Credential-free public HTTP GETs; the successful SEC retry used a transparent "
            "research User-Agent. Successful bodies, headers, and failed-attempt headers "
            "were retained privately."
        ),
        "controlled_body_captures": len(CAPTURES),
        "selected_source_evidence_bodies": 8,
        "assessment_only_bodies": 5,
        "technical_or_redirect_bodies": 2,
        "request_credentials_supplied": False,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": controlled,
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
        "technical_incidents": [
            {
                "source_url": CAPTURES["hive_sec_10k"]["url"],
                "first_attempt_http_status": 403,
                "first_attempt_headers": {
                    "path": "hive_sec_10k.headers",
                    "bytes": CAPTURE_FILE_PINS["hive_sec_10k.headers"][0],
                    "sha256": CAPTURE_FILE_PINS["hive_sec_10k.headers"][1],
                },
                "successful_retry_body": "hive_sec_10k_v2.body",
                "failed_attempt_used_for_claims": False,
            },
            {
                "source_url": "https://www.hivedigitaltechnologies.com/operations/",
                "result": "HTTP 200 script-only redirect body to /operations/paraguay/",
                "redirect_body_used_for_claims": False,
                "direct_destination_capture_used": True,
            },
            {
                "source_url": "https://x.com/propanamagob/status/1950387010113261632",
                "result": "HTTP 200 dynamic shell without governed post text",
                "body_used_for_claims": False,
                "official_credential_free_facebook_embed_used": True,
            },
        ],
    }


def _artifact_documents(
    recorded_at: str,
    source_documents: Mapping[str, Mapping[str, Any]],
) -> dict[str, bytes]:
    source_records = _source_records(source_documents)
    readme = f"""# Global official-build LatAm and Caribbean gap assessment

This immutable artifact records five bounded official/regulatory candidate dispositions researched on 2026-07-21. HIVE's Yguazú 100 MW expansion and Puntonet's Epicentro Quito pass the current physical-construction boundary. Their lifecycle rows are dated observations, not timeless current-status claims.

HIVE's 100 MW is normalized only as contracted grid connection from the audited ANDE power-supply disclosure. Existing 200 MW available and 193.4 MW utilized campus context is excluded. The row is never IT load, gross demand, generation, current draw, consumption, annual energy, or proof of energization. The filing directly supports a crypto-mining workload through its hashrate-services description.

Epicentro's publisher-labeled “6MWATTS de energía”, 1,008 racks, two phases, and four stages remain narrative. The power boundary is ambiguous and rack counts are not converted. AI-ready/high-density design creates no active AI workload. Only Quito is normalized; no secondary north-Quito description or analyst geolocation creates an address or coordinate.

TELCOSUB/Telconet Costa del Este receives a review-only schema record with entities and evidence but no lifecycle. PROPANAMA's July 2025 start is too old to seed current construction without a later direct site-level physical update. The April 2026 network-development statement supplies continuity only. “1.5 megas” is untyped, and the third-party CSN-1 alias is omitted.

Gualeguaychú is historical/review-only because the May 22 decree indicates the finishing work was completed. Trinidad and Tobago's Tier IV/Rated 4 modular project remains review/watch: official budget records mention construction/outfitting, but current physical state and location are unresolved. Tier labels are not power capacity.

No publisher imagery, satellite imagery, aerial imagery, computer vision, or analyst geolocation asserts identity, lifecycle, capacity, type, roles, or workload.

All source and artifact bytes were completed in private staging before `{recorded_at}`. Final paths remained absent until that instant and were promoted without replacement as one rollback-protected set. Accepted open seed v77 and all downstream artifacts remain unchanged. Raw all-rights-reserved captures are not redistributed; the complete {CAPTURE_FILE_COUNT}-file directory was moved intact to the recoverable Trash path recorded in the rights inventory.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at,
        "research_date": "2026-07-21",
        "source_records": source_records,
        "totals": {
            "candidate_assessments": 5,
            "source_records": 3,
            "seed_eligible_source_records": 2,
            "review_only_candidates": 3,
            "review_only_source_records": 1,
            "distinct_campuses": 3,
            "projects": 3,
            "entity_snapshots": 6,
            "unique_evidence_records": 8,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 1,
            "coordinates_present": 0,
            "geometry_present": 0,
        },
        "frozen_v77_non_mutation_witness": {
            "definition": {
                "path": "sources/open-seed-2026-07-21-v77.json",
                "bytes": V77_PINS[V77_DEFINITION][0],
                "sha256": V77_PINS[V77_DEFINITION][1],
            },
            "release_manifest": {
                "path": "releases/2026-07-21-open-seed-v77/manifest.json",
                "bytes": V77_PINS[V77_MANIFEST][0],
                "sha256": V77_PINS[V77_MANIFEST][1],
            },
            "release_tree_sha256": V77_TREE_SHA256,
            "v77_selected_input_count": V77_INPUT_COUNT,
            "new_source_paths_selected_by_v77": False,
            "new_stable_key_collisions": 0,
            "new_evidence_key_collisions": 0,
        },
        "integration": {
            "open_seed_successor_created": False,
            "open_seed_v77_mutated": False,
            "release_integration": "none",
            "construction_timeline_integration": "none",
            "federation_integration": "none",
            "identity_integration": "none",
            "coverage_ledger_integration": "none",
            "downstream_product_integration": "none",
        },
        "publication_contract": {
            "version": 1,
            "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True,
            "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "final_root_ctime_not_before_recorded_at": True,
            "source_file_mode": "0644",
            "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-21",
        "recorded_at": recorded_at,
        "source_rights": (
            "Captured publisher response bodies are treated as all-rights-reserved; "
            "no redistribution license was relied on."
        ),
        "artifact_is_hash_only": True,
        "raw_capture_redistributed": False,
        "raw_response_bodies_retained_in_artifact": False,
        "raw_response_headers_retained_in_artifact": False,
        "publisher_media_retained_in_artifact": False,
        "request_credentials_supplied": False,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "temporary_capture_file_count": CAPTURE_FILE_COUNT,
        "temporary_capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "temporary_capture_tree_sha256": CAPTURE_TREE_SHA256,
        "deletion_performed": False,
        "candidate_dispositions": {"seed_eligible": 2, "review_only": 3},
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessments(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _write_source_stage(
    stage: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    for name in SOURCE_FILENAMES:
        output = stage / name
        output.write_bytes(_canonical(documents[name]))
        output.chmod(0o644)
        _fsync_regular(output)
    _fsync_directory(stage)


def _write_artifact_stage(
    stage: Path,
    recorded_at: str,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        output = stage / name
        output.write_bytes(payloads[name])
        output.chmod(0o444)
        _fsync_regular(output)
    rows = [
        {
            "bytes": (stage / name).stat().st_size,
            "path": name,
            "sha256": _sha256(stage / name),
        }
        for name in CONTENT_FILES
    ]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at,
        "files": rows,
        "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES),
        "candidate_assessments": 5,
        "curated_source_records": 3,
        "seed_eligible_source_records": 2,
        "review_only_candidates": 3,
        "review_only_source_records": 1,
        "successful_http_200_body_captures": 15,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "open_seed_successor_created": False,
        "release_integration": "none",
        "downstream_product_integration": "none",
    }
    manifest_path = stage / "manifest.json"
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o444)
    _fsync_regular(manifest_path)
    sidecar = stage / "manifest.sha256"
    sidecar.write_text(f"{_sha256(manifest_path)}  manifest.json\n", encoding="utf-8")
    sidecar.chmod(0o444)
    _fsync_regular(sidecar)
    stage.chmod(0o555)
    _fsync_directory(stage)


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise OfficialLatamCaribbeanGapError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        source = paths[name]
        if source.is_symlink() or not source.is_file():
            raise OfficialLatamCaribbeanGapError(f"curated source is absent: {source}")
        if source.read_bytes() != _canonical(expected[name]):
            raise OfficialLatamCaribbeanGapError(f"curated source differs: {name}")
        if stat.S_IMODE(source.stat().st_mode) != 0o644:
            raise OfficialLatamCaribbeanGapError(f"curated source mode differs: {name}")
    documents = list(expected.values())
    if any(
        document[entity]["coordinates"] is not None
        or document[entity]["geometry"] is not None
        for document in documents
        for entity in ("campus", "project")
    ):
        raise OfficialLatamCaribbeanGapError("source invented coordinates or geometry")
    if any(document["operating_models"] for document in documents):
        raise OfficialLatamCaribbeanGapError("operating-model boundary differs")
    if documents[1]["capacities"] or documents[2]["capacities"]:
        raise OfficialLatamCaribbeanGapError("ambiguous capacity was normalized")
    if documents[1]["workloads"] or documents[2]["workloads"]:
        raise OfficialLatamCaribbeanGapError("unsupported workload was normalized")
    if documents[2]["lifecycle"]:
        raise OfficialLatamCaribbeanGapError("stale Panama start became lifecycle")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    stable_keys = {
        document[entity]["stable_key"]
        for document in planned.values()
        for entity in ("campus", "project")
    }
    evidence_keys = {
        evidence["key"]
        for document in planned.values()
        for evidence in document["evidence"]
    }
    if len(stable_keys) != 6 or len(evidence_keys) != 8:
        raise OfficialLatamCaribbeanGapError("planned source keys are not unique")
    collisions: dict[str, dict[str, list[str]]] = {}
    for source in SOURCES_ROOT.glob("*.json"):
        if source.name in SOURCE_FILENAMES:
            continue
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        other_stable = {
            record.get("stable_key")
            for key in ("campus", "project")
            if isinstance((record := document.get(key)), dict)
        }
        other_evidence = {
            row.get("key")
            for row in document.get("evidence", [])
            if isinstance(row, dict)
        }
        stable_overlap = sorted(stable_keys & other_stable)
        evidence_overlap = sorted(evidence_keys & other_evidence)
        if stable_overlap or evidence_overlap:
            collisions[source.name] = {
                "stable_keys": stable_overlap,
                "evidence_keys": evidence_overlap,
            }
    if collisions:
        raise OfficialLatamCaribbeanGapError(f"curated source collision: {collisions!r}")


def _validate_v77_nonmutation() -> None:
    for source, pin in V77_PINS.items():
        _pin(source, pin)
    if tree_digest(V77_RELEASE) != V77_TREE_SHA256:
        raise OfficialLatamCaribbeanGapError("accepted v77 release tree differs")
    definition = json.loads(V77_DEFINITION.read_text(encoding="utf-8"))
    if len(definition.get("curated_inputs", [])) != V77_INPUT_COUNT:
        raise OfficialLatamCaribbeanGapError("accepted v77 input count differs")
    selected = {row["path"] for row in definition["curated_inputs"]}
    planned_paths = {f"sources/{name}" for name in SOURCE_FILENAMES}
    if selected & planned_paths:
        raise OfficialLatamCaribbeanGapError("v77 unexpectedly selects a new source path")
    entities_text = V77_ENTITIES.read_text(encoding="utf-8")
    for document in expected_source_documents().values():
        for entity in ("campus", "project"):
            if document[entity]["stable_key"] in entities_text:
                raise OfficialLatamCaribbeanGapError("new stable key collides with v77")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise OfficialLatamCaribbeanGapError(
            f"capture directory is absent or unsafe: {directory}"
        )
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT:
        raise OfficialLatamCaribbeanGapError("capture directory file count differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise OfficialLatamCaribbeanGapError("capture directory contains a non-file")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES:
        raise OfficialLatamCaribbeanGapError("capture directory total bytes differs")
    if tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise OfficialLatamCaribbeanGapError("capture directory tree differs")
    if set(CAPTURE_FILE_PINS) != {entry.name for entry in entries}:
        raise OfficialLatamCaribbeanGapError("capture directory closed set differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory() as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for name in SOURCE_FILENAMES:
            adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
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
            "entities": 6,
            "entity_snapshots": 6,
            "evidence": 8,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 1,
        }
        if counts != expected:
            raise OfficialLatamCaribbeanGapError(
                f"offline import counts differ: {counts!r}"
            )
        capacity = tuple(
            connection.execute(
                "SELECT e.stable_key, c.metric, c.stage, c.unit, c.base "
                "FROM capacity_estimates AS c JOIN entities AS e ON e.id=c.entity_id"
            ).fetchone()
        )
        if capacity != (
            "curated:hive-yguazu-paraguay-campus:2026-100mw-expansion",
            "grid_connection_mw",
            "contracted",
            "MW",
            100.0,
        ):
            raise OfficialLatamCaribbeanGapError(
                f"offline capacity row differs: {capacity!r}"
            )
        return counts


def validate_artifact(
    path: Path = ARTIFACT,
    *,
    source_paths: Mapping[str, Path] | None = None,
    require_live: bool = True,
    wall_clock: datetime | None = None,
) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir():
        raise OfficialLatamCaribbeanGapError("artifact must be an ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES:
        raise OfficialLatamCaribbeanGapError("artifact closed file set differs")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries.values()):
        raise OfficialLatamCaribbeanGapError("artifact contains a non-ordinary file")
    if stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise OfficialLatamCaribbeanGapError("artifact directory mode differs")
    if any(stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise OfficialLatamCaribbeanGapError("artifact file mode differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest):
        raise OfficialLatamCaribbeanGapError("manifest JSON is not canonical")
    if (
        manifest.get("artifact_id") != ARTIFACT_ID
        or set(manifest.get("closed_file_set", [])) != CLOSED_FILES
        or manifest.get("candidate_assessments") != 5
        or manifest.get("curated_source_records") != 3
        or manifest.get("seed_eligible_source_records") != 2
        or manifest.get("review_only_candidates") != 3
        or manifest.get("review_only_source_records") != 1
        or manifest.get("open_seed_successor_created") is not False
        or manifest.get("release_integration") != "none"
        or _file_tree(manifest["files"]) != manifest.get("tree_sha256")
    ):
        raise OfficialLatamCaribbeanGapError("manifest contract differs")
    if [row["path"] for row in manifest["files"]] != list(CONTENT_FILES):
        raise OfficialLatamCaribbeanGapError("manifest file order differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise OfficialLatamCaribbeanGapError(
                f"manifest file pin differs: {row['path']}"
            )
    if entries["manifest.sha256"].read_text(encoding="utf-8") != (
        f"{_sha256_bytes(manifest_raw)}  manifest.json\n"
    ):
        raise OfficialLatamCaribbeanGapError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise OfficialLatamCaribbeanGapError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise OfficialLatamCaribbeanGapError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise OfficialLatamCaribbeanGapError("validation wall clock lacks timezone")
    if require_live:
        if now.astimezone(UTC) < target:
            raise OfficialLatamCaribbeanGapError("artifact recorded_at is not live")
        _assert_final_ctimes((*paths.values(), path), target)
    for capture in CAPTURES.values():
        if _instant(capture["retrieved_at"]) > target:
            raise OfficialLatamCaribbeanGapError("capture retrieval post-dates recorded_at")
    return manifest


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as error:
        raise OfficialLatamCaribbeanGapError(
            f"active publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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


def _all_stage_paths(source_stage: Path, artifact_stage: Path) -> tuple[Path, ...]:
    return (
        source_stage,
        *sorted(source_stage.iterdir(), key=lambda item: item.name),
        artifact_stage,
        *sorted(artifact_stage.iterdir(), key=lambda item: item.name),
    )


@dataclass(frozen=True)
class _PreparedPublication:
    recorded_at: str
    target: datetime
    source_stage: Path
    source_stage_identity: tuple[int, int]
    source_identities: Mapping[str, tuple[int, int]]
    artifact_stage: Path
    artifact_identity: tuple[int, int]
    artifact_member_identities: Mapping[str, tuple[int, int]]


def _prepare_publication(recorded_at: str) -> _PreparedPublication:
    target = _instant(recorded_at)
    if datetime.now(UTC) >= target:
        raise OfficialLatamCaribbeanGapError("recorded_at must be future before staging")
    source_stage = Path(
        tempfile.mkdtemp(prefix=".official-builds-latam-caribbean-gap.", dir=SOURCES_ROOT)
    )
    artifact_stage = Path(
        tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT)
    )
    source_stage_identity = _identity(source_stage, directory=True)
    artifact_identity = _identity(artifact_stage, directory=True)
    try:
        documents = expected_source_documents()
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        source_paths = _source_paths(source_stage)
        _validate_sources(source_paths)
        _offline_import(source_paths, recorded_at)
        validate_artifact(
            artifact_stage,
            source_paths=source_paths,
            require_live=False,
            wall_clock=datetime.now(UTC),
        )
        finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
        _require_finals_absent(finals, "staging")
        _assert_stage_precedes_target(_all_stage_paths(source_stage, artifact_stage), target)
        if datetime.now(UTC) >= target:
            raise OfficialLatamCaribbeanGapError(
                "private staging did not finish before recorded_at"
            )
        return _PreparedPublication(
            recorded_at=recorded_at,
            target=target,
            source_stage=source_stage,
            source_stage_identity=source_stage_identity,
            source_identities={
                name: _identity(source_stage / name, directory=False)
                for name in SOURCE_FILENAMES
            },
            artifact_stage=artifact_stage,
            artifact_identity=artifact_identity,
            artifact_member_identities={
                name: _identity(artifact_stage / name, directory=False)
                for name in CLOSED_FILES
            },
        )
    except BaseException as primary_error:
        try:
            if artifact_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in artifact_stage.iterdir()
                }
                _discard_owned_directory(artifact_stage, artifact_identity, members)
            if source_stage.exists():
                members = {
                    entry.name: _identity(entry, directory=False)
                    for entry in source_stage.iterdir()
                }
                _discard_owned_directory(source_stage, source_stage_identity, members)
        except Exception as cleanup_error:
            primary_error.add_note(f"private-stage cleanup failed: {cleanup_error}")
        raise


def _publish(prepared: _PreparedPublication) -> None:
    final_sources = {name: SOURCES_ROOT / name for name in SOURCE_FILENAMES}
    finals = tuple(final_sources.values()) + (ARTIFACT,)
    _require_finals_absent(finals, "pre-wait")
    _wait_until(prepared.target.timestamp())
    _require_finals_absent(finals, "publication")
    _assert_stage_precedes_target(
        _all_stage_paths(prepared.source_stage, prepared.artifact_stage), prepared.target
    )
    promoted: list[tuple[Path, Path, tuple[int, int], bool]] = []
    try:
        for name in SOURCE_FILENAMES:
            stage = prepared.source_stage / name
            final = final_sources[name]
            identity = prepared.source_identities[name]
            _promote_noreplace(stage, final)
            promoted.append((stage, final, identity, False))
            if not _has_identity(final, identity, directory=False):
                raise OfficialLatamCaribbeanGapError(
                    f"source identity changed on promotion: {name}"
                )
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((prepared.artifact_stage, ARTIFACT, prepared.artifact_identity, True))
        if not _has_identity(ARTIFACT, prepared.artifact_identity, directory=True):
            raise OfficialLatamCaribbeanGapError("artifact identity changed on promotion")
        _assert_final_ctimes(finals, prepared.target)
    except BaseException as primary_error:
        try:
            _rollback_promotions(promoted)
        except Exception as rollback_error:
            primary_error.add_note(f"identity-safe rollback failed: {rollback_error}")
        raise


def _cleanup_prepared(prepared: _PreparedPublication) -> None:
    if prepared.artifact_stage.exists():
        _discard_owned_directory(
            prepared.artifact_stage,
            prepared.artifact_identity,
            prepared.artifact_member_identities,
        )
    if prepared.source_stage.exists():
        _discard_owned_directory(
            prepared.source_stage,
            prepared.source_stage_identity,
            prepared.source_identities,
        )


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise OfficialLatamCaribbeanGapError(
            "both capture origin and Trash destination exist"
        )
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def _default_recorded_at() -> str:
    target = math.ceil(time.time() + 25.0)
    return datetime.fromtimestamp(target, UTC).isoformat().replace("+00:00", "Z")


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    """Publish three source records and the five-candidate assessment."""

    target_text = recorded_at or _default_recorded_at()
    finals = tuple(SOURCES_ROOT / name for name in SOURCE_FILENAMES) + (ARTIFACT,)
    _require_finals_absent(finals, "initial")
    _validate_source_collisions()
    _validate_v77_nonmutation()
    capture_directory = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture_directory)
    with _publication_lock():
        _require_finals_absent(finals, "locked initial")
        prepared = _prepare_publication(target_text)
        published = False
        try:
            _move_capture_to_trash()
            _publish(prepared)
            published = True
        finally:
            if not published:
                _cleanup_prepared(prepared)
        if prepared.source_stage.exists():
            _discard_owned_directory(
                prepared.source_stage,
                prepared.source_stage_identity,
                prepared.source_identities,
            )
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))
    _validate_v77_nonmutation()
    manifest = validate_artifact(ARTIFACT)
    source_records = _validate_sources(_source_paths(SOURCES_ROOT))
    return {
        "artifact_id": ARTIFACT_ID,
        "recorded_at": manifest["recorded_at"],
        "manifest_sha256": _sha256(ARTIFACT / "manifest.json"),
        "artifact_tree_sha256": tree_digest(ARTIFACT),
        "source_records": source_records,
        "counts": {
            "candidates": 5,
            "source_records": 3,
            "seed_eligible": 2,
            "review_only": 3,
            "review_only_source_records": 1,
            "evidence": 8,
            "entities": 6,
            "lifecycle": 2,
            "operating_models": 0,
            "workloads": 1,
            "capacities": 1,
            "coordinates": 0,
            "geometry": 0,
        },
        "capture_directory": str(CAPTURE_TRASH),
        "open_seed_successor_created": False,
        "release_integration": "none",
    }


def main() -> int:
    print(json.dumps(build(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
