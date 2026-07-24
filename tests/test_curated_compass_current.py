from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T05:23:12Z"
SOURCES = {
    "curated-official-2026-07-20-compass-meridian-current-development.json": (
        "a964e25a27f719b9533727dfa09732295a25379ace88c6acc688bde0772abec4"
    ),
    "curated-official-2026-07-20-compass-red-oak-current-development.json": (
        "f6ca71ac9267b43124a86f7550d33453e25e0ba129cfb70ba35d008903462dc5"
    ),
}
CAPTURES = {
    "0731e336238ef93cc52201f87afc78f86c8af0c921578c173d7fe22ce9b12a34": {
        "bytes": 118_032,
        "response_http_date": "2026-07-20T05:21:55Z",
        "source_url": "https://www.compassdatacenters.com/data-center-markets/",
    },
    "897e275f64c6ee4b99449259110f033ba3104d039df6fca07a03634a8b398ddc": {
        "bytes": 176_450,
        "response_http_date": "2026-07-20T05:23:12Z",
        "source_url": (
            "https://mississippi.org/news/compass-datacenters-project-generates-"
            "10-billion-investment-in-lauderdale-county/"
        ),
    },
}


class CompassCurrentConstructionTests(unittest.TestCase):
    def test_exact_sources_import_two_projects_and_one_typed_capacity(self) -> None:
        documents: dict[str, dict] = {}
        seen_captures: dict[str, dict] = {}

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
                ), patch.object(
                    socket,
                    "getaddrinfo",
                    side_effect=AssertionError("DNS used"),
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
                            {evidence["retrieved_at"] for evidence in document["evidence"]},
                            {RETRIEVED_AT},
                        )
                        for entity in (document["campus"], document["project"]):
                            self.assertEqual(entity["roles"], {})
                            self.assertIsNone(entity["coordinates"])
                            self.assertIsNone(entity["geometry"])
                            self.assertEqual(entity["method"], "authoritative_locality")
                        self.assertEqual(document["operating_models"], [])
                        self.assertEqual(document["workloads"], [])
                        self.assertEqual(len(document["lifecycle"]), 1)
                        self.assertEqual(document["lifecycle"][0]["entity"], "project")
                        self.assertEqual(
                            document["lifecycle"][0]["value"], "under_construction"
                        )
                        self.assertEqual(
                            document["lifecycle"][0]["method"],
                            "authoritative_physical_status_update",
                        )
                        for evidence in document["evidence"]:
                            expected = CAPTURES[evidence["content_hash"]]
                            metadata = evidence["metadata"]
                            self.assertEqual(
                                metadata["content_hash_verification"],
                                "fetched_bytes_sha256",
                            )
                            self.assertIn(
                                str(expected["bytes"]), metadata["content_hash_scope"]
                            )
                            self.assertEqual(
                                metadata["response_http_date"],
                                expected["response_http_date"],
                            )
                            self.assertEqual(evidence["source_url"], expected["source_url"])
                            self.assertEqual(metadata["canonical_url"], expected["source_url"])
                            seen_captures[evidence["content_hash"]] = expected
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            path,
                            retrieved_at=RETRIEVED_AT,
                        )

                self.assertEqual(seen_captures, CAPTURES)
                compass_evidence = documents[
                    "curated-official-2026-07-20-compass-red-oak-current-development.json"
                ]["evidence"][0]
                self.assertEqual(
                    compass_evidence,
                    documents[
                        "curated-official-2026-07-20-compass-meridian-current-development.json"
                    ]["evidence"][0],
                )
                metadata = compass_evidence["metadata"]
                self.assertIn("nearing-completion", metadata["red_oak_status_scope"])
                self.assertIn("past-year groundbreaking", metadata["meridian_status_scope"])
                self.assertIn("untyped source metadata", metadata["red_oak_capacity_guardrail"])
                self.assertIn("untyped source metadata", metadata["meridian_capacity_guardrail"])
                self.assertIn("does not create", metadata["other_market_guardrail"])

                meridian = documents[
                    "curated-official-2026-07-20-compass-meridian-current-development.json"
                ]
                self.assertEqual(len(meridian["capacities"]), 1)
                capacity = meridian["capacities"][0]
                self.assertEqual(
                    (
                        capacity["entity"],
                        capacity["metric"],
                        capacity["stage"],
                        capacity["low"],
                        capacity["base"],
                        capacity["high"],
                    ),
                    ("campus", "grid_connection_mw", "planned", 500, 500, 500),
                )
                self.assertIn("approximately 500 MW", capacity["notes"])
                mda_metadata = meridian["evidence"][1]["metadata"]
                self.assertEqual(mda_metadata["data_center_count_as_reported"], 8)
                self.assertIn("do not establish eight current", mda_metadata["program_scope"])
                self.assertIn("not reconciled", mda_metadata["compass_market_capacity_conflict_guardrail"])
                self.assertEqual(
                    documents[
                        "curated-official-2026-07-20-compass-red-oak-current-development.json"
                    ]["capacities"],
                    [],
                )

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               lifecycle_observations.status,
                               lifecycle_observations.as_of_date,
                               lifecycle_observations.method
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:compass-meridian-mississippi-data-center-campus:current-campus-development",
                            "under_construction",
                            "2026-04-22",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:compass-red-oak-texas-data-center-campus:current-campus-development",
                            "under_construction",
                            "2026-04-22",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               capacity_estimates.metric,
                               capacity_estimates.stage,
                               capacity_estimates.low,
                               capacity_estimates.base,
                               capacity_estimates.high,
                               capacity_estimates.as_of_date
                        FROM capacity_estimates
                        JOIN entities ON entities.id = capacity_estimates.entity_id
                        """
                    )],
                    [
                        (
                            "curated:compass-meridian-mississippi-data-center-campus",
                            "grid_connection_mw",
                            "planned",
                            500.0,
                            500.0,
                            500.0,
                            "2025-01-09",
                        )
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates WHERE metric != 'grid_connection_mw'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    2,
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
                        "SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL "
                        "OR longitude IS NOT NULL OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
