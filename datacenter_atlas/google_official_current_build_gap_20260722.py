"""Publish a hash-bound Google official current-build source tranche.

Seven separately identified campus/project records are seed eligible. Four
additional prospects remain review-only because the captured official wording
does not establish a physical start for the exact project. Raw response bytes
remain all-rights-reserved and are represented only by exact hashes and compact
factual extracts.
"""

from __future__ import annotations

from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from .external_captures import resolve_external_capture
from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import global_official_current_build_gap_20260721 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "google-official-current-build-gap-2026-07-22-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".google-official-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-google-current-build-20260722.JXFqK4")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-google-current-build-20260722.JXFqK4")
CAPTURE_FILE_COUNT = 30
CAPTURE_TOTAL_BYTES = 5_889_063
CAPTURE_TREE_SHA256 = "52b06a4d336fbd08374fbe0ed0ccb3cfe570917692cf77fb55052d604558c9a5"

V89_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v89.json"
V89_RELEASE = ROOT / "releases/2026-07-21-open-seed-v89"
V89_MANIFEST = V89_RELEASE / "manifest.json"
V89_ENTITIES = V89_RELEASE / "entities.csv"
V89_PINS = {
    V89_DEFINITION: (
        105_962,
        "1c9be663976b1b5e93f31868df73f76e66498f14ef9eff157baefb8144b8289b",
    ),
    V89_MANIFEST: (
        15_707,
        "07f2f521f365b4427c08a7393f72977a68137aa87f9ea015ccf480cac455f9b2",
    ),
    V89_ENTITIES: (
        1_004_639,
        "1a365e5b9a1ba2a3320fb7058e5e4309173e717a2a86e2911fba017318c8c61c",
    ),
}
V89_TREE_SHA256 = "83b721b2066c3be6cbf3cf3bfb255abb8ed4427ad5ebd17da8dcc5214551fdad"
V89_INPUT_COUNT = 470

MASTER_RELEASE = ROOT / "construction_master/2026-07-21-public-open-v31"
MASTER_MANIFEST = MASTER_RELEASE / "manifest.json"
MASTER_CSV = MASTER_RELEASE / "construction-master.csv"
MASTER_PINS = {
    MASTER_MANIFEST: (
        9_721,
        "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e",
    ),
    MASTER_CSV: (
        190_003_570,
        "3c05febb4bc9ed6bc4fa0876e42e1b685269d6763b4c0bbf1f9ecefea3921e5c",
    ),
}
MASTER_TREE_SHA256 = "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da"
GLOBAL_ENTITIES = ROOT / "releases/2026-07-18-global-open-v3/entities.csv"
GLOBAL_ENTITIES_PIN = (
    12_716_173,
    "badd13d11d9aa720f3208a07f93de4a19a73f9bb781db5f1714b3faf68d489f3",
)

_canonical = prior._canonical
_sha256 = prior._sha256
_sha256_bytes = prior._sha256_bytes
_instant = prior._instant
_pin = prior._pin
_fsync_regular = prior._fsync_regular
_fsync_directory = prior._fsync_directory
_promote_noreplace = prior._promote_noreplace


CAPTURE_FILE_PINS: dict[str, tuple[int, str]] = {
    "dorchester-active-headers.txt": (513, "9068861e57dc0809f8dd8727bb7039ee34523cceb7e4d9c6756feb298cfc460b"),
    "dorchester-active.body": (92_905, "f2c70fb8b5b124b54f44ebc1fefad966be75a7cb2ec2e05e6f50396175c56c73"),
    "dorchester-breakground-headers.txt": (513, "c64bf9d5c16c7851792c64c1496ee1f7dacf0459d738ce889aee20b9391c26cd"),
    "dorchester-breakground.body": (92_976, "903f627264f3631e7358db38cebe5b5568bb8e3af911dfe77aa97d064fbd98a3"),
    "dorchester-headers.txt": (407, "aab05fe6f94475b6d49a039264a2746aadbf5b103c76401532962acb68977a59"),
    "dorchester.body": (427, "91ebf8aa4d76a20430f406388f9e93189cbaf43eab11d508c84f82dca2c4063d"),
    "elmina-headers.txt": (241, "9c349468debdf26e8e1384ed3abc018ee339748f6cb03c4b3dd029b76fddb5ff"),
    "elmina.body": (186_319, "90bc2acbad05c6156b0276be6e10d8aa518866ddf8141e29bb906ce12bc41d82"),
    "farciennes-headers.txt": (941, "d1c30a0ee10432bcec18acd0e241c2f8062a9785719f8b6e0515a22f72ec3e75"),
    "farciennes.body": (361_830, "1ae12ce8bae470edf63854ea78d89cf88f4a6ee39728218e0b2463d605e98b6d"),
    "google-sc-headers.txt": (2_799, "bde1389b7268d6b73870ba53f3312ba137e471e5a803948a0a0753b5737fd0fa"),
    "google-sc.body": (376_841, "d6100f3251d11995a646a4558614817a1c7b0eb0cdac1408c458cbf2fa434249"),
    "groningen-headers.txt": (2_799, "737548ce6f10db26fa4a93ea7c35658ceac1bca9aefcb8e267caada9d719ab45"),
    "groningen.body": (273_272, "97286a5a79ce06296d0e4731b1ebaf6691cc0bb27083b99ce3a1ff3bb31b5641"),
    "lagrange-headers.txt": (276, "8424b9c94e978b464d96078fd44268be47649eccc97f940cae3f6ebaf359ad2d"),
    "lagrange.body": (2_679_367, "6df34d0c0fff11594954d963e6f92098aea355036bef85b8e18c224baf53c609"),
    "locations-headers.txt": (1_596, "11cea44a4b71ee7f13aba047b1fe1ca415a12e6ba7e386ae2eca5bbfd216a747"),
    "locations.body": (158_819, "243f43e26afe8134a2654b4a90646fadf4bdd84dbd34723654f1f58accb3d692"),
    "michigan-city-headers.txt": (576, "9378e3b4efa7518d8a80c65ec308d130543ec7d3b5877a011b58a07e4a4b266e"),
    "michigan-city.body": (75_741, "8c4fb14905acba6692e34b0693b507cc077586e53301a87c0d616636acca0812"),
    "morgan-county-headers.txt": (576, "b4e9f98569ed1080314bc15fafc639a3d061ef58a0d165a842f95b37736b9802"),
    "morgan-county.body": (130_297, "6768f96005758a5aa03d7600b3d8b34bd41c9f670a28496e1cc700898f58e6a3"),
    "skien-forum-headers.txt": (700, "9171d1affd9863e9924f1c7f2de4a60b96e3d03c152d100905764a82702c8b9e"),
    "skien-forum.body": (1_218_512, "22211755eebb86cb877079f6fe6e418ab04ced4530dde9696b572d0c59d30a8e"),
    "skien-headers.txt": (666, "660cbcc9eaffed40721bae0069ff12be21e74f74f484d35b2593ff72b31ac408"),
    "skien.body": (57_915, "07e16e0c2bf564864e48548718060fed9c34c94185cd9a7bf2626013b04e8563"),
    "skien-timeline-headers.txt": (666, "854174cec60c2efc0590195f93c832d3f0e355bf5529ebf9d310d99e0cbb7201"),
    "skien-timeline.body": (66_741, "ab6e0766451b8434a10def98ff3810e27deccb5b7ef8f47754f563a2663bba0a"),
    "spade-headers.txt": (445, "2ed82e5a2c2c01cfd5f040832da7259110f9b2333da2c1f949f984a02ca69223"),
    "spade.body": (103_387, "129ffd694b188f001f78d211dd5b66b5d3e38feb8cb1e3e1c0cb0cc170b90c42"),
}


