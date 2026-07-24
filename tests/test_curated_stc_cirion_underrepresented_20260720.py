from __future__ import annotations

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
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v37.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v37"
BASE_DEFINITION_SHA256 = (
    "c6786e684d76bfa72f5428e26396317bc05495da1afc656be4026c8c2acb9a66"
)
BASE_MANIFEST_SHA256 = (
    "bcc0d1207e5b4c709557f49fc6d42e1080dcaebb762b32093848461afd52d30a"
)
FIRST_ACCEPTED_SEED_VERSION = 40
FIRST_ACCEPTED_DEFINITION = (
    ROOT / "sources" / "open-seed-2026-07-20-v40.json"
)
FIRST_ACCEPTED_DEFINITION_SHA256 = (
    "5e4d8b3f6c507dcd515f5bd92facddb5b4bbb350fe3a0851fc5b08285c5897ff"
)
FIRST_ACCEPTED_MANIFEST = (
    ROOT / "releases" / "2026-07-20-open-seed-v40" / "manifest.json"
)
FIRST_ACCEPTED_MANIFEST_SHA256 = (
    "1b34fedfcef6c564aa17d20efefced3669b648c150f3dca74a3ecba78f341bc5"
)
SUCCESSOR_ACCEPTED_SEED_VERSION = 60
SUCCESSOR_ACCEPTED_DEFINITION = (
    ROOT / "sources" / "open-seed-2026-07-20-v60.json"
)
SUCCESSOR_ACCEPTED_DEFINITION_SHA256 = (
    "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66"
)
SUCCESSOR_ACCEPTED_MANIFEST = (
    ROOT / "releases" / "2026-07-20-open-seed-v60" / "manifest.json"
)
SUCCESSOR_ACCEPTED_MANIFEST_SHA256 = (
    "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430"
)

STC_DAMMAM = "curated-official-2026-07-20-stc-ddc306-dammam.json"
STC_BAHRAIN = "curated-official-2026-07-20-stc-bahrain-dc.json"
STC_MURSALAT = "curated-official-2026-07-20-stc-ruh-new-mursalat.json"
STC_BAHRAIN_SUCCESSOR = "curated-official-2026-07-20-stc-bahrain-dc-v2.json"
STC_BAHRAIN_SUCCESSOR_SHA256 = (
    "4d8976e26d77a9b5aa9b4a247456af3b9274991e9f0751a73b64f862fc2af02e"
)
CIRION_SAN2 = "curated-official-2026-07-20-cirion-san2-quilicura.json"
CIRION_LIM2 = "curated-official-2026-07-20-cirion-lim2-lurin.json"
SOURCE_ORDER = (
    CIRION_LIM2,
    CIRION_SAN2,
    STC_BAHRAIN,
    STC_DAMMAM,
    STC_MURSALAT,
)
STC_SOURCES = {STC_DAMMAM, STC_BAHRAIN, STC_MURSALAT}

