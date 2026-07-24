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
    / "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json"
)
V62_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v62/entities.csv"
SOURCE_SHA256 = "d5210ad0ba71d90aef22128e4642cb2ab18fe78325d9491a8d58d97d010731a0"
RECORDED_AT = "2026-07-21T04:55:00Z"
COUNTY_NEWS_KEY = "fayette-county-qts-fayetteville-facts-2026-05-13-captured-2026-07-20"
MINUTES_KEY = "fayette-county-retreat-minutes-qts-2026-05-13-captured-2026-07-20"
CITY_KEY = "fayetteville-georgia-data-center-discussion-captured-2026-07-20"
QTS_KEY = "qts-fayetteville-current-location-page-captured-2026-07-20"
CAMPUS_KEY = "curated:qts-fayetteville-georgia-data-center-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:active-campus-construction-program"


class QtsFayettevilleConstructionProgramTests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError("QTS Fayetteville curated import attempted network")
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
        self.assertEqual(len(data), 23_770)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        document = json.loads(data.decode("utf-8"))
        self.assertEqual(
            data.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [COUNTY_NEWS_KEY, MINUTES_KEY, CITY_KEY, QTS_KEY],
        )
        expected = (
            (
                "31d60adc6ab27bfa678e8ab7a58635508c0d6ad5bee1e9ce4a172c93d8df4885",
                84_295,
                "cfb31904bf127e638943edded2b15e6d3522cf95274a90996b2d7b69ac012ef3",
                "86d5ee625416ed444694c5ea4bf918a70b281b850ae84a4d31172dcec887ed1a",
                "2026-07-21T04:49:21Z",
            ),
            (
                "f5500b24a646524e8a3c939c1868071a482cc7fce595ece10182dd2875bfe9bd",
                495_205,
                "ea3894de086cc50f88bbeb975d33d26221b1fccd0651ca98647197807ade0fc9",
                "652ba60f0c75ca918a29e43a3399b24bc076e8098f3be240957000963b1666b9",
                "2026-07-21T04:49:21Z",
            ),
            (
                "5e911d203bfc712161b7c73d4fc7592357ac3828b2b7ee11da72096dd8e75f38",
                137_311,
                "b8fac54194675d0175e62bcefbc46b62ee83c2b4634da62d42ee1ae29f0342b4",
                "4a56c465fca2c84063f70e93ca10681f415c2f7db020ffb94e2683af6e5263ef",
                "2026-07-21T04:49:22Z",
            ),
            (
                "6136c7e9d1f65a4d1fa06836f4208281f2167eeda6c27a455dfe1dacf0cc05b8",
                371_148,
                "125b90232c26efecf57b01ff5f8e2b8df258a3b52ee590cdb11ced8ad122de8b",
                "e16fe8c57bddce95d40126530189c60b43ac4c8556c4a8a3a0704ce2844b8664",
                "2026-07-21T04:49:53Z",
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
        self.assertEqual(document["evidence"][1]["metadata"]["document_pages"], 25)
        self.assertEqual(
            document["evidence"][3]["metadata"]["structured_date_modified"],
            "2026-07-15T16:47:03+00:00",
        )

    def test_offline_import_has_exact_source_scoped_rows(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary, connection, result = self._import()
            stack.callback(temporary.cleanup)
            stack.callback(connection.close)
            self.assertEqual(result.entities_created, 2)
            self.assertEqual(result.evidence_created, 4)
            self.assertEqual(result.warnings, ())
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "capacity_estimates",
                    "operating_model_observations",
                    "workload_observations",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 4,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "capacity_estimates": 0,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                },
            )
            snapshots = list(
                connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                [row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY]
            )
            for row in snapshots:
                self.assertIsNone(row["latitude"])
                self.assertIsNone(row["longitude"])
                self.assertIsNone(row["geometry_json"])
                tags = json.loads(row["tags_json"])
                self.assertEqual(
                    tags["address"], "Fayetteville, Georgia, United States"
                )
                self.assertFalse(any(key.startswith("role:") for key in tags))

    def test_status_is_one_source_bounded_program_not_thirteen_buildings(self) -> None:
        temporary, connection, _ = self._import()
        try:
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
                    "2026-05-13",
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM entities WHERE kind = 'project'"
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()
            temporary.cleanup()

    def test_water_topology_and_future_operation_create_no_extra_facts(self) -> None:
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(len(document["lifecycle"]), 1)
        minutes = document["evidence"][1]["metadata"]
        self.assertIn("aggregate", minutes["lifecycle_scope"])
        self.assertIn(
            "not thirteen current projects", minutes["building_count_guardrail"]
        )
        self.assertIn("not normalized", minutes["coming_online_guardrail"])
        self.assertIn("not WUE", minutes["water_guardrail"])
        city = document["evidence"][2]["metadata"]
        self.assertEqual(city["reported_building_plan"], 13)
        self.assertEqual(city["reported_total_square_feet_approximate"], 6_200_000)
        self.assertIn("no lifecycle observation", city["lifecycle_guardrail"])
        qts = document["evidence"][3]["metadata"]
        self.assertIn("future cooling behavior", qts["future_operation_guardrail"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])

    def test_identity_is_new_relative_to_v62_and_calendar_gate_fails_closed(
        self,
    ) -> None:
        with V62_ENTITIES.open(newline="", encoding="utf-8") as handle:
            v62_keys = {row["stable_key"] for row in csv.DictReader(handle)}
        self.assertTrue({CAMPUS_KEY, PROJECT_KEY}.isdisjoint(v62_keys))
        self.assertNotIn("2026-07-21", SOURCE.name)
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(
            all("2026-07-21" not in row["key"] for row in document["evidence"])
        )
        self.assertLessEqual(document["campus"]["as_of_date"], "2026-07-20")
        self.assertLessEqual(document["project"]["as_of_date"], "2026-07-20")
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:49:52Z",
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
