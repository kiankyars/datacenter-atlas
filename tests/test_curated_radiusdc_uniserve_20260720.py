from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RADIUS_SOURCE = "curated-official-2026-07-20-radiusdc-nashville-i.json"
UNISERVE_SOURCE = (
    "curated-official-2026-07-20-uniserve-369-terminal-vancouver.json"
)
SOURCE_PINS = {
    RADIUS_SOURCE: (
        "2026-07-20T16:57:56Z",
        20_662,
        "e402d328e2e9c7217d5692cbf7cf6394ae4875eda9ee6a7cceac1b5f568be7d8",
    ),
    UNISERVE_SOURCE: (
        "2026-07-20T16:56:48Z",
        15_523,
        "fcbaef2079eb7058222a44390590ae80abe31faae184e7faf30c8306469381de",
    ),
}
RADIUS_PROJECT = "curated:radiusdc-nashville-i-trinity-hills-campus:nashville-i"
UNISERVE_PROJECT = (
    "curated:uniserve-369-terminal-avenue-vancouver-data-centre:"
    "two-phase-buildout"
)
CAPTURE_PINS = {
    "radiusdc-nashville-i-groundbreaking-2025-09-04-captured-2026-07-20": (
        16_148,
        "a8d433383ff37a87817050a3c19e17a7fd29499ec64eb7e77c181d237add3fef",
        1_315,
        "ef457906c4f25191be971d69bb11043a130a09c79d387f00fc95fe2be63abad9",
        9_756,
        "9040b8a046bc81c3ec7e10d030ebe16b32fa3582d41f00b59480cf08643cab6c",
    ),
    "radiusdc-nashville-i-current-construction-2026-01-12-captured-2026-07-20": (
        17_138,
        "79b80fd2f4e332e852cb4fcdbd450767a5e1d127f1c2fa4ad1aba14fb0ef6759",
        1_302,
        "98650b7b03d85e3de9d731a07eb6d6626f3d2ea73c120c8563cca62fb5cecfa9",
        9_830,
        "e208bbe3f8b5f3ff17c73ccb0e702688deb619dd84bff935aff63b3291afe0e6",
    ),
    "radiusdc-nashville-i-current-location-captured-2026-07-20": (
        27_043,
        "46289306ab92de268a0f8014d69dcf1d93659765122e4a2eb834b1e8ccb41530",
        1_291,
        "5d7b58247695c01db4b1e21c1f6efc7a19d6e558e7fc2fddd345689b80ededce",
        9_511,
        "a5c4cec581db7d49a710c3819a86eef661106bbb7bf3ad63908c43f54ea3dc7e",
    ),
    "uniserve-369-terminal-phase1-construction-2026-03-04-captured-2026-07-20": (
        110_003,
        "cf0894e67ae636c382daf1bfd5e571165502e8d04b9a34588e3ef6bf9ab2817d",
        188,
        "c4ac47fcf4d273663842c5372861714e42a8d4737bfc071495b2ee3db6d7e3b0",
        17_272,
        "4bc509cd386b886c99c1dd9079a57bb3347cba3c85340301d6f8d27d4bf4b6f6",
    ),
    "uniserve-369-terminal-lease-2025-09-15-captured-2026-07-20": (
        112_185,
        "62347d123e6753d7db3e9e4fbbb7d0a8b6e0301912b9a3a2367a6062f790b612",
        188,
        "214c98c176da918cc1e3e13af72c165fd1e407914cafcc78caf9b206ff8f6afa",
        17_243,
        "1004abd54971dd298a109de6537bd072e800dfbd8a2a7835b925249f72fa14ae",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RadiusDcAndUniserveCuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        blocked = AssertionError("RadiusDC/Uniserve import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=blocked))
        return stack

    def _state(
        self,
        order: tuple[str, ...],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[object, ...], ...], ...]:
        with tempfile.TemporaryDirectory(prefix="radius-uniserve-test-") as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=SOURCE_PINS[name][0],
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, metric, stage, base, unit "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, tags_json, latitude, longitude, "
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id ORDER BY 1",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_sources_are_canonical_hash_pinned_and_capture_bound(self) -> None:
        documents = {}
        for name, (retrieved_at, size, digest) in SOURCE_PINS.items():
            with self.subTest(name=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual((path.stat().st_size, _sha256(path)), (size, digest))
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                documents[name] = document
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertTrue(
                    all(item["retrieved_at"] == retrieved_at for item in document["evidence"])
                )

        evidence = {
            item["key"]: item
            for document in documents.values()
            for item in document["evidence"]
        }
        self.assertEqual(set(evidence), set(CAPTURE_PINS))
        for key, (body_size, body_hash, head_size, head_hash, curl_size, curl_hash) in CAPTURE_PINS.items():
            with self.subTest(key=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertIn(f"exact {body_size}-byte", metadata["content_hash_scope"])
                self.assertEqual(item["content_hash"], body_hash)
                self.assertIn(f"exact {head_size}-byte", metadata["capture_headers_scope"])
                self.assertEqual(metadata["capture_headers_sha256"], head_hash)
                self.assertIn(f"exact {curl_size}-byte", metadata["capture_curl_writeout_scope"])
                self.assertEqual(metadata["capture_curl_writeout_sha256"], curl_hash)
                self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(metadata["redirect_count"], 0)

    def test_radius_nashville_status_capacity_and_date_conflicts_are_conservative(self) -> None:
        document = self._load(RADIUS_SOURCE)
        self.assertEqual(len(document["evidence"]), 3)
        self.assertEqual(
            document["project"]["roles"],
            {
                "developer": ["RadiusDC"],
                "operator": ["RadiusDC"],
                "utility": [
                    "Nashville Electric Service",
                    "Tennessee Valley Authority",
                ],
            },
        )
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": (
                        "radiusdc-nashville-i-current-construction-2026-01-12-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-01-12",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["metric"],
                capacity["stage"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
            ),
            ("critical_it_mw", "planned", 12, 12, 12),
        )
        self.assertEqual(
            [(row["entity"], row["value"]) for row in document["operating_models"]],
            [("project", "colocation")],
        )
        evidence = {item["key"]: item for item in document["evidence"]}
        ground = evidence[
            "radiusdc-nashville-i-groundbreaking-2025-09-04-captured-2026-07-20"
        ]
        self.assertEqual(ground["published_at"], "2025-09-04T00:00:00Z")
        self.assertEqual(
            ground["metadata"]["structured_date_published"],
            "2026-06-02T19:50:55.278Z",
        )
        self.assertIn("website migration", ground["metadata"]["publication_date_conflict_guardrail"])
        current = evidence["radiusdc-nashville-i-current-location-captured-2026-07-20"]
        self.assertEqual(current["metadata"]["reported_building_utility_capacity_mw"], 20)
        self.assertIn("remains untyped metadata", current["metadata"]["utility_capacity_guardrail"])
        self.assertIn("does not explicitly say", current["metadata"]["current_page_status_guardrail"])
        self.assertIn("no PUE", current["metadata"]["energy_guardrail"])

    def test_uniserve_status_and_power_dimensions_are_not_conflated(self) -> None:
        document = self._load(UNISERVE_SOURCE)
        self.assertEqual(len(document["evidence"]), 2)
        self.assertEqual(
            document["project"]["roles"],
            {
                "developer": ["Uniserve Communications Corporation"],
                "operator": ["Uniserve Communications Corporation"],
                "landlord": ["369 Terminal Holdings Ltd."],
                "utility": ["BC Hydro"],
            },
        )
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": (
                        "uniserve-369-terminal-phase1-construction-2026-03-04-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-03-04",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["metric"],
                capacity["stage"],
                capacity["low"],
                capacity["base"],
                capacity["high"],
            ),
            ("grid_connection_mw", "planned", 3, 3, 3),
        )
        self.assertIn("No executed power agreement", capacity["notes"])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        evidence = {item["key"]: item for item in document["evidence"]}
        update = evidence[
            "uniserve-369-terminal-phase1-construction-2026-03-04-"
            "captured-2026-07-20"
        ]
        self.assertEqual(update["published_at"], "2026-03-04T00:00:00Z")
        self.assertIn("earlier generic", update["metadata"]["publication_date_conflict_guardrail"])
        lease = evidence[
            "uniserve-369-terminal-lease-2025-09-15-captured-2026-07-20"
        ]
        self.assertEqual(lease["metadata"]["reported_initial_untyped_mw"], 2)
        self.assertIn("remains metadata", lease["metadata"]["initial_capacity_guardrail"])
        self.assertIn("not itself a physical milestone", lease["metadata"]["construction_wording_guardrail"])
        self.assertIn("no PUE", lease["metadata"]["energy_guardrail"])

    def test_offline_import_is_order_independent_idempotent_and_ungeocoded(self) -> None:
        first = self._state((RADIUS_SOURCE, UNISERVE_SOURCE))
        reverse = self._state((UNISERVE_SOURCE, RADIUS_SOURCE))
        repeated = self._state((RADIUS_SOURCE, UNISERVE_SOURCE), repetitions=2)
        self.assertEqual(first, reverse)
        self.assertEqual(first, repeated)

        entities, evidence, lifecycle, capacities, models, snapshots = first
        self.assertEqual(len(entities), 4)
        self.assertEqual(len(evidence), 5)
        self.assertEqual(
            lifecycle,
            (
                (
                    RADIUS_PROJECT,
                    "under_construction",
                    "2026-01-12",
                    "authoritative_physical_status_update",
                ),
                (
                    UNISERVE_PROJECT,
                    "under_construction",
                    "2026-03-04",
                    "authoritative_physical_status_update",
                ),
            ),
        )
        self.assertEqual(
            capacities,
            (
                (RADIUS_PROJECT, "critical_it_mw", "planned", 12.0, "MW"),
                (UNISERVE_PROJECT, "grid_connection_mw", "planned", 3.0, "MW"),
            ),
        )
        self.assertEqual(models, ((RADIUS_PROJECT, "colocation"),))
        for stable_key, tags_json, latitude, longitude, geometry in snapshots:
            self.assertIsNone(latitude, stable_key)
            self.assertIsNone(longitude, stable_key)
            self.assertIsNone(geometry, stable_key)
            tags = json.loads(tags_json)
            self.assertNotIn("unique_site_count", tags)


if __name__ == "__main__":
    unittest.main()
