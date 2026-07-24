from __future__ import annotations

from collections import Counter
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
    BLOCKED_QUEUE_ID,
    DEFINITION_PATH,
    DEFINITION_SHA256,
    OUTPUT_PATH,
    REVIEW_ID,
    build_unknown034_delta_review_v1,
    validate_unknown034_delta_review_v1,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / DEFINITION_PATH
BUNDLE = ROOT / OUTPUT_PATH
MANIFEST_SHA256 = "a4f97b1f02c993fc22ec204ba923358970cbbcb6f59a57b88de52b9989e39c03"
TREE_INVENTORY_SHA256 = (
    "3210a619fc2fe50dd3cb88cf9d18aacb2e301940fc342c9430131992ea5cf47d"
)
SOURCE_MANIFEST_SHA256 = {
    "catalog_batch": "9cc51440c6d0f53a20f45fef61cf33345a47d0dd2f22265b188a692bd3eb6ebd",
    "catalog_parent": "797ef873d519b9a8e503cf4ad79231d0ca42ea50fcf9159b65db8993a2322c7d",
    "direct_change_batch": "ad9b7d67d55d40f717d4ed7986c1a819fe2b61df5e5dd05854971029eba8ca00",
    "reselected_change_batch": "ad0be0b051f74dbdf0eedf4ce7c77e2ab2a1f7cef08c175f3086173856e6431f",
    "reselection_manifest": "df1391b93aba4c2b91aac3ea54e884bc2fd86748557ecbef2451730be2d56b3a",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    assert path.read_bytes() == b"".join(_canonical_line(row) for row in rows)
    return rows


class Unknown034DeltaReviewV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest_raw = (BUNDLE / "review-manifest.json").read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)
        cls.delta = _jsonl(BUNDLE / "ordered-catalog-pair-delta.jsonl")
        cls.units = _jsonl(BUNDLE / "review-units.jsonl")
        cls.reviews = _jsonl(BUNDLE / "analyst-reviews.jsonl")
        cls.blockers = _jsonl(BUNDLE / "blockers.jsonl")

    def test_bundle_is_frozen_hash_bound_and_offline_replayable(self) -> None:
        self.assertEqual(_sha256(DEFINITION.read_bytes()), DEFINITION_SHA256)
        self.assertEqual(_sha256(self.manifest_raw), MANIFEST_SHA256)
        self.assertEqual(
            (BUNDLE / "manifest.sha256").read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  review-manifest.json\n",
        )
        self.assertEqual(
            self.manifest["tree_inventory_sha256"], TREE_INVENTORY_SHA256
        )
        prior_socket = socket.socket
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline review replay attempted network access"),
        ):
            first = build_unknown034_delta_review_v1(DEFINITION)
            second = build_unknown034_delta_review_v1(DEFINITION)
            validated = validate_unknown034_delta_review_v1(BUNDLE, DEFINITION)
        self.assertIs(socket.socket, prior_socket)
        self.assertEqual(first, second)
        self.assertEqual(first["review-manifest.json"], self.manifest_raw)
        self.assertEqual(validated, self.manifest)

        files = [path for path in BUNDLE.rglob("*") if path.is_file()]
        directories = [
            BUNDLE,
            *[path for path in BUNDLE.rglob("*") if path.is_dir()],
        ]
        self.assertEqual(len(files), 28)
        self.assertEqual(sum(path.stat().st_size for path in files), 14_019_259)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in files)
        )
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o555 for path in directories)
        )
        self.assertFalse(any(path.is_symlink() for path in BUNDLE.rglob("*")))

    def test_exact_ordered_catalog_delta_and_dedup_accounting(self) -> None:
        expected_positions = [
            4770,
            4771,
            4772,
            4774,
            4775,
            4776,
            4777,
            4778,
            4779,
            4782,
            4783,
            4784,
            4785,
            4786,
            4787,
            4788,
            4789,
            4790,
            4791,
            4792,
            4793,
            4794,
        ]
        self.assertEqual([row["queue_position"] for row in self.delta], expected_positions)
        self.assertEqual(
            [row["queue_position"] for row in self.units], expected_positions
        )
        self.assertEqual(len(self.delta), 22)
        self.assertEqual(len(self.units), 22)
        self.assertEqual(
            len({row["accepted_catalog_pair_key_sha256"] for row in self.delta}),
            22,
        )
        self.assertEqual(len({row["review_unit_id"] for row in self.units}), 22)
        self.assertTrue(
            all(len(row["deduplicated_member_queue_ids"]) == 1 for row in self.units)
        )
        summary = self.manifest["summary"]
        self.assertEqual(summary["exact_aoi_scene_pair_duplicate_rows"], 0)
        self.assertEqual(summary["exact_aoi_scene_pair_review_units"], 22)
        self.assertEqual(summary["unique_sites_claimed"], 0)
        self.assertFalse(self.manifest["scope"]["unique_site_claim_created"])

        catalog_delta = self.manifest["catalog_delta"]
        self.assertEqual(catalog_delta["completed_pair_rows"], 22)
        self.assertEqual(
            [
                row["queue_position"]
                for row in catalog_delta[
                    "no_scene_rows_excluded_before_change_analysis"
                ]
            ],
            [4773, 4780, 4781],
        )
        self.assertEqual(
            catalog_delta["parent_to_output_arithmetic"],
            {
                "jobs_completed": 22,
                "jobs_failed": 0,
                "jobs_pending": -25,
                "jobs_unavailable_no_scene": 3,
            },
        )

    def test_every_comparison_has_an_explicit_visual_disposition(self) -> None:
        self.assertEqual(len(self.reviews), 21)
        self.assertEqual(
            Counter(row["label"] for row in self.reviews),
            Counter(
                {"manual-review": 6, "reject": 8, "retain": 2, "uncertain": 5}
            ),
        )
        self.assertEqual(
            Counter(row["label"] for row in self.units),
            Counter(
                {"manual-review": 7, "reject": 8, "retain": 2, "uncertain": 5}
            ),
        )
        self.assertEqual(
            self.manifest["summary"]["label_counts"],
            {"manual-review": 7, "reject": 8, "retain": 2, "uncertain": 5},
        )
        self.assertEqual(
            Counter(row["analysis_lane"] for row in self.reviews),
            Counter({"original_full_cover": 17, "coverage_reselected": 4}),
        )
        for row in self.reviews:
            copied = BUNDLE / row["comparison"]["copied_path"]
            source = ROOT / row["comparison"]["source"]["path"]
            self.assertEqual(copied.read_bytes(), source.read_bytes())
            self.assertEqual(_sha256(copied.read_bytes()), row["comparison"]["source"]["sha256"])
            self.assertEqual(row["review_scope"], "visible_comparison_disposition_only")
            self.assertNotIn("entity", row)

    def test_single_asset_blocker_remains_typed_and_outside_fixed_mosaic_v1(self) -> None:
        self.assertEqual(len(self.blockers), 1)
        blocker = self.blockers[0]
        self.assertEqual(blocker["queue_id"], BLOCKED_QUEUE_ID)
        self.assertEqual(blocker["queue_position"], 4786)
        self.assertEqual(blocker["label"], "manual-review")
        self.assertEqual(
            blocker["resolution_reason"], "no_full_cover_baseline_candidate"
        )
        self.assertEqual(blocker["full_cover_eligible_ids"]["baseline"], [])
        self.assertFalse(blocker["change_analysis_executed"])
        self.assertFalse(blocker["mosaic_lane"]["applied"])
        self.assertFalse(blocker["mosaic_lane"]["exact_contract_match"])
        self.assertNotIn(
            BLOCKED_QUEUE_ID, blocker["mosaic_lane"]["contract_queue_ids"]
        )
        self.assertEqual(self.manifest["summary"]["native_window_blockers"], 1)
        self.assertEqual(self.manifest["summary"]["analysis_failures"], 0)

    def test_inputs_processors_and_no_inference_scope_are_pinned(self) -> None:
        for name, expected in SOURCE_MANIFEST_SHA256.items():
            self.assertEqual(self.manifest["input_pins"][name]["sha256"], expected)
            self.assertEqual(
                _sha256((ROOT / self.manifest["input_pins"][name]["path"]).read_bytes()),
                expected,
            )
        self.assertEqual(
            self.manifest["source_contracts"]["change_algorithm"],
            "sentinel-2-l2a-change-v2",
        )
        self.assertFalse(self.manifest["source_contracts"]["mosaic_v1_applied"])
        scope = self.manifest["scope"]
        self.assertFalse(scope["atlas_mutation"])
        self.assertFalse(scope["automated_promotion_allowed"])
        self.assertTrue(scope["review_labels_are_visual_dispositions_only"])
        self.assertTrue(scope["review_required"])
        for name, value in scope.items():
            if name.startswith("imagery_"):
                self.assertFalse(value, name)

    def test_validation_cli_uses_the_public_carrier(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/build_satellite_unknown034_delta_review_v1.py",
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
        self.assertEqual(payload["summary"], self.manifest["summary"])


if __name__ == "__main__":
    unittest.main()
