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
SOURCE = ROOT / "sources/curated-official-2026-07-20-avaio-taurus-brandon.json"
SOURCE_SHA256 = "b5f56dba59f31af34355fe694d9c9a55e3120545d790dced23310d8676964b35"
RETRIEVED_AT = "2026-07-20T05:42:11Z"
CURRENT_EVIDENCE_KEY = "avaio-taurus-current-development-page-captured-2026-07-20"
RELEASE_EVIDENCE_KEY = "avaio-taurus-groundbreaking-release-captured-2026-07-20"
CURRENT_URL = "https://www.avaiodigital.com/developments/brandon-mississippi"
RELEASE_URL = (
    "https://www.avaiodigital.com/updates/avaio-digital-breaks-ground-on-"
    "6-billion-brandon-data-center-campus-leading-mississippi-contractor-"
    "begins-site-work"
)
CAPTURES = {
    "3759697229a486e93438b910c97839b00f274c546ee487dcee8852199bc9e4c2": {
        "bytes": 54_748,
        "headers_bytes": 805,
        "headers_sha256": (
            "25fe3cc8fd416ec07dc38ac8183d106e7785fad13a0a633d6b46176d8061a08f"
        ),
        "writeout_bytes": 99,
        "writeout_sha256": (
            "c3a17b274dabe67e6bba9bc8951e283176e9e63260821dfd5783e9f2283e6444"
        ),
        "curl_size_download": 14_094,
        "last_modified": "2026-07-18T05:38:15Z",
        "source_url": CURRENT_URL,
    },
    "6a079899544c4c251df2c9c2fe959df702f4695ced5acc1a3bf570f3704acf81": {
        "bytes": 35_681,
        "headers_bytes": 780,
        "headers_sha256": (
            "a34c6aa7ac09242a089edfba8470a65b05f88f559c05febc2a65f871172dd9bd"
        ),
        "writeout_bytes": 190,
        "writeout_sha256": (
            "c0df294b5c463eee960a1d3610435412317eb5eb025e1ba9627f5bfbba95c6ab"
        ),
        "curl_size_download": 10_765,
        "last_modified": "2026-07-15T23:07:17Z",
        "source_url": RELEASE_URL,
    },
}


