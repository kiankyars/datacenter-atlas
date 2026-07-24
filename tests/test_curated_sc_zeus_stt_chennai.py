from __future__ import annotations

import copy
import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v21.json"
BASE_DEFINITION_SHA256 = (
    "4192fb1b2366f5fa86bbcc3ed57037a8c174755454da3b834ea08dadf6ed22f6"
)

ZEUS_SOURCE = "curated-official-2026-07-19-sc-zeus-osa1-osaka-phase-1.json"
STT_SOURCE = "curated-official-2026-07-19-stt-chennai-4-ambattur.json"
SOURCE_ORDER = (ZEUS_SOURCE, STT_SOURCE)

ZEUS_SC_EVIDENCE = (
    "sc-zeus-osa1-osaka-groundbreaking-2025-12-03-captured-2026-07-19"
)
ZEUS_TATEMONO_EVIDENCE = (
    "tokyo-tatemono-zeus-osa1-phase-1-2026-01-30-captured-2026-07-19"
)
STT_EVIDENCE = (
    "stt-chennai-4-ambattur-groundbreaking-2026-02-19-captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    ZEUS_SOURCE: {
        "sha256": "5efb07f0dd4563b94eb0e865400561f8c9200fd17e36e086e4ed2b14b0b0bcbc",
        "retrieved_at": "2026-07-19T20:57:09Z",
        "evidence_keys": (ZEUS_SC_EVIDENCE, ZEUS_TATEMONO_EVIDENCE),
        "evidence_count": 2,
        "campus_key": "curated:sc-zeus-osa1-nanko-osaka-campus",
        "project_key": "curated:sc-zeus-osa1-nanko-osaka-campus:phase-1",
        "country": "Japan",
        "address": "大阪府大阪市住之江区南港北一丁目14番地1（地番）",
        "snapshot_date": "2026-01-30",
        "lifecycle_date": "2025-12-03",
    },
    STT_SOURCE: {
        "sha256": "bbf32bdd2fc7eb532b5515a2851a2a59b2f6d2e2ea10757609d0a0ce044c5aa1",
        "retrieved_at": "2026-07-19T20:57:10Z",
        "evidence_keys": (STT_EVIDENCE,),
        "evidence_count": 1,
        "campus_key": "curated:stt-chennai-ambattur-campus",
        "project_key": "curated:stt-chennai-ambattur-campus:stt-chennai-4",
        "country": "India",
        "address": "Ambattur, Chennai, Tamil Nadu, India",
        "snapshot_date": "2026-02-19",
        "lifecycle_date": "2026-02-19",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    ZEUS_SC_EVIDENCE: {
        "body_bytes": 129851,
        "content_hash": (
            "0745701bea861a0a739c523307a183accc10e9d71850f87b33d6321e63678f0f"
        ),
        "headers_bytes": 579,
        "headers_hash": (
            "5beecfd49dd404ef1601ba58ae308dddcb64e968006482d3325e016018e1c1ed"
        ),
        "writeout_bytes": 11828,
        "writeout_hash": (
            "fd9d3cb7bd6ee103cf828c7f4d88595c8f24a89944230b58ca9f11cdf84b6fff"
        ),
        "content_type": "text/html;charset=utf-8",
        "encoding": "gzip",
        "content_length": 23328,
        "download_bytes": 23328,
        "response_date": "2026-07-19T20:57:09Z",
        "url": (
            "https://www.zeusdatacenters.com/"
            "sc-zeus-launches-flagship-ai-ready-data-center-in-osaka"
        ),
    },
    ZEUS_TATEMONO_EVIDENCE: {
        "body_bytes": 60638,
        "content_hash": (
            "30d1d50699a7609a787ff7c251f2cc2451288f1bd8dda12046e2af9020c68596"
        ),
        "headers_bytes": 203,
        "headers_hash": (
            "1abe9978d9c744ba6d647d30b289bf825e0cf2c12c30ef6e554653d46295ff34"
        ),
        "writeout_bytes": 10789,
        "writeout_hash": (
            "645c67a43d7760b31bb35f20704921dfbdcce158ef6e5de3633b34516dadef41"
        ),
        "content_type": "text/html; charset=UTF-8",
        "encoding": None,
        "content_length": None,
        "download_bytes": 60638,
        "response_date": "2026-07-19T20:57:09Z",
        "url": "https://tatemono.com/news/20260130.html",
    },
    STT_EVIDENCE: {
        "body_bytes": 79789,
        "content_hash": (
            "93ff4d609ed01cfb4522122b872eab74979b608f11e59563c688355dae2ff7bd"
        ),
        "headers_bytes": 2980,
        "headers_hash": (
            "854442e80f2ee70bd3d128720a1ff76cb6add990f338c216d08220def7104b37"
        ),
        "writeout_bytes": 14674,
        "writeout_hash": (
            "a5d97c2cd82268b62d8d1dc6c7505a5118f393b1249e76fd64e754c82575e623"
        ),
        "content_type": "text/html; charset=UTF-8",
        "encoding": None,
        "content_length": 79789,
        "download_bytes": 79789,
        "response_date": "2026-07-19T20:57:10Z",
        "url": (
            "https://www.sttelemediagdc.com/newsroom/"
            "stt-gdc-india-strengthens-its-market-presence-chennai-"
            "multi-campus-expansion-and-inr-4200"
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


class ScZeusSttChennaiTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        capture = CAPTURES[evidence["key"]]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["content_hash"], capture["content_hash"])
        self.assertEqual(evidence["source_url"], capture["url"])
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(capture["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], capture["headers_hash"])
        self.assertIn(
            str(capture["writeout_bytes"]),
            metadata["capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["capture_curl_writeout_sha256"], capture["writeout_hash"]
        )
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertIn("no local address", metadata["capture_artifact_guardrail"])
        self.assertIn("no request-start artifact", metadata["retrieval_method"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], capture["content_type"])
        self.assertEqual(metadata["content_encoding_as_received"], capture["encoding"])
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            capture["content_length"],
        )
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            capture["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], capture["response_date"])
        self.assertIsNone(metadata["http_last_modified_at"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], capture["url"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("computer vision", metadata["imagery_guardrail"])

    def _assert_entity(
        self, entity: dict[str, Any], expected: dict[str, Any], *, project: bool
    ) -> None:
        self.assertEqual(
            entity["stable_key"],
            expected["project_key"] if project else expected["campus_key"],
        )
        self.assertEqual(entity["country"], expected["country"])
        self.assertEqual(entity["address"], expected["address"])
        self.assertEqual(entity["roles"], {})
        self.assertIsNone(entity["coordinates"])
        self.assertIsNone(entity["geometry"])
        self.assertEqual(entity["as_of_date"], expected["snapshot_date"])
        self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(entity["confidence"], 0.99)

    def _assert_capacity(
        self,
        capacity: dict[str, Any],
        *,
        entity: str,
        metric: str,
        stage: str,
        value: float,
        evidence_key: str,
        as_of_date: str,
    ) -> None:
        self.assertEqual(capacity["entity"], entity)
        self.assertEqual(capacity["metric"], metric)
        self.assertEqual(capacity["stage"], stage)
        self.assertEqual(capacity["unit"], "MW")
        self.assertEqual(
            (capacity["low"], capacity["base"], capacity["high"]),
            (value, value, value),
        )
        self.assertEqual(capacity["method"], "reported")
        self.assertEqual(capacity["confidence"], 0.99)
        self.assertEqual(capacity["evidence_key"], evidence_key)
        self.assertEqual(capacity["as_of_date"], as_of_date)
        self.assertIsNone(capacity["target_date"])
        self.assertIn("not", capacity["notes"].lower())

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(
            tuple(evidence["key"] for evidence in document["evidence"]),
            expected["evidence_keys"],
        )
        self.assertEqual(
            {evidence["retrieved_at"] for evidence in document["evidence"]},
            {expected["retrieved_at"]},
        )
        for evidence in document["evidence"]:
            self.assertEqual(evidence["kind"], "company_disclosure")
            self._assert_capture(evidence)

        self._assert_entity(document["campus"], expected, project=False)
        self._assert_entity(document["project"], expected, project=True)
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": expected["evidence_keys"][0],
                    "as_of_date": expected["lifecycle_date"],
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )

        if name == ZEUS_SOURCE:
            sc, tatemono = document["evidence"]
            self.assertEqual(sc["publisher"], "SC Zeus Data Centers")
            self.assertEqual(sc["source_family"], "sc_zeus_news")
            self.assertEqual(sc["published_at"], "2025-12-03")
            self.assertEqual(
                sc["metadata"]["reported_full_facility_it_load_mw"], 70
            )
            self.assertEqual(sc["metadata"]["reported_full_facility_phase_count"], 2)
            self.assertEqual(sc["metadata"]["reported_secured_power_allocation_mw"], 100)
            self.assertEqual(sc["metadata"]["design_pue_target_as_reported"], 1.19)
            self.assertIn("future design target", sc["metadata"]["pue_guardrail"])
            self.assertIn("no normalized workload", sc["metadata"]["classification_guardrail"])
            self.assertIn("not normalized", sc["metadata"]["role_guardrail"])
            self.assertIn("no current load", sc["metadata"]["energy_guardrail"])

            self.assertEqual(tatemono["publisher"], "Tokyo Tatemono Co., Ltd.")
            self.assertEqual(tatemono["source_family"], "tokyo_tatemono_news")
            self.assertEqual(tatemono["published_at"], "2026-01-30")
            self.assertEqual(
                tatemono["metadata"]["address_as_reported_japanese"],
                expected["address"],
            )
            self.assertEqual(
                tatemono["metadata"]["address_component_rendering_context"],
                {
                    "prefecture": "Osaka Prefecture",
                    "city": "Osaka City",
                    "ward": "Suminoe Ward",
                    "district": "Nankokita 1-chome",
                    "lot_number": "14-1",
                },
            )
            self.assertIn("exact Japanese", tatemono["metadata"]["address_guardrail"])
            self.assertEqual(tatemono["metadata"]["reported_phase_1_it_load_mw"], 25)
            self.assertIn("no normalized workload", tatemono["metadata"]["classification_guardrail"])
            self.assertIn("no standardized", tatemono["metadata"]["role_guardrail"])
            self.assertEqual(
                document["campus"]["evidence_key"], ZEUS_TATEMONO_EVIDENCE
            )
            self.assertEqual(
                document["project"]["evidence_key"], ZEUS_TATEMONO_EVIDENCE
            )
            self.assertEqual(len(document["capacities"]), 3)
            self._assert_capacity(
                document["capacities"][0],
                entity="campus",
                metric="critical_it_mw",
                stage="planned",
                value=70,
                evidence_key=ZEUS_SC_EVIDENCE,
                as_of_date="2025-12-03",
            )
            self._assert_capacity(
                document["capacities"][1],
                entity="campus",
                metric="grid_connection_mw",
                stage="contracted",
                value=100,
                evidence_key=ZEUS_SC_EVIDENCE,
                as_of_date="2025-12-03",
            )
            self._assert_capacity(
                document["capacities"][2],
                entity="project",
                metric="critical_it_mw",
                stage="planned",
                value=25,
                evidence_key=ZEUS_TATEMONO_EVIDENCE,
                as_of_date="2026-01-30",
            )
        else:
            evidence = document["evidence"][0]
            metadata = evidence["metadata"]
            self.assertEqual(evidence["publisher"], "ST Telemedia Global Data Centres")
            self.assertEqual(evidence["source_family"], "stt_gdc_newsroom")
            self.assertEqual(evidence["published_at"], "2026-02-19")
            self.assertIn("CDN request diagnostics", metadata["capture_headers_sensitive_data_guardrail"])
            self.assertEqual(metadata["reported_ambattur_operational_capacity_mw"], 40)
            self.assertEqual(
                metadata["reported_total_development_potential_mw_approximate"], 130
            )
            self.assertIs(metadata["reported_total_includes_existing_operational_capacity"], True)
            self.assertIn("same campus", metadata["identity_scope"])
            self.assertIn("no exact groundbreaking day", metadata["status_scope"])
            self.assertIn("Neither value creates", metadata["capacity_metric_guardrail"])
            self.assertIn("no normalized workload", metadata["classification_guardrail"])
            self.assertIn("not normalized", metadata["role_guardrail"])
            self.assertEqual(document["campus"]["evidence_key"], STT_EVIDENCE)
            self.assertEqual(document["project"]["evidence_key"], STT_EVIDENCE)
            self.assertEqual(document["capacities"], [])

    def _baseline_paths(self) -> list[Path]:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        records = definition["curated_inputs"]
        self.assertEqual(len(records), 117)
        self.assertEqual(
            [record["path"] for record in records],
            sorted(record["path"] for record in records),
        )
        self.assertEqual(len(records), len({record["path"] for record in records}))
        paths: list[Path] = []
        for record in records:
            path = ROOT / record["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"]
            )
            paths.append(path)
        return paths

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        values = {evidence["retrieved_at"] for evidence in document["evidence"]}
        self.assertEqual(len(values), 1)
        return next(iter(values))

    def _import(self, connection: Any, path: Path) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection, path, retrieved_at=self._retrieved_at(path)
        )

    def _network_patches(self) -> tuple[Any, ...]:
        blocked = AssertionError("network used")
        return (
            patch.object(socket, "socket", side_effect=blocked),
            patch.object(socket, "create_connection", side_effect=blocked),
            patch.object(socket, "getaddrinfo", side_effect=blocked),
            patch.object(socket, "gethostbyname", side_effect=blocked),
            patch.object(socket, "gethostbyname_ex", side_effect=blocked),
        )

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=lambda row: json.dumps(row, ensure_ascii=False),
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _counts(self, state: dict[str, tuple[tuple[Any, ...], ...]]) -> dict[str, int]:
        return {table: len(rows) for table, rows in state.items()}

    def _scenario(
        self, *, base_first: bool, source_order: Iterable[str], repeat: bool
    ) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        names = tuple(source_order)
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._network_patches()
                results: dict[str, tuple[int, int]] = {}
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    if base_first:
                        for path in self._baseline_paths():
                            self._import(connection, path)
                    for name in names:
                        result = self._import(connection, ROOT / "sources" / name)
                        results[name] = (
                            result.entities_created,
                            result.evidence_created,
                        )
                    before_repeat = self._state(connection)
                    if repeat:
                        for name in names:
                            result = self._import(connection, ROOT / "sources" / name)
                            self.assertEqual(result.entities_created, 0)
                            self.assertEqual(result.evidence_created, 0)
                        self.assertEqual(self._state(connection), before_repeat)
                    if not base_first:
                        for path in self._baseline_paths():
                            self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._state(connection), results
            finally:
                connection.close()

    def _baseline_state(self) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._network_patches()
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    for path in self._baseline_paths():
                        self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._state(connection)
            finally:
                connection.close()

    def test_exact_hashes_raw_lineage_narrow_semantics_and_baseline_absence(self) -> None:
        baseline_text = BASE_DEFINITION.read_text(encoding="utf-8")
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            self.assertNotIn(name, baseline_text)
            self.assertNotIn(expected["campus_key"], baseline_text)
            self.assertNotIn(expected["project_key"], baseline_text)
            self._assert_document(name, self._load(name))

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    patches = self._network_patches()
                    with patches[0], patches[1], patches[2], patches[3], patches[4]:
                        result = self._import(connection, path)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, expected["evidence_count"])
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_v21_forward_reverse_new_first_idempotence_and_exact_deltas(self) -> None:
        baseline = self._baseline_state()
        forward, forward_results = self._scenario(
            base_first=True, source_order=SOURCE_ORDER, repeat=True
        )
        reverse, reverse_results = self._scenario(
            base_first=False, source_order=reversed(SOURCE_ORDER), repeat=True
        )
        self.assertEqual(forward, reverse)
        expected_results = {
            name: (2, expected["evidence_count"])
            for name, expected in SOURCES.items()
        }
        self.assertEqual(forward_results, expected_results)
        self.assertEqual(reverse_results, expected_results)

        baseline_counts = self._counts(baseline)
        forward_counts = self._counts(forward)
        expected_deltas = {
            "evidence": 3,
            "entities": 4,
            "campuses": 2,
            "facilities": 0,
            "buildings": 0,
            "projects": 2,
            "administrative_assignments": 0,
            "entity_snapshots": 4,
            "lifecycle_observations": 2,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 3,
        }
        self.assertEqual(
            {
                table: forward_counts[table] - baseline_counts[table]
                for table in SEMANTIC_TABLES
            },
            expected_deltas,
        )

        new_keys = {
            key
            for expected in SOURCES.values()
            for key in (expected["campus_key"], expected["project_key"])
        }
        baseline_entity_keys = {row[2] for row in baseline["entities"]}
        forward_entity_keys = {row[2] for row in forward["entities"]}
        self.assertTrue(baseline_entity_keys.isdisjoint(new_keys))
        self.assertEqual(forward_entity_keys - baseline_entity_keys, new_keys)

    def test_standalone_rows_are_exact_and_have_no_inferred_classification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._network_patches()
                with patches[0], patches[1], patches[2], patches[3], patches[4]:
                    for name in SOURCE_ORDER:
                        self._import(connection, ROOT / "sources" / name)
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots"
                    ).fetchone()[0],
                    4,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
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
                            SOURCES[ZEUS_SOURCE]["project_key"],
                            "under_construction",
                            "2025-12-03",
                            "authoritative_construction_start",
                        ),
                        (
                            SOURCES[STT_SOURCE]["project_key"],
                            "under_construction",
                            "2026-02-19",
                            "authoritative_construction_start",
                        ),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, metric, stage, low, base, high "
                            "FROM capacity_estimates JOIN entities "
                            "ON entities.id = capacity_estimates.entity_id "
                            "ORDER BY entities.stable_key, metric, stage"
                        )
                    ],
                    [
                        (
                            SOURCES[ZEUS_SOURCE]["campus_key"],
                            "critical_it_mw",
                            "planned",
                            70.0,
                            70.0,
                            70.0,
                        ),
                        (
                            SOURCES[ZEUS_SOURCE]["campus_key"],
                            "grid_connection_mw",
                            "contracted",
                            100.0,
                            100.0,
                            100.0,
                        ),
                        (
                            SOURCES[ZEUS_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            25.0,
                            25.0,
                            25.0,
                        ),
                    ],
                )
                for table in (
                    "operating_model_observations",
                    "workload_observations",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                    )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_closed(self) -> None:
        mutations: list[tuple[str, dict[str, Any]]] = []
        for name in SOURCE_ORDER:
            document = self._load(name)

            mutated = copy.deepcopy(document)
            mutated["evidence"][0]["content_hash"] = "0" * 64
            mutations.append((name, mutated))

            mutated = copy.deepcopy(document)
            mutated["workloads"] = [{"forbidden": "design language is not workload"}]
            mutations.append((name, mutated))

            mutated = copy.deepcopy(document)
            mutated["operating_models"] = [{"forbidden": "no model is normalized"}]
            mutations.append((name, mutated))

            mutated = copy.deepcopy(document)
            mutated["campus"]["roles"] = {"operator": ["publisher"]}
            mutations.append((name, mutated))

            mutated = copy.deepcopy(document)
            mutated["project"]["coordinates"] = {
                "latitude": 0.0,
                "longitude": 0.0,
            }
            mutations.append((name, mutated))

            mutated = copy.deepcopy(document)
            mutated["lifecycle"][0]["value"] = "commissioning"
            mutations.append((name, mutated))

        zeus = self._load(ZEUS_SOURCE)
        mutated = copy.deepcopy(zeus)
        mutated["campus"]["address"] = "1-14-1 Nankokita, Osaka, Japan"
        mutations.append((ZEUS_SOURCE, mutated))

        mutated = copy.deepcopy(zeus)
        mutated["capacities"][0]["base"] = 71
        mutations.append((ZEUS_SOURCE, mutated))

        mutated = copy.deepcopy(zeus)
        mutated["capacities"][1]["stage"] = "energized"
        mutations.append((ZEUS_SOURCE, mutated))

        mutated = copy.deepcopy(zeus)
        mutated["capacities"][2]["entity"] = "campus"
        mutations.append((ZEUS_SOURCE, mutated))

        stt = self._load(STT_SOURCE)
        mutated = copy.deepcopy(stt)
        mutated["capacities"] = [{"forbidden": "aggregate potential is untyped"}]
        mutations.append((STT_SOURCE, mutated))

        mutated = copy.deepcopy(stt)
        mutated["lifecycle"][0]["as_of_date"] = "2026-02-03"
        mutations.append((STT_SOURCE, mutated))

        mutated = copy.deepcopy(stt)
        mutated["project"]["address"] = "Siruseri, Chennai, India"
        mutations.append((STT_SOURCE, mutated))

        for name, mutation in mutations:
            with self.subTest(source=name, mutation=mutation):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, mutation)


if __name__ == "__main__":
    unittest.main()
