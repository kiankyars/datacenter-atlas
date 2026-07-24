from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import importlib.util
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

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v2"
INCIDENT = (
    ROOT
    / "source_artifacts/site-coordinate-assessment-publication-incident-"
    "2026-07-21-v1"
)
TEMPORAL_INCIDENT = (
    ROOT
    / "source_artifacts/site-coordinate-assessment-temporal-incident-"
    "2026-07-21-v1"
)
V1 = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v1"
BUILDER = ROOT / "scripts/build_coordinate_assessment_2026_07_21_v2.py"
RECORDED_AT = "2026-07-21T09:51:13Z"

COHORT: dict[str, tuple[int, str]] = {
    "curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json": (
        6_583,
        "dc887d47d91abbd7e53da238414cf387263569cded4079a0db04f3881c4c2b56",
    ),
    "curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json": (
        6_687,
        "154ea1798c6926ac48d2528f0e2dbe5fd9651fa2b0f547b01e0e364acb13cb95",
    ),
    "curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json": (
        7_048,
        "0e976c4fd1e47bdd60495bbb1b9d98c0d9fc76b15d0aa7450b58088203a01b8f",
    ),
    "curated-official-2026-07-21-harch-dakhla-groundbreaking.json": (
        6_882,
        "15fd52022e98268ff7911dd6a013e5a22d0d6eeea5da411c670b271dbf44712e",
    ),
    "curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json": (
        5_334,
        "2ff597a72913f8650f7c4bfad476388972c087f4a92bb557900ab187ce56d5f5",
    ),
    "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json": (
        6_032,
        "aaf91ac612720e5aaaf66fcc13a5061701b4f95ee5cd4499485b347f9a3d314c",
    ),
    "curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json": (
        5_998,
        "d87b556c1dd1aa9f979eaf37dd4d432b8f90884564e08cc8c32f8f619df3724b",
    ),
    "curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json": (
        10_805,
        "1b43db6573bac2d62848abd8775a9542ca46e282a7057be7afc1353293c65763",
    ),
    "curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json": (
        10_968,
        "7858e23a565879feb9e5fd4254b9f793809735e5fdd3b96717bfb77f3f3ddc14",
    ),
    "curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json": (
        10_971,
        "3c1d13af526ff67b54af365252d25639352cca6608d6ca4e76a2f69a4b81624c",
    ),
    "curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json": (
        6_033,
        "5d8ffb54fbf33f9eead89b21f1d69f148f8f69ed1047a6adc8a160e24801a23c",
    ),
    "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json": (
        5_666,
        "1894b5625adfa95f03a4a3ba981fa0a5e28010ef1cfa0fe1e7ba858e9a877699",
    ),
    "curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json": (
        5_948,
        "04c1747343928095b9c2901c6ed95717766e8c6abce3e480d1157959791ab8c1",
    ),
}