STC_EVIDENCE = (
    "stc-sustainability-report-2024-data-centers-page-11-"
    "captured-2026-07-20"
)
SAN2_EVIDENCE = (
    "cirion-san2-85-percent-construction-progress-2025-07-22-"
    "captured-2026-07-20"
)
LIM2_EVIDENCE = (
    "cirion-lim2-construction-near-completion-2025-06-17-"
    "captured-2026-07-20"
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    CIRION_LIM2: {
        "sha256": "c1d9b3c63f5fc974f672ed2477d7fd828376dcb63a217da59b765ca182018dc4",
        "country": "Peru",
        "address": "Macrópolis, Lurín, Peru",
        "roles": {"developer": ["Cirion Technologies"]},
        "as_of_date": "2025-06-17",
        "retrieved_at": "2026-07-20T02:30:15Z",
        "evidence_key": LIM2_EVIDENCE,
        "campus_key": "curated:cirion-lim2-lurin-data-center",
        "project_key": (
            "curated:cirion-lim2-lurin-data-center:facility-build"
        ),
    },
    CIRION_SAN2: {
        "sha256": "2e4360de4e5188678205d1aa1612141fda3728788b77e981253ace41c56dec60",
        "country": "Chile",
        "address": "Quilicura, Santiago, Chile",
        "roles": {"developer": ["Cirion Technologies"]},
        "as_of_date": "2025-07-22",
        "retrieved_at": "2026-07-20T02:30:13Z",
        "evidence_key": SAN2_EVIDENCE,
        "campus_key": "curated:cirion-san2-quilicura-data-center",
        "project_key": (
            "curated:cirion-san2-quilicura-data-center:facility-build"
        ),
    },
    STC_BAHRAIN: {
        "sha256": "f67bc593369e9fbdcf994f8238ab1c6291ba64408563590c10064437c6784273",
        "country": "Bahrain",
        "address": "Bahrain",
        "roles": {},
        "as_of_date": "2024-12-31",
        "retrieved_at": "2026-07-20T02:29:27Z",
        "evidence_key": STC_EVIDENCE,
        "campus_key": "curated:stc-bahrain-data-center",
        "project_key": (
            "curated:stc-bahrain-data-center:facility-build"
        ),
    },
    STC_DAMMAM: {
        "sha256": "d9f02994c2199642d630fe709df548041e8a6c9706b25b63d617ed0247c9f66b",
        "country": "Saudi Arabia",
        "address": "Dammam, Saudi Arabia",
        "roles": {},
        "as_of_date": "2024-12-31",
        "retrieved_at": "2026-07-20T02:29:27Z",
        "evidence_key": STC_EVIDENCE,
        "campus_key": "curated:stc-ddc306-dammam-data-center",
        "project_key": (
            "curated:stc-ddc306-dammam-data-center:facility-build"
        ),
    },
    STC_MURSALAT: {
        "sha256": "0d8d7693cc5abf676837363ad4d2b5282c5bde58bc0356054c7d13c3150ea4c2",
        "country": "Saudi Arabia",
        "address": "Riyadh, Saudi Arabia",
        "roles": {},
        "as_of_date": "2024-12-31",
        "retrieved_at": "2026-07-20T02:29:27Z",
        "evidence_key": STC_EVIDENCE,
        "campus_key": "curated:stc-ruh-new-mursalat-data-center",
        "project_key": (
            "curated:stc-ruh-new-mursalat-data-center:facility-build"
        ),
    },
}

