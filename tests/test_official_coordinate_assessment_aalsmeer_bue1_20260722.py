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
        "datacenter_atlas.datacenter_atlas."
        "official_coordinate_assessment_aalsmeer_bue1_20260722"
    )
except ModuleNotFoundError:
    builder = importlib.import_module(
        "datacenter_atlas.official_coordinate_assessment_aalsmeer_bue1_20260722"
    )


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = ROOT / (
    "source_artifacts/official-coordinate-assessment-aalsmeer-bue1-2026-07-22-v2"
)
PUBLISHER = ROOT / (
    "scripts/publish_official_coordinate_assessment_aalsmeer_bue1_20260722.py"
)
TEST_RECORDED_AT = "2026-07-22T04:10:00Z"

RECORDED_AT: str | None = "2026-07-22T04:03:01Z"
MANIFEST_SHA256: str | None = (
    "29b18e190f7347134ea90c37eafff35efc82b6c0a852eeb6ab5a96feb2565740"
)
MANIFEST_TREE_SHA256: str | None = (
    "f1d62cacf7e879d724b9ace28da5cec0aae2176d8f5a2ccef9646c122f3328ae"
)
PHYSICAL_TREE_SHA256: str | None = (
    "f9dc77b2f12ed033cd26b1eb02321959e18b5c85d9af0395cfb2986046b81b00"
)
FILES: dict[str, tuple[int, str]] = {
    "README.md": (
        2_421,
        "e0785619d451e843a0c577941da9cbc7ba958452f8bd0c2d1c9d37672dc0459e",
    ),
    "coordinate-observations.json": (
        3_207,
        "608156d43026eaa41612568347b1266cbac6754830ea795e4d3fb9deede95fb4",
    ),
    "disposition.json": (
        6_679,
        "d6b5fde94d67f9b4411df5b809cfe90080e192856292bcbbc429ca1c248f6a1a",
    ),
    "manifest.json": (1_820, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "838fff54444329e9e82fce5e5469edc4e7139351f6a9c7e7861d1fcb8c4bfd4b",
    ),
    (
        "normalized-successors/curated-official-2026-07-22-northc-aalsmeer-"
        "phase-2-expansion-coordinate-v2.json"
    ): (
        12_373,
        "84b48f795ccf7d8a2f8f128454fd3ddc5297214c76818a489a222fcdc99ec9a4",
    ),
    "publication-incident.json": (
        4_821,
        "dc7aea69f1c68c71ba500abd69baa2eabaaef686fd0a8b66308532cc811c6858",
    ),
    "retrieval-inventory.json": (
        5_604,
        "28ededf748860342abc8a79e56c8da3c3c3af5dbb6fa925fc59ad275e00c3293",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfficialCoordinateAssessmentTests(unittest.TestCase):
    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("official-coordinate assessment attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _payloads(self) -> dict[str, bytes]:
        with self._network_guard():
            return builder.build_payloads(TEST_RECORDED_AT)

    def test_exact_partition_coordinate_only_delta_and_one_cardinality(self) -> None:
        payloads = self._payloads()
        self.assertEqual(len(payloads), 8)
        successors = {
            relative: json.loads(raw)
            for relative, raw in payloads.items()
            if relative.startswith("normalized-successors/")
        }
        self.assertEqual(len(successors), 1)
        relative, successor = next(iter(successors.items()))
        predecessor = json.loads(builder.NORTHC_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(relative, f"normalized-successors/{builder._successor_name()}")
        self.assertEqual(successor["evidence"][:-1], predecessor["evidence"])
        self.assertEqual(len(successor["evidence"]), len(predecessor["evidence"]) + 1)
        evidence = successor["evidence"][-1]
        self.assertEqual(evidence["key"], builder.PDOK_EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "government_record")
        self.assertEqual(evidence["license"], "Public Domain Mark 1.0")
        self.assertEqual(evidence["metadata"]["lookup_response"]["num_found"], 1)
        self.assertTrue(evidence["metadata"]["lookup_response"]["num_found_exact"])
        self.assertIn("not as a data-centre", evidence["metadata"]["coordinate_scope"])

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
            self.assertEqual(
                after["coordinates"],
                {"latitude": 52.25979593, "longitude": 4.77335841},
            )
            self.assertEqual(
                after["geometry"],
                {"type": "Point", "coordinates": [4.77335841, 52.25979593]},
            )
            for key in changed:
                restored[entity_name][key] = copy.deepcopy(before[key])
        self.assertEqual(restored, predecessor)
        for section in ("lifecycle", "operating_models", "workloads", "capacities"):
            self.assertEqual(successor[section], predecessor[section])

    def test_bue1_is_review_only_under_explicit_suspension(self) -> None:
        payloads = self._payloads()
        observations = json.loads(payloads["coordinate-observations.json"])
        self.assertEqual(
            observations["assessment_scope"],
            {
                "candidate_project_rows": 2,
                "accepted_successors": 1,
                "accepted_address_points": 1,
                "review_only_rows": 1,
            },
        )
        bue1 = observations["rows"][1]
        self.assertEqual(
            bue1["disposition"],
            "review_api_dataset_suspended_pending_reactivation",
        )
        self.assertIsNone(bue1["successor"])
        self.assertFalse(bue1["candidate_coordinate"]["accepted"])
        self.assertEqual(
            bue1["candidate_coordinate"],
            {
                "longitude": -58.467248,
                "latitude": -34.590172,
                "source_crs": "EPSG:4326",
                "address": "DEL CAMPO AV. 1301, CABA",
                "accepted": False,
            },
        )
        self.assertIn("suspended", bue1["reason"])
        self.assertIn("No stronger current official", bue1["reason"])
        predecessor = json.loads(builder.BUE1_SOURCE.read_text(encoding="utf-8"))
        for entity_name in ("campus", "project"):
            self.assertIsNone(predecessor[entity_name]["coordinates"])
            self.assertIsNone(predecessor[entity_name]["geometry"])

    def test_exact_private_capture_rights_and_source_boundaries(self) -> None:
        with self._network_guard():
            capture = builder.verify_private_capture()
        self.assertEqual(
            capture,
            builder.resolve_external_capture(
                builder.CAPTURE_TRASH,
                builder.CAPTURE_ORIGIN,
            ),
        )
        self.assertEqual(
            builder.CAPTURE_TRASH,
            Path("/Users/kian/.Trash/dc-official-coordinate-gap-20260722.4CXd7D"),
        )
        self.assertEqual(stat.S_IMODE(capture.stat().st_mode), 0o555)
        self.assertEqual(tree_digest(capture), builder.CAPTURE_TREE_SHA256)
        self.assertEqual(len(builder.CAPTURE_FILE_PINS), 16)
        self.assertEqual(
            sum(pin[0] for pin in builder.CAPTURE_FILE_PINS.values()), 182_028
        )
        payloads = self._payloads()
        inventory = json.loads(payloads["retrieval-inventory.json"])
        self.assertFalse(inventory["raw_source_bodies_redistributed"])
        self.assertFalse(inventory["repository_contains_raw_capture"])
        reproducibility = inventory["request_reproducibility"]
        self.assertTrue(reproducibility["accepted_pdok_exact_lookup_url_preserved"])
        self.assertFalse(reproducibility["initial_pdok_search_url_preserved"])
        self.assertFalse(reproducibility["initial_usig_query_url_preserved"])
        disposition = json.loads(payloads["disposition.json"])
        boundaries = disposition["source_boundaries"]
        self.assertEqual(boundaries["openstreetmap_inputs_consumed"], [])
        self.assertEqual(boundaries["peeringdb_inputs_consumed"], [])
        self.assertEqual(boundaries["map_clicks_consumed"], [])
        self.assertFalse(boundaries["satellite_or_cv_claims_added"])
        self.assertEqual(disposition["non_coordinate_claims_added"], [])

        incident = json.loads(payloads["publication-incident.json"])
        self.assertEqual(incident["status"], "rejected_immutable_no_integration")
        self.assertEqual(incident["failure"]["failed_path_count"], 8)
        self.assertTrue(incident["failure"]["passing_root_only"])
        rows = incident["rejected_artifact"]["paths"]
        self.assertEqual({row["path"] for row in rows}, set(builder.REJECTED_V1_PATH_PINS))
        self.assertTrue(next(row for row in rows if row["path"] == ".")["ctime_contract_passed"])
        self.assertTrue(
            all(
                not row["ctime_contract_passed"]
                for row in rows
                if row["path"] != "."
            )
        )
        self.assertTrue(incident["disposition"]["v1_must_not_be_integrated"])
        self.assertEqual(
            disposition["lineage"]["rejected_publication_incident"]["integration"],
            "forbidden",
        )

    def test_successor_imports_offline_and_idempotently(self) -> None:
        payloads = self._payloads()
        raw = payloads[f"normalized-successors/{builder._successor_name()}"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "successor.json"
            path.write_bytes(raw)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._network_guard():
                    first = CuratedOfficialSourceAdapterV11().import_file(
                        connection, path, recorded_at=TEST_RECORDED_AT
                    )
                    repeated = CuratedOfficialSourceAdapterV11().import_file(
                        connection, path, recorded_at=TEST_RECORDED_AT
                    )
                self.assertEqual(first.entities_created, 2)
                self.assertEqual(repeated.entities_created, 0)
                self.assertEqual(repeated.evidence_created, 0)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_temporal_barrier_collision_and_rollback(self) -> None:
        with self.assertRaisesRegex(
            builder.OfficialCoordinateAssessmentError, "precedes an input"
        ):
            builder.build_payloads("2026-07-22T03:56:02Z")

        target = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=10)
        recorded_at = target.isoformat(timespec="seconds").replace("+00:00", "Z")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            final = root / "final"
            lock = root / ".lock"

            def create_collision(_target: datetime) -> None:
                final.mkdir()

            with (
                patch.object(builder, "ARTIFACT_ROOT", root),
                patch.object(builder, "ARTIFACT", final),
                patch.object(builder, "PUBLICATION_LOCK", lock),
                patch.object(builder, "_wait_until", create_collision),
            ):
                with self.assertRaisesRegex(
                    builder.OfficialCoordinateAssessmentError,
                    "late final path collision",
                ):
                    builder.publish(recorded_at)
            leftovers = [
                candidate.name
                for candidate in root.iterdir()
                if candidate.name.startswith(f".{builder.ARTIFACT_ID}.stage-")
                or candidate.name == ".lock"
            ]
            self.assertEqual(leftovers, [])
            self.assertTrue(final.is_dir())

            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            with self.assertRaises(builder.OfficialCoordinateAssessmentError):
                builder._promote_noreplace(source, destination)
            self.assertTrue(source.is_dir())
            self.assertTrue(destination.is_dir())

    @unittest.skipUnless(ARTIFACT.exists(), "coordinate artifact not published yet")
    def test_frozen_artifact_exact_reproduction_and_replay(self) -> None:
        self.assertIsNotNone(RECORDED_AT)
        self.assertIsNotNone(MANIFEST_SHA256)
        self.assertIsNotNone(MANIFEST_TREE_SHA256)
        self.assertIsNotNone(PHYSICAL_TREE_SHA256)
        self.assertTrue(FILES)
        assert RECORDED_AT is not None
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(tree_digest(ARTIFACT), PHYSICAL_TREE_SHA256)
        actual = {
            path.relative_to(ARTIFACT).as_posix()
            for path in ARTIFACT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, set(FILES))
        for relative, expected in FILES.items():
            path = ARTIFACT / relative
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
        manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(sha256(ARTIFACT / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(manifest["tree_sha256"], MANIFEST_TREE_SHA256)
        self.assertEqual(manifest["publication_contract_version"], 6)
        target = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(target, datetime.now(UTC))
        for path in (ARTIFACT, *ARTIFACT.rglob("*")):
            self.assertLessEqual(
                datetime.fromtimestamp(path.stat().st_birthtime, UTC), target
            )
            self.assertLessEqual(datetime.fromtimestamp(path.stat().st_mtime, UTC), target)
            self.assertGreaterEqual(
                datetime.fromtimestamp(path.stat().st_ctime, UTC), target
            )
        with self._network_guard():
            payloads = builder.build_payloads(RECORDED_AT)
        self.assertEqual(set(payloads), set(FILES))
        for relative, raw in payloads.items():
            self.assertEqual(raw, (ARTIFACT / relative).read_bytes())
        before = {
            path.relative_to(ARTIFACT).as_posix(): sha256(path)
            for path in ARTIFACT.rglob("*")
            if path.is_file()
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
            path.relative_to(ARTIFACT).as_posix(): sha256(path)
            for path in ARTIFACT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
