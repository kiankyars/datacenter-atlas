from __future__ import annotations

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

from datacenter_atlas import construction_timeline_v1 as timeline
from datacenter_atlas.open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-20-public-open-v1.json"
)
BUNDLE = ROOT / "construction_timelines/2026-07-20-public-open-v1"
V60_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v60.json"
V60_RELEASE = ROOT / "releases/2026-07-20-open-seed-v60"

DEFINITION_SHA256 = (
    "b7e04ec1915c1527bcb8cd3c7c08dad561b3bde5bdfe668cb5f6defaa14c0e7d"
)
MANIFEST_SHA256 = (
    "610b4058593e2d426faf4560799b9c1335711105c35b0bd839f0bcb06539f4fd"
)
BUNDLE_TREE_SHA256 = (
    "29f5f724089d8a2eafce69cfb6cfd193d6547dbd21efbca1e89945b4557e39b2"
)

V60_PINS = {
    V60_DEFINITION: (
        76_089,
        "4f3a81ad33c3cb73565eefe0904fcf4118d57bfc071852dc226e331e3dd32b66",
        0o644,
    ),
    V60_RELEASE / "manifest.json": (
        10_775,
        "d69ded6f7b86415b4dc8ad84cbee65835d878e310fbcb2c8954636066173f430",
        0o444,
    ),
    ROOT / "datacenter_atlas/open_seed_v60.py": (
        34_918,
        "f5bc896a0527399aaaa274e3b0076e8af6b44e5124f0e558c20c8b56972fcc54",
        0o644,
    ),
    ROOT / "datacenter_atlas/open_seed_release_v5.py": (
        18_865,
        "1e5cc500b0b1f8ba02363634a4e364b4b3c6088355bd9a8b77bbff81da58c137",
        0o644,
    ),
}

