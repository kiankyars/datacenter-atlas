from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_timeline_v2 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-20-public-open-v2.json"
)
BUNDLE = ROOT / "construction_timelines/2026-07-20-public-open-v2"
V1_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-20-public-open-v1.json"
)
V1_BUNDLE = ROOT / "construction_timelines/2026-07-20-public-open-v1"
V62_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"

DEFINITION_SHA256 = (
    "ca48de509f23a0ba0b856bab8815a1872594840e0a83cf9dba09c37133b5909a"
)
MANIFEST_SHA256 = (
    "ab8e798b1b0d2d25ec43744e935565603f8ce138d7d820038ad838702b3b28a7"
)
BUNDLE_TREE_SHA256 = (
    "c0e0db549f8336c012da31a997797814b368b87bae4c42a6173597e920e6b8e3"
)

V1_PINS = {
    V1_DEFINITION: (
        1_672,
        "b7e04ec1915c1527bcb8cd3c7c08dad561b3bde5bdfe668cb5f6defaa14c0e7d",
        0o644,
    ),
    V1_BUNDLE / "manifest.json": (
        2_560,
        "610b4058593e2d426faf4560799b9c1335711105c35b0bd839f0bcb06539f4fd",
        0o444,
    ),
    ROOT / "datacenter_atlas/construction_timeline_v1.py": (
        38_407,
        "c75520069a8f098e6be447891954f6b9bd9c0d0c4bff5b6adb20254c18430a3b",
        0o644,
    ),
}
V1_TREE_SHA256 = (
    "29f5f724089d8a2eafce69cfb6cfd193d6547dbd21efbca1e89945b4557e39b2"
)

V62_PINS = {
    V62_DEFINITION: (
        76_824,
        "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66",
        0o644,
    ),
    V62_RELEASE / "manifest.json": (
        10_934,
        "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6",
        0o444,
    ),
    ROOT / "datacenter_atlas/open_seed_v62.py": (
        35_067,
        "193cb815dd2e632e7eddcefb3941117f77253b658f2fc9c8dbbad6a6134a2605",
        0o644,
    ),
    ROOT / "datacenter_atlas/open_seed_release_v7.py": (
        15_835,
        "c406d53b0e0723b357b2b46221f86a6b7fbefa0a485eaf800801d70dbd11878d",
        0o644,
    ),
}

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        23_529,
        "80af0d0b94a53c0f936f69c58df49b926c3b6fe0adb767dcdae505b4a42b95d2",
    ),
    "README.md": (
        1_770,
        "5d698fc9041e55ecfa6f87a231e6d41673d86e82feea0392891d8dd7ecd5df19",
    ),
    "coverage.json": (
        15_549,
        "5efd3232be48db56b307f9d027f5d7f118ac02691e2caa3f3339eb75d358afe6",
    ),
    "entity-timelines.jsonl": (
        650_489,
        "08034b6031a4adbad0e79d98265d1552dc64ec1830364ef5456c28258c61f6ea",
    ),
    "lifecycle-observations.csv": (
        287_744,
        "67033bdc44b59dbbdcddddde595383450a72a5fcf18c669f579aa121ca019091",
    ),
    "manifest.json": (2_560, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "1f96e71aa2359069e488035a439740a35d00a6958767bff2691ec53b30b592b9",
    ),
}

