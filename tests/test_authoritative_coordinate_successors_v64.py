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
from typing import Any
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas.curated_v11 import (
        CuratedOfficialSourceAdapterV11,
    )
    from datacenter_atlas.datacenter_atlas.database import initialize
    from datacenter_atlas.datacenter_atlas.service import validate_database
except ModuleNotFoundError:
    from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
    from datacenter_atlas.database import initialize
    from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RECORDED_AT = "2026-07-21T06:40:00Z"
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "authoritative-coordinate-successors-v64-2026-07-20-v1"
)

V64 = (
    "open-seed-2026-07-20-v64.json",
    79_698,
    "d398dfd242fe58863998ea45e10d35de0020c7f6b4fd6bc31af19980d871ec7e",
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "coresite": {
        "v1": "curated-official-2026-07-20-coresite-de3-denver.json",
        "v1_bytes": 35_669,
        "v1_sha256": (
            "8bfb0b31e468647753a142e9fc0ba3306e06e8272b02e6fbe848809a3bd69868"
        ),
        "successor": "curated-official-2026-07-20-coresite-de3-denver-v2.json",
        "successor_bytes": 52_842,
        "successor_sha256": (
            "9d0727dcbb8ed42b55887012d0d267188e4561d67f4694dd49ce2e834ed64ab2"
        ),
        "schema_changed": True,
        "point": (39.7861942431606, -104.96277124667975),
        "geometry_type": "Polygon",
        "method": "authoritative_site_plan",
        "evidence_key": (
            "denver-coresite-de3-tax-parcel-captured-2026-07-20"
        ),
        "appended": (
            "denver-coresite-de3-tax-parcel-captured-2026-07-20",
        ),
        "changed": {
            "campus": {"coordinates", "geometry", "evidence_key", "method"},
            "project": {"coordinates", "geometry", "evidence_key", "method"},
        },
    },
    "powerhouse": {
        "v1": (
            "curated-official-2026-07-20-powerhouse-irving-building-1-topout.json"
        ),
        "v1_bytes": 21_449,
        "v1_sha256": (
            "03e3c1de817fba2a0b14d42ec5d063caf07ac23df4083b22bd0a99f6803d0990"
        ),
        "successor": (
            "curated-official-2026-07-20-powerhouse-irving-building-1-topout-v2.json"
        ),
        "successor_bytes": 33_671,
        "successor_sha256": (
            "48ea1c56e18fbf0d7f69be51e4892f60e5871ca5540f19e3eb21040205217ce3"
        ),
        "schema_changed": False,
        "point": (32.888545840931, -96.9410613460374),
        "geometry_type": "Point",
        "method": "authoritative_address_geocode",
        "evidence_key": (
            "irving-powerhouse-permit-2025-02-1125-captured-2026-07-20"
        ),
        "appended": (
            "irving-powerhouse-permit-2025-02-1125-captured-2026-07-20",
            "irving-site-address-4324801-captured-2026-07-20",
        ),
        "changed": {
            "campus": {"coordinates", "geometry", "evidence_key", "method"},
            "project": {
                "coordinates",
                "geometry",
                "evidence_key",
                "as_of_date",
                "method",
            },
        },
    },
    "edged": {
        "v1": "curated-official-2026-07-20-edged-ord01-2-chicago-topout.json",
        "v1_bytes": 17_750,
        "v1_sha256": (
            "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c"
        ),
        "successor": (
            "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v3.json"
        ),
        "successor_bytes": 24_589,
        "successor_sha256": (
            "a61e7d4f4c4374a99b62b52980903c94e7b8c2659a8470045530fbc2cb55fe4e"
        ),
        "schema_changed": True,
        "point": (41.806967678, -88.240996871),
        "geometry_type": "Point",
        "method": "authoritative_address_geocode",
        "evidence_key": (
            "aurora-edged-chicago-address-point-85050-captured-2026-07-20"
        ),
        "appended": (
            "aurora-edged-chicago-address-point-85050-captured-2026-07-20",
        ),
        "changed": {
            "campus": {"coordinates", "geometry", "evidence_key", "method"},
            "project": {"coordinates", "geometry", "evidence_key", "method"},
        },
    },
    "dalton4": {
        "v1": "curated-official-2026-07-20-core-scientific-dalton-4.json",
        "v1_bytes": 19_614,
        "v1_sha256": (
            "ed121928047032b1740d7f6e30faa0fad7304cb6b5144c1b708812300ebe9a09"
        ),
        "successor": (
            "curated-official-2026-07-20-core-scientific-dalton-4-v2.json"
        ),
        "successor_bytes": 31_322,
        "successor_sha256": (
            "55fcb118be1a5380f2ec49ccb56b557fc35deedd3cdfcadef727df3b3bf98733"
        ),
        "schema_changed": False,
        "point": (34.6948095438794, -84.941093728219),
        "geometry_type": "Point",
        "method": "authoritative_address_geocode",
        "evidence_key": (
            "whitfield-1199-enterprise-address-point-captured-2026-07-20"
        ),
        "appended": (
            "ga-epd-dalton4-application-29951-advisory-captured-2026-07-20",
            "whitfield-1199-enterprise-address-point-captured-2026-07-20",
        ),
        "changed": {
            "campus": {
                "coordinates",
                "geometry",
                "evidence_key",
                "as_of_date",
                "method",
            },
            "project": {
                "coordinates",
                "geometry",
                "evidence_key",
                "as_of_date",
                "method",
            },
        },
    },
}

