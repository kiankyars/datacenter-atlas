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

from datacenter_atlas.satellite_change_review_v5 import (
    ALTERNATE_VIEW_SEMANTICS,
    BLIND_REVIEW_SOURCE,
    BUNDLE_FILES,
    DECISION_SEMANTICS,
    DEFINITION_SHA256,
    EXPECTED_QUEUE_IDS,
    EXPECTED_VERDICTS,
    GUARDRAILS,
    PREPARATION_DEFINITION,
    PREPARATION_MANIFEST,
    PREPARATION_PARTITION,
    PREPARATION_TREE,
    REVIEW_ID,
    SOURCE_FREEZE,
    SOURCE_FREEZE_SHA256,
    SOURCE_MANIFEST,
    SOURCE_PRODUCTION_TREE,
    SOURCE_REPLAY,
    SOURCE_TREE,
    SatelliteChangeReviewV5Error,
    build_satellite_change_review_v5,
    validate_satellite_change_review_v5,
    write_review_definition,
    write_satellite_change_review_v5,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v57-active-singleton-review-v1.json"
)
BUNDLE = ROOT / "satellite_change_reviews" / REVIEW_ID
SCRIPT = ROOT / "scripts/build_satellite_change_review_v5.py"
EXPECTED_FILES = {
    "ATTRIBUTION.txt": (
        260,
        "317fa301fe7925a829a4633fbeb71cf1b60e7b5b1224ee9334416fd48bce5030",
    ),
    "README.md": (
        1_198,
        "cdf1e134462ea2d342f7b6fda073aa3bf1d3aa0c56345090ca383e6fb47332d5",
    ),
    "analyst-reviews.jsonl": (
        23_162,
        "6984a64702be51ab7f94207b32f6238afb12f328a4bf798775499bd83be9c138",
    ),
    "manifest.json": (
        16_591,
        "bf853b11b644de3b990e8496b01436a456723adad225b91577e045625176658f",
    ),
    "manifest.sha256": (
        80,
        "a7a9e4c716812d1940831201c93adbfffc383eca94b06c052190c8eb6f3e02c7",
    ),
    "summary.json": (
        5_177,
        "17d27a4fe676619a07ee4b5bce759916d637f9d46c81a39799e3b74258657e86",
    ),
}
EXPECTED_REVIEW_TREE_SHA256 = (
    "86cd93dcf0d14a7e401ad087268ebf9a8dba625ccc87e070dc213bab790cf2af"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pin(path: Path) -> tuple[int, str, int]:
    return path.stat().st_size, _sha256(path.read_bytes()), stat.S_IMODE(
        path.stat().st_mode
    )


def _module():
    return importlib.import_module(build_satellite_change_review_v5.__module__)


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


class FrozenSatelliteChangeReviewV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = json.loads(DEFINITION.read_text())
        cls.blind_review = json.loads((ROOT / BLIND_REVIEW_SOURCE["path"]).read_text())
        cls.records = [
            json.loads(line)
            for line in (BUNDLE / "analyst-reviews.jsonl").read_text().splitlines()
        ]
        cls.summary = json.loads((BUNDLE / "summary.json").read_text())
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text())

    def test_frozen_bundle_reproduces_twice_offline_with_exact_pins(self) -> None:
        self.assertEqual(
            DEFINITION_SHA256,
            "262fb0f6716f6948eb81835c77a34a22e79eca592c9c83f748fb2820b6fcdb04",
        )
        self.assertEqual(_pin(DEFINITION), (4_909, DEFINITION_SHA256, 0o644))
        self.assertEqual(
            _pin(ROOT / BLIND_REVIEW_SOURCE["path"]),
            (11_630, BLIND_REVIEW_SOURCE["sha256"], 0o644),
        )
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        for filename, (size, digest) in EXPECTED_FILES.items():
            self.assertEqual(_pin(BUNDLE / filename), (size, digest, 0o444))
        inventory = _module()._tree_inventory(BUNDLE, "review bundle")
        self.assertEqual(inventory["files"], 6)
        self.assertEqual(inventory["file_bytes"], 46_468)
        self.assertEqual(
            inventory["inventory_sha256"], EXPECTED_REVIEW_TREE_SHA256
        )
        with _offline_guard():
            first = build_satellite_change_review_v5(DEFINITION)
            second = build_satellite_change_review_v5(DEFINITION)
            validated_first = validate_satellite_change_review_v5(
                BUNDLE, definition_path=DEFINITION
            )
            validated_second = validate_satellite_change_review_v5(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.files, second.files)
        self.assertEqual(
            first.files, {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        )
        self.assertEqual(validated_first, validated_second)
        self.assertEqual(validated_first["review_id"], REVIEW_ID)

    def test_identity_blind_verdicts_and_dispositions_are_exact(self) -> None:
        self.assertEqual(len(self.records), 6)
        self.assertEqual(
            [row["blind_id"] for row in self.records],
            [f"V57-S{index:03d}" for index in range(1, 7)],
        )
        self.assertEqual(
            tuple(row["queue_id"] for row in self.records), EXPECTED_QUEUE_IDS
        )
        self.assertEqual(
            {row["queue_id"]: row["visual_verdict"] for row in self.records},
            EXPECTED_VERDICTS,
        )
        self.assertEqual(
            Counter(row["visual_verdict"] for row in self.records),
            Counter({"T": 4, "R": 1, "U": 1}),
        )
        for row in self.records:
            self.assertEqual(
                row["visual_disposition"],
                DECISION_SEMANTICS[row["visual_verdict"]],
            )
            self.assertEqual(
                row["promotion_disposition"], row["visual_disposition"]
            )
            self.assertEqual(
                row["promotion_disposition_basis"],
                "identity_blind_visual_verdict",
            )
        self.assertEqual(
            self.summary["promotion_disposition_job_counts"],
            {
                "inconclusive": 1,
                "reject_imagery_promotion": 1,
                "retain_for_visible_change_follow_up_only": 4,
            },
        )

    def test_blind_method_and_four_visual_inputs_are_preserved(self) -> None:
        method = self.blind_review["method"]
        self.assertEqual(method["analyst_reviews"], 1)
        self.assertTrue(
            method["lineage_unsealed_after_visual_verdicts_were_fixed"]
        )
        self.assertEqual(method["visual_artifacts_inspected_per_job"], 4)
        self.assertEqual(
            self.blind_review["source_view_semantics"], ALTERNATE_VIEW_SEMANTICS
        )
        for source, record in zip(
            self.blind_review["lineage_records"], self.records, strict=True
        ):
            self.assertEqual(
                set(source["source_visual_artifacts"]),
                {"after.png", "before.png", "change-overlay.png", "comparison.png"},
            )
            self.assertEqual(
                record["visual_artifacts_inspected"],
                ["after.png", "before.png", "change-overlay.png", "comparison.png"],
            )
            self.assertEqual(
                record["visual_observations"], source["visual_observations"]
            )

    def test_every_job_binds_all_six_artifacts_without_fact_promotion(self) -> None:
        for record in self.records:
            self.assertEqual(
                set(record["input_artifacts"]),
                {
                    "after.png",
                    "before.png",
                    "change-overlay.png",
                    "change-proposals.geojson",
                    "comparison.png",
                    "report.json",
                },
            )
            for spec in record["input_artifacts"].values():
                path = ROOT / spec["path"]
                self.assertFalse(path.is_symlink())
                raw = path.read_bytes()
                self.assertEqual(len(raw), spec["bytes"])
                self.assertEqual(_sha256(raw), spec["sha256"])
        self.assertTrue(GUARDRAILS)
        self.assertTrue(all(value is False for value in GUARDRAILS.values()))
        self.assertEqual(self.summary["guardrails"], GUARDRAILS)
        self.assertEqual(self.manifest["guardrails"], GUARDRAILS)
        for forbidden in (
            "capacity",
            "current_status",
            "data_centre_type",
            "entity",
            "lifecycle_status",
            "operator",
            "power",
            "pue",
            "site_count",
            "workload",
        ):
            self.assertFalse(_contains_key(self.records, forbidden))

    def test_preparation_run_tree_freeze_and_replay_pins_are_exact(self) -> None:
        self.assertEqual(
            self.definition["source_change_preparation"],
            {
                "closed_tree": PREPARATION_TREE,
                "definition": PREPARATION_DEFINITION,
                "manifest": PREPARATION_MANIFEST,
                "partition": PREPARATION_PARTITION,
            },
        )
        self.assertEqual(
            self.definition["source_change_run"],
            {
                "closed_tree": SOURCE_TREE,
                "freeze_manifest": SOURCE_FREEZE,
                "freeze_sha256": SOURCE_FREEZE_SHA256,
                "manifest": SOURCE_MANIFEST,
                "production_tree": SOURCE_PRODUCTION_TREE,
                "replay": SOURCE_REPLAY,
                "run_input_definition": PREPARATION_DEFINITION,
            },
        )
        self.assertEqual(
            self.summary["alternate_view_semantics"], ALTERNATE_VIEW_SEMANTICS
        )
        self.assertEqual(self.summary["counts"]["source_artifacts_hash_bound"], 36)
        self.assertEqual(self.summary["counts"]["visual_artifacts_inspected"], 24)

    def test_tampered_blind_input_and_visual_artifact_fail_closed(self) -> None:
        module = _module()
        original = module._read_regular
        blind_path = (ROOT / BLIND_REVIEW_SOURCE["path"]).resolve()

        def tampered_blind(path: Path, label: str) -> bytes:
            raw = original(path, label)
            return raw + b" " if path.resolve() == blind_path else raw

        with patch.object(module, "_read_regular", side_effect=tampered_blind):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV5Error, "blind review source checkpoint changed"
            ):
                build_satellite_change_review_v5(DEFINITION)

        visual_path = (
            ROOT
            / self.records[0]["input_artifacts"]["comparison.png"]["path"]
        ).resolve()

        def tampered_visual(path: Path, label: str) -> bytes:
            raw = original(path, label)
            if path.resolve() == visual_path:
                return bytes([raw[0] ^ 1]) + raw[1:]
            return raw

        with patch.object(module, "_read_regular", side_effect=tampered_visual):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV5Error, "singleton source artifact changed"
            ):
                build_satellite_change_review_v5(DEFINITION)

    def test_writers_fail_closed_and_cli_validates(self) -> None:
        with self.assertRaisesRegex(SatelliteChangeReviewV5Error, "existing output"):
            write_review_definition(ROOT, DEFINITION)
        with self.assertRaisesRegex(SatelliteChangeReviewV5Error, "existing output"):
            write_satellite_change_review_v5(DEFINITION, BUNDLE)
        with self.assertRaisesRegex(SatelliteChangeReviewV5Error, "freeze=True"):
            write_satellite_change_review_v5(DEFINITION, BUNDLE, freeze=False)
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
                "jobs": 6,
                "output": str(BUNDLE),
                "review_id": REVIEW_ID,
                "validated": True,
                "views": 6,
            },
        )
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.satellite_change_review_v5 import "
            "validate_satellite_change_review_v5; "
            f"m=validate_satellite_change_review_v5(Path({str(BUNDLE)!r}), "
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

    def test_local_date_paths_never_use_future_july_21(self) -> None:
        self.assertIn("2026-07-20", REVIEW_ID)
        self.assertNotIn("2026-07-21", REVIEW_ID)
        self.assertIn("2026-07-20", str(DEFINITION))
        self.assertNotIn("2026-07-21", str(DEFINITION))
        self.assertIn("2026-07-20", str(BUNDLE))
        self.assertNotIn("2026-07-21", str(BUNDLE))


if __name__ == "__main__":
    unittest.main()
