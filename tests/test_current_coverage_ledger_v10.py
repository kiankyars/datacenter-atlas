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
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = ROOT / "sources" / "current-coverage-2026-07-19-v9.json"
DEFINITION = ROOT / "sources" / "current-coverage-2026-07-20-v10.json"
PREVIOUS_BUNDLE = ROOT / "current_coverage_ledgers" / "2026-07-19-v9"
BUNDLE = ROOT / "current_coverage_ledgers" / "2026-07-20-v10"

DEFINITION_SHA256 = (
    "bb86166ba643fd89f30c0cf4bf80d76f85e2f05823dfdfc213041b0bccc9cb93"
)
LEDGER_SHA256 = (
    "829f64bc8cca100386da7f8a303049fb8021c60ecfdb6c4d31947a96e155383b"
)
MANIFEST_SHA256 = (
    "e033075cc5539b71761055e4a4b43ebb47e3d4032099342853195e78214791aa"
)
BUNDLE_INVENTORY_SHA256 = (
    "a0471438610487c7facfc1358ebf2c6819de0a05da20fb4e7a008e11b46c4943"
)
PREVIOUS_DEFINITION_SHA256 = (
    "b4686cfe1721bca36775bcf05cc9e232b60e6850848cf2a047cb5e096486b365"
)
PREVIOUS_MANIFEST_SHA256 = (
    "b96e641ec861f1db20b312dd281fb9d6d5327236c8fef1389fd00f6144e419b9"
)

REPLACEMENTS = {
    "construction-map-public-open-v13": "construction-map-public-open-v14",
    "construction-master-public-open-v13": "construction-master-public-open-v14",
    "coverage-audit-public-open-v12": "coverage-audit-public-open-v13",
    "federation-public-open-v11": "federation-public-open-v12",
    "seed-epoch-official-v32": "seed-epoch-official-v33",
}
RECOVERY_ID = "satellite-recovery-unknown033-review-v1"
CURRENT_FAMILIES = {
    "construction-map-public-open": "construction-map-public-open-v14",
    "construction-master-public-open": "construction-master-public-open-v14",
    "coverage-audit-public-open": "coverage-audit-public-open-v13",
    "federation-public-open": "federation-public-open-v12",
    "satellite-recovery": RECOVERY_ID,
    "satellite-unknown-batch": "satellite-unknown-batch-030",
    "seed-epoch-official": "seed-epoch-official-v33",
}
ACCEPTED_PINS = {
    "sources/construction-master-2026-07-19-public-open-v14.json": (
        "2483d9965f47756468776f2e377ad7e25720e858dea8798cf0825448aa3870f4"
    ),
    "construction_master/2026-07-19-public-open-v14/manifest.json": (
        "12cb7e843d264bae9d8637db81ac76988c89e2e3eb926ea1fcc1d43077a8d88b"
    ),
    "sources/construction-map-2026-07-19-public-open-v14.json": (
        "7ad7320bbbb8d1ae4bef56363177fe904891be9527e35e31eedc9103b1122db9"
    ),
    "construction_maps/2026-07-19-public-open-v14/manifest.json": (
        "85f102967b8a6329c6d4466e61d1773132ee71b92cad05fc014b475eb0ef75f1"
    ),
    "sources/federation-2026-07-19-public-open-v12.json": (
        "d0ab8b792e28f00910ed0a698e1e358c51961c46c154a95265e422e9b4b93bc7"
    ),
    "federated_indexes/2026-07-19-public-open-v12/manifest.json": (
        "fbcca9103d878379277b7ab2e6dccb4cb3981d4eb1c1652b3dbf178adf3dca6f"
    ),
    "sources/coverage-audit-2026-07-19-public-open-v13.json": (
        "2745fd688f2727dc954b733386a00fbe8cf00401e5aeec4a451528c6d0bc9d9e"
    ),
    "audits/2026-07-19-public-open-coverage-v13/manifest.json": (
        "c91fedfebe19bdc8b8b7a21d328184b532de9ec07d31d9d27b1c1495a612ff4d"
    ),
    "sources/open-seed-2026-07-19-v33.json": (
        "2f89c97de719ebb9dac950c1573726b2d1c835f11daaede2ea62395ae4df5536"
    ),
    "releases/2026-07-19-open-seed-v33/manifest.json": (
        "9cf56d40453cd5fedcace87d763c8fec90bba08fe7fc8df242666a19f459f7b4"
    ),
    "definitions/satellite_recoveries/accepted-2026-07-20-v1.json": (
        "507b606c4ab65605766d7726072d715649830467838d9d24d423ba3b8aac59ad"
    ),
    "definitions/satellite_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25.json": (
        "1b054ac9c1091e1470576fcf9f14df05a64cb6d679a22ab413430957ffbcb420"
    ),
    "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25/recovery-manifest.json": (
        "178f52ad3c42117ea19561c123eef87fe1ed7331c79e9c5c1596bd8d2b7cbfb1"
    ),
}


