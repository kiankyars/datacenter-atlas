from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import stat
import subprocess
import sys
import unittest
from unittest import mock

from datacenter_atlas.satellite_unknown034_delta_review_v1 import (
    OUTPUT_PATH as V1_OUTPUT_PATH,
)
from datacenter_atlas.satellite_unknown034_delta_review_v2 import (
    DEFINITION_PATH,
    DEFINITION_SHA256,
    OUTPUT_PATH,
    PREDECESSOR_MANIFEST_SHA256,
    PREDECESSOR_TREE_SHA256,
    REVIEW_ID,
    SCOPE,
    build_unknown034_delta_review_v2,
    validate_unknown034_delta_review_v2,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / DEFINITION_PATH
V1_BUNDLE = ROOT / V1_OUTPUT_PATH
BUNDLE = ROOT / OUTPUT_PATH
MANIFEST_SHA256 = "36f9612368d8212b46a05a739268fccd02d0a5b0d6914e4bd2658fdd395f7e7d"
TREE_INVENTORY_SHA256 = (
    "8bb37d0f6afe967b9a61345ffe6ce0f2dc7b778bb91024fb3ac8edadfec754ec"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


class Unknown034DeltaReviewV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v1_raw = (V1_BUNDLE / "review-manifest.json").read_bytes()
        cls.v1 = json.loads(cls.v1_raw)
        cls.raw = (BUNDLE / "review-manifest.json").read_bytes()
        cls.manifest = json.loads(cls.raw)

    def test_v1_is_preserved_and_v2_is_collision_isolated_frozen(self) -> None:
        self.assertNotEqual(V1_BUNDLE, BUNDLE)
        self.assertEqual(_sha256(self.v1_raw), PREDECESSOR_MANIFEST_SHA256)
        self.assertEqual(
            self.manifest["predecessor"]["bundle_inventory"]["sha256"],
            PREDECESSOR_TREE_SHA256,
        )
        self.assertEqual(_sha256(self.raw), MANIFEST_SHA256)
        self.assertEqual(
            (BUNDLE / "manifest.sha256").read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  review-manifest.json\n",
        )
        self.assertEqual(
            self.manifest["tree_inventory_sha256"], TREE_INVENTORY_SHA256
        )
        for bundle, expected_bytes in ((V1_BUNDLE, 14_019_259), (BUNDLE, 14_021_002)):
            files = [path for path in bundle.rglob("*") if path.is_file()]
            directories = [
                bundle,
                *[path for path in bundle.rglob("*") if path.is_dir()],
            ]
            self.assertEqual(len(files), 28)
            self.assertEqual(sum(path.stat().st_size for path in files), expected_bytes)
            self.assertTrue(
                all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in files)
            )
            self.assertTrue(
                all(
                    stat.S_IMODE(path.stat().st_mode) == 0o555
                    for path in directories
                )
            )

    def test_v2_replays_offline_byte_for_byte(self) -> None:
        self.assertEqual(_sha256(DEFINITION.read_bytes()), DEFINITION_SHA256)
        prior_socket = socket.socket
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("v2 review replay attempted network access"),
        ):
            first = build_unknown034_delta_review_v2(DEFINITION)
            second = build_unknown034_delta_review_v2(DEFINITION)
            validated = validate_unknown034_delta_review_v2(BUNDLE, DEFINITION)
        self.assertIs(socket.socket, prior_socket)
        self.assertEqual(first, second)
        self.assertEqual(first["review-manifest.json"], self.raw)
        self.assertEqual(validated, self.manifest)

    def test_execution_semantics_are_explicit_and_not_ambiguous(self) -> None:
        self.assertNotIn("change_analysis_executed_by_checkpoint", SCOPE)
        self.assertTrue(SCOPE["source_change_analysis_executed"])
        self.assertFalse(SCOPE["change_analysis_reexecuted_during_review_build"])
        semantics = self.manifest["execution_semantics"]
        self.assertEqual(
            semantics,
            {
                "bound_source_change_algorithm": "sentinel-2-l2a-change-v2",
                "bound_source_change_analysis_executed": True,
                "bound_source_change_jobs_completed": 21,
                "bound_source_change_jobs_failed": 0,
                "comparison_images_copied_from_bound_outputs": 21,
                "review_build_action": "offline_validate_bind_and_copy",
                "review_build_reexecuted_change_analysis": False,
            },
        )
        summary = self.manifest["summary"]
        self.assertEqual(summary["source_change_jobs_completed"], 21)
        self.assertEqual(summary["source_change_jobs_failed"], 0)
        self.assertEqual(
            summary["change_analysis_reexecutions_during_review_build"], 0
        )

    def test_all_review_evidence_and_dispositions_are_preserved(self) -> None:
        v1_artifacts = set(self.v1["artifacts"])
        v2_artifacts = set(self.manifest["artifacts"])
        self.assertEqual(v1_artifacts, v2_artifacts)
        for relative in sorted(v1_artifacts - {"README.md"}):
            self.assertEqual(
                (V1_BUNDLE / relative).read_bytes(), (BUNDLE / relative).read_bytes()
            )
        self.assertNotEqual(
            (V1_BUNDLE / "README.md").read_bytes(),
            (BUNDLE / "README.md").read_bytes(),
        )
        self.assertEqual(
            self.manifest["summary"]["label_counts"],
            {"manual-review": 7, "reject": 8, "retain": 2, "uncertain": 5},
        )
        self.assertEqual(
            _jsonl(BUNDLE / "review-units.jsonl"),
            _jsonl(V1_BUNDLE / "review-units.jsonl"),
        )
        self.assertEqual(
            _jsonl(BUNDLE / "analyst-reviews.jsonl"),
            _jsonl(V1_BUNDLE / "analyst-reviews.jsonl"),
        )
        self.assertEqual(
            _jsonl(BUNDLE / "blockers.jsonl"),
            _jsonl(V1_BUNDLE / "blockers.jsonl"),
        )

    def test_v2_does_not_weaken_no_promotion_or_no_inference_guardrails(self) -> None:
        self.assertEqual(self.manifest["scope"], SCOPE)
        self.assertFalse(SCOPE["atlas_mutation"])
        self.assertFalse(SCOPE["automated_promotion_allowed"])
        self.assertTrue(SCOPE["review_labels_are_visual_dispositions_only"])
        self.assertTrue(SCOPE["review_required"])
        self.assertFalse(SCOPE["unique_site_claim_created"])
        for name, value in SCOPE.items():
            if name.startswith("imagery_"):
                self.assertFalse(value, name)
        self.assertEqual(self.manifest["summary"]["unique_sites_claimed"], 0)
        self.assertEqual(self.manifest["summary"]["native_window_blockers"], 1)
        self.assertFalse(self.manifest["source_contracts"]["mosaic_v1_applied"])

    def test_validation_cli_reports_corrected_v2_semantics(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/build_satellite_unknown034_delta_review_v2.py",
                "--definition",
                str(DEFINITION),
                "--output-dir",
                str(BUNDLE),
                "--validate-only",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["review_id"], REVIEW_ID)
        self.assertTrue(
            payload["execution_semantics"][
                "bound_source_change_analysis_executed"
            ]
        )
        self.assertFalse(
            payload["execution_semantics"][
                "review_build_reexecuted_change_analysis"
            ]
        )


if __name__ == "__main__":
    unittest.main()
