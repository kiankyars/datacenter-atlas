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

import datacenter_atlas.datacenter_atlas.satellite_change_review_explicit_v1 as implementation
from datacenter_atlas.satellite_change_review_explicit_v1 import (
    BLIND_DECISIONS_FILENAME,
    BLIND_REVIEW_DRAFT_BIRTHTIME,
    BLIND_REVIEW_DRAFT_RECORDED_AT,
    BLIND_REVIEW_DRAFT_SHA256,
    DECISION_SEMANTICS,
    DEFINITION_FILENAME,
    EXPECTED_COUNTS,
    GUARDRAILS,
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    README_FILENAME,
    REVIEW_ID,
    REVIEWS_FILENAME,
    SUMMARY_FILENAME,
    build_analyst_review,
    validate_analyst_review,
)


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "satellite_change_reviews" / REVIEW_ID
GENERATED_AT = "2026-07-21T14:24:30.000000Z"
MANIFEST_SHA256 = "d5184c13eca93b9f07711781665deca71d271ec263627437285e813cdb495b12"
TREE_SHA256 = "2f671c8dee331e10f2b297145d6c7eb9efdf300f56592d32048ab075d7f9f2ad"
DECISION_ROWS_SHA256 = "04a12cffee4d728a0ce9abcacccafc678fd07f92e58093a290f7043ecc20a5b1"
EXPECTED_MEMBERS = {
    "ATTRIBUTION.txt": (
        277,
        "6aa7134881d32ca4a298ebe7f2b747aed8c07b723649214f6c6b902037bc2aab",
    ),
    README_FILENAME: (
        994,
        "fad506f870e3447039cee2e09e3a03b1a1420321ae098bdd7ce38f503acc5d99",
    ),
    REVIEWS_FILENAME: (
        24_913,
        "951321125a123cb3be788dfb4d5b44bfddd309318bd740b45671d06c62ab2059",
    ),
    BLIND_DECISIONS_FILENAME: (
        6_890,
        "6e6bc074400b13d47c23953c2224ab50e12b4b6f2b48a1377237275b3edde0eb",
    ),
    DEFINITION_FILENAME: (
        4_158,
        "b2e6acbd705f4d0229222bfa0e6d17532e3866225315280c578933e00bbd3ff2",
    ),
    MANIFEST_FILENAME: (4_203, MANIFEST_SHA256),
    MANIFEST_HASH_FILENAME: (
        80,
        "f752bbf21e2813f2866d24da4c783c63fbec070a1244dd8cfb529ecfc79b6bc4",
    ),
    SUMMARY_FILENAME: (
        3_352,
        "ccdc4ae77e550073469c8b1672d961e7be8a7e26ca4c1d782926effd3e6afeef",
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


class ExplicitV1AnalystReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = json.loads((BUNDLE / DEFINITION_FILENAME).read_text())
        cls.blind = json.loads((BUNDLE / BLIND_DECISIONS_FILENAME).read_text())
        cls.rows = [
            json.loads(line)
            for line in (BUNDLE / REVIEWS_FILENAME).read_bytes().splitlines()
        ]
        cls.summary = json.loads((BUNDLE / SUMMARY_FILENAME).read_text())
        cls.manifest_raw = (BUNDLE / MANIFEST_FILENAME).read_bytes()
        cls.manifest = json.loads(cls.manifest_raw)

    def test_frozen_review_reproduces_twice_offline(self) -> None:
        with mock.patch.object(
            socket,
            "socket",
            side_effect=AssertionError("analyst review attempted network access"),
        ):
            first = validate_analyst_review(BUNDLE)
            second = validate_analyst_review(BUNDLE)
            rebuilt = build_analyst_review(GENERATED_AT)
        self.assertEqual(first, second)
        self.assertEqual(first["review_id"], REVIEW_ID)
        self.assertEqual(first["tree_inventory"]["inventory_sha256"], TREE_SHA256)
        self.assertEqual(
            rebuilt,
            {path.name: path.read_bytes() for path in BUNDLE.iterdir() if path.is_file()},
        )

    def test_exact_members_tree_modes_and_timestamp_boundary(self) -> None:
        self.assertEqual(_sha256(self.manifest_raw), MANIFEST_SHA256)
        self.assertEqual(
            (BUNDLE / MANIFEST_HASH_FILENAME).read_text(encoding="ascii"),
            f"{MANIFEST_SHA256}  {MANIFEST_FILENAME}\n",
        )
        self.assertEqual(set(EXPECTED_MEMBERS), {path.name for path in BUNDLE.iterdir()})
        for name, (size, digest) in EXPECTED_MEMBERS.items():
            raw = (BUNDLE / name).read_bytes()
            self.assertEqual((len(raw), _sha256(raw)), (size, digest))
            self.assertEqual(stat.S_IMODE((BUNDLE / name).stat().st_mode), 0o444)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual(
            implementation.preparation._tree_inventory(BUNDLE),
            {
                "directories": 1,
                "file_bytes": 44_867,
                "files": 8,
                "inventory_sha256": TREE_SHA256,
            },
        )
        generated = implementation.preparation._timestamp(
            GENERATED_AT, "generated_at"
        )[1]
        self.assertGreaterEqual(BUNDLE.stat().st_ctime + 1e-6, generated.timestamp())

    def test_every_fresh_reviewer_decision_is_preserved_exactly(self) -> None:
        self.assertEqual(len(self.rows), 11)
        source = self.blind["decisions"]
        projected = [
            {key: row[key] for key in decision}
            for row, decision in zip(self.rows, source, strict=True)
        ]
        self.assertEqual(projected, source)
        self.assertEqual(
            _sha256(b"".join(implementation._canonical_line(row) for row in source)),
            DECISION_ROWS_SHA256,
        )
        self.assertEqual(
            Counter(row["disposition"] for row in self.rows),
            Counter({"retained_for_manual_followup": 7, "rejected_for_site_promotion": 4}),
        )
        self.assertEqual(
            Counter(row["visible_change"] for row in self.rows),
            Counter({"clear": 7, "ambiguous": 4}),
        )
        self.assertEqual(
            Counter(row["image_quality"] for row in self.rows),
            Counter({"usable": 7, "partially_obscured": 4}),
        )
        self.assertEqual(
            {(row["blind_id"], row["visually_identical_to"]) for row in self.rows if "visually_identical_to" in row},
            {("V71-X001", "V71-X003"), ("V71-X003", "V71-X001")},
        )

    def test_temporal_correction_is_explicit_and_decision_only(self) -> None:
        self.assertEqual(self.blind["recorded_at"], GENERATED_AT)
        self.assertEqual(self.blind["review_id"], implementation.BLIND_REVIEW_ID)
        self.assertEqual(
            self.blind["draft"],
            {
                "bytes": 6_118,
                "disposition": "rejected_temporal_metadata_only",
                "path": "sources/satellite-change-blind-review-2026-07-21-open-seed-v71-explicit-11-v1.json",
                "sha256": BLIND_REVIEW_DRAFT_SHA256,
            },
        )
        temporal = self.blind["temporal_integrity"]
        self.assertEqual(temporal["draft_recorded_at"], BLIND_REVIEW_DRAFT_RECORDED_AT)
        self.assertEqual(temporal["draft_birthtime"], BLIND_REVIEW_DRAFT_BIRTHTIME)
        self.assertTrue(temporal["draft_recorded_at_precedes_artifact_bytes"])
        self.assertTrue(temporal["draft_retained_unchanged"])
        self.assertFalse(temporal["decision_content_changed"])
        self.assertEqual(temporal["decision_rows_sha256"], DECISION_ROWS_SHA256)

    def test_all_six_source_artifacts_are_bound_per_job(self) -> None:
        expected = {
            "after.png",
            "before.png",
            "change-overlay.png",
            "change-proposals.geojson",
            "comparison.png",
            "report.json",
        }
        self.assertEqual(len({row["queue_id"] for row in self.rows}), 11)
        for row in self.rows:
            self.assertEqual(set(row["input_artifacts"]), expected)
            self.assertEqual(
                row["visual_artifacts_inspected"],
                ["after.png", "before.png", "change-overlay.png", "comparison.png"],
            )
            for spec in row["input_artifacts"].values():
                path = ROOT / spec["path"]
                self.assertFalse(path.is_symlink())
                raw = path.read_bytes()
                self.assertEqual((len(raw), _sha256(raw)), (spec["bytes"], spec["sha256"]))
        self.assertEqual(self.summary["counts"]["source_artifacts_hash_bound"], 66)
        self.assertEqual(self.summary["counts"]["visual_artifacts_inspected"], 44)

    def test_scope_is_review_only_and_creates_no_atlas_facts(self) -> None:
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        self.assertEqual(self.summary["guardrails"], GUARDRAILS)
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.manifest["decision_semantics"], DECISION_SEMANTICS)
        self.assertEqual(self.summary["counts"]["image_quality"], EXPECTED_COUNTS["image_quality"])
        self.assertEqual(
            self.summary["counts"]["promotion_dispositions"],
            EXPECTED_COUNTS["promotion_dispositions"],
        )
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

    def test_source_runtime_builder_pins_no_replace_and_cli(self) -> None:
        self.assertEqual(
            self.definition["runtime"], implementation.preparation._runtime_lineage()
        )
        self.assertEqual(
            self.definition["builder"]["files"],
            {
                "cli": {
                    "bytes": 1_752,
                    "path": "scripts/build_satellite_change_review_explicit_v1.py",
                    "sha256": "bdfc528618883e6b3b12909ecb50595e9206fde9207572de5fc0675d5112cf70",
                },
                "module": {
                    "bytes": 24_828,
                    "path": "datacenter_atlas/satellite_change_review_explicit_v1.py",
                    "sha256": "c496441e12dd94e1fb113f70e896feb38914758aa38bbe88063069f2af8c0071",
                },
                "root_shim": {
                    "bytes": 164,
                    "path": "satellite_change_review_explicit_v1.py",
                    "sha256": "3f962d7f08e568d20caa1e5789886ee06df03ba41402ea6ab6d81b2ccf2c35a8",
                },
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            final = root / "final"
            stage.mkdir()
            final.mkdir()
            with self.assertRaisesRegex(
                implementation.preparation.ExplicitV1BlindPreparationError,
                "refusing existing output",
            ):
                implementation.preparation._promote_noreplace(stage, final)
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_satellite_change_review_explicit_v1.py"),
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
        self.assertEqual(payload["tree_inventory"]["inventory_sha256"], TREE_SHA256)


if __name__ == "__main__":
    unittest.main()
