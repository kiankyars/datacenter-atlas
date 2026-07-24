from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest import mock

import datacenter_atlas.datacenter_atlas.satellite_change_review_explicit_v83 as implementation
from datacenter_atlas.satellite_change_review_explicit_v83 import (
    BLIND_DECISIONS_FILENAME,
    EXPECTED_APPROXIMATE_LINK,
    EXPECTED_EXACT_VISUAL_GROUPS,
    EXPECTED_ROW_COUNTS,
    EXPECTED_UNIQUE_EXACT_COUNTS,
    ExplicitV83AnalystReviewError,
    GUARDRAILS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    OUTPUT_PATH,
    PART_A_FILENAME,
    PART_A_PATH,
    PART_A_SHA256,
    PART_B_FILENAME,
    PART_B_PATH,
    PART_B_SHA256,
    REVIEW_ID,
    REVIEWS_FILENAME,
    SUMMARY_FILENAME,
    build_analyst_review,
    publish_analyst_review,
    validate_analyst_review,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = OUTPUT_PATH
PREVIOUS_REVIEW_ID = "2026-07-21-open-seed-v71-active-explicit-11-review-v1"
PREVIOUS_MANIFEST_SHA256 = (
    "d5184c13eca93b9f07711781665deca71d271ec263627437285e813cdb495b12"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ExplicitV83AnalystReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = json.loads((BUNDLE / "definition.json").read_text())
        cls.combined = json.loads(
            (BUNDLE / BLIND_DECISIONS_FILENAME).read_text()
        )
        cls.rows = [
            json.loads(line)
            for line in (BUNDLE / REVIEWS_FILENAME).read_bytes().splitlines()
        ]
        cls.summary = json.loads((BUNDLE / SUMMARY_FILENAME).read_text())
        cls.manifest_raw = (BUNDLE / MANIFEST_FILENAME).read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)

    def test_frozen_review_reproduces_twice_offline(self) -> None:
        generated_at = self.definition["generated_at"]
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("combined review attempted network access"),
        ):
            first = validate_analyst_review(BUNDLE)
            second = validate_analyst_review(BUNDLE)
            rebuilt_a = build_analyst_review(generated_at)
            rebuilt_b = build_analyst_review(generated_at)
        self.assertEqual(first, second)
        self.assertEqual(rebuilt_a, rebuilt_b)
        self.assertEqual(
            rebuilt_a,
            {path.name: path.read_bytes() for path in BUNDLE.iterdir()},
        )
        self.assertEqual(first["review_id"], REVIEW_ID)

    def test_exact_sources_and_all_68_decisions_are_preserved(self) -> None:
        raw_a = PART_A_PATH.read_bytes()
        raw_b = PART_B_PATH.read_bytes()
        self.assertEqual((len(raw_a), _sha256(raw_a)), (14_135, PART_A_SHA256))
        self.assertEqual((len(raw_b), _sha256(raw_b)), (13_230, PART_B_SHA256))
        self.assertEqual((BUNDLE / PART_A_FILENAME).read_bytes(), raw_a)
        self.assertEqual((BUNDLE / PART_B_FILENAME).read_bytes(), raw_b)
        source = [
            *json.loads(raw_a)["decisions"],
            *json.loads(raw_b)["decisions"],
        ]
        self.assertEqual(self.combined["decisions"], source)
        projected = [
            {key: row[key] for key in decision}
            for decision, row in zip(source, self.rows, strict=True)
        ]
        self.assertEqual(projected, source)
        self.assertEqual(len(self.rows), 68)
        self.assertEqual(
            Counter(row["image_quality"] for row in self.rows),
            Counter(EXPECTED_ROW_COUNTS["image_quality"]),
        )
        self.assertEqual(
            Counter(row["visible_change"] for row in self.rows),
            Counter(EXPECTED_ROW_COUNTS["visible_change"]),
        )
        self.assertEqual(
            Counter(row["disposition"] for row in self.rows),
            Counter(EXPECTED_ROW_COUNTS["promotion_dispositions"]),
        )

    def test_exact_duplicate_accounting_excludes_approximate_similarity(self) -> None:
        groups = {
            row["visual_evidence_set_sha256"]: tuple(row["blind_ids"])
            for row in self.summary["accounting"]["exact_duplicate_groups"]
        }
        self.assertEqual(groups, EXPECTED_EXACT_VISUAL_GROUPS)
        unique = self.summary["accounting"][
            "unique_exact_visual_evidence_sets"
        ]
        self.assertEqual(unique, {"total": 65, **EXPECTED_UNIQUE_EXACT_COUNTS})
        flags = {
            (row["reported_by"], row["reported_target"]): row
            for row in self.summary["accounting"]["reviewer_similarity_flags"]
        }
        approximate = flags[EXPECTED_APPROXIMATE_LINK]
        self.assertEqual(
            approximate["type"],
            "reviewer_reported_approximate_visual_similarity",
        )
        self.assertFalse(approximate["exact_four_image_hash_match"])
        self.assertFalse(approximate["counted_as_exact_duplicate"])
        rows = {row["blind_id"]: row for row in self.rows}
        self.assertNotEqual(
            rows["V83-X052"]["exact_visual_evidence"]["set_sha256"],
            rows["V83-X041"]["exact_visual_evidence"]["set_sha256"],
        )
        self.assertTrue(
            rows["V83-X052"]["exact_visual_evidence"][
                "unique_set_representative_for_accounting"
            ]
        )
        self.assertEqual(
            sum(
                row["exact_visual_evidence"][
                    "unique_set_representative_for_accounting"
                ]
                for row in self.rows
            ),
            65,
        )

    def test_exact_lineage_commitment_entities_and_artifacts_are_bound(self) -> None:
        source = json.loads(
            (implementation.SOURCE_RUN_PATH / "batch-manifest.json").read_text()
        )
        order = dict(
            implementation.preparation._blind_order(
                tuple(source["selection"]["selected_queue_ids"])
            )
        )
        self.assertEqual(
            implementation.preparation._lineage_commitment(
                source, tuple(order.items())
            ),
            implementation.SOURCE_LINEAGE_COMMITMENT_SHA256,
        )
        self.assertEqual(
            self.definition["sources"]["blind_preparation"][
                "lineage_commitment_sha256"
            ],
            implementation.SOURCE_LINEAGE_COMMITMENT_SHA256,
        )
        for row in self.rows:
            queue_id = order[row["blind_id"]]
            self.assertEqual(row["queue_id"], queue_id)
            self.assertEqual(row["source_entity_lineage"], source["jobs"][queue_id]["entity"])
            self.assertEqual(set(row["input_artifacts"]), implementation.SOURCE_ARTIFACT_NAMES)
            self.assertEqual(set(row["review_artifacts"]), set(implementation.VISUAL_ARTIFACT_NAMES))
            for spec in [
                *row["input_artifacts"].values(),
                *row["review_artifacts"].values(),
            ]:
                path = ROOT / spec["path"]
                self.assertFalse(path.is_symlink())
                raw = path.read_bytes()
                self.assertEqual((len(raw), _sha256(raw)), (spec["bytes"], spec["sha256"]))
        self.assertEqual(self.summary["counts"]["source_artifacts_hash_bound"], 408)
        self.assertEqual(self.summary["counts"]["review_artifacts_hash_bound"], 272)

    def test_zero_promotion_scope_and_temporal_incident_are_explicit(self) -> None:
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        self.assertEqual(self.summary["guardrails"], GUARDRAILS)
        self.assertTrue(
            self.combined["temporal_integrity"][
                "part_a_recorded_at_precedes_artifact_birthtime"
            ]
        )
        self.assertTrue(
            self.combined["temporal_integrity"][
                "part_b_artifact_birthtime_precedes_recorded_at"
            ]
        )
        self.assertTrue(
            all(
                row["decision_scope"]
                == "identity_blind_visible_change_triage_only"
                for row in self.rows
            )
        )
        self.assertEqual(
            sum(row["disposition"] == "retained_for_manual_followup" for row in self.rows),
            47,
        )
        self.assertFalse(any("atlas_mutation" in row for row in self.rows))

    def test_tamper_double_build_and_no_replace_guards(self) -> None:
        with mock.patch.object(implementation, "PART_B_SHA256", "0" * 64):
            with self.assertRaisesRegex(
                ExplicitV83AnalystReviewError, "review part B changed"
            ):
                build_analyst_review(self.definition["generated_at"])
        first = build_analyst_review(self.definition["generated_at"])
        second = build_analyst_review(self.definition["generated_at"])
        self.assertEqual(first, second)
        future = (datetime.now(UTC) + timedelta(seconds=120)).isoformat().replace(
            "+00:00", "Z"
        )
        with self.assertRaisesRegex(
            ExplicitV83AnalystReviewError, "refusing existing output"
        ):
            publish_analyst_review(future, BUNDLE)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.mkdir()
            final.mkdir()
            with self.assertRaisesRegex(
                implementation.preparation.ExplicitV83BlindPreparationError,
                "refusing existing output",
            ):
                implementation.preparation._promote_noreplace(stage, final)

    def test_exact_members_modes_clock_and_previous_review_regression(self) -> None:
        manifest_sha256 = _sha256(self.manifest_raw)
        self.assertEqual(
            (BUNDLE / MANIFEST_HASH_FILENAME).read_text(encoding="ascii"),
            f"{manifest_sha256}  {MANIFEST_FILENAME}\n",
        )
        for path in BUNDLE.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        generated = implementation.preparation._timestamp(
            self.definition["generated_at"], "generated_at"
        )[1]
        self.assertGreaterEqual(BUNDLE.stat().st_ctime + 1e-6, generated.timestamp())
        previous = (
            ROOT
            / "satellite_change_reviews"
            / PREVIOUS_REVIEW_ID
            / MANIFEST_FILENAME
        ).read_bytes()
        self.assertEqual(_sha256(previous), PREVIOUS_MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
