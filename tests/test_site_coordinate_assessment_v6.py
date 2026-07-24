from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.open_seed_v69 import tree_digest
from datacenter_atlas.service import validate_database


try:
    builder = importlib.import_module(
        "datacenter_atlas.datacenter_atlas.site_coordinate_assessment_v6"
    )
except ModuleNotFoundError:
    builder = importlib.import_module("datacenter_atlas.site_coordinate_assessment_v6")


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = ROOT / "source_artifacts/site-coordinate-assessment-2026-07-21-v6"
PUBLISHER = ROOT / "scripts/publish_coordinate_assessment_2026_07_21_v6.py"
TEST_RECORDED_AT = "2026-07-21T20:00:00Z"

RECORDED_AT: str | None = "2026-07-21T19:41:03Z"
MANIFEST_SHA256: str | None = (
    "d44713078f9cf879e250d3696aaff59d702eaa1f4e8c77ec066b6b2dbc7dfd36"
)
MANIFEST_TREE_SHA256: str | None = (
    "838c968ba9a31dd1399798b00ef63ee1b231d059a6d6b1ced74dea9f4199a616"
)
PHYSICAL_TREE_SHA256: str | None = (
    "905ec4fb87f92106edfea595723a35507cddf654bc00cc60e1a4d50e46ce1ba0"
)
FILES: dict[str, tuple[int, str]] = {
    "README.md": (
        2_280,
        "8005a293f7d00edac0bd21d6380b1e45ccaa4922c31931e5e30378e058336c6d",
    ),
    "coordinate-observations.json": (
        10_315,
        "1ea54a04543472c171faf5c04c6aa4bbe33b35f06a7a7ace50dd0cb2ff88df09",
    ),
    "disposition.json": (
        14_988,
        "c6cc7fd363fcd68a3dc230e62838b9320dc44012e753ed71f58887ea8f63014b",
    ),
    "manifest.json": (3_013, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "ee4ca239d0ff4c48b07cca5f233f5b8ba24d53c51f76ff1f7797e395510e6390",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-airtrunk-syd3-"
        "current-build-coordinate-v6.json"
    ): (
        10_864,
        "79206ac75bdc2dccb6a527289c029383b7f5114619ae107fd315aa44269a13d0",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-ast-janciems-"
        "shell-fit-out-coordinate-v6.json"
    ): (
        7_213,
        "7e56879107d1ac8e47820047584503909e5dc304a5fd8ef6bfd6390e51a30388",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-cdc-eastern-creek-"
        "ec5-current-build-coordinate-v6.json"
    ): (
        8_505,
        "3e104aa051e99fd4bf573579f8f81b1dc78012d1164094352de5be8e8f72c26f",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-cdc-eastern-creek-"
        "ec6-current-build-coordinate-v6.json"
    ): (
        8_505,
        "536861d0e662892cfb9f3fafdf26af464a67639ec8bff62261ddc23ffad61ee6",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-microsoft-ath04-"
        "spata-current-build-coordinate-v6.json"
    ): (
        17_276,
        "0cfec135b321bc0c7f10ff6660b7ff33e43a02634af1eefe0095d1d327e1ebf2",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-ten-brinke-spata-"
        "current-build-coordinate-v6.json"
    ): (
        10_642,
        "159a1326c5dabf9d87b62d0d72ab31f09d7591b6e148826879fc889e1dce9344",
    ),
    (
        "normalized-successors/curated-official-2026-07-21-tet-dc7-salaspils-"
        "phase1-current-build-coordinate-v6.json"
    ): (
        9_545,
        "ad64eebd072949695cab3051d70dccb80c637281807f22617a6c876a50ab27d0",
    ),
    "retrieval-inventory.json": (
        4_801,
        "ac695cedfd7b723def72186f93e1658f76f1fb62c9066adb5b513d5e20b6ec44",
    ),
}


def sha256(filename: Path) -> str:
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def signed_area(ring: list[list[float]]) -> float:
    return sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(ring, ring[1:])
    ) / 2


