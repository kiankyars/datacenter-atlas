from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
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
    from datacenter_atlas.datacenter_atlas import construction_timeline_v4 as timeline
except ModuleNotFoundError:
    from datacenter_atlas import construction_timeline_v4 as timeline

from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v4.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v4"
V3_DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v3.json"
V3_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v3"
V68_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
V68_RELEASE = ROOT / "releases/2026-07-21-open-seed-v68"

DEFINITION_PIN = (
    2_676,
    "8e45d010686c24c09411183caa31770df68496efb49be881b265be955e30ffdd",
)
MANIFEST_SHA256 = "d09831798f54d245067498f1b8ddf46f048ffde1c4100a1b55435e5daf8f4589"
BUNDLE_TREE_SHA256 = "a46931052c9ba21d056a8bd7efedef09c9b2890fa60b4ded036dee519f3d30df"

ARTIFACTS = {
    "ATTRIBUTION.txt": (26_773, "b7b3022e758953aa41bbff8ca2bff0761f6c46318bf984fc57369ecfc3e88be8"),
    "README.md": (1_098, "968affb4cfe08e07914cb179963f0393967123d85f7ba3faa7c6dc892f9832a3"),
    "coverage.json": (29_402, "85441364285d36266455d36069c6af3fc9a78c8565d495dff7568a17a86d0184"),
    "entity-timelines.jsonl": (714_295, "56cfc32652f41000d4f50a5af862ee77de85e530b93646f6811f29d0c510620a"),
    "lifecycle-observations.csv": (315_739, "313af0129ce70586757a17d7b4ac99eed43e08214b0e185ef515930f02f99311"),
    "manifest.json": (3_632, MANIFEST_SHA256),
    "manifest.sha256": (80, "3820d68c6ea9bc300840e479a9fcd2d21888b3263070b3f0434aa2cd8b69c4b4"),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v4.py": (
        49_645,
        "744cd078036976b7fc02192be2fe1c64fa6e69faa1f064c1ab70b3912a837275",
    ),
    ROOT / "construction_timeline_v4.py": (
        151,
        "08bd4a60250c651d9a6c2a97658e5440de9d9b37fa8f227e34c39a0e758119e3",
    ),
    ROOT / "scripts/build_construction_timeline_v4.py": (
        1_435,
        "bebd50176ff344f78f29eee8802f34f1075f68643d365e61bfeb6440b4a17fc9",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV4Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v4 attempted network access")
        for name in (
            "socket", "create_connection", "getaddrinfo", "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_definition_bundle_inputs_and_code_pins_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(V3_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V68_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for path, expected in CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), expected)
        self.assertEqual(sha256(V3_DEFINITION), timeline.PREDECESSOR_DEFINITION_SHA256)
        self.assertEqual(sha256(V68_DEFINITION), timeline.OPEN_SEED_DEFINITION_SHA256)

    def test_exact_v3_rows_and_complete_v68_delta_are_preserved(self) -> None:
        predecessor = timeline.v3._parse_csv(V3_BUNDLE / timeline.OBSERVATIONS_FILENAME)
        current = timeline.v3._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (459, 472))
        for row in predecessor:
            self.assertEqual(current_by_id[row["observation_id"]], row)
        additions = [row for row in current if row["observation_id"] not in predecessor_ids]
        self.assertEqual(len(additions), 13)
        self.assertEqual(len({row["observation_id"] for row in additions}), 13)
        self.assertEqual(len({row["entity_stable_key"] for row in additions}), 13)
        self.assertEqual(
            {row["entity_stable_key"] for row in additions},
            set(timeline.PROJECT_SOURCE_BY_KEY),
        )
        self.assertEqual(timeline._event_contract(additions), timeline.V68_ADDITION_EVENT_CONTRACT)

        predecessor_timelines = timeline.v3._parse_jsonl(
            V3_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.v3._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        self.assertEqual((len(predecessor_timelines), len(current_timelines)), (443, 456))
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        for row in predecessor_timelines:
            self.assertEqual(current_by_key[row["entity_stable_key"]], row)
        new_timelines = [
            row for row in current_timelines
            if row["entity_stable_key"] in timeline.PROJECT_SOURCE_BY_KEY
        ]
        self.assertEqual(len(new_timelines), 13)
        self.assertTrue(all(row["observation_count"] == 1 for row in new_timelines))
        self.assertTrue(all(not row["has_status_change"] for row in new_timelines))

    def test_counts_order_freshness_and_noninference_are_exact(self) -> None:
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        rows = timeline.v3._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        timelines = timeline.v3._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(
            timeline.DELTA_CONTRACT,
            {
                "full_v68_raw_lifecycle_observations": 472,
                "inherited_observations": 459,
                "inherited_timelines": 443,
                "recorded_at_values_preserved_from_v3": True,
                "v68_added_lifecycle_observations": 13,
                "v68_added_project_entities": 13,
                "v68_inherited_recorded_at_rewrites_ignored": 74,
            },
        )
        self.assertEqual(
            Counter(event[11] for event in timeline.V68_ADDITION_EVENT_CONTRACT),
            {"recent_0_90_days": 12, "aging_91_365_days": 1},
        )
        self.assertEqual(Counter(row["entity_kind"] for row in rows), {"project": 389, "campus": 83})
        self.assertEqual(coverage["current_status_classification_counts"], {"unknown": 456})
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] is False
                and row["latest_observation_persistence_assumed"] is False
                for row in timelines
            )
        )
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])
        stt = coverage["stt_johor_historical_only"]
        self.assertEqual(stt["observation_age_days"], 512)
        self.assertEqual(stt["freshness_class"], "stale_over_365_days")
        self.assertEqual(stt["current_status_classification"], "unknown")
        self.assertFalse(stt["current_construction_claim"])

    def test_offline_double_reconstruction_is_byte_exact(self) -> None:
        frozen = {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        with tempfile.TemporaryDirectory(prefix="timeline-v4-rebuild-", dir="/private/tmp") as temporary:
            reproduced = Path(temporary) / BUNDLE.name
            with ExitStack() as stack:
                self._offline(stack)
                wrapped = timeline._prepare_payloads
                with patch.object(timeline, "_prepare_payloads", wraps=wrapped) as rebuild:
                    built = timeline.write_construction_timeline_bundle(DEFINITION, reproduced)
                self.assertGreaterEqual(rebuild.call_count, 3)
            self.assertEqual(built["counts"], timeline.EXPECTED_COUNTS)
            self.assertEqual(
                {path.name: path.read_bytes() for path in reproduced.iterdir()}, frozen
            )
        self.assertEqual({path.name: path.read_bytes() for path in BUNDLE.iterdir()}, frozen)

    def test_tamper_symlink_definition_and_collisions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="timeline-v4-fail-closed-", dir="/private/tmp") as temporary:
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
                timeline.validate_construction_timeline_bundle(copied, require_frozen=False)

            collision = root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(timeline.ConstructionTimelineError):
                timeline.write_construction_timeline_bundle(DEFINITION, collision)
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            symlink = root / "symlink"
            symlink.symlink_to(BUNDLE, target_is_directory=True)
            with self.assertRaises(timeline.ConstructionTimelineError):
                timeline.write_construction_timeline_bundle(DEFINITION, symlink)
            self.assertTrue(symlink.is_symlink())

            changed = json.loads(DEFINITION.read_text())
            changed = deepcopy(changed)
            changed["delta"]["v68_added_lifecycle_observations"] = 12
            bad_definition = root / "definition.json"
            bad_definition.write_bytes(timeline.v3._canonical_json(changed))
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "definition contract differs"
            ):
                timeline._load_definition(bad_definition)

    def test_cli_verify_inputs_and_both_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [
                sys.executable, "scripts/build_construction_timeline_v4.py",
                "--definition", str(DEFINITION), "--output-dir", str(BUNDLE),
                "--validate-only", "--verify-inputs",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["counts"], timeline.EXPECTED_COUNTS)
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.construction_timeline_v4 import "
            "validate_construction_timeline_bundle as v; "
            f"m=v(Path({str(BUNDLE)!r})); "
            "assert m['counts']['raw_lifecycle_observations']==472; "
            "assert m['counts']['entities_with_lifecycle_observations']==456; "
            "assert m['scope']['unique_physical_sites'] is None"
        )
        for working_directory in (ROOT, WORKSPACE):
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=working_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
