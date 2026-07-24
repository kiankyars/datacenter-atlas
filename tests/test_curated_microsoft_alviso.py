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
SOURCE = ROOT / "sources/curated-official-2026-07-20-microsoft-alviso-phase-2.json"
SOURCE_SHA256 = "7dcd5b73ffe64319c234c16a1db94e0e883096663396eae55a071f626b6bca3a"
RETRIEVED_AT = "2026-07-20T05:47:18Z"
HITT_KEY = "hitt-microsoft-alviso-groundbreaking-2026-06-10-captured-2026-07-20"
MICROSOFT_KEY = "microsoft-local-alviso-construction-update-captured-2026-07-20"
CAPTURES = {
    HITT_KEY: {
        "body_bytes": 306_207,
        "body_sha256": "0b3e2fbd4eedc81f3a6ff29993c2e9c50b19215ed8e5d7543c7cebf1beaef14b",
        "header_bytes": 755,
        "header_sha256": "e022d66cad7fe171fb3412f126d3e2470993a7eba630f0dc209087551854a917",
        "writeout_bytes": 115,
        "writeout_sha256": "af620ac23382514b0ae11629dca9500533fef3d429dd3d28ff2703c624a61f20",
        "http_date": "2026-07-20T05:47:17Z",
    },
    MICROSOFT_KEY: {
        "body_bytes": 194_330,
        "body_sha256": "59374c7f87f679f1cc9727388f2bc76834ef3aa887f7cc8493111ea9af5de7a7",
        "header_bytes": 1_058,
        "header_sha256": "ce685f5b5a4fbbf5b651a8505433009c181bfa70de760cc4340b37ec5f6c7011",
        "writeout_bytes": 109,
        "writeout_sha256": "f5c79af23a274a519d0e903c2b78946367f9b361265268fc5a33fb79d3ae829c",
        "http_date": "2026-07-20T05:47:18Z",
    },
}


class MicrosoftAlvisoCurrentConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_exact_source_and_capture_provenance_are_pinned(self) -> None:
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        self.assertEqual(self.document["schema_version"], "1.0")
        evidence = {item["key"]: item for item in self.document["evidence"]}
        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(item["retrieved_at"], RETRIEVED_AT)
                self.assertEqual(item["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f'{expected["body_bytes"]}-byte',
                    metadata["content_hash_scope"],
                )
                self.assertIn(
                    f'{expected["header_bytes"]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["header_sha256"]
                )
                self.assertIn(
                    f'{expected["writeout_bytes"]}-byte',
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["redirect_count"], 0)

    def test_one_phase_project_preserves_roles_status_and_48_mw_scope(self) -> None:
        expected_roles = {
            "developer": ["Microsoft"],
            "contractor": ["HITT Contracting Inc."],
        }
        self.assertEqual(
            self.document["campus"]["stable_key"],
            "curated:microsoft-alviso-san-jose-datacenter-campus",
        )
        self.assertEqual(
            self.document["project"]["stable_key"],
            "curated:microsoft-alviso-san-jose-datacenter-campus:phase-2-greenfield-development",
        )
        for entity in (self.document["campus"], self.document["project"]):
            self.assertEqual(entity["roles"], expected_roles)
            self.assertEqual(
                entity["address"], "Alviso, San Jose, California, United States"
            )
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(
            self.document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": HITT_KEY,
                    "as_of_date": "2026-06-10",
                    "method": "authoritative_construction_start",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(self.document["operating_models"], [])
        self.assertEqual(self.document["workloads"], [])
        self.assertEqual(len(self.document["capacities"]), 1)
        capacity = self.document["capacities"][0]
        self.assertEqual(
            (
                capacity["entity"],
                capacity["metric"],
                capacity["stage"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
                capacity["target_date"],
            ),
            ("project", "critical_it_mw", "planned", 48, 48, 48, None),
        )

    def test_forecasts_and_classification_do_not_leak_into_claims(self) -> None:
        evidence = {item["key"]: item for item in self.document["evidence"]}
        hitt = evidence[HITT_KEY]["metadata"]
        microsoft = evidence[MICROSOFT_KEY]["metadata"]
        self.assertIn("not converted", hitt["forecast_guardrail"])
        self.assertIn("does not establish", hitt["classification_guardrail"])
        self.assertIn("no normalized operating model", hitt["operating_model_guardrail"])
        self.assertIn("not evidence", microsoft["forecast_guardrail"])
        self.assertIn("sole source", microsoft["capacity_guardrail"])
        self.assertNotIn("operator", self.document["campus"]["roles"])
        self.assertNotIn("owner", self.document["campus"]["roles"])

    def test_offline_import_is_exact_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                error = AssertionError("curated import attempted network access")
                with patch.object(socket, "socket", side_effect=error), patch.object(
                    socket, "create_connection", side_effect=error
                ), patch.object(socket, "getaddrinfo", side_effect=error):
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        SOURCE,
                        retrieved_at=RETRIEVED_AT,
                    )
                self.assertEqual(result.entities_created, 2)
                self.assertEqual(result.evidence_created, 2)
                self.assertEqual(validate_database(connection), [])
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
                            SELECT entities.stable_key, status, as_of_date, method
                            FROM lifecycle_observations
                            JOIN entities ON entities.id = lifecycle_observations.entity_id
                            """
                        )
                    ],
                    [
                        (
                            "curated:microsoft-alviso-san-jose-datacenter-campus:phase-2-greenfield-development",
                            "under_construction",
                            "2026-06-10",
                            "authoritative_construction_start",
                        )
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key, metric, stage, low, base, high,
                                   target_date
                            FROM capacity_estimates
                            JOIN entities ON entities.id = capacity_estimates.entity_id
                            """
                        )
                    ],
                    [
                        (
                            "curated:microsoft-alviso-san-jose-datacenter-campus:phase-2-greenfield-development",
                            "critical_it_mw",
                            "planned",
                            48.0,
                            48.0,
                            48.0,
                            None,
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
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                role_tags = {
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
                }
                self.assertEqual(
                    set(role_tags),
                    {
                        "curated:microsoft-alviso-san-jose-datacenter-campus",
                        "curated:microsoft-alviso-san-jose-datacenter-campus:phase-2-greenfield-development",
                    },
                )
                for tags in role_tags.values():
                    self.assertEqual(
                        tags,
                        {
                            "role:contractor": "HITT Contracting Inc.",
                            "role:developer": "Microsoft",
                        },
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
