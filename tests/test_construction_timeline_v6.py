from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_timeline_v6 as timeline
except ModuleNotFoundError:
    from datacenter_atlas import construction_timeline_v6 as timeline

from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v6.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v6"
V5_DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v5.json"
V5_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v5"
V73_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v73.json"
V73_RELEASE = ROOT / "releases/2026-07-21-open-seed-v73"

DEFINITION_PIN = (
    3_001,
    "cf89ac2d9672eb8d4e82ee65e7a6ed243887d71dbac0ef1d537a49000edc7afa",
)
MANIFEST_SHA256 = "c01c91efd8c4100edcd197c0b8aa601a494d9c67ab60372cd46d25f045016543"
BUNDLE_TREE_SHA256 = "6f754dcaa6f9d0df7ded14a90da70b2eb7c14d75634ec7bd1c503d47ed060e8f"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        27_734,
        "2794b2ff4e9d6912ec41c827ead7b86e413484c7fff517dbdb332101003dd2b7",
    ),
    "README.md": (
        1_397,
        "e367ddf478dd2c0ab1b109eb37bea75e2ea886e8488710da6c2072fc83b64745",
    ),
    "coverage.json": (
        23_468,
        "edcde1a60597894f3b36de5055fa4e761d6f31bc0d1f5bca4a0be1ec3bde2104",
    ),
    "entity-timelines.jsonl": (
        724_822,
        "92c3a88085b113c56243a0df304d2bd37e5fc417897570a1093b3ad054e5e66f",
    ),
    "lifecycle-observations.csv": (
        320_853,
        "1a0546d6853a1bfa64b5c78e0a6182b49c0cd993f7b40374f48b7f60419017d2",
    ),
    "manifest.json": (3_957, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "7124702ab87a286d89fdd743c9249f9dab7a317c77f9de1ac141c6617ed618fc",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v6.py": (
        59_911,
        "a00f4946d0c3581a8fcfe25b80e817d4156d961bd14fe45a762b4e466bb2296f",
    ),
    ROOT / "construction_timeline_v6.py": (
        331,
        "9b83ccb5f2d71c17aae3daff443ca6696d1170921d78276f01e40a3e009c54e1",
    ),
    ROOT / "scripts/build_construction_timeline_v6.py": (
        1_484,
        "ff596310c1878ccdf4e35f004c832da9bd93c84e56600520bfe8c8332925b310",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV6Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v6 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_definition_bundle_inputs_and_code_pins_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(V5_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V73_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES)
        self.assertEqual(set(ARTIFACTS), timeline.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for path, expected in CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
        self.assertEqual(sha256(V5_DEFINITION), timeline.PREDECESSOR_DEFINITION_SHA256)
        self.assertEqual(sha256(V73_DEFINITION), timeline.OPEN_SEED_DEFINITION_SHA256)

    def test_exact_v5_rows_and_complete_v73_delta_are_preserved(self) -> None:
        predecessor = timeline.v5.v3._parse_csv(
            V5_BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        current = timeline.v5.v3._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (474, 479))
        for row in predecessor:
            self.assertEqual(current_by_id[row["observation_id"]], row)
        additions = [row for row in current if row["observation_id"] not in predecessor_ids]
        self.assertEqual(len(additions), 5)
        self.assertEqual(len({row["observation_id"] for row in additions}), 5)
        self.assertEqual(len({row["entity_stable_key"] for row in additions}), 4)
        self.assertEqual(
            {row["entity_stable_key"] for row in additions},
            set(timeline.PROJECT_SOURCE_BY_KEY),
        )
        self.assertEqual(
            timeline._event_contract(additions),
            timeline.V73_ADDITION_EVENT_CONTRACT,
        )

        predecessor_timelines = timeline.v5.v3._parse_jsonl(
            V5_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.v5.v3._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        self.assertEqual((len(predecessor_timelines), len(current_timelines)), (458, 462))
        current_by_key = {
            row["entity_stable_key"]: row for row in current_timelines
        }
        for row in predecessor_timelines:
            self.assertEqual(current_by_key[row["entity_stable_key"]], row)
        new_timelines = [
            row
            for row in current_timelines
            if row["entity_stable_key"] in timeline.PROJECT_SOURCE_BY_KEY
        ]
        self.assertEqual(len(new_timelines), 4)
        self.assertEqual(
            {row["entity_stable_key"] for row in new_timelines if row["has_status_change"]},
            {
                "curated:icatec-ica-digital-transformation-data-center:"
                "four-storey-technology-center-build"
            },
        )

    def test_counts_coordinate_neutrality_and_noninference_are_exact(self) -> None:
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        rows = timeline.v5.v3._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        timelines = timeline.v5.v3._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(
            Counter(event[11] for event in timeline.V73_ADDITION_EVENT_CONTRACT),
            {"recent_0_90_days": 2, "aging_91_365_days": 3},
        )
        self.assertEqual(Counter(row["entity_kind"] for row in rows), {"project": 396, "campus": 83})
        self.assertEqual(Counter(row["entity_kind"] for row in timelines), {"project": 379, "campus": 83})
        self.assertEqual(coverage["current_status_classification_counts"], {"unknown": 462})
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] is False
                and row["latest_observation_persistence_assumed"] is False
                for row in timelines
            )
        )
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])
        coordinate = coverage["v72_coordinate_only_delta"]
        self.assertEqual(coordinate["project_keys"], sorted(timeline.V72_COORDINATE_PROJECT_KEYS))
        self.assertEqual(coordinate["lifecycle_observations_added"], 0)
        self.assertEqual(coordinate["lifecycle_semantic_changes"], 0)
        self.assertEqual(coordinate["timeline_rows_changed"], 0)
        self.assertFalse(coordinate["current_construction_claim"])
        events = {row["entity_stable_key"]: row for row in coverage["v73_addition_events"]}
        self.assertEqual(events["curated:bichuten-chovar-data-center:initial-container-build"]["observation_age_days"], 112)
        icatec = next(
            row
            for row in timelines
            if row["entity_stable_key"]
            == "curated:icatec-ica-digital-transformation-data-center:"
            "four-storey-technology-center-build"
        )
        self.assertTrue(icatec["has_status_change"])
        self.assertFalse(icatec["current_construction_claim"])

    def test_two_offline_reconstructions_are_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        definition = timeline._load_definition(DEFINITION)
        with ExitStack() as stack:
            self._offline(stack)
            first, first_manifest = timeline._prepare_payloads(definition)
            second, second_manifest = timeline._prepare_payloads(definition)
        self.assertEqual(first, second)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first, frozen)
        self.assertEqual({path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen)

    def test_publication_times_and_injected_future_clock_fail_closed(self) -> None:
        generated = timeline._parse_utc(timeline.GENERATED_AT, label="generated_at")
        timeline.validate_construction_timeline_bundle(BUNDLE)
        for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
            metadata = path.stat()
            self.assertLessEqual(metadata.st_birthtime, generated.timestamp() + 0.000_001)
            self.assertLessEqual(metadata.st_mtime, generated.timestamp() + 0.000_001)
        for root in (DEFINITION, BUNDLE):
            self.assertGreaterEqual(root.stat().st_ctime + 0.000_001, generated.timestamp())
        with self.assertRaisesRegex(
            timeline.ConstructionTimelineError,
            "exceeds validation wall clock",
        ):
            timeline.validate_construction_timeline_bundle(
                BUNDLE,
                validation_wall_clock=generated - timedelta(seconds=1),
            )

    def test_tamper_symlink_collision_and_stage_mutation_fail_closed(self) -> None:
        frozen_definition = DEFINITION.read_bytes()
        frozen_manifest = (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes()
        with self.assertRaisesRegex(timeline.ConstructionTimelineError, "already exists"):
            timeline.publish_construction_timeline_v6()
        self.assertEqual(DEFINITION.read_bytes(), frozen_definition)
        self.assertEqual((BUNDLE / timeline.MANIFEST_FILENAME).read_bytes(), frozen_manifest)

        with tempfile.TemporaryDirectory(
            prefix="timeline-v6-fail-closed-",
            dir="/private/tmp",
        ) as temporary:
            root = Path(temporary)
            copied = root / "tampered"
            shutil.copytree(BUNDLE, copied)
            copied.chmod(0o755)
            observations = copied / timeline.OBSERVATIONS_FILENAME
            observations.chmod(0o644)
            observations.write_bytes(observations.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError,
                "checkpoint differs",
            ):
                timeline.validate_construction_timeline_bundle(
                    copied,
                    require_frozen=False,
                    verify_publication_times=False,
                )

            linked = root / "linked"
            shutil.copytree(BUNDLE, linked)
            linked.chmod(0o755)
            attribution = linked / timeline.ATTRIBUTION_FILENAME
            attribution.chmod(0o644)
            attribution.unlink()
            attribution.symlink_to(BUNDLE / timeline.ATTRIBUTION_FILENAME)
            with self.assertRaises(timeline.ConstructionTimelineError):
                timeline.validate_construction_timeline_bundle(
                    linked,
                    require_frozen=False,
                    verify_publication_times=False,
                )

            stage = root / "stage"
            stage.write_bytes(b"staged\n")
            collision = root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(SystemExit):
                timeline.promote_noreplace(stage, collision)
            self.assertEqual(stage.read_bytes(), b"staged\n")
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            contaminated = root / "contaminated"
            contaminated.mkdir()
            preexisting = contaminated / "x"
            preexisting.write_bytes(b"first\n")
            with self.assertRaises(FileExistsError):
                timeline._write_bundle_stage(contaminated, {"x": b"second\n"})
            self.assertEqual(preexisting.read_bytes(), b"first\n")

    def test_definition_has_only_v5_and_v73_checkpoint_artifacts(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(
            definition["predecessor"]["definition"]["path"],
            V5_DEFINITION.name,
        )
        self.assertEqual(
            definition["open_seed"]["definition"]["path"],
            V73_DEFINITION.name,
        )
        checkpoint_text = json.dumps(
            {
                "open_seed": definition["open_seed"],
                "predecessor": definition["predecessor"],
            },
            sort_keys=True,
        )
        self.assertNotIn("public-open-v4", checkpoint_text)
        self.assertNotIn("federation", checkpoint_text)
        self.assertNotIn("identity-accounting", checkpoint_text)

    def test_cli_validate_only_is_offline_and_exact(self) -> None:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_construction_timeline_v6.py"),
                "--validate-only",
            ],
            cwd=WORKSPACE,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["counts"], timeline.EXPECTED_COUNTS)


if __name__ == "__main__":
    unittest.main()
