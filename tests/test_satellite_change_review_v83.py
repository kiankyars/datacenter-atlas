from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import datacenter_atlas.datacenter_atlas.satellite_change_review_v83 as implementation
from datacenter_atlas.satellite_change_review_v83 import (
    GUARDRAILS,
    OUTPUT_PATH,
    REVIEW_ID,
    build_analyst_review,
    validate_analyst_review,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COUNTS = implementation.EXPECTED_COUNTS
PREMATURE_DRAFT_SHA256 = implementation.PREMATURE_DRAFT_SHA256
SOURCE_CHANGE_MANIFEST_SHA256 = implementation.SOURCE_CHANGE_MANIFEST_SHA256
SOURCE_CHANGE_TREE_SHA256 = implementation.SOURCE_CHANGE_TREE_SHA256
GENERATED_AT = "2026-07-21T18:52:30.000000Z"
MANIFEST_SHA256 = "4cbe507b44e830a92879079cc9f33290d9d64459e1b1a33a9d2944737e3eba33"
TREE_SHA256 = "b58368608ad2e37024ee3263c1ab6e7ff42d33272d392c9527ac97a8a53a1749"
EXPECTED_MEMBERS = {
    "ATTRIBUTION.txt": (
        281,
        "2b3f19ba6b64fe6296c94ed6a5991789c80abc1a6bf854328a6a008decaa4705",
    ),
    "README.md": (
        910,
        "7a354e6932b91f1def1210c970be692d199160c6620d424e8a0ccf1e90e4ae5c",
    ),
    "analyst-reviews.jsonl": (
        6_447,
        "000751541195ca2bef05d4faddc323d6d886794eb91e294f23a0ed838dfda7d4",
    ),
    "blind-decisions.json": (
        4_646,
        "99dfa722aa3d6bd914d450dda528ccec5e7670eeb66157a85880d1356eb3c06a",
    ),
    "definition.json": (
        6_622,
        "9328509714323a523b4adb8dd3a1131ae960c120f56a6beaf9ffb64d35f288c3",
    ),
    "manifest.json": (6_526, MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "660acd37fd03906e36cf6a4e3cd6b86720fe463ef0aa44a73998b894e5b6ac3c",
    ),
    "publication-incident.json": (
        1_361,
        "a69b9167ebb5268e518f7b4d64652e973450bd5c3396e9e9df974483322a738b",
    ),
    "summary.json": (
        5_477,
        "7ff6f4ff7499892cfc9c38278b85a868fb264f5c6379277205d11a4ca0fd47e3",
    ),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


class SatelliteChangeReviewV83Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest_raw = (OUTPUT_PATH / "manifest.json").read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)
        cls.definition = json.loads((OUTPUT_PATH / "definition.json").read_text())
        cls.blind = json.loads((OUTPUT_PATH / "blind-decisions.json").read_text())
        cls.rows = [
            json.loads(line)
            for line in (OUTPUT_PATH / "analyst-reviews.jsonl").read_bytes().splitlines()
        ]
        cls.summary = json.loads((OUTPUT_PATH / "summary.json").read_text())
        cls.publication_incident = json.loads(
            (OUTPUT_PATH / "publication-incident.json").read_text()
        )

    def test_frozen_review_reproduces_twice_offline(self) -> None:
        network_failure = AssertionError("v83 analyst review attempted network access")
        with mock.patch.object(socket, "socket", side_effect=network_failure), mock.patch.object(
            socket, "create_connection", side_effect=network_failure
        ), mock.patch.object(socket, "getaddrinfo", side_effect=network_failure):
            first = validate_analyst_review(OUTPUT_PATH)
            second = validate_analyst_review(OUTPUT_PATH)
            rebuilt = build_analyst_review(GENERATED_AT)
        self.assertEqual(first, second)
        self.assertEqual(first["review_id"], REVIEW_ID)
        self.assertEqual(first["tree_inventory"]["inventory_sha256"], TREE_SHA256)
        self.assertEqual(
            rebuilt,
            {path.name: path.read_bytes() for path in OUTPUT_PATH.iterdir() if path.is_file()},
        )

    def test_exact_members_modes_hashes_and_time_boundary(self) -> None:
        self.assertEqual(_sha256(self.manifest_raw), MANIFEST_SHA256)
        self.assertEqual(
            (OUTPUT_PATH / "manifest.sha256").read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  manifest.json\n",
        )
        self.assertEqual(set(EXPECTED_MEMBERS), {path.name for path in OUTPUT_PATH.iterdir()})
        for name, (size, digest) in EXPECTED_MEMBERS.items():
            raw = (OUTPUT_PATH / name).read_bytes()
            self.assertEqual((len(raw), _sha256(raw)), (size, digest))
            self.assertEqual(stat.S_IMODE((OUTPUT_PATH / name).stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(OUTPUT_PATH.stat().st_mode), 0o555)
        generated = implementation.publication._timestamp(GENERATED_AT, "generated_at")[1]
        self.assertGreaterEqual(OUTPUT_PATH.stat().st_ctime + 1e-6, generated.timestamp())

    def test_fresh_identity_blind_decisions_are_preserved(self) -> None:
        self.assertEqual([row["blind_id"] for row in self.rows], ["A", "B", "C"])
        self.assertEqual(
            Counter(row["disposition"] for row in self.rows),
            Counter({"rejected_for_site_promotion": 2, "uncertain_for_manual_followup": 1}),
        )
        self.assertEqual(
            Counter(row["image_quality"] for row in self.rows),
            Counter({"partially_obscured": 2, "usable": 1}),
        )
        self.assertEqual(
            Counter(row["visible_change"] for row in self.rows),
            Counter({"ambiguous": 1, "clear": 1, "none": 1}),
        )
        for decision, record in zip(self.blind["decisions"], self.rows, strict=True):
            self.assertEqual({key: record[key] for key in decision}, decision)
        self.assertEqual(self.blind["summary"]["proposal_features_reviewed"], 35)

    def test_only_allowed_review_artifacts_are_bound(self) -> None:
        expected = {
            "after.png",
            "before.png",
            "change-overlay.png",
            "change-proposals.geojson",
            "comparison.png",
        }
        self.assertEqual(len({row["queue_id"] for row in self.rows}), 3)
        self.assertEqual(sum(row["proposal_count"] for row in self.rows), 35)
        for row in self.rows:
            self.assertEqual(set(row["input_artifacts"]), expected)
            self.assertNotIn("report.json", row["input_artifacts"])
            self.assertEqual(
                row["visual_artifacts_inspected"],
                ["after.png", "before.png", "change-overlay.png", "comparison.png"],
            )
            for spec in row["input_artifacts"].values():
                path = ROOT / spec["path"]
                self.assertFalse(path.is_symlink())
                raw = path.read_bytes()
                self.assertEqual((len(raw), _sha256(raw)), (spec["bytes"], spec["sha256"]))
        self.assertEqual(self.summary["counts"]["review_input_artifacts_hash_bound"], 15)
        self.assertEqual(self.summary["counts"]["visual_artifacts_inspected"], 12)

    def test_all_claim_flags_false_and_no_atlas_mutation(self) -> None:
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        self.assertEqual(self.summary["guardrails"], GUARDRAILS)
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.summary["counts"]["promotion_dispositions"], EXPECTED_COUNTS["promotion_dispositions"])
        for forbidden in (
            "capacity",
            "current_status",
            "data_centre_type",
            "energy",
            "lifecycle_status",
            "operator",
            "power",
            "pue",
            "site_count",
            "workload",
        ):
            self.assertFalse(_contains_key(self.rows, forbidden), forbidden)

    def test_jashore_and_both_incidents_are_outside_analyst_outcomes(self) -> None:
        sources = self.definition["sources"]
        unavailable = sources["unavailable_catalog_job"]
        self.assertEqual(unavailable["count"], 1)
        self.assertFalse(unavailable["analyst_decision_created"])
        self.assertTrue(set(unavailable["queue_ids"]).isdisjoint({row["queue_id"] for row in self.rows}))
        technical = sources["technical_incident"]
        self.assertTrue(technical["technical_not_model_outcome"])
        self.assertFalse(technical["model_outcome_created"])
        self.assertFalse(technical["analyst_decision_created"])
        premature = sources["rejected_premature_definition"]
        self.assertEqual(premature["sha256"], PREMATURE_DRAFT_SHA256)
        self.assertEqual(premature["disposition"], "rejected_publication_control_violation")
        self.assertFalse(premature["model_or_analyst_outcome_created"])
        self.assertTrue(self.publication_incident["final_paths_absent_before_rebuild"])
        self.assertTrue(
            self.publication_incident["transaction"]["atomic_no_replace_root_promotion"]
        )
        self.assertTrue(
            self.publication_incident["transaction"]["private_stage_before_publication"]
        )

    def test_exact_queue_catalog_and_change_inputs_are_pinned(self) -> None:
        sources = self.definition["sources"]
        self.assertEqual(sources["change_run"]["manifest_sha256"], SOURCE_CHANGE_MANIFEST_SHA256)
        self.assertEqual(sources["change_run"]["tree_sha256"], SOURCE_CHANGE_TREE_SHA256)
        self.assertEqual(
            sources["catalog"]["manifest_sha256"], implementation.execution.CATALOG_MANIFEST_SHA256
        )
        self.assertEqual(
            sources["queue"]["manifest_sha256"], implementation.execution.QUEUE_MANIFEST_SHA256
        )
        self.assertEqual(sources["queue"]["queue_sha256"], implementation.execution.QUEUE_SHA256)

    def test_cli_and_collision_refusal(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_satellite_change_review_v83.py"),
                "--validate-only",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / "stage"
            final = Path(temporary) / "final"
            stage.mkdir()
            final.mkdir()
            with self.assertRaisesRegex(Exception, "refusing existing output"):
                implementation.publication._promote_noreplace(stage, final)
            self.assertTrue(stage.exists())
            self.assertTrue(final.exists())


if __name__ == "__main__":
    unittest.main()
