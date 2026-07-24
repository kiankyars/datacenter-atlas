from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

ORD_V1 = "curated-official-2026-07-20-edged-ord01-2-chicago-topout.json"
ATL_V1 = "curated-official-2026-07-20-edged-atl01-3-atlanta-topout.json"
ROM1_V2 = "curated-official-2026-07-19-digital-realty-rom1-rome-v2.json"
FRA20_V2 = "curated-official-2026-07-19-digital-realty-fra20-frankfurt-v2.json"
ATH1_V2 = "curated-official-2026-07-19-data4-ath1-first-data-center-v2.json"
ZRH12_V5 = "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v5.json"

ACCEPTED_SOURCES = (ORD_V1, ATL_V1, ROM1_V2, FRA20_V2, ATH1_V2, ZRH12_V5)

ACCEPTED_HASHES = {
    ORD_V1: "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c",
    ATL_V1: "0213438b6b2844bbad14674ed8381e3a019c3d240ef55db3625c1543a4f98c06",
    ROM1_V2: "f11d6fad3f51d5e5df8c2f667a9c4d600de7df94df5f5442a4201d44655c5120",
    FRA20_V2: "d50982f91d6bb3e9f69a555ceb61d7885ac4c463fd806c9daf5dbedc2edb8197",
    ATH1_V2: "f5945a8c0b0c290bea1251d3514986c9d6fefc96ccc6f784ed23c703646f046a",
    ZRH12_V5: "45b8ba2a95b743fbff19df93ce4cb9b846d92aa347360bfd0606dd32d1fc90d8",
}

REJECTED_SUCCESSORS = {
    "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json": (
        "03fa4a5915a43d70456b63ab54c2b7c8eb9bdf918ffc10c938276a4da90db368"
    ),
    "curated-official-2026-07-20-edged-atl01-3-atlanta-topout-v2.json": (
        "6011e9ed8172d940d15df2d0da46e4ec1c98014dc5dae47eb94a4c7125c16ded"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json": (
        "6cd9f44731f769cf03e68ec41ee018ac312a6f41ef2ddbb462bdd6f91f2fa728"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v3.json": (
        "d053d2a638a73c8730e1c3eae22c2f7ac83842edff2f62e04ae30b231f70c15d"
    ),
    "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v4.json": (
        "4248a4487577cf53f56ba9d90aa5c0ad2b8e0a8330607e4fb5fc1bd25d719376"
    ),
}

VANTAGE_COORDINATE_METADATA_KEYS = frozenset(
    {
        "coordinate_guardrail",
        "coordinate_scope",
        "coordinate_source_locator",
        "coordinate_source_type",
        "coordinate_values",
    }
)

