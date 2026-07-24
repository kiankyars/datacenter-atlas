from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "sources"
    / "satellite-change-blind-review-2026-07-20-open-seed-v57-single-tile-v1.json"
)
EXPECTED_SOURCE_BYTES = 189_885
EXPECTED_SOURCE_SHA256 = (
    "4880a51f3b5bf974b43543f256a4469af72d38aaaebfd706646b4e2eb26ffe0f"
)
EXPECTED_RUN_MANIFEST_SHA256 = (
    "69b749f599ff5b36b98cbbf3c13add7f242164ee04666d60551c0e85e193a62d"
)
EXPECTED_RUN_TREE_SHA256 = (
    "575bc6c94cffc7e43bbc3ae5913cea9f5bad2af5d0a303fb1efe15fbb7cce75d"
)
EXPECTED_FILES = {
    "after.png",
    "before.png",
    "change-overlay.png",
    "change-proposals.geojson",
    "comparison.png",
    "report.json",
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class SatelliteChangeBlindReviewV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = SOURCE.read_bytes()
        cls.document = json.loads(cls.raw)

    def test_source_is_canonical_and_exactly_pinned(self) -> None:
        self.assertEqual(len(self.raw), EXPECTED_SOURCE_BYTES)
        self.assertEqual(_sha256(self.raw), EXPECTED_SOURCE_SHA256)
        self.assertEqual(
            self.raw,
            (
                json.dumps(
                    self.document,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8"),
        )
        self.assertEqual(self.document["schema_version"], 1)
        self.assertEqual(
            self.document["review_id"],
            "2026-07-20-open-seed-v57-active-single-tile-blind-review-v1",
        )

    def test_two_blind_reviews_and_adjudication_are_hash_bound(self) -> None:
        self.assertEqual(
            self.document["review_inputs"],
            [
                {
                    "bytes": 10_061,
                    "logical_id": "root_blind_review",
                    "sha256": "84cf3d82019e8d7903ddd8f378b5f3a4d260ad146014ed6b18266acf45789c77",
                },
                {
                    "bytes": 7_988,
                    "logical_id": "independent_blind_review",
                    "sha256": "e1b4d1800294209c339d0e6c2d7aef1cdfe5200295cc0c1d5e5d9ae5ca90deb8",
                },
                {
                    "bytes": 4_921,
                    "logical_id": "blind_adjudication",
                    "sha256": "e611d94167cea1ce2d67fd577fd415435a4679301362dd2d0117253db5841f5e",
                },
            ],
        )
        method = self.document["method"]
        self.assertEqual(method["independent_reviews"], 2)
        self.assertEqual(method["agreement_views"], 59)
        self.assertEqual(method["disagreement_views"], 12)
        self.assertTrue(
            method["lineage_unsealed_after_adjudication_sha256_was_fixed"]
        )
        self.assertEqual(
            self.document["source_lineage_audit"],
            {
                "bytes": 28_949,
                "logical_id": "sealed_blind_lineage",
                "sha256": "01c30e8b7e2ba1fd7b3472e59b2ef5b6d8f17beb6898e648d7d7373ba5787c70",
            },
        )

    def test_all_71_views_and_74_jobs_are_bound_once(self) -> None:
        rows = self.document["lineage_records"]
        self.assertEqual(len(rows), 71)
        self.assertEqual(
            {row["blind_id"] for row in rows},
            {f"V57-B{index:03d}" for index in range(1, 72)},
        )
        self.assertEqual(
            Counter(row["visual_verdict"] for row in rows),
            Counter({"T": 41, "R": 11, "U": 19}),
        )
        members = [member for row in rows for member in row["members"]]
        self.assertEqual(len(members), 74)
        self.assertEqual(len({member["queue_id"] for member in members}), 74)
        self.assertEqual(
            Counter(
                row["visual_verdict"]
                for row in rows
                for _member in row["members"]
            ),
            Counter({"T": 44, "R": 11, "U": 19}),
        )
        self.assertEqual(self.document["view_counts"], {"R": 11, "T": 41, "U": 19})
        self.assertEqual(self.document["job_counts"], {"R": 11, "T": 44, "U": 19})

    def test_every_decision_binds_all_six_frozen_source_artifacts(self) -> None:
        for row in self.document["lineage_records"]:
            self.assertIn(row["visual_verdict"], {"R", "T", "U"})
            for member in row["members"]:
                artifacts = member["source_artifacts"]
                self.assertEqual(set(artifacts), EXPECTED_FILES)
                for spec in artifacts.values():
                    path = ROOT / spec["path"]
                    self.assertFalse(path.is_symlink())
                    raw = path.read_bytes()
                    self.assertEqual(len(raw), spec["bytes"])
                    self.assertEqual(_sha256(raw), spec["sha256"])

    def test_source_run_and_closed_tree_are_exact(self) -> None:
        source = self.document["source_run"]
        self.assertEqual(source["manifest"]["sha256"], EXPECTED_RUN_MANIFEST_SHA256)
        manifest = ROOT / source["manifest"]["path"]
        raw = manifest.read_bytes()
        self.assertEqual(len(raw), source["manifest"]["bytes"])
        self.assertEqual(_sha256(raw), source["manifest"]["sha256"])
        self.assertEqual(
            source["closed_tree"]["inventory_sha256"], EXPECTED_RUN_TREE_SHA256
        )
        self.assertEqual(source["closed_tree"]["files"], 445)
        self.assertEqual(source["closed_tree"]["file_bytes"], 119_253_658)

    def test_near_duplicate_is_not_a_unique_site_claim(self) -> None:
        self.assertEqual(
            self.document["near_duplicate_visual_relationships"],
            [
                {
                    "blind_ids": ["V57-B042", "V57-B046"],
                    "disposition": (
                        "treat_as_one_near_identical_visual_site_candidate_until_"
                        "exact_identity_resolution"
                    ),
                    "evidence": (
                        "same Sentinel scene pair and AOI bounds differing by less "
                        "than one microdegree; comparison pixels are near-identical "
                        "but not byte-identical"
                    ),
                    "unique_site_claim_created": False,
                }
            ],
        )

    def test_review_scope_cannot_create_atlas_or_status_facts(self) -> None:
        self.assertTrue(self.document["guardrails"])
        self.assertTrue(
            all(value is False for value in self.document["guardrails"].values())
        )
        self.assertEqual(
            self.document["decision_semantics"]["T"],
            "retain_for_visible_change_follow_up_only",
        )
        serialized = self.raw.decode("utf-8")
        self.assertNotIn('"current_status":', serialized)
        self.assertNotIn('"lifecycle_status":', serialized)
        self.assertNotIn('"it_capacity_mw":', serialized)

    def test_predecessor_decisions_match_except_blind_penta_uncertainty(self) -> None:
        by_queue = {
            member["queue_id"]: row["visual_verdict"]
            for row in self.document["lineage_records"]
            for member in row["members"]
        }
        self.assertEqual(
            {
                queue_id: by_queue[queue_id]
                for queue_id in (
                    "satq-02a713b5d0ec25375cffb0c3",
                    "satq-511257788faac7f8fe916b55",
                    "satq-5feb20b3df63076cce05ab3f",
                    "satq-ac9d66dd45f3a868190ec4c1",
                    "satq-ef22ae26b5cba60034c8567f",
                    "satq-b6f121dc644b91ad78eb479a",
                )
            },
            {
                "satq-02a713b5d0ec25375cffb0c3": "T",
                "satq-511257788faac7f8fe916b55": "R",
                "satq-5feb20b3df63076cce05ab3f": "R",
                "satq-ac9d66dd45f3a868190ec4c1": "T",
                "satq-ef22ae26b5cba60034c8567f": "T",
                "satq-b6f121dc644b91ad78eb479a": "U",
            },
        )


if __name__ == "__main__":
    unittest.main()