QAREEB_KEY = (
    "curated:batelco-qareeb-beyon-data-oasis-edge-data-center:facility-build"
)
APPLIED_PARENT_KEY = (
    "curated:applied-digital-polaris-forge-1:second-150mw-facility"
)
APPLIED_PHASE_KEY = f"{APPLIED_PARENT_KEY}:phase-1"
DATABANK_KEY = "curated:databank-culpeper-campus:iad5-current-build"
STC_KEY = "curated:stc-bahrain-data-center:facility-build"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class ConstructionTimelineV2Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline v2 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_trees_and_predecessor_preservation(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(V1_BUNDLE), V1_TREE_SHA256)
        self.assertEqual(tree_digest(V62_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(stat.S_IMODE(V1_BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(stat.S_IMODE(V62_RELEASE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for pins in (V1_PINS, V62_PINS):
            for path, (size, digest, mode) in pins.items():
                self.assertEqual((path.stat().st_size, sha256(path)), (size, digest))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_exact_v1_history_successor_and_four_observation_delta(self) -> None:
        predecessor = csv_rows(V1_BUNDLE / timeline.OBSERVATIONS_FILENAME)
        current = csv_rows(BUNDLE / timeline.OBSERVATIONS_FILENAME)
        self.assertEqual((len(predecessor), len(current)), (426, 430))
        predecessor_ids = Counter(row["observation_id"] for row in predecessor)
        current_ids = Counter(row["observation_id"] for row in current)
        self.assertFalse(predecessor_ids - current_ids)
        added = current_ids - predecessor_ids
        added_rows = [row for row in current if row["observation_id"] in added]
        self.assertEqual(
            Counter(row["entity_stable_key"] for row in added_rows),
            Counter(
                {
                    QAREEB_KEY: 2,
                    APPLIED_PHASE_KEY: 1,
                    DATABANK_KEY: 1,
                }
            ),
        )
        predecessor_events = Counter(
            (row["entity_stable_key"], row["observed_date"], row["status"])
            for row in predecessor
        )
        current_events = Counter(
            (row["entity_stable_key"], row["observed_date"], row["status"])
            for row in current
        )
        self.assertFalse(predecessor_events - current_events)
        self.assertEqual(len({row["entity_id"] for row in current}), 415)
        self.assertEqual(len({row["evidence_source_family"] for row in current}), 178)
        for row in current:
            for field in (
                "entity_stable_key",
                "entity_kind",
                "entity_name",
                "entity_country",
                "observed_date",
                "status",
                "method",
                "confidence",
                "recorded_at",
                "evidence_id",
                "evidence_kind",
                "evidence_source_family",
                "evidence_title",
                "evidence_source_url",
                "evidence_retrieved_at",
                "evidence_content_hash",
            ):
                self.assertTrue(row[field], (row["observation_id"], field))
        self.assertEqual({row["superseded_at"] for row in current}, {""})

    def test_focus_histories_and_capacity_identity_boundaries(self) -> None:
        timelines = [
            json.loads(line)
            for line in (BUNDLE / timeline.TIMELINES_FILENAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        by_key = {row["entity_stable_key"]: row for row in timelines}

        def events(stable_key: str) -> list[tuple[str, str]]:
            return [
                (item["observed_date"], item["status"])
                for item in by_key[stable_key]["observations"]
            ]

        self.assertEqual(
            events(QAREEB_KEY),
            [
                ("2025-02-05", "under_construction"),
                ("2026-01-13", "commissioning"),
            ],
        )
        self.assertEqual(
            events(STC_KEY),
            [
                ("2024-12-31", "under_construction"),
                ("2025-12-31", "operational"),
            ],
        )
        self.assertEqual(events(APPLIED_PARENT_KEY), [("2026-04-08", "under_construction")])
        self.assertEqual(events(APPLIED_PHASE_KEY), [("2026-07-01", "operational")])
        self.assertNotEqual(
            by_key[APPLIED_PARENT_KEY]["entity_id"],
            by_key[APPLIED_PHASE_KEY]["entity_id"],
        )
        self.assertEqual(events(DATABANK_KEY), [("2026-05-14", "under_construction")])

        coverage = json.loads(
            (BUNDLE / timeline.COVERAGE_FILENAME).read_text(encoding="utf-8")
        )
        self.assertEqual(coverage["v62_focus_contract"], timeline.V62_FOCUS_CONTRACT)
        self.assertEqual(
            coverage["v62_focus_contract"]["applied_digital_parent"]["critical_it_mw"],
            150.0,
        )
        self.assertEqual(
            coverage["v62_focus_contract"]["applied_digital_phase_1_child"]["critical_it_mw"],
            75.0,
        )
        self.assertEqual(
            coverage["v62_focus_contract"]["databank_iad5"]["critical_it_mw"],
            72.0,
        )

    def test_counts_scope_and_current_unknown_guardrails(self) -> None:
        coverage = json.loads(
            (BUNDLE / timeline.COVERAGE_FILENAME).read_text(encoding="utf-8")
        )
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["observation_entity_kind_counts"], {
            "campus": 83,
            "project": 347,
        })
        self.assertEqual(coverage["timeline_entity_kind_counts"], {
            "campus": 83,
            "project": 332,
        })
        self.assertEqual(coverage["observation_status_counts"], {
            "announced": 6,
            "civil_works": 2,
            "commissioning": 2,
            "expansion": 29,
            "foundations": 2,
            "mep_electrical": 19,
            "operational": 42,
            "permitted": 3,
            "proposed": 2,
            "shell": 27,
            "site_control": 1,
            "site_preparation": 13,
            "under_construction": 282,
        })
        self.assertEqual(coverage["current_status_classification_counts"], {
            "unknown": 415,
        })
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])
        for field in (
            "cross_source_identity_resolution_applied",
            "current_construction_claimed",
            "forecast_conversion_applied",
            "interpolation_applied",
            "latest_observation_persistence_assumed",
            "quarterly_2017_2032_parity_claimed",
            "satellite_cv_promoted_to_lifecycle",
        ):
            self.assertFalse(coverage["scope"][field], field)

        timelines = [
            json.loads(line)
            for line in (BUNDLE / timeline.TIMELINES_FILENAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(len(timelines), 415)
        self.assertEqual(sum(row["observation_count"] for row in timelines), 430)
        self.assertEqual(sum(row["has_multiple_observations"] for row in timelines), 15)
        self.assertEqual(sum(row["has_status_change"] for row in timelines), 11)
        self.assertEqual(
            sum(row["single_old_observation_current_unknown"] for row in timelines),
            24,
        )
        for row in timelines:
            self.assertEqual(row["current_status_classification"], "unknown")
            self.assertFalse(row["current_construction_claim"])
            self.assertFalse(row["latest_observation_persistence_assumed"])

    def test_offline_exact_replay_and_double_rebuild(self) -> None:
        with ExitStack() as stack:
            self._offline(stack)
            validated = timeline.validate_construction_timeline_bundle(
                BUNDLE,
                definition_path=DEFINITION,
                verify_inputs=True,
            )
            self.assertEqual(validated["counts"], timeline.EXPECTED_COUNTS)
            with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
                output = Path(temporary) / "timeline-v2"
                rebuilt = timeline.write_construction_timeline_bundle(
                    DEFINITION, output
                )
                self.assertEqual(rebuilt, validated)
                self.assertEqual(tree_digest(output), BUNDLE_TREE_SHA256)

    def test_collision_tamper_definition_and_symlink_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_path = Path(temporary)
            collision = temporary_path / "collision"
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_text("preserve\n", encoding="utf-8")
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "refusing overwrite"
            ):
                timeline.write_construction_timeline_bundle(DEFINITION, collision)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")

            tampered = temporary_path / "tampered"
            shutil.copytree(BUNDLE, tampered)
            tampered.chmod(0o755)
            target = tampered / timeline.OBSERVATIONS_FILENAME
            target.chmod(0o644)
            target.write_bytes(
                target.read_bytes().replace(
                    b"commissioning", b"commissioninG", 1
                )
            )
            for path in tampered.iterdir():
                path.chmod(0o444)
            tampered.chmod(0o555)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "checkpoint differs"
            ):
                timeline.validate_construction_timeline_bundle(tampered)

            document = json.loads(DEFINITION.read_text(encoding="utf-8"))
            document["open_seed"]["expected_release_tree_sha256"] = "0" * 64
            altered_definition = temporary_path / DEFINITION.name
            altered_definition.write_bytes(timeline._canonical_json(document))
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "accepted pins differ"
            ):
                timeline._load_definition(altered_definition)

            linked = temporary_path / "linked-bundle"
            os.symlink(BUNDLE, linked)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "ordinary directory"
            ):
                timeline.validate_construction_timeline_bundle(linked)


if __name__ == "__main__":
    unittest.main()
