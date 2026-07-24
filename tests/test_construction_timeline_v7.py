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

from datacenter_atlas.datacenter_atlas import construction_timeline_v7 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v7.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v7"
V6_DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v6.json"
V6_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v6"
V83_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v83.json"
V83_RELEASE = ROOT / "releases/2026-07-21-open-seed-v83"

DEFINITION_PIN = (
    2_941,
    "2fa593cbb2f135e1e6feb5baf3e18efa0fd4b9a88a4b264884306a50e43aece1",
)
MANIFEST_SHA256 = "a5378eb55f42132193d1e82b97dec5a252e950fa5c4d0c22b278c404ad921265"
BUNDLE_TREE_SHA256 = "b7dd059de068366d12da84970ca750fc3a2872f59069b5563ac47c5e05ce568c"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        33_549,
        "2d9c4024cdf1960a873797f996ae7155bbde5bd65bb42810320cc183f7ddb0e1",
    ),
    "README.md": (
        1_414,
        "45746fc32af1cf3f22cf5d0d5ea0439d59738d12bd5137509a042acbf1355bcf",
    ),
    "coverage.json": (
        68_483,
        "45246273b5a84287a4da3633fa9dbb437f97976be23731f5998fd0f763c12c60",
    ),
    "entity-timelines.jsonl": (
        796_704,
        "2a4db63d9e80c6245e48aef64696a24f08c0ab864617329a670a6c582377ae7a",
    ),
    "lifecycle-observations.csv": (
        353_923,
        "ac9d57eae0bdd302083b787cf3ed40703d29210e1ba09fa8c0553b70573b5609",
    ),
    "manifest.json": (3_897, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "fbe00796d12fb0dbab1c94abda9de5256063770fdc430b2cdfae6c5f4248c50c",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v7.py": (
        68_784,
        "1c87b42c5798f95658b80b18e14b0b1459cdbd191febfd6bd85477723ce60692",
    ),
    ROOT / "construction_timeline_v7.py": (
        331,
        "e0a853fe40fb375622e2f4a20bd9d22007ac2a05746d6c1b9b31ecadfe126e60",
    ),
    ROOT / "scripts/build_construction_timeline_v7.py": (
        1_484,
        "aa85ecbead8ce12a8173e77323db4c2ab69f54afdc86a7df3497a4a34071d365",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV7Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v7 attempted network access")
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
        self.assertEqual(tree_digest(V6_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V83_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
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
        self.assertEqual(sha256(V6_DEFINITION), timeline.PREDECESSOR_DEFINITION_SHA256)
        self.assertEqual(sha256(V83_DEFINITION), timeline.OPEN_SEED_DEFINITION_SHA256)

    def test_exact_v6_rows_and_complete_v83_delta_are_preserved(self) -> None:
        predecessor = timeline.previous.v5.v3._parse_csv(
            V6_BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        current = timeline.previous.v5.v3._parse_csv(
            BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (479, 526))
        for row in predecessor:
            self.assertEqual(current_by_id[row["observation_id"]], row)
        additions = [
            row for row in current if row["observation_id"] not in predecessor_ids
        ]
        source_by_key = timeline._post_v73_source_contract()
        contract = timeline._event_contract(additions)
        self.assertEqual((len(additions), len(source_by_key)), (47, 44))
        self.assertEqual(
            {row["entity_stable_key"] for row in additions}, set(source_by_key)
        )
        self.assertEqual(
            timeline._event_contract_sha256(contract),
            timeline.V83_ADDITION_EVENT_CONTRACT_SHA256,
        )

        predecessor_timelines = timeline.previous.v5.v3._parse_jsonl(
            V6_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.previous.v5.v3._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        self.assertEqual(
            (len(predecessor_timelines), len(current_timelines)), (462, 506)
        )
        for row in predecessor_timelines:
            self.assertEqual(current_by_key[row["entity_stable_key"]], row)
        new_timelines = [
            row
            for row in current_timelines
            if row["entity_stable_key"] in source_by_key
        ]
        self.assertEqual(len(new_timelines), 44)
        self.assertFalse(any(row["has_status_change"] for row in new_timelines))

    def test_source_delta_has_lifecycle_and_no_non_lifecycle_promotion(self) -> None:
        source_by_key = timeline._post_v73_source_contract()
        definition = json.loads(V83_DEFINITION.read_text())
        additions = definition["curated_inputs"][timeline.V6_ACCEPTED_INPUTS :]
        self.assertEqual(len(definition["curated_inputs"]), 441)
        self.assertEqual(
            tuple(row["path"] for row in additions), timeline.POST_V73_SOURCE_PATHS
        )
        self.assertEqual(len(source_by_key), 44)
        lifecycle_count = 0
        for path in timeline.POST_V73_SOURCE_PATHS:
            document = json.loads((ROOT / path).read_text())
            self.assertTrue(document["lifecycle"])
            self.assertTrue(
                all(row["entity"] == "project" for row in document["lifecycle"])
            )
            lifecycle_count += len(document["lifecycle"])
        self.assertEqual(lifecycle_count, 47)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        self.assertEqual(
            coverage["post_v73_non_lifecycle_promotion"],
            {
                "capacity_only_sources_promoted_to_lifecycle": 0,
                "coordinate_only_sources_promoted_to_lifecycle": 0,
            },
        )

    def test_counts_operational_closures_staleness_and_noninference_are_exact(
        self,
    ) -> None:
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
                V6_BUNDLE / timeline.OBSERVATIONS_FILENAME
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
            {"recent_0_90_days": 28, "aging_91_365_days": 15, "stale_over_365_days": 4},
        )
        self.assertEqual(
            Counter(row["entity_kind"] for row in rows), {"project": 443, "campus": 83}
        )
        self.assertEqual(
            Counter(row["entity_kind"] for row in timelines),
            {"project": 423, "campus": 83},
        )
        self.assertEqual(
            coverage["current_status_classification_counts"], {"unknown": 506}
        )
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] is False
                and row["latest_observation_persistence_assumed"] is False
                for row in timelines
            )
        )
        closures = coverage["recent_operational_lifecycle_closures"]
        self.assertEqual(
            {row["entity_stable_key"] for row in closures},
            timeline.RECENT_OPERATIONAL_CLOSURE_KEYS,
        )
        self.assertTrue(
            all(row["current_operational_claim"] is False for row in closures)
        )
        stale = coverage["stale_latest_addition_timelines"]
        self.assertEqual(
            {row["entity_stable_key"] for row in stale},
            timeline.STALE_LATEST_ADDITION_KEYS,
        )
        self.assertEqual(
            {row["entity_stable_key"] for row in stale if row["single_observation"]},
            timeline.SINGLE_OLD_ADDITION_KEYS,
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

    def test_tamper_symlink_collision_and_stage_mutation_fail_closed(self) -> None:
        frozen_definition = DEFINITION.read_bytes()
        frozen_manifest = (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes()
        with self.assertRaisesRegex(
            timeline.ConstructionTimelineError, "already exists"
        ):
            timeline.publish_construction_timeline_v7()
        self.assertEqual(DEFINITION.read_bytes(), frozen_definition)
        self.assertEqual(
            (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes(), frozen_manifest
        )

        with tempfile.TemporaryDirectory(
            prefix="timeline-v7-fail-closed-", dir="/private/tmp"
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

    def test_definition_checkpoints_and_cli_validate_only_are_exact(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(
            definition["predecessor"]["definition"]["path"], V6_DEFINITION.name
        )
        self.assertEqual(
            definition["open_seed"]["definition"]["path"], V83_DEFINITION.name
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
                str(ROOT / "scripts/build_construction_timeline_v7.py"),
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
