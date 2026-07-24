from __future__ import annotations

import copy
import csv
import hashlib
import json
import socket
import stat
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
BASES = {
    30: {
        "definition": ROOT / "sources" / "open-seed-2026-07-19-v30.json",
        "release": ROOT / "releases" / "2026-07-19-open-seed-v30",
        "definition_sha256": (
            "b89c7414fe9a96ddd2acfff766386dda514d61278dae039d1d70eb490340ef12"
        ),
        "manifest_sha256": (
            "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619"
        ),
        "curated_inputs": 146,
    },
    31: {
        "definition": ROOT / "sources" / "open-seed-2026-07-19-v31.json",
        "release": ROOT / "releases" / "2026-07-19-open-seed-v31",
        "definition_sha256": (
            "15d5d8a29b2a1cef0a8cbfa1f24276ea5619f9811aab53959bf83cfb3b5050dd"
        ),
        "manifest_sha256": (
            "f81df7005c17ee75ab09ff8e81d86589ad64bfe75164b10b5c643cc14d55f2ea"
        ),
        "curated_inputs": 150,
    },
}
BASE_DEFINITION = BASES[31]["definition"]
BASE_RELEASE = BASES[31]["release"]

DATA4_SOURCE = "curated-official-2026-07-19-data4-ath1-first-data-center.json"
GOOGLE_SOURCE = "curated-official-2026-07-19-google-canelones-uruguay.json"
VIETTEL_SOURCE = "curated-official-2026-07-19-viettel-tan-phu-trung-hcmc.json"
SOURCE_ORDER = (DATA4_SOURCE, GOOGLE_SOURCE, VIETTEL_SOURCE)