class AvaioTaurusCurrentConstructionTests(unittest.TestCase):
    def test_exact_source_imports_typed_overlapping_power_without_double_counting(self) -> None:
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(
            {evidence["retrieved_at"] for evidence in document["evidence"]},
            {RETRIEVED_AT},
        )
        self.assertEqual(
            [evidence["key"] for evidence in document["evidence"]],
            [CURRENT_EVIDENCE_KEY, RELEASE_EVIDENCE_KEY],
        )

        expected_roles = {
            "developer": ["AVAIO Digital Partners"],
            "operator": ["AVAIO Digital Partners"],
        }
        expected_coordinates = {"latitude": 32.2593, "longitude": -90.0185}
        self.assertEqual(
            document["campus"]["stable_key"],
            "curated:avaio-taurus-brandon-mississippi-campus",
        )
        self.assertEqual(
            document["project"]["stable_key"],
            (
                "curated:avaio-taurus-brandon-mississippi-campus:"
                "phase-one-current-campus-build"
            ),
        )
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["roles"], expected_roles)
            self.assertEqual(entity["coordinates"], expected_coordinates)
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_site_plan")
            self.assertEqual(entity["as_of_date"], "2026-07-20")
            self.assertEqual(
                entity["address"],
                (
                    "East Metropolitan Center, Brandon, Rankin County, Mississippi, "
                    "United States"
                ),
            )
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": CURRENT_EVIDENCE_KEY,
                    "as_of_date": "2026-07-20",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(
            document["workloads"],
            [
                {
                    "entity": "project",
                    "value": "mixed",
                    "evidence_key": RELEASE_EVIDENCE_KEY,
                    "as_of_date": "2025-09-10",
                    "method": "company_disclosure",
                    "confidence": 0.98,
                }
            ],
        )

        capacities = document["capacities"]
        self.assertEqual(
            [
                (
                    row["entity"],
                    row["metric"],
                    row["stage"],
                    row["low"],
                    row["base"],
                    row["high"],
                    row["target_date"],
                )
                for row in capacities
            ],
            [
                ("campus", "grid_connection_mw", "contracted", 116, 116, 116, None),
                ("campus", "grid_connection_mw", "planned", 536, 536, 536, None),
                (
                    "campus",
                    "generation_nameplate_mw",
                    "planned",
                    500,
                    500,
                    500,
                    None,
                ),
            ],
        )
        self.assertEqual({row["evidence_key"] for row in capacities}, {CURRENT_EVIDENCE_KEY})
        self.assertFalse(any(row["base"] in {420, 1036} for row in capacities))
        self.assertIn("contained", capacities[0]["notes"])
        self.assertIn("contains", capacities[1]["notes"])
        self.assertIn("creates no additional row", capacities[2]["notes"])

        by_key = {evidence["key"]: evidence for evidence in document["evidence"]}
        current_metadata = by_key[CURRENT_EVIDENCE_KEY]["metadata"]
        release_metadata = by_key[RELEASE_EVIDENCE_KEY]["metadata"]
        self.assertEqual(current_metadata["initial_grid_power_as_reported_mw"], 116)
        self.assertEqual(current_metadata["total_grid_power_as_reported_mw"], 536)
        self.assertEqual(current_metadata["additional_grid_power_as_reported_mw"], 420)
        self.assertEqual(current_metadata["onsite_thermal_generation_as_reported_mw"], 500)
        self.assertEqual(current_metadata["total_baseload_power_as_reported_mw"], 1036)
        self.assertIn("creates no third capacity row", current_metadata["aggregate_power_guardrail"])
        self.assertIn("swaps or mislabels", current_metadata["structured_data_conflict_guardrail"])
        self.assertIn("not additive current load", current_metadata["capacity_overlap_guardrail"])
        self.assertIn("No source value", current_metadata["energy_guardrail"])
        self.assertIn("mixed intended", release_metadata["workload_scope"])
        self.assertIn("no normalized", release_metadata["operating_model_guardrail"])
        self.assertEqual(release_metadata["first_phase_power_as_reported_mw"], 116)
        self.assertEqual(
            release_metadata["first_phase_floor_area_as_reported"],
            "over 600,000 square feet of data center buildings",
        )

        seen_captures = {}
        for evidence in document["evidence"]:
            expected = CAPTURES[evidence["content_hash"]]
            metadata = evidence["metadata"]
            self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
            self.assertIn(str(expected["bytes"]), metadata["content_hash_scope"])
            self.assertIn(str(expected["headers_bytes"]), metadata["capture_headers_scope"])
            self.assertEqual(metadata["capture_headers_sha256"], expected["headers_sha256"])
            self.assertIn(
                str(expected["writeout_bytes"]), metadata["capture_curl_writeout_scope"]
            )
            self.assertEqual(
                metadata["capture_curl_writeout_sha256"], expected["writeout_sha256"]
            )
            self.assertEqual(
                metadata["curl_size_download_bytes_as_received"],
                expected["curl_size_download"],
            )
            self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
            self.assertEqual(metadata["http_last_modified_at"], expected["last_modified"])
            self.assertEqual(evidence["source_url"], expected["source_url"])
            self.assertEqual(metadata["requested_url"], expected["source_url"])
            self.assertEqual(metadata["effective_url"], expected["source_url"])
            self.assertEqual(metadata["canonical_url"], expected["source_url"])
            self.assertEqual(metadata["redirect_count"], 0)
            self.assertEqual(metadata["content_encoding_as_received"], "gzip")
            seen_captures[evidence["content_hash"]] = expected
        self.assertEqual(seen_captures, CAPTURES)

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
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        SOURCE,
                        retrieved_at=RETRIEVED_AT,
                    )
                self.assertEqual(result.entities_created, 2)
                self.assertEqual(result.evidence_created, 2)
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 1), ("project", 1)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   lifecycle_observations.status,
                                   lifecycle_observations.as_of_date,
                                   lifecycle_observations.method
                            FROM lifecycle_observations
                            JOIN entities ON entities.id = lifecycle_observations.entity_id
                            """
                        )
                    ],
                    [
                        (
                            (
                                "curated:avaio-taurus-brandon-mississippi-campus:"
                                "phase-one-current-campus-build"
                            ),
                            "under_construction",
                            "2026-07-20",
                            "authoritative_physical_status_update",
                        )
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   workload_observations.workload,
                                   workload_observations.as_of_date
                            FROM workload_observations
                            JOIN entities ON entities.id = workload_observations.entity_id
                            """
                        )
                    ],
                    [
                        (
                            (
                                "curated:avaio-taurus-brandon-mississippi-campus:"
                                "phase-one-current-campus-build"
                            ),
                            "mixed",
                            "2025-09-10",
                        )
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   capacity_estimates.metric,
                                   capacity_estimates.stage,
                                   capacity_estimates.low,
                                   capacity_estimates.base,
                                   capacity_estimates.high,
                                   capacity_estimates.as_of_date,
                                   capacity_estimates.target_date
                            FROM capacity_estimates
                            JOIN entities ON entities.id = capacity_estimates.entity_id
                            ORDER BY capacity_estimates.metric, capacity_estimates.stage
                            """
                        )
                    ],
                    [
                        (
                            "curated:avaio-taurus-brandon-mississippi-campus",
                            "generation_nameplate_mw",
                            "planned",
                            500.0,
                            500.0,
                            500.0,
                            "2026-07-20",
                            None,
                        ),
                        (
                            "curated:avaio-taurus-brandon-mississippi-campus",
                            "grid_connection_mw",
                            "contracted",
                            116.0,
                            116.0,
                            116.0,
                            "2026-07-20",
                            None,
                        ),
                        (
                            "curated:avaio-taurus-brandon-mississippi-campus",
                            "grid_connection_mw",
                            "planned",
                            536.0,
                            536.0,
                            536.0,
                            "2026-07-20",
                            None,
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates WHERE base IN (420, 1036)"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   entity_snapshots.latitude,
                                   entity_snapshots.longitude,
                                   entity_snapshots.method,
                                   entity_snapshots.geometry_json
                            FROM entity_snapshots
                            JOIN entities ON entities.id = entity_snapshots.entity_id
                            ORDER BY entities.stable_key
                            """
                        )
                    ],
                    [
                        (
                            "curated:avaio-taurus-brandon-mississippi-campus",
                            32.2593,
                            -90.0185,
                            "authoritative_site_plan",
                            '{"coordinates":[-90.0185,32.2593],"type":"Point"}',
                        ),
                        (
                            (
                                "curated:avaio-taurus-brandon-mississippi-campus:"
                                "phase-one-current-campus-build"
                            ),
                            32.2593,
                            -90.0185,
                            "authoritative_site_plan",
                            '{"coordinates":[-90.0185,32.2593],"type":"Point"}',
                        ),
                    ],
                )
                self.assertEqual(
                    {
                        row["stable_key"]: {
                            key: value
                            for key, value in json.loads(row["tags_json"]).items()
                            if key.startswith("role:")
                        }
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key, entity_snapshots.tags_json
                            FROM entity_snapshots
                            JOIN entities ON entities.id = entity_snapshots.entity_id
                            """
                        )
                    },
                    {
                        "curated:avaio-taurus-brandon-mississippi-campus": {
                            "role:developer": "AVAIO Digital Partners",
                            "role:operator": "AVAIO Digital Partners",
                        },
                        (
                            "curated:avaio-taurus-brandon-mississippi-campus:"
                            "phase-one-current-campus-build"
                        ): {
                            "role:developer": "AVAIO Digital Partners",
                            "role:operator": "AVAIO Digital Partners",
                        },
                    },
                )
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 2)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
