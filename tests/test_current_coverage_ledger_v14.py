from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.current_coverage_v14 import (
    ADDED_SATELLITE_IDS,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    CurrentCoverageV14Error,
    NEW_ARTIFACT_IDS,
    V13_BASE_LINEAGE,
    V14_DEFINITION_SHA256,
    V14_LEDGER_ID,
    build_current_coverage_ledger_v14,
    make_v14_definition,
    validate_current_coverage_ledger_v14,
    write_current_coverage_ledger_v14,
    write_v14_definition,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v14.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v13.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v14"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v13"

DEFINITION_SHA256 = "907942b43861845703900dfb57e518ed56611bb932b2ec0f16f1ab656b0beab0"
LEDGER_SHA256 = "ede89a5b75ca30dae4c96f3ae876e02abf53eff00497a8edc85fc9fcde69b2bd"
MANIFEST_SHA256 = "5f318e610653a4579fb9d995133fd3ea388de5c7a2a3b66c2e250fced69d150c"
SIDECAR_SHA256 = "a9ad99f6a82b749ec69ef9f38a1b2f1c010848b0e7db33b878c232b64d4ce536"
UNCHANGED_36_SHA256 = "8c8f2cbbdebe0ee7259c451873ea5e299addf388f7a090fc9d74c72b05619ecb"
NEW_8_SHA256 = "af8ae4eef673c54c1f5ee11e010eb06e8536857618cf8d72164d9de0a1d6d917"
PARITY_GAPS_SHA256 = "d7fbe5e6039fcbb053b935bdfbabafc89f296763f4c8b4bc29ae3a2a21fff400"
EXPECTED_SIZES = {
    DEFINITION: 129_254,
    BUNDLE / "current-coverage-ledger.json": 89_210,
    BUNDLE / "manifest.json": 24_814,
    BUNDLE / "manifest.sha256": 80,
}
BASE_HASHES = {
    BASE_DEFINITION: "7e23abc7be3c6a3e898c640960912a308297bf02aee22b86638a66b350d19cc5",
    BASE_BUNDLE / "current-coverage-ledger.json": (
        "aabbc77b6fad657794b44e8eda6c833bccc694d863602ab8c7efaf79da49e0b7"
    ),
    BASE_BUNDLE / "manifest.json": (
        "3ab86c29de2d7a6054a0ec3c941644a639ef89cba7fdf27614ff9ea170f9f034"
    ),
    BASE_BUNDLE / "manifest.sha256": (
        "92cb408e7346fdbcae3a5dd3e70539b88dfcdfde987b255a34b0f0972d23b7f1"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _entry_map(document: dict) -> dict[str, dict]:
    return {entry["artifact_id"]: entry for entry in document["entries"]}


def _implementation_module():
    return importlib.import_module(build_current_coverage_ledger_v14.__module__)


@contextmanager
def _offline_guard():
    with patch.object(
        socket,
        "socket",
        side_effect=AssertionError("v14 attempted network access"),
    ), patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("v14 attempted network access"),
    ), patch.object(
        socket,
        "getaddrinfo",
        side_effect=AssertionError("v14 attempted DNS resolution"),
    ), patch.object(
        socket,
        "gethostbyname",
        side_effect=AssertionError("v14 attempted DNS resolution"),
    ):
        yield


class FrozenCurrentCoverageLedgerV14Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline(self) -> None:
        self.assertEqual(V14_DEFINITION_SHA256, DEFINITION_SHA256)
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(_sha256(BUNDLE / "current-coverage-ledger.json"), LEDGER_SHA256)
        self.assertEqual(_sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_sha256(BUNDLE / "manifest.sha256"), SIDECAR_SHA256)
        for path, expected_size in EXPECTED_SIZES.items():
            self.assertEqual(path.stat().st_size, expected_size)

        with _offline_guard():
            first = build_current_coverage_ledger_v14(DEFINITION)
            second = build_current_coverage_ledger_v14(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v14(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v14(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V14_LEDGER_ID)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 44)
        self.assertEqual(first_manifest["base_ledger"], V13_BASE_LINEAGE)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_five_replacements_three_review_additions(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        base_entries = _entry_map(base)
        entries = _entry_map(current)
        self.assertEqual(set(base_entries) - set(entries), set(ARTIFACT_REPLACEMENTS))
        self.assertEqual(set(entries) - set(base_entries), NEW_ARTIFACT_IDS)
        self.assertEqual(len(entries), 44)
        self.assertNotIn("seed-epoch-official-v45", entries)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        self.assertEqual(len(unchanged_ids), 36)
        unchanged_digest = hashlib.sha256()
        for artifact_id in unchanged_ids:
            self.assertEqual(entries[artifact_id], base_entries[artifact_id])
            unchanged_digest.update(_canonical_line(entries[artifact_id]))
        self.assertEqual(unchanged_digest.hexdigest(), UNCHANGED_36_SHA256)

        new_digest = hashlib.sha256()
        for artifact_id in sorted(NEW_ARTIFACT_IDS):
            new_digest.update(_canonical_line(entries[artifact_id]))
        self.assertEqual(new_digest.hexdigest(), NEW_8_SHA256)
        self.assertEqual(
            hashlib.sha256(_canonical_line(current["parity_gaps"])).hexdigest(),
            PARITY_GAPS_SHA256,
        )
        gaps = {gap["gap_id"]: gap for gap in current["parity_gaps"]}
        for gap_id in (
            "global-construction-coverage-partial",
            "satellite-review-backlog",
        ):
            self.assertTrue(
                ADDED_SATELLITE_IDS.issubset(
                    gaps[gap_id]["affected_artifact_ids"]
                )
            )

    def test_satellite_additions_are_nonadditive_review_only_lineage(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        entries = _entry_map(definition)
        for artifact_id in ADDED_SATELLITE_IDS:
            entry = entries[artifact_id]
            self.assertEqual(entry["current_role"], "public_supporting_review_lane")
            self.assertEqual(entry["evidence_scope"], "review_only")
            self.assertEqual(entry["publication_mode"], "public_review_or_discovery")
            limitations = " ".join(entry["limitations"]).lower()
            self.assertTrue("not additive" in limitations or "non-additive" in limitations)

        reselection = entries[
            "satellite-catalog-reselection-open-seed-v43-active-v2-001"
        ]
        checkpoint_ids = {row["checkpoint_id"] for row in reselection["checkpoints"]}
        self.assertEqual(
            checkpoint_ids,
            {
                "grid_headers",
                "manifest",
                "queue_manifest",
                "source_catalog_manifest",
                "unresolved",
            },
        )
        metrics = {row["label"]: row["value"] for row in reselection["metrics"]}
        self.assertEqual(metrics["atlas_rows_emitted"], 0)
        self.assertEqual(metrics["change_jobs_executed"], 0)
        self.assertEqual(metrics["jobs_reselected"], 2)
        self.assertEqual(metrics["unique_aois_reselected"], 2)

    def test_central_v17_v44_v20_v19_metrics_and_closed_trees_are_exact(self) -> None:
        module = _implementation_module()
        module._validate_accepted_inputs(ROOT)
        bundle = build_current_coverage_ledger_v14(DEFINITION)
        artifacts = {row["artifact_id"]: row for row in bundle.ledger["artifacts"]}
        self.assertEqual(
            artifacts["construction-master-public-open-v17"]["reported_metrics"]
            ["total_master_rows"],
            109_211,
        )
        self.assertEqual(
            artifacts["construction-map-public-open-v17"]["reported_metrics"]
            ["mapped_total_rows"],
            108_975,
        )
        self.assertEqual(
            artifacts["construction-map-public-open-v17"]["reported_metrics"]
            ["unmapped_rows"],
            236,
        )
        self.assertEqual(
            artifacts["seed-epoch-official-v44"]["reported_metrics"]
            ["source_scoped_entity_rows"],
            573,
        )
        self.assertEqual(
            artifacts["federation-public-open-v20"]["reported_metrics"]
            ["source_scoped_rows"],
            15_998,
        )
        self.assertEqual(
            artifacts["coverage-audit-public-open-v19"]["reported_metrics"]
            ["open_gaps"],
            3_123,
        )
        self.assertIsNone(
            artifacts["coverage-audit-public-open-v19"]["reported_metrics"]
            ["unique_physical_sites"]
        )
        self.assertEqual(
            bundle.ledger["artifact_inventory_counts"],
            module._EXPECTED_INVENTORY_COUNTS,
        )

    def test_definition_generation_is_order_independent_and_collision_safe(self) -> None:
        canonical = make_v14_definition(ROOT)
        self.assertEqual(canonical, DEFINITION.read_bytes())
        module = _implementation_module()
        base_definition, base_ledger, base_manifest = module._load_v13_base(ROOT)
        shuffled = deepcopy(base_definition)
        shuffled["entries"] = list(reversed(shuffled["entries"]))
        with patch.object(
            module,
            "_load_v13_base",
            return_value=(shuffled, base_ledger, base_manifest),
        ):
            self.assertEqual(module.make_v14_definition(ROOT), canonical)

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "definition.json"
            self.assertEqual(write_v14_definition(ROOT, destination), DEFINITION_SHA256)
            self.assertEqual(destination.read_bytes(), canonical)
            with self.assertRaisesRegex(CurrentCoverageV14Error, "refusing existing output"):
                write_v14_definition(ROOT, destination)

    def test_definition_mutations_fail_closed_without_touching_source(self) -> None:
        module = _implementation_module()
        original_read = module._read_regular
        document = json.loads(DEFINITION.read_text())
        mutations = []

        changed = deepcopy(document)
        changed["scope"]["global_completeness_claimed"] = True
        mutations.append(changed)
        changed = deepcopy(document)
        changed["entries"] = changed["entries"][:-1]
        mutations.append(changed)
        changed = deepcopy(document)
        changed["entries"].append(deepcopy(changed["entries"][-1]))
        mutations.append(changed)
        changed = deepcopy(document)
        changed["base_ledger"]["ledger"]["sha256"] = "0" * 64
        mutations.append(changed)
        changed = deepcopy(document)
        next(
            row
            for row in changed["entries"]
            if row["artifact_id"] == "satellite-queue-open-seed-v43"
        )["current_role"] = "authoritative_public_core"
        mutations.append(changed)

        for mutation in mutations:
            mutation_raw = module._canonical_json(mutation)

            def changed_read(path: Path, label: str) -> bytes:
                if Path(path).resolve() == DEFINITION.resolve():
                    return mutation_raw
                return original_read(path, label)

            with patch.object(module, "_read_regular", side_effect=changed_read):
                with self.assertRaises(CurrentCoverageV14Error):
                    build_current_coverage_ledger_v14(DEFINITION)

    def test_writer_refuses_collisions_requires_freeze_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "fresh"
            write_current_coverage_ledger_v14(DEFINITION, destination, freeze=True)
            try:
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
                self.assertEqual({path.name for path in destination.iterdir()}, BUNDLE_FILES)
                self.assertTrue(
                    all(
                        stat.S_IMODE(path.stat().st_mode) == 0o444
                        for path in destination.iterdir()
                    )
                )
                validate_current_coverage_ledger_v14(
                    destination, definition_path=DEFINITION
                )
                with self.assertRaisesRegex(
                    CurrentCoverageV14Error, "refusing existing output"
                ):
                    write_current_coverage_ledger_v14(
                        DEFINITION, destination, freeze=True
                    )
            finally:
                destination.chmod(0o755)
                for path in destination.iterdir():
                    path.chmod(0o644)

            with self.assertRaisesRegex(
                CurrentCoverageV14Error, "requires freeze=True"
            ):
                write_current_coverage_ledger_v14(
                    DEFINITION, root / "unfrozen", freeze=False
                )

            locked = root / "locked"
            lock = root / ".locked.lock"
            lock.write_text("owned\n")
            with self.assertRaisesRegex(CurrentCoverageV14Error, "active output lock"):
                write_current_coverage_ledger_v14(DEFINITION, locked, freeze=True)

    def test_v13_definition_and_frozen_bundle_remain_byte_stable(self) -> None:
        before = {path: path.read_bytes() for path in BASE_HASHES}
        for path, expected_sha256 in BASE_HASHES.items():
            self.assertEqual(_sha256(path), expected_sha256)
        module = _implementation_module()
        with _offline_guard():
            make_v14_definition(ROOT)
            build_current_coverage_ledger_v14(DEFINITION)
            base_built = module._legacy.build_current_coverage_ledger(BASE_DEFINITION)
            base_manifest = module._legacy.validate_current_coverage_ledger(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
        self.assertEqual(base_manifest["ledger_id"], "current-coverage-2026-07-20-v13")
        self.assertEqual(
            base_built.ledger_bytes,
            before[BASE_BUNDLE / "current-coverage-ledger.json"],
        )
        self.assertEqual(before, {path: path.read_bytes() for path in BASE_HASHES})

    def test_root_and_nested_import_layouts_reproduce_same_hashes(self) -> None:
        code = "\n".join(
            [
                "import hashlib",
                "from datacenter_atlas.current_coverage_v14 import build_current_coverage_ledger_v14",
                f"bundle = build_current_coverage_ledger_v14({str(DEFINITION)!r})",
                "print(hashlib.sha256(bundle.ledger_bytes).hexdigest())",
                "print(hashlib.sha256(bundle.manifest_bytes).hexdigest())",
            ]
        )
        expected = [LEDGER_SHA256, MANIFEST_SHA256]
        for cwd in (ROOT.parent, ROOT):
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.stdout.strip().splitlines(), expected)

    def test_cli_validate_is_offline_and_reports_44_artifacts(self) -> None:
        environment = dict(os.environ)
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build_current_coverage_ledger_v14.py"),
                "--validate-only",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["ledger_id"], V14_LEDGER_ID)
        self.assertEqual(result["artifacts"], 44)
        self.assertTrue(result["validated"])


if __name__ == "__main__":
    unittest.main()

