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
SOURCES = {
    "curated-official-2026-07-19-applied-digital-delta-forge-1.json": (
        "a7bbaf9f8da95c56a50d27ce7b4326a1c1f886499fc591faff0888203aa8db1c"
    ),
    "curated-official-2026-07-19-applied-digital-pf1-second-150mw.json": (
        "bb586f6351c3b97f099c485e067b6e1c843d795d612f76b00f0612470d381332"
    ),
    "curated-official-2026-07-19-applied-digital-pf1-third-150mw.json": (
        "899b21e24ca42037f3acf6f19f219f7d2392ba4c6e256d4e1f9d70f8f9bcd504"
    ),
    "curated-official-2026-07-19-applied-digital-pf2-building-1.json": (
        "87c7bed88dd9459eca7ec156bb383eb665d89a1cb91a375728e0db127624dda1"
    ),
    "curated-official-2026-07-19-applied-digital-pf2-building-2.json": (
        "d4831e42ab2a60ff403dad49eba1c1c4f5e8469274ff606428cd24f7a2a44f29"
    ),
}


class AppliedDigitalConstructionDisclosureTests(unittest.TestCase):
    def test_five_physical_projects_keep_load_and_generation_semantics_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch(
                    "socket.create_connection", side_effect=AssertionError("network used")
                ):
                    for name, expected_sha256 in sorted(SOURCES.items()):
                        path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(),
                            expected_sha256,
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        retrieved_at = {
                            row["retrieved_at"] for row in document["evidence"]
                        }
                        self.assertEqual(retrieved_at, {"2026-07-19T14:27:13Z"})
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=retrieved_at.pop(),
                        )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 3), ("project", 5)],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.kind, lifecycle_observations.status, COUNT(*)
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        GROUP BY entities.kind, lifecycle_observations.status
                        """
                    )],
                    [("project", "under_construction", 5)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT metric, stage, COUNT(*), SUM(base)
                        FROM capacity_estimates
                        GROUP BY metric, stage
                        ORDER BY metric, stage
                        """
                    )],
                    [
                        ("critical_it_mw", "contracted", 3, 600.0),
                        ("critical_it_mw", "planned", 2, 300.0),
                        ("generation_nameplate_mw", "planned", 1, 576.0),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM capacity_estimates
                        WHERE metric IN (
                            'gross_facility_mw', 'grid_connection_mw', 'annual_energy_mwh'
                        )
                        """
                    ).fetchone()[0],
                    0,
                )
                generation = connection.execute(
                    """
                    SELECT capacity_estimates.method, capacity_estimates.notes,
                           evidence.kind, evidence.source_family,
                           evidence.metadata_json
                    FROM capacity_estimates
                    JOIN evidence ON evidence.id = capacity_estimates.evidence_id
                    WHERE capacity_estimates.metric = 'generation_nameplate_mw'
                    """
                ).fetchone()
                self.assertEqual(generation["method"], "calculated")
                self.assertEqual(generation["kind"], "government_record")
                self.assertEqual(
                    generation["source_family"],
                    "north_dakota_deq_air_quality_records",
                )
                self.assertIn("not data-center load", generation["notes"])
                metadata = json.loads(generation["metadata_json"])["record"]
                self.assertIn("emergency-generation nameplate", metadata["generation_guardrail"])
                self.assertIn("draft AQEA", metadata["permit_guardrail"])
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
