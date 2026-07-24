from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

CAPTURE_METADATA_KEYS = frozenset(
    {
        "coordinate_capture_artifact_guardrail",
        "coordinate_capture_body_scope",
        "coordinate_capture_body_sha256",
        "coordinate_capture_content_type",
        "coordinate_capture_credentials_guardrail",
        "coordinate_capture_curl_writeout_scope",
        "coordinate_capture_curl_writeout_sha256",
        "coordinate_capture_effective_url",
        "coordinate_capture_headers_scope",
        "coordinate_capture_headers_sha256",
        "coordinate_capture_http_status",
        "coordinate_capture_http_version_as_received",
        "coordinate_capture_redirect_count",
        "coordinate_capture_requested_url",
        "coordinate_capture_response_header_blocks",
        "coordinate_capture_retrieval_method",
        "coordinate_capture_retrieved_at",
        "coordinate_capture_size_download_bytes_as_received",
        "coordinate_guardrail",
        "coordinate_scope",
        "coordinate_source_locator",
        "coordinate_source_type",
        "coordinate_values",
    }
)

SPECS: dict[str, dict[str, Any]] = {
    "ord": {
        "v1": "curated-official-2026-07-20-edged-ord01-2-chicago-topout.json",
        "v2": "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json",
        "v1_sha256": "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c",
        "v2_sha256": "03fa4a5915a43d70456b63ab54c2b7c8eb9bdf918ffc10c938276a4da90db368",
        "evidence_index": 1,
        "evidence_key": "edged-chicago-location-page-captured-2026-07-20",
        "coordinates": (41.8079909, -88.2419971),
        "entities": ("campus", "project"),
        "metadata_replacements": {"address_scope", "imagery_guardrail"},
        "source_type": "publisher_authored_outbound_map_link",
        "capture": {
            "body_bytes": 106458,
            "body_sha256": "d4110379d78f1108a4d6323c507dac307fafa23c5b4f07a1387793ad5165befe",
            "headers_bytes": 735,
            "headers_sha256": "2b8d6686ef7e8ef7e49f03f6c7c457e6c00b1ddcc46f24d4cbe238b0e12269f5",
            "writeout_bytes": 9292,
            "writeout_sha256": "7a7da4c8c3e66612a8f028d992cddc0a5bc61f8acdfccbca79e148d8d2b18c43",
            "retrieved_at": "2026-07-20T18:19:44Z",
            "content_type": "text/html; charset=utf-8",
            "size_download": 39315,
        },
    },
    "atl": {
        "v1": "curated-official-2026-07-20-edged-atl01-3-atlanta-topout.json",
        "v2": "curated-official-2026-07-20-edged-atl01-3-atlanta-topout-v2.json",
        "v1_sha256": "0213438b6b2844bbad14674ed8381e3a019c3d240ef55db3625c1543a4f98c06",
        "v2_sha256": "6011e9ed8172d940d15df2d0da46e4ec1c98014dc5dae47eb94a4c7125c16ded",
        "evidence_index": 1,
        "evidence_key": "edged-atlanta-location-page-captured-2026-07-20",
        "coordinates": (33.800763, -84.437293),
        "entities": ("project",),
        "metadata_replacements": {"address_scope", "imagery_guardrail"},
        "source_type": "publisher_authored_outbound_map_link",
        "capture": {
            "body_bytes": 103995,
            "body_sha256": "780f482af9c6895c665758ec8eba32110b1fe2592ee82278c0d9d55d6a73504c",
            "headers_bytes": 736,
            "headers_sha256": "f036691a61537302e563253002152e42e22aa0d13aa3860ff33eed10af492019",
            "writeout_bytes": 9292,
            "writeout_sha256": "f55b5062b4eed84711b49ec34b92654c1688957349fd75998ed6c046a86e05ce",
            "retrieved_at": "2026-07-20T18:20:07Z",
            "content_type": "text/html; charset=utf-8",
            "size_download": 39152,
        },
    },
    "rom1": {
        "v1": "curated-official-2026-07-19-digital-realty-rom1-rome.json",
        "v2": "curated-official-2026-07-19-digital-realty-rom1-rome-v2.json",
        "v1_sha256": "f809518a71f8d0f4333daabab2e94534af03ea1a1b6b19cd35a91bdecd52e84e",
        "v2_sha256": "f11d6fad3f51d5e5df8c2f667a9c4d600de7df94df5f5442a4201d44655c5120",
        "evidence_index": 2,
        "evidence_key": "digital-realty-rom1-address-captured-2026-07-19",
        "coordinates": (41.776044, 12.48923),
        "entities": ("campus", "project"),
        "metadata_replacements": {"coordinate_basis"},
        "source_type": "publisher_html_structured_facility_fields",
        "capture": {
            "body_bytes": 196008,
            "body_sha256": "5e0d6ca4a486b8d8b9e4664480c681717c9f52d8750020b42d096dfd38258271",
            "headers_bytes": 383,
            "headers_sha256": "6bdb08c7045154c07fa052afbcbfcfc223f975c38d00df60b5a162a57eb25786",
            "writeout_bytes": 16273,
            "writeout_sha256": "baac9867edee7fc443b796f20e091327b36f949ef681896b6ad926c4b3e356e5",
            "retrieved_at": "2026-07-20T18:20:09Z",
            "content_type": "text/html; charset=utf-8",
            "size_download": 29470,
        },
    },
    "fra20": {
        "v1": "curated-official-2026-07-19-digital-realty-fra20-frankfurt.json",
        "v2": "curated-official-2026-07-19-digital-realty-fra20-frankfurt-v2.json",
        "v1_sha256": "096378e468cfd10d4ed41e25b5fe1b32fff3d2c19b8bc71df6ab51cdadb38e59",
        "v2_sha256": "d50982f91d6bb3e9f69a555ceb61d7885ac4c463fd806c9daf5dbedc2edb8197",
        "evidence_index": 1,
        "evidence_key": "digital-realty-fra20-address-captured-2026-07-19",
        "coordinates": (50.125936, 8.752816),
        "entities": ("campus", "project"),
        "metadata_replacements": {"coordinate_basis"},
        "source_type": "publisher_html_structured_facility_fields",
        "capture": {
            "body_bytes": 198952,
            "body_sha256": "5bf2e60b5f30d22ca177bf077012344126efc54af83b4a358cef032c40ea39b9",
            "headers_bytes": 383,
            "headers_sha256": "adb42ca1c3dc123401db47f2416a0688010b31f2253bae2710c753b55ac34036",
            "writeout_bytes": 16310,
            "writeout_sha256": "503a75520939a3246268efa3f56eedbf4e48047a9d47144f25b1250d55709de9",
            "retrieved_at": "2026-07-20T18:20:10Z",
            "content_type": "text/html; charset=utf-8",
            "size_download": 33725,
        },
    },
    "ath1": {
        "v1": "curated-official-2026-07-19-data4-ath1-first-data-center.json",
        "v2": "curated-official-2026-07-19-data4-ath1-first-data-center-v2.json",
        "v1_sha256": "028990145023dd581beff459437414324bcf76b0da893a2c46c0a13aa065df7c",
        "v2_sha256": "f5945a8c0b0c290bea1251d3514986c9d6fefc96ccc6f784ed23c703646f046a",
        "evidence_index": 1,
        "evidence_key": "data4-athens-campus-current-location-captured-2026-07-19",
        "coordinates": (37.9429028, 23.8735719),
        "entities": ("campus", "project"),
        "metadata_replacements": {
            "address_normalization_scope",
            "imagery_guardrail",
            "locality_guardrail",
        },
        "source_type": "publisher_html_map_marker",
        "capture": {
            "body_bytes": 124396,
            "body_sha256": "ed826d9fbc599020c0b8006ccbe815d3db73a27372905d042d760677161d47a3",
            "headers_bytes": 571,
            "headers_sha256": "d2ce5f06f2fbca5fc6ce80ab5c3da464b612287f20ba812bb8dcf2ccc87b0c1f",
            "writeout_bytes": 11391,
            "writeout_sha256": "8202ba79af4b346f955e972fdd4c87574d8af661cd39edc09fd916afa95d79cb",
            "retrieved_at": "2026-07-20T18:20:10Z",
            "content_type": "text/html; charset=UTF-8",
            "size_download": 23085,
        },
    },
    "zrh12": {
        "v1": "curated-official-2026-07-20-vantage-zrh12-winterthur-topout.json",
        "v2": "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json",
        "v1_sha256": "587318195fb538e94bbbea1aea27abe12f47e7526b055acd8d22143815d13515",
        "v2_sha256": "6cd9f44731f769cf03e68ec41ee018ac312a6f41ef2ddbb462bdd6f91f2fa728",
        "evidence_index": 1,
        "evidence_key": "vantage-zrh1-winterthur-campus-current-captured-2026-07-20",
        "coordinates": (47.5020821, 8.7713397),
        "entities": ("campus", "project"),
        "metadata_replacements": {"imagery_guardrail"},
        "source_type": "publisher_html_map_marker",
        "entity_provenance": {
            "project": {
                "evidence_key": "vantage-zrh1-winterthur-campus-current-captured-2026-07-20",
                "as_of_date": "2026-07-20",
            }
        },
        "capture": {
            "body_bytes": 220986,
            "body_sha256": "1400734895f83baa651d75397f8ea474177c11d2614abb060280f3ed4f1554d3",
            "headers_bytes": 2010,
            "headers_sha256": "04fd33d956b3bf3b57a0d71f116222d2b92ed65852e2bfcd24aa13116adb23e8",
            "writeout_bytes": 9523,
            "writeout_sha256": "597bc676de7464c8faf4371ec1fd45278b9606af666152c39ff149a54f0204c8",
            "retrieved_at": "2026-07-20T18:20:15Z",
            "content_type": "text/html; charset=UTF-8",
            "size_download": 34057,
        },
    },
}