DIRECT_CAPTURE_METADATA_KEYS = frozenset(
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

DIRECT_SUCCESSORS: dict[str, dict[str, Any]] = {
    ROM1_V2: {
        "v1": "curated-official-2026-07-19-digital-realty-rom1-rome.json",
        "v1_sha256": "f809518a71f8d0f4333daabab2e94534af03ea1a1b6b19cd35a91bdecd52e84e",
        "evidence_index": 2,
        "coordinates": (41.776044, 12.48923),
        "metadata_replacements": {"coordinate_basis"},
    },
    FRA20_V2: {
        "v1": "curated-official-2026-07-19-digital-realty-fra20-frankfurt.json",
        "v1_sha256": "096378e468cfd10d4ed41e25b5fe1b32fff3d2c19b8bc71df6ab51cdadb38e59",
        "evidence_index": 1,
        "coordinates": (50.125936, 8.752816),
        "metadata_replacements": {"coordinate_basis"},
    },
    ATH1_V2: {
        "v1": "curated-official-2026-07-19-data4-ath1-first-data-center.json",
        "v1_sha256": "028990145023dd581beff459437414324bcf76b0da893a2c46c0a13aa065df7c",
        "evidence_index": 1,
        "coordinates": (37.9429028, 23.8735719),
        "metadata_replacements": {
            "address_normalization_scope",
            "imagery_guardrail",
            "locality_guardrail",
        },
    },
}

VANTAGE_V1 = "curated-official-2026-07-20-vantage-zrh12-winterthur-topout.json"
VANTAGE_V1_SHA256 = "587318195fb538e94bbbea1aea27abe12f47e7526b055acd8d22143815d13515"
VANTAGE_CAMPUS_KEY = "curated:vantage-zrh1-winterthur-campus"
VANTAGE_PROJECT_KEY = "curated:vantage-zrh1-winterthur-campus:zrh12"
VANTAGE_CAMPUS_EVIDENCE = "vantage-zrh1-winterthur-campus-current-captured-2026-07-20"
VANTAGE_PROJECT_EVIDENCE = (
    "dpr-vantage-zrh12-topout-linkedin-2026-01-15-captured-2026-07-20"
)

ALL_TABLES = (
    "evidence",
    "entities",
    "entity_snapshots",
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


class CoordinateSuccessorDispositionV5Tests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _retrieved_at(self, name: str) -> str:
        values = {item["retrieved_at"] for item in self._load(name)["evidence"]}
        self.assertEqual(len(values), 1)
        return next(iter(values))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("coordinate disposition attempted network access")
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
        self, names: Iterable[str], *, repetitions: int = 1
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in names:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=self._retrieved_at(name),
                            )
                self.assertEqual(validate_database(connection), [])
                return {
                    table: tuple(
                        sorted(
                            tuple(row)
                            for row in connection.execute(f"SELECT * FROM {table}")
                        )
                    )
                    for table in ALL_TABLES
                }
            finally:
                connection.close()

    def test_hash_pinned_disposition_and_vantage_v5_delta_are_exact(self) -> None:
        self.assertEqual(len(ACCEPTED_SOURCES), 6)
        self.assertTrue(set(ACCEPTED_SOURCES).isdisjoint(REJECTED_SUCCESSORS))

        for name, expected_hash in {**ACCEPTED_HASHES, **REJECTED_SUCCESSORS}.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                raw = path.read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_hash)
                document = json.loads(raw)
                self.assertEqual(
                    raw.decode("utf-8"),
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )

        vantage_v1_path = self._path(VANTAGE_V1)
        self.assertEqual(
            hashlib.sha256(vantage_v1_path.read_bytes()).hexdigest(),
            VANTAGE_V1_SHA256,
        )
        v1 = self._load(VANTAGE_V1)
        v5 = self._load(ZRH12_V5)
        self.assertEqual(len(v5["evidence"]), 3)
        self.assertEqual(v5["evidence"][0], v1["evidence"][0])
        self.assertEqual(v5["evidence"][2], v1["evidence"][2])
        self.assertEqual(
            {
                key: value
                for key, value in v5["evidence"][1].items()
                if key != "metadata"
            },
            {
                key: value
                for key, value in v1["evidence"][1].items()
                if key != "metadata"
            },
        )
        self.assertEqual(
            v5["evidence"][1]["content_hash"],
            "211623c8cbbc8872dc91fc3fbfd062aa20222558ef237ed3bf94f408bc08fa62",
        )
        self.assertEqual(v5["evidence"][1]["retrieved_at"], "2026-07-20T06:42:12Z")
        self.assertIn(
            "exact 220986-byte",
            v5["evidence"][1]["metadata"]["content_hash_scope"],
        )
        self.assertEqual(v5["project"], v1["project"])
        self.assertEqual(
            json.dumps(v5["project"], indent=2, ensure_ascii=False),
            json.dumps(v1["project"], indent=2, ensure_ascii=False),
        )
        self.assertIsNone(v5["project"]["coordinates"])
        self.assertEqual(v5["project"]["evidence_key"], VANTAGE_PROJECT_EVIDENCE)
        self.assertEqual(v5["project"]["as_of_date"], "2026-01-15")
        self.assertEqual(v5["project"]["method"], "authoritative_locality")

        self.assertEqual(
            v5["campus"]["coordinates"],
            {"latitude": 47.5020821, "longitude": 8.7713397},
        )
        self.assertEqual(v5["campus"]["method"], "authoritative_site_plan")
        self.assertEqual(v5["campus"]["evidence_key"], VANTAGE_CAMPUS_EVIDENCE)
        self.assertEqual(v5["campus"]["as_of_date"], "2026-07-20")

        coordinate_metadata = v5["evidence"][1]["metadata"]
        self.assertEqual(
            set(coordinate_metadata) - set(v1["evidence"][1]["metadata"]),
            VANTAGE_COORDINATE_METADATA_KEYS,
        )
        self.assertEqual(
            {
                key
                for key in set(coordinate_metadata) & set(v1["evidence"][1]["metadata"])
                if coordinate_metadata[key] != v1["evidence"][1]["metadata"][key]
            },
            {"imagery_guardrail"},
        )
        self.assertEqual(
            coordinate_metadata["coordinate_values"],
            {"latitude": 47.5020821, "longitude": 8.7713397},
        )
        self.assertIn("campus/address point", coordinate_metadata["coordinate_scope"])
        self.assertIn("not assigned to ZRH12", coordinate_metadata["coordinate_scope"])
        self.assertIn("project-coordinate", coordinate_metadata["coordinate_guardrail"])
        locator = coordinate_metadata["coordinate_source_locator"]
        self.assertIn("exact retained 220986-byte", locator)
        self.assertIn(v5["evidence"][1]["content_hash"], locator)
        self.assertIn(v5["evidence"][1]["retrieved_at"], locator)
        self.assertIn('data-lat="47.5020821"', locator)
        self.assertIn('data-lng="8.7713397"', locator)
        self.assertFalse(
            any(key.startswith("coordinate_capture_") for key in coordinate_metadata)
        )
        serialized_v5 = json.dumps(v5, sort_keys=True)
        self.assertNotIn("2026-07-20T18:20:15Z", serialized_v5)
        self.assertNotIn(
            "1400734895f83baa651d75397f8ea474177c11d2614abb060280f3ed4f1554d3",
            serialized_v5,
        )

        restored = copy.deepcopy(v5)
        restored["evidence"][1]["metadata"] = copy.deepcopy(
            v1["evidence"][1]["metadata"]
        )
        restored["campus"]["coordinates"] = v1["campus"]["coordinates"]
        restored["campus"]["method"] = v1["campus"]["method"]
        self.assertEqual(restored, v1)

    def test_rejected_vantage_candidates_have_pinned_distinct_failures(self) -> None:
        v1 = self._load(VANTAGE_V1)
        v2 = self._load(
            "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json"
        )
        self.assertNotEqual(v2["project"], v1["project"])
        self.assertEqual(v2["project"]["coordinates"], v2["campus"]["coordinates"])
        self.assertEqual(v2["project"]["evidence_key"], VANTAGE_CAMPUS_EVIDENCE)
        self.assertEqual(v2["project"]["as_of_date"], "2026-07-20")

        v3 = self._load(
            "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v3.json"
        )
        self.assertEqual(v3["evidence"][1]["retrieved_at"], "2026-07-20T06:42:12Z")
        self.assertEqual(
            v3["evidence"][1]["metadata"]["coordinate_capture_retrieved_at"],
            "2026-07-20T18:20:15Z",
        )

        v4_name = "curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v4.json"
        v4 = self._load(v4_name)
        self.assertEqual(
            {item["retrieved_at"] for item in v4["evidence"]},
            {"2026-07-20T06:42:12Z", "2026-07-20T18:20:15Z"},
        )
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError,
                    r"evidence\[3\]\.retrieved_at must equal the import retrieved_at",
                ):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(v4_name),
                        retrieved_at="2026-07-20T06:42:12Z",
                    )
            finally:
                connection.close()

    def test_direct_body_successors_are_exact_one_for_one_replacements(self) -> None:
        for v2_name, spec in DIRECT_SUCCESSORS.items():
            with self.subTest(source=v2_name):
                v1_path = self._path(spec["v1"])
                self.assertEqual(
                    hashlib.sha256(v1_path.read_bytes()).hexdigest(),
                    spec["v1_sha256"],
                )
                v1 = self._load(spec["v1"])
                v2 = self._load(v2_name)
                restored = copy.deepcopy(v2)

                for index, (before, after) in enumerate(
                    zip(v1["evidence"], v2["evidence"])
                ):
                    if index != spec["evidence_index"]:
                        self.assertEqual(after, before)
                        continue
                    self.assertEqual(
                        {
                            key: value
                            for key, value in after.items()
                            if key != "metadata"
                        },
                        {
                            key: value
                            for key, value in before.items()
                            if key != "metadata"
                        },
                    )
                    metadata = after["metadata"]
                    self.assertEqual(
                        set(metadata) - set(before["metadata"]),
                        DIRECT_CAPTURE_METADATA_KEYS,
                    )
                    self.assertEqual(
                        {
                            key
                            for key in set(metadata) & set(before["metadata"])
                            if metadata[key] != before["metadata"][key]
                        },
                        spec["metadata_replacements"],
                    )
                    for key in DIRECT_CAPTURE_METADATA_KEYS:
                        del restored["evidence"][index]["metadata"][key]
                    for key in spec["metadata_replacements"]:
                        restored["evidence"][index]["metadata"][key] = before[
                            "metadata"
                        ][key]

                latitude, longitude = spec["coordinates"]
                for entity in ("campus", "project"):
                    self.assertEqual(
                        v2[entity]["coordinates"],
                        {"latitude": latitude, "longitude": longitude},
                    )
                    self.assertEqual(v2[entity]["method"], "authoritative_site_plan")
                    restored[entity]["coordinates"] = v1[entity]["coordinates"]
                    restored[entity]["method"] = v1[entity]["method"]
                self.assertEqual(restored, v1)

        for name in (ORD_V1, ATL_V1):
            document = self._load(name)
            for entity in ("campus", "project"):
                self.assertIsNone(document[entity]["coordinates"])
                self.assertIsNone(document[entity]["geometry"])
                self.assertEqual(document[entity]["method"], "authoritative_locality")

    def test_accepted_selection_is_offline_reversible_and_idempotent(self) -> None:
        forward = self._state(ACCEPTED_SOURCES, repetitions=2)
        reverse = self._state(reversed(ACCEPTED_SOURCES))
        self.assertEqual(reverse, forward)
        self.assertEqual(
            {table: len(rows) for table, rows in forward.items()},
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

        snapshots = forward["entity_snapshots"]
        self.assertEqual(sum(row[3] is not None for row in snapshots), 7)
        self.assertEqual(
            sum(row[12] == "authoritative_site_plan" for row in snapshots), 7
        )
        self.assertEqual(
            sum(row[12] == "authoritative_locality" for row in snapshots), 5
        )

        entities = {row[2]: row for row in forward["entities"]}
        evidence_ids = {
            json.loads(row[12])["curated_record_key"]: row[0]
            for row in forward["evidence"]
        }
        vantage_project = entities[VANTAGE_PROJECT_KEY]
        self.assertEqual(vantage_project[3], evidence_ids[VANTAGE_PROJECT_EVIDENCE])
        project_snapshot = next(
            row for row in snapshots if row[1] == vantage_project[0]
        )
        self.assertIsNone(project_snapshot[3])
        self.assertIsNone(project_snapshot[4])
        self.assertEqual(project_snapshot[8], "2026-01-15")
        self.assertEqual(project_snapshot[12], "authoritative_locality")

        vantage_campus = entities[VANTAGE_CAMPUS_KEY]
        campus_snapshot = next(row for row in snapshots if row[1] == vantage_campus[0])
        self.assertEqual(
            (campus_snapshot[3], campus_snapshot[4]), (47.5020821, 8.7713397)
        )
        self.assertEqual(campus_snapshot[12], "authoritative_site_plan")

    def test_accepted_selection_imports_in_both_workspace_layouts(self) -> None:
        specs = [
            (str(self._path(name)), self._retrieved_at(name))
            for name in ACCEPTED_SOURCES
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

specs = {specs!r}
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for source, retrieved_at in specs:
                CuratedOfficialSourceAdapter().import_file(
                    connection, source, retrieved_at=retrieved_at
                )
        assert validate_database(connection) == []
        result = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "coordinates": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL AND longitude IS NOT NULL").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "locality": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE method = 'authoritative_locality'").fetchone()[0],
            "site_plan": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE method = 'authoritative_site_plan'").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
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
                        "coordinates": 7,
                        "entities": 12,
                        "evidence": 15,
                        "lifecycle": 6,
                        "locality": 5,
                        "site_plan": 7,
                        "snapshots": 12,
                        "workloads": 4,
                    },
                )


if __name__ == "__main__":
    unittest.main()
