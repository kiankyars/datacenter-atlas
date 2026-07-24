from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

import datacenter_atlas.current_coverage as current_coverage_module
from datacenter_atlas.current_coverage import (
    CurrentCoverageError,
    build_current_coverage_ledger,
    validate_current_coverage_ledger,
)


ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v10.json"
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v12.json"
ACCEPTED_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v10"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v12"

DEFINITION_SHA256 = (
    "f1f365a517179b2526911665161c76ff59865b6e4fd14fcddf3361f490a3a72a"
)
LEDGER_SHA256 = (
    "ec93020a2794221961639b935003732568c10a5b4158143e7258a1d835d6a988"
)
MANIFEST_SHA256 = (
    "a7b5e3522c90301020db2d47fa6e1f10830f82524be559967df9aa18896ff412"
)
SIDECAR_FILE_SHA256 = (
    "5817b471338cc2005f2bbad98282c046a8dfeadc0d98c6bdabe55f774d59c6a5"
)
BUNDLE_INVENTORY_SHA256 = (
    "c1115a81cf69a5e268a160d5cdb3e34c3be024f1da23a2d781fe99cb25923215"
)
ACCEPTED_DEFINITION_SHA256 = (
    "bb86166ba643fd89f30c0cf4bf80d76f85e2f05823dfdfc213041b0bccc9cb93"
)
ACCEPTED_LEDGER_SHA256 = (
    "829f64bc8cca100386da7f8a303049fb8021c60ecfdb6c4d31947a96e155383b"
)
ACCEPTED_MANIFEST_SHA256 = (
    "e033075cc5539b71761055e4a4b43ebb47e3d4032099342853195e78214791aa"
)
ACCEPTED_SIDECAR_FILE_SHA256 = (
    "857b78abeddee46a70cf8b8ab37064a3f1a0185bb40a6b4c1663283f23d901ef"
)