EXACT_TABLES = (
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "administrative_assignments",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)
ALL_TABLES = ("evidence", "entities", "entity_snapshots", *EXACT_TABLES)
VANTAGE_PROJECT_KEY = "curated:vantage-zrh1-winterthur-campus:zrh12"
ATLANTA_CAMPUS_KEY = "curated:edged-atlanta-campus"


class CoordinateOnlyCuratedSuccessorsV2Tests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _retrieved_at(self, path: Path) -> str:
        values = {
            row["retrieved_at"]
            for row in json.loads(path.read_text(encoding="utf-8"))["evidence"]
        }
        self.assertEqual(len(values), 1)
        return next(iter(values))

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    tuple(row) for row in connection.execute(f"SELECT * FROM {table}")
                )
            )
            for table in ALL_TABLES
        }

    def _build(
        self, names: Iterable[str], *, repeat: bool = False
    ) -> tuple[Any, dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        results: dict[str, tuple[int, int]] = {}
        try:
            with self._network_guard():
                for name in names:
                    path = self._path(name)
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection, path, retrieved_at=self._retrieved_at(path)
                    )
                    results[name] = (result.entities_created, result.evidence_created)
                state = self._state(connection)
                if repeat:
                    for name in names:
                        path = self._path(name)
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=self._retrieved_at(path)
                        )
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._state(connection), state)
            self.assertEqual(validate_database(connection), [])
            connection.close()
            return temporary, state, results
        except Exception:
            connection.close()
            temporary.cleanup()
            raise

    def _capture_assertions(
        self, metadata: dict[str, Any], spec: dict[str, Any]
    ) -> None:
        capture = spec["capture"]
        self.assertEqual(
            metadata["coordinate_capture_body_sha256"], capture["body_sha256"]
        )
        self.assertIn(
            f"exact {capture['body_bytes']}-byte",
            metadata["coordinate_capture_body_scope"],
        )
        self.assertEqual(
            metadata["coordinate_capture_headers_sha256"], capture["headers_sha256"]
        )
        self.assertIn(
            f"exact {capture['headers_bytes']}-byte",
            metadata["coordinate_capture_headers_scope"],
        )
        self.assertEqual(
            metadata["coordinate_capture_curl_writeout_sha256"],
            capture["writeout_sha256"],
        )
        self.assertIn(
            f"exact {capture['writeout_bytes']}-byte",
            metadata["coordinate_capture_curl_writeout_scope"],
        )
        self.assertEqual(
            metadata["coordinate_capture_retrieved_at"], capture["retrieved_at"]
        )
        self.assertEqual(metadata["coordinate_capture_http_status"], 200)
        self.assertEqual(
            metadata["coordinate_capture_http_version_as_received"], "HTTP/2"
        )
        self.assertEqual(metadata["coordinate_capture_redirect_count"], 0)
        self.assertEqual(metadata["coordinate_capture_response_header_blocks"], 1)
        self.assertEqual(
            metadata["coordinate_capture_content_type"], capture["content_type"]
        )
        self.assertEqual(
            metadata["coordinate_capture_size_download_bytes_as_received"],
            capture["size_download"],
        )
        self.assertEqual(metadata["coordinate_source_type"], spec["source_type"])
        latitude, longitude = spec["coordinates"]
        self.assertEqual(
            metadata["coordinate_values"],
            {"latitude": latitude, "longitude": longitude},
        )
        retrieval = metadata["coordinate_capture_retrieval_method"]
        self.assertIn("credential-free", retrieval)
        self.assertIn("no retries", retrieval)
        self.assertIn("or map-link follow-up", retrieval)
        credentials = metadata["coordinate_capture_credentials_guardrail"]
        for forbidden_input in ("Authorization", "Cookie request header", "cookie jar"):
            self.assertIn(forbidden_input, credentials)
        guardrail = metadata["coordinate_guardrail"]
        for forbidden_method in (
            "geocoder",
            "OpenStreetMap",
            "satellite imagery",
            "computer vision",
            "parcel",
            "footprint",
        ):
            self.assertIn(forbidden_method, guardrail)

    def test_v1_hashes_and_json_deltas_are_exactly_coordinate_scoped(self) -> None:
        for label, spec in SPECS.items():
            with self.subTest(source=label):
                v1_path = self._path(spec["v1"])
                v2_path = self._path(spec["v2"])
                self.assertEqual(
                    hashlib.sha256(v1_path.read_bytes()).hexdigest(), spec["v1_sha256"]
                )
                self.assertEqual(
                    hashlib.sha256(v2_path.read_bytes()).hexdigest(), spec["v2_sha256"]
                )
                v1 = self._load(spec["v1"])
                v2 = self._load(spec["v2"])
                self.assertEqual(v1["schema_version"], v2["schema_version"])
                self.assertEqual(len(v1["evidence"]), len(v2["evidence"]))
                self.assertEqual(
                    [row["key"] for row in v1["evidence"]],
                    [row["key"] for row in v2["evidence"]],
                )
                self.assertEqual(
                    v2["evidence"][spec["evidence_index"]]["key"], spec["evidence_key"]
                )

                restored = copy.deepcopy(v2)
                for index, (before, after) in enumerate(
                    zip(v1["evidence"], v2["evidence"])
                ):
                    if index != spec["evidence_index"]:
                        self.assertEqual(after, before)
                        continue
                    before_without_metadata = {
                        key: value for key, value in before.items() if key != "metadata"
                    }
                    after_without_metadata = {
                        key: value for key, value in after.items() if key != "metadata"
                    }
                    self.assertEqual(after_without_metadata, before_without_metadata)
                    metadata = after["metadata"]
                    self.assertTrue(
                        CAPTURE_METADATA_KEYS.isdisjoint(before["metadata"])
                    )
                    self.assertEqual(
                        set(metadata) - set(before["metadata"]), CAPTURE_METADATA_KEYS
                    )
                    changed_existing = {
                        key
                        for key in set(metadata) & set(before["metadata"])
                        if metadata[key] != before["metadata"][key]
                    }
                    self.assertEqual(changed_existing, spec["metadata_replacements"])
                    self._capture_assertions(metadata, spec)
                    restored_metadata = restored["evidence"][index]["metadata"]
                    for key in CAPTURE_METADATA_KEYS:
                        del restored_metadata[key]
                    for key in spec["metadata_replacements"]:
                        restored_metadata[key] = before["metadata"][key]

                for entity_name in ("campus", "project"):
                    before = v1[entity_name]
                    after = v2[entity_name]
                    self.assertEqual(after["stable_key"], before["stable_key"])
                    self.assertEqual(after["name"], before["name"])
                    self.assertEqual(after["country"], before["country"])
                    self.assertEqual(after["address"], before["address"])
                    self.assertEqual(after["roles"], before["roles"])
                    self.assertEqual(after["geometry"], before["geometry"])
                    self.assertEqual(after["confidence"], before["confidence"])
                    if entity_name in spec["entities"]:
                        latitude, longitude = spec["coordinates"]
                        self.assertEqual(
                            after["coordinates"],
                            {"latitude": latitude, "longitude": longitude},
                        )
                        self.assertEqual(after["method"], "authoritative_site_plan")
                        restored[entity_name]["coordinates"] = before["coordinates"]
                        restored[entity_name]["method"] = before["method"]
                    else:
                        self.assertEqual(after, before)
                    for key, expected in (
                        spec.get("entity_provenance", {}).get(entity_name, {}).items()
                    ):
                        self.assertEqual(after[key], expected)
                        restored[entity_name][key] = before[key]

                self.assertEqual(restored, v1)
                for section in (
                    "lifecycle",
                    "operating_models",
                    "workloads",
                    "capacities",
                ):
                    self.assertEqual(v2[section], v1[section])
                for evidence in v2["evidence"]:
                    self.assertNotEqual(evidence["kind"], "satellite_imagery")

    def _import_documents(self, version: str) -> tuple[Any, Any]:
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        try:
            with self._network_guard():
                for spec in SPECS.values():
                    path = self._path(spec[version])
                    CuratedOfficialSourceAdapter().import_file(
                        connection, path, retrieved_at=self._retrieved_at(path)
                    )
            self.assertEqual(validate_database(connection), [])
            return temporary, connection
        except Exception:
            connection.close()
            temporary.cleanup()
            raise

    def _evidence_map(self, connection: Any) -> dict[str, dict[str, Any]]:
        return {
            row["id"]: dict(row)
            for row in connection.execute("SELECT * FROM evidence ORDER BY id")
        }

    def _entity_map(self, connection: Any) -> dict[str, dict[str, Any]]:
        return {
            row["stable_key"]: dict(row)
            for row in connection.execute("SELECT * FROM entities ORDER BY stable_key")
        }

    def _snapshot_map(self, connection: Any) -> dict[str, dict[str, Any]]:
        return {
            row["stable_key"]: dict(row)
            for row in connection.execute(
                "SELECT entities.stable_key, entity_snapshots.* "
                "FROM entity_snapshots JOIN entities "
                "ON entities.id = entity_snapshots.entity_id "
                "ORDER BY entities.stable_key"
            )
        }

    def test_adapter_v1_v2_delta_is_coordinate_and_provenance_only(self) -> None:
        v1_temporary, v1_connection = self._import_documents("v1")
        v2_temporary, v2_connection = self._import_documents("v2")
        try:
            for table in EXACT_TABLES:
                self.assertEqual(
                    [
                        tuple(row)
                        for row in v2_connection.execute(
                            f"SELECT * FROM {table} ORDER BY 1"
                        )
                    ],
                    [
                        tuple(row)
                        for row in v1_connection.execute(
                            f"SELECT * FROM {table} ORDER BY 1"
                        )
                    ],
                    table,
                )

            v1_evidence = self._evidence_map(v1_connection)
            v2_evidence = self._evidence_map(v2_connection)
            self.assertEqual(set(v2_evidence), set(v1_evidence))
            specs_by_key = {spec["evidence_key"]: spec for spec in SPECS.values()}
            for evidence_id, before in v1_evidence.items():
                after = copy.deepcopy(v2_evidence[evidence_id])
                before_metadata = json.loads(before["metadata_json"])
                after_metadata = json.loads(after["metadata_json"])
                record_key = before_metadata["curated_record_key"]
                if record_key in specs_by_key:
                    spec = specs_by_key[record_key]
                    for key in CAPTURE_METADATA_KEYS:
                        del after_metadata["record"][key]
                    for key in spec["metadata_replacements"]:
                        after_metadata["record"][key] = before_metadata["record"][key]
                after["metadata_json"] = json.dumps(
                    after_metadata, sort_keys=True, separators=(",", ":")
                )
                self.assertEqual(after, before, record_key)

            v1_entities = self._entity_map(v1_connection)
            v2_entities = self._entity_map(v2_connection)
            self.assertEqual(set(v2_entities), set(v1_entities))
            for stable_key, before in v1_entities.items():
                after = copy.deepcopy(v2_entities[stable_key])
                if stable_key == VANTAGE_PROJECT_KEY:
                    self.assertNotEqual(
                        after["created_from_evidence_id"],
                        before["created_from_evidence_id"],
                    )
                    after["created_from_evidence_id"] = before[
                        "created_from_evidence_id"
                    ]
                self.assertEqual(after, before, stable_key)

            expected_coordinates: dict[str, tuple[float, float]] = {}
            for spec in SPECS.values():
                document = self._load(spec["v2"])
                for entity_name in spec["entities"]:
                    expected_coordinates[document[entity_name]["stable_key"]] = spec[
                        "coordinates"
                    ]
            v1_snapshots = self._snapshot_map(v1_connection)
            v2_snapshots = self._snapshot_map(v2_connection)
            self.assertEqual(set(v2_snapshots), set(v1_snapshots))
            self.assertEqual(len(v2_snapshots), 12)
            for stable_key, before in v1_snapshots.items():
                after = v2_snapshots[stable_key]
                if stable_key not in expected_coordinates:
                    self.assertEqual(after, before, stable_key)
                    continue
                latitude, longitude = expected_coordinates[stable_key]
                self.assertIsNone(before["latitude"])
                self.assertIsNone(before["longitude"])
                self.assertIsNone(before["geometry_json"])
                self.assertEqual(before["method"], "authoritative_locality")
                self.assertEqual(after["latitude"], latitude)
                self.assertEqual(after["longitude"], longitude)
                self.assertEqual(after["method"], "authoritative_site_plan")
                self.assertEqual(
                    json.loads(after["geometry_json"]),
                    {"type": "Point", "coordinates": [longitude, latitude]},
                )
                allowed = {"id", "latitude", "longitude", "geometry_json", "method"}
                if stable_key == VANTAGE_PROJECT_KEY:
                    allowed.update({"evidence_id", "as_of_date"})
                    self.assertEqual(after["as_of_date"], "2026-07-20")
                for key in set(before) - allowed:
                    self.assertEqual(after[key], before[key], f"{stable_key}.{key}")
                self.assertEqual(after["confidence"], before["confidence"])

            self.assertEqual(
                v2_snapshots[ATLANTA_CAMPUS_KEY], v1_snapshots[ATLANTA_CAMPUS_KEY]
            )
        finally:
            v1_connection.close()
            v2_connection.close()
            v1_temporary.cleanup()
            v2_temporary.cleanup()

    def test_combined_v2_import_is_offline_reversible_and_idempotent(self) -> None:
        names = tuple(spec["v2"] for spec in SPECS.values())
        forward_temporary, forward, forward_results = self._build(names, repeat=True)
        reverse_temporary, reverse, reverse_results = self._build(reversed(names))
        try:
            self.assertEqual(reverse, forward)
            expected_results = {
                spec["v2"]: (2, len(self._load(spec["v2"])["evidence"]))
                for spec in SPECS.values()
            }
            self.assertEqual(forward_results, expected_results)
            self.assertEqual(reverse_results, expected_results)
            counts = {table: len(rows) for table, rows in forward.items()}
            self.assertEqual(
                counts,
                {
                    "evidence": 15,
                    "entities": 12,
                    "entity_snapshots": 12,
                    "campuses": 6,
                    "facilities": 0,
                    "buildings": 0,
                    "projects": 6,
                    "administrative_assignments": 0,
                    "lifecycle_observations": 6,
                    "operating_model_observations": 0,
                    "workload_observations": 4,
                    "capacity_estimates": 6,
                },
            )
            coordinate_rows = [
                row for row in forward["entity_snapshots"] if row[3] is not None
            ]
            self.assertEqual(len(coordinate_rows), 11)
        finally:
            forward_temporary.cleanup()
            reverse_temporary.cleanup()

    def test_adapter_imports_v2_offline_in_both_workspace_layouts(self) -> None:
        source_specs = [
            (str(self._path(spec["v2"])), self._retrieved_at(self._path(spec["v2"])))
            for spec in SPECS.values()
        ]
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated import CuratedOfficialSourceAdapter
from {package}.database import initialize
from {package}.service import validate_database

sources = {source_specs!r}
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for source, retrieved_at in sources:
                CuratedOfficialSourceAdapter().import_file(connection, source, retrieved_at=retrieved_at)
        assert validate_database(connection) == []
        result = {{
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "coordinates": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL AND longitude IS NOT NULL").fetchone()[0],
            "site_plan": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE method = 'authoritative_site_plan'").fetchone()[0],
            "locality": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE method = 'authoritative_locality'").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
        }}
        print(json.dumps(result, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "capacity": 6,
                        "coordinates": 11,
                        "entities": 12,
                        "evidence": 15,
                        "lifecycle": 6,
                        "locality": 1,
                        "operating_models": 0,
                        "site_plan": 11,
                        "snapshots": 12,
                        "workloads": 4,
                    },
                )


if __name__ == "__main__":
    unittest.main()
