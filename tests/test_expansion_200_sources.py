"""Reviewed source facts remain distinct from admission to the published core."""

from __future__ import annotations

import csv
from datetime import date
import hashlib
import importlib
import json
from pathlib import Path
import unittest

from datacenter_atlas import verified_construction_core as core


ROOT = Path(__file__).resolve().parents[1]
curated_v11 = importlib.import_module(f"{core.__package__}.curated_v11")
BASELINE = ROOT / "verified_construction_core/2026-08-20-preview-v0.17"
CAPTURED_AT = "2026-09-08T18:28:04Z"
CAPITALAND = {
    "navi-mumbai-tower-2": {
        "bytes": 6608,
        "sha256": "9b43d9d8ace2f51ba0c15e728c6e166aee9481e88498319bc23150ef02c99161",
        "campus_key": "curated:capitaland-dc-navi-mumbai-campus",
        "project_key": "curated:capitaland-dc-navi-mumbai-campus:tower-2",
        "point": [73.000187, 19.175772],
        "locator_sha256": "07d35973f72892883a63d699f408c3ad128aee8df088134bb5528636e88659ee",
        "locator_bytes": 273539,
    },
    "itph-hyderabad-current-build": {
        "bytes": 6810,
        "sha256": "eaa2341f979a625fb417eea734f733ea8e35efdef322392dbb5a464903025104",
        "campus_key": "curated:capitaland-dc-itph-hyderabad",
        "project_key": "curated:capitaland-dc-itph-hyderabad:current-facility-build",
        "point": [78.38405032, 17.43532415],
        "locator_sha256": "b837112d31778cd0dc5dedf15ae87c94aa67dcfb414cd5463057f6552e0f6f19",
        "locator_bytes": 269416,
    },
}


def source_path(slug: str) -> Path:
    return ROOT / "sources" / f"curated-official-2026-09-08-capitaland-{slug}.json"


class Expansion200SourceTests(unittest.TestCase):
    def test_reviewed_source_bytes_and_schema(self) -> None:
        for slug, expected in CAPITALAND.items():
            with self.subTest(source=slug):
                path = source_path(slug)
                raw = path.read_bytes()
                self.assertEqual(len(raw), expected["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["sha256"])
                parsed = curated_v11._parse_document(path, CAPTURED_AT)
                self.assertEqual(parsed.project.stable_key, expected["project_key"])
                self.assertEqual(parsed.campus.stable_key, expected["campus_key"])
                self.assertEqual(len(parsed.evidence), 2)
                self.assertEqual(len(parsed.lifecycle), 1)
                self.assertEqual(parsed.lifecycle[0].value.value, "under_construction")
                self.assertEqual(parsed.lifecycle[0].as_of_date, "2026-07-29")

    def test_september_location_does_not_refresh_july_construction(self) -> None:
        for slug in CAPITALAND:
            with self.subTest(source=slug):
                payload = json.loads(source_path(slug).read_text())
                status, locator = payload["evidence"]
                lifecycle = payload["lifecycle"][0]
                self.assertEqual(lifecycle["evidence_key"], status["key"])
                self.assertEqual(lifecycle["method"], "authoritative_physical_status_update")
                self.assertEqual(lifecycle["as_of_date"], "2026-07-29")
                age = (date(2026, 8, 20) - date.fromisoformat(lifecycle["as_of_date"])).days
                self.assertEqual(age, 22)
                for entity in (payload["campus"], payload["project"]):
                    self.assertEqual(entity["evidence_key"], locator["key"])
                    self.assertEqual(entity["as_of_date"], "2026-09-08")
                    self.assertEqual(entity["address"], locator["metadata"]["data_address"])
                self.assertEqual(status["published_at"], "2026-07-29")
                self.assertIsNone(locator["published_at"])
                for evidence in (status, locator):
                    self.assertEqual(evidence["retrieved_at"], CAPTURED_AT)
                    self.assertEqual(evidence["metadata"]["capture_finished_at"], CAPTURED_AT)
                self.assertIn("not asserted as an inspection day", status["metadata"]["status_date_scope"])

    def test_capture_provenance_and_source_precision_are_explicit(self) -> None:
        for slug, expected in CAPITALAND.items():
            with self.subTest(source=slug):
                payload = json.loads(source_path(slug).read_text())
                status, locator = payload["evidence"]
                self.assertEqual(status["content_hash"], "5ce78c489021757c8e3f7978039ee3efc256cc58a569625c6f0fc446ea9321af")
                self.assertEqual(status["metadata"]["raw_capture_bytes"], 2016960)
                self.assertEqual(status["metadata"]["reviewed_pages"], [1, 34])
                self.assertEqual(locator["content_hash"], expected["locator_sha256"])
                metadata = locator["metadata"]
                self.assertEqual(metadata["raw_capture_bytes"], expected["locator_bytes"])
                self.assertEqual(metadata["selector"], "#entity-detail-map")
                self.assertEqual(metadata["geometry"], {"type": "Point", "coordinates": expected["point"]})
                self.assertEqual(metadata["geometry_use_scope"], "campus_locator")
                self.assertEqual(metadata["geometry_authority_class"], "official_source")
                self.assertFalse(metadata["official_boundary"])
                self.assertIsNone(metadata["horizontal_uncertainty_metres"])
                self.assertTrue(metadata["horizontal_uncertainty_unknown_reason"])
                for evidence in (status, locator):
                    self.assertFalse(evidence["metadata"]["request_credentials_supplied"])
                    self.assertEqual(evidence["license"], "all-rights-reserved")
                    self.assertTrue(evidence["metadata"]["rights_scope"])

    def test_no_unreviewed_claims_or_published_site_count_change(self) -> None:
        with (BASELINE / "sites.csv").open(newline="", encoding="utf-8") as handle:
            sites = list(csv.DictReader(handle))
        self.assertEqual(len(sites), 100)
        existing = {row["physical_site_stable_key"] for row in sites}
        candidate_keys = set()
        for slug, expected in CAPITALAND.items():
            with self.subTest(source=slug):
                payload = json.loads(source_path(slug).read_text())
                self.assertNotIn(expected["campus_key"], existing)
                candidate_keys.add(expected["campus_key"])
                for entity in (payload["campus"], payload["project"]):
                    self.assertEqual(entity["roles"], {})
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                for collection in ("operating_models", "workloads", "capacities"):
                    self.assertEqual(payload[collection], [])
                self.assertEqual([row["entity"] for row in payload["lifecycle"]], ["project"])
        self.assertEqual(len(candidate_keys), 2)


if __name__ == "__main__":
    unittest.main()
