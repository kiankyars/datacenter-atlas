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

from datacenter_atlas.datacenter_atlas import construction_timeline_v9 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v9.json"
BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v9"
V8_DEFINITION = ROOT / "sources/construction-timeline-2026-07-21-public-open-v8.json"
V8_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v8"
V87_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v87.json"
V87_RELEASE = ROOT / "releases/2026-07-21-open-seed-v87"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v36.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v36"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v12.json"
)
IDENTITY_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v12"

DEFINITION_PIN = (
    3_981,
    "fe5d4ff2d842e00911ffd352b6d6416e9164a00b03950ef33fe88927a4e7eb35",
)
MANIFEST_SHA256 = "d4ce768af05b6a5ea0a4b955f5fb2a3a38dad98b5fa383655d762491982e0fae"
BUNDLE_TREE_SHA256 = "de8ddc533922852ee39e901d01552174bc2367fe8532ebf065bb5389f577f227"
ARTIFACTS = {
    "ATTRIBUTION.txt": (
        34_879,
        "e912aa5c60cd145167b0cfe42902be77c5fbe8e0f54b5f7fa9d83871d36c117e",
    ),
    "README.md": (
        1_432,
        "232d90f552c606f745e43c0af8875e162a7f4f327bd6e79903a194eb112940ac",
    ),
    "coverage.json": (
        56_178,
        "91bfd4dd4885cca168859a3d2bb7b603e55bf48620ae4b5d7ef6cb52e3aaeb8c",
    ),
    "entity-timelines.jsonl": (
        819_292,
        "e17c2aa2112b22d88b241576bd656f767a34414565bb84c47e1b51de231431f4",
    ),
    "lifecycle-observations.csv": (
        363_513,
        "b9c093a094037090ce4aa508edb638f36cc2d30dd084c505cc589f19de2a0634",
    ),
    "manifest.json": (5_094, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "16356f6dbd6f466e65d4eae0b46d7b91283dc1ec96d823f1afde44b607e10f01",
    ),
}
CODE_PINS = {
    ROOT / "datacenter_atlas/construction_timeline_v9.py": (
        71_108,
        "d242575beb38fc053a3835b74f12abb7163b0da9237f7e7376fc83f8b548fd2a",
    ),
    ROOT / "construction_timeline_v9.py": (
        331,
        "deabbd79d24347f28c747472d26fd2254701a2ac57978d622a7073b4545c3b4e",
    ),
    ROOT / "scripts/build_construction_timeline_v9.py": (
        1_498,
        "e26f51e007d0e875bead43944383da67c63476cc120c3fb59c23b3c6ec8fbe3f",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV9Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v9 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_artifacts_code_and_all_four_input_pins_are_exact(self) -> None:
        self.assertEqual((DEFINITION.stat().st_size, sha256(DEFINITION)), DEFINITION_PIN)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o444)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for path, expected in CODE_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), expected)

        self.assertEqual(tree_digest(V8_BUNDLE), timeline.PREDECESSOR_TREE_SHA256)
        self.assertEqual(tree_digest(V87_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION_BUNDLE), timeline.FEDERATION_TREE_SHA256)
        self.assertEqual(tree_digest(IDENTITY_BUNDLE), timeline.IDENTITY_TREE_SHA256)
        self.assertEqual(
            (V8_DEFINITION.stat().st_size, sha256(V8_DEFINITION)),
            timeline.PREDECESSOR_DEFINITION_PIN,
        )
        self.assertEqual(
            (V87_DEFINITION.stat().st_size, sha256(V87_DEFINITION)),
            timeline.OPEN_SEED_DEFINITION_PIN,
        )
        self.assertEqual(
            (FEDERATION_DEFINITION.stat().st_size, sha256(FEDERATION_DEFINITION)),
            timeline.FEDERATION_DEFINITION_PIN,
        )
        self.assertEqual(
            (IDENTITY_DEFINITION.stat().st_size, sha256(IDENTITY_DEFINITION)),
            timeline.IDENTITY_DEFINITION_PIN,
        )

    def test_all_v8_rows_are_byte_exact_and_delta_is_exactly_four(self) -> None:
        predecessor = timeline.CODEC._parse_csv(
            V8_BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        current = timeline.CODEC._parse_csv(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        predecessor_ids = {row["observation_id"] for row in predecessor}
        current_by_id = {row["observation_id"]: row for row in current}
        self.assertEqual((len(predecessor), len(current)), (537, 541))
        for row in predecessor:
            inherited = current_by_id[row["observation_id"]]
            self.assertEqual(inherited, row)
            self.assertEqual(
                timeline.CODEC._csv_bytes([inherited]),
                timeline.CODEC._csv_bytes([row]),
            )
        additions = [
            row for row in current if row["observation_id"] not in predecessor_ids
        ]
        self.assertEqual(
            {
                (row["entity_stable_key"], row["status"], row["observed_date"])
                for row in additions
            },
            {
                (
                    "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit",
                    "under_construction",
                    "2026-01-16",
                ),
                (
                    "curated:riot-rockdale-site:amd-lease-first-phase",
                    "operational",
                    "2026-01-31",
                ),
                (
                    "curated:databank-lithia-springs-campus:atl5-current-build",
                    "under_construction",
                    "2026-05-07",
                ),
                (
                    "curated:databank-lithia-springs-campus:atl6-current-build",
                    "under_construction",
                    "2026-05-07",
                ),
            },
        )
        contract = timeline._event_contract(additions)
        self.assertEqual(
            timeline._event_contract_sha256(contract),
            timeline.V87_ADDITION_EVENT_CONTRACT_SHA256,
        )

        predecessor_timelines = timeline.CODEC._parse_jsonl(
            V8_BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_timelines = timeline.CODEC._parse_jsonl(
            BUNDLE / timeline.TIMELINES_FILENAME
        )
        current_by_key = {row["entity_stable_key"]: row for row in current_timelines}
        self.assertEqual((len(predecessor_timelines), len(current_timelines)), (517, 521))
        for row in predecessor_timelines:
            inherited = current_by_key[row["entity_stable_key"]]
            self.assertEqual(inherited, row)
            self.assertEqual(
                timeline.CODEC._canonical_json_line(inherited),
                timeline.CODEC._canonical_json_line(row),
            )

    def test_counts_lineage_split_closure_and_noninference_are_exact(self) -> None:
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        coverage = json.loads((BUNDLE / timeline.COVERAGE_FILENAME).read_text())
        observations = timeline.CODEC._parse_csv(
            BUNDLE / timeline.OBSERVATIONS_FILENAME
        )
        timelines = timeline.CODEC._parse_jsonl(BUNDLE / timeline.TIMELINES_FILENAME)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(
            coverage["lifecycle_row_linked_source_family_count"], 253
        )
        self.assertEqual(coverage["lineage_aware_source_family_count"], 254)
        self.assertEqual(
            coverage["v87_delta_new_row_linked_source_families"],
            ["riot_platforms_company_news"],
        )
        self.assertEqual(
            coverage["v87_delta_new_lineage_source_families"],
            ["databank_facility_pages", "riot_platforms_company_news"],
        )
        self.assertEqual(
            Counter(row["evidence_source_family"] for row in observations)[
                "databank_official_linkedin"
            ],
            4,
        )
        self.assertNotIn(
            "databank_facility_pages",
            {row["evidence_source_family"] for row in observations},
        )
        self.assertEqual(
            Counter(row["status"] for row in observations)["operational"], 49
        )
        self.assertEqual(
            Counter(row["status"] for row in observations)["under_construction"],
            376,
        )
        self.assertEqual(
            Counter(row["entity_kind"] for row in observations),
            {"project": 458, "campus": 83},
        )
        self.assertEqual(
            Counter(row["entity_kind"] for row in timelines),
            {"project": 438, "campus": 83},
        )
        self.assertTrue(
            all(
                row["current_status_classification"] == "unknown"
                and row["current_construction_claim"] is False
                and row["latest_observation_persistence_assumed"] is False
                for row in timelines
            )
        )
        closures = coverage["v9_delta_operational_lifecycle_closures"]
        self.assertEqual(
            {row["entity_stable_key"] for row in closures},
            timeline.OPERATIONAL_CLOSURE_KEYS,
        )
        self.assertTrue(
            all(
                row["current_operational_claim"] is False
                and row["current_status_classification"] == "unknown"
                for row in closures
            )
        )
        self.assertEqual(
            coverage["v9_delta_inference_guardrails"], timeline.INFERENCE_GUARDRAILS
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

    def test_future_clock_no_replace_rollback_and_residue_fail_closed(self) -> None:
        generated = timeline._parse_utc(timeline.GENERATED_AT, label="generated_at")
        timeline.validate_construction_timeline_bundle(BUNDLE)
        for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
            metadata = path.stat()
            self.assertLessEqual(
                metadata.st_birthtime, generated.timestamp() + 0.000_001
            )
            self.assertLessEqual(metadata.st_mtime, generated.timestamp() + 0.000_001)
        for root in (DEFINITION, BUNDLE):
            self.assertGreaterEqual(root.stat().st_ctime + 0.000_001, generated.timestamp())
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

        frozen_definition = DEFINITION.read_bytes()
        frozen_manifest = (BUNDLE / timeline.MANIFEST_FILENAME).read_bytes()
        with self.assertRaisesRegex(timeline.ConstructionTimelineError, "already exists"):
            timeline.publish_construction_timeline_v9()
        self.assertEqual(DEFINITION.read_bytes(), frozen_definition)
        self.assertEqual((BUNDLE / timeline.MANIFEST_FILENAME).read_bytes(), frozen_manifest)

        with tempfile.TemporaryDirectory(
            prefix="timeline-v9-publication-contract-", dir="/private/tmp"
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
            self.assertEqual(
                (bundle_stage / "manifest.json").read_bytes(), b"manifest\n"
            )

    def test_tamper_lineage_definition_and_cli_fail_closed(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(
            definition["predecessor"]["definition"]["path"], V8_DEFINITION.name
        )
        self.assertEqual(
            definition["open_seed"]["definition"]["path"], V87_DEFINITION.name
        )
        self.assertEqual(
            definition["federation"]["definition"]["path"],
            FEDERATION_DEFINITION.name,
        )
        self.assertEqual(
            definition["exact_identity"]["definition"]["path"],
            IDENTITY_DEFINITION.name,
        )
        self.assertEqual(
            timeline._identity_source_family_contract(),
            {
                "curated:databank-lithia-springs-campus:atl5-current-build": "databank_facility_pages",
                "curated:databank-lithia-springs-campus:atl6-current-build": "databank_facility_pages",
                "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit": "riot_platforms_company_news",
                "curated:riot-rockdale-site:amd-lease-first-phase": "riot_platforms_company_news",
            },
        )

        with tempfile.TemporaryDirectory(
            prefix="timeline-v9-fail-closed-", dir="/private/tmp"
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
                    copied, require_frozen=False, verify_publication_times=False
                )

        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_construction_timeline_v9.py"),
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
