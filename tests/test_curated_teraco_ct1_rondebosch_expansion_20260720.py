from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "sources"
    / "curated-official-2026-07-20-teraco-ct1-rondebosch-expansion.json"
)
V63_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
V63_RELEASE = ROOT / "releases/2026-07-20-open-seed-v63"
SOURCE_BYTES = 10_999
SOURCE_SHA256 = "2a73a6dacb84bfcd5cee8e51bf08955f9863dca328117833d94d06634fa43eea"
V63_DEFINITION_SHA256 = (
    "13bfdcbda96769de1a39e1bc41e67ad7e0a6e98d026fedda3384fbd89bc8adff"
)
V63_MANIFEST_SHA256 = (
    "8ee3539f639641c7f97827ba7a21c13b7e907881ba858970e701675510eab4ba"
)
RECORDED_AT = "2026-07-21T05:28:00Z"
EVIDENCE_KEY = (
    "teraco-ct1-rondebosch-expansion-current-2026-07-17-captured-2026-07-20"
)
CAMPUS_KEY = "curated:teraco-ct1-rondebosch-data-centre"
PROJECT_KEY = f"{CAMPUS_KEY}:current-expansion"
SOURCE_URL = (
    "https://www.teraco.co.za/news/"
    "teraco-announces-ct1-data-centre-expansion-in-rondebosch-cape-town/"
)
BODY_SHA256 = "7a0daa8edc0c82b8c876250b187cbb0acbbe8e9c766080d868227d6660c8161e"
HEADERS_SHA256 = (
    "363449696118454fdbbf592b35b98b2b43dde7318d66caf1ef41044f4d943492"
)
WRITEOUT_SHA256 = (
    "1ce6707c2ae490788adbbe6acf5524f297b718f332047483a038325cd3ec44ad"
)


