from __future__ import annotations

import copy
import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T06:36:14Z"

VA1_SOURCE = "curated-official-2026-07-20-menlo-digital-md-va1-herndon.json"
PHX1_SOURCE = "curated-official-2026-07-20-menlo-digital-md-phx1-phoenix.json"
CHN1_SOURCE = "curated-official-2026-07-20-iron-mountain-chn1-chennai-topout.json"
SOURCES = (VA1_SOURCE, PHX1_SOURCE, CHN1_SOURCE)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    VA1_SOURCE: {
        "sha256": "8957e43eaad55b46b36ed8a72db30cb145614158c257400c4013a89b062b24e4",
        "bytes": 16_355,
        "evidence_count": 2,
        "campus_key": "curated:menlo-digital-md-va1-herndon-data-center",
        "project_key": (
            "curated:menlo-digital-md-va1-herndon-data-center:"
            "48mw-facility-build"
        ),
    },
    PHX1_SOURCE: {
        "sha256": "6aca705019ecc1629c14cd96320ac3a1a7fb33e12f8ffa937dc4d6984d3d3281",
        "bytes": 16_862,
        "evidence_count": 2,
        "campus_key": "curated:menlo-digital-md-phx1-phoenix-campus",
        "project_key": (
            "curated:menlo-digital-md-phx1-phoenix-campus:"
            "current-site-preparation"
        ),
    },
    CHN1_SOURCE: {
        "sha256": "cdd605fcc6df19840e203999b8fb5e3e9be66580189843eeb0b0f917d31dd736",
        "bytes": 8_396,
        "evidence_count": 1,
        "campus_key": "curated:iron-mountain-chennai-data-center-campus",
        "project_key": "curated:iron-mountain-chennai-data-center-campus:chn1",
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "menlo-digital-md-va1-topout-2026-04-23-captured-2026-07-20": {
        "body_bytes": 60_156,
        "body_sha256": "68d9e52797b608873b1f840346c79525735503e4e04ef69f524d3d9675cee667",
        "headers_bytes": 888,
        "headers_sha256": "3b556078bda69bfe598f696b8e5c37d17ce5fb70e492ab5b17db2ba86f07907a",
        "writeout_bytes": 16_637,
        "writeout_sha256": "fbdde304197f37f98ff23eb03c2920367d3958cd790546966352851c2dd3093e",
        "response_http_date": "2026-07-20T06:36:14Z",
        "source_url": (
            "https://menlo-digital.com/"
            "menlo-digital-celebrates-topping-out-md-va1/"
        ),
    },
    "menlo-digital-md-va1-portfolio-page-captured-2026-07-20": {
        "body_bytes": 72_332,
        "body_sha256": "88e6511a4ed4b2e7cdb5f148e1ec77bfd59c26f732bf84a61df95134b47ab075",
        "headers_bytes": 773,
        "headers_sha256": "4f0b20bfc767e0a402f3b61293bcc0695777dc1eaf4648fad8476f6aaa6deec9",
        "writeout_bytes": 16_559,
        "writeout_sha256": "d3428151f5fc9eb6964af5c90e0ba4cc21bec10848a35d30a52822f493515bfa",
        "response_http_date": "2026-07-20T06:36:14Z",
        "source_url": "https://menlo-digital.com/portfolio/md-va1-herndon/",
    },
    "menlo-digital-md-phx1-demolition-2025-09-22-captured-2026-07-20": {
        "body_bytes": 319_162,
        "body_sha256": "50b2ddd16ad8a6f23c401ed53ec13ccba61b05c45b4318a709b70a226f42b232",
        "headers_bytes": 5_347,
        "headers_sha256": "e900bb6587ee6f7c7ca84c6a296c15feb268cdb52ef85e7468715a01f96e5c83",
        "writeout_bytes": 17_757,
        "writeout_sha256": "bf1b2622a9d1ca6f7f8b51c4cf9950f8c74ec5489b534717169f5c2f0e22b8b0",
        "response_http_date": "2026-07-20T06:36:14Z",
        "source_url": (
            "https://www.linkedin.com/posts/menlo-digital_datacenters-"
            "digitalinfrastructure-phoenix-activity-7375960657772466176-Ru4l"
        ),
    },
    "menlo-digital-md-phx1-portfolio-page-captured-2026-07-20": {
        "body_bytes": 77_441,
        "body_sha256": "5d1a7d44e3c1052a412327de9555f5cd82a0cd45c7b383a960ea9485c4923b95",
        "headers_bytes": 773,
        "headers_sha256": "e9bfa1fcac91b5579a10a2fbb0427a7f7ac06b4a6ba1a7319ab2a792ec5e7db8",
        "writeout_bytes": 16_564,
        "writeout_sha256": "40d7b404998cc2c7cd309e0756b77cfdabc851ff6740457370d3a8d912ed1134",
        "response_http_date": "2026-07-20T06:36:14Z",
        "source_url": "https://menlo-digital.com/portfolio/md-phx1-phoenix/",
    },
    "iron-mountain-chn1-chennai-topout-2026-04-13-captured-2026-07-20": {
        "body_bytes": 189_144,
        "body_sha256": "b48d0fc9fa876c5fee08ed1e33475786a7bd0d528a6374f5e502389f7591cca8",
        "headers_bytes": 5_347,
        "headers_sha256": "96e8aabe14e53791d573a0bc9d61a550f462a8a9a07670735a200f6e49e4ec83",
        "writeout_bytes": 17_796,
        "writeout_sha256": "8d35dd7906468b433ea60be94c1e39e0345dbc2f3a8cccee99dc765734c55b32",
        "response_http_date": "2026-07-20T06:36:13Z",
        "source_url": (
            "https://www.linkedin.com/posts/iron-mountain-data-centers_"
            "topping-out-in-chennai-we-are-thrilled-activity-"
            "7449365773053136896-cgw2"
        ),
    },
}


