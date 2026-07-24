from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
RETRIEVED_AT = "2026-07-19T15:25:08Z"
SOURCES = {
    "curated-official-2026-07-19-microsoft-finland-espoo-01-second-building.json": (
        "f38e0458567101596f64d7b56dd5f951ef2bb744e7e9ece48e9daa66e75595fc"
    ),
    "curated-official-2026-07-19-microsoft-finland-espoo-02-phase-3-permit.json": (
        "562403abef6485297d37cc5674d2eb98d660e7e8708cbcd9e0d14d1f525e488c"
    ),
    "curated-official-2026-07-19-microsoft-finland-kirkkonummi-01-building-1.json": (
        "f410f5857ecaa05ee74ccd19c8c38d576aee45d88af4a05e42be4d4a9bdb7469"
    ),
    "curated-official-2026-07-19-microsoft-finland-kirkkonummi-02-building-2.json": (
        "30fc0b9199099021509f2712c515020e08409c7a7cfaf18a2959376172b00294"
    ),
    "curated-official-2026-07-19-microsoft-finland-vihti-01-phase-1.json": (
        "15f24270623c11a2e15aa83b346a84652d86b0eec69fb00b07318e0a73ef5171"
    ),
    "curated-official-2026-07-19-microsoft-finland-vihti-02-phase-2-permit.json": (
        "93ba074b1212d14e91a174caf68a57fdc306ce45a2da703cda44e30ad29ca68d"
    ),
}
CONTENT_HASHES = {
    "023b83bc84061ff72849b3fd93b800b4dc84315b7e3c59fcc8769a970819df4d",
    "433fd8c5c9e6ee790a19a73b408ea90c3db45c117ff3d9c178ce6f934acb6ba2",
    "4ec8ee3662c5dbad6c74417c89de53655000c36d007d4025b1e6f1837c431697",
    "b8ca46e287628c6b2d7421fdb5b1459cc7e21ddf3ebfa9ee114c8fa2874a7e57",
    "d8877277d46bce7fecfaf3bf931611fb0a68d0fffd1c4b2f0c68cd1aeea5ca6b",
}


class MicrosoftFinlandConstructionTests(unittest.TestCase):
    def test_physical_projects_and_permits_remain_distinct_without_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch(
                    "socket.socket", side_effect=AssertionError("network used")
                ), patch(
                    "socket.create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected_sha256 in sorted(SOURCES.items()):
                        path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        self.assertEqual(
                            {row["retrieved_at"] for row in document["evidence"]},
                            {RETRIEVED_AT},
                        )
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=RETRIEVED_AT,
                        )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 3), ("project", 6)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.method,
                               lifecycle_observations.as_of_date,
                               evidence.source_family
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        JOIN evidence ON evidence.id = lifecycle_observations.evidence_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:microsoft-finland-espoo-hepokorpi-campus:phase-3",
                            "permitted",
                            "government_record",
                            "2026-06-11",
                            "finnish_municipal_data_center_updates",
                        ),
                        (
                            "curated:microsoft-finland-espoo-hepokorpi-campus:second-building",
                            "under_construction",
                            "authoritative_construction_start",
                            "2026-05-01",
                            "microsoft_local_project_updates",
                        ),
                        (
                            "curated:microsoft-finland-kirkkonummi-campus:building-1",
                            "under_construction",
                            "authoritative_construction_start",
                            "2026-04-01",
                            "microsoft_local_project_updates",
                        ),
                        (
                            "curated:microsoft-finland-kirkkonummi-campus:building-2",
                            "under_construction",
                            "authoritative_construction_start",
                            "2026-04-01",
                            "microsoft_local_project_updates",
                        ),
                        (
                            "curated:microsoft-finland-vihti-campus:phase-1",
                            "under_construction",
                            "authoritative_construction_start",
                            "2026-04-28",
                            "finnish_municipal_data_center_updates",
                        ),
                        (
                            "curated:microsoft-finland-vihti-campus:phase-2",
                            "permitted",
                            "authoritative_status_update",
                            "2026-04-28",
                            "microsoft_official_news",
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        WHERE entities.kind != 'project'
                        """
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT source_family, COUNT(*) FROM evidence "
                        "GROUP BY source_family ORDER BY source_family"
                    )],
                    [
                        ("finnish_municipal_data_center_updates", 2),
                        ("microsoft_local_project_updates", 2),
                        ("microsoft_official_news", 1),
                    ],
                )
                self.assertEqual(
                    {
                        row[0]
                        for row in connection.execute(
                            "SELECT content_hash FROM evidence"
                        )
                    },
                    CONTENT_HASHES,
                )

                ppa_record = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence WHERE content_hash = ?",
                    (
                        "b8ca46e287628c6b2d7421fdb5b1459cc7e21ddf3ebfa9ee114c8fa2874a7e57",
                    ),
                ).fetchone()[0])["record"]
                self.assertIn("more-than-200-MW", ppa_record["ppa_guardrail"])
                self.assertIn("not site load", ppa_record["ppa_guardrail"])
                self.assertIn(
                    "remains permitted and is not under construction",
                    ppa_record["construction_guardrail"],
                )

                phase_three_record = json.loads(connection.execute(
                    "SELECT metadata_json FROM evidence WHERE content_hash = ?",
                    (
                        "4ec8ee3662c5dbad6c74417c89de53655000c36d007d4025b1e6f1837c431697",
                    ),
                ).fetchone()[0])["record"]
                self.assertIn(
                    "remains permitted, not under construction",
                    phase_three_record["permit_guardrail"],
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
                        "SELECT COUNT(*) FROM evidence WHERE kind='satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute(
                    "SELECT entities.stable_key, entity_snapshots.name, "
                    "entity_snapshots.tags_json, entity_snapshots.confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id"
                ):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                    self.assertNotIn("HEL04", row["stable_key"])
                    self.assertNotIn("HEL04", row["name"])
                    self.assertLessEqual(row["confidence"], 0.15)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
