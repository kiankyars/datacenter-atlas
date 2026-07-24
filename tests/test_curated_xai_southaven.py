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
SOURCE = ROOT / "sources/curated-official-2026-07-20-xai-macrohardrr-southaven.json"
SOURCE_SHA256 = "deff762efb7c40a89e783f779a932bfc71843ce2b216371685eb980999714ec2"
RETRIEVED_AT = "2026-07-20T05:31:15Z"
CAPTURES = {
    "d3fe8b61b6eeaa81fdab902a417b05b8399d9da3093fffdb183b5f3f97060c70": {
        "bytes": 176_469,
        "response_http_date": "2026-07-20T05:30:52Z",
        "source_url": (
            "https://mississippi.org/news/tech-leader-xai-investing-more-than-"
            "20-billion-in-southaven/"
        ),
    },
    "4c976b1d1c366cbc2ecaf35df67e2bd8bb9c7c0fdb90ac26a73caf81d8aaf8fb": {
        "bytes": 130_755,
        "response_http_date": "2026-07-20T05:31:15Z",
        "source_url": "https://www.southaven.org/Blog.aspx?IID=227",
    },
}


class XaiSouthavenCurrentConstructionTests(unittest.TestCase):
    def test_exact_source_imports_one_role_typed_ai_retrofit_without_capacity(self) -> None:
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(
            {evidence["retrieved_at"] for evidence in document["evidence"]},
            {RETRIEVED_AT},
        )
        self.assertEqual(
            document["campus"]["stable_key"],
            "curated:xai-macrohardrr-southaven-data-center",
        )
        self.assertEqual(
            document["project"]["stable_key"],
            "curated:xai-macrohardrr-southaven-data-center:building-retrofit",
        )
        expected_roles = {
            "owner": ["xAI"],
            "developer": ["xAI"],
            "operator": ["xAI"],
        }
        self.assertEqual(document["campus"]["roles"], expected_roles)
        self.assertEqual(document["project"]["roles"], expected_roles)
        for entity in (document["campus"], document["project"]):
            self.assertEqual(
                entity["address"],
                "2400 Stateline Road, Southaven, Mississippi, United States",
            )
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": "mda-xai-macrohardrr-southaven-captured-2026-07-20",
                    "as_of_date": "2026-01-08",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(
            [(row["entity"], row["value"]) for row in document["operating_models"]],
            [("campus", "enterprise_private")],
        )
        self.assertEqual(
            [(row["entity"], row["value"]) for row in document["workloads"]],
            [("project", "ai_specialized_unspecified")],
        )
        self.assertEqual(document["capacities"], [])

        by_key = {evidence["key"]: evidence for evidence in document["evidence"]}
        mda = by_key["mda-xai-macrohardrr-southaven-captured-2026-07-20"]
        city = by_key["southaven-xai-expansion-captured-2026-07-20"]
        self.assertIn("present-progressive retrofit", mda["metadata"]["status_scope"])
        self.assertIn("forward-looking", mda["metadata"]["operations_forecast_guardrail"])
        self.assertIn("No capacity row", mda["metadata"]["capacity_guardrail"])
        self.assertIn("not merged", mda["metadata"]["nearby_power_plant_guardrail"])
        self.assertEqual(city["metadata"]["address_as_reported"], "2400 Stateline Road")
        self.assertEqual(city["metadata"]["floor_area_as_reported_square_feet"], 810_000)
        self.assertIn("GB300", city["metadata"]["workload_scope"])
        self.assertIn("Only the 2400", city["metadata"]["portfolio_guardrail"])
        self.assertIn("creates no generation", city["metadata"]["temporary_power_guardrail"])

        seen = {}
        for evidence in document["evidence"]:
            expected = CAPTURES[evidence["content_hash"]]
            metadata = evidence["metadata"]
            self.assertEqual(
                metadata["content_hash_verification"], "fetched_bytes_sha256"
            )
            self.assertIn(str(expected["bytes"]), metadata["content_hash_scope"])
            self.assertEqual(
                metadata["response_http_date"], expected["response_http_date"]
            )
            self.assertEqual(evidence["source_url"], expected["source_url"])
            self.assertEqual(metadata["canonical_url"], expected["source_url"])
            seen[evidence["content_hash"]] = expected
        self.assertEqual(seen, CAPTURES)

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
                    [tuple(row) for row in connection.execute(
                        "SELECT kind, COUNT(*) FROM entities GROUP BY kind ORDER BY kind"
                    )],
                    [("campus", 1), ("project", 1)],
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
                        """
                    )],
                    [
                        (
                            "curated:xai-macrohardrr-southaven-data-center:building-retrofit",
                            "under_construction",
                            "2026-01-08",
                            "authoritative_physical_status_update",
                        )
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               operating_model_observations.operating_model,
                               operating_model_observations.as_of_date
                        FROM operating_model_observations
                        JOIN entities ON entities.id = operating_model_observations.entity_id
                        """
                    )],
                    [
                        (
                            "curated:xai-macrohardrr-southaven-data-center",
                            "enterprise_private",
                            "2026-01-08",
                        )
                    ],
                )
                self.assertEqual(
                    [tuple(row) for row in connection.execute(
                        """
                        SELECT entities.stable_key,
                               workload_observations.workload,
                               workload_observations.as_of_date
                        FROM workload_observations
                        JOIN entities ON entities.id = workload_observations.entity_id
                        """
                    )],
                    [
                        (
                            "curated:xai-macrohardrr-southaven-data-center:building-retrofit",
                            "ai_specialized_unspecified",
                            "2026-01-07",
                        )
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
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
                        "curated:xai-macrohardrr-southaven-data-center": {
                            "role:developer": "xAI",
                            "role:operator": "xAI",
                            "role:owner": "xAI",
                        },
                        "curated:xai-macrohardrr-southaven-data-center:building-retrofit": {
                            "role:developer": "xAI",
                            "role:operator": "xAI",
                            "role:owner": "xAI",
                        },
                    },
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
