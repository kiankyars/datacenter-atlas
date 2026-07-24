from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
SOURCES = {
    "curated-official-2026-07-19-qts-cambois-earthworks.json": (
        "1960b1cdfdde3da6cebfccb006ebdd6addc85bc1079c3b111b3f5b38bf5d8e89"
    ),
    "curated-official-2026-07-19-qts-cedar-rapids-current-campus-development.json": (
        "0b8a466bc192a20b432e621081612927374d4cd0949553ef2c5c7aed8499bcd5"
    ),
    "curated-official-2026-07-19-qts-eagle-mountain-building-1.json": (
        "a53e19f3f7042674b378cd736f703e53568ae8d71a6b1d5ba153c9282b4e3ef0"
    ),
    "curated-official-2026-07-19-qts-eagle-mountain-building-2.json": (
        "c3a1da2ebea96d1e3427ee272fa4fc66f968da3ccc6e0014a122e52be6bdea21"
    ),
    "curated-official-2026-07-19-qts-eagle-mountain-building-3.json": (
        "054bc66a6cdbc880211c1947a0bb4b0c3ec3786bde727c7845fd8e49742d1967"
    ),
    "curated-official-2026-07-19-qts-york-initial-phase-building-1.json": (
        "11b588dfcd677fc3a5b5f8807e7aa4041f6f5e9b4fe8d31459034401d1692c4c"
    ),
}
BATCH_RETRIEVED_AT = {
    "curated-official-2026-07-19-qts-cambois-earthworks.json": (
        "2026-07-19T16:29:03Z"
    ),
    "curated-official-2026-07-19-qts-cedar-rapids-current-campus-development.json": (
        "2026-07-19T16:29:03Z"
    ),
    "curated-official-2026-07-19-qts-eagle-mountain-building-1.json": (
        "2026-07-19T16:45:08Z"
    ),
    "curated-official-2026-07-19-qts-eagle-mountain-building-2.json": (
        "2026-07-19T16:45:08Z"
    ),
    "curated-official-2026-07-19-qts-eagle-mountain-building-3.json": (
        "2026-07-19T16:45:08Z"
    ),
    "curated-official-2026-07-19-qts-york-initial-phase-building-1.json": (
        "2026-07-19T16:40:30Z"
    ),
}
CAPTURES = {
    "351c687edfe19a2c948815b6e4d60061de1fdc8dee12f944796c2d2134d8d176": (
        272322,
        "2026-07-19T16:45:08Z",
        "https://eaglemountain.gov/eagle-mountain-city-celebrates-major-milestone-with-qts-topping-out-ceremony/",
    ),
    "400cb1d0d1414483ee0d81c7b37b00716a4493b806f635622c9b411c427baf8a": (
        455028,
        "2026-07-19T16:37:52Z",
        "https://q.com/data-centers/eagle-mountain/",
    ),
    "673d0a607d69ab3a249142d0632525d4170446bae8931aa74ab117d725fb86df": (
        128506,
        "2026-07-19T16:29:04Z",
        "https://www.gilbaneco.com/about/whats-new/news/gilbane-marks-steel-topping-out-milestone-for-data-center-campus-in-upstate-south-carolina/",
    ),
    "6eab7c0ac2af11363f89c7d3257d1e17e072a60b1bb1a15055d638acd770a06c": (
        325306,
        "2026-07-19T16:29:03Z",
        "https://q.com/data-centers/cambois/",
    ),
    "6f8ea57f1adf6106c79a3a3ac87f720d3977198e95b90cae6849462eb1b1d4e5": (
        270506,
        "2026-07-19T16:37:52Z",
        "https://q.com/news/layton-construction-and-qts-data-centers-celebrate-topping-out-of-data-center-campus-in-eagle-mountain/",
    ),
    "b42fe80b92a4af49d68864c87f42483a68414bff15280be439d810a703fa924b": (
        312862,
        "2026-07-19T16:29:03Z",
        "https://q.com/data-centers/cedar-rapids/",
    ),
    "b8b5aa37394875dd4a3223ab6dc8d4e9c2f84311e22c917e7f171935da4b5474": (
        153371,
        "2026-07-19T16:42:47Z",
        "https://www.laytonconstruction.com/slc1-data-center-topping-out/",
    ),
    "d11b5b153f42cd5f96da2a20552c8c62387c0b3ca2604178dd83779ec7d90a6b": (
        490023,
        "2026-07-19T16:40:30Z",
        "https://q.com/data-centers/york/",
    ),
}