DATA4_ANNOUNCEMENT = "data4-ath1-paiania-announcement-2024-09-20-captured-2026-07-19"
DATA4_LOCATION = "data4-athens-campus-current-location-captured-2026-07-19"
DATA4_CSR = "data4-csr-2024-athens-first-foundation-stone-captured-2026-07-19"
GOOGLE_PRESIDENCY = (
    "uruguay-presidency-google-canelones-construction-2026-04-14-captured-2026-07-19"
)
GOOGLE_BLOG = "google-canelones-construction-start-2024-08-29-captured-2026-07-19"
VIETTEL_VNA = (
    "vna-viettel-tan-phu-trung-current-construction-2025-04-29-captured-2026-07-19"
)
VIETTEL_POST = (
    "viettel-high-tech-data-rd-center-construction-start-2025-04-23-captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    DATA4_SOURCE: {
        "sha256": "028990145023dd581beff459437414324bcf76b0da893a2c46c0a13aa065df7c",
        "evidence_keys": (DATA4_ANNOUNCEMENT, DATA4_LOCATION, DATA4_CSR),
        "retrieved_at": "2026-07-19T22:32:25Z",
        "country": "Greece",
        "address": "Agiou Louka 33, 190 02 Paiania, Greece",
        "campus_key": "curated:data4-ath1-paiania-campus",
        "campus_name": "DATA4 ATH1 Paiania Campus",
        "project_key": "curated:data4-ath1-paiania-campus:first-data-center",
        "project_name": "DATA4 ATH1 First Data Center",
        "entity_evidence": DATA4_LOCATION,
        "entity_as_of": "2026-07-19",
        "lifecycle_evidence": DATA4_CSR,
        "lifecycle_as_of": "2024-12-31",
        "lifecycle_method": "authoritative_construction_start",
        "confidence": 0.95,
    },
    GOOGLE_SOURCE: {
        "sha256": "7ca2b59fdddc843e62d8e1661e13416daa109238bdf37ef414decff53af586a7",
        "evidence_keys": (GOOGLE_PRESIDENCY, GOOGLE_BLOG),
        "retrieved_at": "2026-07-19T22:30:09Z",
        "country": "Uruguay",
        "address": "Parque de las Ciencias, Canelones, Uruguay",
        "campus_key": "curated:google-parque-de-las-ciencias-data-center-campus",
        "campus_name": "Google Parque de las Ciencias Data Center Campus",
        "project_key": (
            "curated:google-parque-de-las-ciencias-data-center-campus:data-center-project"
        ),
        "project_name": "Google Canelones Data Center Project",
        "entity_evidence": GOOGLE_PRESIDENCY,
        "entity_as_of": "2026-04-14",
        "lifecycle_evidence": GOOGLE_PRESIDENCY,
        "lifecycle_as_of": "2026-04-14",
        "lifecycle_method": "authoritative_physical_status_update",
        "confidence": 0.99,
    },
    VIETTEL_SOURCE: {
        "sha256": "ecdf26ee064eb9513867940211e0c4c07a51fade9aa94786279542465f46b652",
        "evidence_keys": (VIETTEL_VNA, VIETTEL_POST),
        "retrieved_at": "2026-07-19T22:30:12Z",
        "country": "Viet Nam",
        "address": (
            "Tan Phu Trung Industrial Zone, Cu Chi, Ho Chi Minh City, Viet Nam"
        ),
        "campus_key": "curated:viettel-tan-phu-trung-data-center-campus",
        "campus_name": "Viettel Tan Phu Trung Data Center Campus",
        "project_key": (
            "curated:viettel-tan-phu-trung-data-center-campus:high-tech-data-rd-center"
        ),
        "project_name": (
            "Viettel High-Tech Data and Research and Development Center"
        ),
        "entity_evidence": VIETTEL_VNA,
        "entity_as_of": "2025-04-29",
        "lifecycle_evidence": VIETTEL_POST,
        "lifecycle_as_of": "2025-04-23",
        "lifecycle_method": "authoritative_construction_start",
        "confidence": 0.99,
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    GOOGLE_PRESIDENCY: {
        "source": GOOGLE_SOURCE,
        "kind": "government_record",
        "publisher": "Presidencia Uruguay",
        "source_family": "uruguay_presidency_news",
        "published_at": "2026-04-14",
        "body_bytes": 43828,
        "content_hash": "3aa58d57fb70fa904d467e5456c31de365151e4833a60f36fdf8b3878de557f6",
        "headers_bytes": 786,
        "headers_hash": "d48d8db65cbbe00dba0593b5421bd27716dc995071d729683fd173724ea859ed",
        "writeout_bytes": 15968,
        "writeout_hash": "d5bda850fc700bbff9ae38f2024c568cd58e6dc9dc817e77ec11c8fa209cab9b",
        "download_bytes": 19149,
        "response_date": "2026-07-19T22:30:09Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "transfer_encoding": "chunked",
        "content_length": None,
        "requested_url": (
            "https://www.gub.uy/presidencia/comunicacion/noticias/"
            "orsi-google-datacenter-uruguay-canelones"
        ),
        "effective_url": (
            "https://www.gub.uy/presidencia/comunicacion/noticias/"
            "orsi-google-datacenter-uruguay-canelones"
        ),
        "canonical_url": (
            "https://www.gub.uy/presidencia/comunicacion/noticias/"
            "orsi-google-datacenter-uruguay-canelones"
        ),
    },
    GOOGLE_BLOG: {
        "source": GOOGLE_SOURCE,
        "kind": "company_disclosure",
        "publisher": "Google",
        "source_family": "google_company_blog",
        "published_at": "2024-08-29",
        "body_bytes": 347935,
        "content_hash": "8336a93fcad5e06e386eb82a3a0f38edad2eb9f5d44b0847ddde12a61d0ce82f",
        "headers_bytes": 2799,
        "headers_hash": "cf71008b9d3b3907c8203743e44e050114158174390a64cc10eb0eb553601bff",
        "writeout_bytes": 15884,
        "writeout_hash": "97691e05f34d2fbbee5787f2d02dcb34958fe74e23d67f16a3c4210f4cec7976",
        "download_bytes": 67920,
        "response_date": "2026-07-19T22:30:09Z",
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "transfer_encoding": None,
        "content_length": 67920,
        "requested_url": (
            "https://blog.google/company-news/inside-google/around-the-globe/"
            "google-latin-america/a-new-data-center-in-latin-america/"
        ),
        "effective_url": (
            "https://blog.google/company-news/inside-google/around-the-globe/"
            "google-latin-america/a-new-data-center-in-latin-america/"
        ),
        "canonical_url": (
            "https://blog.google/company-news/inside-google/around-the-globe/"
            "google-latin-america/a-new-data-center-in-latin-america/"
        ),
    },
    VIETTEL_VNA: {
        "source": VIETTEL_SOURCE,
        "kind": "government_record",
        "publisher": "VietnamPlus, Vietnam News Agency",
        "source_family": "vietnam_news_agency_vietnamplus",
        "published_at": "2025-04-29T14:30:44+07:00",
        "body_bytes": 120713,
        "content_hash": "24071a2e81a9bad978a0dca46c427dc75d99b4a48fede7381bda4acce139c3e8",
        "headers_bytes": 285,
        "headers_hash": "36dff3d0eac385d1f675c2442f0e3fc9df2f9a38a19ee099a9d3039b0dd26074",
        "writeout_bytes": 10975,
        "writeout_hash": "2a74581fae9d829fcba0df0c70466e0c3e233b24f6d5e6032f9214ee8e2ddf85",
        "download_bytes": 25026,
        "response_date": "2026-07-19T22:30:11Z",
        "content_type": "text/html;charset=utf-8",
        "content_encoding": "gzip",
        "transfer_encoding": "chunked",
        "content_length": None,
        "requested_url": (
            "https://fr.vietnamplus.vn/viettel-construit-le-plus-grand-"
            "centre-de-donnees-au-vietnam-post245060.vnp"
        ),
        "effective_url": (
            "https://fr.vietnamplus.vn/viettel-construit-le-plus-grand-"
            "centre-de-donnees-au-vietnam-post245060.vnp"
        ),
        "canonical_url": (
            "https://fr.vietnamplus.vn/viettel-construit-le-plus-grand-"
            "centre-de-donnees-au-vietnam-post245060.vnp"
        ),
    },
    VIETTEL_POST: {
        "source": VIETTEL_SOURCE,
        "kind": "company_disclosure",
        "publisher": "Viettel Group",
        "source_family": "viettel_official_linkedin",
        "published_at": "2025-04-25T04:26:25.983Z",
        "body_bytes": 157709,
        "content_hash": "de06c22ffb3a4587772bd3de6b98baac3bb84f16c48dcf178da74db296fc5734",
        "headers_bytes": 5348,
        "headers_hash": "869e5ad6e95bd475e026a669e1b36edf4c87de6e791d7349dae53205ab037958",
        "writeout_bytes": 17754,
        "writeout_hash": "1a1c0d003f79f1393df8b143c77a842f4a62f43756b8487345f216a1a04dc41b",
        "download_bytes": 21693,
        "response_date": "2026-07-19T22:30:12Z",
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "transfer_encoding": None,
        "content_length": 21693,
        "requested_url": (
            "https://www.linkedin.com/posts/viettel-group_viettel-commences-"
            "construction-of-the-first-activity-7321389098894614528-XWVj"
        ),
        "effective_url": (
            "https://www.linkedin.com/posts/viettel-group_viettel-commences-"
            "construction-of-the-first-activity-7321389098894614528-XWVj"
        ),
        "canonical_url": (
            "https://www.linkedin.com/posts/viettelcareers_viettel-commences-"
            "construction-of-the-first-activity-7321389098894614528-ipfk"
        ),
    },
    DATA4_ANNOUNCEMENT: {
        "source": DATA4_SOURCE,
        "kind": "company_disclosure",
        "publisher": "DATA4",
        "source_family": "data4_news",
        "published_at": "2024-09-20T12:36:56+00:00",
        "body_bytes": 131368,
        "content_hash": "bb095d16556595f008438f75f0f4ec80338d571a09005b68c6e4933f0f5b0d8d",
        "headers_bytes": 571,
        "headers_hash": "31b91a31d00ef28ce6e1337ba9dc970711cf3ad06304adf11d2e5ecea9acb364",
        "writeout_bytes": 11720,
        "writeout_hash": "90d979e42615fa9ba3208f0d43326807cfca2a15ee697565c9be7cc7e86b0fa4",
        "download_bytes": 25364,
        "response_date": "2026-07-19T22:30:13Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "transfer_encoding": None,
        "content_length": 25364,
        "requested_url": (
            "https://www.data4group.com/en/news-data4/data4-announces-major-"
            "investment-of-300-million-euros-in-greece-to-develop-new-data-center-campus/"
        ),
        "effective_url": (
            "https://www.data4group.com/en/news-data4/data4-announces-major-"
            "investment-of-300-million-euros-in-greece-to-develop-new-data-center-campus/"
        ),
        "canonical_url": (
            "https://www.data4group.com/en/news-data4/data4-announces-major-"
            "investment-of-300-million-euros-in-greece-to-develop-new-data-center-campus/"
        ),
    },
    DATA4_LOCATION: {
        "source": DATA4_SOURCE,
        "kind": "company_disclosure",
        "publisher": "DATA4",
        "source_family": "data4_location_pages",
        "published_at": "2024-09-10T10:50:33+00:00",
        "body_bytes": 124439,
        "content_hash": "3036824a2f3e4db6b0c2051287d24a73bff99a273a00537c20cb9cb9ee9ec770",
        "headers_bytes": 571,
        "headers_hash": "3855c07a53d7634f61626788c3f5f63d771d3b52aee32a8151bf070db63654f2",
        "writeout_bytes": 11382,
        "writeout_hash": "a22e87f16eb91bcbfcbb10a78b60297fbf83eddad20f47c57aef58a5711428f4",
        "download_bytes": 23098,
        "response_date": "2026-07-19T22:30:14Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "transfer_encoding": None,
        "content_length": 23098,
        "requested_url": "https://www.data4group.com/en/data-center-athens-greece/",
        "effective_url": "https://www.data4group.com/en/data-center-athens-greece/",
        "canonical_url": "https://www.data4group.com/en/data-center-athens-greece/",
    },
    DATA4_CSR: {
        "source": DATA4_SOURCE,
        "kind": "company_disclosure",
        "publisher": "DATA4",
        "source_family": "data4_csr_reports",
        "published_at": None,
        "body_bytes": 15049486,
        "content_hash": "252b6498c5780f2e0ae63119267fe4b0e26cc5cb56c76a98208ef0c97809aed5",
        "headers_bytes": 322,
        "headers_hash": "347fd6dd9b39d01f074aadb40977d083a4e6bbcc45a138de8581ad3276f84d1c",
        "writeout_bytes": 11484,
        "writeout_hash": "ed7c8b50cd527a59d0c0561a3801964def7814a9bd85c7cb5a9d378e6dcbf550",
        "download_bytes": 15049486,
        "response_date": "2026-07-19T22:32:25Z",
        "last_modified": "2026-01-22T12:58:21Z",
        "content_type": "application/pdf",
        "content_encoding": None,
        "transfer_encoding": None,
        "content_length": 15049486,
        "requested_url": (
            "https://www.data4group.com/wp-content/uploads/2025/05/"
            "Data4-CSR-Report-2024-En.pdf"
        ),
        "effective_url": (
            "https://www.data4group.com/wp-content/uploads/2025/05/"
            "Data4-CSR-Report-2024-En.pdf"
        ),
        "canonical_url": (
            "https://www.data4group.com/wp-content/uploads/2025/05/"
            "Data4-CSR-Report-2024-En.pdf"
        ),
    },
}

SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "administrative_assignments",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class GoogleViettelData4Tests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        expected = CAPTURES[evidence["key"]]
        source = SOURCES[expected["source"]]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["kind"], expected["kind"])
        self.assertEqual(evidence["publisher"], expected["publisher"])
        self.assertEqual(evidence["source_family"], expected["source_family"])
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], source["retrieved_at"])
        self.assertEqual(evidence["content_hash"], expected["content_hash"])
        self.assertEqual(evidence["source_url"], expected["canonical_url"])
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(expected["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(expected["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], expected["headers_hash"])
        self.assertIn(
            str(expected["writeout_bytes"]),
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], expected["writeout_hash"]
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], expected["content_type"])
        self.assertEqual(
            metadata["content_encoding_as_received"], expected["content_encoding"]
        )
        self.assertEqual(
            metadata["http_transfer_encoding_as_received"],
            expected["transfer_encoding"],
        )
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            expected["content_length"],
        )
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            expected["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], expected["response_date"])
        self.assertEqual(
            metadata["http_last_modified_at"], expected.get("last_modified")
        )
        self.assertEqual(metadata["requested_url"], expected["requested_url"])
        self.assertEqual(metadata["effective_url"], expected["effective_url"])
        self.assertEqual(metadata["canonical_url"], expected["canonical_url"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("not redistributed", metadata["rights_scope"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        self.assertEqual(
            set(document),
            {
                "schema_version",
                "evidence",
                "campus",
                "project",
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            },
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(
            tuple(row["key"] for row in document["evidence"]),
            expected["evidence_keys"],
        )
        for evidence in document["evidence"]:
            self._assert_capture(evidence)

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], expected["entity_evidence"])
            self.assertEqual(entity["as_of_date"], expected["entity_as_of"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["campus"]["name"], expected["campus_name"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["project"]["name"], expected["project_name"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": expected["lifecycle_evidence"],
                    "as_of_date": expected["lifecycle_as_of"],
                    "method": expected["lifecycle_method"],
                    "confidence": expected["confidence"],
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

        evidence = {row["key"]: row for row in document["evidence"]}
        if name == GOOGLE_SOURCE:
            current = evidence[GOOGLE_PRESIDENCY]["metadata"]
            start = evidence[GOOGLE_BLOG]["metadata"]
            self.assertIn("generic project under_construction", current["status_scope"])
            self.assertEqual(start["reported_project_investment_usd"], 850000000)
            self.assertIn("metadata only", start["investment_guardrail"])
            self.assertIn("No OpenStreetMap feature", current["osm_conflation_guardrail"])
            self.assertIn("no automatic merge", start["osm_conflation_guardrail"])
            self.assertIn("no normalized workload", start["classification_guardrail"])
        elif name == VIETTEL_SOURCE:
            state = evidence[VIETTEL_VNA]["metadata"]
            start = evidence[VIETTEL_POST]["metadata"]
            self.assertEqual(state["reported_design_or_projected_power_mw"], 140)
            self.assertEqual(state["reported_average_rack_density_kw"], 10)
            self.assertEqual(state["reported_maximum_rack_density_kw"], 60)
            self.assertEqual(state["reported_design_standard_wording_as_reported"], "Uptime Tier III")
            self.assertEqual(state["reported_target_pue_inequality"], "< 1.4")
            self.assertIn("no normalized capacity", state["power_metric_guardrail"])
            self.assertIn("no structured PUE", state["pue_guardrail"])
            self.assertIn("no normalized workload", state["classification_guardrail"])
            self.assertIn("2026 AIC or KBC", state["identity_guardrail"])
            self.assertIn("2026 AIC or KBC", start["identity_guardrail"])
            self.assertIn("does not authorize splitting", state["phase_guardrail"])
        else:
            announcement = evidence[DATA4_ANNOUNCEMENT]["metadata"]
            location = evidence[DATA4_LOCATION]["metadata"]
            csr = evidence[DATA4_CSR]["metadata"]
            self.assertEqual(announcement["reported_power_capacity_mw_maximum"], 90)
            self.assertEqual(location["reported_available_electricity_reserves_mw"], 90)
            self.assertIn("no normalized capacity", announcement["power_metric_guardrail"])
            self.assertIn("no normalized capacity", location["power_metric_guardrail"])
            self.assertEqual(csr["evidence_page_number"], 19)
            self.assertEqual(csr["construction_year_scope"], 2024)
            self.assertIn("generic under_construction", csr["status_scope"])
            self.assertIn("2024-12-31", csr["as_of_date_guardrail"])
            self.assertEqual(
                csr["uncaptured_government_corroboration_url"],
                "https://www.primeminister.gr/2024/11/19/35328",
            )
            self.assertIn(
                "HTTP 403", csr["uncaptured_government_corroboration_capture_status"]
            )
            self.assertIn(
                "no government content hash",
                csr["uncaptured_government_corroboration_guardrail"],
            )
            for key in expected["evidence_keys"]:
                self.assertIn(
                    "second facility",
                    evidence[key]["metadata"]["second_facility_guardrail"],
                )

    def _base_paths(self) -> list[Path]:
        base = BASES[31]
        definition = base["definition"]
        release = base["release"]
        self.assertEqual(
            hashlib.sha256(definition.read_bytes()).hexdigest(),
            base["definition_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((release / "manifest.json").read_bytes()).hexdigest(),
            base["manifest_sha256"],
        )
        document = json.loads(definition.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in document["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            paths.append(path)
        self.assertEqual(len(paths), base["curated_inputs"])
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(
            len(paths),
            len({hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}),
        )
        return paths

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        values = {row["retrieved_at"] for row in document["evidence"]}
        self.assertEqual(len(values), 1)
        return next(iter(values))

    def _import(self, connection: Any, path: Path) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            path,
            retrieved_at=self._retrieved_at(path),
        )

    def _semantic_state(
        self, connection: Any
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _offline(self) -> tuple[Any, ...]:
        error = AssertionError("network used")
        return (
            patch.object(socket, "socket", side_effect=error),
            patch.object(socket, "create_connection", side_effect=error),
            patch.object(socket, "getaddrinfo", side_effect=error),
            patch.object(socket, "gethostbyname", side_effect=error),
            patch.object(socket, "gethostbyname_ex", side_effect=error),
        )

    def _build(
        self,
        source_order: Iterable[str],
        *,
        base_first: bool,
    ) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                results: dict[str, tuple[int, int]] = {}
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    if base_first:
                        for path in self._base_paths():
                            self._import(connection, path)
                    for name in source_order:
                        result = self._import(connection, ROOT / "sources" / name)
                        results[name] = (
                            result.entities_created,
                            result.evidence_created,
                        )
                    if not base_first:
                        for path in self._base_paths():
                            self._import(connection, path)
                    final_state = self._semantic_state(connection)
                    for name in SOURCE_ORDER:
                        result = self._import(connection, ROOT / "sources" / name)
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._semantic_state(connection), final_state)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()
                self.assertEqual(validate_database(connection), [])
                return final_state, results
            finally:
                connection.close()

    def _baseline_state(self) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    for path in self._base_paths():
                        self._import(connection, path)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection)
            finally:
                connection.close()

    def test_exact_source_capture_contract_and_v30_v31_collision_absence(self) -> None:
        new_keys: set[str] = set()
        new_hashes: set[str] = set()
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            document = self._load(name)
            self._assert_document(name, document)
            new_keys.update((expected["campus_key"], expected["project_key"]))
            new_hashes.update(row["content_hash"] for row in document["evidence"])
            for suffix in (".body", ".headers", ".writeout"):
                self.assertFalse((ROOT / "sources" / f"{name}{suffix}").exists())

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    patches = self._offline()
                    for network_patch in patches:
                        network_patch.start()
                    try:
                        result = self._import(connection, path)
                    finally:
                        for network_patch in reversed(patches):
                            network_patch.stop()
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(
                        result.evidence_created, len(expected["evidence_keys"])
                    )
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

        self.assertEqual(len(new_keys), 6)
        self.assertEqual(len(new_hashes), 7)
        self.assertEqual(
            new_hashes,
            {capture["content_hash"] for capture in CAPTURES.values()},
        )

        for version, base in BASES.items():
            definition = base["definition"]
            release = base["release"]
            self.assertEqual(
                hashlib.sha256(definition.read_bytes()).hexdigest(),
                base["definition_sha256"],
                version,
            )
            self.assertEqual(
                hashlib.sha256((release / "manifest.json").read_bytes()).hexdigest(),
                base["manifest_sha256"],
                version,
            )
            definition_text = definition.read_text(encoding="utf-8")
            for name in SOURCE_ORDER:
                self.assertNotIn(name, definition_text)
            with (release / "entities.csv").open(encoding="utf-8", newline="") as stream:
                base_keys = {row["stable_key"] for row in csv.DictReader(stream)}
            with (release / "evidence.csv").open(encoding="utf-8", newline="") as stream:
                base_hashes = {row["content_hash"] for row in csv.DictReader(stream)}
            self.assertTrue(new_keys.isdisjoint(base_keys), version)
            self.assertTrue(new_hashes.isdisjoint(base_hashes), version)

    def test_forward_reverse_base_order_idempotence_and_exact_deltas(self) -> None:
        baseline_state = self._baseline_state()
        scenarios = [
            self._build(SOURCE_ORDER, base_first=True),
            self._build(reversed(SOURCE_ORDER), base_first=True),
            self._build(SOURCE_ORDER, base_first=False),
            self._build(reversed(SOURCE_ORDER), base_first=False),
        ]
        expected_results = {
            DATA4_SOURCE: (2, 3),
            GOOGLE_SOURCE: (2, 2),
            VIETTEL_SOURCE: (2, 2),
        }
        reference_state = scenarios[0][0]
        for state, results in scenarios:
            self.assertEqual(state, reference_state)
            self.assertEqual(results, expected_results)

        baseline_counts = {table: len(rows) for table, rows in baseline_state.items()}
        final_counts = {table: len(rows) for table, rows in reference_state.items()}
        self.assertEqual(
            {
                table: final_counts[table] - baseline_counts[table]
                for table in SEMANTIC_TABLES
            },
            {
                "evidence": 7,
                "entities": 6,
                "campuses": 3,
                "facilities": 0,
                "buildings": 0,
                "projects": 3,
                "administrative_assignments": 0,
                "entity_snapshots": 6,
                "lifecycle_observations": 3,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 0,
            },
        )

    def test_combined_import_has_only_exact_narrow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    for name in SOURCE_ORDER:
                        self._import(connection, ROOT / "sources" / name)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()

                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 3), ("project", 3)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        (
                            SOURCES[DATA4_SOURCE]["project_key"],
                            "under_construction",
                            "2024-12-31",
                            "authoritative_construction_start",
                        ),
                        (
                            SOURCES[GOOGLE_SOURCE]["project_key"],
                            "under_construction",
                            "2026-04-14",
                            "authoritative_physical_status_update",
                        ),
                        (
                            SOURCES[VIETTEL_SOURCE]["project_key"],
                            "under_construction",
                            "2025-04-23",
                            "authoritative_construction_start",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    7,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots WHERE geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                for table in (
                    "administrative_assignments",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                        table,
                    )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_closed(self) -> None:
        google = self._load(GOOGLE_SOURCE)
        viettel = self._load(VIETTEL_SOURCE)
        data4 = self._load(DATA4_SOURCE)
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(google)
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((GOOGLE_SOURCE, mutated))
        mutated = copy.deepcopy(google)
        mutated["capacities"] = [{"forbidden": "850 million USD is not capacity"}]
        mutations.append((GOOGLE_SOURCE, mutated))
        mutated = copy.deepcopy(google)
        mutated["workloads"] = [{"forbidden": "AI access is not workload evidence"}]
        mutations.append((GOOGLE_SOURCE, mutated))
        mutated = copy.deepcopy(google)
        mutated["project"]["roles"] = {"owner": ["Google"]}
        mutations.append((GOOGLE_SOURCE, mutated))
        mutated = copy.deepcopy(google)
        mutated["project"]["coordinates"] = {
            "latitude": -34.815242,
            "longitude": -55.995001,
        }
        mutations.append((GOOGLE_SOURCE, mutated))
        mutated = copy.deepcopy(google)
        mutated["lifecycle"][0]["as_of_date"] = "2024-08-29"
        mutations.append((GOOGLE_SOURCE, mutated))

        mutated = copy.deepcopy(viettel)
        mutated["lifecycle"][0]["value"] = "foundations"
        mutations.append((VIETTEL_SOURCE, mutated))
        mutated = copy.deepcopy(viettel)
        mutated["capacities"] = [{"forbidden": "140 MW is untyped"}]
        mutations.append((VIETTEL_SOURCE, mutated))
        mutated = copy.deepcopy(viettel)
        mutated["capacities"] = [{"forbidden": "PUE inequality is metadata"}]
        mutations.append((VIETTEL_SOURCE, mutated))
        mutated = copy.deepcopy(viettel)
        mutated["workloads"] = [{"forbidden": "AI and HPC capability is not workload"}]
        mutations.append((VIETTEL_SOURCE, mutated))
        mutated = copy.deepcopy(viettel)
        mutated["operating_models"] = [{"forbidden": "hyperscale wording is not a model"}]
        mutations.append((VIETTEL_SOURCE, mutated))
        mutated = copy.deepcopy(viettel)
        mutated["project"]["name"] = "AIC KBC Data Center"
        mutations.append((VIETTEL_SOURCE, mutated))
        mutated = copy.deepcopy(viettel)
        mutated["project"]["roles"] = {"operator": ["Viettel"]}
        mutations.append((VIETTEL_SOURCE, mutated))

        mutated = copy.deepcopy(data4)
        mutated["lifecycle"][0]["value"] = "foundations"
        mutations.append((DATA4_SOURCE, mutated))
        mutated = copy.deepcopy(data4)
        mutated["lifecycle"][0]["as_of_date"] = "2024-11-19"
        mutations.append((DATA4_SOURCE, mutated))
        mutated = copy.deepcopy(data4)
        mutated["capacities"] = [{"forbidden": "90 MW is untyped campus power"}]
        mutations.append((DATA4_SOURCE, mutated))
        mutated = copy.deepcopy(data4)
        mutated["project"]["stable_key"] = "curated:data4-ath1-paiania-campus:second-data-center"
        mutations.append((DATA4_SOURCE, mutated))
        mutated = copy.deepcopy(data4)
        mutated["project"]["roles"] = {"operator": ["DATA4"]}
        mutations.append((DATA4_SOURCE, mutated))
        mutated = copy.deepcopy(data4)
        mutated["campus"]["coordinates"] = {
            "latitude": 37.95,
            "longitude": 23.85,
        }
        mutations.append((DATA4_SOURCE, mutated))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