REPLACEMENTS = {
    "coverage-audit-public-open-v13": "coverage-audit-public-open-v17",
    "federation-public-open-v12": "federation-public-open-v18",
    "seed-epoch-official-v33": "seed-epoch-official-v42",
}
RECOVERY_ID = "satellite-recovery-unknown033-review-v1"
CURRENT_FAMILIES = {
    "construction-map-public-open": "construction-map-public-open-v14",
    "construction-master-public-open": "construction-master-public-open-v14",
    "coverage-audit-public-open": "coverage-audit-public-open-v17",
    "federation-public-open": "federation-public-open-v18",
    "satellite-recovery": RECOVERY_ID,
    "satellite-unknown-batch": "satellite-unknown-batch-030",
    "seed-epoch-official": "seed-epoch-official-v42",
}
ACCEPTED_PINS = {
    "sources/open-seed-2026-07-20-v42.json": (
        "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f"
    ),
    "releases/2026-07-20-open-seed-v42/manifest.json": (
        "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680"
    ),
    "sources/federation-2026-07-20-public-open-v18.json": (
        "bab7ae5e2f09e34d658663112c70b88ac3ca3b02a075380356cfe3f7af7298d0"
    ),
    "federated_indexes/2026-07-20-public-open-v18/federated-index.json": (
        "45048828bf4cc90e1c70fd0da86962c5a0bc0a00d588ad8c3f22e35e2597f6df"
    ),
    "federated_indexes/2026-07-20-public-open-v18/manifest.json": (
        "3f52b09facdaa5bbea82bbef045e459901a6f3206452271482d0ea798a7f28d6"
    ),
    "sources/coverage-audit-2026-07-20-public-open-v17.json": (
        "964926e8432b4bf83233201c07cad0c40dc2fc34d9d4b1f89cd871f51c461f3d"
    ),
    "audits/2026-07-20-public-open-coverage-v17/manifest.json": (
        "37807873e8dc0009d31b1a1eb8d4d6cc4dd2dceb88a1ab52076c166e37f04755"
    ),
    "audits/2026-07-20-public-open-coverage-v17/coverage-audit.json": (
        "925abb9218e11a31a423348cb3ba29b722e98aa844d23f04e68569251faa9cf7"
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

REJECTED_PATH_FRAGMENTS = (
    "sources/open-seed-2026-07-20-v41.json",
    "releases/2026-07-20-open-seed-v41",
    "sources/federation-2026-07-20-public-open-v17.json",
    "federated_indexes/2026-07-20-public-open-v17",
    "sources/coverage-audit-2026-07-20-public-open-v16.json",
    "audits/2026-07-20-public-open-coverage-v16",
    "sources/current-coverage-2026-07-20-v11.json",
    "current_coverage_ledgers/2026-07-20-v11",
)
REJECTED_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        "seed-epoch-official-v41",
        "epoch-official-open-seed-v41",
        "2026-07-20-open-seed-v41",
        "coverage-audit-public-open-v16",
        "coverage-audit-2026-07-20-public-open-v16",
        "2026-07-20-public-open-coverage-v16",
        "federation-public-open-v17",
        "federation-2026-07-20-public-open-v17",
        "federated_indexes/2026-07-20-public-open-v17",
        "967127f07f0e30be989bfbeba2ab7884a20b4ff570357648af8c48652e67c1b5",
        "e346df3f432ddb4a53fbfe9b4d172d2231a73b631e6b18106b74b49d977a2428",
        "19589fb2a579046fac956fe1bda68c6469678d6e81f506459d73266794644780",
        "bb0600d6997f4874a64b5f7ff8bebaa8a77dfd448fab17b51a7bdfab57874071",
        "dff68953b205cc2cc27553bddf50a8b3e7bc11ed02e7af028c98500df0d94ae9",
        "eb3b29f6bef972afab1b21672250c31e16e75dd484f89c940ec96a8cb2255f6e",
        "ce1cd31367afc196690bb8139f2d9dcb1a55c30abb4c4ba7105a021b38a99fda",
        "a60aa409e8e56b65f672874d7a162a1a6844bb90ea2867a4fb76afd5686bc09b",
        "ef333e31eff93167cbef2d446a3f34fd6fcdf4ff34828b0e71d91c9cb160e0a4",
        "0ff690d8b54c158597ee0c58aa22197f125124ecd40b239146158e37ca6530f4",
        "11917fc370dd1f0c981f868dc626a2c481538c9ba490bcb6d2c78075e2ad2cf4",
        "857b4915bb1d796a4452759503e9760bcb8125fd4b1667a2a9fccad3ee9e654a",
    )
)


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


@contextmanager
def _offline_rejected_path_guard():
    original_regular_bytes = current_coverage_module._regular_bytes
    paths_read: list[Path] = []

    def guarded_read(path: Path, label: str) -> bytes:
        normalized = path.resolve().as_posix().lower()
        for fragment in REJECTED_PATH_FRAGMENTS:
            if fragment in normalized:
                raise AssertionError(f"v12 attempted rejected path access: {path}")
        paths_read.append(path)
        return original_regular_bytes(path, label)

    with patch.object(
        current_coverage_module,
        "_regular_bytes",
        side_effect=guarded_read,
    ), patch.object(
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
    ), patch.object(
        socket,
        "gethostbyname",
        side_effect=AssertionError("ledger validation attempted DNS resolution"),
    ), patch.object(
        socket,
        "gethostbyname_ex",
        side_effect=AssertionError("ledger validation attempted DNS resolution"),
    ):
        yield paths_read


