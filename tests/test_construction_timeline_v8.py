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

from datacenter_atlas.datacenter_atlas import construction_timeline_v8 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v8.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v8"
V7_DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v7.json"
V7_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v7"
V86_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"

DEFINITION_PIN = (
    2_881,
    "9f67b19847aadf326cdd3701c3e4a8aa5309a9b59c58d3d749a6369fdfc3ec97",
)
MANIFEST_SHA256 = "4a71dd94b0ab97a8b0e9add0b4688bececec285832de991f7c71a23a7dc8a02d"
BUNDLE_TREE_SHA256 = "f3231947d338bd201bc416dd7d78cba51e5193d484a8fb84a0f2bab2b4b65f12"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        34_593,
        "6095d31b51f6f7d9467b46fc5252f15251a8f0ae4ce7fd94d99df5ec20967a95",
    ),
    "README.md": (
        1_406,
        "a881c107d5fb15bf5183d30b0a524cceff790decbc0d3e92bb1de32a17df3a58",
    ),
    "coverage.json": (
        35_509,
        "5a8708f2f581fb6541931733648cb23f943eee1b4a7b1f975b5e59b5e4a004aa",
    ),
    "entity-timelines.jsonl": (
        813_113,
        "b480c352776be9fb7d43443bb53aff64f9e3b9754eb695360e33f1264b13c98a",
    ),
    "lifecycle-observations.csv": (
        360_794,
        "92b73cb4283ceaaa94a79546a73362e574fda671d374927736ff6743e9623cff",
    ),
    "manifest.json": (3_881, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "fe6b30a2beef29c09aaa934065ca70f5407c268cf3f75bb11fc073388a485bc6",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v8.py": (
        67_029,
        "74864aebfd96ce65b7fe7e13037c93e30087b1652d7f63a562859590974fdc0f",
    ),
    ROOT / "construction_timeline_v8.py": (
        331,
        "52f7691deb02103ad769683c96356f7343d4c5fcb94e9d69a56f606919c88f9c",
    ),
    ROOT / "scripts/build_construction_timeline_v8.py": (
        1_484,
        "18d831a8556e1788763a48f708f1c87d332c9dd1f4fb58dadeb608ac73952bda",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV8Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v8 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_definition_bundle_inputs_and_code_pins_are_exact(self) -> None:
        self.assertEqual(
            (DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(V7_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V86_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(
            {path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES
        )
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for path, expected in CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
        self.assertEqual(
            (V86_DEFINITION.stat().st_size, sha256(V86_DEFINITION)),
            timeline.OPEN_SEED_DEFINITION_PIN,
        )
        self.assertEqual(sha256(V7_DEFINITION), timeline.PREDECESSOR_DEFINITION_SHA256)

    def test_exact_v7_rows_and_complete_v86_delta_are_preserved(self) -> None:
        predecessor = timeline.previous.v5.v3._parse_csv(
            V7_BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        current = timeline.previous.v5.v3._parse_csv(
            BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (526, 537))
        for row in predecessor:
            self.assertEqual(current_by_id[row["observation_id"]], row)
            self.assertEqual(
                timeline.previous.v5.v3._csv_bytes(
                    [current_by_id[row["observation_id"]]]
                ),
                timeline.previous.v5.v3._csv_bytes([row]),
            )
        additions = [
            row for row in current if row["observation_id"] not in predecessor_ids
        ]
        source_by_key = timeline._post_v83_source_contract()
        contract = timeline._event_contract(additions)
        self.assertEqual((len(additions), len(source_by_key)), (11, 11))
        self.assertEqual(
            {row["entity_stable_key"] for row in additions}, set(source_by_key)
        )
        self.assertEqual(
            timeline._event_contract_sha256(contract),
            timeline.V86_ADDITION_EVENT_CONTRACT_SHA256,
        )

        predecessor_timelines = timeline.previous.v5.v3._parse_jsonl(
            V7_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.previous.v5.v3._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        self.assertEqual(
            (len(predecessor_timelines), len(current_timelines)), (506, 517)
        )
        for row in predecessor_timelines:
            inherited = current_by_key[row["entity_stable_key"]]
            self.assertEqual(inherited, row)
            self.assertEqual(
                timeline.previous.v5.v3._canonical_json_line(inherited),
                timeline.previous.v5.v3._canonical_json_line(row),
            )
        new_timelines = [
            row
            for row in current_timelines
            if row["entity_stable_key"] in source_by_key
        ]
        self.assertEqual(len(new_timelines), 11)
        self.assertFalse(any(row["has_status_change"] for row in new_timelines))

    def test_six_v84_five_v86_sources_and_no_v85_lifecycle_are_exact(self) -> None:
        definition = json.loads(V86_DEFINITION.read_text())
        additions = definition["curated_inputs"][timeline.V7_ACCEPTED_INPUTS :]
        self.assertEqual(len(definition["curated_inputs"]), 452)
        self.assertEqual(
            tuple(row["path"] for row in additions), timeline.POST_V83_SOURCE_PATHS
        )
        self.assertEqual(
            tuple(timeline.open_seed_v84.ADDITION_ORDER),
            timeline.POST_V83_SOURCE_PATHS[:6],
        )
        self.assertEqual(
            tuple(timeline.open_seed_v86.ADDITION_ORDER),
            timeline.POST_V83_SOURCE_PATHS[6:],
        )
        self.assertEqual(timeline.V85_LIFECYCLE_SOURCES, 0)
        lifecycle_count = 0
        for item in additions:
            path = ROOT / item["path"]
            self.assertEqual(sha256(path), item["sha256"])
            document = json.loads(path.read_text())
            self.assertEqual(len(document["lifecycle"]), 1)
            self.assertEqual(document["lifecycle"][0]["entity"], "project")
            lifecycle_count += 1
        self.assertEqual(lifecycle_count, 11)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        self.assertEqual(
            coverage["v8_delta_non_lifecycle_promotion"],
            {
                "capacity_only_sources_promoted_to_lifecycle": 0,
                "coordinate_only_sources_promoted_to_lifecycle": 0,
            },
        )

    def test_counts_closures_staleness_and_noninference_are_exact(self) -> None:
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        rows = timeline.previous.v5.v3._parse_csv(
            BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        timelines = timeline.previous.v5.v3._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        predecessor_ids = {
            row["observation_id"]
            for row in timeline.previous.v5.v3._parse_csv(
                V7_BUNDLE / timeline.OBSERVATIONS_FILENAME
            )
        }
        additions = [
            row for row in rows if row["observation_id"] not in predecessor_ids
        ]
        contract = timeline._event_contract(additions)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(
            Counter(event[11] for event in contract),
            {
                "aging_91_365_days": 6,
                "recent_0_90_days": 4,
                "stale_over_365_days": 1,
            },
        )
        self.assertEqual(
            Counter(row["entity_kind"] for row in rows),
            {"project": 454, "campus": 83},
        )
        self.assertEqual(
            Counter(row["entity_kind"] for row in timelines),
            {"project": 434, "campus": 83},
        )
        self.assertEqual(
            coverage["current_status_classification_counts"], {"unknown": 517}
        )
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] is False
                and row["latest_observation_persistence_assumed"] is False
                for row in timelines
            )
        )
        closures = coverage["v8_delta_operational_lifecycle_closures"]
        self.assertEqual(
            {row["entity_stable_key"] for row in closures},
            timeline.RECENT_OPERATIONAL_CLOSURE_KEYS,
        )
        self.assertTrue(
            all(row["current_operational_claim"] is False for row in closures)
        )
        stale = coverage["v8_delta_stale_latest_timelines"]
        self.assertEqual(
            {row["entity_stable_key"] for row in stale},
            timeline.STALE_LATEST_ADDITION_KEYS,
        )
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])

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
        self.assertEqual(
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen
        )

    def test_publication_times_future_clock_and_private_residue_fail_closed(
        self,
    ) -> None:
        generated = timeline._parse_utc(timeline.GENERATED_AT, label="generated_at")
        timeline.validate_construction_timeline_bundle(BUNDLE)
        for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
            metadata = path.stat()
            self.assertLessEqual(
                metadata.st_birthtime, generated.timestamp() + 0.000_001
            )
            self.assertLessEqual(metadata.st_mtime, generated.timestamp() + 0.000_001)
        for root in (DEFINITION, BUNDLE):
            self.assertGreaterEqual(
                root.stat().st_ctime + 0.000_001, generated.timestamp()
            )
        with self.assertRaisesRegex(
            timeline.ConstructionTimelineError, "exceeds validation wall clock"
        ):
            timeline.validate_construction_timeline_bundle(
                BUNDLE, validation_wall_clock=generated - timedelta(seconds=1)
            )
        self.assertFalse(timeline.PUBLICATION_LOCK.exists())
        self.assertFalse(
            list(DEFINITION.parent.glob(f".{DEFINITION.name}.private-stage-*"))
        )
        self.assertFalse(list(BUNDLE.parent.glob(f".{BUNDLE.name}.private-stage-*")))

    def test_tamper_collision_stage_mutation_and_cli_fail_closed(self) -> None:
        frozen_definition = DEFINITION.read_bytes()
        frozen_manifest = (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes()
        with self.assertRaisesRegex(
            timeline.ConstructionTimelineError, "already exists"
        ):
            timeline.publish_construction_timeline_v8()
        self.assertEqual(DEFINITION.read_bytes(), frozen_definition)
        self.assertEqual(
            (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes(), frozen_manifest
        )

        with tempfile.TemporaryDirectory(
            prefix="timeline-v8-fail-closed-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            copied = root / "tampered"
            shutil.copytree(BUNDLE, copied)
            copied.chmod(0o755)
            observations = copied / timeline.OBSERVATIONS_FILENAME
            observations.chmod(0o644)
            observations.write_bytes(observations.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "checkpoint differs"
            ):
                timeline.validate_construction_timeline_bundle(
                    copied, require_frozen=False, verify_publication_times=False
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
                    linked, require_frozen=False, verify_publication_times=False
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

        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(
            definition["predecessor"]["definition"]["path"], V7_DEFINITION.name
        )
        self.assertEqual(
            definition["open_seed"]["definition"]["path"], V86_DEFINITION.name
        )
        checkpoint_text = json.dumps(
            {
                "open_seed": definition["open_seed"],
                "predecessor": definition["predecessor"],
            },
            sort_keys=True,
        )
        self.assertNotIn("federation", checkpoint_text)
        self.assertNotIn("identity-accounting", checkpoint_text)
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_construction_timeline_v8.py"),
                "--validate-only",
            ],
            cwd=WORKSPACE,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout)["counts"], timeline.EXPECTED_COUNTS
        )


if __name__ == "__main__":
    unittest.main()
