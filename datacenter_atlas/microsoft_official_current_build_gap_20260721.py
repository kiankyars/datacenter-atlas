"""Publish a hash-bound Microsoft official current-build source tranche.

Nine named projects are seed eligible. Donnacona remains review-only because
schema 1.1 cannot faithfully represent a completed building while internal and
substation work continues. Raw official response bytes are all-rights-reserved
and are represented only by exact hashes and compact factual extracts.
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

from .curated_v11 import CuratedOfficialSourceAdapterV11
from .database import initialize
from . import global_official_current_build_gap_20260721 as prior
from .open_seed_v56 import tree_digest
from .service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_ROOT = ROOT / "sources"
ARTIFACT_ROOT = ROOT / "source_artifacts"
ARTIFACT_ID = "microsoft-official-current-build-gap-2026-07-21-v1"
ARTIFACT = ARTIFACT_ROOT / ARTIFACT_ID
PUBLICATION_LOCK = ROOT / ".microsoft-official-current-build-gap.lock"

CAPTURE_ORIGIN = Path("/private/tmp/dc-microsoft-current-build-20260721.rX1ieK")
CAPTURE_TRASH = Path("/Users/kian/.Trash/dc-microsoft-current-build-20260721.rX1ieK")
CAPTURE_FILE_COUNT = 20
CAPTURE_TOTAL_BYTES = 1_907_997
CAPTURE_TREE_SHA256 = "2c489a544206926e42b8626156a6993424d38664076b15b479e82043b1d217a6"

V88_DEFINITION = SOURCES_ROOT / "open-seed-2026-07-21-v88.json"
V88_RELEASE = ROOT / "releases/2026-07-21-open-seed-v88"
V88_MANIFEST = V88_RELEASE / "manifest.json"
V88_ENTITIES = V88_RELEASE / "entities.csv"
V88_PINS = {
    V88_DEFINITION: (
        104_159,
        "7267e71dc26581eb8f62bf11525475c3ccc732494c4cca0cea58c0f30b0232da",
    ),
    V88_MANIFEST: (
        15_706,
        "63bdeac96b5f3cebac092a63cff40de2d928d0643d42fe5b041fd649fc9955e0",
    ),
    V88_ENTITIES: (
        992_569,
        "e06ae785ad89b614257e0276eec1816985b26c2cdf511594c83c3f5753706218",
    ),
}
V88_TREE_SHA256 = "aae34cbd2b8111a498ef529b08d0be6937c837b70025bdba6c097735b606073e"
V88_INPUT_COUNT = 461

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
    "bergheim-headers.txt": (1_776, "4cfcd088935c1b309692545eaf6774ef42b9307e88a987531833246a4efa0e61"),
    "bergheim.body": (121_170, "219285463ed1658418ee4e34af8ecca48fb91db7bbac960815240a54cfd71919"),
    "bornasco-headers.txt": (1_058, "ca2635816fb33625269e812c3cb10a15a14bcb88b641473aa8732e3cebfc161c"),
    "bornasco.body": (195_803, "e2be3a616703275d4c0866033590f9f393b3741e873fbc98b061b4e611dd17fc"),
    "county-road-381-headers.txt": (1_058, "32bbeba3dfead11babf7739ae4a0b48068500ced6e1dfa07634110a28d6a0be1"),
    "county-road-381.body": (206_139, "efe2aef1f3126f3a3b61a916bd77442593d62aec04a609b50c36a0351e0494f1"),
    "donnacona-headers.txt": (1_058, "a104efaee9e2ca7268df7b062e161f47c80027dc1764a973a9a7d45dc12b14e4"),
    "donnacona.body": (197_317, "8754b32780764a524e9e0c192b394f7273117cf362e42aca45ab2f7cf4045831"),
    "ginger-east-headers.txt": (1_057, "f5a6ccb133023b9a775ff5652874ac706dab186cf6ee27c7bc7d5cf3cbade9dc"),
    "ginger-east.body": (194_547, "02d928e34144c65901a3033fc1da0c5ed7ee8c412b8b4005185299dbaf91edb0"),
    "ginger-west-headers.txt": (1_058, "50b07195ede84ace8c8e224496b891cb7794ff7e59bc43e7e401af2964aed09e"),
    "ginger-west.body": (194_602, "2ec099155f8d2e4ee06772346eda7ade566fbd517482b0f1cc4f84f631a181bf"),
    "hr-ranch-headers.txt": (1_058, "179cd86a709d1a645f8beb5d1036c12185275ea76c10914e89d19db724e8f7ad"),
    "hr-ranch.body": (193_607, "341e36428b4ca220f6eb0fe2b1bfe615a0e18fd9bcabc760529654d673ee6591"),
    "lancienne-lorette-headers.txt": (1_058, "2a4c4d9b5c0e16c55270e7c40ea0b24cf085ef9ee699f6f0bfb86947c34346b6"),
    "lancienne-lorette.body": (196_970, "0fa687a037c39b71ee0327edbcab7a009446835338f7e9e981f3f3f20b8c688d"),
    "levis-headers.txt": (1_058, "e1d2ece18d268955a2491adcc44510e08486665be1084be37a27b3ca29398eb0"),
    "levis.body": (199_029, "dc4f923a7cb0d00fbc4f745946d2e1fa4429e947ca9927a76506672008beb1a0"),
    "lyle-creek-headers.txt": (1_058, "8773f30afeaf7e1dd252c6457749bac0f3134cbcea39b4833c182d8e89008854"),
    "lyle-creek.body": (197_516, "159aea8b6ba5a8d7a8fef6c25dfdcc32624e5d726e08051f4f31ce045e5c5ad5"),
}


@dataclass(frozen=True)
class Site:
    slug: str
    country: str
    address: str
    campus_key: str
    project_key: str
    campus_name: str
    project_name: str
    evidence_key: str
    url: str
    published_at: str
    retrieved_at: str
    as_of_date: str
    status: str
    method: str
    excerpt: str
    factual_extract: Mapping[str, Any]
    source_family: str = "microsoft_local_project_updates"
    publisher: str = "Microsoft"

    @property
    def filename(self) -> str:
        return f"curated-official-2026-07-21-microsoft-{self.slug}-current-build.json"


SITES = (
    Site(
        "bornasco-via-olivetti", "Italy",
        "Via Olivetti (formerly Via Rimembranze), near La Fornace, Bornasco (PV), Italy",
        "curated:microsoft-bornasco-via-olivetti-data-center",
        "curated:microsoft-bornasco-via-olivetti-data-center:current-build",
        "Microsoft Bornasco Via Olivetti Data Center",
        "Microsoft Bornasco Via Olivetti Current Build",
        "microsoft-bornasco-via-olivetti-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/bornasco-datacenter-construction-update/",
        "2026-02-03", "2026-07-22T00:44:36Z", "2026-02-03",
        "site_preparation", "authoritative_physical_status_update",
        "Microsoft says urban-development work is active at its Via Olivetti Bornasco site.",
        {
            "date_published": "2026-02-03T05:31:47+00:00",
            "date_modified": "2026-02-03T05:31:47+00:00",
            "physical_status_as_reported": "Primary and secondary urban-development activities began September 15, 2025; current work includes excavation, grading, utilities, access roads, and land preparation.",
            "stage_scope": "Site preparation only; no building start, foundation, shell, completion, commissioning, or operation is inferred.",
        },
    ),
    Site(
        "bergheim-first-cluster-facility", "Germany",
        "Bergheim, North Rhine-Westphalia, Germany",
        "curated:microsoft-bergheim-first-cluster-data-center",
        "curated:microsoft-bergheim-first-cluster-data-center:2026-groundbreaking-current-build",
        "Microsoft Bergheim First Cluster Data Center",
        "Microsoft Bergheim First Cluster Data Center Groundbreaking",
        "microsoft-bergheim-first-cluster-current-build-captured-2026-07-21",
        "https://news.microsoft.com/source/emea/2026/03/spatenstich-fuer-rechenzentrums-cluster-in-nordrhein-westfalen-microsoft-staerkt-die-digitale-infrastruktur-fuer-deutschlands-ki-zukunft/?lang=de",
        "2026-03-12", "2026-07-22T00:44:37Z", "2026-03-12",
        "under_construction", "authoritative_construction_start",
        "Microsoft reports the March 12 groundbreaking for the first data center in its regional cluster at Bergheim.",
        {
            "date_published": "2026-03-12T13:56:40+00:00",
            "date_modified": "2026-03-17T15:02:33+00:00",
            "physical_status_as_reported": "Groundbreaking in Bergheim for the first data center of the regional cluster.",
            "scope_guardrail": "Bedburg was permitted and said to start shortly; Elsdorf is future context. Neither becomes a source record or lifecycle claim.",
        },
        "microsoft_official_news",
        "Microsoft Deutschland",
    ),
    Site(
        "hr-ranch-road-cheyenne", "United States",
        "HR Ranch Road, greater Cheyenne, Wyoming, United States",
        "curated:microsoft-hr-ranch-road-cheyenne-data-center",
        "curated:microsoft-hr-ranch-road-cheyenne-data-center:current-build",
        "Microsoft HR Ranch Road Data Center",
        "Microsoft HR Ranch Road Current Build",
        "microsoft-hr-ranch-road-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/hr-ranch-road-datacenter-construction/",
        "2025-08-14", "2026-07-22T00:44:37Z", "2025-08-14",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft says it is building a data center on HR Ranch Road in greater Cheyenne.",
        {
            "date_published": "2025-08-14T16:45:52+00:00",
            "date_modified": "2025-08-19T20:34:28+00:00",
            "physical_status_as_reported": "Microsoft is building; JE Dunn is the general contractor and heavy earthwork was anticipated July through November 2025.",
            "freshness_guardrail": "The early-2026 completion target is a forecast, not a completion or current-operation observation.",
        },
    ),
    Site(
        "county-road-381-san-antonio", "United States",
        "County Road 381, San Antonio, Texas, United States",
        "curated:microsoft-county-road-381-san-antonio-data-center",
        "curated:microsoft-county-road-381-san-antonio-data-center:current-build",
        "Microsoft County Road 381 Data Center",
        "Microsoft County Road 381 Current Build",
        "microsoft-county-road-381-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/county-road-381-datacenter-construction-update/",
        "2025-12-05", "2026-07-22T00:44:37Z", "2025-11-30",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft's November 2025 update says construction continues on County Road 381.",
        {
            "date_published": "2025-08-05T04:39:40+00:00",
            "date_modified": "2025-12-05T06:30:29+00:00",
            "physical_status_as_reported": "Construction work continues along County Road 381.",
            "month_end_as_of_basis": "The update gives November 2025 month precision; month-end does not imply an exact observation day.",
            "forecast_guardrail": "The winter-2028 schedule creates no later status, completion, commissioning, or operation observation.",
        },
    ),
    Site(
        "ginger-west-des-moines", "United States",
        "Greater Des Moines, Iowa, United States",
        "curated:microsoft-ginger-west-des-moines-data-center",
        "curated:microsoft-ginger-west-des-moines-data-center:current-build",
        "Microsoft Ginger West Data Center",
        "Microsoft Ginger West Current Build",
        "microsoft-ginger-west-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/ginger-west-datacenter-construction-update/",
        "2026-04-28", "2026-07-22T00:44:37Z", "2026-04-28",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft says it is building the separately named Ginger West data center in greater Des Moines.",
        {
            "date_published": "2025-01-08T19:30:43+00:00",
            "date_modified": "2026-04-28T17:56:40+00:00",
            "physical_status_as_reported": "Microsoft is building; Turner Construction is the general contractor.",
            "identity_guardrail": "Ginger West remains separate from Ginger East despite a shared broad locality.",
            "forecast_guardrail": "Summer 2028 is a construction-completion estimate and does not establish operation.",
        },
    ),
    Site(
        "ginger-east-des-moines", "United States",
        "Greater Des Moines, Iowa, United States",
        "curated:microsoft-ginger-east-des-moines-data-center",
        "curated:microsoft-ginger-east-des-moines-data-center:current-build",
        "Microsoft Ginger East Data Center",
        "Microsoft Ginger East Current Build",
        "microsoft-ginger-east-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/ginger-east-datacenter-construction-update/",
        "2026-03-23", "2026-07-22T00:44:37Z", "2026-03-23",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft says it is building the separately named Ginger East data center in greater Des Moines.",
        {
            "date_published": "2025-01-08T19:21:09+00:00",
            "date_modified": "2026-03-23T17:39:07+00:00",
            "physical_status_as_reported": "Microsoft is building; Weitz Construction is the general contractor.",
            "identity_guardrail": "Ginger East remains separate from Ginger West despite a shared broad locality.",
            "forecast_guardrail": "Mid-2028 is a construction-completion estimate and does not establish operation.",
        },
    ),
    Site(
        "lancienne-lorette", "Canada", "L’Ancienne-Lorette, Quebec, Canada",
        "osm:way/1383040176", "osm:way/1383040176:development-project",
        "Microsoft L’Ancienne-Lorette Data Center",
        "Microsoft L’Ancienne-Lorette Development Project",
        "microsoft-lancienne-lorette-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/lancienne-lorette-datacentre-construction-update/",
        "2026-05-04", "2026-07-22T00:44:38Z", "2026-04-30",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft's April 2026 update says groundwork continues and substation work remains active.",
        {
            "date_published": "2024-08-27T16:23:57+00:00",
            "date_modified": "2026-05-04T22:23:49+00:00",
            "physical_status_as_reported": "Groundwork will continue until autumn 2026; substation commissioning work is planned for autumn.",
            "month_end_as_of_basis": "The physical update gives April 2026 month precision; month-end does not imply an exact observation day.",
            "collision_resolution": "Reuses the exact global-open-v3 OSM campus and development-project stable keys, while inheriting no coordinates or geometry.",
        },
    ),
    Site(
        "lyle-creek-conover", "United States",
        "Lyle Creek site, Conover, North Carolina, United States",
        "curated:microsoft-lyle-creek-conover-data-center",
        "curated:microsoft-lyle-creek-conover-data-center:current-build",
        "Microsoft Conover Lyle Creek Data Center",
        "Microsoft Conover Lyle Creek Current Build",
        "microsoft-lyle-creek-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/lyle-creek-datacenter-construction-update/",
        "2026-06-30", "2026-07-22T00:44:38Z", "2026-05-31",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft's May 2026 update reports foundations, slabs, and steel across multiple Lyle Creek buildings.",
        {
            "date_published": "2024-05-15T20:38:05+00:00",
            "date_modified": "2026-06-30T19:20:45+00:00",
            "physical_status_as_reported": "Several buildings have completed underground work, foundations, and slabs; steel has begun; additional buildings remain at foundation and footing stages.",
            "month_end_as_of_basis": "The physical update gives May 2026 month precision; month-end does not imply an exact observation day.",
            "identity_guardrail": "Lyle Creek is not merged with Hickory/Stover, Boyd Farms, or another Catawba County project.",
        },
    ),
    Site(
        "levis-charny", "Canada", "Charny neighborhood, Lévis, Quebec, Canada",
        "osm:way/1383040174", "osm:way/1383040174:development-project",
        "Microsoft Lévis Charny Data Center",
        "Microsoft Lévis Charny Development Project",
        "microsoft-levis-charny-current-build-captured-2026-07-21",
        "https://local.microsoft.com/blog/levis-datacenter-project-updates/",
        "2026-04-30", "2026-07-22T00:44:38Z", "2026-04-30",
        "under_construction", "authoritative_physical_status_update",
        "Microsoft's April 2026 update reports continuing civil and sound-wall work at Lévis Charny.",
        {
            "date_published": "2024-03-27T16:42:52+00:00",
            "date_modified": "2026-04-30T09:00:54+00:00",
            "physical_status_as_reported": "Civil works continue until autumn 2026 and sound-wall construction is progressing.",
            "month_end_as_of_basis": "The physical update gives April 2026 month precision; month-end does not imply an exact observation day.",
            "collision_resolution": "Reuses the exact global-open-v3 OSM campus and development-project stable keys, while inheriting no coordinates or geometry.",
            "locality_guardrail": "The Microsoft Charny project is distinct from QScale Q01 elsewhere in Lévis.",
        },
    ),
)

SOURCE_FILENAMES = tuple(site.filename for site in SITES)
SITE_BY_FILENAME = {site.filename: site for site in SITES}
CONTENT_FILES = (
    "README.md", "candidate-assessment.json", "retrieval-inventory.json",
    "rights-and-disposition.json", "source-snapshot.json",
)
CLOSED_FILES = frozenset((*CONTENT_FILES, "manifest.json", "manifest.sha256"))


def _evidence(site: Site) -> dict[str, Any]:
    body = f"{site.slug.split('-')[0]}.body"
    capture_names = {
        "bornasco-via-olivetti": "bornasco",
        "bergheim-first-cluster-facility": "bergheim",
        "hr-ranch-road-cheyenne": "hr-ranch",
        "county-road-381-san-antonio": "county-road-381",
        "ginger-west-des-moines": "ginger-west",
        "ginger-east-des-moines": "ginger-east",
        "lancienne-lorette": "lancienne-lorette",
        "lyle-creek-conover": "lyle-creek",
        "levis-charny": "levis",
    }
    capture = capture_names[site.slug]
    body = f"{capture}.body"
    headers = f"{capture}-headers.txt"
    body_bytes, body_sha = CAPTURE_FILE_PINS[body]
    header_bytes, header_sha = CAPTURE_FILE_PINS[headers]
    metadata = {
        "capture_artifact_id": ARTIFACT_ID,
        "capture_request_id": capture,
        "capture_method": "credential_free_curl_location_compressed",
        "requested_url": site.url,
        "effective_url": site.url,
        "request_credentials_supplied": False,
        "http_status": 200,
        "content_type": "text/html; charset=UTF-8",
        "content_hash_scope": f"SHA-256 of the exact {body_bytes}-byte content-decoded credential-free public response body",
        "content_hash_verification": "fetched_bytes_sha256",
        "capture_headers_scope": f"SHA-256 of the exact {header_bytes}-byte raw HTTP response-header capture",
        "capture_headers_sha256": header_sha,
        "status_semantics": "dated_last_observed_current_status_unknown",
        "rights_scope": "Compact factual extraction from all-rights-reserved official bytes; raw bodies, headers, telemetry, and publisher media are not redistributed.",
        "normalization_guardrail": "No capacity, energy use, PUE, WUE, generation, facility type, operating model, workload, role, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is normalized.",
        **site.factual_extract,
    }
    return {
        "key": site.evidence_key,
        "kind": "company_disclosure",
        "title": f"{site.campus_name} official construction update",
        "source_url": site.url,
        "publisher": site.publisher,
        "source_family": site.source_family,
        "published_at": site.published_at,
        "retrieved_at": site.retrieved_at,
        "license": "all-rights-reserved",
        "attribution": site.publisher,
        "excerpt": site.excerpt,
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
        "evidence_key": site.evidence_key,
        "as_of_date": site.as_of_date,
        "method": "authoritative_locality",
        "confidence": 0.99,
    }


def _source(site: Site) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "evidence": [_evidence(site)],
        "campus": _entity(site, project=False),
        "project": _entity(site, project=True),
        "lifecycle": [{
            "entity": "project", "value": site.status,
            "evidence_key": site.evidence_key, "as_of_date": site.as_of_date,
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
            "evidence_records": 1, "lifecycle_observations": 1,
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
    for path, pin in {**V88_PINS, **MASTER_PINS, GLOBAL_ENTITIES: GLOBAL_ENTITIES_PIN}.items():
        _pin(path, pin)
    if tree_digest(V88_RELEASE) != V88_TREE_SHA256:
        raise RuntimeError("v88 release tree differs")
    if tree_digest(MASTER_RELEASE) != MASTER_TREE_SHA256:
        raise RuntimeError("master v31 tree differs")
    definition = json.loads(V88_DEFINITION.read_text(encoding="utf-8"))
    selected = definition.get("curated_inputs")
    if not isinstance(selected, list) or len(selected) != V88_INPUT_COUNT:
        raise RuntimeError("v88 selected input inventory differs")
    planned_stable, planned_evidence = _planned_keys(documents)
    with V88_ENTITIES.open(encoding="utf-8", newline="") as stream:
        base_rows = list(csv.DictReader(stream))
    base_stable = {row["stable_key"] for row in base_rows}
    if planned_stable & base_stable:
        raise RuntimeError("planned Microsoft stable key collides with v88")
    source_inputs = json.loads((V88_RELEASE / "source_inputs.json").read_text(encoding="utf-8")).get("sources")
    base_evidence = {
        key for row in source_inputs or [] if isinstance(row, dict)
        for key in [row.get("provenance", {}).get("curated_record_key")]
        if isinstance(key, str)
    }
    if planned_evidence & base_evidence:
        raise RuntimeError("planned Microsoft evidence key collides with v88")

    with GLOBAL_ENTITIES.open(encoding="utf-8", newline="") as stream:
        global_rows = {row["stable_key"]: row for row in csv.DictReader(stream)}
    exact_master_keys = {
        "osm:way/1383040174", "osm:way/1383040174:development-project",
        "osm:way/1383040176", "osm:way/1383040176:development-project",
    }
    expected_names = {
        "osm:way/1383040174": "Microsoft centre de données de Lévis",
        "osm:way/1383040174:development-project": "Microsoft centre de données de Lévis development project",
        "osm:way/1383040176": "Microsoft centre de données de L’Ancienne-Lorette",
        "osm:way/1383040176:development-project": "Microsoft centre de données de L’Ancienne-Lorette development project",
    }
    if {key: global_rows.get(key, {}).get("name") for key in exact_master_keys} != expected_names:
        raise RuntimeError("global-open exact Microsoft identity witness differs")
    with MASTER_CSV.open(encoding="utf-8", newline="") as stream:
        master_rows = list(csv.DictReader(stream))
    exact_names = set(expected_names.values())
    master_exact = {
        row["name"] for row in master_rows
        if row["name"] in exact_names and row["review_only"] == "false"
    }
    if master_exact != exact_names:
        raise RuntimeError("master exact Microsoft identity witness differs")
    qscale_locality = [
        row["name"] for row in master_rows
        if row["name"] == "QScale Q01 Building B" and "Lévis" in row["address"]
    ]
    if qscale_locality != ["QScale Q01 Building B"]:
        raise RuntimeError("Lévis distinct-locality witness differs")
    return {
        "v88_selected_input_count": len(selected),
        "v88_entity_count": len(base_rows),
        "planned_distinct_stable_keys": len(planned_stable),
        "planned_distinct_evidence_keys": len(planned_evidence),
        "exact_v88_stable_key_collisions": [],
        "exact_v88_evidence_key_collisions": [],
        "exact_master_identity_keys_reused": sorted(exact_master_keys),
        "master_collision_resolution": "Lévis and L’Ancienne-Lorette reuse exact global-open-v3 stable keys; official records inherit no OSM coordinates or geometry.",
        "distinct_locality_boundary": "QScale Q01 Building B is a separate Lévis project and is not merged with Microsoft Charny.",
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
    candidates.append({
        "candidate_id": "donnacona",
        "decision": "review_only_mixed_stage_schema_boundary",
        "source_paths": [], "seed_eligible": False,
        "capture": {"url": "https://local.microsoft.com/blog/donnacona-datacentre-construction-update/", "body_bytes": CAPTURE_FILE_PINS["donnacona.body"][0], "body_sha256": CAPTURE_FILE_PINS["donnacona.body"][1]},
        "official_factual_extract": "April 2026 says the data-center building was completed in November 2025 while internal, substation, and sound-wall work continues or is forecast.",
        "boundary": "Schema 1.1 cannot preserve building-complete and ancillary-work-active as simultaneous partial stages; flattening to generic current build or operation would be inaccurate.",
    })
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-current-build-assessment-v1",
        "research_date": "2026-07-21", "recorded_at": recorded_at,
        "candidate_count": 10, "seed_eligible_candidate_count": 9,
        "seed_eligible_source_record_count": 9, "review_only_count": 1,
        "regional_completeness_claimed": False, "candidates": candidates,
    }


def _capture_inventory(recorded_at: str) -> dict[str, Any]:
    capture_names = [
        "bornasco", "bergheim", "hr-ranch", "county-road-381", "ginger-west",
        "ginger-east", "lancienne-lorette", "lyle-creek", "levis", "donnacona",
    ]
    return {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-official-source-retrieval-inventory-v3",
        "research_date": "2026-07-21", "recorded_at": recorded_at,
        "request_credentials_supplied": False,
        "successful_http_200_body_captures": 10,
        "raw_capture_redistributed": False,
        "capture_file_count": CAPTURE_FILE_COUNT,
        "capture_total_bytes": CAPTURE_TOTAL_BYTES,
        "capture_tree_sha256": CAPTURE_TREE_SHA256,
        "temporary_capture_directory_original_path": str(CAPTURE_ORIGIN),
        "temporary_capture_directory_moved_to_trash": True,
        "temporary_capture_trash_path": str(CAPTURE_TRASH),
        "temporary_capture_recoverable": True,
        "controlled_captures": [{
            "capture_id": name,
            "body": {"path": f"{name}.body", "bytes": CAPTURE_FILE_PINS[f"{name}.body"][0], "sha256": CAPTURE_FILE_PINS[f"{name}.body"][1], "retained_in_artifact": False, "moved_to_trash": True},
            "headers": {"path": f"{name}-headers.txt", "bytes": CAPTURE_FILE_PINS[f"{name}-headers.txt"][0], "sha256": CAPTURE_FILE_PINS[f"{name}-headers.txt"][1], "retained_in_artifact": False, "moved_to_trash": True},
            "http_status": 200, "request_credentials_supplied": False,
            "claim_use": "review_only" if name == "donnacona" else "normalized",
        } for name in capture_names],
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
        "candidate_assessments": 10, "source_records": 9,
        "seed_eligible_candidates": 9, "seed_eligible_source_records": 9,
        "review_only_candidates": 1, "distinct_campuses_in_source_records": 9,
        "projects": 9, "distinct_entities_in_source_records": 18,
        "new_entities_against_v88": 18,
        "exact_master_identity_keys_reused": 4,
        "source_document_entity_snapshots": 18,
        "unique_imported_entity_snapshots": 18,
        "unique_evidence_records": 9, "lifecycle_observations": 9,
        "operating_model_observations": 0, "workload_observations": 0,
        "capacity_estimates": 0, "coordinates_present": 0, "geometry_present": 0,
    }
    readme = f"""# Microsoft official current-build gap tranche

