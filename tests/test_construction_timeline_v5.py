from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
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
    from datacenter_atlas.datacenter_atlas import construction_timeline_v5 as timeline
except ModuleNotFoundError:
    from datacenter_atlas import construction_timeline_v5 as timeline

from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v5.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v5"
V3_DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v3.json"
V3_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v3"
V71_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v71.json"
V71_RELEASE = ROOT / "releases/2026-07-21-open-seed-v71"

DEFINITION_PIN = (
    2_676,
    "f70f520e3ab887f0efea717c6850cb05dc26ce9b6b0697f96e0e6a9b8670a739",
)
MANIFEST_SHA256 = "aa378cde74d50b6016c5cd040a32a24e044489c0eb0fe9b412450d8abb038dba"
BUNDLE_TREE_SHA256 = "06ea50e5675c9931459fff09fd8bcfab92ebc3c0d9346fd5f5564fa65fa9641d"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        27_062,
        "6f62ca0e11cdf67afc3a102bc0b9b11f1bc58cb488b332eb4deb6fbd00acc711",
    ),
    "README.md": (
        1_098,
        "cf8999bf70d7c2ced4e10b4942dce04b72f0a975977ab2af23943518ca33cbee",
    ),
    "coverage.json": (
        31_650,
        "e7d61b3ae399aaae5bd062e73bad7251c57396a7a00a1c36061aa01d3fb0c3ca",
    ),
    "entity-timelines.jsonl": (
        717_504,
        "0804181e786ae3b2465c67a33d31b3146be0b34d88a60322745f20e8167a501b",
    ),
    "lifecycle-observations.csv": (
        317_215,
        "4c31bc5ce8d51020fbdeb7dc61a95cb1023f430ec432890ea570df96228db2a2",
    ),
    "manifest.json": (3_632, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "7eb4362ff47039e9d60e55719bc7cfd976847c8a65cf2cf650807b0cbd13ffa4",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v5.py": (
        60_977,
        "610833a77516b3747790f001a561583610d259536ee15f66192fa333614a2455",
    ),
    ROOT / "construction_timeline_v5.py": (
        151,
        "f5dd50327a7a4bbb08da8eb3ad70b20dfc6e7887feaa3f33f82ef9423efb26f8",
    ),
    ROOT / "scripts/build_construction_timeline_v5.py": (
        1_484,
        "a996f4bd319e2d34c5b12d3b539bf5b63f3960a8eef30d1e8bb1d87f5925ce0c",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV5Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v5 attempted network access")
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
        self.assertEqual(tree_digest(V3_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V71_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
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
        self.assertEqual(sha256(V71_DEFINITION), timeline.OPEN_SEED_DEFINITION_SHA256)

    def test_exact_v3_rows_and_complete_v71_delta_are_preserved(self) -> None:
        predecessor = timeline.v3._parse_csv(V3_BUNDLE / timeline.OBSERVATIONS_FILENAME)
        current = timeline.v3._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (459, 474))
        for row in predecessor:
            self.assertEqual(current_by_id[row["observation_id"]], row)
        additions = [row for row in current if row["observation_id"] not in predecessor_ids]
        self.assertEqual(len(additions), 15)
        self.assertEqual(len({row["observation_id"] for row in additions}), 15)
        self.assertEqual(len({row["entity_stable_key"] for row in additions}), 15)
        self.assertEqual(
            {row["entity_stable_key"] for row in additions},
            set(timeline.PROJECT_SOURCE_BY_KEY),
        )
        self.assertEqual(
            timeline._event_contract(additions),
            timeline.V71_ADDITION_EVENT_CONTRACT,
        )

        predecessor_timelines = timeline.v3._parse_jsonl(
            V3_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.v3._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        self.assertEqual((len(predecessor_timelines), len(current_timelines)), (443, 458))
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        for row in predecessor_timelines:
            self.assertEqual(current_by_key[row["entity_stable_key"]], row)
        new_timelines = [
            row
            for row in current_timelines
            if row["entity_stable_key"] in timeline.PROJECT_SOURCE_BY_KEY
        ]
        self.assertEqual(len(new_timelines), 15)
        self.assertTrue(all(row["observation_count"] == 1 for row in new_timelines))
        self.assertTrue(all(not row["has_status_change"] for row in new_timelines))

    def test_counts_freshness_and_noninference_are_exact(self) -> None:
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        rows = timeline.v3._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        timelines = timeline.v3._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(
            Counter(event[11] for event in timeline.V71_ADDITION_EVENT_CONTRACT),
            {
                "recent_0_90_days": 12,
                "aging_91_365_days": 2,
                "stale_over_365_days": 1,
            },
        )
        self.assertEqual(Counter(row["entity_kind"] for row in rows), {"project": 391, "campus": 83})
        self.assertEqual(coverage["current_status_classification_counts"], {"unknown": 458})
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] is False
                and row["latest_observation_persistence_assumed"] is False
                for row in timelines
            )
        )
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])
        arnes = next(
            row
            for row in timelines
            if row["entity_stable_key"]
            == "curated:arnes-maribor-data-center-site:source-scoped-development"
        )
        self.assertTrue(arnes["single_old_observation_current_unknown"])
        self.assertFalse(arnes["current_construction_claim"])
        events = {row["entity_stable_key"]: row for row in coverage["v71_addition_events"]}
        arnes_event = events[arnes["entity_stable_key"]]
        self.assertEqual(arnes_event["observation_age_days"], 441)
        self.assertEqual(arnes_event["freshness_class"], "stale_over_365_days")
        kio = events[
            "curated:kio-tec-guatemala-campus:second-data-center"
        ]
        self.assertEqual(kio["observation_age_days"], 299)
        self.assertEqual(kio["freshness_class"], "aging_91_365_days")
        kio_timeline = next(
            row
            for row in timelines
            if row["entity_stable_key"]
            == "curated:kio-tec-guatemala-campus:second-data-center"
        )
        self.assertFalse(kio_timeline["single_old_observation_current_unknown"])

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
        with self.assertRaisesRegex(
            timeline.ConstructionTimelineError,
            "already exists",
        ):
            timeline.publish_construction_timeline_v5()
        self.assertEqual(DEFINITION.read_bytes(), frozen_definition)
        self.assertEqual((BUNDLE / timeline.MANIFEST_FILENAME).read_bytes(), frozen_manifest)

        with tempfile.TemporaryDirectory(
            prefix="timeline-v5-fail-closed-",
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

            definition_symlink = root / "definition-link.json"
            definition_symlink.symlink_to(DEFINITION)
            with self.assertRaises(timeline.ConstructionTimelineError):
                timeline._load_definition(definition_symlink)

    def test_definition_has_only_accepted_lineage(self) -> None:
        document = json.loads(DEFINITION.read_text())
        serialized = json.dumps(document, sort_keys=True)
        self.assertEqual(document, timeline._definition_document())
        self.assertIn("open-seed-2026-07-21-v71", serialized)
        self.assertIn("construction-timeline-2026-07-21-public-open-v3", serialized)
        for rejected in (
            "open-seed-2026-07-21-v68",
            "construction-timeline-2026-07-21-public-open-v4",
        ):
            self.assertNotIn(rejected, serialized)

        changed = deepcopy(document)
        changed["predecessor"]["bundle_path"] = (
            "../construction_timelines/2026-07-21-public-open-v4"
        )
        descriptor, name = tempfile.mkstemp(prefix=".timeline-v5-bad-", dir=DEFINITION.parent)
        os.close(descriptor)
        bad_definition = Path(name)
        try:
            bad_definition.write_bytes(timeline.v3._canonical_json(changed))
            with self.assertRaises(timeline.ConstructionTimelineError):
                timeline._load_definition(bad_definition)
        finally:
            bad_definition.unlink(missing_ok=True)

    def test_cli_and_both_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/build_construction_timeline_v5.py",
                "--definition",
                str(DEFINITION),
                "--output-dir",
                str(BUNDLE),
                "--validate-only",
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
            "from datacenter_atlas.construction_timeline_v5 import "
            "validate_construction_timeline_bundle as v; "
            f"m=v(Path({str(BUNDLE)!r})); "
            "assert m['counts']['raw_lifecycle_observations']==474; "
            "assert m['counts']['entities_with_lifecycle_observations']==458; "
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
