from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any, Iterable
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T06:04:09Z"
AS01_SOURCE = "curated-official-2026-07-20-edgecore-as01-sterling.json"
AS02_SOURCE = "curated-official-2026-07-20-edgecore-as02-sterling.json"
SOURCES = (AS01_SOURCE, AS02_SOURCE)

AS01_POST_KEY = (
    "edgecore-as01-topping-out-linkedin-2025-09-24-captured-2026-07-20"
)
AS02_POST_KEY = (
    "edgecore-as02-topping-out-linkedin-2026-07-01-captured-2026-07-20"
)
LOCATION_KEY = "edgecore-ashburn-location-page-current-captured-2026-07-20"
RELEASE_KEY = (
    "edgecore-as01-as02-construction-financing-release-2026-04-21-"
    "captured-2026-07-20"
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    AS01_SOURCE: {
        "sha256": "dd9b10b617ece6c59d5e50c3fc01ba43590656b33d44688d84d7f90a3c53efca",
        "campus_key": "curated:edgecore-as01-sterling-virginia-campus",
        "project_key": (
            "curated:edgecore-as01-sterling-virginia-campus:as01-data-center"
        ),
        "project_name": "EdgeCore AS01 Data Center",
        "post_key": AS01_POST_KEY,
        "status_date": "2025-09-24",
    },
    AS02_SOURCE: {
        "sha256": "ffbb3fe0340194e909fd443478bca2fe79009d686784e78847d7a41c441329f9",
        "campus_key": "curated:edgecore-as02-sterling-virginia-campus",
        "project_key": (
            "curated:edgecore-as02-sterling-virginia-campus:as02-data-center"
        ),
        "project_name": "EdgeCore AS02 Data Center",
        "post_key": AS02_POST_KEY,
        "status_date": "2026-07-01",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    AS01_POST_KEY: {
        "body_bytes": 181_010,
        "body_sha256": (
            "9cf5afff3f2347dda05265926cd320a09cc10a1c079879534c2555508e0c4942"
        ),
        "header_bytes": 5_347,
        "header_sha256": (
            "296931f57827459e92e52b6967a938e58e96e8d28139529cff42fa5103696636"
        ),
        "writeout_bytes": 17_813,
        "writeout_sha256": (
            "81f67b921b00fe7f2eac8b7548ff88af8c16021b3b6c21be1ed9603fcf009b12"
        ),
        "download_bytes": 21_308,
        "http_date": "2026-07-20T06:04:08Z",
        "url": (
            "https://www.linkedin.com/posts/edgecore-digital-infrastructure_"
            "yesterday-was-an-exciting-day-in-ashburn-activity-"
            "7376652714761621504-8OKG"
        ),
        "appearances": 1,
    },
    AS02_POST_KEY: {
        "body_bytes": 112_475,
        "body_sha256": (
            "e2e7be3885f8fb982770cc0655622db43906982977de0f4af519f1495f9407cf"
        ),
        "header_bytes": 5_348,
        "header_sha256": (
            "cbe46d6925b99e740df46e82f59c88ae5fbf943f54d95dec38b7408eb143fc91"
        ),
        "writeout_bytes": 17_817,
        "writeout_sha256": (
            "aee6ab736c30ead9f2dd6116910e91200d4f12435da988be9b3b365dd212b05d"
        ),
        "download_bytes": 17_315,
        "http_date": "2026-07-20T06:02:09Z",
        "url": (
            "https://www.linkedin.com/posts/edgecore-digital-infrastructure_"
            "yesterday-edgecore-celebrated-the-topping-activity-"
            "7478135212778938368-t979"
        ),
        "appearances": 1,
    },
    LOCATION_KEY: {
        "body_bytes": 44_088,
        "body_sha256": (
            "e02d1a93ee961d6f0961fc924575b33781e1c026f87f18035f964b4bd02ca160"
        ),
        "header_bytes": 1_360,
        "header_sha256": (
            "898939c77a80107d8658635f468cbac0a862c48ba277703dcc8a77fdc399c947"
        ),
        "writeout_bytes": 9_421,
        "writeout_sha256": (
            "fd811d98f3a0fc69f04f9e5c60c75c37ef6d32334113a8d2dd50bd0eaf3bf607"
        ),
        "download_bytes": 11_078,
        "http_date": "2026-07-20T06:04:09Z",
        "url": "https://edgecore.com/locations/ashburn-data-center",
        "appearances": 2,
    },
    RELEASE_KEY: {
        "body_bytes": 34_857,
        "body_sha256": (
            "fa444e9d32365973e06890358e89b07d495d41761a9245aefeb4cfe029c4f6e6"
        ),
        "header_bytes": 1_335,
        "header_sha256": (
            "2e36585b8c9b2310c10d4c5a84d4c6424997b22635119533f67f2b445aa3c5f0"
        ),
        "writeout_bytes": 9_978,
        "writeout_sha256": (
            "746f8618384649478542a10c802dfc842aa49f21871dd011e5cb2afcc63bb3b5"
        ),
        "download_bytes": 10_546,
        "http_date": "2026-07-20T06:02:09Z",
        "url": (
            "https://edgecore.com/resources/press-releases/edgecore-digital-"
            "infrastructure-secures-1-5-billion-of-construction-financing-for-"
            "two-fully-leased-hyperscale-data-centers-in-northern-virginia"
        ),
        "appearances": 2,
    },
}


class EdgeCoreAshburnCuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("curated source import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _state(
        self,
        order: Iterable[str],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=RETRIEVED_AT,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, base, target_date "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_source_files_are_canonical_byte_pinned_and_shared_evidence_is_exact(self) -> None:
        documents = {name: self._load(name) for name in SOURCES}
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = documents[name]
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(len(document["evidence"]), 3)

        for key in (LOCATION_KEY, RELEASE_KEY):
            first = next(
                item for item in documents[AS01_SOURCE]["evidence"] if item["key"] == key
            )
            second = next(
                item for item in documents[AS02_SOURCE]["evidence"] if item["key"] == key
            )
            self.assertEqual(first, second)

    def test_capture_provenance_is_exact_and_retrieval_is_guarded(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        appearances: dict[str, int] = defaultdict(int)
        for name in SOURCES:
            for item in self._load(name)["evidence"]:
                previous = evidence.setdefault(item["key"], item)
                self.assertEqual(previous, item)
                appearances[item["key"]] += 1

        self.assertEqual(set(evidence), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                self.assertEqual(appearances[key], expected["appearances"])
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
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download_bytes"],
                )
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["canonical_url"], expected["url"])
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("--retry 0", metadata["retrieval_method"])
                self.assertIn(
                    "supplied no Authorization",
                    metadata["request_credentials_guardrail"],
                )
                self.assertIn(
                    "not redistributed", metadata["capture_artifact_guardrail"]
                )
                self.assertIn("satellite imagery", metadata["imagery_guardrail"])

    def test_two_distinct_sites_have_only_source_supported_status_and_developer(self) -> None:
        stable_keys: set[str] = set()
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                document = self._load(name)
                campus = document["campus"]
                project = document["project"]
                self.assertEqual(campus["stable_key"], expected["campus_key"])
                self.assertEqual(project["stable_key"], expected["project_key"])
                self.assertEqual(project["name"], expected["project_name"])
                stable_keys.update((campus["stable_key"], project["stable_key"]))
                for entity in (campus, project):
                    self.assertEqual(entity["country"], "United States")
                    self.assertEqual(
                        entity["address"], "Sterling, Virginia, United States"
                    )
                    self.assertEqual(
                        entity["roles"],
                        {"developer": ["EdgeCore Digital Infrastructure"]},
                    )
                    self.assertEqual(entity["evidence_key"], RELEASE_KEY)
                    self.assertEqual(entity["as_of_date"], "2026-04-21")
                    self.assertEqual(entity["method"], "authoritative_locality")
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                self.assertEqual(
                    document["lifecycle"],
                    [
                        {
                            "entity": "project",
                            "value": "under_construction",
                            "evidence_key": expected["post_key"],
                            "as_of_date": expected["status_date"],
                            "method": "authoritative_physical_status_update",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                self.assertEqual(document["capacities"], [])

        self.assertEqual(len(stable_keys), 4)
        self.assertTrue(all("maries" not in key and "moran" not in key for key in stable_keys))

    def test_combined_metrics_forecasts_and_classification_remain_metadata_only(self) -> None:
        as01 = self._load(AS01_SOURCE)
        as02 = self._load(AS02_SOURCE)
        by_key = {
            item["key"]: item
            for document in (as01, as02)
            for item in document["evidence"]
        }

        as01_post = by_key[AS01_POST_KEY]["metadata"]
        as02_post = by_key[AS02_POST_KEY]["metadata"]
        location = by_key[LOCATION_KEY]["metadata"]
        release = by_key[RELEASE_KEY]["metadata"]

        self.assertEqual(as01_post["reported_combined_critical_it_load_mw"], 114)
        self.assertEqual(as01_post["reported_combined_floor_area_sq_ft"], 608_000)
        self.assertEqual(location["reported_combined_critical_it_load_mw"], 114)
        self.assertEqual(location["reported_combined_floor_area_sq_ft"], 685_000)
        self.assertEqual(release["reported_combined_critical_load_mw"], 114)
        self.assertEqual(release["reported_combined_floor_area_sq_ft"], 685_000)
        for metadata in (as01_post, location, release):
            self.assertIn("neither value", metadata["combined_metric_scope"].lower())
        self.assertIn("without reconciliation", as01_post["floor_area_conflict_guardrail"])

        self.assertEqual(location["site_count_as_reported"], 2)
        self.assertEqual(location["reported_road_names"], ["Maries Road", "Moran Road"])
        self.assertIn("does not map", location["road_mapping_guardrail"])
        self.assertIn("distinct", location["site_identity_scope"])

        self.assertEqual(release["reported_site_codes"], ["AS01", "AS02"])
        self.assertEqual(
            release["as01_initial_occupancy_forecast_as_reported"], "November 2026"
        )
        self.assertEqual(
            release["as02_initial_occupancy_forecast_as_reported"], "July 2027"
        )
        self.assertIn("forward-looking", release["forecast_guardrail"])
        self.assertIn("No owner or operator", release["owner_operator_guardrail"])
        self.assertIn("no utility role", release["utility_guardrail"])
        self.assertIn("No workload row", release["classification_guardrail"])
        self.assertIn("normalized operating-model observation", release["leasing_guardrail"])
        self.assertIn("No contractor", as01_post["holder_role_guardrail"])
        self.assertIn("no capacity row", as02_post["virginia_roadmap_guardrail"])

    def test_new_keys_and_hashes_do_not_collide_with_other_curated_inputs(self) -> None:
        expected_entities: dict[str, str] = {
            spec[field]: name
            for name, spec in SOURCE_SPECS.items()
            for field in ("campus_key", "project_key")
        }
        entity_appearances: dict[str, list[str]] = defaultdict(list)
        evidence_appearances: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
        hash_appearances: dict[str, list[tuple[str, str]]] = defaultdict(list)
        source_hashes: dict[str, list[str]] = defaultdict(list)

        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            source_hashes[hashlib.sha256(path.read_bytes()).hexdigest()].append(path.name)
            document = json.loads(path.read_text(encoding="utf-8"))
            for entity_name in ("campus", "project"):
                entity = document.get(entity_name)
                if entity is not None:
                    entity_appearances[entity["stable_key"]].append(path.name)
            for item in document["evidence"]:
                evidence_appearances[item["key"]].append((path.name, item))
                hash_appearances[item["content_hash"]].append((path.name, item["key"]))

        for key, expected_source in expected_entities.items():
            self.assertEqual(entity_appearances[key], [expected_source])

        expected_evidence_sources = {
            AS01_POST_KEY: [AS01_SOURCE],
            AS02_POST_KEY: [AS02_SOURCE],
            LOCATION_KEY: sorted(SOURCES),
            RELEASE_KEY: sorted(SOURCES),
        }
        for key, expected_sources in expected_evidence_sources.items():
            appearances = evidence_appearances[key]
            self.assertEqual(sorted(name for name, _ in appearances), expected_sources)
            first = appearances[0][1]
            self.assertTrue(all(item == first for _, item in appearances))

        for key, expected in CAPTURES.items():
            self.assertEqual(
                sorted({item_key for _, item_key in hash_appearances[expected["body_sha256"]]}),
                [key],
            )

        for name, spec in SOURCE_SPECS.items():
            self.assertEqual(source_hashes[spec["sha256"]], [name])

    def test_each_source_imports_offline_in_isolation(self) -> None:
        for name in SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 3)
                    self.assertEqual(validate_database(connection), [])
                    expected_counts = {
                        "evidence": 3,
                        "entities": 2,
                        "campuses": 1,
                        "projects": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    }
                    for table, expected in expected_counts.items():
                        self.assertEqual(
                            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                            expected,
                            table,
                        )
                finally:
                    connection.close()

    def test_combined_import_is_offline_idempotent_and_order_independent(self) -> None:
        forward = self._state(SOURCES)
        reverse = self._state(reversed(SOURCES))
        repeated = self._state(SOURCES, repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

        entities, evidence, lifecycle, snapshots, capacities, models, workloads = forward
        self.assertEqual(len(entities), 4)
        self.assertEqual(len(evidence), 4)
        self.assertEqual(len(lifecycle), 2)
        self.assertEqual(len(snapshots), 4)
        self.assertEqual(capacities, ())
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(
            [row[1:] for row in lifecycle],
            [
                (
                    "under_construction",
                    "2025-09-24",
                    "authoritative_physical_status_update",
                ),
                (
                    "under_construction",
                    "2026-07-01",
                    "authoritative_physical_status_update",
                ),
            ],
        )
        for row in snapshots:
            tags = json.loads(row[2])
            self.assertEqual(tags["address"], "Sterling, Virginia, United States")
            self.assertEqual(tags["country"], "United States")
            self.assertEqual(
                tags["role:developer"], "EdgeCore Digital Infrastructure"
            )
            self.assertEqual(
                {key for key in tags if key.startswith("role:")},
                {"role:developer"},
            )
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            self.assertIsNone(row[5])


if __name__ == "__main__":
    unittest.main()
