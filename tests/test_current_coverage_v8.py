from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.current_coverage import (
    CurrentCoverageError,
    build_current_coverage_ledger,
    validate_current_coverage_ledger,
    write_current_coverage_ledger,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = ROOT / "sources" / "current-coverage-2026-07-19-v7.json"
DEFINITION = ROOT / "sources" / "current-coverage-2026-07-19-v8.json"
BUNDLE = ROOT / "current_coverage_ledgers" / "2026-07-19-v8"

DEFINITION_SHA256 = (
    "6593bdf4453f178aabd1e164161b1866126c9f947d30c7938ac40c0a249448f9"
)
LEDGER_SHA256 = (
    "e6b756fab1b72367d24fdde712ea28417714c248f4712b8d70a263b8bf5fa49b"
)
MANIFEST_SHA256 = (
    "7f6bc99bf3c77ea1b3c2d76d85a57d084e437ace2437e0129747428e3b9245ad"
)
BUNDLE_INVENTORY_SHA256 = (
    "078115d44b43cbd7005d7a155ee6928209b5472eb6a51e7285a31132aa4e159f"
)
REPLACEMENTS = {
    "construction-map-public-open-v11": "construction-map-public-open-v12",
    "construction-master-public-open-v11": "construction-master-public-open-v12",
    "coverage-audit-public-open-v10": "coverage-audit-public-open-v11",
    "federation-public-open-v9": "federation-public-open-v10",
    "seed-epoch-official-v20": "seed-epoch-official-v30",
}


def _bundle_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


class FrozenCurrentCoverageV8Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("ledger validation attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("ledger validation attempted network access"),
        ), patch.object(
            socket,
            "getaddrinfo",
            side_effect=AssertionError("ledger validation attempted DNS resolution"),
        ):
            first = validate_current_coverage_ledger(
                BUNDLE, definition_path=DEFINITION
            )
            second = validate_current_coverage_ledger(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first, second)
        self.assertEqual(first["ledger_id"], "current-coverage-2026-07-19-v8")
        self.assertEqual(len(first["input_checkpoints"]), 40)
        self.assertEqual(
            hashlib.sha256(
                (BUNDLE / "current-coverage-ledger.json").read_bytes()
            ).hexdigest(),
            LEDGER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(_bundle_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(entry.stat().st_mode) == 0o444
                and not entry.is_symlink()
                for entry in BUNDLE.iterdir()
            )
        )

    def test_exact_v7_successor_replaces_only_five_current_artifacts(self) -> None:
        previous = json.loads(PREVIOUS_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        previous_entries = {
            entry["artifact_id"]: entry for entry in previous["entries"]
        }
        current_entries = {entry["artifact_id"]: entry for entry in current["entries"]}
        self.assertEqual(
            set(current_entries),
            (set(previous_entries) - set(REPLACEMENTS)) | set(REPLACEMENTS.values()),
        )
        for artifact_id, entry in previous_entries.items():
            if artifact_id not in REPLACEMENTS:
                self.assertEqual(current_entries[artifact_id], entry)

        expected_checkpoints = {
            "construction-map-public-open-v12": {
                "coverage": (
                    "construction_maps/2026-07-19-public-open-v12/coverage.json",
                    6_236,
                    "63af71077ec6712f5c1dcd2cdc4fcd7591a1530999750b4d11a3e9a62d01ef65",
                ),
                "definition": (
                    "sources/construction-map-2026-07-19-public-open-v12.json",
                    7_399,
                    "aa94b20bd4e3264ead3756fd21e31fcea0a26fd8084e7511f970a9aad34644a2",
                ),
                "manifest": (
                    "construction_maps/2026-07-19-public-open-v12/manifest.json",
                    1_967,
                    "2e5d68db464ef88cea1df4477b8adc75a4a79b197c246adeaa8771cef65756e7",
                ),
            },
            "construction-master-public-open-v12": {
                "coverage": (
                    "construction_master/2026-07-19-public-open-v12/coverage.json",
                    29_709,
                    "be938a2ff916b2dc66dca75d19b48e3c27287101941d3282b12cc134cf66cf4d",
                ),
                "definition": (
                    "sources/construction-master-2026-07-19-public-open-v12.json",
                    15_027,
                    "286e60979bb313d0ca085ae1980009427e50521b520c6d47425452f5af9c45c5",
                ),
                "manifest": (
                    "construction_master/2026-07-19-public-open-v12/manifest.json",
                    47_668,
                    "f11a800cbaccacfc9204362d63ac08df1cdd580b5bbb5ede2d1da1e7f39a18cc",
                ),
            },
            "coverage-audit-public-open-v11": {
                "manifest": (
                    "audits/2026-07-19-public-open-coverage-v11/manifest.json",
                    2_240,
                    "edf1b0cdf1e842b1ea8a848c1e07d0c5cb0860b34fe267798daeef0158a0ea2c",
                ),
            },
            "federation-public-open-v10": {
                "index": (
                    "federated_indexes/2026-07-19-public-open-v10/federated-index.json",
                    17_791,
                    "aa6b55f29d237aa298cc6d2f3dfe5dfd57ed7bbd1ef6bd63688efd6be1e38251",
                ),
                "manifest": (
                    "federated_indexes/2026-07-19-public-open-v10/manifest.json",
                    986,
                    "7db9cb7e285f222ce92986e060d3974942cdf641d7e19fd3efaa88482025abd2",
                ),
            },
            "seed-epoch-official-v30": {
                "manifest": (
                    "releases/2026-07-19-open-seed-v30/manifest.json",
                    4_980,
                    "35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619",
                ),
            },
        }
        for artifact_id, expected in expected_checkpoints.items():
            actual = {
                checkpoint["checkpoint_id"]: (
                    checkpoint["path"],
                    checkpoint["bytes"],
                    checkpoint["sha256"],
                )
                for checkpoint in current_entries[artifact_id]["checkpoints"]
            }
            self.assertEqual(actual, expected)

        previous_gaps = {gap["gap_id"]: gap for gap in previous["parity_gaps"]}
        current_gaps = {gap["gap_id"]: gap for gap in current["parity_gaps"]}
        self.assertEqual(set(current_gaps), set(previous_gaps))
        self.assertEqual(len(current_gaps), 6)
        for gap_id, gap in previous_gaps.items():
            self.assertEqual(
                current_gaps[gap_id],
                {
                    **gap,
                    "affected_artifact_ids": [
                        REPLACEMENTS.get(artifact_id, artifact_id)
                        for artifact_id in gap["affected_artifact_ids"]
                    ],
                },
            )

    def test_metrics_and_scope_remain_nonadditive_and_source_scoped(self) -> None:
        ledger = build_current_coverage_ledger(DEFINITION).ledger
        counts = ledger["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 40)
        self.assertEqual(
            counts["by_access_tier"], {"local_restricted": 6, "public_open": 34}
        )
        self.assertEqual(counts["public_open_review_only_artifacts"], 21)
        self.assertEqual(
            counts["parity_gaps_by_status"],
            {
                "not_computed": 1,
                "partial_coverage": 3,
                "review_backlog": 1,
                "rights_blocked": 1,
            },
        )
        self.assertFalse(ledger["scope"]["cross_artifact_counts_are_additive"])
        self.assertFalse(ledger["scope"]["global_completeness_claimed"])
        self.assertFalse(
            ledger["scope"]["source_scoped_rows_are_unique_physical_sites"]
        )
        self.assertIsNone(ledger["scope"]["unique_physical_site_count"])
        artifacts = {entry["artifact_id"]: entry for entry in ledger["artifacts"]}

        self.assertEqual(
            artifacts["construction-map-public-open-v12"]["reported_metrics"],
            {
                "default_visible_rows": 6_479,
                "mapped_tier_a_rows": 199,
                "mapped_tier_b_rows": 6_280,
                "mapped_tier_c_rows": 102_494,
                "mapped_total_rows": 108_973,
                "mapped_unknown_country_rows": 102_541,
                "master_total_rows": 109_096,
                "unique_physical_sites": None,
                "unmapped_rows": 123,
            },
        )
        master = artifacts["construction-master-public-open-v12"][
            "reported_metrics"
        ]
        self.assertEqual(
            (
                master["total_master_rows"],
                master["tier_a_rows"],
                master["tier_b_rows"],
                master["tier_c_rows"],
                master["review_only_rows"],
            ),
            (109_096, 304, 6_298, 102_494, 108_792),
        )
        self.assertEqual(master["status_under_construction_rows"], 215)
        self.assertEqual(master["typed_capacity_evidence_observations"], 233)
        self.assertEqual(master["workload_evidence_observations"], 103)
        self.assertEqual(
            artifacts["coverage-audit-public-open-v11"]["reported_metrics"],
            {
                "coverage_groups": 421,
                "non_review_source_scoped_rows": 9_643,
                "open_gaps": 2_308,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 15_773,
                "unique_physical_sites": None,
            },
        )
        federation = artifacts["federation-public-open-v10"]["reported_metrics"]
        self.assertEqual(federation["construction_pipeline_records"], 6_434)
        self.assertEqual(federation["non_review_construction_pipeline_records"], 304)
        self.assertEqual(federation["source_scoped_rows"], 15_773)
        self.assertIsNone(federation["unique_physical_sites"])
        self.assertEqual(
            artifacts["seed-epoch-official-v30"]["reported_metrics"],
            {
                "capacity_observations": 401,
                "construction_pipeline_records": 184,
                "construction_source_signals": 153,
                "evidence_records": 215,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 348,
            },
        )

    def test_contract_metrics_and_frozen_mode_fail_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        changes: list[tuple[dict, str]] = []
        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-19T22:05:01Z"
        changes.append((changed, "v8 generation timestamp changed"))
        changed = deepcopy(document)
        changed["entries"][0]["artifact_id"] = "changed-artifact"
        changes.append((changed, "v8 must contain exactly 40 current artifacts"))
        changed = deepcopy(document)
        master = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "construction-master-public-open-v12"
        )
        master["checkpoints"][0]["sha256"] = "0" * 64
        changes.append(
            (changed, "v8 construction-master-public-open-v12 current checkpoint contract changed")
        )
        changed = deepcopy(document)
        gap = next(
            gap
            for gap in changed["parity_gaps"]
            if "seed-epoch-official-v30" in gap["affected_artifact_ids"]
        )
        gap["affected_artifact_ids"] = [
            "seed-epoch-official-v20"
            if artifact_id == "seed-epoch-official-v30"
            else artifact_id
            for artifact_id in gap["affected_artifact_ids"]
        ]
        changes.append((changed, "v8 parity gaps contain stale current artifacts"))

        for index, (changed, message) in enumerate(changes):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=DEFINITION.parent,
                prefix=f"changed-v8-{index}-",
                suffix=".json",
            ) as temporary:
                temporary.write(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                temporary.flush()
                with self.assertRaisesRegex(CurrentCoverageError, message):
                    build_current_coverage_ledger(temporary.name)

        with tempfile.TemporaryDirectory() as temporary:
            unfrozen = Path(temporary) / "unfrozen"
            write_current_coverage_ledger(DEFINITION, unfrozen)
            with self.assertRaisesRegex(
                CurrentCoverageError, "ledger bundle must be frozen 0555/0444"
            ):
                validate_current_coverage_ledger(
                    unfrozen, definition_path=DEFINITION
                )


if __name__ == "__main__":
    unittest.main()