ARTIFACTS = {
    "ATTRIBUTION.txt": (
        23_133,
        "64d4f2060b4daa12789c49400cd8880d40f05cba4f5a16b009860e63ba845e9a",
    ),
    "README.md": (
        1_321,
        "371511eef158cee4dd700df5860027982b16ffe1aa82e7646985da686e09f3cb",
    ),
    "coverage.json": (
        13_481,
        "a6cae1d80beb450707d0c64db48c70886f4cb6a1c93bfdbc695eb00785d56a9e",
    ),
    "entity-timelines.jsonl": (
        644_758,
        "709bc1570d32d020925b1947ea61633a03bc80009d29e0840d1e34b9a53dee65",
    ),
    "lifecycle-observations.csv": (
        284_833,
        "cb7abbd4acfa94c2067dbef41627616e478575928690cbb752390e70753e8c09",
    ),
    "manifest.json": (
        2_560,
        MANIFEST_SHA256,
    ),
    "manifest.sha256": (
        80,
        "06e6e3b9d288345beeafb50df50f9e4c99140d1a9dd9c1905a23276ec05cc23c",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConstructionTimelineV1Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("construction timeline attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_tree_and_v60_preservation(self) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(BUNDLE), BUNDLE_TREE_SHA256)
        self.assertEqual(tree_digest(V60_RELEASE), timeline.OPEN_SEED_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(stat.S_IMODE(V60_RELEASE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, timeline.BUNDLE_FILES)
        for path in BUNDLE.iterdir():
            self.assertFalse(path.is_symlink())
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((path.stat().st_size, sha256(path)), ARTIFACTS[path.name])
        for path, (size, digest, mode) in V60_PINS.items():
            self.assertEqual((path.stat().st_size, sha256(path)), (size, digest))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)

    def test_flat_rows_preserve_every_raw_observation_and_provenance(self) -> None:
        with (BUNDLE / timeline.OBSERVATIONS_FILENAME).open(
            encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(tuple(rows[0]), timeline.OBSERVATION_FIELDS)
        self.assertEqual(len(rows), 426)
        self.assertEqual(len({row["observation_id"] for row in rows}), 426)
        self.assertEqual(len({row["entity_id"] for row in rows}), 412)
        self.assertEqual(
            {row["entity_kind"] for row in rows}, {"campus", "project"}
        )
        for row in rows:
            for field in (
                "entity_stable_key",
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
        self.assertEqual({row["superseded_at"] for row in rows}, {""})
        self.assertEqual({row["valid_to_date"] for row in rows}, {""})

    def test_grouped_timelines_expose_milestones_without_current_inference(self) -> None:
        timelines = [
            json.loads(line)
            for line in (BUNDLE / timeline.TIMELINES_FILENAME)
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        self.assertEqual(len(timelines), 412)
        self.assertEqual(sum(row["observation_count"] for row in timelines), 426)
        self.assertEqual(sum(row["has_multiple_observations"] for row in timelines), 14)
        self.assertEqual(sum(row["has_status_change"] for row in timelines), 10)
        self.assertEqual(
            sum(row["single_old_observation_current_unknown"] for row in timelines),
            24,
        )
        for row in timelines:
            self.assertEqual(row["current_status_classification"], "unknown")
            self.assertFalse(row["current_construction_claim"])
            self.assertFalse(row["latest_observation_persistence_assumed"])
            self.assertTrue(row["source_scoped_identity_only"])

        by_key = {row["entity_stable_key"]: row for row in timelines}
        expected = {
            "curated:airtrunk-tok2-west-tokyo-data-centre:initial-build": [
                ("2022-11-17", "under_construction"),
                ("2024-05-31", "operational"),
            ],
            "curated:raxio-civ1-abidjan-data-centre:initial-build": [
                ("2022-11-07", "under_construction"),
                ("2024-09-24", "operational"),
            ],
            "curated:stc-bahrain-data-center:facility-build": [
                ("2024-12-31", "under_construction"),
                ("2025-12-31", "operational"),
            ],
            "curated:kazakhstan-data-center-valley-ekibastuz:initial-campus-development": [
                ("2026-05-25", "site_preparation"),
                ("2026-07-01", "under_construction"),
            ],
        }
        for stable_key, milestones in expected.items():
            self.assertEqual(
                [
                    (item["observed_date"], item["status"])
                    for item in by_key[stable_key]["observations"]
                ],
                milestones,
            )

    def test_coverage_and_scope_make_non_claims_explicit(self) -> None:
        coverage = json.loads(
            (BUNDLE / timeline.COVERAGE_FILENAME).read_text(encoding="utf-8")
        )
        manifest = timeline.validate_construction_timeline_bundle(BUNDLE)
        self.assertEqual(coverage["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(manifest["counts"], timeline.EXPECTED_COUNTS)
        self.assertEqual(coverage["scope"], timeline.SCOPE)
        self.assertEqual(coverage["date_coverage"], {
            "latest_observed_date": "2026-07-20",
            "oldest_observed_date": "2022-01-14",
        })
        self.assertEqual(coverage["observation_entity_kind_counts"], {
            "campus": 83,
            "project": 343,
        })
        self.assertEqual(coverage["timeline_entity_kind_counts"], {
            "campus": 83,
            "project": 329,
        })
        self.assertIsNone(coverage["scope"]["unique_physical_sites"])
        self.assertFalse(coverage["scope"]["quarterly_2017_2032_parity_claimed"])
        self.assertFalse(coverage["scope"]["satellite_cv_promoted_to_lifecycle"])
        self.assertFalse(coverage["scope"]["interpolation_applied"])
        self.assertFalse(coverage["scope"]["forecast_conversion_applied"])

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
                output = Path(temporary) / "timeline"
                rebuilt = timeline.write_construction_timeline_bundle(
                    DEFINITION, output
                )
                self.assertEqual(rebuilt, validated)
                self.assertEqual(tree_digest(output), BUNDLE_TREE_SHA256)

    def test_collision_and_tamper_fail_closed_without_clobber(self) -> None:
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
            raw = target.read_bytes()
            target.write_bytes(raw.replace(b"under_construction", b"under_constructioN", 1))
            for path in tampered.iterdir():
                path.chmod(0o444)
            tampered.chmod(0o555)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "checkpoint differs"
            ):
                timeline.validate_construction_timeline_bundle(tampered)

    def test_definition_pin_tamper_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_path = Path(temporary)
            document = json.loads(DEFINITION.read_text(encoding="utf-8"))
            document["open_seed"]["expected_release_tree_sha256"] = "0" * 64
            tampered = temporary_path / DEFINITION.name
            tampered.write_bytes(timeline._canonical_json(document))
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "accepted pins differ"
            ):
                timeline._load_definition(tampered)

            linked = temporary_path / "linked-bundle"
            os.symlink(BUNDLE, linked)
            with self.assertRaisesRegex(
                timeline.ConstructionTimelineError, "ordinary directory"
            ):
                timeline.validate_construction_timeline_bundle(linked)


if __name__ == "__main__":
    unittest.main()