def _bundle_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def _metrics(ledger: dict, artifact_id: str) -> dict:
    return next(
        artifact["reported_metrics"]
        for artifact in ledger["artifacts"]
        if artifact["artifact_id"] == artifact_id
    )


def _changed_metrics(previous: dict, current: dict) -> dict:
    return {
        label: (previous[label], current[label])
        for label in sorted(previous)
        if previous[label] != current[label]
    }


class FrozenCurrentCoverageLedgerV10Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256(PREVIOUS_DEFINITION.read_bytes()).hexdigest(),
            PREVIOUS_DEFINITION_SHA256,
        )
        for relative_path, expected_sha256 in ACCEPTED_PINS.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                expected_sha256,
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
            previous = validate_current_coverage_ledger(
                PREVIOUS_BUNDLE, definition_path=PREVIOUS_DEFINITION
            )
        self.assertEqual(first, second)
        self.assertEqual(first["ledger_id"], "current-coverage-2026-07-20-v10")
        self.assertEqual(len(first["input_checkpoints"]), 41)
        self.assertEqual(previous["ledger_id"], "current-coverage-2026-07-19-v9")
        self.assertEqual(
            hashlib.sha256((BUNDLE / "current-coverage-ledger.json").read_bytes()).hexdigest(),
            LEDGER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((PREVIOUS_BUNDLE / "manifest.json").read_bytes()).hexdigest(),
            PREVIOUS_MANIFEST_SHA256,
        )
        self.assertEqual(_bundle_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                entry.is_file()
                and not entry.is_symlink()
                and stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in BUNDLE.iterdir()
            )
        )

    def test_exact_v9_successor_replaces_five_and_adds_one_review_artifact(self) -> None:
        previous = json.loads(PREVIOUS_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        previous_entries = {
            entry["artifact_id"]: entry for entry in previous["entries"]
        }
        current_entries = {
            entry["artifact_id"]: entry for entry in current["entries"]
        }
        self.assertEqual(len(previous_entries), 40)
        self.assertEqual(len(current_entries), 41)
        self.assertEqual(
            set(current_entries),
            (set(previous_entries) - set(REPLACEMENTS))
            | set(REPLACEMENTS.values())
            | {RECOVERY_ID},
        )
        unchanged = set(previous_entries) - set(REPLACEMENTS)
        self.assertEqual(len(unchanged), 35)
        for artifact_id in unchanged:
            self.assertEqual(current_entries[artifact_id], previous_entries[artifact_id])
        self.assertEqual(current["scope"], previous["scope"])
        self.assertEqual(current["generated_at"], "2026-07-20T01:49:35Z")

        artifact_ids = [entry["artifact_id"] for entry in current["entries"]]
        self.assertEqual(artifact_ids, sorted(artifact_ids))
        for prefix, expected_id in CURRENT_FAMILIES.items():
            self.assertEqual(
                [artifact_id for artifact_id in artifact_ids if artifact_id.startswith(prefix)],
                [expected_id],
            )
        checkpoint_paths = {
            checkpoint["path"]
            for entry in current["entries"]
            for checkpoint in entry["checkpoints"]
        }
        self.assertFalse(
            any(
                fragment in path.lower()
                for path in checkpoint_paths
                for fragment in ("unknown-031", "unknown-032")
            )
        )

        recovery = current_entries[RECOVERY_ID]
        self.assertEqual(recovery["artifact_kind"], "satellite_catalog_batch")
        self.assertEqual(recovery["evidence_scope"], "review_only")
        self.assertEqual(recovery["publication_mode"], "public_review_or_discovery")
        self.assertEqual(recovery["record_units"], ["catalog_job"])
        self.assertEqual(
            [checkpoint["checkpoint_id"] for checkpoint in recovery["checkpoints"]],
            ["acceptance", "definition", "manifest"],
        )
        self.assertEqual(
            recovery["checkpoints"][1]["binding"],
            {
                "checkpoint_id": "acceptance",
                "json_pointer": "/accepted/definition",
            },
        )
        self.assertEqual(
            recovery["checkpoints"][2]["binding"],
            {
                "checkpoint_id": "acceptance",
                "json_pointer": "/accepted/recovery_manifest",
            },
        )

        recovery_gaps = {
            gap["gap_id"]
            for gap in current["parity_gaps"]
            if RECOVERY_ID in gap["affected_artifact_ids"]
        }
        self.assertEqual(
            recovery_gaps,
            {
                "global-construction-coverage-partial",
                "satellite-review-backlog",
            },
        )
        for gap in current["parity_gaps"]:
            self.assertTrue(set(gap["affected_artifact_ids"]).isdisjoint(REPLACEMENTS))

    def test_stack_metric_deltas_and_recovery_nonadditivity_are_exact(self) -> None:
        previous = build_current_coverage_ledger(PREVIOUS_DEFINITION).ledger
        current = build_current_coverage_ledger(DEFINITION).ledger
        expected_changes = {
            ("construction-map-public-open-v13", "construction-map-public-open-v14"): {
                "master_total_rows": (109_107, 109_111),
                "unmapped_rows": (134, 138),
            },
            ("construction-master-public-open-v13", "construction-master-public-open-v14"): {
                "construction_arithmetic_rows": (315, 319),
                "master_rows_with_capacity": (94, 95),
                "status_site_preparation_rows": (9, 10),
                "status_under_construction_rows": (226, 229),
                "tier_a_rows": (315, 319),
                "total_master_rows": (109_107, 109_111),
                "typed_capacity_evidence_observations": (233, 234),
            },
            ("coverage-audit-public-open-v12", "coverage-audit-public-open-v13"): {
                "coverage_groups": (441, 449),
                "non_review_source_scoped_rows": (9_665, 9_673),
                "open_gaps": (2_411, 2_446),
                "source_scoped_rows": (15_795, 15_803),
            },
            ("federation-public-open-v11", "federation-public-open-v12"): {
                "capacity_observations": (1_187, 1_189),
                "construction_pipeline_records": (6_445, 6_449),
                "non_review_construction_pipeline_records": (315, 319),
                "non_review_source_scoped_rows": (9_665, 9_673),
                "source_scoped_rows": (15_795, 15_803),
            },
            ("seed-epoch-official-v32", "seed-epoch-official-v33"): {
                "capacity_observations": (401, 403),
                "construction_pipeline_records": (195, 199),
                "construction_source_signals": (161, 165),
                "evidence_records": (226, 230),
                "source_scoped_entity_rows": (370, 378),
            },
        }
        for (previous_id, current_id), expected in expected_changes.items():
            self.assertEqual(
                _changed_metrics(
                    _metrics(previous, previous_id), _metrics(current, current_id)
                ),
                expected,
            )

        self.assertEqual(
            _metrics(current, RECOVERY_ID),
            {
                "atlas_release_integration": False,
                "recovered_batch_completed_jobs": 4_375,
                "recovered_batch_failed_jobs": 0,
                "recovered_batch_pending_jobs": 2_061,
                "recovered_batch_unavailable_no_scene_jobs": 300,
                "recovered_selected_jobs": 25,
                "selection_later_job_leakage": 0,
                "source_batch_promoted": False,
                "unique_physical_sites": None,
            },
        )
        counts = current["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 41)
        self.assertEqual(
            counts["by_access_tier"], {"local_restricted": 6, "public_open": 35}
        )
        self.assertEqual(counts["public_open_review_only_artifacts"], 22)
        self.assertEqual(
            counts["by_publication_mode"],
            {
                "local_quarantined": 6,
                "public_index_or_audit": 4,
                "public_metadata_or_aggregate_only": 5,
                "public_review_or_discovery": 21,
                "public_row_release": 5,
            },
        )
        self.assertFalse(current["scope"]["cross_artifact_counts_are_additive"])
        self.assertFalse(current["scope"]["global_completeness_claimed"])
        self.assertFalse(current["scope"]["benchmark_parity_claimed"])
        self.assertIsNone(current["scope"]["unique_physical_site_count"])

    def test_v10_contract_rejects_recovery_promotion_or_stale_scope(self) -> None:
        document = json.loads(DEFINITION.read_text())
        cases: list[tuple[dict, str]] = []

        changed = deepcopy(document)
        changed["entries"] = [
            entry for entry in changed["entries"] if entry["artifact_id"] != RECOVERY_ID
        ]
        cases.append((changed, "exactly 41 current artifacts"))

        changed = deepcopy(document)
        recovery = next(
            entry for entry in changed["entries"] if entry["artifact_id"] == RECOVERY_ID
        )
        recovery["evidence_scope"] = "source_scoped"
        cases.append((changed, "inventory or publication-mode arithmetic changed"))

        changed = deepcopy(document)
        for gap in changed["parity_gaps"]:
            if gap["gap_id"] == "satellite-review-backlog":
                gap["affected_artifact_ids"].remove(RECOVERY_ID)
        cases.append((changed, "recovery parity-gap scope changed"))

        for index, (changed, message) in enumerate(cases):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=DEFINITION.parent,
                prefix=f"changed-v10-{index}-",
                suffix=".json",
            ) as temporary:
                temporary.write(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                temporary.flush()
                with self.assertRaisesRegex(CurrentCoverageError, message):
                    build_current_coverage_ledger(temporary.name)


if __name__ == "__main__":
    unittest.main()
