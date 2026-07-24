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
    "curated-official-2026-07-19-colt-london4-hayes.json": (
        "44a4569bed0c12103d726d0e73f8a05078f4528c74c7f032dfc5feaa9ea0b05b",
        "2026-07-19T17:00:24Z",
    ),
    "curated-official-2026-07-19-cyrusone-dfw7-fort-worth.json": (
        "be3c809f135e8c00b8cd299e99ae6a5cce6cd22642bb719e86ffbb0ac4b105ee",
        "2026-07-19T16:59:09Z",
    ),
    "curated-official-2026-07-19-cyrusone-mil1-segrate.json": (
        "393fd497f26e46ab15831f2d8b0dd9cf74356c65d54436e9e5139a9e1a3a975e",
        "2026-07-19T16:59:11Z",
    ),
    "curated-official-2026-07-19-cyrusone-yorkville-technology-campus.json": (
        "358f37b1e224488f38ebdaf590ffc1ddb1fd2bc3fbd3e01edca960c91c572c9b",
        "2026-07-19T16:59:12Z",
    ),
}
CAPTURES = {
    "09c60fc430f4bfa1123a52121cec0774c799f17ac773bfd0d81c0d1fa2a98ce2": (
        117688,
        "2026-07-19T16:59:12Z",
        "2026-07-19T16:59:12Z",
        "2026-07-16T12:21:57Z",
        "https://www.cyrusone.com/data-centers/north-america/yorkville-technology-campus",
    ),
    "4f4e24a958e8544022e2b39e10d10bc4bd881c647f11ac2ab81765a9ff0e2b5c": (
        289406,
        "2026-07-19T16:59:13Z",
        "2026-07-19T16:59:13Z",
        "2026-07-19T16:59:13Z",
        "https://www.coltdatacentres.net/en-GB/our-locations/data-centre-locations-europe/london-4/timeline",
    ),
    "694bd8798e4a5223011bc1a3a4e2d8a02ba488a16a95556f8958369179215621": (
        88925,
        "2026-07-19T16:59:09Z",
        "2026-07-19T16:59:09Z",
        "2026-07-16T12:21:53Z",
        "https://www.cyrusone.com/resources/press-releases/cyrusone-and-eolian-partner-to-enable-rapid-deployment-of-200-megawatt-data-center-campus-in-fort-worth-texas",
    ),
    "b5f0fafe970e5a1c744d571a45ce4407c76fb374a0b1d03784607dbf68648a25": (
        257943,
        "2026-07-19T17:00:24Z",
        "2026-07-19T17:00:24Z",
        "2026-07-19T17:00:24Z",
        "https://www.coltdatacentres.net/en-GB/our-locations/data-centre-locations-europe/london-4",
    ),
    "e2aa8cb6b5bbdb744b553a1cac1dc314ccb022e351085ac107fce01235ebd795": (
        90919,
        "2026-07-19T16:59:11Z",
        "2026-07-19T16:59:11Z",
        "2026-07-16T12:21:58Z",
        "https://www.cyrusone.com/resources/press-releases/cyrusone-breaks-ground-on-first-data-center-in-italy",
    ),
}