class SiteCoordinateAssessmentV6Tests(unittest.TestCase):
    def _load(self, filename: Path) -> dict:
        return json.loads(filename.read_text(encoding="utf-8"))

    def _payload_documents(self) -> tuple[dict[str, bytes], dict[str, dict]]:
        payloads = builder.build_payloads(TEST_RECORDED_AT)
        documents = {
            relative: json.loads(raw)
            for relative, raw in payloads.items()
            if relative.startswith("normalized-successors/")
        }
        return payloads, documents

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("coordinate v6 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def test_builder_exact_partition_and_coordinate_only_deltas(self) -> None:
        with self._network_guard():
            payloads, documents = self._payload_documents()
        self.assertEqual(len(documents), 7)
        self.assertEqual(len(payloads), 13)
        self.assertEqual(
            list(builder.COHORT)[:7],
            [specification["predecessor"] for specification in builder.ACCEPTED],
        )

        observations = json.loads(payloads["coordinate-observations.json"])
        self.assertEqual(
            observations["assessment_scope"],
            {
                "candidate_project_rows": 13,
                "accepted_successors": 7,
                "accepted_project_locations": 6,
                "accepted_campus_identities": 6,
                "accepted_point_successors": 6,
                "accepted_geometry_only_successors": 1,
                "review_or_ineligible_rows": 6,
            },
        )
        self.assertEqual(
            observations["accepted_order"],
            ["syd3", "ec5", "ec6", "ath04", "tet", "ten_brinke", "ast"],
        )
        self.assertEqual(len(observations["rows"]), 13)

        for specification in builder.ACCEPTED:
            predecessor_path = ROOT / "sources" / specification["predecessor"]
            predecessor = self._load(predecessor_path)
            relative = (
                "normalized-successors/"
                + builder._successor_name(specification["predecessor"])
            )
            successor = documents[relative]
            self.assertEqual(successor["evidence"][:-1], predecessor["evidence"])
            self.assertEqual(len(successor["evidence"]), len(predecessor["evidence"]) + 1)
            self.assertEqual(
                successor["evidence"][-1]["key"], specification["evidence_key"]
            )
            self.assertEqual(
                successor["evidence"][-1]["kind"], specification["kind"]
            )
            restored = copy.deepcopy(successor)
            restored["evidence"] = copy.deepcopy(predecessor["evidence"])
            expected_changed = (
                {"coordinates", "geometry", "evidence_key", "method"}
                if "point" in specification
                else {"geometry", "evidence_key", "method"}
            )
            for entity_name in ("campus", "project"):
                before = predecessor[entity_name]
                after = successor[entity_name]
                changed = {
                    key
                    for key in set(before) | set(after)
                    if before.get(key) != after.get(key)
                }
                self.assertEqual(changed, expected_changed)
                for key in changed:
                    restored[entity_name][key] = copy.deepcopy(before[key])
            for section in (
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            ):
                self.assertEqual(successor[section], predecessor[section])
            self.assertEqual(restored, predecessor)

    def test_exact_six_points_and_source_specific_evidence(self) -> None:
        _payloads, documents = self._payload_documents()
        expected = {
            "syd3": ([150.876, -33.798627], "government_record", True),
            "ec5": ([150.837668, -33.818072], "government_record", False),
            "ec6": ([150.837668, -33.818072], "government_record", False),
            "tet": ([24.3802635323, 56.8656322193], "government_record", True),
            "ten_brinke": (
                [23.90870178233002, 37.96626241294147],
                "company_disclosure",
                True,
            ),
            "ast": ([24.1814716538, 56.933100002], "government_record", True),
        }
        for specification in builder.ACCEPTED:
            label = specification["label"]
            if label == "ath04":
                continue
            relative = (
                "normalized-successors/"
                + builder._successor_name(specification["predecessor"])
            )
            successor = documents[relative]
            point, kind, facility_specific = expected[label]
            longitude, latitude = point
            for entity_name in ("campus", "project"):
                entity = successor[entity_name]
                self.assertEqual(
                    entity["coordinates"],
                    {"latitude": latitude, "longitude": longitude},
                )
                self.assertEqual(entity["geometry"], {"type": "Point", "coordinates": point})
            evidence = successor["evidence"][-1]
            self.assertEqual(evidence["kind"], kind)
            self.assertEqual(evidence["metadata"]["facility_specific"], facility_specific)
            self.assertIn("adds no identity", evidence["metadata"]["claim_guardrail"])
            self.assertIn("No OpenStreetMap", evidence["metadata"]["osm_guardrail"])

        ec5 = documents[
            "normalized-successors/curated-official-2026-07-21-cdc-eastern-"
            "creek-ec5-current-build-coordinate-v6.json"
        ]["evidence"][-1]
        self.assertEqual(ec5["metadata"]["application_id"], "SSD-10330")
        self.assertIn("not distinguish", ec5["metadata"]["shared_campus_scope"])

        tet = documents[
            "normalized-successors/curated-official-2026-07-21-tet-dc7-"
            "salaspils-phase1-current-build-coordinate-v6.json"
        ]["evidence"][-1]
        self.assertEqual(tet["metadata"]["vzd_feature_id"], "AD107074603")
        self.assertEqual(tet["metadata"]["canonical_address"], "Krasta iela 2 k-1, Salaspils")
        self.assertEqual(tet["metadata"]["native_epsg_3059"], [523183.323, 302493.311])

        ast = documents[
            "normalized-successors/curated-official-2026-07-21-ast-janciems-"
            "shell-fit-out-coordinate-v6.json"
        ]["evidence"][-1]
        self.assertEqual(ast["metadata"]["vzd_feature_id"], "AD101873308")
        self.assertEqual(ast["metadata"]["native_epsg_3059"], [511043.784, 309953.622])

    def test_ath04_exact_geometry_and_midpoint_suppression_guard(self) -> None:
        payloads, documents = self._payload_documents()
        ath04 = documents[
            "normalized-successors/curated-official-2026-07-21-microsoft-"
            "ath04-spata-current-build-coordinate-v6.json"
        ]
        self.assertIsNone(ath04["campus"]["coordinates"])
        self.assertIsNone(ath04["project"]["coordinates"])
        self.assertEqual(ath04["campus"]["geometry"], builder.ATH04_CAMPUS_GEOMETRY)
        self.assertEqual(ath04["project"]["geometry"], builder.ATH04_PROJECT_GEOMETRY)
        for ring in (
            builder.E31_WGS84_SOURCE_ORDER,
            builder.E26_WGS84_SOURCE_ORDER,
        ):
            self.assertLess(signed_area(ring), 0)
            self.assertGreater(signed_area(list(reversed(ring))), 0)

        evidence = ath04["evidence"][-1]
        metadata = evidence["metadata"]
        self.assertEqual(
            metadata["source_native_rings_epsg_2100"],
            {"E31": builder.E31_NATIVE, "E26": builder.E26_NATIVE},
        )
        self.assertEqual(
            metadata["areas_square_metres"],
            {
                "E31_stated": 69_538.91,
                "E26_stated": 14_998.50,
                "E31_coordinate_derived": 69_552.7847,
                "E26_coordinate_derived": 15_004.8134,
            },
        )
        self.assertEqual(metadata["transform"]["library"], "proj4@2.20.2")
        self.assertTrue(metadata["representative_point_intentionally_absent"])
        self.assertFalse(metadata["downstream_guard"]["import_in_v6_tests"])

        disposition = json.loads(payloads["disposition.json"])
        guard = disposition["ath04_geometry_only_guard"]
        self.assertTrue(guard["coordinates_remain_null"])
        self.assertTrue(guard["curated_bbox_midpoint_synthesis_must_be_suppressed"])
        self.assertTrue(guard["release_geometry_center_must_be_suppressed"])

    def test_marsden_review_and_five_explicit_exclusions(self) -> None:
        payloads, _documents = self._payload_documents()
        disposition = json.loads(payloads["disposition.json"])
        rows = disposition["not_accepted"]["rows"]
        self.assertEqual(len(rows), 6)
        by_disposition = {row["disposition"]: row for row in rows}
        marsden = by_disposition[
            "review_two_official_lot_points_no_multipoint_schema"
        ]
        self.assertEqual(
            marsden["source_response_sha256"],
            "dc0d60ae74ad23e33def28ba49c3ac2ea1dced0e0a736cd8d4c064c74ab58040",
        )
        self.assertEqual(
            [point["feature_guid"] for point in marsden["candidate_points"]],
            [
                "{f516a473-f348-447a-95ce-5b1c09391068}",
                "{a47cbd56-a6e0-4861-807d-22dd21f8b548}",
            ],
        )
        self.assertIn("no MultiPoint", marsden["reason"])
        self.assertEqual(
            set(by_disposition) - {marsden["disposition"]},
            {
                "review_no_facility_coordinate_bridge",
                "review_aggregate_unnamed_facilities",
                "review_operational_not_current_construction",
                "ineligible_locality_only",
                "ineligible_operational_closure",
            },
        )

    def test_point_successors_import_offline_and_idempotently(self) -> None:
        payloads, _documents = self._payload_documents()
        for relative, raw in payloads.items():
            if not relative.startswith("normalized-successors/") or "ath04" in relative:
                continue
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                successor = Path(temporary) / "successor.json"
                successor.write_bytes(raw)
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._network_guard():
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection, successor, recorded_at=TEST_RECORDED_AT
                        )
                        repeated = CuratedOfficialSourceAdapterV11().import_file(
                            connection, successor, recorded_at=TEST_RECORDED_AT
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(repeated.entities_created, 0)
                    self.assertEqual(repeated.evidence_created, 0)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_closed_stage_rollback_and_no_replace_collision(self) -> None:
        target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=10)
        recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            final = temporary_path / "final"
            lock = temporary_path / ".lock"

            def create_late_collision(_target: datetime) -> None:
                final.mkdir()

            with (
                patch.object(builder, "PUBLICATION_ROOT", temporary_path),
                patch.object(builder, "ARTIFACT_DIR", final),
                patch.object(builder, "PUBLICATION_LOCK", lock),
                patch.object(builder, "_wait_until", create_late_collision),
            ):
                with self.assertRaisesRegex(
                    builder.SiteCoordinateAssessmentV6Error,
                    "late final path collision",
                ):
                    builder.publish(recorded_at)
            leftovers = [
                candidate.name
                for candidate in temporary_path.iterdir()
                if candidate.name.startswith(f".{builder.ARTIFACT_ID}.stage-")
                or candidate.name == ".lock"
            ]
            self.assertEqual(leftovers, [])
            self.assertTrue(final.is_dir())

            source = temporary_path / "source"
            destination = temporary_path / "destination"
            source.mkdir()
            destination.mkdir()
            with self.assertRaises(builder.SiteCoordinateAssessmentV6Error):
                builder._promote_noreplace(source, destination)
            self.assertTrue(source.is_dir())
            self.assertTrue(destination.is_dir())

    @unittest.skipUnless(ARTIFACT.exists(), "v6 artifact not published yet")
    def test_frozen_artifact_exact_pins_reproduction_and_replay(self) -> None:
        self.assertIsNotNone(RECORDED_AT)
        self.assertIsNotNone(MANIFEST_SHA256)
        self.assertIsNotNone(MANIFEST_TREE_SHA256)
        self.assertIsNotNone(PHYSICAL_TREE_SHA256)
        self.assertTrue(FILES)
        assert RECORDED_AT is not None
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(tree_digest(ARTIFACT), PHYSICAL_TREE_SHA256)
        actual = {
            filename.relative_to(ARTIFACT).as_posix()
            for filename in ARTIFACT.rglob("*")
            if filename.is_file()
        }
        self.assertEqual(actual, set(FILES))
        for relative, expected in FILES.items():
            filename = ARTIFACT / relative
            self.assertFalse(filename.is_symlink())
            self.assertEqual(stat.S_IMODE(filename.stat().st_mode), 0o444)
            self.assertEqual((filename.stat().st_size, sha256(filename)), expected)
            if filename.suffix == ".json":
                document = self._load(filename)
                self.assertEqual(
                    filename.read_bytes(),
                    (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode(),
                )
        for directory in (
            candidate for candidate in ARTIFACT.rglob("*") if candidate.is_dir()
        ):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)

        manifest = self._load(ARTIFACT / "manifest.json")
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(sha256(ARTIFACT / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(manifest["tree_sha256"], MANIFEST_TREE_SHA256)
        self.assertEqual(manifest["publication_contract_version"], 6)
        self.assertEqual(
            hashlib.sha256(
                (json.dumps(manifest["files"], indent=2, ensure_ascii=False) + "\n").encode()
            ).hexdigest(),
            MANIFEST_TREE_SHA256,
        )
        target = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(target, datetime.now(UTC))
        for filename in (ARTIFACT, *ARTIFACT.rglob("*")):
            self.assertLessEqual(datetime.fromtimestamp(filename.stat().st_birthtime, UTC), target)
            self.assertLessEqual(datetime.fromtimestamp(filename.stat().st_mtime, UTC), target)
        self.assertGreaterEqual(datetime.fromtimestamp(ARTIFACT.stat().st_ctime, UTC), target)

        with self._network_guard():
            payloads = builder.build_payloads(RECORDED_AT)
        self.assertEqual(set(payloads), set(FILES))
        for relative, raw in payloads.items():
            self.assertEqual(raw, (ARTIFACT / relative).read_bytes())

        before = {
            filename.relative_to(ARTIFACT).as_posix(): sha256(filename)
            for filename in ARTIFACT.rglob("*")
            if filename.is_file()
        }
        result = subprocess.run(
            [sys.executable, str(PUBLISHER)],
            cwd=WORKSPACE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "existing-identical")
        after = {
            filename.relative_to(ARTIFACT).as_posix(): sha256(filename)
            for filename in ARTIFACT.rglob("*")
            if filename.is_file()
        }
        self.assertEqual(after, before)
        leftovers = [
            candidate.name
            for candidate in ARTIFACT.parent.iterdir()
            if candidate.name.startswith(f".{ARTIFACT.name}.stage-")
            or candidate.name == f".{ARTIFACT.name}.lock"
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
