from __future__ import annotations

import copy
from contextlib import ExitStack
from collections.abc import Iterable, Sequence
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "sources"
RETRIEVED_AT = "2026-07-20T09:18:30Z"
V44_NAME = "open-seed-2026-07-20-v44.json"
V44_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"

HKG_V1 = "curated-official-2026-07-20-goodman-hkg09-kwai-chung.json"
HKG_V2 = "curated-official-2026-07-20-goodman-hkg09-kwai-chung-v2.json"
SYD_V1 = "curated-official-2026-07-20-goodman-syd01-macquarie-park.json"
SYD_V2 = "curated-official-2026-07-20-goodman-syd01-macquarie-park-v2.json"

HKG_CAMPUS = "curated:goodman-hkg09-kwai-chung-data-centre"
HKG_PROJECT = f"{HKG_CAMPUS}:current-redevelopment"
SYD_CAMPUS = "curated:goodman-syd01-macquarie-park-data-centre"
SYD_PROJECT = f"{SYD_CAMPUS}:current-single-building-development"

HKG_NEWS = "goodman-hkg09-commencement-2026-07-15-captured-2026-07-20"
HKG_PIPELINE = "goodman-hk-global-data-centre-pipeline-captured-2026-07-20"
SYD_NEWS = "goodman-syd01-construction-2026-03-02-captured-2026-07-20"
SYD_PROPERTY = "goodman-syd01-property-page-captured-2026-07-20"
AU_PIPELINE = "goodman-au-global-data-centre-pipeline-captured-2026-07-20"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    HKG_V2: {
        "bytes": 18_236,
        "sha256": "e4e0f0c9db3ce6295696427e425a41cc458441cc06d9413e8b6cab50a40367d1",
        "campus": HKG_CAMPUS,
        "project": HKG_PROJECT,
        "v1": HKG_V1,
        "evidence": {HKG_NEWS, HKG_PIPELINE},
    },
    SYD_V2: {
        "bytes": 25_551,
        "sha256": "4667aea59067cd587bba475d9c42f26ac08e4edbdac058412b5a8df8a738d660",
        "campus": SYD_CAMPUS,
        "project": SYD_PROJECT,
        "v1": SYD_V1,
        "evidence": {SYD_NEWS, SYD_PROPERTY, AU_PIPELINE},
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    HKG_NEWS: {
        "url": (
            "https://hk.goodman.com/en/about-goodman/media-centre/news/2026/"
            "20260716-goodman-advances-hkg09-groundbreaking"
        ),
        "canonical": (
            "https://hk.goodman.com/about-goodman/media-centre/news/2026/"
            "20260716-goodman-advances-hkg09-groundbreaking"
        ),
        "published_at": "2026-07-15",
        "body_bytes": 206_515,
        "body_sha256": "20e2094f5d2af2bec605bf094444e909a6598cbcb3b85f4e9ac6610f013ef51e",
        "raw_bytes": 38_138,
        "raw_sha256": "8880962cb45887a67ae0374538e67b229d9b99fabbbbc5c5ca045a119cb3fe63",
        "header_bytes": 12_969,
        "header_sha256": "a571e61cbcf183d3a7195c9c39a57d2414fb7c6cb1519a8ab44825e5c4e31e5e",
        "header_count": 21,
        "facts_bytes": 1_267,
        "facts_sha256": "26371608d94581b6234c9a0579e6f6219e08fb88741e20bfe7caf3cb4f0424a8",
        "http_date": "2026-07-20T09:18:29Z",
    },
    HKG_PIPELINE: {
        "url": (
            "https://hk.goodman.com/our-properties/data-centres/"
            "global-data-centre-pipeline"
        ),
        "canonical": (
            "https://hk.goodman.com/our-properties/data-centres/"
            "global-data-centre-pipeline"
        ),
        "published_at": None,
        "body_bytes": 272_505,
        "body_sha256": "b5f76126cd9beb317eebcc1fd1579f7a1bd855dbb5584c32e342add9bb7353f5",
        "raw_bytes": 46_575,
        "raw_sha256": "bb24b29c0e25fb711574a916b8f782f482a2666aaefa386c5e3265ab1df29426",
        "header_bytes": 13_031,
        "header_sha256": "4376b5077ee50fe2087dfbb9ed435f4deac68ea76a6d48e5ef0f99caa1f4f60b",
        "header_count": 22,
        "facts_bytes": 1_205,
        "facts_sha256": "c7de8ee99839fb50da10c8b6663840875fd3f61c7cff834228bd4117462a9035",
        "http_date": "2026-07-20T09:18:29Z",
    },
    SYD_NEWS: {
        "url": (
            "https://au.goodman.com/en/about-goodman/media-centre/news/2026/"
            "syd01-construction"
        ),
        "canonical": (
            "https://au.goodman.com/about-goodman/media-centre/news/2026/"
            "syd01-construction"
        ),
        "published_at": "2026-03-02",
        "body_bytes": 208_108,
        "body_sha256": "7b73aa2671db45451a93718740f46881a4386011d94104b8281bc68479aeb472",
        "raw_bytes": 39_887,
        "raw_sha256": "723faac8e8da90041c7ae50c9cffb1e3f885de084c0dc785105792e20da85673",
        "header_bytes": 13_027,
        "header_sha256": "8af4ece82f456609b1f66358ad8f175a40c3341dbfb3f474073afbd27ec3ad1c",
        "header_count": 22,
        "facts_bytes": 1_211,
        "facts_sha256": "48c7af082a3215ba95fcbd81c2c5273ecf5608e40ae2ffac0af5afa1a5de05df",
        "http_date": "2026-07-20T09:18:30Z",
    },
    SYD_PROPERTY: {
        "url": (
            "https://au.goodman.com/en/our-properties/properties-for-lease/"
            "goodman-syd01"
        ),
        "canonical": (
            "https://au.goodman.com/our-properties/properties-for-lease/"
            "goodman-syd01"
        ),
        "published_at": None,
        "body_bytes": 261_669,
        "body_sha256": "c02900e0abb8cd5a3aabdca24a8dec28b9e4fb111b59b1731be83c6aae95a45b",
        "raw_bytes": 48_429,
        "raw_sha256": "110b4d38969afa64c6c8dc9a1b6df21e1a115e98704c318f26612beea40da245",
        "header_bytes": 12_968,
        "header_sha256": "eb75cbe7f680847b6b30b6c3e5ce4770543d25260c78875422e322e8319d93e8",
        "header_count": 21,
        "facts_bytes": 1_199,
        "facts_sha256": "9212484847bea37516baaeeeb84a4415d3792a2289fd4e8c9209300cc607a822",
        "http_date": "2026-07-20T09:18:30Z",
    },
    AU_PIPELINE: {
        "url": (
            "https://au.goodman.com/en/our-properties/data-centres/"
            "global-data-centre-pipeline"
        ),
        "canonical": (
            "https://au.goodman.com/our-properties/data-centres/"
            "global-data-centre-pipeline"
        ),
        "published_at": None,
        "body_bytes": 268_963,
        "body_sha256": "fd157c6d5cf26937ef5972330b55d702ac6efe17c3931a3399ef3839f0df2ee8",
        "raw_bytes": 46_446,
        "raw_sha256": "fdc083871ae669189735320cd0607cf22a9d3ed4ee1318b7da54ed6662ddd113",
        "header_bytes": 12_968,
        "header_sha256": "b1ad996ad241e3d08b23eea00e79c9b1b5bb21e43f7baffe016d7f7d49544393",
        "header_count": 21,
        "facts_bytes": 1_211,
        "facts_sha256": "eedeff4d10859ea896c5af0d0239f5e5a234d016fc72e4474c1601c7f53f1814",
        "http_date": "2026-07-20T09:18:30Z",
    },
}