class CyrusOneColtCurrentConstructionTests(unittest.TestCase):
    def test_exact_sources_import_only_supported_current_claims(self) -> None:
        documents: dict[str, dict[str, object]] = {}
        seen_captures: set[str] = set()

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, (expected_hash, retrieved_at) in sorted(SOURCES.items()):
                        path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash
                        )
                        document = json.loads(path.read_text(encoding="utf-8"))
                        documents[name] = document
                        self.assertEqual(document["schema_version"], "1.0")
                        self.assertEqual(
                            {row["retrieved_at"] for row in document["evidence"]},
                            {retrieved_at},
                        )
                        for entity_name in ("campus", "project"):
                            entity = document[entity_name]
                            self.assertEqual(entity["roles"], {})
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

                        for evidence in document["evidence"]:
                            content_hash = evidence["content_hash"]
                            byte_count, request_start, http_date, last_modified, url = (
                                CAPTURES[content_hash]
                            )
                            metadata = evidence["metadata"]
                            self.assertEqual(
                                metadata["content_hash_verification"],
                                "fetched_bytes_sha256",
                            )
                            self.assertIn(str(byte_count), metadata["content_hash_scope"])
                            self.assertEqual(
                                metadata.get(
                                    "request_started_at", metadata.get("request_start_utc")
                                ),
                                request_start,
                            )
                            self.assertEqual(metadata["response_http_date"], http_date)
                            self.assertEqual(
                                metadata["http_last_modified_at"], last_modified
                            )
                            self.assertEqual(evidence["source_url"], url)
                            self.assertEqual(metadata["canonical_url"], url)
                            self.assertEqual(
                                metadata.get(
                                    "final_effective_url_as_captured",
                                    metadata.get("effective_url"),
                                ),
                                url,
                            )
                            seen_captures.add(content_hash)

                        CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=retrieved_at
                        )

                self.assertEqual(seen_captures, set(CAPTURES))

                dfw = documents[
                    "curated-official-2026-07-19-cyrusone-dfw7-fort-worth.json"
                ]["evidence"][0]["metadata"]
                self.assertEqual(
                    dfw["capacity_wording_as_reported"],
                    "200 Megawatt Data Center Campus",
                )
                self.assertIn("100MW", dfw["capacity_guardrail"])
                self.assertIn("Neither value", dfw["capacity_guardrail"])
                self.assertIn("no reliable finer physical substage", dfw["status_scope"])

                mil1 = documents[
                    "curated-official-2026-07-19-cyrusone-mil1-segrate.json"
                ]["evidence"][0]["metadata"]
                self.assertIn("three planned 9-megawatt", mil1["capacity_scope"])
                self.assertIn(
                    "future design and operating intent", mil1["renewable_guardrail"]
                )
                self.assertIn(
                    "do not establish completion or operation",
                    mil1["operation_guardrail"],
                )

                yorkville = documents[
                    "curated-official-2026-07-19-cyrusone-yorkville-technology-campus.json"
                ]["evidence"][0]
                self.assertIsNone(yorkville["published_at"])
                self.assertIsNone(yorkville["metadata"]["page_publication_date"])
                self.assertIn(
                    "retrieval date anchors",
                    yorkville["metadata"]["source_date_guardrail"],
                )
                self.assertIn(
                    "site work began in early 2026",
                    yorkville["metadata"]["status_scope"],
                )
                self.assertIn(
                    "seeking approval", yorkville["metadata"]["plan_changes_guardrail"]
                )

                london_document = documents[
                    "curated-official-2026-07-19-colt-london4-hayes.json"
                ]
                london_evidence = {
                    row["key"]: row for row in london_document["evidence"]
                }
                location = london_evidence[
                    "colt-london4-location-page-captured-2026-07-19"
                ]
                timeline = london_evidence[
                    "colt-london4-construction-timeline-captured-2026-07-19"
                ]
                self.assertEqual(location["retrieved_at"], timeline["retrieved_at"])
                self.assertNotEqual(
                    location["metadata"]["request_start_utc"],
                    timeline["metadata"]["request_start_utc"],
                )
                self.assertIn(
                    "stale", location["metadata"]["completion_forecast_guardrail"]
                )
                self.assertIn(
                    "not completion",
                    location["metadata"]["completion_forecast_guardrail"],
                )
                self.assertIn(
                    "Colt House", location["metadata"]["corporate_address_guardrail"]
                )
                self.assertIn(
                    "rejected", location["metadata"]["corporate_address_guardrail"]
                )
                self.assertEqual(location["metadata"]["pue_as_reported"], 1.24)
                self.assertIn("measured", location["metadata"]["pue_guardrail"])
                self.assertIn("do not prove", timeline["metadata"]["stage_guardrail"])
                self.assertNotIn("Colt House", london_document["campus"]["address"])
                self.assertNotIn("Colt House", london_document["project"]["address"])

                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 4), ("project", 4)],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key, lifecycle_observations.status,
                               lifecycle_observations.as_of_date,
                               lifecycle_observations.method
                        FROM lifecycle_observations
                        JOIN entities ON entities.id = lifecycle_observations.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:colt-london-hayes-campus:london4-current-facility-build",
                            "under_construction",
                            "2026-07-19",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:cyrusone-dfw7-fort-worth-campus:current-campus-build",
                            "under_construction",
                            "2026-01-13",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:cyrusone-mil1-segrate-data-center:current-facility-build",
                            "under_construction",
                            "2026-03-25",
                            "authoritative_physical_status_update",
                        ),
                        (
                            "curated:cyrusone-yorkville-technology-campus:current-site-work",
                            "site_preparation",
                            "2026-07-19",
                            "authoritative_physical_status_update",
                        ),
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key, capacity_estimates.metric,
                               capacity_estimates.stage, capacity_estimates.base,
                               capacity_estimates.unit, capacity_estimates.as_of_date,
                               capacity_estimates.method
                        FROM capacity_estimates
                        JOIN entities ON entities.id = capacity_estimates.entity_id
                        ORDER BY entities.stable_key
                        """
                    )],
                    [
                        (
                            "curated:colt-london-hayes-campus:london4-current-facility-build",
                            "critical_it_mw",
                            "planned",
                            31.0,
                            "MW",
                            "2026-07-19",
                            "reported",
                        ),
                        (
                            "curated:cyrusone-mil1-segrate-data-center:current-facility-build",
                            "critical_it_mw",
                            "planned",
                            27.0,
                            "MW",
                            "2026-03-25",
                            "reported",
                        ),
                    ],
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
                    8,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 5
                )
                self.assertEqual(
                    {row[0] for row in connection.execute("SELECT content_hash FROM evidence")},
                    set(CAPTURES),
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric != 'critical_it_mw'"
                    ).fetchone()[0],
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