This immutable artifact assesses ten official Microsoft pages and publishes nine named, seed-eligible source records. Every site is a separate exact named campus/project pair. Lévis and L’Ancienne-Lorette reuse exact global-open-v3 stable keys after a pinned construction-master collision audit, but inherit no coordinates or geometry. Donnacona remains review-only because the current schema cannot express its building-complete/internal-and-substation-active mixed state without flattening it inaccurately.

No capacity, energy use, generation, PUE, WUE, facility type, operating model, workload, standardized role, current-status extrapolation, coordinate, geometry, satellite, aerial, map-click, or computer-vision claim is added. Forecast completion dates remain metadata only. All normalized statuses are dated last-observed facts whose current status is unknown.

All source and artifact bytes were staged before {recorded_at}; final paths were absent until that instant and promoted without replacement. Raw all-rights-reserved captures are represented only by exact hashes and retrieval facts. The intact {CAPTURE_FILE_COUNT}-file raw capture directory was moved to recoverable Trash only after successful source publication.
"""
    snapshot = {
        "artifact_id": ARTIFACT_ID,
        "format": "datacenter-atlas-curated-source-snapshot-v3",
        "recorded_at": recorded_at, "research_date": "2026-07-21",
        "regional_completeness_claimed": False,
        "source_records": source_records, "totals": totals,
        "frozen_v88_non_mutation_witness": {
            "definition": {"path": "sources/open-seed-2026-07-21-v88.json", "bytes": V88_PINS[V88_DEFINITION][0], "sha256": V88_PINS[V88_DEFINITION][1]},
            "release_manifest": {"path": "releases/2026-07-21-open-seed-v88/manifest.json", "bytes": V88_PINS[V88_MANIFEST][0], "sha256": V88_PINS[V88_MANIFEST][1]},
            "release_entities": {"path": "releases/2026-07-21-open-seed-v88/entities.csv", "bytes": V88_PINS[V88_ENTITIES][0], "sha256": V88_PINS[V88_ENTITIES][1]},
            "release_tree_sha256": V88_TREE_SHA256,
            **collision,
        },
        "integration": {
            "open_seed_successor_created": False, "open_seed_v88_mutated": False,
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
        "research_date": "2026-07-21", "recorded_at": recorded_at,
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
    with tempfile.TemporaryDirectory(prefix="microsoft-current-build-import-", dir="/private/tmp") as temporary:
        connection, _ = initialize(Path(temporary) / "atlas.sqlite")
        adapter = CuratedOfficialSourceAdapterV11()
        for _ in range(2):
            for name in SOURCE_FILENAMES:
                adapter.import_file(connection, paths[name], recorded_at=recorded_at)
        validate_database(connection)
        tables = ("entities", "entity_snapshots", "evidence", "lifecycle_observations", "operating_model_observations", "workload_observations", "capacity_estimates")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        expected = {"entities": 18, "entity_snapshots": 18, "evidence": 9, "lifecycle_observations": 9, "operating_model_observations": 0, "workload_observations": 0, "capacity_estimates": 0}
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
    if manifest_raw != _canonical(manifest) or manifest.get("artifact_id") != ARTIFACT_ID or set(manifest.get("closed_file_set", [])) != CLOSED_FILES or manifest.get("candidate_assessments") != 10 or manifest.get("curated_source_records") != 9 or manifest.get("seed_eligible_candidates") != 9 or manifest.get("review_only_candidates") != 1 or _file_tree(manifest["files"]) != manifest.get("tree_sha256"):
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
    if any(_instant(site.retrieved_at) > target for site in SITES):
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
        "closed_file_set": sorted(CLOSED_FILES), "candidate_assessments": 10,
        "curated_source_records": 9, "seed_eligible_candidates": 9,
        "seed_eligible_source_records": 9, "review_only_candidates": 1,
        "successful_http_200_body_captures": 10,
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
        raise RuntimeError("active Microsoft source publication lock exists") from error
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
        raise RuntimeError("Microsoft source final-path collision")
    _validate_source_collisions()
    capture = CAPTURE_ORIGIN if CAPTURE_ORIGIN.exists() else CAPTURE_TRASH
    _validate_capture_directory(capture)
    documents = expected_source_documents()
    source_stage = Path(tempfile.mkdtemp(prefix=".microsoft-current-build-sources.", dir=SOURCES_ROOT))
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
        raise RuntimeError("late Microsoft source final-path collision")
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
    _validate_capture_directory(CAPTURE_TRASH)


def build(*, recorded_at: str | None = None) -> dict[str, Any]:
    if ARTIFACT.exists() and all((SOURCES_ROOT / name).exists() for name in SOURCE_FILENAMES):
        manifest = validate_artifact()
        _move_capture_to_trash()
        return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 9, "status": "existing-identical"}
    if ARTIFACT.exists() or ARTIFACT.is_symlink() or any((SOURCES_ROOT / name).exists() or (SOURCES_ROOT / name).is_symlink() for name in SOURCE_FILENAMES):
        raise RuntimeError("partial Microsoft source final-path collision")
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
    return {"artifact": str(ARTIFACT), "artifact_tree_sha256": tree_digest(ARTIFACT), "capture_trash": str(CAPTURE_TRASH), "manifest_sha256": _sha256(ARTIFACT / "manifest.json"), "recorded_at": manifest["recorded_at"], "source_records": 9, "status": "published"}


def main() -> int:
    print(json.dumps(build(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
