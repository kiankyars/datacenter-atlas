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
    / "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json"
)
V62_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v62/entities.csv"
SOURCE_SHA256 = "03e3c1de817fba2a0b14d42ec5d063caf07ac23df4083b22bd0a99f6803d0990"
RECORDED_AT = "2026-07-21T04:40:00Z"
POST_KEY = "powerhouse-irving-building-1-topout-2026-03-27-captured-2026-07-20"
PAGE_KEY = "powerhouse-irving-current-facility-page-captured-2026-07-20"
RELEASE_KEY = "powerhouse-irving-address-release-2024-05-15-captured-2026-07-20"
CAMPUS_KEY = "curated:powerhouse-irving-data-center-campus"
PROJECT_KEY = f"{CAMPUS_KEY}:building-1-current-build"


class PowerHouseIrvingBuilding1Tests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "PowerHouse Irving curated import attempted network access"
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
        self.assertEqual(len(data), 21_449)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        document = json.loads(data.decode("utf-8"))
        self.assertEqual(
            data.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [POST_KEY, PAGE_KEY, RELEASE_KEY],
        )
        expected = (
            (
                "590313c03194a2d12d7451932a15835fd4298962e0acf0c5e40cdc3d9cb64bc4",
                130_148,
                "085becefaf721a321e265b70d9bd865991d5e46d729ad44953f0801b2cca4a7c",
                "2ccc0d8d71c4b082fcb8c1ee475cb0a1ef09738a79d2f616f14728342565482e",
                "2026-07-21T04:38:25Z",
            ),
            (
                "0aa31b1d4465950ba72f69d09efd210bdbfa8b1ba497e23d1c4b80d8b6a77ebf",
                25_220,
                "cfbcb2cd23ba8018d7350b693d6272d4edcc02bdfa7ffa7439e2f3ed723f4f99",
                "98ea2ca9eb0a8d3d47ce1c6e390b82fa61b12dfecc8ca03343144e95ded1946f",
                "2026-07-21T04:38:25Z",
            ),
            (
                "ad1ac50546f945177860892a5aa1a6bce40e255120a96d38fbdf65c7935c9c72",
                21_334,
                "7a993c37b1f3f0d8dd1dee76ac4d3ea17687d70c75fd2792535432253ed580de",
                "cee9a91874da60c9255914edd04255443eecac3e578e083b0f5303e62611c391",
                "2026-07-21T04:38:54Z",
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
            "2026-03-27T13:45:09.448Z",
        )
        self.assertEqual(
            document["evidence"][1]["metadata"]["reported_max_utility_power_mw"],
            201,
        )
        self.assertEqual(
            document["evidence"][2]["metadata"]["reported_address"],
            "111 Customer Way, Irving-Las Colinas, Irving, Texas, United States",
        )

    def test_offline_import_has_exact_source_scoped_rows_and_roles(self) -> None:
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
                    "capacity_estimates",
                    "operating_model_observations",
                    "workload_observations",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 3,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "capacity_estimates": 1,
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
                    tags["address"], "111 Customer Way, Irving, Texas, United States"
                )
                self.assertEqual(tags["role:developer"], "PowerHouse Data Centers")
            project_tags = json.loads(snapshots[1]["tags_json"])
            self.assertEqual(project_tags["role:contractor"], "Brasfield & Gorrie, LLC")
            self.assertNotIn("role:operator", project_tags)
            self.assertNotIn("role:tenant", project_tags)

    def test_shell_status_and_campus_utility_capacity_are_not_conflated(self) -> None:
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
                    "shell",
                    "2026-03-27",
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            capacity = connection.execute(
                "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                "method, as_of_date FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(capacity),
                (
                    CAMPUS_KEY,
                    "grid_connection_mw",
                    "planned",
                    "MW",
                    201.0,
                    201.0,
                    201.0,
                    "reported",
                    "2026-07-20",
                ),
            )
        finally:
            connection.close()
            temporary.cleanup()

    def test_online_wording_area_and_three_building_plan_create_no_extra_facts(
        self,
    ) -> None:
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["lifecycle"]), 1)
        self.assertEqual(document["lifecycle"][0]["value"], "shell")
        self.assertEqual(len(document["capacities"]), 1)
        self.assertEqual(
            (
                document["capacities"][0]["entity"],
                document["capacities"][0]["metric"],
                document["capacities"][0]["stage"],
                document["capacities"][0]["base"],
            ),
            ("campus", "grid_connection_mw", "planned", 201),
        )
        post = document["evidence"][0]["metadata"]
        self.assertIn("not normalized as operational", post["online_wording_guardrail"])
        self.assertIn("not allocated", post["capacity_scope"])
        self.assertIn("not three project records", post["building_count_guardrail"])
        release = document["evidence"][2]["metadata"]
        self.assertIn("historical metadata only", release["capacity_guardrail"])
        for entity in (document["campus"], document["project"]):
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])

    def test_identity_is_new_relative_to_v62_and_time_gate_fails_closed(self) -> None:
        with V62_ENTITIES.open(newline="", encoding="utf-8") as handle:
            v62_keys = {row["stable_key"] for row in csv.DictReader(handle)}
        self.assertTrue({CAMPUS_KEY, PROJECT_KEY}.isdisjoint(v62_keys))
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:38:53Z",
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
