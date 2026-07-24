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
PREVIOUS_DEFINITION = ROOT / "sources" / "current-coverage-2026-07-19-v8.json"
DEFINITION = ROOT / "sources" / "current-coverage-2026-07-19-v9.json"
PREVIOUS_BUNDLE = ROOT / "current_coverage_ledgers" / "2026-07-19-v8"
BUNDLE = ROOT / "current_coverage_ledgers" / "2026-07-19-v9"

DEFINITION_SHA256 = (
    "b4686cfe1721bca36775bcf05cc9e232b60e6850848cf2a047cb5e096486b365"
)
LEDGER_SHA256 = (
    "9c74baec74eab5b7a7f79eb6dc29d77f0071d99f0b3b67ff88fe3a337b0f32c9"
)
MANIFEST_SHA256 = (
    "b96e641ec861f1db20b312dd281fb9d6d5327236c8fef1389fd00f6144e419b9"
)
BUNDLE_INVENTORY_SHA256 = (
    "683a872088ef9c2de91d6060e825324378b923040115843184ef674e79e4bed7"
)
PREVIOUS_DEFINITION_SHA256 = (
    "6593bdf4453f178aabd1e164161b1866126c9f947d30c7938ac40c0a249448f9"
)
PREVIOUS_LEDGER_SHA256 = (
    "e6b756fab1b72367d24fdde712ea28417714c248f4712b8d70a263b8bf5fa49b"
)