EDGED_REJECTED_V2 = (
    "curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json",
    21_279,
    "03fa4a5915a43d70456b63ab54c2b7c8eb9bdf918ffc10c938276a4da90db368",
)

ARTIFACT_FILE_SPECS = {
    "README.md": (
        1_805,
        "75b2e1546aa6d76bb85f68dcfcdc4e098112f9b47697e7f1d6adf38a3e6b3428",
    ),
    "disposition.json": (
        6_734,
        "696ae6c2dfe2bb0133d055cb517957a4a2e3341b60b77ef3bfb56a6648ca0968",
    ),
    "manifest.json": (
        705,
        "ddcf876b522bb8941296d86c8830f72a29c1959c22cb38067bd5c20f724424bd",
    ),
    "manifest.sha256": (
        80,
        "1ab304d093c24b8d856fc01142269508f33721a5aff7462176b4db252b54dd9d",
    ),
    "retrieval-inventory.json": (
        18_054,
        "6549848da837730a6af7306c879f8f08b3b4db3296bbb17b4e9b14ef2699de32",
    ),
}

CAPTURE_PINS = {
    "denver_parcel": (
        3_919,
        "41387d3d2d09af9e88e494d24f29ccc6897f25b0b077edf5f9011a470de0c7e2",
        1_118,
        "fcc46caa6d9c1693f648395d3a81be9cfb7d1489521c64475a78eb372db2f719",
        12_647,
        "073fc0fd71d0c126f6ed1cc9bbde919f3cce4d3a6c501e4a659f6b3367e2bed9",
    ),
    "denver_rights": (
        158_115,
        "dd38845675c959b61e56f6e58e1bf7c967e6279793d7561d7d40af010a442d13",
        1_053,
        "7989f91b9b648636537b20b02d1832b527798f70ed2a1b99f82addd2ad4f866a",
        27_193,
        "f6aac63cee8cf3b1d2adb05a72a08d411229cd3ff0e2997875d0c1e107d8d411",
    ),
    "irving_permit": (
        582,
        "c01d04e1303c2c66df6449656f0cc102d487bcb9c5564b58d8a3ddce405ebb0d",
        1_156,
        "f6ca4dcc3a222ac6cf54ae068aaa422e9d7dc0458ff2de06147669d4a0873d6e",
        12_494,
        "5cf75c3fe508367bd69ad5b3973847b8d56281a2eee880e1ac54e4991797853c",
    ),
    "irving_address": (
        359,
        "5713981c26c61f9571361e35e0f29461eaa51d8e60a75df9f6999c056540d10e",
        1_154,
        "4899f9534a5aa56d52a223349c22aedb194cc2ff60cc9f9bf6b9402cc65c23f1",
        12_262,
        "b0891c68596c96502af832e7adb9a391deae389707e109ad705ca7a0d7aa0448",
    ),
    "aurora_address": (
        426,
        "8db6b8217609665b4b58ab8ade5e5bb0a252321f056a1e80d6203533d837a84a",
        1_158,
        "d0783cf4a5ffb9a72bd129abd417b09c5377e2f9a5f676b168de11ce6e489324",
        12_390,
        "d375bc28d8a41fc4584528e22b1429014b3f53920186a614f2c30dcf1a6463a1",
    ),
    "aurora_public_domain": (
        2_080,
        "172afdc84cbd96063c3bb410889ae69889d05e4fab2a84f23f1ab1783ce1a347",
        491,
        "64c5dbf46cb4bc6972b2eeb5e7e1f76913df9576bd6f3b9604503687045a7b76",
        14_545,
        "936d5ab187eec2850d1ad5d6c897be2abd5ba0e179a706d8e8da5dd5edab973c",
    ),
    "ga_epd_advisory": (
        104_495,
        "2f292f0c5b03dedfcd3beaba324875f247b487bbe2a5267d82b30888b5bd49a9",
        1_027,
        "5ff944aafe8d704a4c9a42bf4fc9e03d46117f193d4040b3d8886d198c792c9f",
        9_566,
        "9434c4c85424a86dca8ae1fc0eb91c7bae7a360fe6138e65a94190a6001f651d",
    ),
    "whitfield_address": (
        346,
        "add0b6ce576afa5b0de6e6a23ee7990d64ae19b805414106b938baefdfd3f5a9",
        559,
        "77067c16e7b014d8da445cbf65cee6913977b42385a2ecaf6d4db454825e2963",
        16_034,
        "c35e5f9da8da6d5ea5d225ad82c960c96b82433e46b9771cd195334211b73cf5",
    ),
    "whitfield_disclaimer": (
        3_442,
        "c562307d57768eef89836eb22c7f19a572b8d2bbb2781da898f45b6d5a810fef",
        245,
        "e212567f6683d0bdec7babea04bf12f2b791bcdee68799b7326537fc1ebd9a4d",
        14_943,
        "1725fc5ad554568a1991a5190ece54a4c6a6239f6887a2f950a3b8849c483f7f",
    ),
}

