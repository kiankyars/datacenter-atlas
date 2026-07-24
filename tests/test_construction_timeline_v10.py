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

from datacenter_atlas.datacenter_atlas import construction_timeline_v10 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v10.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v10"
V9_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v9"

DEFINITION_PIN = (
    7_042,
    "8c06566529d45cd209fb9f055a69b5146e79bbc1f83f15e9cbf9060a66cbf333",
)
MANIFEST_SHA256 = "c2fa0fb5041ebdea9ec320f5d922833bf53574f5efe6091db79e1db6cc304e28"
BUNDLE_TREE_SHA256 = "6e4a42092f26736ad0db89c06259d419d7156c4e516a5dfb20a13507e2cafb9a"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        37_018,
        "c55ba494768008c3ed7217f9400242f9ff886280a36bd8867db37074651d19ca",
    ),
    "README.md": (
        974,
        "d187db09d351041414307d2be542cf64f6e2d3f031e6ffdbc97a25d88709d02c",
    ),
    "coverage.json": (
        85_542,
        "cdffa52492b2e5bde65718335624f75a3d335a59ef9b8084dd2b8ac7c723efe0",
    ),
    "entity-timelines.jsonl": (
        865_249,
        "ea2d516e96651c92d89f8e6a4852f10be690b23a5027f76c654654e1c53e26e1",
    ),
    "lifecycle-observations.csv": (
        384_119,
        "346bfe15c585758b29ce28492c4d04cbb2f02067bdef884a6ea326b045f033d8",
    ),
    "manifest.json": (8_279, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "8ea97667f530ede6b2e76f04c19fd6a3f158d07aa92a11dd2cdc9ee270b29b14",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v10.py": (
        60_584,
        "2d22ec31de3a4e50ec743ad4657a47deefff2e11ce9c9975dd3baa8ea25acd07",
    ),
    ROOT / "construction_timeline_v10.py": (
        387,
        "ac2bf730345a14e981fe6801400a2cf187100f849a6015ee6456c6cad6f19fde",
    ),
    ROOT / "scripts/build_construction_timeline_v10.py": (
        1_485,
        "c8d91f78592b776f8e6e6cbc1dea2837339c68734df9284dafc25a5789afb663",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV10Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v10 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_artifacts_code_and_all_input_pins_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
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
        self.assertEqual(tree_digest(V9_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        for spec in timeline.RELEASE_SPECS:
            self.assertEqual(tree_digest(spec.release), spec.tree_sha256)
            self.assertEqual(
                (spec.definition.stat().st_size, sha256(spec.definition)),
                spec.definition_pin,
            )
            self.assertEqual(
                (
                    (spec.release / "manifest.json").stat().st_size,
                    sha256(spec.release / "manifest.json"),
                ),
                spec.manifest_pin,
            )

    def test_every_v9_row_is_exact_and_delta_is_exactly_30(self) -> None:
        predecessor = timeline.CODEC._parse_csv(
            V9_BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        current = timeline.CODEC._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (541, 571))
        for row in predecessor:
            inherited = current_by_id[row["observation_id"]]
            self.assertEqual(inherited, row)
            self.assertEqual(
                timeline.CODEC._csv_bytes([inherited]),
                timeline.CODEC._csv_bytes([row]),
            )
        additions = [row for row in current if row["observation_id"] not in predecessor_ids]
        self.assertEqual(len(additions), 30)
        self.assertEqual(len({row["entity_stable_key"] for row in additions}), 29)
        self.assertEqual(
            Counter(row["status"] for row in additions),
            {"under_construction": 26, "site_preparation": 2, "shell": 2},
        )

        predecessor_timelines = timeline.CODEC._parse_jsonl(
            V9_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.CODEC._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        self.assertEqual((len(predecessor_timelines), len(current_timelines)), (521, 550))
        for row in predecessor_timelines:
            inherited = current_by_key[row["entity_stable_key"]]
            self.assertEqual(inherited, row)
            self.assertEqual(
                timeline.CODEC._canonical_json_line(inherited),
                timeline.CODEC._canonical_json_line(row),
            )
        austin = current_by_key[timeline.SABEY_AUSTIN_KEY]
        self.assertEqual(
            [(row["observed_date"], row["status"]) for row in austin["observations"]],
            [("2025-07-29", "under_construction"), ("2026-06-16", "shell")],
        )
        self.assertTrue(austin["has_status_change"])
        self.assertEqual(austin["current_status_classification"], "unknown")

    def test_counts_release_clocks_transitions_and_noninference_are_exact(self) -> None:
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(
            coverage["open_seed_release_event_counts"],
            timeline.RELEASE_ADDITION_COUNTS,
        )
        self.assertEqual(
            coverage["v10_addition_event_contract_sha256"],
            timeline.ADDITION_EVENT_CONTRACT_SHA256,
        )
        events = coverage["v10_addition_events"]
        recorded = {
            spec.release_id: spec.recorded_at for spec in timeline.RELEASE_SPECS
        }
        self.assertTrue(
            all(row["recorded_at"] == recorded[row["source_release_id"]] for row in events)
        )
        self.assertEqual(
            Counter(row["source_release_id"] for row in events),
            timeline.RELEASE_ADDITION_COUNTS,
        )
        self.assertEqual(
            coverage["v10_authoritative_status_transitions"],
            [
                {
                    "closed_at": "2026-06-16",
                    "current_status_classification": "unknown",
                    "entity_stable_key": timeline.SABEY_AUSTIN_KEY,
                    "from_observed_date": "2025-07-29",
                    "from_status": "under_construction",
                    "raw_valid_to_date_rewritten": False,
                    "to_status": "shell",
                    "transition_semantics": "closed_by_later_authoritative_observation",
                }
            ],
        )
        self.assertEqual(coverage["v10_delta_operational_lifecycle_closures"], [])
        self.assertEqual(
            coverage["v10_delta_inference_guardrails"], timeline.INFERENCE_GUARDRAILS
        )
        self.assertEqual(coverage["current_status_classification_counts"], {"unknown": 550})
        self.assertEqual(coverage["observation_entity_kind_counts"], {"campus": 83, "project": 488})
        self.assertEqual(coverage["timeline_entity_kind_counts"], {"campus": 83, "project": 467})

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

    def test_all_member_chronology_no_replace_rollback_and_residue(self) -> None:
        generated = timeline._parse_utc(timeline.GENERATED_AT, label="generated_at")
        timeline.validate_construction_timeline_bundle(BUNDLE)
        for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
            metadata = path.stat()
            self.assertLessEqual(metadata.st_birthtime, generated.timestamp() + 0.000_001)
            self.assertLessEqual(metadata.st_mtime, generated.timestamp() + 0.000_001)
            self.assertGreaterEqual(metadata.st_ctime + 0.000_001, generated.timestamp())
        with self.assertRaisesRegex(
            timeline.ConstructionTimelineError, "exceeds validation wall clock"
        ):
            timeline.validate_construction_timeline_bundle(
                BUNDLE, validation_wall_clock=generated - timedelta(seconds=1)
            )
        self.assertFalse(timeline.PUBLICATION_LOCK.exists())
        self.assertFalse(list(DEFINITION.parent.glob(f".{DEFINITION.name}.private-stage-*")))
        self.assertFalse(list(BUNDLE.parent.glob(f".{BUNDLE.name}.private-stage-*")))

        frozen_definition = DEFINITION.read_bytes()
        frozen_manifest = (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes()
        with self.assertRaisesRegex(timeline.ConstructionTimelineError, "already exists"):
            timeline.publish_construction_timeline_v10()
        self.assertEqual(DEFINITION.read_bytes(), frozen_definition)
        self.assertEqual((BUNDLE / timeline.MANIFEST_FILENAME).read_bytes(), frozen_manifest)

        with tempfile.TemporaryDirectory(
            prefix="timeline-v10-publication-contract-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            collision = root / "collision"
            stage.write_bytes(b"staged\n")
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(SystemExit):
                timeline.promote_noreplace(stage, collision)
            self.assertEqual(stage.read_bytes(), b"staged\n")
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            final_definition = root / "published-definition"
            final_bundle = root / "published-bundle"
            definition_stage = root / "definition-stage"
            bundle_stage = root / "bundle-stage"
            final_definition.write_bytes(b"definition\n")
            final_bundle.mkdir()
            (final_bundle / "manifest.json").write_bytes(b"manifest\n")
            with (
                patch.object(timeline, "DEFINITION", final_definition),
                patch.object(timeline, "BUNDLE", final_bundle),
            ):
                timeline._rollback_published(
                    definition_stage,
                    bundle_stage,
                    definition_published=True,
                    bundle_published=True,
                )
            self.assertFalse(final_definition.exists())
            self.assertFalse(final_bundle.exists())
            self.assertEqual(definition_stage.read_bytes(), b"definition\n")
            self.assertEqual((bundle_stage / "manifest.json").read_bytes(), b"manifest\n")

    def test_tamper_definition_and_cli_fail_closed(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(definition["predecessor"]["definition"]["path"], timeline.PREDECESSOR_DEFINITION.name)
        self.assertEqual(
            [row["release_id"] for row in definition["open_seed_inputs"]],
            [spec.release_id for spec in timeline.RELEASE_SPECS],
        )
        with tempfile.TemporaryDirectory(
            prefix="timeline-v10-fail-closed-", dir="/private/tmp"
        ) as temporary:
            copied = Path(temporary) / "tampered"
            shutil.copytree(BUNDLE, copied)
            copied.chmod(0o755)
            observations = copied / timeline.OBSERVATIONS_FILENAME
            observations.chmod(0o644)
            observations.write_bytes(observations.read_bytes() + b"tamper\n")
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "checkpoint differs"
            ):
                timeline.validate_construction_timeline_bundle(
                    copied,
                    require_frozen=False,
                    verify_publication_times=False,
                )

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_construction_timeline_v10.py"),
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