REPLACEMENTS = {
    "construction-map-public-open-v12": "construction-map-public-open-v13",
    "construction-master-public-open-v12": "construction-master-public-open-v13",
    "coverage-audit-public-open-v11": "coverage-audit-public-open-v12",
    "federation-public-open-v10": "federation-public-open-v11",
    "seed-epoch-official-v30": "seed-epoch-official-v32",
}
CURRENT_FAMILIES = {
    "construction-map-public-open": "construction-map-public-open-v13",
    "construction-master-public-open": "construction-master-public-open-v13",
    "coverage-audit-public-open": "coverage-audit-public-open-v12",
    "federation-public-open": "federation-public-open-v11",
    "satellite-unknown-batch": "satellite-unknown-batch-030",
    "seed-epoch-official": "seed-epoch-official-v32",
}
ACCEPTED_PINS = {
    "sources/construction-master-2026-07-19-public-open-v13.json": (
        "6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07"
    ),
    "construction_master/2026-07-19-public-open-v13/manifest.json": (
        "d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0"
    ),
    "sources/construction-map-2026-07-19-public-open-v13.json": (
        "56e7edc827a30763e246bdde61724a024a7cd4482e42765f8ebf89ce15b23483"
    ),
    "construction_maps/2026-07-19-public-open-v13/manifest.json": (
        "0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49"
    ),
    "sources/federation-2026-07-19-public-open-v11.json": (
        "e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c"
    ),
    "federated_indexes/2026-07-19-public-open-v11/manifest.json": (
        "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
    ),
    "sources/coverage-audit-2026-07-19-public-open-v12.json": (
        "1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f"
    ),
    "audits/2026-07-19-public-open-coverage-v12/manifest.json": (
        "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77"
    ),
    "sources/open-seed-2026-07-19-v32.json": (
        "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
    ),
    "releases/2026-07-19-open-seed-v32/manifest.json": (
        "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
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
    artifact = next(
        artifact
        for artifact in ledger["artifacts"]
        if artifact["artifact_id"] == artifact_id
    )
    return artifact["reported_metrics"]


def _changed_metrics(previous: dict, current: dict) -> dict:
    return {
        label: (previous[label], current[label])
        for label in sorted(previous)
        if previous[label] != current[label]
    }


class FrozenCurrentCoverageLedgerV9Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline(self) -> None:
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(),
            DEFINITION_SHA256,
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
        self.assertEqual(first["ledger_id"], "current-coverage-2026-07-19-v9")
        self.assertEqual(len(first["input_checkpoints"]), 40)
        self.assertEqual(previous["ledger_id"], "current-coverage-2026-07-19-v8")
        self.assertEqual(
            hashlib.sha256(
                (PREVIOUS_BUNDLE / "current-coverage-ledger.json").read_bytes()
            ).hexdigest(),
            PREVIOUS_LEDGER_SHA256,
        )
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

    def test_exact_v8_successor_replaces_only_five_core_artifacts(self) -> None:
        previous = json.loads(PREVIOUS_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        previous_entries = {
            entry["artifact_id"]: entry for entry in previous["entries"]
        }
        current_entries = {
            entry["artifact_id"]: entry for entry in current["entries"]
        }
        self.assertEqual(len(previous_entries), 40)
        self.assertEqual(len(current_entries), 40)
        self.assertEqual(
            set(current_entries),
            (set(previous_entries) - set(REPLACEMENTS))
            | set(REPLACEMENTS.values()),
        )
        unchanged = set(previous_entries) - set(REPLACEMENTS)
        self.assertEqual(len(unchanged), 35)
        for artifact_id in unchanged:
            self.assertEqual(current_entries[artifact_id], previous_entries[artifact_id])
        self.assertEqual(current["scope"], previous["scope"])

        previous_ledger = build_current_coverage_ledger(PREVIOUS_DEFINITION).ledger
        current_ledger = build_current_coverage_ledger(DEFINITION).ledger
        previous_artifacts = {
            artifact["artifact_id"]: artifact
            for artifact in previous_ledger["artifacts"]
        }
        current_artifacts = {
            artifact["artifact_id"]: artifact
            for artifact in current_ledger["artifacts"]
        }
        for artifact_id in unchanged:
            self.assertEqual(
                current_artifacts[artifact_id], previous_artifacts[artifact_id]
            )

        expected_checkpoints = {
            "construction-map-public-open-v13": {
                "coverage": (
                    "construction_maps/2026-07-19-public-open-v13/coverage.json",
                    6_236,
                    "c1b08000f674ff29598041433f5c2d88e1785bcfc5d9dbde6c11e27b57d59e51",
                ),
                "definition": (
                    "sources/construction-map-2026-07-19-public-open-v13.json",
                    7_905,
                    "56e7edc827a30763e246bdde61724a024a7cd4482e42765f8ebf89ce15b23483",
                ),
                "manifest": (
                    "construction_maps/2026-07-19-public-open-v13/manifest.json",
                    1_967,
                    "0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49",
                ),
            },
            "construction-master-public-open-v13": {
                "coverage": (
                    "construction_master/2026-07-19-public-open-v13/coverage.json",
                    29_705,
                    "a55236fe69909486cc6457df186db43a5b86c24a85340658c28ab6a8f60607f8",
                ),
                "definition": (
                    "sources/construction-master-2026-07-19-public-open-v13.json",
                    15_027,
                    "6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07",
                ),
                "manifest": (
                    "construction_master/2026-07-19-public-open-v13/manifest.json",
                    47_668,
                    "d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0",
                ),
            },
            "coverage-audit-public-open-v12": {
                "manifest": (
                    "audits/2026-07-19-public-open-coverage-v12/manifest.json",
                    2_240,
                    "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77",
                ),
            },
            "federation-public-open-v11": {
                "index": (
                    "federated_indexes/2026-07-19-public-open-v11/federated-index.json",
                    18_227,
                    "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd",
                ),
                "manifest": (
                    "federated_indexes/2026-07-19-public-open-v11/manifest.json",
                    986,
                    "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4",
                ),
            },
            "seed-epoch-official-v32": {
                "manifest": (
                    "releases/2026-07-19-open-seed-v32/manifest.json",
                    5_245,
                    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c",
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

    def test_stack_metric_deltas_are_exact_and_nonadditive(self) -> None:
        previous = build_current_coverage_ledger(PREVIOUS_DEFINITION).ledger
        current = build_current_coverage_ledger(DEFINITION).ledger
        expected_changes = {
            (
                "construction-map-public-open-v12",
                "construction-map-public-open-v13",
            ): {
                "master_total_rows": (109_096, 109_107),
                "unmapped_rows": (123, 134),
            },
            (
                "construction-master-public-open-v12",
                "construction-master-public-open-v13",
            ): {
                "construction_arithmetic_rows": (304, 315),
                "status_under_construction_rows": (215, 226),
                "tier_a_rows": (304, 315),
                "total_master_rows": (109_096, 109_107),
            },
            (
                "coverage-audit-public-open-v11",
                "coverage-audit-public-open-v12",
            ): {
                "coverage_groups": (421, 441),
                "non_review_source_scoped_rows": (9_643, 9_665),
                "open_gaps": (2_308, 2_411),
                "source_scoped_rows": (15_773, 15_795),
            },
            (
                "federation-public-open-v10",
                "federation-public-open-v11",
            ): {
                "construction_pipeline_records": (6_434, 6_445),
                "non_review_construction_pipeline_records": (304, 315),
                "non_review_source_scoped_rows": (9_643, 9_665),
                "source_scoped_rows": (15_773, 15_795),
            },
            (
                "seed-epoch-official-v30",
                "seed-epoch-official-v32",
            ): {
                "construction_pipeline_records": (184, 195),
                "construction_source_signals": (153, 161),
                "evidence_records": (215, 226),
                "source_scoped_entity_rows": (348, 370),
            },
        }
        for (previous_id, current_id), expected in expected_changes.items():
            self.assertEqual(
                _changed_metrics(
                    _metrics(previous, previous_id), _metrics(current, current_id)
                ),
                expected,
            )

        counts = current["artifact_inventory_counts"]
        self.assertEqual(counts, previous["artifact_inventory_counts"])
        self.assertEqual(counts["artifacts"], 40)
        self.assertEqual(
            counts["by_access_tier"], {"local_restricted": 6, "public_open": 34}
        )
        self.assertEqual(counts["public_open_review_only_artifacts"], 21)
        self.assertFalse(current["scope"]["cross_artifact_counts_are_additive"])
        self.assertFalse(current["scope"]["benchmark_parity_claimed"])
        self.assertFalse(current["scope"]["global_completeness_claimed"])
        self.assertFalse(
            current["scope"]["source_scoped_rows_are_unique_physical_sites"]
        )
        self.assertIsNone(current["scope"]["unique_physical_site_count"])
        for artifact_id in REPLACEMENTS.values():
            metrics = _metrics(current, artifact_id)
            if "unique_physical_sites" in metrics:
                self.assertIsNone(metrics["unique_physical_sites"])
        self.assertEqual(
            _metrics(current, "seed-epoch-official-v32"),
            {
                "capacity_observations": 401,
                "construction_pipeline_records": 195,
                "construction_source_signals": 161,
                "evidence_records": 226,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 370,
            },
        )

    def test_predecessor_and_unaccepted_satellite_families_are_excluded(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        artifact_ids = [entry["artifact_id"] for entry in definition["entries"]]
        for prefix, expected_id in CURRENT_FAMILIES.items():
            self.assertEqual(
                [artifact_id for artifact_id in artifact_ids if artifact_id.startswith(prefix)],
                [expected_id],
            )
        self.assertFalse(set(REPLACEMENTS) & set(artifact_ids))
        combined = (
            DEFINITION.read_text()
            + (BUNDLE / "current-coverage-ledger.json").read_text()
            + (BUNDLE / "manifest.json").read_text()
        ).lower()
        for prohibited in (
            "recovery",
            "unknown-031",
            "unknown-032",
            "unknown-033",
            "satellite-recover",
            "satellite_recover",
        ):
            self.assertNotIn(prohibited, combined)

    def test_v9_contract_fails_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        changes: list[tuple[dict, str]] = []

        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-19T22:55:01Z"
        changes.append((changed, "v9 generation timestamp changed"))

        changed = deepcopy(document)
        changed["entries"][0]["artifact_id"] = "changed-artifact"
        changes.append((changed, "v9 must contain exactly 40 current artifacts"))

        changed = deepcopy(document)
        master = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "construction-master-public-open-v13"
        )
        master["checkpoints"][0]["sha256"] = "0" * 64
        changes.append(
            (
                changed,
                "v9 construction-master-public-open-v13 current checkpoint contract changed",
            )
        )

        changed = deepcopy(document)
        seed = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "seed-epoch-official-v32"
        )
        seed["checkpoints"][0]["sha256"] = "0" * 64
        changes.append(
            (
                changed,
                "v9 seed-epoch-official-v32 current checkpoint contract changed",
            )
        )

        changed = deepcopy(document)
        gap = next(
            gap
            for gap in changed["parity_gaps"]
            if "federation-public-open-v11" in gap["affected_artifact_ids"]
        )
        gap["affected_artifact_ids"] = [
            "federation-public-open-v10"
            if artifact_id == "federation-public-open-v11"
            else artifact_id
            for artifact_id in gap["affected_artifact_ids"]
        ]
        changes.append((changed, "v9 parity gaps contain stale current artifacts"))

        changed = deepcopy(document)
        cleanview = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "cleanview-rights-assessment-v1"
        )
        cleanview["checkpoints"][0]["path"] = "satellite_recovery/unaccepted.json"
        changes.append((changed, "v9 includes an explicitly excluded source lane"))

        for index, (changed, message) in enumerate(changes):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=DEFINITION.parent,
                prefix=f"changed-v9-{index}-",
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