CAPTURE_FACTS: dict[str, dict[str, Any]] = {
    STC_EVIDENCE: {
        "appearances": 3,
        "body_bytes": 2_168_585,
        "content_hash": "85ab1a0ed34b0ff890f916f46f011b79a36739e21f15d3c8dfcd6c439f328c8e",
        "headers_bytes": 647,
        "headers_hash": "1834a0a7fde39442092d4ae393a458f7a401330e3dc0420d9a5688c9808803fb",
        "writeout_bytes": 9_724,
        "writeout_hash": "ea30f02022020866aceb02a0a04a1bd3fd056f50929930b85469a8a9c45b5ba1",
        "content_type": "application/pdf",
        "download_bytes": 2_168_585,
        "url": (
            "https://www.stc.com.sa/content/dam/groupsites/"
            "stc-sustainability-report-2024/assets/img/pdfs/"
            "Development_of_human_capital_through_digital_innovation.pdf"
        ),
    },
    SAN2_EVIDENCE: {
        "appearances": 1,
        "body_bytes": 84_422,
        "content_hash": "81407ef02c305a2ea82ff035fc60a24efc111f2b49e4515978a133b5c6fab4b6",
        "headers_bytes": 1_713,
        "headers_hash": "7ed1bc827c7c0fd055b1a24b01ebea0ba289c45d4e14ab6e176b5d8239d93d71",
        "writeout_bytes": 12_799,
        "writeout_hash": "8a97a167ddfa6ee04db2d0348d51fae1fd6856be8eb3b38653f6a9e8f261a0a5",
        "content_type": "text/html; charset=UTF-8",
        "download_bytes": 20_489,
        "url": (
            "https://press.ciriontechnologies.com/2025/07/22/"
            "medidas-sostenible-industria-data-centers/"
        ),
    },
    LIM2_EVIDENCE: {
        "appearances": 1,
        "body_bytes": 241_585,
        "content_hash": "9fd63f9e2e1a2ac3f6d2984504f2e37d93de709dc3578bca58a17e974c3c0b2e",
        "headers_bytes": 1_459,
        "headers_hash": "d89d5abe231f4cc65a1fbf690839573681aa1bfe331b7ed2171c491c13ad6d8c",
        "writeout_bytes": 12_724,
        "writeout_hash": "f539ee651bcb858ad23be0fa98148a942b3b7d6333d4bc27ee904031b0e23616",
        "content_type": "text/html; charset=UTF-8",
        "download_bytes": 43_342,
        "url": (
            "https://blog.ciriontechnologies.com/en/"
            "new-connection-peru-hyperscalers"
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


class StcCirionUnderrepresentedOfficialSourceTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

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

    def _network_block(self, stack: ExitStack) -> None:
        network_error = AssertionError("network used")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=network_error))

    def _import(self, connection: Any, name: str) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            self._path(name),
            retrieved_at=SOURCE_SPECS[name]["retrieved_at"],
        )

    def _build(
        self, order: Iterable[str]
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._network_block(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                evidence_created = 0
                for name in order:
                    result = self._import(connection, name)
                    self.assertEqual(result.entities_created, 2)
                    evidence_created += result.evidence_created
                    self.assertEqual(result.warnings, ())
                self.assertEqual(evidence_created, 3)
                self.assertEqual(validate_database(connection), [])

                expected_counts = {
                    "evidence": 3,
                    "entities": 10,
                    "campuses": 5,
                    "projects": 5,
                    "entity_snapshots": 10,
                    "lifecycle_observations": 5,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 0,
                }
                for table, count in expected_counts.items():
                    self.assertEqual(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0],
                        count,
                    )

                frozen = self._state(connection)
                for name in SOURCE_ORDER:
                    result = self._import(connection, name)
                    self.assertEqual(result.entities_created, 0)
                    self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(result.warnings, ())
                self.assertEqual(self._state(connection), frozen)
                self.assertEqual(validate_database(connection), [])
                return frozen
            finally:
                connection.close()

    def test_files_are_canonical_byte_pinned_and_collision_free(self) -> None:
        new_entity_keys = {
            value
            for spec in SOURCE_SPECS.values()
            for value in (spec["campus_key"], spec["project_key"])
        }
        evidence_records: dict[str, dict[str, Any]] = {}
        appearances: dict[str, int] = {}

        for name in SOURCE_ORDER:
            path = self._path(name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                SOURCE_SPECS[name]["sha256"],
            )
            text = path.read_text(encoding="utf-8")
            document = json.loads(text)
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            record = document["evidence"][0]
            key = record["key"]
            if key in evidence_records:
                self.assertEqual(record, evidence_records[key])
            else:
                evidence_records[key] = record
            appearances[key] = appearances.get(key, 0) + 1

        self.assertEqual(set(evidence_records), set(CAPTURE_FACTS))
        for key, expected in CAPTURE_FACTS.items():
            record = evidence_records[key]
            metadata = record["metadata"]
            self.assertEqual(appearances[key], expected["appearances"])
            self.assertEqual(record["content_hash"], expected["content_hash"])
            self.assertEqual(record["source_url"], expected["url"])
            self.assertEqual(metadata["canonical_url"], expected["url"])
            self.assertEqual(metadata["effective_url"], expected["url"])
            self.assertEqual(metadata["http_status"], 200)
            self.assertEqual(metadata["content_type"], expected["content_type"])
            self.assertEqual(
                metadata["curl_size_download_bytes_as_received"],
                expected["download_bytes"],
            )
            self.assertEqual(
                metadata["content_hash_scope"],
                (
                    f"SHA-256 of the exact {expected['body_bytes']}-byte "
                    + (
                        "official PDF response body"
                        if key == STC_EVIDENCE
                        else (
                            "content-decoded official HTML response body "
                            "captured with curl --compressed"
                        )
                    )
                ),
            )
            self.assertIn(
                f"exact {expected['headers_bytes']}-byte",
                metadata["capture_headers_scope"],
            )
            self.assertEqual(
                metadata["capture_headers_sha256"], expected["headers_hash"]
            )
            self.assertIn(
                f"exact {expected['writeout_bytes']}-byte",
                metadata["capture_curl_writeout_scope"],
            )
            self.assertEqual(
                metadata["capture_curl_writeout_sha256"],
                expected["writeout_hash"],
            )

        for path in sorted((ROOT / "sources").glob("curated-official*.json")):
            if path.name in SOURCE_SPECS:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            existing = {document["campus"]["stable_key"]}
            if document.get("project") is not None:
                existing.add(document["project"]["stable_key"])
            existing_evidence = {
                item["key"]: item for item in document.get("evidence", [])
            }
            stable_overlap = new_entity_keys & existing
            evidence_overlap = set(evidence_records) & set(existing_evidence)
            if path.name == STC_BAHRAIN_SUCCESSOR:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    STC_BAHRAIN_SUCCESSOR_SHA256,
                )
                self.assertEqual(
                    stable_overlap,
                    {
                        SOURCE_SPECS[STC_BAHRAIN]["campus_key"],
                        SOURCE_SPECS[STC_BAHRAIN]["project_key"],
                    },
                )
                self.assertEqual(evidence_overlap, {STC_EVIDENCE})
                self.assertEqual(
                    existing_evidence[STC_EVIDENCE],
                    evidence_records[STC_EVIDENCE],
                )
                continue
            self.assertEqual(
                stable_overlap,
                set(),
                f"new stable-key collision in {path.name}",
            )
            self.assertEqual(
                evidence_overlap,
                set(),
                f"new evidence-key collision in {path.name}",
            )

    def test_semantic_envelope_is_exact_and_non_inferential(self) -> None:
        stc_evidence_records = []
        for name in SOURCE_ORDER:
            document = self._load(name)
            expected = SOURCE_SPECS[name]
            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(len(document["evidence"]), 1)
            self.assertEqual(
                document["evidence"][0]["retrieved_at"],
                expected["retrieved_at"],
            )
            self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
            self.assertEqual(
                document["project"]["stable_key"], expected["project_key"]
            )
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["country"], expected["country"])
                self.assertEqual(entity["address"], expected["address"])
                self.assertEqual(entity["roles"], expected["roles"])
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["as_of_date"], expected["as_of_date"])
                self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(
                document["lifecycle"],
                [
                    {
                        "entity": "project",
                        "value": "under_construction",
                        "evidence_key": expected["evidence_key"],
                        "as_of_date": expected["as_of_date"],
                        "method": "authoritative_physical_status_update",
                        "confidence": 0.99,
                    }
                ],
            )
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            metadata = document["evidence"][0]["metadata"]
            self.assertIn("historical", metadata["historical_status_guardrail"])
            self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

            if name in STC_SOURCES:
                stc_evidence_records.append(document["evidence"][0])
                self.assertEqual(
                    metadata["under_construction_projects_as_reported"],
                    ["Dammam DDC306", "Bahrain DC", "RUH - New Mursalat"],
                )
                self.assertEqual(
                    metadata["portfolio_capacity_as_reported"],
                    {
                        "phase_4_total_it_shell_capacity_mw": 20,
                        "phase_4_initial_day_1_it_load_mw": 10.8,
                        "year_end_total_it_capacity_mw": 125,
                        "year_end_live_active_capacity_mw": 92,
                    },
                )
                self.assertIn("conflicts", metadata["internal_inconsistency_guardrail"])
                self.assertIn("creates no Jeddah record", metadata["internal_inconsistency_guardrail"])
            elif name == CIRION_SAN2:
                self.assertEqual(metadata["physical_progress_percent_as_reported"], 85)
                self.assertNotIn("reported_untyped_power_mw", metadata)
            else:
                self.assertEqual(metadata["reported_untyped_power_mw"], 20)
                self.assertIn("untyped evidence metadata", metadata["capacity_guardrail"])

        self.assertTrue(all(item == stc_evidence_records[0] for item in stc_evidence_records))
        normalized_entity_text = " ".join(
            str(self._load(name)[entity][field])
            for name in SOURCE_ORDER
            for entity in ("campus", "project")
            for field in ("stable_key", "name", "address")
        ).lower()
        self.assertNotIn("jeddah", normalized_entity_text)

    def test_offline_import_is_idempotent_and_order_independent(self) -> None:
        forward = self._build(SOURCE_ORDER)
        reverse = self._build(reversed(SOURCE_ORDER))
        self.assertEqual(forward, reverse)

    def test_seed_lineage_is_absent_at_v37_and_hash_pinned_from_v40(self) -> None:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(BASE_DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BASE_RELEASE.stat().st_mode), 0o555)

        definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        accepted_names = {
            Path(record["path"]).name for record in definition["curated_inputs"]
        }
        self.assertTrue(set(SOURCE_ORDER).isdisjoint(accepted_names))

        accepted_entity_keys: set[str] = set()
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"]
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            accepted_entity_keys.add(document["campus"]["stable_key"])
            if document.get("project") is not None:
                accepted_entity_keys.add(document["project"]["stable_key"])

        new_entity_keys = {
            value
            for spec in SOURCE_SPECS.values()
            for value in (spec["campus_key"], spec["project_key"])
        }
        self.assertTrue(new_entity_keys.isdisjoint(accepted_entity_keys))

        for path, expected_hash in (
            (FIRST_ACCEPTED_DEFINITION, FIRST_ACCEPTED_DEFINITION_SHA256),
            (FIRST_ACCEPTED_MANIFEST, FIRST_ACCEPTED_MANIFEST_SHA256),
            (SUCCESSOR_ACCEPTED_DEFINITION, SUCCESSOR_ACCEPTED_DEFINITION_SHA256),
            (SUCCESSOR_ACCEPTED_MANIFEST, SUCCESSOR_ACCEPTED_MANIFEST_SHA256),
        ):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)

        original_inputs = {
            name: spec["sha256"] for name, spec in SOURCE_SPECS.items()
        }
        successor_inputs = dict(original_inputs)
        del successor_inputs[STC_BAHRAIN]
        successor_inputs[STC_BAHRAIN_SUCCESSOR] = STC_BAHRAIN_SUCCESSOR_SHA256
        relevant_names = set(original_inputs) | {STC_BAHRAIN_SUCCESSOR}

        for path in sorted((ROOT / "sources").glob("open-seed-*.json")):
            version_text = path.stem.rpartition("-v")[2]
            self.assertTrue(version_text.isdecimal(), path.name)
            version = int(version_text)
            seed_definition = json.loads(path.read_text(encoding="utf-8"))
            selected_inputs = {
                Path(record["path"]).name: record["sha256"]
                for record in seed_definition["curated_inputs"]
                if isinstance(record, dict) and isinstance(record.get("path"), str)
            }
            selected_relevant = relevant_names & set(selected_inputs)
            with self.subTest(seed_definition=path.name):
                if version < FIRST_ACCEPTED_SEED_VERSION:
                    self.assertEqual(selected_relevant, set())
                    continue
                expected_inputs = (
                    original_inputs
                    if version < SUCCESSOR_ACCEPTED_SEED_VERSION
                    else successor_inputs
                )
                self.assertEqual(selected_relevant, set(expected_inputs))
                self.assertEqual(
                    {
                        name: selected_inputs[name]
                        for name in expected_inputs
                    },
                    expected_inputs,
                )


if __name__ == "__main__":
    unittest.main()