SPECS: dict[str, dict[str, Any]] = {
    "lampa": {
        "predecessor": (
            "curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-scala-sscllp01-lampa-current-build-"
            "coordinate-v2.json"
        ),
        "coordinates": {"latitude": -33.29298, "longitude": -70.73915},
        "geometry": {"type": "Point", "coordinates": [-70.73915, -33.29298]},
        "evidence_key": (
            "chile-mma-simbio-scala-lampa-point-2152920300-captured-2026-07-21"
        ),
        "source_decimal_text": {
            "x": "-70.739149706490736",
            "y": "-33.292981624952226",
        },
        "project_name": "SCALA DATA CENTER CAMPUS",
        "expediente": 2_152_920_300,
        "decimal_places": 5,
        "uncertainty_m": 50,
        "sha256": "f5797adc6d6455b92164320fd80b0bff7556f4c29e8e53b82aac39df8908018b",
        "bytes": 10_846,
    },
    "huechuraba": {
        "predecessor": (
            "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build-"
            "coordinate-v2.json"
        ),
        "coordinates": {"latitude": -33.36636, "longitude": -70.67394},
        "geometry": {"type": "Point", "coordinates": [-70.67394, -33.36636]},
        "evidence_key": (
            "chile-mma-simbio-scala-huechuraba-point-2162968448-captured-"
            "2026-07-21"
        ),
        "source_decimal_text": {
            "x": "-70.673941427872251",
            "y": "-33.366357816565355",
        },
        "project_name": "Ampliación Data Center Campus Scala Huechuraba",
        "expediente": 2_162_968_448,
        "decimal_places": 5,
        "uncertainty_m": 50,
        "sha256": "78a289a28b0d09a5e2918cc16be747de3b3bea1a1a5616bf931e5bb480d9b948",
        "bytes": 10_625,
    },
    "fortaleza": {
        "predecessor": (
            "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json"
        ),
        "successor": (
            "curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build-"
            "coordinate-v2.json"
        ),
        "coordinates": {"latitude": -3.751509, "longitude": -38.458001},
        "geometry": {"type": "Point", "coordinates": [-38.458001, -3.751509]},
        "project_geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-38.458162, -3.753499],
                [-38.459020, -3.753223],
                [-38.457840, -3.749518],
                [-38.456983, -3.749794],
                [-38.458162, -3.753499],
            ]],
        },
        "evidence_key": "fortaleza-seuma-sforpf01-survey-plan-captured-2026-07-21",
        "decimal_places": 6,
        "uncertainty_m": 5,
        "sha256": "ee17cc76868b1481058779a090f263cbcae2ef178cdd88f4896b3b052e2caa62",
        "bytes": 11_862,
    },
}

UNRESOLVED_REASONS = {
    "curated:azerbaijan-undisclosed-new-data-center-site": (
        "official_source_withholds_city_district_address_and_parcel"
    ),
    "curated:firebird-ai-center-hrazdan-site": (
        "official_source_only_reports_near_hrazdan_without_site_identifier"
    ),
    "curated:green-mountain-fra-mainz-campus": (
        "no_deterministic_official_bridge_to_exact_osm_construction_polygon"
    ),
    "curated:harch-intelligence-dakhla-campus": (
        "operator_reports_50_hectare_dakhla_site_without_parcel_or_address"
    ),
    "curated:scala-smextp02-tepotzotlan-data-center": (
        "no_primary_site_specific_smextp02_address_or_parcel"
    ),
    "curated:scala-tambore-campus": (
        "official_addresses_do_not_disambiguate_the_four_project_site_cluster"
    ),
    "curated:scala-zona-franca-bogota-campus": (
        "no_official_or_open_site_specific_parcel_for_sbogzb01"
    ),
}

V2_FILES = {
    "README.md": (1_439, "d5523bc079ed642c26f6e133899834d4b5fcdaf83b22b2bd6e81e7f9148514e7"),
    "coordinate-observations.json": (2_952, "0d978d2eb01e920ca2ab357eb03339bc083eccf4764f7f5cf39d1710b9aa832a"),
    "disposition.json": (10_092, "c5dd0b7cad5b73ccf9010c3a98d0852de269e5f7f9f91d9b3ee469c3df754fde"),
    "manifest.json": (1_592, "5b2e8c6d4ea3638ffb75ed3f00b4cdf672c2aaca04fd8fc899a4633506b09024"),
    "manifest.sha256": (80, "44a4b539a784fd3fb8ff729762530b463d3fe7d148510f27aa35a6b4618c53bd"),
    "normalized-successors/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build-coordinate-v2.json": (11_862, "ee17cc76868b1481058779a090f263cbcae2ef178cdd88f4896b3b052e2caa62"),
    "normalized-successors/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build-coordinate-v2.json": (10_625, "78a289a28b0d09a5e2918cc16be747de3b3bea1a1a5616bf931e5bb480d9b948"),
    "normalized-successors/curated-official-2026-07-21-scala-sscllp01-lampa-current-build-coordinate-v2.json": (10_846, "f5797adc6d6455b92164320fd80b0bff7556f4c29e8e53b82aac39df8908018b"),
    "retrieval-inventory.json": (4_633, "076f66decce26688179c623e4379773d2c0b576c8635ac04bd7046d005dd175d"),
}

