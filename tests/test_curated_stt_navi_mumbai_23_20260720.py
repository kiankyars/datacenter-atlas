from __future__ import annotations

import copy
import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T07:16:00Z"
AS_OF_DATE = "2024-11-07"
SOURCE_URL = (
    "https://www.linkedin.com/posts/sttgdcindia_sttgdcindia-aiready-"
    "datacentre-activity-7260209391721668609-d3XJ"
)
EVIDENCE_KEY = (
    "stt-navi-mumbai-2-3-construction-start-2024-11-07-"
    "captured-2026-07-20"
)
LOCALITY = "Navi Mumbai, Maharashtra, India"
SOURCE_SPECS = {
    "curated-official-2026-07-20-stt-navi-mumbai-2.json": {
        "bytes": 8_693,
        "sha256": "c39ef82aa21969f405a6c3750348f517d26da9169881371e8bd29247a19c69d6",
        "campus_key": "curated:stt-navi-mumbai-2-locality-scoped-campus",
        "campus_name": "STT Navi Mumbai 2 Locality-Scoped Campus",
        "project_key": (
            "curated:stt-navi-mumbai-2-locality-scoped-campus:"
            "stt-navi-mumbai-2"
        ),
        "project_name": "STT Navi Mumbai 2",
    },
    "curated-official-2026-07-20-stt-navi-mumbai-3.json": {
        "bytes": 8_693,
        "sha256": "0387265e803a16bb3bb43ffc869cc53de07071b04c4c5cee128f32e001e8e7c1",
        "campus_key": "curated:stt-navi-mumbai-3-locality-scoped-campus",
        "campus_name": "STT Navi Mumbai 3 Locality-Scoped Campus",
        "project_key": (
            "curated:stt-navi-mumbai-3-locality-scoped-campus:"
            "stt-navi-mumbai-3"
        ),
        "project_name": "STT Navi Mumbai 3",
    },
}
SOURCE_ORDER = tuple(SOURCE_SPECS)
ENTITY_KEYS = {
    value[key]
    for value in SOURCE_SPECS.values()
    for key in ("campus_key", "project_key")
}
PROJECT_KEYS = {value["project_key"] for value in SOURCE_SPECS.values()}
PROJECT_TARGETS = {
    (value["project_key"], value["campus_key"])
    for value in SOURCE_SPECS.values()
}
SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class SttNaviMumbai23CuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated source import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _build(
        self,
        source_order: Iterable[str],
        *,
        repeat: int = 1,
    ) -> tuple[
        dict[str, tuple[tuple[Any, ...], ...]],
        tuple[tuple[int, int, tuple[str, ...]], ...],
    ]:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            results: list[tuple[int, int, tuple[str, ...]]] = []
            try:
                for _ in range(repeat):
                    for name in source_order:
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                        results.append(
                            (
                                result.entities_created,
                                result.evidence_created,
                                result.warnings,
                            )
                        )
                self.assertEqual(validate_database(connection), [])
                return self._state(connection), tuple(results)
            finally:
                connection.close()

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            source = Path(temporary) / "source.json"
            source.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapter().import_file(
                    connection,
                    source,
                    retrieved_at=RETRIEVED_AT,
                )
            finally:
                connection.close()

    def test_sources_are_canonical_hash_pinned_regular_files(self) -> None:
        documents: dict[str, dict[str, Any]] = {}
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
            path = self._path(name)
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertTrue(stat.S_ISREG(path.stat().st_mode))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            raw = path.read_bytes()
            self.assertEqual(len(raw), expected["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["sha256"])
            text = raw.decode("utf-8")
            document = json.loads(text)
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            self.assertEqual(set(document), expected_fields)
            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(len(document["evidence"]), 1)
            documents[name] = document

        self.assertEqual(
            documents[SOURCE_ORDER[0]]["evidence"][0],
            documents[SOURCE_ORDER[1]]["evidence"][0],
        )

    def test_exact_official_capture_contract_is_closed_and_byte_bound(self) -> None:
        evidence = self._load(SOURCE_ORDER[0])["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(
            evidence["publisher"],
            "ST Telemedia Global Data Centres (India)",
        )
        self.assertEqual(evidence["source_family"], "stt_gdc_india_linkedin_company_posts")
        self.assertEqual(evidence["title"], "Another groundbreaking milestone achieved!")
        self.assertEqual(evidence["source_url"], SOURCE_URL)
        self.assertEqual(evidence["published_at"], "2024-11-07T08:40:07.136Z")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(
            evidence["content_hash"],
            "d80749a74fd4e0b2b6fe0485dfaff11ff0d7f463e8e7239f6cb313bc7685dbb1",
        )
        self.assertIn("193415-byte", metadata["content_hash_scope"])
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn("5348-byte", metadata["capture_headers_scope"])
        self.assertEqual(
            metadata["capture_headers_sha256"],
            "b66fd1ee6116bb28661fb88ccb529040fdbe76d0cf78fa9ef8d676b35eda8917",
        )
        self.assertIn("17696-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"],
            "448511352004319c12f57cc63c7b24b041bb4d381ca8058b4ce74a18de4b2d52",
        )
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=utf-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertEqual(metadata["http_content_length_bytes_as_received"], 23_042)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 23_042)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        for marker in ("rel=canonical", "og:url", "VideoObject @id"):
            self.assertIn(marker, metadata["canonical_url_basis"])
        self.assertIn("supplied no Authorization", metadata["request_credentials_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])

    def test_structured_publication_fields_and_textual_scope_are_exact(self) -> None:
        evidence = self._load(SOURCE_ORDER[0])["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(metadata["structured_type"], "VideoObject")
        self.assertEqual(
            metadata["structured_date_published"],
            "2024-11-07T08:40:07.136Z",
        )
        self.assertEqual(
            metadata["structured_upload_date"],
            "2024-11-07T08:40:07.136Z",
        )
        self.assertEqual(
            metadata["structured_headline"],
            "Another groundbreaking milestone achieved!",
        )
        self.assertEqual(
            metadata["construction_wording_as_reported"],
            "We proudly marked the start of our STT Navi Mumbai 2 & STT Navi Mumbai 3 data centres",
        )
        self.assertIn("generic under_construction", metadata["status_scope"])
        for unsupported in (
            "site preparation",
            "foundations",
            "shell",
            "MEP",
            "energization",
            "commissioning",
            "operation",
            "current load",
        ):
            self.assertIn(unsupported, metadata["status_scope"])

    def test_two_exact_projects_use_distinct_nonphysical_locality_scopes(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_ORDER}
        observed_entities: set[str] = set()
        for name, document in documents.items():
            expected = SOURCE_SPECS[name]
            self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
            self.assertEqual(document["campus"]["name"], expected["campus_name"])
            self.assertEqual(document["project"]["stable_key"], expected["project_key"])
            self.assertEqual(document["project"]["name"], expected["project_name"])
            observed_entities.update(
                (document["campus"]["stable_key"], document["project"]["stable_key"])
            )
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], "India")
                self.assertEqual(entity["address"], LOCALITY)
                self.assertEqual(entity["roles"], {})
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
                self.assertEqual(entity["as_of_date"], AS_OF_DATE)
                self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(entity["confidence"], 0.99)
        self.assertEqual(observed_entities, ENTITY_KEYS)
        self.assertNotEqual(
            documents[SOURCE_ORDER[0]]["campus"]["stable_key"],
            documents[SOURCE_ORDER[1]]["campus"]["stable_key"],
        )
        metadata = documents[SOURCE_ORDER[0]]["evidence"][0]["metadata"]
        self.assertIn("technical grouping containers only", metadata["identity_scope"])
        self.assertIn("do not assert a shared physical campus", metadata["identity_scope"])
        self.assertIn("no source-verifiable street address", metadata["locality_guardrail"])

    def test_lifecycle_is_exactly_two_generic_project_starts(self) -> None:
        for name in SOURCE_ORDER:
            document = self._load(name)
            self.assertEqual(
                document["lifecycle"],
                [
                    {
                        "entity": "project",
                        "value": "under_construction",
                        "evidence_key": EVIDENCE_KEY,
                        "as_of_date": AS_OF_DATE,
                        "method": "authoritative_construction_start",
                        "confidence": 0.99,
                    }
                ],
            )
        self.assertEqual(
            sum(len(self._load(name)["lifecycle"]) for name in SOURCE_ORDER),
            2,
        )

    def test_comments_marketing_roles_energy_and_media_create_no_rows(self) -> None:
        for name in SOURCE_ORDER:
            document = self._load(name)
            evidence = document["evidence"][0]
            metadata = evidence["metadata"]
            self.assertEqual(document["campus"]["roles"], {})
            self.assertEqual(document["project"]["roles"], {})
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            evidence_fields = {
                key: value for key, value in evidence.items() if key != "metadata"
            }
            evidence_text = json.dumps(evidence_fields, sort_keys=True).lower()
            for excluded in ("110+", "three-data-centre", "dc1", "simultaneously"):
                self.assertNotIn(excluded, evidence_text)
            for marker in (
                "110+ MW",
                "three-data-centre campus",
                "DC1 being operational",
                "starting simultaneously",
            ):
                self.assertIn(marker, metadata["comment_guardrail"])
            self.assertIn("Roles remain empty", metadata["role_guardrail"])
            self.assertIn("no normalized workload", metadata["classification_guardrail"])
            self.assertIn("operating model", metadata["classification_guardrail"])
            self.assertIn("installed hardware", metadata["classification_guardrail"])
            self.assertIn("no source-level numeric capacity", metadata["capacity_energy_guardrail"])
            self.assertIn("No capacity or energy observation", metadata["capacity_energy_guardrail"])
            self.assertIn("computer vision", metadata["imagery_guardrail"])
            self.assertIn("contribute nothing", metadata["imagery_guardrail"])
            self.assertIn("was not downloaded", metadata["media_scope"])

    def test_offline_import_exact_delta_shared_evidence_and_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                before = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in SEMANTIC_TABLES
                }
                results = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in SOURCE_ORDER
                ]
                self.assertEqual(
                    [
                        (result.entities_created, result.evidence_created, result.warnings)
                        for result in results
                    ],
                    [(2, 1, ()), (2, 0, ())],
                )
                after = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in SEMANTIC_TABLES
                }
                expected_delta = {
                    "evidence": 1,
                    "entities": 4,
                    "campuses": 2,
                    "facilities": 0,
                    "buildings": 0,
                    "projects": 2,
                    "entity_snapshots": 4,
                    "lifecycle_observations": 2,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                }
                self.assertEqual(
                    {table: after[table] - before[table] for table in SEMANTIC_TABLES},
                    expected_delta,
                )
                evidence_rows = [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT content_hash, source_url, retrieved_at, metadata_json FROM evidence"
                    )
                ]
                self.assertEqual(len(evidence_rows), 1)
                self.assertEqual(
                    evidence_rows[0][:3],
                    (
                        "d80749a74fd4e0b2b6fe0485dfaff11ff0d7f463e8e7239f6cb313bc7685dbb1",
                        SOURCE_URL,
                        RETRIEVED_AT,
                    ),
                )
                self.assertEqual(
                    json.loads(evidence_rows[0][3])["curated_record_key"],
                    EVIDENCE_KEY,
                )
                links = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT project.stable_key, target.stable_key
                        FROM projects AS p
                        JOIN entities AS project ON project.id = p.entity_id
                        JOIN entities AS target ON target.id = p.target_entity_id
                        """
                    )
                }
                self.assertEqual(links, PROJECT_TARGETS)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_database_payload_has_only_locality_tags_and_generic_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in SOURCE_ORDER:
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                snapshots = [
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, s.name, s.latitude, s.longitude,
                               s.geometry_json, s.tags_json, s.as_of_date,
                               s.recorded_at, s.method, s.confidence
                        FROM entity_snapshots AS s
                        JOIN entities AS e ON e.id = s.entity_id
                        ORDER BY e.stable_key
                        """
                    )
                ]
                self.assertEqual(len(snapshots), 4)
                for stable_key, name, latitude, longitude, geometry, tags, as_of, recorded, method, confidence in snapshots:
                    self.assertIn(stable_key, ENTITY_KEYS)
                    self.assertTrue(name.startswith("STT Navi Mumbai"))
                    self.assertIsNone(latitude)
                    self.assertIsNone(longitude)
                    self.assertIsNone(geometry)
                    self.assertEqual(
                        json.loads(tags),
                        {
                            "address": LOCALITY,
                            "country": "India",
                            "source_dataset": "curated_official_sources",
                        },
                    )
                    self.assertEqual(as_of, AS_OF_DATE)
                    self.assertEqual(recorded, RETRIEVED_AT)
                    self.assertEqual(method, "authoritative_locality")
                    self.assertEqual(confidence, 0.99)
                lifecycle = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, l.status, l.as_of_date, l.recorded_at,
                               l.method, l.confidence
                        FROM lifecycle_observations AS l
                        JOIN entities AS e ON e.id = l.entity_id
                        """
                    )
                }
                self.assertEqual(
                    lifecycle,
                    {
                        (
                            key,
                            "under_construction",
                            AS_OF_DATE,
                            RETRIEVED_AT,
                            "authoritative_construction_start",
                            0.99,
                        )
                        for key in PROJECT_KEYS
                    },
                )
                for table in (
                    "facilities",
                    "buildings",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                        table,
                    )
            finally:
                connection.close()

    def test_import_order_is_invariant_and_reimport_is_idempotent(self) -> None:
        forward, first_results = self._build(SOURCE_ORDER)
        reverse, reverse_results = self._build(reversed(SOURCE_ORDER))
        repeated, repeated_results = self._build(SOURCE_ORDER, repeat=2)
        self.assertEqual(first_results, ((2, 1, ()), (2, 0, ())))
        self.assertEqual(reverse_results, ((2, 1, ()), (2, 0, ())))
        self.assertEqual(
            repeated_results,
            ((2, 1, ()), (2, 0, ()), (0, 0, ()), (0, 0, ())),
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

    def test_entity_and_evidence_keys_do_not_collide_with_other_curated_sources(self) -> None:
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path.name in SOURCE_SPECS:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            for field in ("campus", "project"):
                entity = document.get(field)
                if entity is not None:
                    self.assertNotIn(entity["stable_key"], ENTITY_KEYS, path.name)
            for evidence in document.get("evidence", []):
                self.assertNotEqual(evidence["key"], EVIDENCE_KEY, path.name)

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load(SOURCE_ORDER[0]))
        document["evidence"][0]["retrieved_at"] = "2026-07-20T07:15:59Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_weak_construction_method(self) -> None:
        document = copy.deepcopy(self._load(SOURCE_ORDER[0]))
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load(SOURCE_ORDER[0]))
        document["campus"]["coordinates"] = {
            "latitude": 19.033,
            "longitude": 73.029,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