OTHER_GOODMAN_Q3 = (
    "curated-official-2026-07-20-goodman-ams01-amsterdam.json",
    "curated-official-2026-07-20-goodman-fra02-frankfurt.json",
    "curated-official-2026-07-20-goodman-hkg10-tsuen-wan.json",
    "curated-official-2026-07-20-goodman-lax01-los-angeles.json",
    "curated-official-2026-07-20-goodman-par01-paris.json",
    "curated-official-2026-07-20-goodman-par02-paris.json",
    "curated-official-2026-07-20-goodman-ty005-tokyo.json",
    "curated-official-2026-07-20-goodman-ty006-tokyo.json",
)
NEXT_SELECTION = (*OTHER_GOODMAN_Q3, HKG_V2, SYD_V2)


class GoodmanHkg09Syd01V2CuratedTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((SOURCES_DIR / name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Goodman v2 curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _selection_claims(
        self,
        names: Iterable[str],
    ) -> tuple[dict[tuple[str, str], str], dict[str, tuple[str, str, str]]]:
        entities: dict[tuple[str, str], str] = {}
        evidence: dict[str, tuple[str, str, str]] = {}
        for name in names:
            document = self._load(name)
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if not isinstance(entity, dict):
                    continue
                claim = (kind, entity["stable_key"])
                if claim in entities:
                    raise ValueError(
                        f"stable-key source-selection collision: {entities[claim]} and "
                        f"{name} claim {kind} {entity['stable_key']}"
                    )
                entities[claim] = name
            for item in document.get("evidence", []):
                fingerprint = (
                    item["content_hash"],
                    item["source_url"],
                    item["publisher"],
                )
                prior = evidence.get(item["key"])
                if prior is not None and prior != fingerprint:
                    raise ValueError(
                        f"conflicting evidence-key source-selection collision: "
                        f"{item['key']}"
                    )
                evidence[item["key"]] = fingerprint
        return entities, evidence

    def _state(
        self,
        names: Sequence[str],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in names:
                            document = self._load(name)
                            retrieved_at = document["evidence"][0]["retrieved_at"]
                            result = CuratedOfficialSourceAdapter().import_file(
                                connection,
                                SOURCES_DIR / name,
                                retrieved_at=retrieved_at,
                            )
                            self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, source_url, retrieved_at FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, as_of_date, recorded_at",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence, notes "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model FROM "
                    "operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key, operating_model",
                    "SELECT entities.stable_key, workload FROM workload_observations "
                    "JOIN entities ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key, workload",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _import_document(self, name: str, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            source_path = Path(temporary) / name
            source_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapter().import_file(
                    connection,
                    source_path,
                    retrieved_at=RETRIEVED_AT,
                )
            finally:
                connection.close()

    def _assert_semantic_contract(self, documents: dict[str, dict[str, Any]]) -> None:
        hkg = documents[HKG_V2]
        syd = documents[SYD_V2]

        self.assertEqual(hkg["campus"]["stable_key"], HKG_CAMPUS)
        self.assertEqual(hkg["project"]["stable_key"], HKG_PROJECT)
        self.assertEqual(hkg["campus"]["address"], "Kwai Chung, Hong Kong")
        self.assertEqual(hkg["project"]["address"], "Kwai Chung, Hong Kong")
        self.assertEqual(
            hkg["campus"]["roles"],
            {"developer": ["Goodman Group"]},
        )
        self.assertEqual(hkg["project"]["roles"], hkg["campus"]["roles"])
        self.assertEqual(
            hkg["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": HKG_NEWS,
                    "as_of_date": "2026-07-15",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            [
                (
                    row["metric"],
                    row["stage"],
                    row["low"],
                    row["base"],
                    row["high"],
                    row["evidence_key"],
                    row["target_date"],
                )
                for row in hkg["capacities"]
            ],
            [
                ("critical_it_mw", "planned", 28, 28, 28, HKG_PIPELINE, None),
                ("grid_connection_mw", "contracted", 50, 50, 50, HKG_PIPELINE, None),
            ],
        )

        self.assertEqual(syd["campus"]["stable_key"], SYD_CAMPUS)
        self.assertEqual(syd["project"]["stable_key"], SYD_PROJECT)
        self.assertEqual(syd["campus"]["name"], "Goodman SYD01 Artarmon Data Centre")
        self.assertEqual(
            syd["campus"]["address"],
            "2-8 Lanceley Place, Artarmon, NSW, 2064, Australia",
        )
        self.assertEqual(syd["project"]["address"], syd["campus"]["address"])
        self.assertEqual(
            syd["campus"]["roles"],
            {
                "developer": ["Goodman Group"],
                "operator": ["Goodman Group"],
            },
        )
        self.assertEqual(syd["project"]["roles"], syd["campus"]["roles"])
        self.assertEqual(
            syd["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": SYD_PROPERTY,
                    "as_of_date": "2026-07-20",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            [
                (
                    row["metric"],
                    row["stage"],
                    row["low"],
                    row["base"],
                    row["high"],
                    row["evidence_key"],
                    row["target_date"],
                )
                for row in syd["capacities"]
            ],
            [
                ("critical_it_mw", "planned", 61, 61, 61, SYD_PROPERTY, None),
                ("grid_connection_mw", "contracted", 90, 90, 90, SYD_PROPERTY, None),
            ],
        )

        for document in documents.values():
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            for entity in (document["campus"], document["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")

    def test_sources_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        expected_fields = {
            "schema_version",
            "evidence",
            "campus",
            "project",
            "lifecycle",
            "operating_models",
            "workloads",
            "capacities",
        }
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = SOURCES_DIR / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertTrue(stat.S_ISREG(path.stat().st_mode))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(path.stat().st_size, expected["bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(set(document), expected_fields)
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(
                    {item["key"] for item in document["evidence"]},
                    expected["evidence"],
                )

    def test_capture_contract_is_exact_first_party_and_credential_safe(self) -> None:
        evidence = {
            item["key"]: item
            for name in SOURCE_SPECS
            for item in self._load(name)["evidence"]
        }
        self.assertEqual(set(evidence), set(CAPTURES))
        source_text = "\n".join(
            (SOURCES_DIR / name).read_text(encoding="utf-8")
            for name in SOURCE_SPECS
        )
        self.assertNotIn("__cf_bm=", source_text)
        forbidden_metadata_keys = {
            "authorization",
            "cookie",
            "local_ip",
            "local_port",
            "primary_ip",
            "remote_ip",
            "remote_port",
            "set-cookie",
        }
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f'{expected["body_bytes"]}-byte',
                    metadata["content_hash_scope"],
                )
                self.assertEqual(
                    metadata["content_hash_verification"],
                    "fetched_bytes_sha256",
                )
                self.assertIn(
                    f'{expected["raw_bytes"]}-byte',
                    metadata["capture_raw_body_scope"],
                )
                self.assertEqual(
                    metadata["capture_raw_body_sha256"],
                    expected["raw_sha256"],
                )
                self.assertIn(
                    f'{expected["header_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"],
                    expected["header_sha256"],
                )
                self.assertIn(
                    f'{expected["facts_bytes"]}-byte',
                    metadata["capture_facts_scope"],
                )
                self.assertEqual(
                    metadata["capture_facts_sha256"],
                    expected["facts_sha256"],
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
                self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
                self.assertEqual(metadata["content_encoding_as_received"], "gzip")
                self.assertIsNone(metadata["http_content_length_bytes_as_received"])
                self.assertEqual(
                    metadata["download_size_bytes_as_received"],
                    expected["raw_bytes"],
                )
                self.assertEqual(metadata["decoded_body_bytes"], expected["body_bytes"])
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(metadata["response_header_count"], expected["header_count"])
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["canonical"])
                self.assertTrue(
                    forbidden_metadata_keys.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )
                self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
                self.assertIn("anonymous", metadata["retrieval_method"])
                self.assertIn("No retries", metadata["retrieval_method"])
                self.assertIn("Neither request supplied", metadata["request_credentials_guardrail"])

    def test_identity_location_roles_and_historical_supersession_are_exact(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_SPECS}
        self._assert_semantic_contract(documents)
        hkg_metadata = {item["key"]: item["metadata"] for item in documents[HKG_V2]["evidence"]}
        syd_metadata = {item["key"]: item["metadata"] for item in documents[SYD_V2]["evidence"]}

        self.assertEqual(hkg_metadata[HKG_NEWS]["reported_locality"], "Kwai Chung, Hong Kong SAR")
        self.assertIn("being developed by Goodman", hkg_metadata[HKG_NEWS]["reported_developer_wording"])
        self.assertEqual(
            hkg_metadata[HKG_NEWS]["historical_q3_snapshot_as_reported"]["prior_curated_status"],
            "site_preparation",
        )
        self.assertIn("must select v2 instead", hkg_metadata[HKG_NEWS]["supersession_guardrail"])

        self.assertEqual(
            syd_metadata[SYD_PROPERTY]["reported_exact_address"],
            "2-8 Lanceley Place, Artarmon, NSW, 2064, Australia",
        )
        self.assertEqual(
            syd_metadata[SYD_PROPERTY]["historical_q3_snapshot_as_reported"]["reported_locality"],
            "Macquarie Park Availability Zone, Sydney, Australia",
        )
        self.assertIn("same stable SYD01 identity", syd_metadata[SYD_PROPERTY]["historical_reconciliation_guardrail"])
        self.assertIn("intended operator", syd_metadata[SYD_PROPERTY]["role_scope"])

    def test_lifecycle_is_current_generic_construction_only(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_SPECS}
        self._assert_semantic_contract(documents)
        hkg = {item["key"]: item["metadata"] for item in documents[HKG_V2]["evidence"]}
        syd = {item["key"]: item["metadata"] for item in documents[SYD_V2]["evidence"]}
        self.assertEqual(hkg[HKG_NEWS]["article_release_timestamp_as_reported"], "2026-07-15T14:00:00Z")
        self.assertIn("officially marked commencement", hkg[HKG_NEWS]["reported_construction_wording"])
        self.assertEqual(syd[SYD_NEWS]["article_release_timestamp_as_reported"], "2026-03-02T13:00:00Z")
        self.assertEqual(syd[SYD_PROPERTY]["reported_current_status"], "under construction")
        for metadata in (hkg[HKG_NEWS], syd[SYD_NEWS]):
            for unsupported in (
                "site preparation",
                "clearing",
                "civil works",
                "excavation",
                "foundations",
                "shell",
                "MEP",
                "energization",
                "commissioning",
                "completion",
                "occupancy",
                "operation",
            ):
                self.assertIn(unsupported, metadata["construction_scope"])
        self.assertIn("structure", hkg[HKG_NEWS]["construction_scope"])
        self.assertIn("structural frame", syd[SYD_NEWS]["construction_scope"])

    def test_typed_power_and_nested_phase_arithmetic_are_nonadditive(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_SPECS}
        self._assert_semantic_contract(documents)
        hkg = {item["key"]: item["metadata"] for item in documents[HKG_V2]["evidence"]}
        syd = {item["key"]: item["metadata"] for item in documents[SYD_V2]["evidence"]}

        self.assertEqual(hkg[HKG_PIPELINE]["reported_hkg09_it_power_mw_approximate"], 28)
        self.assertEqual(hkg[HKG_PIPELINE]["reported_hkg09_primary_power_secured_mw"], 50)
        self.assertIn("never added", hkg[HKG_PIPELINE]["capacity_scope"])
        self.assertIn("non-additive", hkg[HKG_PIPELINE]["nonaggregation_guardrail"])
        self.assertIn("untyped", hkg[HKG_NEWS]["ambiguous_50_mw_guardrail"])

        self.assertEqual(syd[SYD_PROPERTY]["reported_total_it_capacity_mw"], 61)
        self.assertEqual(syd[SYD_PROPERTY]["reported_phase_count"], 5)
        self.assertEqual(syd[SYD_PROPERTY]["reported_each_phase_it_mw"], 12.2)
        self.assertEqual(syd[SYD_PROPERTY]["reported_secured_primary_power_mw"], 90)
        self.assertEqual(5 * 12.2, 61)
        self.assertIn("comprise", syd[SYD_PROPERTY]["phase_nonaggregation_guardrail"])
        self.assertIn("metadata only", syd[SYD_PROPERTY]["phase_nonaggregation_guardrail"])
        self.assertEqual(len(documents[SYD_V2]["capacities"]), 2)

    def test_anonymous_prelease_marketing_and_energy_do_not_leak(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_SPECS}
        self._assert_semantic_contract(documents)
        hkg_metadata = {item["key"]: item["metadata"] for item in documents[HKG_V2]["evidence"]}
        syd_metadata = {item["key"]: item["metadata"] for item in documents[SYD_V2]["evidence"]}
        self.assertEqual(
            hkg_metadata[HKG_NEWS]["reported_prelease_description"],
            "pre-leased to a leading Singapore-based data centre operator",
        )
        self.assertIn("no tenant identity", hkg_metadata[HKG_NEWS]["prelease_guardrail"])
        self.assertNotIn("tenant", documents[HKG_V2]["project"]["roles"])
        self.assertNotIn("operator", documents[HKG_V2]["project"]["roles"])
        self.assertIn("PUE and WUE", syd_metadata[SYD_NEWS]["efficiency_guardrail"])

        for document in documents.values():
            metrics = {row["metric"] for row in document["capacities"]}
            stages = {row["stage"] for row in document["capacities"]}
            self.assertEqual(metrics, {"critical_it_mw", "grid_connection_mw"})
            self.assertNotIn("measured", stages)
            self.assertNotIn("annual_energy_mwh", metrics)
            self.assertNotIn("gross_facility_mw", metrics)
            self.assertNotIn("generation_nameplate_mw", metrics)
            self.assertNotIn("pue", metrics)
            text = json.dumps(document, ensure_ascii=False)
            self.assertIn("MW is not converted to MWh", text)
            self.assertIn("current electrical load", text)

    def test_each_source_imports_offline_valid_and_idempotent(self) -> None:
        for name in SOURCE_SPECS:
            with self.subTest(source=name):
                once = self._state((name,))
                self.assertEqual(self._state((name,), repetitions=2), once)
                entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = once
                self.assertEqual(len(entities), 2)
                self.assertEqual(len(evidence), len(SOURCE_SPECS[name]["evidence"]))
                self.assertEqual(len(snapshots), 2)
                self.assertEqual(len(lifecycle), 1)
                self.assertEqual(len(capacities), 2)
                self.assertEqual(models, ())
                self.assertEqual(workloads, ())
                self.assertEqual(len(projects), 1)

    def test_v2_pair_import_is_offline_order_independent_and_exact(self) -> None:
        forward = self._state((HKG_V2, SYD_V2))
        self.assertEqual(self._state((SYD_V2, HKG_V2)), forward)
        self.assertEqual(self._state((HKG_V2, SYD_V2), repetitions=2), forward)
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = forward
        self.assertEqual(len(entities), 4)
        self.assertEqual(len(evidence), 5)
        self.assertEqual(len(snapshots), 4)
        self.assertEqual(
            {row[0:3] for row in lifecycle},
            {
                (HKG_PROJECT, "under_construction", "2026-07-15"),
                (SYD_PROJECT, "under_construction", "2026-07-20"),
            },
        )
        self.assertEqual(
            {(row[0], row[1], row[2], row[5]) for row in capacities},
            {
                (HKG_PROJECT, "critical_it_mw", "planned", 28.0),
                (HKG_PROJECT, "grid_connection_mw", "contracted", 50.0),
                (SYD_PROJECT, "critical_it_mw", "planned", 61.0),
                (SYD_PROJECT, "grid_connection_mw", "contracted", 90.0),
            },
        )
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(
            projects,
            ((HKG_PROJECT, HKG_CAMPUS), (SYD_PROJECT, SYD_CAMPUS)),
        )

    def test_next_selection_keeps_other_eight_and_is_order_independent(self) -> None:
        self._selection_claims(NEXT_SELECTION)
        forward = self._state(NEXT_SELECTION)
        self.assertEqual(self._state(tuple(reversed(NEXT_SELECTION))), forward)
        self.assertEqual(self._state(NEXT_SELECTION, repetitions=2), forward)
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = forward
        self.assertEqual(len(entities), 20)
        self.assertEqual(len(evidence), 6)
        self.assertEqual(len(snapshots), 20)
        self.assertEqual(len(lifecycle), 10)
        self.assertEqual(len(capacities), 6)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(len(projects), 10)

    def test_v1_v2_collision_requires_replacement_and_v44_is_unchanged(self) -> None:
        next_entities, _ = self._selection_claims(NEXT_SELECTION)
        self.assertEqual(len(next_entities), 20)
        for v1, v2 in ((HKG_V1, HKG_V2), (SYD_V1, SYD_V2)):
            with self.subTest(v1=v1, v2=v2):
                with self.assertRaisesRegex(ValueError, "source-selection collision"):
                    self._selection_claims((*NEXT_SELECTION, v1))
                old = self._load(v1)
                new = self._load(v2)
                self.assertEqual(old["campus"]["stable_key"], new["campus"]["stable_key"])
                self.assertEqual(old["project"]["stable_key"], new["project"]["stable_key"])

        claimed = {HKG_CAMPUS, HKG_PROJECT, SYD_CAMPUS, SYD_PROJECT}
        occurrences: dict[str, set[str]] = {key: set() for key in claimed}
        evidence_occurrences: dict[str, set[str]] = {key: set() for key in CAPTURES}
        for path in sorted(SOURCES_DIR.glob("curated-official-*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if isinstance(entity, dict) and entity["stable_key"] in occurrences:
                    occurrences[entity["stable_key"]].add(path.name)
            for item in document.get("evidence", []):
                if item["key"] in evidence_occurrences:
                    evidence_occurrences[item["key"]].add(path.name)
        self.assertEqual(occurrences[HKG_CAMPUS], {HKG_V1, HKG_V2})
        self.assertEqual(occurrences[HKG_PROJECT], {HKG_V1, HKG_V2})
        self.assertEqual(occurrences[SYD_CAMPUS], {SYD_V1, SYD_V2})
        self.assertEqual(occurrences[SYD_PROJECT], {SYD_V1, SYD_V2})
        for key, paths in evidence_occurrences.items():
            expected_source = HKG_V2 if key in {HKG_NEWS, HKG_PIPELINE} else SYD_V2
            self.assertEqual(paths, {expected_source})

        v44_path = SOURCES_DIR / V44_NAME
        self.assertEqual(hashlib.sha256(v44_path.read_bytes()).hexdigest(), V44_SHA256)
        v44_text = v44_path.read_text(encoding="utf-8")
        for marker in (
            HKG_V1,
            HKG_V2,
            SYD_V1,
            SYD_V2,
            HKG_CAMPUS,
            HKG_PROJECT,
            SYD_CAMPUS,
            SYD_PROJECT,
            *CAPTURES,
        ):
            self.assertNotIn(marker, v44_text)

    def test_semantic_leakage_mutations_fail_the_focused_contract(self) -> None:
        original = {name: self._load(name) for name in SOURCE_SPECS}
        mutations: list[tuple[str, dict[str, dict[str, Any]]]] = []

        changed = copy.deepcopy(original)
        changed[HKG_V2]["lifecycle"][0]["value"] = "foundations"
        mutations.append(("hkg-start-promoted-to-foundations", changed))

        changed = copy.deepcopy(original)
        changed[HKG_V2]["campus"]["address"] = "Invented street, Kwai Chung"
        mutations.append(("hkg-street-invented", changed))

        changed = copy.deepcopy(original)
        changed[HKG_V2]["project"]["roles"]["operator"] = ["Goodman Group"]
        mutations.append(("hkg-goodman-operator-invented", changed))

        changed = copy.deepcopy(original)
        changed[HKG_V2]["project"]["roles"]["tenant"] = ["Unnamed operator"]
        mutations.append(("anonymous-tenant-promoted", changed))

        changed = copy.deepcopy(original)
        changed[HKG_V2]["capacities"][0]["base"] = 50
        mutations.append(("untyped-fifty-promoted-to-it", changed))

        changed = copy.deepcopy(original)
        changed[SYD_V2]["campus"]["address"] = (
            "Macquarie Park Availability Zone, Sydney, Australia"
        )
        mutations.append(("historical-zone-overwrites-address", changed))

        changed = copy.deepcopy(original)
        changed[SYD_V2]["capacities"].append(
            {
                **changed[SYD_V2]["capacities"][0],
                "low": 12.2,
                "base": 12.2,
                "high": 12.2,
            }
        )
        mutations.append(("phase-one-double-counted", changed))

        changed = copy.deepcopy(original)
        changed[SYD_V2]["workloads"] = [
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": SYD_NEWS,
                "as_of_date": "2026-03-02",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(("ai-demand-promoted-to-workload", changed))

        changed = copy.deepcopy(original)
        changed[SYD_V2]["capacities"].append(
            {
                **changed[SYD_V2]["capacities"][0],
                "metric": "pue",
                "unit": "ratio",
                "low": 1.2,
                "base": 1.2,
                "high": 1.2,
            }
        )
        mutations.append(("unquantified-pue-invented", changed))

        changed = copy.deepcopy(original)
        changed[SYD_V2]["project"]["coordinates"] = {
            "latitude": -33.8,
            "longitude": 151.2,
        }
        mutations.append(("coordinate-inferred", changed))

        for label, documents in mutations:
            with self.subTest(mutation=label), self.assertRaises(AssertionError):
                self._assert_semantic_contract(documents)

    def test_import_rejects_retrieval_drift_coordinates_and_weak_status(self) -> None:
        hkg = self._load(HKG_V2)
        changed = copy.deepcopy(hkg)
        changed["evidence"][0]["retrieved_at"] = "2026-07-20T09:18:31Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(HKG_V2, changed)

        changed = copy.deepcopy(hkg)
        changed["campus"]["coordinates"] = {
            "latitude": 22.36,
            "longitude": 114.13,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(HKG_V2, changed)

        changed = copy.deepcopy(hkg)
        changed["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(HKG_V2, changed)


if __name__ == "__main__":
    unittest.main()