INCIDENT_FILES = {
    "README.md": (650, "6b75175ab40dc3e95e92012c1f1e6eb142aaa103eda7328ddc92fd002cfc553a"),
    "incident.json": (3_695, "d9b8a661c52f068469e97df4712b9b197d94c9da7803942650d97bc7b3886a6e"),
    "manifest.json": (560, "8128a6be3fb6fbe7d9d576e8445524590ff53542530fc499c5d40588cd0bed1d"),
    "manifest.sha256": (80, "55f5f60cb8cdf21ad8f623b1ec5dff4734543f0d34c18ea3efab73af89ae6236"),
}

TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "entity_snapshots",
    "administrative_assignments",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class CoordinateAssessmentV2Tests(unittest.TestCase):
    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

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
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in TABLES
        }

    def _build(
        self, paths: Iterable[Path], *, repeat: bool = False
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                paths = tuple(paths)
                with self._network_guard():
                    for path in paths:
                        CuratedOfficialSourceAdapterV11().import_file(
                            connection, path, recorded_at=RECORDED_AT
                        )
                    state = self._state(connection)
                    if repeat:
                        for path in paths:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection, path, recorded_at=RECORDED_AT
                            )
                            self.assertEqual(result.entities_created, 0)
                            self.assertEqual(result.evidence_created, 0)
                        self.assertEqual(self._state(connection), state)
                self.assertEqual(validate_database(connection), [])
                return state
            finally:
                connection.close()

    def _assert_frozen_bundle(
        self, root: Path, expected: dict[str, tuple[int, str]], tree_sha256: str
    ) -> None:
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o555)
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, set(expected))
        for relative, (size, digest) in expected.items():
            path = root / relative
            raw = path.read_bytes()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, relative)
            self.assertEqual(len(raw), size, relative)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, relative)
            if path.suffix == ".json":
                document = json.loads(raw)
                self.assertEqual(
                    raw,
                    (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode(),
                    relative,
                )
        for path in root.rglob("*"):
            if path.is_dir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o555)
        manifest = self._load(root / "manifest.json")
        self.assertEqual(manifest["tree_sha256"], tree_sha256)
        rows = manifest["files"]
        self.assertEqual(
            hashlib.sha256(
                (json.dumps(rows, indent=2, ensure_ascii=False) + "\n").encode()
            ).hexdigest(),
            tree_sha256,
        )
        self.assertEqual(
            (root / "manifest.sha256").read_text(),
            f"{expected['manifest.json'][1]}  manifest.json\n",
        )

    def test_frozen_manifests_direct_pins_and_artifact_only_scope(self) -> None:
        self._assert_frozen_bundle(
            ARTIFACT,
            V2_FILES,
            "d104bd68bdb7e3d9fec7d748f639cad51f96a8a3421c0378ba0d86e6e294a1ca",
        )
        self._assert_frozen_bundle(
            INCIDENT,
            INCIDENT_FILES,
            "dc80687ee6ec61cbc71fb31169ed568ab23ab6140de7d86688079861ca1835b8",
        )

        disposition = self._load(ARTIFACT / "disposition.json")
        self.assertEqual(disposition["integration"], "none")
        self.assertIsNone(disposition["accepted_seed_definition"])
        self.assertTrue(disposition["lineage"]["direct_curated_source_pins_only"])
        self.assertEqual(disposition["non_coordinate_claims_added"], [])
        rejected = {
            row["path"]: row["reason"]
            for row in disposition["lineage"]["rejected_as_lineage"]
        }
        self.assertEqual(
            rejected["sources/open-seed-2026-07-21-v68.json"],
            "rejected_future_recorded_at_metadata",
        )
        self.assertEqual(
            rejected["source_artifacts/site-coordinate-assessment-2026-07-21-v1"],
            "rejected_publication_identity_mutation_incident",
        )
        self.assertFalse(disposition["publication_integrity"]["v1_accepted"])

        rows = {Path(row["path"]).name: row for row in disposition["cohort"]["rows"]}
        self.assertEqual(set(rows), set(COHORT))
        for name, (size, digest) in COHORT.items():
            source = ROOT / "sources" / name
            self.assertEqual(source.stat().st_size, size)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            self.assertEqual((rows[name]["bytes"], rows[name]["sha256"]), (size, digest))

        for spec in SPECS.values():
            self.assertFalse((ROOT / "sources" / spec["successor"]).exists())
            needle = spec["successor"]
            for path in (ROOT / "sources").glob("open-seed-*.json"):
                self.assertNotIn(needle, path.read_text(encoding="utf-8"), path.name)

    def test_publication_incident_pins_v1_and_new_temporal_incident_rejects_v2(self) -> None:
        incident = self._load(INCIDENT / "incident.json")
        self.assertEqual(incident["acceptance"], "rejected")
        self.assertEqual(incident["integration"], "none")
        first = incident["observed_states"]["first_published"]
        current = incident["observed_states"]["current_preserved"]
        self.assertEqual(
            first["manifest_sha256"],
            "e973cced3b9c2de838738ba0c238b940131678793f1dc9964efd2af5c1df1d7a",
        )
        self.assertEqual(
            current["manifest_sha256"],
            "448bd1943fd4a3332f7afcaefd17e098e359b9ec4e360cbe5f323a020fac2ec7",
        )
        self.assertEqual(first["huechuraba_successor_bytes"], 10_623)
        self.assertEqual(current["huechuraba_successor_bytes"], 10_625)
        self.assertEqual(incident["exact_factual_delta"]["huechuraba_byte_delta"], 2)
        self.assertFalse(incident["exact_factual_delta"]["coordinate_or_geometry_delta"])
        self.assertFalse(incident["exact_factual_delta"]["non_coordinate_claim_delta"])
        self.assertFalse(incident["containment"]["v1_accepted"])
        self.assertEqual(
            hashlib.sha256((V1 / "manifest.json").read_bytes()).hexdigest(),
            current["manifest_sha256"],
        )
        self.assertEqual(
            self._load(V1 / "manifest.json")["tree_sha256"], current["tree_sha256"]
        )

        integrity = self._load(ARTIFACT / "disposition.json")["publication_integrity"]
        self.assertFalse(integrity["v1_accepted"])
        self.assertEqual(integrity["v1_first_manifest_sha256"], first["manifest_sha256"])
        self.assertEqual(integrity["v1_current_manifest_sha256"], current["manifest_sha256"])
        self.assertEqual(integrity["incident_manifest_sha256"], INCIDENT_FILES["manifest.json"][1])
        self.assertEqual(
            integrity["publication_contract"],
            "unique_sibling_stage_then_freeze_then_atomic_no_replace",
        )
        temporal = self._load(TEMPORAL_INCIDENT / "incident.json")
        self.assertEqual(temporal["acceptance"], "non_accepted")
        self.assertEqual(
            temporal["rejected_v2"]["manifest_sha256"], V2_FILES["manifest.json"][1]
        )
        self.assertEqual(
            temporal["invalid_temporal_metadata"]["v2_retrieved_at"],
            "2026-07-21T17:05:51Z",
        )
        self.assertIn(
            "never cure",
            temporal["invalid_temporal_metadata"]["passage_of_time_guardrail"],
        )

    def test_successor_delta_is_only_coordinates_geometry_evidence_and_method(self) -> None:
        disposition = self._load(ARTIFACT / "disposition.json")
        self.assertEqual(
            disposition["accepted"],
            {
                "campuses": 3,
                "projects": 3,
                "coordinate_rows": 6,
                "successors": disposition["accepted"]["successors"],
            },
        )
        for label, spec in SPECS.items():
            with self.subTest(site=label):
                predecessor = self._load(ROOT / "sources" / spec["predecessor"])
                successor_path = ARTIFACT / "normalized-successors" / spec["successor"]
                successor = self._load(successor_path)
                self.assertEqual(successor_path.stat().st_size, spec["bytes"])
                self.assertEqual(
                    hashlib.sha256(successor_path.read_bytes()).hexdigest(), spec["sha256"]
                )
                self.assertEqual(successor["schema_version"], predecessor["schema_version"])
                self.assertEqual(successor["evidence"][:-1], predecessor["evidence"])
                self.assertEqual(len(successor["evidence"]), len(predecessor["evidence"]) + 1)
                added = successor["evidence"][-1]
                self.assertEqual(added["key"], spec["evidence_key"])
                self.assertEqual(added["metadata"]["horizontal_uncertainty_m"], spec["uncertainty_m"])
                self.assertEqual(
                    added["metadata"]["stored_coordinate_decimal_places"],
                    spec["decimal_places"],
                )

                restored = copy.deepcopy(successor)
                restored["evidence"] = copy.deepcopy(predecessor["evidence"])
                for entity_name in ("campus", "project"):
                    before = predecessor[entity_name]
                    after = successor[entity_name]
                    changed = {
                        key
                        for key in set(before) | set(after)
                        if before.get(key) != after.get(key)
                    }
                    self.assertEqual(
                        changed, {"coordinates", "geometry", "evidence_key", "method"}
                    )
                    self.assertEqual(after["coordinates"], spec["coordinates"])
                    expected_geometry = (
                        spec.get("project_geometry", spec["geometry"])
                        if entity_name == "project"
                        else spec["geometry"]
                    )
                    self.assertEqual(after["geometry"], expected_geometry)
                    self.assertEqual(after["evidence_key"], spec["evidence_key"])
                    self.assertEqual(after["method"], "authoritative_site_plan")
                    for key in ("address", "as_of_date", "confidence", "roles"):
                        self.assertEqual(after[key], before[key])
                    for key in changed:
                        restored[entity_name][key] = copy.deepcopy(before[key])
                self.assertEqual(restored, predecessor)
                for section in (
                    "lifecycle",
                    "operating_models",
                    "workloads",
                    "capacities",
                ):
                    self.assertEqual(successor[section], predecessor[section], section)
                for claim in (
                    *successor["lifecycle"],
                    *successor["operating_models"],
                    *successor["workloads"],
                    *successor["capacities"],
                ):
                    self.assertNotEqual(claim["evidence_key"], spec["evidence_key"])
                self.assertTrue(
                    successor["project"]["stable_key"].startswith(
                        successor["campus"]["stable_key"] + ":"
                    )
                )

    def test_coordinate_provenance_precision_geometry_and_unresolved_partition(self) -> None:
        for label in ("lampa", "huechuraba"):
            spec = SPECS[label]
            document = self._load(ARTIFACT / "normalized-successors" / spec["successor"])
            evidence = document["evidence"][-1]
            metadata = evidence["metadata"]
            self.assertEqual(metadata["returned_expediente_id"], spec["expediente"])
            self.assertEqual(metadata["returned_project_name"], spec["project_name"])
            self.assertEqual(metadata["returned_geometry_decimal_text"], spec["source_decimal_text"])
            self.assertEqual(metadata["returned_spatial_reference_wkid"], 4326)
            self.assertEqual(metadata["returned_geometry_type"], "esriGeometryPoint")
            self.assertEqual(metadata["last_synchronization_as_reported"], "2026-03-05")
            self.assertIn("representative point", metadata["representative_point_scope"])
            self.assertEqual(document["campus"]["geometry"]["type"], "Point")
            self.assertEqual(document["project"]["geometry"]["type"], "Point")

        fortaleza = SPECS["fortaleza"]
        document = self._load(
            ARTIFACT / "normalized-successors" / fortaleza["successor"]
        )
        metadata = document["evidence"][-1]["metadata"]
        self.assertEqual(metadata["project_name_as_reported"], "PRAIA DO FUTURO - SFORPF01")
        self.assertEqual(metadata["plan_code_as_reported"], "SFORPF01-B-SCD-DC01-AR20-DE-0002")
        self.assertEqual(metadata["source_coordinate_reference_system"], "SIRGAS 2000 / UTM zone 24S (EPSG:31984)")
        self.assertEqual(
            metadata["source_boundary_vertices_xy_m"],
            [
                {"vertex": "P1", "x": "560165.382", "y": "9585100.992"},
                {"vertex": "P2", "x": "560070.156", "y": "9585131.517"},
                {"vertex": "P3", "x": "560201.416", "y": "9585540.994"},
                {"vertex": "P4", "x": "560296.643", "y": "9585510.468"},
            ],
        )
        self.assertEqual(metadata["source_crs_centroid_xy_m"], {"x": "560183.39925", "y": "9585320.99275"})
        self.assertEqual(
            metadata["transformation"]["unrounded_centroid"],
            {"latitude": "-3.751508763660", "longitude": "-38.458001391848"},
        )
        self.assertEqual(metadata["transformation"]["pyproj_version"], "3.7.2")
        self.assertEqual(metadata["transformation"]["proj_version"], "9.5.1")
        self.assertEqual(metadata["transformation"]["epsg_database_version"], "v11.022")
        ring = document["project"]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        x = document["campus"]["coordinates"]["longitude"]
        y = document["campus"]["coordinates"]["latitude"]
        inside = False
        for first, second in zip(ring, ring[1:]):
            x1, y1 = first
            x2, y2 = second
            if (y1 > y) != (y2 > y):
                crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < crossing:
                    inside = not inside
        self.assertTrue(inside)
        self.assertEqual(document["campus"]["geometry"]["type"], "Point")
        self.assertEqual(document["project"]["geometry"]["type"], "Polygon")

        disposition = self._load(ARTIFACT / "disposition.json")
        unresolved = {
            row["campus_key"]: row for row in disposition["unresolved"]["rows"]
        }
        self.assertEqual(disposition["unresolved"]["campuses"], 7)
        self.assertEqual(disposition["unresolved"]["projects"], 10)
        self.assertEqual({key: row["reason"] for key, row in unresolved.items()}, UNRESOLVED_REASONS)
        self.assertEqual(sum(len(row["project_keys"]) for row in unresolved.values()), 10)

        cohort_documents = [self._load(ROOT / "sources" / name) for name in COHORT]
        cohort_campuses = {document["campus"]["stable_key"] for document in cohort_documents}
        cohort_projects = {document["project"]["stable_key"] for document in cohort_documents}
        accepted = disposition["accepted"]["successors"]
        accepted_campuses = {row["campus_key"] for row in accepted.values()}
        accepted_projects = {row["project_key"] for row in accepted.values()}
        unresolved_projects = {
            project for row in unresolved.values() for project in row["project_keys"]
        }
        self.assertEqual(cohort_campuses, accepted_campuses | set(unresolved))
        self.assertEqual(cohort_projects, accepted_projects | unresolved_projects)
        self.assertTrue(accepted_campuses.isdisjoint(unresolved))
        self.assertTrue(accepted_projects.isdisjoint(unresolved_projects))

    def test_raw_capture_closure_is_hash_only(self) -> None:
        inventory = self._load(ARTIFACT / "retrieval-inventory.json")
        for key in (
            "raw_payloads_redistributed",
            "raw_response_bodies_retained_in_repository",
            "raw_response_headers_retained_in_repository",
            "raw_curl_writeouts_retained_in_repository",
        ):
            self.assertFalse(inventory[key])
        self.assertTrue(inventory["all_rights_reserved_raw_bytes_hash_only"])
        self.assertTrue(inventory["analysis_capture_directory_moved_intact_to_trash"])
        self.assertEqual(
            inventory["trash_recovery_path"],
            "/Users/kian/.Trash/datacenter-atlas-v68-coordinate-capture-20260721-1707Z-y0NdsP",
        )
        for request in inventory["accepted_capture_requests"]:
            for carrier in ("body", "headers", "curl_writeout"):
                self.assertFalse(request[carrier]["retained_in_repository"])
                self.assertRegex(request[carrier]["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(request[carrier]["bytes"], 0)
        self.assertEqual(
            {path.suffix for path in ARTIFACT.rglob("*") if path.is_file()},
            {".md", ".json", ".sha256"},
        )

    def test_v2_simbio_successors_fail_honest_temporal_gate_before_any_write(
        self,
    ) -> None:
        for label, spec in SPECS.items():
            path = ARTIFACT / "normalized-successors" / spec["successor"]
            with self.subTest(source=path.name):
                with tempfile.TemporaryDirectory() as temporary:
                    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                    try:
                        with self._network_guard():
                            if label == "fortaleza":
                                CuratedOfficialSourceAdapterV11().import_file(
                                    connection, path, recorded_at=RECORDED_AT
                                )
                            else:
                                with self.assertRaisesRegex(
                                    ValueError,
                                    r"evidence\[1\]\.retrieved_at must not be later than the import recorded_at",
                                ):
                                    CuratedOfficialSourceAdapterV11().import_file(
                                        connection, path, recorded_at=RECORDED_AT
                                    )
                        if label == "fortaleza":
                            self.assertEqual(validate_database(connection), [])
                            self.assertEqual(
                                connection.execute(
                                    "SELECT COUNT(*) FROM entities"
                                ).fetchone()[0],
                                2,
                            )
                        else:
                            for table in TABLES:
                                self.assertEqual(
                                    connection.execute(
                                        f"SELECT COUNT(*) FROM {table}"
                                    ).fetchone()[0],
                                    0,
                                    table,
                                )
                    finally:
                        connection.close()

    def test_v2_rejection_is_independent_of_predecessor_coexistence(self) -> None:
        for label, spec in SPECS.items():
            predecessor = ROOT / "sources" / spec["predecessor"]
            successor = ARTIFACT / "normalized-successors" / spec["successor"]
            with self.subTest(site=label):
                with tempfile.TemporaryDirectory() as temporary:
                    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                    try:
                        with self._network_guard():
                            CuratedOfficialSourceAdapterV11().import_file(
                                connection, predecessor, recorded_at=RECORDED_AT
                            )
                            before = self._state(connection)
                            expected_error = (
                                "entity_snapshots already has a claim"
                                if label == "fortaleza"
                                else r"evidence\[1\]\.retrieved_at must not be later than the import recorded_at"
                            )
                            with self.assertRaisesRegex(ValueError, expected_error):
                                CuratedOfficialSourceAdapterV11().import_file(
                                    connection, successor, recorded_at=RECORDED_AT
                                )
                        self.assertEqual(self._state(connection), before)
                        self.assertEqual(validate_database(connection), [])
                    finally:
                        connection.close()

    def test_builder_is_read_only_idempotent_and_refuses_collisions(self) -> None:
        before = {
            path.relative_to(ROOT).as_posix(): (path.read_bytes(), path.stat().st_mode)
            for bundle in (V1, INCIDENT, ARTIFACT)
            for path in bundle.rglob("*")
            if path.is_file()
        }
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"assessment": "existing-identical", "incident": "existing-identical"},
        )
        after = {
            path.relative_to(ROOT).as_posix(): (path.read_bytes(), path.stat().st_mode)
            for bundle in (V1, INCIDENT, ARTIFACT)
            for path in bundle.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

        scripts = str(BUILDER.parent)
        sys.path.insert(0, scripts)
        try:
            module_spec = importlib.util.spec_from_file_location(
                "coordinate_assessment_v2_builder_test", BUILDER
            )
            assert module_spec is not None and module_spec.loader is not None
            module = importlib.util.module_from_spec(module_spec)
            module_spec.loader.exec_module(module)
        finally:
            sys.path.remove(scripts)
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            publication_root = Path(temporary)
            self.assertEqual(
                module.publish_all(publication_root),
                {"incident": "published", "assessment": "published"},
            )
            self.assertEqual(
                module.publish_all(publication_root),
                {"incident": "existing-identical", "assessment": "existing-identical"},
            )

        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            collision = Path(temporary) / module.ARTIFACT_ID
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_bytes(b"do-not-overwrite\n")
            with self.assertRaisesRegex(module.PublicationError, "file set mismatch"):
                module._publish(collision, module._v2_payloads(INCIDENT_FILES["manifest.json"][1]))
            self.assertEqual(sentinel.read_bytes(), b"do-not-overwrite\n")


if __name__ == "__main__":
    unittest.main()