class QTSCurrentConstructionTests(unittest.TestCase):
    def test_exact_sources_import_only_six_narrow_current_projects(self) -> None:
        documents: dict[str, dict[str, object]] = {}
        seen_captures: dict[str, tuple[int, str, str]] = {}

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket,
                    "socket",
                    side_effect=AssertionError("network used"),
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected_sha256 in sorted(SOURCES.items()):
                        path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        documents[name] = document
                        self.assertEqual(document["schema_version"], "1.0")
                        self.assertEqual(
                            {row["retrieved_at"] for row in document["evidence"]},
                            {BATCH_RETRIEVED_AT[name]},
                        )
                        self.assertEqual(document["campus"]["roles"], {})
                        self.assertEqual(document["project"]["roles"], {})
                        for entity in (document["campus"], document["project"]):
                            self.assertIsNone(entity["coordinates"])
                            self.assertIsNone(entity["geometry"])
                            self.assertEqual(entity["method"], "authoritative_locality")
                        self.assertEqual(len(document["lifecycle"]), 1)
                        self.assertEqual(document["lifecycle"][0]["entity"], "project")
                        self.assertEqual(
                            document["lifecycle"][0]["method"],
                            "authoritative_physical_status_update",
                        )
                        self.assertEqual(document["operating_models"], [])
                        self.assertEqual(document["workloads"], [])
                        self.assertEqual(document["capacities"], [])

                        for evidence in document["evidence"]:
                            content_hash = evidence["content_hash"]
                            expected_capture = CAPTURES[content_hash]
                            metadata = evidence["metadata"]
                            self.assertEqual(
                                metadata["content_hash_verification"],
                                "fetched_bytes_sha256",
                            )
                            self.assertIn(
                                str(expected_capture[0]),
                                metadata["content_hash_scope"],
                            )
                            self.assertEqual(
                                metadata["response_retrieved_at"],
                                expected_capture[1],
                            )
                            self.assertEqual(evidence["source_url"], expected_capture[2])
                            self.assertEqual(metadata["canonical_url"], expected_capture[2])
                            self.assertTrue(evidence["source_url"].startswith("https://"))
                            seen_captures[content_hash] = expected_capture

                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=BATCH_RETRIEVED_AT[name],
                        )

                self.assertEqual(seen_captures, CAPTURES)

                eagle_names = [
                    f"curated-official-2026-07-19-qts-eagle-mountain-building-{number}.json"
                    for number in (1, 2, 3)
                ]
                first_eagle = documents[eagle_names[0]]
                for name in eagle_names[1:]:
                    self.assertEqual(documents[name]["campus"], first_eagle["campus"])
                    self.assertEqual(documents[name]["evidence"], first_eagle["evidence"])

                cambois = documents[
                    "curated-official-2026-07-19-qts-cambois-earthworks.json"
                ]["evidence"][0]["metadata"]
                self.assertIn("eastern and southern", cambois["status_scope"])
                self.assertIn("first data-centre building", cambois["future_work_guardrail"])
                self.assertIn("Neither future statement", cambois["future_work_guardrail"])

                cedar_document = documents[
                    "curated-official-2026-07-19-qts-cedar-rapids-current-campus-development.json"
                ]
                cedar = cedar_document["evidence"][0]["metadata"]
                self.assertEqual(len(cedar["project_locations_as_reported"]), 3)
                self.assertIn("do not create three building projects", cedar["individual_building_guardrail"])
                self.assertIn("up-to-seven-building", cedar["full_build_guardrail"])
                self.assertNotIn("6200", cedar_document["campus"]["address"])
                self.assertEqual(
                    cedar_document["project"]["address"],
                    "Cedar Rapids, Iowa, United States",
                )

                york_document = documents[
                    "curated-official-2026-07-19-qts-york-initial-phase-building-1.json"
                ]
                york_evidence = {
                    row["key"]: row["metadata"] for row in york_document["evidence"]
                }
                gilbane = york_evidence["gilbane-qts-york-topout-captured-2026-07-19"]
                qts_york = york_evidence["qts-york-location-page-captured-2026-07-19"]
                self.assertIn("first building in the initial phase", gilbane["status_scope"])
                self.assertIn("not enclosure completion", gilbane["stage_guardrail"])
                self.assertIn("does not create an unnamed second-building", qts_york["current_count_guardrail"])
                self.assertIn("nine-building", qts_york["phase_guardrail"])
                self.assertEqual(
                    york_document["campus"]["address"],
                    "2143 Hands Mill Hwy, Rock Hill, South Carolina 29745",
                )
                self.assertEqual(
                    york_document["project"]["address"],
                    "York, South Carolina, United States",
                )

                eagle_evidence = {
                    row["key"]: row["metadata"] for row in first_eagle["evidence"]
                }
                eagle_location = eagle_evidence[
                    "qts-eagle-mountain-location-page-captured-2026-07-19"
                ]
                eagle_topout = eagle_evidence[
                    "qts-eagle-mountain-building-3-topout-captured-2026-07-19"
                ]
                eagle_city = eagle_evidence[
                    "eagle-mountain-city-qts-topout-conflict-captured-2026-07-19"
                ]
                self.assertIn("Building 1, Building 2, and Building 3", eagle_location["status_scope"])
                self.assertIn("Buildings 4 and 5", eagle_location["future_building_guardrail"])
                self.assertIn("third building", eagle_topout["building_identity_guardrail"])
                self.assertIn("does not support shell status for Building 1", eagle_topout["building_identity_guardrail"])
                self.assertIn("conflicts", eagle_city["conflict_guardrail"])
                self.assertIn("does not create a Building 1 shell", eagle_city["conflict_guardrail"])

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 4), ("project", 6)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT project_entity.stable_key,
                               campus_entity.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.as_of_date,
                               lifecycle_observations.method
                        FROM lifecycle_observations
                        JOIN entities AS project_entity
                          ON project_entity.id = lifecycle_observations.entity_id
                        JOIN projects ON projects.entity_id = project_entity.id
                        JOIN entities AS campus_entity
                          ON campus_entity.id = projects.target_entity_id
                        ORDER BY project_entity.stable_key
                        """
                    )],
                    [
                        (
                            "curated:qts-cambois-data-centre-campus:2026-earthworks",
                            "curated:qts-cambois-data-centre-campus",
                            "civil_works",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:qts-cedar-rapids-data-center-campus:current-campus-development",
                            "curated:qts-cedar-rapids-data-center-campus",
                            "under_construction",
                            "2026-07-15",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:qts-eagle-mountain-slc1-data-center-campus:building-1",
                            "curated:qts-eagle-mountain-slc1-data-center-campus",
                            "under_construction",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:qts-eagle-mountain-slc1-data-center-campus:building-2",
                            "curated:qts-eagle-mountain-slc1-data-center-campus",
                            "under_construction",
                            "2026-07-01",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:qts-eagle-mountain-slc1-data-center-campus:building-3",
                            "curated:qts-eagle-mountain-slc1-data-center-campus",
                            "shell",
                            "2026-04-17",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:qts-york-county-south-carolina-data-center-campus:initial-phase-building-1",
                            "curated:qts-york-county-south-carolina-data-center-campus",
                            "shell",
                            "2026-06-30",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations "
                        "JOIN entities ON entities.id = lifecycle_observations.entity_id "
                        "WHERE entities.kind != 'project'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL "
                        "OR longitude IS NOT NULL OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
                    10,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    8,
                )
                self.assertEqual(
                    {row[0] for row in connection.execute("SELECT content_hash FROM evidence")},
                    set(CAPTURES),
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations "
                        "WHERE status IN ('commissioning', 'operational')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE kind = 'satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
