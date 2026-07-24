from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_change_review_v4 import (
    BLIND_REVIEW_SOURCE,
    BUNDLE_FILES,
    CATALOG_MANIFEST,
    CATALOG_TREE,
    DECISION_SEMANTICS,
    DEFINITION_SHA256,
    GUARDRAILS,
    NEAR_DUPLICATE_RELATIONSHIPS,
    PENTAPOINT_QUEUE_ID,
    PREPARATION_DEFINITION,
    PREPARATION_MANIFEST,
    PREPARATION_SINGLE_TILE,
    PREPARATION_TREE,
    QUEUE_FILE,
    QUEUE_MANIFEST,
    QUEUE_TREE,
    REVIEW_ID,
    SOURCE_MANIFEST,
    SOURCE_TREE,
    SatelliteChangeReviewV4Error,
    build_satellite_change_review_v4,
    validate_satellite_change_review_v4,
    write_review_definition,
    write_satellite_change_review_v4,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v57-active-review-v1.json"
)
BUNDLE = ROOT / "satellite_change_reviews" / REVIEW_ID
SCRIPT = ROOT / "scripts/build_satellite_change_review_v4.py"
EXPECTED_FILES = {
    "ATTRIBUTION.txt": (
        260,
        "317fa301fe7925a829a4633fbeb71cf1b60e7b5b1224ee9334416fd48bce5030",
    ),
    "README.md": (
        1_417,
        "e9057b03f4c7ca8407414ff87aeb5cccc712e150e09a75e46aaac397777e204f",
    ),
    "analyst-reviews.jsonl": (
        351_822,
        "59bd729e58a12af4ad3a5092eece86e054920f08c73fd66d58537a0e27c4a320",
    ),
    "manifest.json": (
        141_541,
        "ab6510ba065c3b7b9655645a06fbf4af628a7d229cf75b1b20f4fade8c6a4c27",
    ),
    "manifest.sha256": (
        80,
        "044a500adb07340fd0d4d69fe3a4bf718c8a3677ddcbcb00e0c8f3fa2d78f6fb",
    ),
    "summary.json": (
        6_924,
        "936ce3bd6c4704da6f6931ee12b6004023da118b49c79d0822f8f6d6b59a703e",
    ),
}
EXPECTED_DEFINITION_SHA256 = (
    "eb009c496f805d8c68e9510904f45f5a7c82af3fe3f0428a4c96d97dd38aa482"
)
EXPECTED_REVIEW_TREE_SHA256 = (
    "0e79d853fd6ee4ba11ead97754850efe9de16c2c9782a47ce6e01105e3358a41"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(path: Path) -> tuple[int, str, int]:
    return path.stat().st_size, _sha256(path.read_bytes()), stat.S_IMODE(
        path.stat().st_mode
    )


def _module():
    return importlib.import_module(build_satellite_change_review_v4.__module__)


def _contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, dict):
        return forbidden in value or any(
            _contains_key(child, forbidden) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


@contextmanager
def _offline_guard():
    error = AssertionError("satellite review attempted network access")
    with (
        patch.object(socket, "socket", side_effect=error),
        patch.object(socket, "create_connection", side_effect=error),
        patch.object(socket, "getaddrinfo", side_effect=error),
        patch.object(socket, "gethostbyname", side_effect=error),
    ):
        yield


class FrozenSatelliteChangeReviewV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = json.loads(DEFINITION.read_text())
        cls.records = [
            json.loads(line)
            for line in (BUNDLE / "analyst-reviews.jsonl").read_text().splitlines()
        ]
        cls.summary = json.loads((BUNDLE / "summary.json").read_text())
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text())

    def test_frozen_bundle_reproduces_twice_offline_with_exact_pins(self) -> None:
        self.assertEqual(DEFINITION_SHA256, EXPECTED_DEFINITION_SHA256)
        self.assertEqual(_pin(DEFINITION), (6_624, DEFINITION_SHA256, 0o644))
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        for filename, (size, digest) in EXPECTED_FILES.items():
            self.assertEqual(_pin(BUNDLE / filename), (size, digest, 0o444))
        inventory = _module()._tree_inventory(BUNDLE, "review bundle")
        self.assertEqual(inventory["files"], 6)
        self.assertEqual(inventory["file_bytes"], 502_044)
        self.assertEqual(
            inventory["inventory_sha256"], EXPECTED_REVIEW_TREE_SHA256
        )
        with _offline_guard():
            first = build_satellite_change_review_v4(DEFINITION)
            second = build_satellite_change_review_v4(DEFINITION)
            validated_first = validate_satellite_change_review_v4(
                BUNDLE, definition_path=DEFINITION
            )
            validated_second = validate_satellite_change_review_v4(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.files, second.files)
        self.assertEqual(
            first.files, {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        )
        self.assertEqual(validated_first, validated_second)
        self.assertEqual(validated_first["review_id"], REVIEW_ID)

    def test_all_visual_verdicts_and_site_dispositions_are_preserved(self) -> None:
        self.assertEqual(len(self.records), 71)
        self.assertEqual(
            [row["blind_id"] for row in self.records],
            [f"V57-B{index:03d}" for index in range(1, 72)],
        )
        self.assertEqual(
            Counter(row["visual_verdict"] for row in self.records),
            Counter({"T": 41, "R": 11, "U": 19}),
        )
        members = [member for row in self.records for member in row["members"]]
        self.assertEqual(len(members), 74)
        self.assertEqual(len({member["queue_id"] for member in members}), 74)
        self.assertEqual(
            Counter(
                row["visual_verdict"]
                for row in self.records
                for _member in row["members"]
            ),
            Counter({"T": 44, "R": 11, "U": 19}),
        )
        for row in self.records:
            self.assertEqual(
                row["visual_disposition"],
                DECISION_SEMANTICS[row["visual_verdict"]],
            )
        mismatches = [
            (row, member)
            for row in self.records
            for member in row["members"]
            if member["promotion_disposition"] != row["visual_disposition"]
        ]
        self.assertEqual(len(mismatches), 1)
        penta_row, penta = mismatches[0]
        self.assertEqual(penta_row["visual_verdict"], "U")
        self.assertEqual(penta["queue_id"], PENTAPOINT_QUEUE_ID)
        self.assertEqual(penta["visual_disposition"], "inconclusive")
        self.assertEqual(penta["promotion_disposition"], "reject_imagery_promotion")
        self.assertEqual(
            penta["promotion_disposition_basis"],
            "predecessor_official_evidence_limit_preserved_not_imagery",
        )
        self.assertEqual(
            self.summary["promotion_disposition_job_counts"],
            {
                "inconclusive": 18,
                "reject_imagery_promotion": 12,
                "retain_for_visible_change_follow_up_only": 44,
            },
        )

    def test_every_job_binds_six_artifacts_and_queue_status_metadata(self) -> None:
        queue_rows = {
            row["queue_id"]: row
            for row in (
                json.loads(line)
                for line in (ROOT / QUEUE_FILE["path"]).read_text().splitlines()
            )
        }
        for row in self.records:
            for member in row["members"]:
                self.assertEqual(set(member["input_artifacts"]), {
                    "after.png",
                    "before.png",
                    "change-overlay.png",
                    "change-proposals.geojson",
                    "comparison.png",
                    "report.json",
                })
                for spec in member["input_artifacts"].values():
                    path = ROOT / spec["path"]
                    self.assertFalse(path.is_symlink())
                    raw = path.read_bytes()
                    self.assertEqual(len(raw), spec["bytes"])
                    self.assertEqual(_sha256(raw), spec["sha256"])
                queue = queue_rows[member["queue_id"]]
                expected_status = {
                    "age_days_at_atlas_as_of": queue["status_freshness"][
                        "age_days_at_atlas_as_of"
                    ],
                    "atlas_as_of": "2026-07-20",
                    "last_observed_value": queue["priority"]["lifecycle_status"],
                    "missing": queue["status_freshness"]["missing"],
                    "queue_input_only": True,
                    "status_as_of": queue["status_freshness"]["status_as_of"],
                }
                self.assertEqual(
                    member["last_observed_status_metadata"], expected_status
                )
                self.assertEqual(
                    member["authoritative_status_refresh"],
                    {
                        "completed_by_this_review": False,
                        "imagery_can_satisfy_refresh": False,
                        "imagery_refresh_performed": False,
                        "required_before_treating_last_observation_as_current": True,
                    },
                )

    def test_all_v57_lineage_pins_and_near_duplicate_guard_are_exact(self) -> None:
        self.assertEqual(
            self.definition["source_blind_review"], BLIND_REVIEW_SOURCE
        )
        self.assertEqual(
            self.definition["source_queue_bundle"],
            {
                "closed_tree": QUEUE_TREE,
                "manifest": QUEUE_MANIFEST,
                "queue": QUEUE_FILE,
            },
        )
        self.assertEqual(
            self.definition["source_catalog_run"],
            {"closed_tree": CATALOG_TREE, "manifest": CATALOG_MANIFEST},
        )
        self.assertEqual(
            self.definition["source_change_preparation"],
            {
                "closed_tree": PREPARATION_TREE,
                "definition": PREPARATION_DEFINITION,
                "manifest": PREPARATION_MANIFEST,
                "single_tile_ready": PREPARATION_SINGLE_TILE,
            },
        )
        self.assertEqual(
            self.definition["source_change_run"],
            {"closed_tree": SOURCE_TREE, "manifest": SOURCE_MANIFEST},
        )
        self.assertEqual(
            self.summary["near_duplicate_visual_relationships"],
            NEAR_DUPLICATE_RELATIONSHIPS,
        )
        self.assertFalse(
            self.summary["near_duplicate_visual_relationships"][0][
                "unique_site_claim_created"
            ]
        )

    def test_review_cannot_create_atlas_identity_status_or_capacity_facts(self) -> None:
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.summary["guardrails"], GUARDRAILS)
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        self.assertEqual(
            self.summary["status_observation_policy"],
            {
                "authoritative_refresh_completed_by_review": False,
                "authoritative_refresh_required_before_current_status_use": True,
                "imagery_can_satisfy_authoritative_status_refresh": False,
                "imagery_status_refresh_performed": False,
                "metadata_source": "source_queue_input_only",
                "semantics": "dated_last_observed_metadata_not_current_status",
            },
        )
        for forbidden in (
            "current_status",
            "it_capacity_mw",
            "site_count",
            "operator",
            "workload",
        ):
            self.assertFalse(_contains_key(self.records, forbidden))

    def test_writers_fail_closed_and_cli_validates(self) -> None:
        with self.assertRaisesRegex(SatelliteChangeReviewV4Error, "existing output"):
            write_review_definition(ROOT, DEFINITION)
        with self.assertRaisesRegex(SatelliteChangeReviewV4Error, "existing output"):
            write_satellite_change_review_v4(DEFINITION, BUNDLE)
        with self.assertRaisesRegex(SatelliteChangeReviewV4Error, "freeze=True"):
            write_satellite_change_review_v4(DEFINITION, BUNDLE, freeze=False)
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-only"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            json.loads(completed.stdout),
            {
                "jobs": 74,
                "output": str(BUNDLE),
                "review_id": REVIEW_ID,
                "validated": True,
                "views": 71,
            },
        )
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.satellite_change_review_v4 import "
            "validate_satellite_change_review_v4; "
            f"m=validate_satellite_change_review_v4(Path({str(BUNDLE)!r}), "
            f"definition_path=Path({str(DEFINITION)!r})); "
            f"assert m['review_id'] == {REVIEW_ID!r}"
        )
        for cwd in (ROOT, WORKSPACE):
            with self.subTest(cwd=cwd):
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
