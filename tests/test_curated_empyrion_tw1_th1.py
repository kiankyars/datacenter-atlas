from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
BASE_DEFINITION = "open-seed-2026-07-19-v21.json"
BASE_DEFINITION_SHA256 = (
    "4192fb1b2366f5fa86bbcc3ed57037a8c174755454da3b834ea08dadf6ed22f6"
)
TW1_SOURCE = "curated-official-2026-07-19-empyrion-tw1-taipei.json"
TH1_SOURCE = "curated-official-2026-07-19-empyrion-th1-bang-na.json"

SOURCES: dict[str, dict[str, Any]] = {
    TW1_SOURCE: {
        "sha256": "46214b54a0397a39c9f9d0519066d659652364677f7e0eb8a9e3d7089ed13c53",
        "evidence_key": (
            "empyrion-tw1-taipei-groundbreaking-2026-01-13-"
            "captured-2026-07-19"
        ),
        "published_at": "2026-01-13",
        "as_of_date": "2026-01-13",
        "country": "Taiwan",
        "address": "Neihu, Taipei, Taiwan",
        "campus_key": "curated:empyrion-tw1-taipei-data-center",
        "project_key": (
            "curated:empyrion-tw1-taipei-data-center:current-facility-build"
        ),
        "capacity": 7.0,
        "reported_power": 10,
        "area_key": "reported_area_square_metres",
        "area_value": 4260,
        "forecast": "Q4 2027",
    },
    TH1_SOURCE: {
        "sha256": "5dd87f17ac34309b936e0135cb10b691047541f78bdd425cef7b3beb3c4eccfb",
        "evidence_key": (
            "empyrion-th1-bang-na-groundbreaking-2026-05-07-"
            "captured-2026-07-19"
        ),
        "published_at": "2026-05-07",
        "as_of_date": "2026-05-07",
        "country": "Thailand",
        "address": "Bang Na, Bangkok, Thailand",
        "campus_key": "curated:empyrion-th1-bang-na-data-center",
        "project_key": (
            "curated:empyrion-th1-bang-na-data-center:current-facility-build"
        ),
        "capacity": 20.0,
        "reported_power": None,
        "area_key": "reported_site_area_square_metres_over",
        "area_value": 17000,
        "forecast": "Q3 2027",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    TW1_SOURCE: {
        "body_bytes": 278325,
        "content_hash": (
            "0ae2d638ff7785a09cd75cd5c045569a89a64d8ff656ee64131891a281da88a8"
        ),
        "headers_bytes": 1355,
        "headers_hash": (
            "452639e02f7f22a176a2d789c34300706ffa31ec0dc27d00b333c437b6702526"
        ),
        "writeout_bytes": 9796,
        "writeout_hash": (
            "afd455fd53ed9702c376f4af64ff643096fdc8d537db2355790389fcb4dae080"
        ),
        "download_bytes": 37083,
        "url": (
            "https://empyriondigital.com/empyrion-digital-breaks-ground-on-"
            "first-taiwan-data-centre-in-taipeis-neihu-technology-hub/"
        ),
    },
    TH1_SOURCE: {
        "body_bytes": 281569,
        "content_hash": (
            "4fe32da7fefeee4082243e77c8063c14f91a12b70cb41978376e8ae6e8593e7e"
        ),
        "headers_bytes": 1355,
        "headers_hash": (
            "7d4b2ebe4cd2990fd87afa3722c089415ae44bd40e648b65ce0aca50c9ba2ffa"
        ),
        "writeout_bytes": 9808,
        "writeout_hash": (
            "082271c2c6a82719964cd1a45eb169fb99d5ae6e36046e0ae0122eb0c19d908c"
        ),
        "download_bytes": 37702,
        "url": (
            "https://empyriondigital.com/empyrion-digital-breaks-ground-on-"
            "its-first-thailand-data-centre-in-bangkoks-bang-na-district/"
        ),
    },
}


class EmpyrionTw1Th1Tests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        capture = CAPTURES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], expected["evidence_key"])
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "Empyrion Digital")
        self.assertEqual(evidence["source_family"], "empyrion_digital_news")
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], "2026-07-19T20:52:34Z")
        self.assertEqual(evidence["content_hash"], capture["content_hash"])
        self.assertEqual(evidence["source_url"], capture["url"])

        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(capture["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], capture["headers_hash"])
        self.assertIn(
            str(capture["writeout_bytes"]), metadata["capture_curl_writeout_scope"]
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], capture["writeout_hash"]
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"], capture["download_bytes"]
        )
        self.assertEqual(metadata["response_http_date"], "2026-07-19T20:52:34Z")
        self.assertIsNone(metadata["http_last_modified_at"])
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], capture["url"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("exact response HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("under_construction", metadata["status_scope"])
        self.assertIn("mixed future", metadata["classification_guardrail"])
        self.assertIn("authoritative named locality", metadata["locality_guardrail"])
        self.assertIn("no current load", metadata["sustainability_guardrail"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("computer vision", metadata["imagery_guardrail"])
        self.assertEqual(metadata[expected["area_key"]], expected["area_value"])
        self.assertEqual(metadata["service_forecast_as_reported"], expected["forecast"])
        self.assertIn("context only", metadata["forecast_guardrail"])

        if name == TW1_SOURCE:
            self.assertEqual(metadata["reported_powered_capacity_mw"], 10)
            self.assertEqual(metadata["reported_scalable_it_load_mw"], 7)
            self.assertIn("not assigned a normalized metric", metadata["capacity_scope"])
            self.assertEqual(metadata["reported_storeys"], 5)
        else:
            self.assertEqual(metadata["reported_it_load_mw"], 20)
            self.assertEqual(
                metadata["secured_power_wording_as_reported"], "secured power allocation"
            )
            self.assertIn("no MW value", metadata["secured_power_guardrail"])
            self.assertIn("memorandum", metadata["role_guardrail"])

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], expected["evidence_key"])
            self.assertEqual(entity["as_of_date"], expected["as_of_date"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])

        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": expected["evidence_key"],
                    "as_of_date": expected["as_of_date"],
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(capacity["entity"], "project")
        self.assertEqual(capacity["metric"], "critical_it_mw")
        self.assertEqual(capacity["stage"], "planned")
        self.assertEqual(capacity["unit"], "MW")
        self.assertEqual(
            (capacity["low"], capacity["base"], capacity["high"]),
            (expected["capacity"],) * 3,
        )
        self.assertEqual(capacity["method"], "reported")
        self.assertEqual(capacity["confidence"], 0.99)
        self.assertEqual(capacity["evidence_key"], expected["evidence_key"])
        self.assertEqual(capacity["as_of_date"], expected["as_of_date"])
        self.assertIsNone(capacity["target_date"])
        self.assertIn("not current load", capacity["notes"])

    def _base_paths(self) -> list[Path]:
        definition_path = ROOT / "sources" / BASE_DEFINITION
        self.assertEqual(
            hashlib.sha256(definition_path.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            paths.append(path)
        self.assertEqual(len(paths), 117)
        self.assertEqual(len(paths), len(set(paths)))
        return paths

    def _import(self, connection: Any, path: Path) -> Any:
        document = json.loads(path.read_text(encoding="utf-8"))
        retrieved = {row["retrieved_at"] for row in document["evidence"]}
        self.assertEqual(len(retrieved), 1)
        return CuratedOfficialSourceAdapter().import_file(
            connection, path, retrieved_at=next(iter(retrieved))
        )

    def _state(self, connection: Any) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        queries = (
            "SELECT kind, stable_key, created_at FROM entities",
            "SELECT kind, title, source_url, publisher, source_family, license, "
            "attribution, published_at, retrieved_at, excerpt, content_hash, "
            "metadata_json FROM evidence",
            "SELECT projects_entity.stable_key, target_entity.stable_key "
            "FROM projects JOIN entities AS projects_entity "
            "ON projects_entity.id = projects.entity_id JOIN entities AS target_entity "
            "ON target_entity.id = projects.target_entity_id",
            "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
            "tags_json, evidence.content_hash, as_of_date, valid_to_date, recorded_at, "
            "superseded_at, method, confidence FROM entity_snapshots JOIN entities "
            "ON entities.id = entity_snapshots.entity_id JOIN evidence "
            "ON evidence.id = entity_snapshots.evidence_id",
            "SELECT entities.stable_key, status, evidence.content_hash, as_of_date, "
            "valid_to_date, recorded_at, superseded_at, method, confidence, notes "
            "FROM lifecycle_observations JOIN entities "
            "ON entities.id = lifecycle_observations.entity_id JOIN evidence "
            "ON evidence.id = lifecycle_observations.evidence_id",
            "SELECT entities.stable_key, operating_model FROM "
            "operating_model_observations JOIN entities "
            "ON entities.id = operating_model_observations.entity_id",
            "SELECT entities.stable_key, workload FROM workload_observations JOIN "
            "entities ON entities.id = workload_observations.entity_id",
            "SELECT entities.stable_key, metric, stage, unit, low, base, high, method, "
            "confidence, evidence.content_hash, as_of_date, target_date, valid_to_date, "
            "recorded_at, superseded_at, notes FROM capacity_estimates JOIN entities "
            "ON entities.id = capacity_estimates.entity_id JOIN evidence "
            "ON evidence.id = capacity_estimates.evidence_id",
        )
        return tuple(
            tuple(
                sorted(
                    (tuple(row) for row in connection.execute(query)),
                    key=lambda row: json.dumps(row, ensure_ascii=False),
                )
            )
            for query in queries
        )

    def _counts(self, connection: Any) -> dict[str, int]:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "entities",
                "campuses",
                "projects",
                "evidence",
                "entity_snapshots",
                "lifecycle_observations",
                "operating_model_observations",
                "workload_observations",
                "capacity_estimates",
            )
        }

    def _network_patches(self) -> tuple[Any, ...]:
        blocked = AssertionError("network used")
        return (
            patch.object(socket, "socket", side_effect=blocked),
            patch.object(socket, "create_connection", side_effect=blocked),
            patch.object(socket, "getaddrinfo", side_effect=blocked),
            patch.object(socket, "gethostbyname", side_effect=blocked),
            patch.object(socket, "gethostbyname_ex", side_effect=blocked),
        )

    def _scenario(
        self, base_first: bool, new_order: tuple[str, ...]
    ) -> tuple[tuple[tuple[tuple[Any, ...], ...], ...], dict[str, int]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._network_patches()
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    if base_first:
                        for path in self._base_paths():
                            self._import(connection, path)
                    for name in new_order:
                        self._import(connection, ROOT / "sources" / name)
                    before_repeat = self._state(connection)
                    for name in new_order:
                        result = self._import(connection, ROOT / "sources" / name)
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._state(connection), before_repeat)
                    if not base_first:
                        for path in self._base_paths():
                            self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._state(connection), self._counts(connection)
            finally:
                connection.close()

    def _base_state(self) -> tuple[
        tuple[tuple[tuple[Any, ...], ...], ...], dict[str, int]
    ]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._network_patches()
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    for path in self._base_paths():
                        self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._state(connection), self._counts(connection)
            finally:
                connection.close()

    def test_exact_sources_capture_lineage_and_narrow_semantics(self) -> None:
        base_text = (ROOT / "sources" / BASE_DEFINITION).read_text(encoding="utf-8")
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"])
            self.assertNotIn(name, base_text)
            self.assertNotIn(expected["campus_key"], base_text)
            self.assertNotIn(expected["project_key"], base_text)
            self._assert_document(name, self._load(name))

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    patches = self._network_patches()
                    with patches[0], patches[1], patches[2], patches[3], patches[4]:
                        result = self._import(connection, path)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_v21_forward_reverse_idempotence_and_exact_deltas(self) -> None:
        base_state, base_counts = self._base_state()
        names = tuple(SOURCES)
        forward_state, forward_counts = self._scenario(True, names)
        reverse_state, reverse_counts = self._scenario(False, tuple(reversed(names)))
        self.assertEqual(forward_state, reverse_state)
        self.assertEqual(forward_counts, reverse_counts)

        expected_deltas = {
            "entities": 4,
            "campuses": 2,
            "projects": 2,
            "evidence": 2,
            "entity_snapshots": 4,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 2,
        }
        self.assertEqual(
            {
                table: forward_counts[table] - base_counts[table]
                for table in expected_deltas
            },
            expected_deltas,
        )

        new_entity_keys = {
            key
            for expected in SOURCES.values()
            for key in (expected["campus_key"], expected["project_key"])
        }
        base_entities = {row[1] for row in base_state[0]}
        all_entities = {row[1] for row in forward_state[0]}
        self.assertTrue(base_entities.isdisjoint(new_entity_keys))
        self.assertEqual(all_entities - base_entities, new_entity_keys)

        new_snapshots = [row for row in forward_state[3] if row[0] in new_entity_keys]
        self.assertEqual(len(new_snapshots), 4)
        for snapshot in new_snapshots:
            self.assertIsNone(snapshot[2])
            self.assertIsNone(snapshot[3])
            self.assertIsNone(snapshot[4])
            self.assertFalse(
                any(key.startswith("role:") for key in json.loads(snapshot[5]))
            )

        new_lifecycle = [row for row in forward_state[4] if row[0] in new_entity_keys]
        self.assertEqual(len(new_lifecycle), 2)
        self.assertEqual(
            {(row[0], row[1], row[3], row[7]) for row in new_lifecycle},
            {
                (
                    expected["project_key"],
                    "under_construction",
                    expected["as_of_date"],
                    "authoritative_construction_start",
                )
                for expected in SOURCES.values()
            },
        )
        self.assertEqual(
            {(row[0], row[1], row[2], row[5]) for row in forward_state[7] if row[0] in new_entity_keys},
            {
                (expected["project_key"], "critical_it_mw", "planned", expected["capacity"])
                for expected in SOURCES.values()
            },
        )

    def test_semantic_mutations_fail_closed(self) -> None:
        for name in SOURCES:
            document = self._load(name)
            mutations: list[dict[str, Any]] = []

            mutated = copy.deepcopy(document)
            mutated["workloads"] = [{"forbidden": "design language is not workload"}]
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["operating_models"] = [{"forbidden": "future customers are not model"}]
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["campus"]["roles"] = {"operator": ["Empyrion Digital"]}
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["project"]["coordinates"] = {"latitude": 0.0, "longitude": 0.0}
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["lifecycle"][0]["value"] = "commissioning"
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["capacities"][0]["metric"] = "gross_mw"
            mutations.append(mutated)

            mutated = copy.deepcopy(document)
            mutated["capacities"][0]["base"] += 1
            mutations.append(mutated)

            for index, mutation in enumerate(mutations):
                with self.subTest(source=name, mutation=index):
                    with self.assertRaises(AssertionError):
                        self._assert_document(name, mutation)


if __name__ == "__main__":
    unittest.main()