TABLES = (
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


class AuthoritativeCoordinateSuccessorsV64Tests(unittest.TestCase):
    def _source(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_canonical_source(
        self, name: str, *, size: int, sha256: str
    ) -> dict[str, Any]:
        path = self._source(name)
        self.assertTrue(path.is_file())
        self.assertFalse(path.is_symlink())
        self.assertTrue(stat.S_ISREG(path.stat().st_mode))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        raw = path.read_bytes()
        self.assertEqual(len(raw), size)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), sha256)
        document = json.loads(raw)
        self.assertEqual(
            raw.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        return document

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("coordinate-successor import attempted network access")
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
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in TABLES
        }

    def _build(
        self, names: tuple[str, ...], *, repeat: bool
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for name in names:
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            self._source(name),
                            recorded_at=RECORDED_AT,
                        )
                        self.assertEqual(result.entities_created, 2)
                        self.assertEqual(result.warnings, ())
                    state = self._state(connection)
                    if repeat:
                        for name in names:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection,
                                self._source(name),
                                recorded_at=RECORDED_AT,
                            )
                            self.assertEqual(result.entities_created, 0)
                            self.assertEqual(result.evidence_created, 0)
                            self.assertEqual(result.warnings, ())
                        self.assertEqual(self._state(connection), state)
                self.assertEqual(validate_database(connection), [])
                return state
            finally:
                connection.close()

    def _point_in_ring(
        self, longitude: float, latitude: float, ring: list[list[float]]
    ) -> bool:
        inside = False
        previous = ring[-1]
        for current in ring:
            x1, y1 = previous
            x2, y2 = current
            crosses = (y1 > latitude) != (y2 > latitude)
            if crosses:
                crossing_x = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
                if longitude < crossing_x:
                    inside = not inside
            previous = current
        return inside

    def _orientation(
        self, first: list[float], second: list[float], third: list[float]
    ) -> float:
        return (second[0] - first[0]) * (third[1] - first[1]) - (
            second[1] - first[1]
        ) * (third[0] - first[0])

    def _segments_cross(
        self,
        first_a: list[float],
        first_b: list[float],
        second_a: list[float],
        second_b: list[float],
    ) -> bool:
        first = self._orientation(first_a, first_b, second_a)
        second = self._orientation(first_a, first_b, second_b)
        third = self._orientation(second_a, second_b, first_a)
        fourth = self._orientation(second_a, second_b, first_b)
        return first * second < 0 and third * fourth < 0

    def test_exact_full_file_delta_v64_selection_and_rejected_v2(self) -> None:
        definition = self._assert_canonical_source(
            V64[0], size=V64[1], sha256=V64[2]
        )
        selected = {
            row["path"]: row["sha256"] for row in definition["curated_inputs"]
        }
        for label, spec in SOURCE_SPECS.items():
            with self.subTest(site=label):
                predecessor = self._assert_canonical_source(
                    spec["v1"], size=spec["v1_bytes"], sha256=spec["v1_sha256"]
                )
                successor = self._assert_canonical_source(
                    spec["successor"],
                    size=spec["successor_bytes"],
                    sha256=spec["successor_sha256"],
                )
                self.assertEqual(
                    selected[f"sources/{spec['v1']}"], spec["v1_sha256"]
                )
                self.assertNotIn(f"sources/{spec['successor']}", selected)
                self.assertEqual(successor["schema_version"], "1.1")
                self.assertEqual(
                    predecessor["schema_version"] != successor["schema_version"],
                    spec["schema_changed"],
                )
                inherited_count = len(predecessor["evidence"])
                self.assertEqual(
                    successor["evidence"][:inherited_count],
                    predecessor["evidence"],
                )
                self.assertEqual(
                    tuple(
                        row["key"]
                        for row in successor["evidence"][inherited_count:]
                    ),
                    spec["appended"],
                )
                for section in (
                    "lifecycle",
                    "operating_models",
                    "workloads",
                    "capacities",
                ):
                    self.assertEqual(successor[section], predecessor[section], section)
                for entity_name in ("campus", "project"):
                    before = predecessor[entity_name]
                    after = successor[entity_name]
                    changed = {
                        key for key in before if before[key] != after[key]
                    }
                    self.assertEqual(changed, spec["changed"][entity_name])
                    latitude, longitude = spec["point"]
                    self.assertEqual(
                        after["coordinates"],
                        {"latitude": latitude, "longitude": longitude},
                    )
                    self.assertEqual(after["geometry"]["type"], spec["geometry_type"])
                    self.assertEqual(after["evidence_key"], spec["evidence_key"])
                    self.assertEqual(after["as_of_date"], "2026-07-20")
                    self.assertEqual(after["method"], spec["method"])
                    self.assertEqual(after["address"], before["address"])
                    self.assertEqual(after["roles"], before["roles"])

                restored = copy.deepcopy(successor)
                restored["schema_version"] = predecessor["schema_version"]
                restored["evidence"] = copy.deepcopy(predecessor["evidence"])
                restored["campus"] = copy.deepcopy(predecessor["campus"])
                restored["project"] = copy.deepcopy(predecessor["project"])
                self.assertEqual(restored, predecessor)

        rejected = self._assert_canonical_source(
            EDGED_REJECTED_V2[0],
            size=EDGED_REJECTED_V2[1],
            sha256=EDGED_REJECTED_V2[2],
        )
        self.assertNotIn(f"sources/{EDGED_REJECTED_V2[0]}", selected)
        self.assertEqual(
            rejected["campus"]["coordinates"],
            {"latitude": 41.8079909, "longitude": -88.2419971},
        )
        disposition = self._load(ARTIFACT / "disposition.json")
        self.assertEqual(
            disposition["rejected_nonpromotions"],
            [
                {
                    "path": f"sources/{EDGED_REJECTED_V2[0]}",
                    "bytes": EDGED_REJECTED_V2[1],
                    "sha256": EDGED_REJECTED_V2[2],
                    "disposition": (
                        "rejected_nonpromotion_google_maps_derived_coordinate"
                    ),
                }
            ],
        )

    def test_exact_stable_ids_coordinate_scope_and_topology(self) -> None:
        documents = {
            label: self._load(self._source(spec["successor"]))
            for label, spec in SOURCE_SPECS.items()
        }

        coresite = {
            row["key"]: row for row in documents["coresite"]["evidence"]
        }
        parcel = coresite[
            "denver-coresite-de3-tax-parcel-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(parcel["returned_feature_count"], 1)
        self.assertEqual(parcel["returned_object_id"], 1_231_023)
        self.assertEqual(parcel["returned_schedule_number"], "0214400131000")
        self.assertEqual(parcel["returned_situs_address_id"], 23_973)
        self.assertEqual(parcel["returned_owner_name"], "CORESITE REAL ESTATE DE3 LLC")
        self.assertEqual(parcel["geometry_label"], "de3_tax_parcel_boundary")
        self.assertTrue(parcel["topology_validation"]["is_valid"])
        self.assertTrue(parcel["topology_validation"]["is_simple"])
        self.assertIn("city-owned", parcel["sliver_exclusion_guardrail"])
        polygon = documents["coresite"]["campus"]["geometry"]
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    polygon, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest(),
            "7dfc83d83c26a99cb935a0022e2310a3249d02db2a7737675050936072d84914",
        )
        ring = polygon["coordinates"][0]
        self.assertEqual(len(ring), 53)
        self.assertEqual(ring[0], ring[-1])
        latitude, longitude = SOURCE_SPECS["coresite"]["point"]
        self.assertTrue(self._point_in_ring(longitude, latitude, ring))
        segment_count = len(ring) - 1
        for first_index in range(segment_count):
            for second_index in range(first_index + 1, segment_count):
                if abs(first_index - second_index) <= 1:
                    continue
                if first_index == 0 and second_index == segment_count - 1:
                    continue
                self.assertFalse(
                    self._segments_cross(
                        ring[first_index],
                        ring[first_index + 1],
                        ring[second_index],
                        ring[second_index + 1],
                    ),
                    (first_index, second_index),
                )
        self.assertEqual(documents["coresite"]["project"]["geometry"], polygon)

        powerhouse = {
            row["key"]: row for row in documents["powerhouse"]["evidence"]
        }
        permit = powerhouse[
            "irving-powerhouse-permit-2025-02-1125-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(permit["returned_feature_count"], 1)
        self.assertEqual(permit["returned_object_id"], 658)
        self.assertEqual(permit["returned_permit"], "2025-02-1125")
        self.assertEqual(
            permit["returned_global_id"],
            "2581c8c2-7038-463b-b2e4-f6df2b86cd2f",
        )
        self.assertEqual(permit["returned_status"], "UNDER CONSTRUCTION")
        self.assertIn("metadata only", permit["status_nonpromotion_guardrail"])
        address = powerhouse[
            "irving-site-address-4324801-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(address["returned_feature_count"], 1)
        self.assertEqual(address["returned_object_id"], 5_827)
        self.assertEqual(address["returned_site_address_id"], "4324801")
        self.assertEqual(address["returned_address_point_key"], "4324801")
        self.assertIn("not a parcel", address["geometry_guardrail"])

        edged = {row["key"]: row for row in documents["edged"]["evidence"]}
        aurora = edged[
            "aurora-edged-chicago-address-point-85050-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(aurora["returned_feature_count"], 1)
        self.assertEqual(aurora["returned_object_id"], 166_456_816)
        self.assertEqual(aurora["returned_location_id"], 85_050)
        self.assertEqual(aurora["returned_pin"], "07-05-105-006")
        self.assertEqual(aurora["returned_owner_name"], "EDGED CHICAGO LLC")
        self.assertEqual(aurora["geometry_scope"], "campus_address_point")
        self.assertIn("not an ORD01-2 building centroid", aurora["coordinate_scope"])
        self.assertIn("Google Maps-derived v2", aurora["excluded_source_guardrail"])

        dalton = {
            row["key"]: row for row in documents["dalton4"]["evidence"]
        }
        epd = dalton[
            "ga-epd-dalton4-application-29951-advisory-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(epd["reported_application_number"], 29_951)
        self.assertEqual(
            epd["reported_facility_name"],
            "Core Scientific-Dalton 4 Enterprise Drive",
        )
        self.assertEqual(
            epd["draft_permit_retrieval_incident_id"],
            "ga_epd_draft_unpublished",
        )
        whitfield = dalton[
            "whitfield-1199-enterprise-address-point-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(whitfield["returned_feature_count"], 1)
        self.assertEqual(whitfield["returned_object_id"], 226_055)
        self.assertEqual(whitfield["returned_house_number"], 1_199)
        self.assertEqual(whitfield["returned_street"], "ENTERPRISE DR")
        self.assertEqual(
            whitfield["canonical_address"],
            "3024 Old Tilton Road, Dalton, Georgia, United States",
        )
        self.assertEqual(
            whitfield["official_address_alias"],
            "1199 Enterprise Drive, Dalton, Georgia 30721, United States",
        )
        self.assertIn("not a parcel", whitfield["coordinate_scope"])
        for entity_name in ("campus", "project"):
            self.assertEqual(
                documents["dalton4"][entity_name]["address"],
                "3024 Old Tilton Road, Dalton, Georgia, United States",
            )

    def test_frozen_hash_only_artifact_and_technical_incident(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_sha256) in ARTIFACT_FILE_SPECS.items():
            with self.subTest(artifact_file=name):
                path = ARTIFACT / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                data = path.read_bytes()
                self.assertEqual(len(data), expected_bytes)
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected_sha256)

        manifest = self._load(ARTIFACT / "manifest.json")
        manifest_hash = ARTIFACT_FILE_SPECS["manifest.json"][1]
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{manifest_hash}  manifest.json\n",
        )
        for row in manifest["files"]:
            data = (ARTIFACT / row["path"]).read_bytes()
            self.assertEqual(len(data), row["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
        tree_payload = json.dumps(
            manifest["files"], indent=2, sort_keys=True
        ) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )
        self.assertEqual(
            manifest["tree_sha256"],
            "f99ff1a0b1a4622a29bebee7561aebc49828e6d879a9f0713e71374cbc89c4fd",
        )

        inventory = self._load(ARTIFACT / "retrieval-inventory.json")
        self.assertTrue(inventory["analysis_temporary_response_bodies_deleted"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertFalse(inventory["raw_response_headers_retained"])
        self.assertFalse(inventory["raw_curl_writeouts_retained"])
        self.assertFalse(inventory["raw_payloads_redistributed"])
        self.assertEqual(inventory["direct_request_attempts"], 10)
        self.assertEqual(inventory["successful_response_requests"], 9)
        self.assertEqual(inventory["technical_incidents"], 1)
        rows = {
            row["request_id"]: row
            for row in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(rows), {*CAPTURE_PINS, "ga_epd_draft_unpublished"})
        for request_id, pins in CAPTURE_PINS.items():
            with self.subTest(capture=request_id):
                row = rows[request_id]
                self.assertEqual(
                    (row["body"]["bytes"], row["body"]["sha256"]), pins[0:2]
                )
                self.assertEqual(
                    (row["headers"]["bytes"], row["headers"]["sha256"]),
                    pins[2:4],
                )
                self.assertEqual(
                    (
                        row["curl_writeout"]["bytes"],
                        row["curl_writeout"]["sha256"],
                    ),
                    pins[4:6],
                )
                self.assertFalse(row["body"]["retained"])
                self.assertFalse(row["headers"]["retained"])
                self.assertFalse(row["curl_writeout"]["retained"])
                self.assertFalse(row["request_credentials_supplied"])
                self.assertFalse(row["request_cookie_input_supplied"])
                self.assertFalse(row["response_cookies_persisted_or_reused"])

        failed = rows["ga_epd_draft_unpublished"]
        self.assertEqual(failed["http_status"], 403)
        self.assertEqual(
            failed["disposition"],
            "technical_incident_unpublished_no_evidence",
        )
        self.assertIsNone(failed["evidence_key"])
        self.assertIsNone(failed["body"]["bytes"])
        self.assertIsNone(failed["body"]["sha256"])
        all_evidence_keys = {
            row["key"]
            for spec in SOURCE_SPECS.values()
            for row in self._load(self._source(spec["successor"]))["evidence"]
        }
        self.assertNotIn("ga_epd_draft_unpublished", all_evidence_keys)
        irving_reference = inventory["reference_only_urls"][0]
        self.assertIsNone(irving_reference["body_bytes"])
        self.assertIsNone(irving_reference["body_sha256"])

        forbidden_keys = {
            "authorization",
            "certs",
            "conn_id",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(inventory)

    def test_offline_import_is_valid_idempotent_and_order_invariant(self) -> None:
        names = tuple(spec["successor"] for spec in SOURCE_SPECS.values())
        forward = self._build(names, repeat=True)
        reverse = self._build(tuple(reversed(names)), repeat=False)
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward["entities"]), 8)
        self.assertEqual(len(forward["campuses"]), 4)
        self.assertEqual(len(forward["projects"]), 4)
        self.assertEqual(len(forward["evidence"]), 18)
        self.assertEqual(len(forward["lifecycle_observations"]), 4)
        self.assertEqual(len(forward["capacity_estimates"]), 7)
        self.assertEqual(len(forward["operating_model_observations"]), 2)
        self.assertEqual(len(forward["workload_observations"]), 3)

    def test_builder_is_idempotent_and_imports_from_both_roots(self) -> None:
        builder = ROOT / "scripts/build_authoritative_coordinate_successors_v64.py"
        before = {
            name: hashlib.sha256(self._source(name).read_bytes()).hexdigest()
            for name in (spec["successor"] for spec in SOURCE_SPECS.values())
        }
        artifact_before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in ARTIFACT.iterdir()
            if path.is_file()
        }
        result = subprocess.run(
            [sys.executable, str(builder)],
            cwd=WORKSPACE,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            before,
            {
                name: hashlib.sha256(self._source(name).read_bytes()).hexdigest()
                for name in before
            },
        )
        self.assertEqual(
            artifact_before,
            {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in ARTIFACT.iterdir()
                if path.is_file()
            },
        )

        names = tuple(spec["successor"] for spec in SOURCE_SPECS.values())
        script = f"""
from pathlib import Path
from tempfile import TemporaryDirectory
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database
root = Path({str(ROOT)!r})
names = {names!r}
with TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    for name in names:
        CuratedOfficialSourceAdapterV11().import_file(
            connection,
            root / "sources" / name,
            recorded_at={RECORDED_AT!r},
        )
    assert validate_database(connection) == []
    connection.close()
print("ok")
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        for cwd in (WORKSPACE, ROOT):
            with self.subTest(cwd=cwd):
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