class FrozenCurrentCoverageLedgerV12Tests(unittest.TestCase):
    def _assert_definition_rejected(
        self,
        document: dict,
        message: str,
        *,
        prefix: str,
    ) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DEFINITION.parent,
            prefix=prefix,
            suffix=".json",
        ) as temporary:
            temporary.write(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            )
            temporary.flush()
            with self.assertRaisesRegex(CurrentCoverageError, message):
                build_current_coverage_ledger(temporary.name)

    def test_frozen_bundle_reproduces_twice_offline_from_accepted_v10(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 122_646)
        self.assertEqual(
            hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), DEFINITION_SHA256
        )
        self.assertEqual(
            hashlib.sha256(ACCEPTED_DEFINITION.read_bytes()).hexdigest(),
            ACCEPTED_DEFINITION_SHA256,
        )
        for relative_path, expected_sha256 in ACCEPTED_PINS.items():
            self.assertEqual(
                hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                expected_sha256,
            )

        with _offline_rejected_path_guard() as paths_read:
            first_build = build_current_coverage_ledger(DEFINITION)
            second_build = build_current_coverage_ledger(DEFINITION)
            first = validate_current_coverage_ledger(
                BUNDLE,
                definition_path=DEFINITION,
            )
            second = validate_current_coverage_ledger(
                BUNDLE,
                definition_path=DEFINITION,
            )
            accepted_build = build_current_coverage_ledger(ACCEPTED_DEFINITION)
            accepted = validate_current_coverage_ledger(
                ACCEPTED_BUNDLE,
                definition_path=ACCEPTED_DEFINITION,
            )

        self.assertTrue(paths_read)
        self.assertEqual(first_build.ledger_bytes, second_build.ledger_bytes)
        self.assertEqual(first_build.manifest_bytes, second_build.manifest_bytes)
        self.assertEqual(
            first_build.manifest_hash_bytes,
            second_build.manifest_hash_bytes,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["ledger_id"], "current-coverage-2026-07-20-v12")
        self.assertEqual(len(first["input_checkpoints"]), 41)
        self.assertEqual(accepted["ledger_id"], "current-coverage-2026-07-20-v10")

        frozen_ledger = BUNDLE / "current-coverage-ledger.json"
        frozen_manifest = BUNDLE / "manifest.json"
        frozen_sidecar = BUNDLE / "manifest.sha256"
        self.assertEqual(first_build.ledger_bytes, frozen_ledger.read_bytes())
        self.assertEqual(first_build.manifest_bytes, frozen_manifest.read_bytes())
        self.assertEqual(first_build.manifest_hash_bytes, frozen_sidecar.read_bytes())
        self.assertEqual(frozen_ledger.stat().st_size, 82_572)
        self.assertEqual(frozen_manifest.stat().st_size, 22_045)
        self.assertEqual(frozen_sidecar.stat().st_size, 80)
        self.assertEqual(
            hashlib.sha256(frozen_ledger.read_bytes()).hexdigest(),
            LEDGER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(frozen_manifest.read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(frozen_sidecar.read_bytes()).hexdigest(),
            SIDECAR_FILE_SHA256,
        )
        self.assertEqual(
            frozen_sidecar.read_bytes(),
            f"{MANIFEST_SHA256}  manifest.json\n".encode("ascii"),
        )
        self.assertEqual(_bundle_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)

        self.assertEqual(
            hashlib.sha256(accepted_build.ledger_bytes).hexdigest(),
            ACCEPTED_LEDGER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(accepted_build.manifest_bytes).hexdigest(),
            ACCEPTED_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(accepted_build.manifest_hash_bytes).hexdigest(),
            ACCEPTED_SIDECAR_FILE_SHA256,
        )
        self.assertEqual(
            accepted_build.ledger_bytes,
            (ACCEPTED_BUNDLE / "current-coverage-ledger.json").read_bytes(),
        )
        self.assertEqual(
            accepted_build.manifest_bytes,
            (ACCEPTED_BUNDLE / "manifest.json").read_bytes(),
        )
        self.assertEqual(
            accepted_build.manifest_hash_bytes,
            (ACCEPTED_BUNDLE / "manifest.sha256").read_bytes(),
        )

        entries = sorted(BUNDLE.iterdir(), key=lambda path: path.name)
        self.assertEqual(
            [entry.name for entry in entries],
            ["current-coverage-ledger.json", "manifest.json", "manifest.sha256"],
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                entry.is_file()
                and not entry.is_symlink()
                and stat.S_IMODE(entry.stat().st_mode) == 0o444
                for entry in entries
            )
        )

    def test_exact_v10_successor_replaces_only_three_current_entries(self) -> None:
        accepted = json.loads(ACCEPTED_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        accepted_entries = {
            entry["artifact_id"]: entry for entry in accepted["entries"]
        }
        current_entries = {
            entry["artifact_id"]: entry for entry in current["entries"]
        }

        self.assertEqual(
            current_coverage_module._V12_ARTIFACT_REPLACEMENTS,
            REPLACEMENTS,
        )
        self.assertEqual(
            current_coverage_module._V12_RECOVERY_ARTIFACT_ID,
            current_coverage_module._V10_RECOVERY_ARTIFACT_ID,
        )
        self.assertEqual(
            current_coverage_module._V12_ARTIFACT_IDS,
            tuple(
                sorted(
                    REPLACEMENTS.get(artifact_id, artifact_id)
                    for artifact_id in current_coverage_module._V10_ARTIFACT_IDS
                )
            ),
        )
        unchanged_checkpoint_ids = (
            set(current_coverage_module._V10_EXACT_CURRENT_CHECKPOINTS)
            - set(REPLACEMENTS)
        )
        for artifact_id in unchanged_checkpoint_ids:
            self.assertEqual(
                current_coverage_module._V12_EXACT_CURRENT_CHECKPOINTS[artifact_id],
                current_coverage_module._V10_EXACT_CURRENT_CHECKPOINTS[artifact_id],
            )
        self.assertIs(
            current_coverage_module._V12_EXACT_METRICS[RECOVERY_ID],
            current_coverage_module._V10_EXACT_RECOVERY_METRICS,
        )
        self.assertIs(
            current_coverage_module._V12_PARITY_GAP_IDS,
            current_coverage_module._V10_PARITY_GAP_IDS,
        )
        self.assertIs(
            current_coverage_module._V12_PUBLICATION_MODE_COUNTS,
            current_coverage_module._V10_PUBLICATION_MODE_COUNTS,
        )

        self.assertEqual(len(accepted_entries), 41)
        self.assertEqual(len(current_entries), 41)
        self.assertEqual(
            set(current_entries),
            (set(accepted_entries) - set(REPLACEMENTS))
            | set(REPLACEMENTS.values()),
        )
        unchanged = set(accepted_entries) - set(REPLACEMENTS)
        self.assertEqual(len(unchanged), 38)
        for artifact_id in unchanged:
            self.assertEqual(current_entries[artifact_id], accepted_entries[artifact_id])
        self.assertEqual(current["scope"], accepted["scope"])
        self.assertEqual(current["generated_at"], "2026-07-20T05:45:00Z")

        expected_gaps = deepcopy(accepted["parity_gaps"])
        for gap in expected_gaps:
            gap["affected_artifact_ids"] = [
                REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in gap["affected_artifact_ids"]
            ]
        self.assertEqual(current["parity_gaps"], expected_gaps)

        artifact_ids = [entry["artifact_id"] for entry in current["entries"]]
        self.assertEqual(artifact_ids, sorted(artifact_ids))
        for prefix, expected_id in CURRENT_FAMILIES.items():
            self.assertEqual(
                [
                    artifact_id
                    for artifact_id in artifact_ids
                    if artifact_id.startswith(prefix)
                ],
                [expected_id],
            )

        recovery = current_entries[RECOVERY_ID]
        self.assertEqual(recovery, accepted_entries[RECOVERY_ID])
        self.assertEqual(recovery["artifact_kind"], "satellite_catalog_batch")
        self.assertEqual(recovery["current_role"], "public_supporting_review_lane")
        self.assertEqual(recovery["evidence_scope"], "review_only")
        self.assertEqual(recovery["publication_mode"], "public_review_or_discovery")
        self.assertEqual(recovery["record_units"], ["catalog_job"])
        recovery_gaps = {
            gap["gap_id"]
            for gap in current["parity_gaps"]
            if RECOVERY_ID in gap["affected_artifact_ids"]
        }
        self.assertEqual(
            recovery_gaps,
            {"global-construction-coverage-partial", "satellite-review-backlog"},
        )
        for gap in current["parity_gaps"]:
            self.assertTrue(set(gap["affected_artifact_ids"]).isdisjoint(REPLACEMENTS))

    def test_exact_v10_to_v12_metric_deltas_and_nonadditivity(self) -> None:
        accepted = build_current_coverage_ledger(ACCEPTED_DEFINITION).ledger
        current = build_current_coverage_ledger(DEFINITION).ledger
        expected_changes = {
            ("coverage-audit-public-open-v13", "coverage-audit-public-open-v17"): {
                "coverage_groups": (449, 526),
                "non_review_source_scoped_rows": (9_673, 9_797),
                "open_gaps": (2_446, 2_845),
                "source_scoped_rows": (15_803, 15_927),
            },
            ("federation-public-open-v12", "federation-public-open-v18"): {
                "capacity_observations": (1_189, 1_213),
                "construction_pipeline_records": (6_449, 6_512),
                "non_review_construction_pipeline_records": (319, 382),
                "non_review_source_scoped_rows": (9_673, 9_797),
                "source_scoped_rows": (15_803, 15_927),
            },
            ("seed-epoch-official-v33", "seed-epoch-official-v42"): {
                "capacity_observations": (403, 427),
                "construction_pipeline_records": (199, 262),
                "construction_source_signals": (165, 187),
                "evidence_records": (230, 273),
                "source_scoped_entity_rows": (378, 502),
            },
        }
        for (accepted_id, current_id), expected in expected_changes.items():
            self.assertEqual(
                _changed_metrics(
                    _metrics(accepted, accepted_id),
                    _metrics(current, current_id),
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
        federation = _metrics(current, "federation-public-open-v18")
        self.assertEqual(federation["review_only_source_scoped_rows"], 6_130)
        self.assertEqual(
            federation["review_only_construction_pipeline_records"],
            6_130,
        )
        self.assertIsNone(federation["unique_physical_sites"])
        self.assertEqual(
            _metrics(current, "seed-epoch-official-v42")["resolution_candidates"],
            4,
        )

        counts = current["artifact_inventory_counts"]
        self.assertEqual(counts["artifacts"], 41)
        self.assertEqual(
            counts["by_access_tier"],
            {"local_restricted": 6, "public_open": 35},
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
        self.assertEqual(
            counts["by_redistribution_status"],
            {
                "eligible_with_upstream_terms": 30,
                "metadata_only_no_source_rows": 5,
                "quarantined_pending_rights": 6,
            },
        )
        self.assertFalse(current["scope"]["cross_artifact_counts_are_additive"])
        self.assertFalse(current["scope"]["global_completeness_claimed"])
        self.assertFalse(current["scope"]["benchmark_parity_claimed"])
        self.assertIsNone(current["scope"]["unique_physical_site_count"])

    def test_accepted_child_pins_v4_marker_and_audit_lineage_are_exact(self) -> None:
        seed_manifest = json.loads(
            (ROOT / "releases/2026-07-20-open-seed-v42/manifest.json").read_text()
        )
        federation_index = json.loads(
            (
                ROOT
                / "federated_indexes/2026-07-20-public-open-v18/federated-index.json"
            ).read_text()
        )
        federation_manifest = json.loads(
            (
                ROOT / "federated_indexes/2026-07-20-public-open-v18/manifest.json"
            ).read_text()
        )
        coverage_manifest = json.loads(
            (
                ROOT / "audits/2026-07-20-public-open-coverage-v17/manifest.json"
            ).read_text()
        )
        coverage_audit = json.loads(
            (
                ROOT
                / "audits/2026-07-20-public-open-coverage-v17/coverage-audit.json"
            ).read_text()
        )

        marker = seed_manifest["publication_contract_version"]
        self.assertIs(type(marker), int)
        self.assertEqual(marker, 4)
        descriptors = {
            release["release_id"]: release for release in federation_index["releases"]
        }
        federation_marker = descriptors["epoch-official-open-seed-v42"]["manifest"][
            "publication_contract_version"
        ]
        self.assertIs(type(federation_marker), int)
        self.assertEqual(federation_marker, 4)
        self.assertNotIn(
            "publication_contract_version",
            descriptors["global-open-v3"]["manifest"],
        )
        self.assertNotIn(
            "publication_contract_version",
            descriptors["osm-fuzzy-review-v2"]["manifest"],
        )

        federation_definition = federation_manifest["definition"]
        federation_definition_path = (
            ROOT / "sources/federation-2026-07-20-public-open-v18.json"
        )
        self.assertEqual(federation_manifest["generated_at"], "2026-07-20T05:00:00Z")
        self.assertEqual(
            federation_definition["bytes"],
            federation_definition_path.stat().st_size,
        )
        self.assertEqual(
            federation_definition["sha256"],
            ACCEPTED_PINS["sources/federation-2026-07-20-public-open-v18.json"],
        )

        coverage_definition = coverage_manifest["definition"]
        coverage_definition_path = (
            ROOT / "sources/coverage-audit-2026-07-20-public-open-v17.json"
        )
        self.assertEqual(coverage_manifest["generated_at"], "2026-07-20T05:30:00Z")
        self.assertEqual(coverage_definition["bytes"], coverage_definition_path.stat().st_size)
        self.assertEqual(
            coverage_definition["sha256"],
            ACCEPTED_PINS["sources/coverage-audit-2026-07-20-public-open-v17.json"],
        )
        self.assertEqual(
            coverage_manifest["inputs"]["child_manifest_sha256"][
                "epoch-official-open-seed-v42"
            ],
            ACCEPTED_PINS["releases/2026-07-20-open-seed-v42/manifest.json"],
        )
        self.assertEqual(
            coverage_manifest["inputs"]["federated_manifest_sha256"],
            ACCEPTED_PINS[
                "federated_indexes/2026-07-20-public-open-v18/manifest.json"
            ],
        )
        self.assertEqual(
            coverage_manifest["artifacts"]["coverage-audit.json"]["sha256"],
            ACCEPTED_PINS[
                "audits/2026-07-20-public-open-coverage-v17/coverage-audit.json"
            ],
        )

        audit_descriptors = {
            child["release_id"]: child for child in coverage_audit["inputs"]["children"]
        }
        audit_marker = audit_descriptors["epoch-official-open-seed-v42"]["manifest"][
            "publication_contract_version"
        ]
        self.assertIs(type(audit_marker), int)
        self.assertEqual(audit_marker, 4)
        self.assertNotIn(
            "publication_contract_version",
            audit_descriptors["global-open-v3"]["manifest"],
        )
        self.assertNotIn(
            "publication_contract_version",
            audit_descriptors["osm-fuzzy-review-v2"]["manifest"],
        )
        audit_federation = coverage_audit["inputs"]["federated_index"]
        self.assertEqual(
            audit_federation["index"]["sha256"],
            ACCEPTED_PINS[
                "federated_indexes/2026-07-20-public-open-v18/federated-index.json"
            ],
        )
        self.assertEqual(
            audit_federation["manifest"]["sha256"],
            ACCEPTED_PINS[
                "federated_indexes/2026-07-20-public-open-v18/manifest.json"
            ],
        )

    def test_candidate_and_accepted_lineage_contain_no_rejected_graph_markers(self) -> None:
        paths = [
            DEFINITION,
            *(BUNDLE / name for name in current_coverage_module.BUNDLE_FILES),
            *(ROOT / relative_path for relative_path in ACCEPTED_PINS),
        ]
        for path in paths:
            raw = path.read_bytes()
            for marker in REJECTED_MARKERS:
                with self.subTest(path=path.relative_to(ROOT), marker=marker):
                    self.assertNotIn(marker, raw)

    def test_publication_markers_reject_non_builtin_integer_four(self) -> None:
        original_regular_bytes = current_coverage_module._regular_bytes

        def mutated_reader(label: str, replacement: object):
            def read(path: Path, actual_label: str) -> bytes:
                raw = original_regular_bytes(path, actual_label)
                if actual_label != label:
                    return raw
                document = json.loads(raw)
                if label == "v12 seed manifest":
                    document["publication_contract_version"] = replacement
                else:
                    descriptor = next(
                        release
                        for release in document["releases"]
                        if release["release_id"] == "epoch-official-open-seed-v42"
                    )
                    descriptor["manifest"]["publication_contract_version"] = replacement
                return (
                    json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8")

            return read

        cases = (
            ("v12 seed manifest", 4.0),
            ("v12 federation index", True),
        )
        for label, replacement in cases:
            with self.subTest(label=label, replacement=replacement), patch.object(
                current_coverage_module,
                "_regular_bytes",
                side_effect=mutated_reader(label, replacement),
            ):
                with self.assertRaisesRegex(
                    CurrentCoverageError,
                    "publication contract marker propagation changed",
                ):
                    build_current_coverage_ledger(DEFINITION)

        original_json_object = current_coverage_module._json_object

        def mutated_coverage_document(raw: bytes, label: str) -> dict:
            document = original_json_object(raw, label)
            if label == "v12 coverage audit":
                descriptor = next(
                    child
                    for child in document["inputs"]["children"]
                    if child["release_id"] == "epoch-official-open-seed-v42"
                )
                descriptor["manifest"]["publication_contract_version"] = "4"
            return document

        with patch.object(
            current_coverage_module,
            "_json_object",
            side_effect=mutated_coverage_document,
        ):
            with self.assertRaisesRegex(
                CurrentCoverageError,
                "coverage publication contract marker propagation changed",
            ):
                build_current_coverage_ledger(DEFINITION)

    def test_canonical_timestamp_and_definition_mutations_fail_closed(self) -> None:
        document = json.loads(DEFINITION.read_text())
        cases: list[tuple[dict, str, str]] = []

        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-20T06:45:00+01:00"
        cases.append((changed, "canonical UTC with whole seconds", "offset"))

        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-20T05:45:00.5Z"
        cases.append((changed, "canonical UTC with whole seconds", "fraction"))

        changed = deepcopy(document)
        changed["generated_at"] = "2026-07-20T05:45:01Z"
        cases.append((changed, "generation timestamp changed", "timestamp"))

        changed = deepcopy(document)
        recovery = next(
            entry for entry in changed["entries"] if entry["artifact_id"] == RECOVERY_ID
        )
        recovery["evidence_scope"] = "source_scoped"
        cases.append((changed, "recovery review-only guardrails changed", "recovery"))

        changed = deepcopy(document)
        recovery = next(
            entry for entry in changed["entries"] if entry["artifact_id"] == RECOVERY_ID
        )
        metric = next(
            metric
            for metric in recovery["metrics"]
            if metric["label"] == "source_batch_promoted"
        )
        metric["value"] = True
        cases.append((changed, "accepted metric contract changed", "metric"))

        changed = deepcopy(document)
        for gap in changed["parity_gaps"]:
            if gap["gap_id"] == "satellite-review-backlog":
                gap["affected_artifact_ids"].remove(RECOVERY_ID)
        cases.append((changed, "recovery parity-gap scope changed", "gap"))

        changed = deepcopy(document)
        audit = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "coverage-audit-public-open-v17"
        )
        audit["checkpoints"][0]["sha256"] = "0" * 64
        cases.append((changed, "current checkpoint contract changed", "checkpoint"))

        changed = deepcopy(document)
        unchanged_entry = next(
            entry
            for entry in changed["entries"]
            if entry["artifact_id"] == "candidate-fusion-osm-planet-priority-v13"
        )
        unchanged_entry["limitations"][0] += " Drift."
        cases.append((changed, "definition content changed", "content"))

        for changed, message, prefix in cases:
            with self.subTest(prefix=prefix):
                self._assert_definition_rejected(
                    changed,
                    message,
                    prefix=f"changed-v12-{prefix}-",
                )

    def test_child_definition_drift_and_unfrozen_bundle_fail_closed(self) -> None:
        original_regular_bytes = current_coverage_module._regular_bytes

        def changed_child_definition(path: Path, label: str) -> bytes:
            raw = original_regular_bytes(path, label)
            if label == "v12 seed definition":
                return raw + b"\n"
            return raw

        with patch.object(
            current_coverage_module,
            "_regular_bytes",
            side_effect=changed_child_definition,
        ):
            with self.assertRaisesRegex(
                CurrentCoverageError,
                "seed definition checkpoint changed",
            ):
                build_current_coverage_ledger(DEFINITION)

        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "v12"
            shutil.copytree(BUNDLE, copied)
            copied.chmod(0o755)
            for entry in copied.iterdir():
                entry.chmod(0o644)
            with self.assertRaisesRegex(CurrentCoverageError, "must be frozen"):
                validate_current_coverage_ledger(
                    copied,
                    definition_path=DEFINITION,
                )


if __name__ == "__main__":
    unittest.main()