@dataclass(frozen=True)
class Capture:
    capture_id: str
    file_stem: str
    url: str
    retrieved_at: str
    published_at: str | None
    http_status: int
    content_type: str
    use: str


CAPTURES = (
    Capture("dorchester_fact_sheet", "dorchester", "https://www.dorchestercountysc.gov/business/data-center-fact-sheet", "2026-07-22T01:02:08Z", None, 403, "text/html", "failed_capture_review_only"),
    Capture("dorchester_groundbreaking", "dorchester-breakground", "https://www.dorchesterforbusiness.com/news/google_breaks_ground/", "2026-07-22T01:02:38Z", "2024-09-26", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("dorchester_active", "dorchester-active", "https://www.dorchesterforbusiness.com/news/google-expands-investment-in-dorchester-county/", "2026-07-22T01:02:38Z", "2025-10-13", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("google_south_carolina", "google-sc", "https://blog.google/company-news/inside-google/company-announcements/google-american-innovation-south-carolina/", "2026-07-22T01:02:39Z", "2025-10-13", 200, "text/html; charset=utf-8", "normalized"),
    Capture("groningen", "groningen", "https://blog.google/intl/nl-nl/google-nieuws/over-google/google-investeert-600-miljoen-in-een-nieuw-datacenter-in-groningen/", "2026-07-22T01:02:39Z", "2024-04-23", 200, "text/html; charset=utf-8", "normalized"),
    Capture("skien", "skien", "https://www.skien.kommune.no/by-og-naeringsutvikling/google-etablering-i-skien-kommune/", "2026-07-22T01:02:40Z", None, 200, "text/html; charset=utf-8", "normalized"),
    Capture("skien_timeline", "skien-timeline", "https://www.skien.kommune.no/by-og-naeringsutvikling/google-etablering-i-skien-kommune/tidslinje-hva-har-skjedd-fram-til-naa/", "2026-07-22T01:03:05Z", "2024-02-19", 200, "text/html; charset=utf-8", "review_only_boundary"),
    Capture("skien_forum", "skien-forum", "https://www.skien.kommune.no/media/b0ilznne/referat-plan-og-byggesaksforum-120424.pdf", "2026-07-22T01:04:41Z", "2024-04-12", 200, "application/pdf", "normalized"),
    Capture("elmina", "elmina", "https://www.mida.gov.my/mida-news/googles-hyperscale-data-centre-at-elmina-business-park-breaks-ground/", "2026-07-22T01:02:41Z", "2024-10-02", 200, "text/html; charset=UTF-8", "normalized"),
    Capture("farciennes", "farciennes", "https://www.farciennes.be/en-images/2024/pose-de-la-premiere-pierre-chez-google-05-avril", "2026-07-22T01:02:44Z", "2024-04-05", 200, "text/html;charset=utf-8", "normalized"),
    Capture("lagrange", "lagrange", "https://ted.cviog.uga.edu/FINANCIAL-DOCUMENTS/sites/default/files/budgetdoc/financial-report/city-lagrange-fy2025-financial-report.pdf", "2026-07-22T01:02:45Z", "2025-12-30", 200, "application/pdf", "normalized"),
    Capture("google_locations", "locations", "https://www.datacenters.google/locations/", "2026-07-22T01:02:46Z", None, 200, "text/html", "discovery_only"),
    Capture("project_spade", "spade", "https://www.projectspade-missouri.com/", "2026-07-22T01:02:47Z", None, 200, "text/html; charset=utf-8", "review_only"),
    Capture("michigan_city", "michigan-city", "https://www.michigancitydatacenter.com/", "2026-07-22T01:02:47Z", None, 200, "text/html; charset=utf-8", "review_only"),
    Capture("morgan_county", "morgan-county", "https://www.morgancountydatacenter.com/", "2026-07-22T01:02:48Z", None, 200, "text/html; charset=utf-8", "review_only"),
)
CAPTURE_BY_ID = {capture.capture_id: capture for capture in CAPTURES}


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    capture_id: str
    title: str
    publisher: str
    source_family: str
    kind: str
    excerpt: str
    factual_extract: Mapping[str, Any]


EVIDENCE = (
    EvidenceSpec("google-dorchester-groundbreaking-2024-09-26", "dorchester_groundbreaking", "Google breaks ground on two Dorchester County campuses", "Dorchester County Economic Development", "dorchester_county_economic_development", "government_record", "Dorchester County reports that Google broke ground on two new data-center campuses, at Pine Hill Business Campus and Winding Woods Commerce Park.", {"physical_status_as_reported": "Google broke ground on two separately named campuses.", "investment_context_not_normalized": "$2 billion stated for the two campuses."}),
    EvidenceSpec("google-dorchester-active-construction-2025-10-13", "dorchester_active", "Google expands investment in Dorchester County", "Dorchester County Economic Development", "dorchester_county_economic_development", "government_record", "Dorchester County says the two campus projects announced in 2024 are now under active construction.", {"physical_status_as_reported": "Both separately named 2024 campus projects were under active construction.", "identity_basis": "Names are bound by the 2024 county groundbreaking page."}),
    EvidenceSpec("google-south-carolina-continued-construction-2025-10-13", "google_south_carolina", "Google announces continued construction in Dorchester County", "Google", "google_company_blog", "company_disclosure", "Google says its South Carolina funding supports continued construction of two new Dorchester County sites.", {"physical_status_as_reported": "Continued construction of two new Dorchester County sites.", "corroboration_scope": "Corroborates construction and two-site count; county source supplies exact site names."}),
    EvidenceSpec("google-groningen-westpoort-construction-start-2024-04-23", "groningen", "Google starts construction of a new Groningen data center", "Google Nederland", "google_company_blog", "company_disclosure", "Google announces the start of construction of a new data center at Westpoort business park in Groningen.", {"physical_status_as_reported": "Start of construction at Westpoort business park, Groningen.", "investment_context_not_normalized": "EUR 600 million stated.", "identity_guardrail": "This Groningen Westpoort site is not Amsterdam Westpoort, Plus Ultra Groningen, NorthC Groningen, or Pure DC Amsterdam Westpoort."}),
    EvidenceSpec("google-skien-first-phase-announcement-observed-2026-07-22", "skien", "Google establishment in Skien municipality", "Skien kommune", "skien_municipality", "government_record", "Skien municipality says Google announced the first construction phase in February 2024 and activity around Gromstul has since been high.", {"physical_status_as_reported": "First phase announced and high activity around Gromstul.", "scope_guardrail": "Corroboration only; the dated forum minutes establish site preparation."}),
    EvidenceSpec("google-skien-gromstul-site-preparation-2024-04-12", "skien_forum", "Plan and building forum minutes: Gromstul", "Skien kommune", "skien_municipality", "government_record", "Municipal forum minutes say infrastructure to the site is being built, the plot is being prepared, and groundworks have commencement permission.", {"physical_status_as_reported": "Infrastructure to the site was being built and the plot prepared for construction; groundworks had commencement permission.", "power_context_not_normalized": "Minutes mention 100 MW-plus installations and a 240 MW concession; neither is normalized as data-center capacity or energy use.", "stage_scope": "Site preparation only; no building start, completion, commissioning, or operation is inferred."}),
    EvidenceSpec("google-elmina-business-park-groundbreaking-2024-10-02", "elmina", "Google data centre at Elmina Business Park breaks ground", "Malaysian Investment Development Authority", "mida_official_news", "government_record", "MIDA reports that Google's Elmina Business Park data centre broke ground on 2 October 2024 and was being built.", {"physical_status_as_reported": "Groundbreaking and being built at Elmina Business Park.", "type_guardrail": "The source's hyperscale wording remains evidence metadata and is not normalized as facility type."}),
    EvidenceSpec("google-farciennes-ecopole-first-stone-2024-04-05", "farciennes", "First stone laid for Google at Farciennes Ecopôle", "Commune de Farciennes", "farciennes_municipality", "government_record", "Farciennes municipality reports the first stone for the Google data center was laid at the Ecopôle on 5 April 2024.", {"physical_status_as_reported": "First stone laid at Farciennes Ecopôle.", "identity_guardrail": "Farciennes is distinct from Google's Saint-Ghislain GBL1 and its later building expansion."}),
    EvidenceSpec("google-lagrange-former-jindal-construction-2025-12-30", "lagrange", "City of LaGrange FY2025 annual comprehensive financial report", "City of LaGrange", "lagrange_city_financial_report", "government_record", "LaGrange says Google acquired the former Jindal Films facility and is constructing a large data center.", {"document_date": "2025-12-30", "physical_status_as_reported": "Google is constructing a large data center at the former Jindal Films facility.", "forecast_guardrail": "Expected operation in 2027 is a forecast and does not establish completion, commissioning, or operation."}),
)
EVIDENCE_BY_KEY = {evidence.key: evidence for evidence in EVIDENCE}


@dataclass(frozen=True)
class Site:
    slug: str
    country: str
    address: str
    campus_key: str
    project_key: str
    campus_name: str
    project_name: str
    evidence_keys: tuple[str, ...]
    primary_evidence_key: str
    as_of_date: str
    status: str
    method: str

    @property
    def filename(self) -> str:
        return f"curated-official-2026-07-22-google-{self.slug}-current-build.json"


DORCHESTER_EVIDENCE = (
    "google-dorchester-groundbreaking-2024-09-26",
    "google-dorchester-active-construction-2025-10-13",
    "google-south-carolina-continued-construction-2025-10-13",
)
SITES = (
    Site("pine-hill-ridgeville", "United States", "Pine Hill Business Campus, Ridgeville, Dorchester County, South Carolina, United States", "osm:way/1319701990", "osm:way/1319701990:development-project", "Google Pine Hill Business Campus", "Google Pine Hill Business Campus Development Project", DORCHESTER_EVIDENCE, "google-dorchester-active-construction-2025-10-13", "2025-10-13", "under_construction", "authoritative_physical_status_update"),
    Site("winding-woods-st-george", "United States", "Winding Woods Commerce Park, St. George, Dorchester County, South Carolina, United States", "osm:way/1288894119", "osm:way/1288894119:development-project", "Google Winding Woods Commerce Park Campus", "Google Winding Woods Commerce Park Development Project", DORCHESTER_EVIDENCE, "google-dorchester-active-construction-2025-10-13", "2025-10-13", "under_construction", "authoritative_physical_status_update"),
    Site("groningen-westpoort", "Netherlands", "Westpoort business park, Groningen municipality, Netherlands", "curated:google-groningen-westpoort-data-center", "curated:google-groningen-westpoort-data-center:2024-construction", "Google Groningen Westpoort Data Center", "Google Groningen Westpoort 2024 Construction Project", ("google-groningen-westpoort-construction-start-2024-04-23",), "google-groningen-westpoort-construction-start-2024-04-23", "2024-04-23", "under_construction", "authoritative_construction_start"),
    Site("skien-gromstul-first-phase", "Norway", "Gromstul, Skien municipality, Norway", "curated:google-skien-gromstul-data-center", "curated:google-skien-gromstul-data-center:first-phase-site-preparation", "Google Skien Gromstul Data Center", "Google Skien Gromstul First Phase Site Preparation", ("google-skien-first-phase-announcement-observed-2026-07-22", "google-skien-gromstul-site-preparation-2024-04-12"), "google-skien-gromstul-site-preparation-2024-04-12", "2024-04-12", "site_preparation", "authoritative_physical_status_update"),
    Site("elmina-business-park", "Malaysia", "Elmina Business Park, Selangor, Malaysia", "wikidata:Q136745002", "curated:google-elmina-business-park-data-center:2024-groundbreaking", "Google Data Center, Elmina Business Park", "Google Elmina Business Park 2024 Groundbreaking Project", ("google-elmina-business-park-groundbreaking-2024-10-02",), "google-elmina-business-park-groundbreaking-2024-10-02", "2024-10-02", "under_construction", "authoritative_construction_start"),
    Site("farciennes-ecopole", "Belgium", "Ecopôle, Farciennes, Wallonia, Belgium", "curated:google-farciennes-ecopole-data-center", "curated:google-farciennes-ecopole-data-center:2024-first-stone", "Google Farciennes Ecopôle Data Center", "Google Farciennes Ecopôle 2024 First-Stone Project", ("google-farciennes-ecopole-first-stone-2024-04-05",), "google-farciennes-ecopole-first-stone-2024-04-05", "2024-04-05", "under_construction", "authoritative_construction_start"),
    Site("lagrange-former-jindal-films", "United States", "Former Jindal Films facility, Pegasus Parkway, LaGrange, Georgia, United States", "curated:google-lagrange-former-jindal-films-data-center", "curated:google-lagrange-former-jindal-films-data-center:2025-construction", "Google LaGrange Former Jindal Films Data Center", "Google LaGrange Former Jindal Films 2025 Construction Project", ("google-lagrange-former-jindal-construction-2025-12-30",), "google-lagrange-former-jindal-construction-2025-12-30", "2025-12-30", "under_construction", "authoritative_physical_status_update"),
)

SOURCE_FILENAMES = tuple(site.filename for site in SITES)
SITE_BY_FILENAME = {site.filename: site for site in SITES}
CONTENT_FILES = (
    "README.md", "candidate-assessment.json", "retrieval-inventory.json",
    "rights-and-disposition.json", "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _evidence(spec: EvidenceSpec) -> dict[str, Any]:
    capture = CAPTURE_BY_ID[spec.capture_id]
    body = f"{capture.file_stem}.body"
    headers = f"{capture.file_stem}-headers.txt"
    body_bytes, body_sha = CAPTURE_FILE_PINS[body]
    header_bytes, header_sha = CAPTURE_FILE_PINS[headers]
    metadata = {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture.capture_id,
        "capture_method": "credential_free_curl_location_compressed",
        "requested_url": capture.url,
        "effective_url": capture.url,
        "request_credentials_supplied": False,
        "http_status": capture.http_status,
        "content_type": capture.content_type,
        "content_hash_scope": f"SHA-256 of the exact {body_bytes}-byte content-decoded credential-free public response body",
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": f"SHA-256 of the exact {header_bytes}-byte raw HTTP response-header capture",
        "capture_headers_sha256": header_sha,
        "status_semantics": "dated_last_observed_current_status_unknown",
        "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw bodies, headers, telemetry, and publisher media are not redistributed.",
        "normalization_guardrail": "No capacity, energy use, PUE, WUE, generation, facility type, operating model, workload, role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is normalized.",
        **spec.factual_extract,
    }
    return {
        "key": spec.key,
        "kind": spec.kind,
        "title": spec.title,
        "source_url": capture.url,
        "publisher": spec.publisher,
        "source_family": spec.source_family,
        "published_at": capture.published_at,
        "retrieved_at": capture.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": spec.publisher,
        "excerpt": spec.excerpt,
        "content_hash": body_sha,
        "metadata": metadata,
    }


def _entity(site: Site, *, project: bool) -> dict[str, Any]:
    return {
        "stable_key": site.project_key if project else site.campus_key,
        "name": site.project_name if project else site.campus_name,
        "country": site.country,
        "address": site.address,
        "roles": {},
        "coordinates": None,
        "geometry": None,
        "evidence_key": site.primary_evidence_key,
        "as_of_date": site.as_of_date,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _source(site: Site) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": [_evidence(EVIDENCE_BY_KEY[key]) for key in site.evidence_keys],
        "campus": _entity(site, project=False),
        "project": _entity(site, project=True),
        "lifecycle": [{
            "entity": "project", "value": site.status,
            "evidence_key": site.primary_evidence_key, "as_of_date": site.as_of_date,
            "method": site.method, "confidence": 0.99,
        }],
        "operating_models": [], "workloads": [], "capacities": [],
    }


def expected_source_documents() -> dict[str, dict[str, Any]]:
    return {site.filename: _source(site) for site in SITES}


def _source_records(documents: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for name in SOURCE_FILENAMES:
        document = documents[name]
        payload = _canonical(document)
        rows.append({
            "path": f"sources/{name}", "bytes": len(payload),
            "sha256": _sha256_bytes(payload), "schema_version": "1.1",
            "country": document["campus"]["country"],
            "campus_stable_key": document["campus"]["stable_key"],
            "project_stable_key": document["project"]["stable_key"],
            "evidence_records": len(document["evidence"]), "lifecycle_observations": 1,
            "operating_model_observations": 0, "workload_observations": 0,
            "capacity_estimates": 0, "coordinates_present": 0,
            "geometry_present": 0,
            "disposition": "seed_eligible_direct_authoritative_physical_update",
            "seed_eligible": True, "seeded": False,
        })
    return rows


def _planned_keys(documents: Mapping[str, Mapping[str, Any]]) -> tuple[set[str], set[str]]:
    stable = {document[entity]["stable_key"] for document in documents.values() for entity in ("campus", "project")}
    evidence = {row["key"] for document in documents.values() for row in document["evidence"]}
    return stable, evidence


def _collision_witness(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    for path, pin in {**V89_PINS, **MASTER_PINS, GLOBAL_ENTITIES: GLOBAL_ENTITIES_PIN}.items():
        _pin(path, pin)
    if tree_digest(V89_RELEASE) != V89_TREE_SHA256:
        raise RuntimeError("v89 release tree differs")
    if tree_digest(MASTER_RELEASE) != MASTER_TREE_SHA256:
        raise RuntimeError("master v31 tree differs")
    definition = json.loads(V89_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V89_INPUT_COUNT:
        raise RuntimeError("v89 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V89_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned Google stable key collides with v89")
    source_inputs = json.loads((V89_RELEASE / "source_inputs.json").read_text(encoding="utf-8")).get("sources")
    base_evidence = {
        key for row in source_inputs or [] if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Google evidence key collides with v89")

    with GLOBAL_ENTITIES.open(encoding="utf-8", newline="") as stream:
        global_rows = {row["stable_key"]: row for row in csv.DictReader(stream)}
    exact_master_keys = {
        "osm:way/1288894119", "osm:way/1288894119:development-project",
        "osm:way/1319701990", "osm:way/1319701990:development-project",
        "wikidata:Q136745002",
    }
    expected_names = {
        "osm:way/1288894119": "Google datacenter",
        "osm:way/1288894119:development-project": "Google datacenter development project",
        "osm:way/1319701990": "Dorchester County Google Datacenter",
        "osm:way/1319701990:development-project": "Dorchester County Google Datacenter development project",
        "wikidata:Q136745002": "Google Data Center, Elmina Business Park",
    }
    if {key: global_rows.get(key, {}).get("name") for key in exact_master_keys} != expected_names:
        raise RuntimeError("global-open exact Google identity witness differs")
    with MASTER_CSV.open(encoding="utf-8", newline="") as stream:
        master_rows = list(csv.DictReader(stream))
    exact_names = {
        value for key, value in expected_names.items() if key != "wikidata:Q136745002"
    }
    master_exact = {
        row["name"] for row in master_rows
        if row["name"] in exact_names and row["review_only"] == "false"
    }
    if master_exact != exact_names:
        raise RuntimeError("master exact Google identity witness differs")
    distinct_global = {
        key: global_rows.get(key, {}).get("name")
        for key in (
            "osm:way/1392760295", "osm:way/1081886104",
            "wikidata:Q139760640", "osm:way/143759902",
        )
    }
    if distinct_global != {
        "osm:way/1392760295": "Plus Ultra Groningen",
        "osm:way/1081886104": "NorthC Data center Groningen",
        "wikidata:Q139760640": "Data center Westpoort",
        "osm:way/143759902": "Google Data Center GBL1",
    }:
        raise RuntimeError("distinct Google locality collision witness differs")
    pure = json.loads(
        (SOURCES_ROOT / "curated-official-2026-07-21-pure-dc-ams01-amsterdam-westpoort-current-build.json").read_text(encoding="utf-8")
    )
    if pure.get("campus", {}).get("stable_key") != "curated:pure-dc-ams01-amsterdam-westpoort-campus":
        raise RuntimeError("Pure DC Amsterdam Westpoort witness differs")
    return {
        "v89_selected_input_count": len(selected),
        "v89_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v89_stable_key_collisions": [],
        "exact_v89_evidence_key_collisions": [],
        "exact_master_identity_keys_reused": sorted(exact_master_keys),
        "master_collision_resolution": "The two Dorchester campus/project pairs and Elmina campus reuse exact global-open-v3 stable keys; no source coordinate or geometry is inherited.",
        "distinct_locality_boundary": "Google Groningen Westpoort remains distinct from Plus Ultra Groningen, NorthC Groningen, Amsterdam Westpoort identities, and Pure DC Amsterdam Westpoort; Farciennes remains distinct from Saint-Ghislain GBL1.",
        "structural_candidate_boundary": "Anonymous or non-data-center structural candidates do not establish identity and are not merged.",
    }


def _candidate_assessment(recorded_at: str) -> dict[str, Any]:
    candidates = [{
        "candidate_id": site.slug,
        "decision": "seed_eligible_direct_authoritative_physical_update",
        "source_paths": [f"sources/{site.filename}"],
        "campus_stable_key": site.campus_key,
        "project_stable_key": site.project_key,
        "lifecycle": {"status": site.status, "as_of_date": site.as_of_date, "method": site.method},
        "withheld": ["current-status extrapolation", "capacity or energy", "PUE or WUE", "facility type or workload", "standardized role", "coordinates or geometry"],
    } for site in SITES]
    candidates.extend((
        {
            "candidate_id": "skien-second-data-center",
            "decision": "review_only_groundworks_permit_application",
            "source_paths": [], "seed_eligible": False,
            "capture_id": "skien_timeline",
            "official_factual_extract": "The August 2025 timeline entry says a framework-permit application was submitted for groundworks for a second data center south of the first.",
            "boundary": "A permit application is not physical start evidence and does not create a second entity or lifecycle claim.",
        },
        {
            "candidate_id": "project-spade-montgomery-county-missouri",
            "decision": "review_only_future_construction_forecast",
            "source_paths": [], "seed_eligible": False,
            "capture_id": "project_spade",
            "official_factual_extract": "Construction is anticipated to begin in late 2026.",
            "boundary": "A future forecast is not a physical start observation.",
        },
        {
            "candidate_id": "michigan-city-project-maize",
            "decision": "review_only_ambiguous_ongoing_development",
            "source_paths": [], "seed_eligible": False,
            "capture_id": "michigan_city",
            "official_factual_extract": "Google says it acquired an ongoing data-center development known as Project Maize.",
            "boundary": "Ongoing development does not cleanly establish an exact physical construction stage or start date.",
        },
        {
            "candidate_id": "morgan-county-indiana",
            "decision": "review_only_future_groundbreaking",
            "source_paths": [], "seed_eligible": False,
            "capture_id": "morgan_county",
            "official_factual_extract": "The site says Google is set to break ground in 2026.",
            "boundary": "Future groundbreaking wording is not a physical start observation.",
        },
    ))
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "candidate_count": 11, "seed_eligible_candidate_count": 7,
        "seed_eligible_source_record_count": 7, "review_only_count": 4,
        "regional_completeness_claimed": False, "candidates": candidates,
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 14,
        "failed_http_body_captures": 1,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [{
            "capture_id": capture.capture_id,
            "requested_url": capture.url,
            "effective_url": capture.url,
            "retrieved_at": capture.retrieved_at,
            "body": {"path": f"{capture.file_stem}.body", "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][0], "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}.body"][1], "retained_in_artifact": False, "moved_to_trash": True},
            "headers": {"path": f"{capture.file_stem}-headers.txt", "bytes": CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"][0], "sha256": CAPTURE_FILE_PINS[f"{capture.file_stem}-headers.txt"][1], "retained_in_artifact": False, "moved_to_trash": True},
            "http_status": capture.http_status,
            "content_type": capture.content_type,
            "request_credentials_supplied": False,
            "claim_use": capture.use,
        } for capture in CAPTURES],
        "complete_private_file_inventory": [
            {"path": name, "bytes": pin[0], "sha256": pin[1]}
            for name, pin in sorted(CAPTURE_FILE_PINS.items())
        ],
    }


def _file_tree(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes((json.dumps(rows, indent=2, sort_keys=True) + "\n").encode())


def _artifact_documents(recorded_at: str, source_documents: Mapping[str, Mapping[str, Any]]) -> dict[str, bytes]:
    collision = _collision_witness(source_documents)
    source_records = _source_records(source_documents)
    totals = {
        "candidate_assessments": 11, "source_records": 7,
        "seed_eligible_candidates": 7, "seed_eligible_source_records": 7,
        "review_only_candidates": 4, "distinct_campuses_in_source_records": 7,
        "projects": 7, "distinct_entities_in_source_records": 14,
        "new_entities_against_v89": 14,
        "exact_global_open_identity_keys_reused": 5,
        "source_document_entity_snapshots": 14,
        "unique_imported_entity_snapshots": 14,
        "source_document_evidence_references": 12,
        "unique_evidence_records": 9, "lifecycle_observations": 7,
        "operating_model_observations": 0, "workload_observations": 0,
        "capacity_estimates": 0, "coordinates_present": 0, "geometry_present": 0,
    }
    readme = f"""# Google official current-build gap tranche

This immutable artifact closes fifteen credential-free official captures and publishes seven named, seed-eligible campus/project records. The two Dorchester sites and Elmina reuse five exact global-open-v3 stable keys after pinned collision audits, but inherit no coordinates or geometry. Groningen Westpoort and Farciennes are kept distinct from similarly named or nearby existing records. A second Skien data center, Project Spade, Michigan City, and Morgan County remain review-only because their captured wording does not establish a clean physical start for the exact project.

No capacity, energy use, generation, PUE, WUE, facility type, operating model, workload, standardized role, current-status extrapolation, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added. Forecast completion dates remain metadata only. All normalized statuses are dated last-observed facts whose current status is unknown.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at, "research_date": "2026-07-22",
        "regional_completeness_claimed": False,
        "source_records": source_records, "totals": totals,
        "frozen_v89_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v89.json", "bytes": V89_PINS[V89_DEFINITION][0], "sha256": V89_PINS[V89_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v89/manifest.json", "bytes": V89_PINS[V89_MANIFEST][0], "sha256": V89_PINS[V89_MANIFEST][1]},
            "release_entities": {"path": "releases/2026-07-21-open-seed-v89/entities.csv", "bytes": V89_PINS[V89_ENTITIES][0], "sha256": V89_PINS[V89_ENTITIES][1]},
            "release_tree_sha256": V89_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False, "open_seed_v89_mutated": False,
            "release_integration": "none", "construction_master_integration": "none",
            "map_integration": "none", "federation_integration": "none",
            "coverage_integration": "none", "review_integration": "none",
        },
        "publication_contract": {
            "version": 1, "all_source_and_artifact_bytes_staged_before_recorded_at": True,
            "final_paths_absent_before_recorded_at": True,
            "publication_waited_until_recorded_at": True, "no_replace_promotion": True,
            "identity_checked_rollback_on_late_collision": True,
            "raw_capture_moved_to_trash_after_source_publication": True,
            "source_file_mode": "0444", "artifact_directory_mode": "0555",
            "artifact_file_mode": "0444",
        },
    }
    rights = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-source-rights-disposition-v3",
        "research_date": "2026-07-22", "recorded_at": recorded_at,
        "source_rights": "All captured official response bodies are treated as all-rights-reserved; no redistribution license was relied on.",
        "artifact_is_hash_only": True, "raw_capture_redistributed": False,
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
    }
    return {
        "README.md": readme.encode(),
        "candidate-assessment.json": _canonical(_candidate_assessment(recorded_at)),
        "retrieval-inventory.json": _canonical(_capture_inventory(recorded_at)),
        "rights-and-disposition.json": _canonical(rights),
        "source-snapshot.json": _canonical(snapshot),
    }


def _validate_sources(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    expected = expected_source_documents()
    if set(paths) != set(SOURCE_FILENAMES):
        raise RuntimeError("source path inventory differs")
    for name in SOURCE_FILENAMES:
        path = paths[name]
        if path.is_symlink() or not path.is_file() or path.read_bytes() != _canonical(expected[name]) or stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise RuntimeError(f"curated source differs: {name}")
    documents = list(expected.values())
    if any(document[entity][field] is not None for document in documents for entity in ("campus", "project") for field in ("coordinates", "geometry")):
        raise RuntimeError("source invented coordinates or geometry")
    if any(document[entity]["roles"] for document in documents for entity in ("campus", "project")):
        raise RuntimeError("source invented roles")
    if any(document[collection] for document in documents for collection in ("operating_models", "workloads", "capacities")):
        raise RuntimeError("source invented normalized non-lifecycle claims")
    lifecycle = {(document["project"]["stable_key"], row["value"], row["as_of_date"], row["method"]) for document in documents for row in document["lifecycle"]}
    expected_lifecycle = {(site.project_key, site.status, site.as_of_date, site.method) for site in SITES}
    if lifecycle != expected_lifecycle:
        raise RuntimeError("lifecycle contract differs")
    return _source_records(expected)


def _validate_source_collisions() -> None:
    planned = expected_source_documents()
    _collision_witness(planned)
    planned_stable, planned_evidence = _planned_keys(planned)
    source_names = set(SOURCE_FILENAMES)
    collisions: dict[str, Any] = {}
    for path in SOURCES_ROOT.glob("*.json"):
        if path.name in source_names:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(document, dict):
            continue
        stable = {row.get("stable_key") for key in ("campus", "facility", "building", "project") if isinstance((row := document.get(key)), dict)}
        evidence = {row.get("key") for row in document.get("evidence", []) if isinstance(row, dict)}
        if planned_stable & stable or planned_evidence & evidence:
            collisions[str(path.relative_to(ROOT))] = {
                "stable_keys": sorted(planned_stable & stable),
                "evidence_keys": sorted(planned_evidence & evidence),
            }
    if collisions:
        raise RuntimeError(f"source collision detected: {collisions!r}")


def _validate_capture_directory(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("capture directory absent or unsafe")
    entries = list(directory.iterdir())
    if len(entries) != CAPTURE_FILE_COUNT or set(CAPTURE_FILE_PINS) != {entry.name for entry in entries} or any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise RuntimeError("capture directory closed set differs")
    if sum(entry.stat().st_size for entry in entries) != CAPTURE_TOTAL_BYTES or tree_digest(directory) != CAPTURE_TREE_SHA256:
        raise RuntimeError("capture directory aggregate differs")
    for name, pin in CAPTURE_FILE_PINS.items():
        _pin(directory / name, pin)


def _offline_import(paths: Mapping[str, Path], recorded_at: str) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="google-current-build-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 14, "entity_snapshots": 14, "evidence": 9, "lifecycle_observations": 7, "operating_model_observations": 0, "workload_observations": 0, "capacity_estimates": 0}
        if counts != expected:
            raise RuntimeError(f"offline import counts differ: {counts!r}")
        return counts


def _source_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / name for name in SOURCE_FILENAMES}


def validate_artifact(path: Path = ARTIFACT, *, source_paths: Mapping[str, Path] | None = None, require_live: bool = True, wall_clock: datetime | None = None) -> dict[str, Any]:
    paths = source_paths or _source_paths(SOURCES_ROOT)
    source_records = _validate_sources(paths)
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o555:
        raise RuntimeError("artifact must be a frozen ordinary directory")
    entries = {entry.name: entry for entry in path.iterdir()}
    if set(entries) != CLOSED_FILES or any(entry.is_symlink() or not entry.is_file() or stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries.values()):
        raise RuntimeError("artifact closed frozen set differs")
    manifest_raw = entries["manifest.json"].read_bytes()
    manifest = json.loads(manifest_raw)
    if manifest_raw != _canonical(manifest) or manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 11 or manifest.get("curated_source_records") != 7 or manifest.get("seed_eligible_candidates") != 7 or manifest.get("review_only_candidates") != 4 or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
        raise RuntimeError("manifest contract differs")
    for row in manifest["files"]:
        payload = entries[row["path"]].read_bytes()
        if (len(payload), _sha256_bytes(payload)) != (row["bytes"], row["sha256"]):
            raise RuntimeError(f"manifest file pin differs: {row['path']}")
    if entries["manifest.sha256"].read_text(encoding="utf-8") != f"{_sha256_bytes(manifest_raw)}  manifest.json\n":
        raise RuntimeError("manifest checksum differs")
    expected = _artifact_documents(manifest["recorded_at"], expected_source_documents())
    for name in CONTENT_FILES:
        if entries[name].read_bytes() != expected[name]:
            raise RuntimeError(f"artifact content differs: {name}")
    snapshot = json.loads(entries["source-snapshot.json"].read_text(encoding="utf-8"))
    if snapshot["source_records"] != source_records:
        raise RuntimeError("artifact source pins differ")
    target = _instant(manifest["recorded_at"])
    now = wall_clock or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None or (require_live and now.astimezone(UTC) < target):
        raise RuntimeError("artifact recorded_at is not live")
    if any(_instant(capture.retrieved_at) > target for capture in CAPTURES):
        raise RuntimeError("capture retrieval post-dates recorded_at")
    replay = [_offline_import(paths, manifest["recorded_at"]) for _ in range(2)]
    if replay[0] != replay[1]:
        raise RuntimeError("offline replay differs")
    return manifest


def _write_source_stage(stage: Path, documents: Mapping[str, Mapping[str, Any]]) -> None:
    for name in SOURCE_FILENAMES:
        target = stage / name
        target.write_bytes(_canonical(documents[name]))
        target.chmod(0o444)
        _fsync_regular(target)
    _fsync_directory(stage)


def _write_artifact_stage(stage: Path, recorded_at: str, documents: Mapping[str, Mapping[str, Any]]) -> None:
    payloads = _artifact_documents(recorded_at, documents)
    for name in CONTENT_FILES:
        target = stage / name
        target.write_bytes(payloads[name])
        target.chmod(0o444)
        _fsync_regular(target)
    rows = [{"bytes": (stage / name).stat().st_size, "path": name, "sha256": _sha256(stage / name)} for name in CONTENT_FILES]
    manifest = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-artifact-manifest-v3",
        "recorded_at": recorded_at, "files": rows, "tree_sha256": _file_tree(rows),
        "closed_file_set": sorted(CLOSED_FILES), "candidate_assessments": 11,
        "curated_source_records": 7, "seed_eligible_candidates": 7,
        "seed_eligible_source_records": 7, "review_only_candidates": 4,
        "successful_http_200_body_captures": 14,
        "raw_capture_redistributed": False,
        "raw_capture_directory_moved_intact_to_trash": True,
        "raw_capture_moved_after_source_publication": True,
        "regional_completeness_claimed": False,
        "open_seed_successor_created": False, "release_integration": "none",
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


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RuntimeError("active Google source publication lock exists") from error
    os.write(descriptor, f"pid={os.getpid()}\n".encode())
    os.fsync(descriptor)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    try:
        yield
    finally:
        os.close(descriptor)
        if PUBLICATION_LOCK.exists():
            current = PUBLICATION_LOCK.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != identity:
                raise RuntimeError("refusing substituted lock cleanup")
            PUBLICATION_LOCK.unlink()


@dataclass(frozen=True)
class _Prepared:
    source_stage: Path
    artifact_stage: Path
    recorded_at: str


def _prepare(recorded_at: str) -> _Prepared:
    if any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES) or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise RuntimeError("Google source final-path collision")
    _validate_source_collisions()
    capture = resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".google-current-build-sources.", dir=SOURCES_ROOT))
    artifact_stage = Path(tempfile.mkdtemp(prefix=f".{ARTIFACT_ID}.", dir=ARTIFACT_ROOT))
    try:
        _write_source_stage(source_stage, documents)
        _write_artifact_stage(artifact_stage, recorded_at, documents)
        validate_artifact(artifact_stage, source_paths=_source_paths(source_stage), require_live=False, wall_clock=_instant(recorded_at))
        return _Prepared(source_stage, artifact_stage, recorded_at)
    except Exception:
        if source_stage.exists():
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            artifact_stage.chmod(0o700)
            shutil.rmtree(artifact_stage)
        raise


def _publish(prepared: _Prepared) -> None:
    target = _instant(prepared.recorded_at)
    while datetime.now(UTC) < target:
        time.sleep(min(0.25, (target - datetime.now(UTC)).total_seconds()))
    if any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES) or ARTIFACT.exists() or ARTIFACT.is_symlink():
        raise RuntimeError("late Google source final-path collision")
    promoted: list[tuple[Path, Path]] = []
    try:
        for name in SOURCE_FILENAMES:
            staged, final = prepared.source_stage / name, SOURCES_ROOT / name
            _promote_noreplace(staged, final)
            promoted.append((final, staged))
        _promote_noreplace(prepared.artifact_stage, ARTIFACT)
        promoted.append((ARTIFACT, prepared.artifact_stage))
    except BaseException as error:
        for final, staged in reversed(promoted):
            try:
                _promote_noreplace(final, staged)
            except Exception as rollback_error:
                error.add_note(f"rollback failed for {final}: {rollback_error}")
        raise


def _move_capture_to_trash() -> None:
    if CAPTURE_ORIGIN.exists() and CAPTURE_TRASH.exists():
        raise RuntimeError("both raw capture origin and Trash destination exist")
    if CAPTURE_ORIGIN.exists():
        _validate_capture_directory(CAPTURE_ORIGIN)
        _promote_noreplace(CAPTURE_ORIGIN, CAPTURE_TRASH)
    _validate_capture_directory(resolve_external_capture(CAPTURE_ORIGIN, CAPTURE_TRASH))


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 7, "status": "existing-identical"}
    if ARTIFACT.exists() or ARTIFACT.is_symlink() or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES):
        raise RuntimeError("partial Google source final-path collision")
    target = _instant(recorded_at) if recorded_at else datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=45)
    if datetime.now(UTC) >= target:
        raise RuntimeError("recorded_at must be future before staging")
    timestamp = target.isoformat(timespec="seconds").replace("+00:00", "Z")
    with _publication_lock():
        prepared = _prepare(timestamp)
        _publish(prepared)
        _move_capture_to_trash()
        manifest = validate_artifact()
        if any(prepared.source_stage.iterdir()):
            raise RuntimeError("source stage not empty after publication")
        prepared.source_stage.rmdir()
    return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 7, "status": "published"}


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
