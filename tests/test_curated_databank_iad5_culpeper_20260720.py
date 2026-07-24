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
SOURCE = ROOT / "sources/curated-official-2026-07-20-databank-iad5-culpeper.json"
V60_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v60/entities.csv"
SOURCE_SHA256 = "4e32216ede500acb5a75e64a6c4a8b29c655e5d6d505894d90dbafab85d3c747"
RECORDED_AT = "2026-07-21T04:30:00Z"
POST_KEY = "databank-iad5-culpeper-construction-video-2026-05-14-captured-2026-07-20"
PAGE_KEY = (
    "databank-iad5-culpeper-facility-page-modified-2026-05-14-captured-2026-07-20"
)
DHCD_KEY = "virginia-dhcd-14601-germanna-highway-address-point-captured-2026-07-20"
CAMPUS_KEY = "curated:databank-culpeper-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:iad5-current-build"


class DataBankIad5CulpeperTests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "DataBank IAD5 curated import attempted network access"
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _import(self):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        result = CuratedOfficialSourceAdapterV11().import_file(
            connection, SOURCE, recorded_at=RECORDED_AT
        )
        return temporary, connection, result

    def test_source_is_canonical_and_capture_facts_are_byte_pinned(self) -> None:
        data = SOURCE.read_bytes()
        self.assertEqual(len(data), 22_522)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        document = json.loads(data.decode("utf-8"))
        self.assertEqual(
            data.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [POST_KEY, PAGE_KEY, DHCD_KEY],
        )
        expected = (
            (
                "ce57c3d09af03c7e0b333bbe37dde2755620e464f6b3b2aa50c5adb1e9aebd16",
                331_309,
                "de67839890c046a077d08db301029489a50ddff1d027496a90f75f9e17f2440f",
                "56a51c8a9a72af864c1789422a69de51f4272f922dc83f5a19063d0fc7f51e58",
                "2026-07-21T04:19:37Z",
            ),
            (
                "c9e96e0c93e1593035e786efce937c969d44ff0f1b82fef4c7fc3a08c57e5f32",
                121_273,
                "67ee452185d5ba2da64eff3bbe219be76b70d808d39b687ebad1725786b32634",
                "632f34fdc438b6dfa6889227cf6d3ce880a422e01db951968bd2988b5173d578",
                "2026-07-21T04:19:36Z",
            ),
            (
                "a9cd3e4d919d4c11a97b4bca717c6e617730efa26d02ffec8b0983114a8b1f41",
                7_225_328,
                "a46c57544a1baa7bca015f3c8d75fdc24a782a6fd72922d29a49d72adf5a85ca",
                "be8e935a65878ead60181341cbabe0df9160bb55c9f1315b3261145454c22f00",
                "2026-07-21T04:27:49Z",
            ),
        )
        for evidence, (
            body_hash,
            body_bytes,
            header_hash,
            facts_hash,
            retrieved,
        ) in zip(document["evidence"], expected, strict=True):
            metadata = evidence["metadata"]
            self.assertEqual(evidence["content_hash"], body_hash)
            self.assertEqual(evidence["retrieved_at"], retrieved)
            self.assertEqual(evidence["license"], "all-rights-reserved")
            self.assertEqual(metadata["http_status"], 200)
            self.assertIn(str(body_bytes), metadata["content_hash_scope"])
            self.assertEqual(metadata["capture_headers_sha256"], header_hash)
            self.assertEqual(metadata["capture_curl_writeout_sha256"], facts_hash)
            self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
            self.assertEqual(metadata["requested_url"], metadata["effective_url"])
            self.assertEqual(metadata["effective_url"], metadata["canonical_url"])
        self.assertEqual(
            document["evidence"][0]["metadata"]["structured_date_published"],
            "2026-05-14T15:03:53.358Z",
        )
        self.assertEqual(
            document["evidence"][1]["metadata"]["page_modified_at"],
            "2026-05-14T19:00:22+00:00",
        )
        coordinate = document["evidence"][2]["metadata"]
        self.assertEqual(coordinate["pdf_matching_page"], 40)
        self.assertEqual(coordinate["reported_address"], "14601 GERMANNA HWY")
        self.assertEqual(
            (coordinate["reported_latitude"], coordinate["reported_longitude"]),
            (38.45185992, -77.98378765),
        )
        self.assertEqual(
            coordinate["coordinate_reference_system"], "not stated by source"
        )
        self.assertIn("not a parcel", coordinate["coordinate_scope"])
        self.assertIn("location only", coordinate["identity_bridge_scope"])

    def test_offline_import_has_exact_source_scoped_rows(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary, connection, result = self._import()
            stack.callback(temporary.cleanup)
            stack.callback(connection.close)
            self.assertEqual(result.entities_created, 2)
            self.assertEqual(result.evidence_created, 3)
            self.assertEqual(result.warnings, ())
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 3,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "operating_model_observations": 1,
                    "workload_observations": 0,
                    "capacity_estimates": 1,
                },
            )
            snapshots = list(
                connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, "
                    "geometry_json, tags_json "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                [row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY]
            )
            for row in snapshots:
                self.assertEqual(row["latitude"], 38.45185992)
                self.assertEqual(row["longitude"], -77.98378765)
                self.assertEqual(
                    json.loads(row["geometry_json"]),
                    {
                        "type": "Point",
                        "coordinates": [-77.98378765, 38.45185992],
                    },
                )
                tags = json.loads(row["tags_json"])
                self.assertEqual(
                    tags["address"],
                    "14601 Germanna Hwy, Culpeper, Virginia 22701, United States",
                )
                self.assertEqual(tags["role:developer"], "DataBank")
                self.assertEqual(tags["role:operator"], "DataBank")

    def test_status_capacity_and_colocation_scope_are_exact(self) -> None:
        temporary, connection, _ = self._import()
        try:
            lifecycle = connection.execute(
                "SELECT status, as_of_date, method, confidence "
                "FROM lifecycle_observations"
            ).fetchone()
            self.assertEqual(
                tuple(lifecycle),
                (
                    "under_construction",
                    "2026-05-14",
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            capacity = connection.execute(
                "SELECT metric, stage, unit, low, base, high, method, as_of_date "
                "FROM capacity_estimates"
            ).fetchone()
            self.assertEqual(
                tuple(capacity),
                (
                    "critical_it_mw",
                    "planned",
                    "MW",
                    72.0,
                    72.0,
                    72.0,
                    "reported",
                    "2026-05-14",
                ),
            )
            model = connection.execute(
                "SELECT operating_model, as_of_date, method "
                "FROM operating_model_observations"
            ).fetchone()
            self.assertEqual(
                tuple(model), ("colocation", "2026-05-14", "company_disclosure")
            )
        finally:
            connection.close()
            temporary.cleanup()

    def test_energy_space_and_design_language_create_no_extra_facts(self) -> None:
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (capacity["metric"], capacity["stage"], capacity["base"]),
            ("critical_it_mw", "planned", 72),
        )
        for evidence in document["evidence"]:
            metadata_text = json.dumps(evidence["metadata"], ensure_ascii=False)
            self.assertIn("current", metadata_text)
            self.assertIn("energy", metadata_text)
            self.assertIn("site count", metadata_text)
        page = document["evidence"][1]["metadata"]
        self.assertIn("annual energy", page["energy_guardrail"])
        self.assertIn("metadata", page["space_guardrail"])
        self.assertIn("no current workload", page["workload_guardrail"])
        self.assertIn("no completion", page["forecast_guardrail"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(
                entity["coordinates"],
                {"latitude": 38.45185992, "longitude": -77.98378765},
            )
            self.assertEqual(
                entity["geometry"],
                {
                    "type": "Point",
                    "coordinates": [-77.98378765, 38.45185992],
                },
            )
            self.assertEqual(entity["evidence_key"], DHCD_KEY)
            self.assertEqual(entity["method"], "authoritative_address_geocode")
            self.assertEqual(entity["as_of_date"], "2026-07-20")

    def test_identity_is_new_relative_to_frozen_v60_and_time_gate_fails_closed(
        self,
    ) -> None:
        with V60_ENTITIES.open(newline="", encoding="utf-8") as handle:
            v60_keys = {row["stable_key"] for row in csv.DictReader(handle)}
        self.assertTrue({CAMPUS_KEY, PROJECT_KEY}.isdisjoint(v60_keys))
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        self.assertTrue(PROJECT_KEY.startswith(CAMPUS_KEY + ":"))
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:27:48Z",
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