class MenloIronMountainCuratedTests(unittest.TestCase):
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
        order: tuple[str, ...],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            result = CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=RETRIEVED_AT,
                            )
                            self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at, created_from_evidence_id "
                    "FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key, recorded_at",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key, as_of_date, recorded_at",
                    "SELECT entities.stable_key, metric, stage, low, base, high, unit, "
                    "as_of_date, recorded_at, target_date, method "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, targets.stable_key "
                    "FROM projects JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _import_document(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.json"
            source.write_text(
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        source,
                        retrieved_at=RETRIEVED_AT,
                    )
            finally:
                connection.close()

    def test_exact_sources_are_hash_pinned_canonical_regular_files(self) -> None:
        self.assertEqual(len(SOURCES), 3)
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(path.stat().st_size, expected["bytes"])
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    expected["sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(
                    len(document["evidence"]), expected["evidence_count"]
                )
                self.assertEqual(
                    document["campus"]["stable_key"], expected["campus_key"]
                )
                self.assertEqual(
                    document["project"]["stable_key"], expected["project_key"]
                )

    def test_capture_contract_is_closed_canonical_and_byte_bound(self) -> None:
        observed: dict[str, dict[str, Any]] = {}
        for name in SOURCES:
            for evidence in self._load(name)["evidence"]:
                self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
                self.assertNotIn(evidence["key"], observed)
                observed[evidence["key"]] = evidence

        self.assertEqual(set(observed), set(CAPTURES))
        for key, expected in CAPTURES.items():
            with self.subTest(evidence=key):
                evidence = observed[key]
                metadata = evidence["metadata"]
                self.assertEqual(evidence["content_hash"], expected["body_sha256"])
                self.assertIn(
                    f"{expected['body_bytes']}-byte", metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f"{expected['headers_bytes']}-byte",
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers_sha256"]
                )
                self.assertIn(
                    f"{expected['writeout_bytes']}-byte",
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout_sha256"],
                )
                self.assertEqual(
                    metadata["response_http_date"], expected["response_http_date"]
                )
                self.assertEqual(evidence["source_url"], expected["source_url"])
                self.assertEqual(metadata["requested_url"], expected["source_url"])
                self.assertEqual(metadata["effective_url"], expected["source_url"])
                self.assertEqual(metadata["canonical_url"], expected["source_url"])
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertIn("unauthenticated curl", metadata["retrieval_method"])
                self.assertIn(
                    "supplied no Authorization",
                    metadata["request_credentials_guardrail"],
                )
                self.assertIn("not redistributed", metadata["rights_scope"])

    def test_entities_have_exact_scopes_roles_and_source_coordinates(self) -> None:
        va1 = self._load(VA1_SOURCE)
        phx1 = self._load(PHX1_SOURCE)
        chn1 = self._load(CHN1_SOURCE)

        expected = (
            (
                va1,
                "13775 McLearen Road, Herndon, VA, United States",
                {"latitude": 38.927085, "longitude": -77.424201},
                "authoritative_address_geocode",
            ),
            (
                phx1,
                "4801-4811 East Thistle Landing Drive, Phoenix, AZ, United States",
                {"latitude": 33.311966, "longitude": -111.978165},
                "authoritative_address_geocode",
            ),
            (
                chn1,
                "Ambattur, Chennai, India",
                None,
                "authoritative_locality",
            ),
        )
        keys: set[str] = set()
        for document, address, coordinates, method in expected:
            for entity_name in ("campus", "project"):
                entity = document[entity_name]
                self.assertNotIn(entity["stable_key"], keys)
                keys.add(entity["stable_key"])
                self.assertEqual(entity["address"], address)
                self.assertEqual(entity["roles"], {})
                self.assertEqual(entity["coordinates"], coordinates)
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], method)

        self.assertEqual(len(keys), 6)
        self.assertIn("source site marker", va1["evidence"][1]["metadata"]["coordinate_scope"])
        self.assertIn("source campus marker", phx1["evidence"][1]["metadata"]["coordinate_scope"])

    def test_lifecycle_is_shell_site_preparation_shell_only(self) -> None:
        expected = {
            VA1_SOURCE: (
                "shell",
                "2026-04-23",
                "authoritative_physical_status_update",
            ),
            PHX1_SOURCE: (
                "site_preparation",
                "2025-09-22",
                "authoritative_physical_status_update",
            ),
            CHN1_SOURCE: (
                "shell",
                "2026-04-13",
                "authoritative_physical_status_update",
            ),
        }
        for name, values in expected.items():
            with self.subTest(source=name):
                document = self._load(name)
                self.assertEqual(len(document["lifecycle"]), 1)
                row = document["lifecycle"][0]
                self.assertEqual(row["entity"], "project")
                self.assertEqual(
                    (row["value"], row["as_of_date"], row["method"]), values
                )
                self.assertNotIn(
                    row["value"],
                    {"mep_electrical", "commissioning", "operational"},
                )

    def test_va1_date_typo_and_start_conflict_are_explicitly_preserved(self) -> None:
        document = self._load(VA1_SOURCE)
        topout = document["evidence"][0]
        current = document["evidence"][1]
        self.assertEqual(topout["published_at"], "2026-04-23")
        self.assertEqual(
            topout["metadata"]["visible_dateline_wording_as_reported"],
            "Herndon, VA – April 23, 2025",
        )
        self.assertEqual(
            topout["metadata"]["construction_start_wording_as_reported"],
            "broke ground in October 2025",
        )
        self.assertIn("impossible", topout["metadata"]["publication_date_guardrail"])
        self.assertIn("publisher typo", topout["metadata"]["publication_date_guardrail"])
        self.assertEqual(
            current["metadata"]["construction_start_wording_as_reported"],
            "Construction commenced Q1 2025.",
        )
        self.assertIn(
            "conflicts", current["metadata"]["construction_start_conflict_guardrail"]
        )
        self.assertNotEqual(document["lifecycle"][0]["as_of_date"], "2025-04-23")

    def test_phx1_demolition_and_zero_percent_do_not_become_building_construction(self) -> None:
        document = self._load(PHX1_SOURCE)
        post = document["evidence"][0]
        page = document["evidence"][1]
        self.assertEqual(
            post["published_at"], "2025-09-22T18:34:19.489Z"
        )
        self.assertEqual(post["metadata"]["status_wording_as_reported"], "Demolition is underway")
        self.assertIn("does not establish data-center building construction", post["metadata"]["physical_scope"])
        self.assertEqual(page["metadata"]["reported_building_count"], 5)
        self.assertEqual(page["metadata"]["reported_construction_progress_percent"], 0)
        self.assertIn("metadata only", page["metadata"]["development_status_guardrail"])
        self.assertIn("no individual building entities", page["metadata"]["building_count_guardrail"])
        self.assertEqual(document["lifecycle"][0]["value"], "site_preparation")

    def test_typed_capacities_are_exact_separate_and_non_operational(self) -> None:
        va1 = self._load(VA1_SOURCE)
        phx1 = self._load(PHX1_SOURCE)
        chn1 = self._load(CHN1_SOURCE)

        va_rows = {
            (row["entity"], row["metric"], row["stage"]): row
            for row in va1["capacities"]
        }
        self.assertEqual(set(va_rows), {
            ("project", "critical_it_mw", "planned"),
            ("project", "grid_connection_mw", "contracted"),
        })
        self.assertEqual(
            (va_rows[("project", "critical_it_mw", "planned")]["low"],
             va_rows[("project", "critical_it_mw", "planned")]["base"],
             va_rows[("project", "critical_it_mw", "planned")]["high"]),
            (48, 48, 48),
        )
        self.assertEqual(
            (va_rows[("project", "grid_connection_mw", "contracted")]["low"],
             va_rows[("project", "grid_connection_mw", "contracted")]["base"],
             va_rows[("project", "grid_connection_mw", "contracted")]["high"]),
            (67.2, 67.2, 67.2),
        )

        phx_rows = {
            (row["entity"], row["metric"], row["stage"]): row
            for row in phx1["capacities"]
        }
        self.assertEqual(set(phx_rows), {
            ("campus", "critical_it_mw", "planned"),
            ("campus", "grid_connection_mw", "contracted"),
        })
        self.assertEqual(
            (phx_rows[("campus", "critical_it_mw", "planned")]["low"],
             phx_rows[("campus", "critical_it_mw", "planned")]["base"],
             phx_rows[("campus", "critical_it_mw", "planned")]["high"]),
            (180, 180, 180),
        )
        self.assertEqual(
            (phx_rows[("campus", "grid_connection_mw", "contracted")]["low"],
             phx_rows[("campus", "grid_connection_mw", "contracted")]["base"],
             phx_rows[("campus", "grid_connection_mw", "contracted")]["high"]),
            (257, 257, 257),
        )
        self.assertEqual(chn1["capacities"], [])
        for document in (va1, phx1, chn1):
            for row in document["capacities"]:
                self.assertNotIn(row["stage"], {"installed", "energized", "operational", "measured"})
                self.assertIsNone(row["target_date"])

    def test_chn1_ambiguous_power_is_metadata_only(self) -> None:
        document = self._load(CHN1_SOURCE)
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["reported_chn1_total_power_capacity_mw"], 23.2)
        self.assertEqual(
            metadata["reported_full_campus_it_load_wording"],
            "over 42 MW of IT load",
        )
        self.assertEqual(
            metadata["reported_campus_highlight_wording"],
            "42 MW total capacity at full build-out (23.2 MW at CHN-1 - 19 MW at CHN-2)",
        )
        self.assertIn("not semantically consistent", metadata["capacity_exclusion"])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertIn("HTTP 429", metadata["source_exclusion"])
        self.assertNotIn(
            "https://www.ironmountain.com/data-centers/locations/chennai-data-center",
            {item["source_url"] for item in document["evidence"]},
        )

    def test_marketing_does_not_create_roles_models_or_workloads(self) -> None:
        for name in SOURCES:
            with self.subTest(source=name):
                document = self._load(name)
                self.assertEqual(document["campus"]["roles"], {})
                self.assertEqual(document["project"]["roles"], {})
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                for evidence in document["evidence"]:
                    metadata = evidence["metadata"]
                    self.assertIn("role_guardrail", metadata)
                    self.assertIn("classification_guardrail", metadata)
                    self.assertIn("no normalized", metadata["classification_guardrail"])

    def test_offline_import_counts_relationships_and_validation(self) -> None:
        state = self._state(SOURCES)
        entities, evidence, snapshots, lifecycle, capacities, models, workloads, projects = state
        self.assertEqual(len(entities), 6)
        self.assertEqual(len(evidence), 5)
        self.assertEqual(len(snapshots), 6)
        self.assertEqual(len(lifecycle), 3)
        self.assertEqual(len(capacities), 4)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(len(projects), 3)
        self.assertEqual({row[2] for row in entities}, {RETRIEVED_AT})
        self.assertEqual({row[2] for row in evidence}, {RETRIEVED_AT})
        self.assertEqual({row[7] for row in snapshots}, {RETRIEVED_AT})
        self.assertEqual({row[3] for row in lifecycle}, {RETRIEVED_AT})
        self.assertEqual({row[8] for row in capacities}, {RETRIEVED_AT})
        self.assertEqual({row[1] for row in projects}, {
            SOURCE_SPECS[VA1_SOURCE]["campus_key"],
            SOURCE_SPECS[PHX1_SOURCE]["campus_key"],
            SOURCE_SPECS[CHN1_SOURCE]["campus_key"],
        })

    def test_import_is_idempotent_and_order_invariant(self) -> None:
        baseline = self._state(SOURCES)
        self.assertEqual(self._state(tuple(reversed(SOURCES))), baseline)
        self.assertEqual(self._state(SOURCES, repetitions=2), baseline)

    def test_import_rejects_retrieval_timestamp_drift(self) -> None:
        document = copy.deepcopy(self._load(CHN1_SOURCE))
        document["evidence"][0]["retrieved_at"] = "2026-07-20T06:36:13Z"
        with self.assertRaisesRegex(ValueError, "must equal the import retrieved_at"):
            self._import_document(document)

    def test_import_rejects_weak_methods_for_physical_construction(self) -> None:
        document = copy.deepcopy(self._load(PHX1_SOURCE))
        document["lifecycle"][0]["method"] = "authoritative_status_update"
        with self.assertRaisesRegex(ValueError, "construction status requires"):
            self._import_document(document)

    def test_import_rejects_coordinates_disguised_as_locality(self) -> None:
        document = copy.deepcopy(self._load(CHN1_SOURCE))
        document["campus"]["coordinates"] = {
            "latitude": 13.0,
            "longitude": 80.0,
        }
        with self.assertRaisesRegex(
            ValueError,
            "authoritative_locality requires null coordinates and geometry",
        ):
            self._import_document(document)


if __name__ == "__main__":
    unittest.main()