class TeracoCt1RondeboschExpansionTests(unittest.TestCase):
    def _document(self) -> dict[str, object]:
        return json.loads(SOURCE.read_text(encoding="utf-8"))

    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError("Teraco CT1 curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _table_state(self, connection):
        tables = (
            "entities",
            "evidence",
            "entity_snapshots",
            "lifecycle_observations",
            "operating_model_observations",
            "workload_observations",
            "capacity_estimates",
        )
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in tables
        }

    def test_source_is_canonical_and_capture_contract_is_byte_pinned(self) -> None:
        data = SOURCE.read_bytes()
        self.assertEqual(len(data), SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        document = json.loads(data.decode("utf-8"))
        self.assertEqual(
            data.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(len(document["evidence"]), 1)
        evidence = document["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], "Teraco")
        self.assertEqual(evidence["source_family"], "teraco_newsroom")
        self.assertEqual(evidence["source_url"], SOURCE_URL)
        self.assertEqual(evidence["published_at"], "2026-07-17")
        self.assertEqual(evidence["retrieved_at"], "2026-07-21T05:27:43Z")
        self.assertEqual(evidence["license"], "all-rights-reserved")
        self.assertEqual(evidence["content_hash"], BODY_SHA256)
        self.assertIn("144462-byte", metadata["content_hash_scope"])
        self.assertEqual(metadata["decoded_body_bytes"], 144_462)
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertIn("1114-byte", metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_SHA256)
        self.assertIn("17329-byte", metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["curl_exit_code"], 0)
        self.assertEqual(metadata["http_version_as_received"], "HTTP/2")
        self.assertEqual(metadata["content_type"], "text/html; charset=UTF-8")
        self.assertEqual(metadata["content_encoding_as_received"], "gzip")
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertIsNone(metadata["http_content_length_bytes_as_received"])
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], 34_197)
        self.assertEqual(metadata["curl_size_header_bytes"], 1_114)
        self.assertEqual(metadata["curl_num_headers"], 23)
        self.assertEqual(metadata["response_http_date"], evidence["retrieved_at"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        for field in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[field], SOURCE_URL)
        self.assertIn("credential-free", metadata["retrieval_method"])
        self.assertIn("no Authorization", metadata["request_credentials_guardrail"])
        self.assertIn("recoverable Trash", metadata["capture_artifact_guardrail"])
        self.assertNotIn("/private/tmp/", data.decode("utf-8"))

    def test_2026_status_date_is_explicit_and_narrowly_scoped(self) -> None:
        document = self._document()
        evidence = document["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(
            metadata["page_original_published_at"],
            "2025-11-12T06:30:04+00:00",
        )
        self.assertEqual(
            metadata["page_modified_at"], "2026-07-17T07:03:16+00:00"
        )
        self.assertEqual(metadata["page_updated_date_as_displayed"], "July 17th, 2026")
        self.assertIn("dateModified", metadata["publication_date_scope"])
        self.assertIn("currently underway", metadata["current_physical_status_wording_as_reported"])
        self.assertIn("July 17, 2026", metadata["status_date_basis"])
        self.assertEqual(metadata["last_observed_physical_status"], "under_construction")
        self.assertEqual(metadata["last_observed_physical_status_date"], "2026-07-17")
        self.assertEqual(metadata["current_status_classification"], "under_construction")
        self.assertIn("does not establish", metadata["physical_status_scope"])
        self.assertIn("not used", metadata["http_last_modified_guardrail"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": "2026-07-17",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )

    def test_offline_import_is_exact_idempotent_and_integrity_clean(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with ExitStack() as stack:
                    self._block_network(stack)
                    result = CuratedOfficialSourceAdapterV11().import_file(
                        connection, SOURCE, recorded_at=RECORDED_AT
                    )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(result.imported_elements, 1)
                    self.assertEqual(result.skipped_elements, 0)
                    self.assertEqual(result.warnings, ())
                    self.assertEqual(validate_database(connection), [])
                    first_state = self._table_state(connection)
                    repeated = CuratedOfficialSourceAdapterV11().import_file(
                        connection, SOURCE, recorded_at=RECORDED_AT
                    )
                    self.assertEqual(repeated.entities_created, 0)
                    self.assertEqual(repeated.evidence_created, 0)
                    self.assertEqual(repeated.warnings, ())
                    self.assertEqual(self._table_state(connection), first_state)
                self.assertEqual(
                    {table: len(rows) for table, rows in first_state.items()},
                    {
                        "entities": 2,
                        "evidence": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 1,
                    },
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_imported_identity_status_and_capacity_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapterV11().import_file(
                    connection, SOURCE, recorded_at=RECORDED_AT
                )
                entities = [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT stable_key, kind FROM entities ORDER BY stable_key"
                    )
                ]
                self.assertEqual(
                    entities,
                    [(CAMPUS_KEY, "campus"), (PROJECT_KEY, "project")],
                )
                target = connection.execute(
                    "SELECT target.stable_key FROM projects "
                    "JOIN entities AS project ON project.id = projects.entity_id "
                    "JOIN entities AS target ON target.id = projects.target_entity_id "
                    "WHERE project.stable_key = ?",
                    (PROJECT_KEY,),
                ).fetchone()
                self.assertEqual(target["stable_key"], CAMPUS_KEY)
                lifecycle = connection.execute(
                    "SELECT entities.stable_key, status, as_of_date, method, confidence "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id"
                ).fetchone()
                self.assertEqual(
                    tuple(lifecycle),
                    (
                        PROJECT_KEY,
                        "under_construction",
                        "2026-07-17",
                        "authoritative_physical_status_update",
                        0.99,
                    ),
                )
                capacity = connection.execute(
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "method, as_of_date, target_date FROM capacity_estimates "
                    "JOIN entities ON entities.id = capacity_estimates.entity_id"
                ).fetchone()
                self.assertEqual(
                    tuple(capacity),
                    (
                        PROJECT_KEY,
                        "critical_it_mw",
                        "planned",
                        "MW",
                        2.0,
                        2.0,
                        2.0,
                        "reported",
                        "2026-07-17",
                        None,
                    ),
                )
                snapshots = list(
                    connection.execute(
                        "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                        "tags_json, entity_snapshots.method, entity_snapshots.as_of_date "
                        "FROM entity_snapshots JOIN entities "
                        "ON entities.id = entity_snapshots.entity_id "
                        "ORDER BY entities.stable_key"
                    )
                )
                self.assertEqual(
                    [row["stable_key"] for row in snapshots],
                    [CAMPUS_KEY, PROJECT_KEY],
                )
                for row in snapshots:
                    self.assertIsNone(row["latitude"])
                    self.assertIsNone(row["longitude"])
                    self.assertIsNone(row["geometry_json"])
                    self.assertEqual(row["method"], "authoritative_locality")
                    self.assertEqual(row["as_of_date"], "2026-07-17")
                    self.assertEqual(
                        json.loads(row["tags_json"]),
                        {
                            "address": "Rondebosch, Cape Town, South Africa",
                            "country": "South Africa",
                            "source_dataset": "curated_official_sources",
                        },
                    )
            finally:
                connection.close()

    def test_metric_stage_and_non_promotions_are_fail_closed(self) -> None:
        document = self._document()
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["entity"],
                capacity["metric"],
                capacity["stage"],
                capacity["unit"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
                capacity["target_date"],
            ),
            ("project", "critical_it_mw", "planned", "MW", 2, 2, 2, None),
        )
        self.assertIn("not current operating load", capacity["notes"])
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_existing_critical_it_mw"], 3)
        self.assertEqual(metadata["reported_expansion_additional_critical_it_mw"], 2)
        self.assertEqual(metadata["reported_platform_critical_power_load_mw"], 191)
        self.assertEqual(metadata["reported_cape_town_campus_critical_power_load_mw"], 55)
        self.assertIn("not added", metadata["existing_capacity_guardrail"])
        self.assertIn("remain metadata only", metadata["aggregate_capacity_guardrail"])
        self.assertIn("No MW-to-MWh conversion", metadata["energy_guardrail"])
        self.assertIn("not normalized", metadata["completion_guardrail"])
        self.assertIn("no normalized operating model", metadata["classification_guardrail"])
        self.assertIn("no normalized owner", metadata["role_guardrail"])
        self.assertIn("no street address", metadata["locality_guardrail"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])

    def test_identity_and_evidence_are_absent_from_frozen_v63(self) -> None:
        self.assertEqual(
            hashlib.sha256(V63_DEFINITION.read_bytes()).hexdigest(),
            V63_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((V63_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            V63_MANIFEST_SHA256,
        )
        with (V63_RELEASE / "entities.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            entity_rows = list(csv.DictReader(handle))
        with (V63_RELEASE / "evidence.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            evidence_rows = list(csv.DictReader(handle))
        self.assertEqual(len(entity_rows), 737)
        self.assertEqual(len(evidence_rows), 452)
        self.assertTrue(
            {CAMPUS_KEY, PROJECT_KEY}.isdisjoint(
                row["stable_key"] for row in entity_rows
            )
        )
        self.assertNotIn(SOURCE_URL, {row["source_url"] for row in evidence_rows})
        self.assertNotIn(BODY_SHA256, {row["content_hash"] for row in evidence_rows})
        definition = json.loads(V63_DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["release_id"], "2026-07-20-open-seed-v63")
        self.assertEqual(len(definition["curated_inputs"]), 354)
        self.assertNotIn(
            "sources/" + SOURCE.name,
            {row["path"] for row in definition["curated_inputs"]},
        )

    def test_future_retrieval_time_fails_before_any_rows_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T05:27:42Z",
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    0,
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
