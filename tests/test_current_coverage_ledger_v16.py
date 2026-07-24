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

from datacenter_atlas.current_coverage_v16 import (
    ADDED_ARTIFACT_IDS,
    ALL_ENTRIES_SHA256,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    CurrentCoverageV16Error,
    NEW_ARTIFACT_IDS,
    NEW_ENTRIES_SHA256,
    PARITY_GAPS_SHA256,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_ARTIFACT_IDS,
    UNCHANGED_39_SHA256,
    V14_BASE_LINEAGE,
    V16_DEFINITION_SHA256,
    V16_LEDGER_ID,
    build_current_coverage_ledger_v16,
    make_v16_definition,
    validate_current_coverage_ledger_v16,
    write_current_coverage_ledger_v16,
    write_v16_definition,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v16.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v14.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v16"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v14"
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v16.py"

DEFINITION_SHA256 = "df337239c05f02ebd40847c22a214230ada51730f35444b6b13b8fc2e6e05137"
LEDGER_SHA256 = "1e9368fd910653edc116070710e08d49033110c6c448fcc715e9d3fbde603d95"
MANIFEST_SHA256 = "3745f27ef5cf631dccd1ac0c894ea59d1e31751825ad05acf0d2243e9b971dad"
SIDECAR_SHA256 = "92989e32ccbd8a40b633d4aeb7728ef152ca0898de16567967fa936427af4f38"

FILE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v16.py": (
        50_693,
        "e5d385c5caf6dfa56a45b10a8150d46360413e99abdb594b86d5f370f6a35b90",
    ),
    ROOT / "current_coverage_v16.py": (
        150,
        "88e3a89c14174436f2ae6ef80aad2dae500a165e99d7a95ba130c41101f7952a",
    ),
    SCRIPT: (
        2_795,
        "f90231520df4b6c8bdb01e84c756c7fd304acc6882ad62f32d7c4db3f9cb18e9",
    ),
    DEFINITION: (132_723, DEFINITION_SHA256),
    BUNDLE / "current-coverage-ledger.json": (91_839, LEDGER_SHA256),
    BUNDLE / "manifest.json": (25_659, MANIFEST_SHA256),
    BUNDLE / "manifest.sha256": (80, SIDECAR_SHA256),
}

BASE_HASHES = {
    BASE_DEFINITION: "907942b43861845703900dfb57e518ed56611bb932b2ec0f16f1ab656b0beab0",
    BASE_BUNDLE / "current-coverage-ledger.json": (
        "ede89a5b75ca30dae4c96f3ae876e02abf53eff00497a8edc85fc9fcde69b2bd"
    ),
    BASE_BUNDLE / "manifest.json": (
        "5f318e610653a4579fb9d995133fd3ea388de5c7a2a3b66c2e250fced69d150c"
    ),
    BASE_BUNDLE / "manifest.sha256": (
        "a9ad99f6a82b749ec69ef9f38a1b2f1c010848b0e7db33b878c232b64d4ce536"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _component_digest(entries: list[dict]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _entry_map(document: dict) -> dict[str, dict]:
    return {entry["artifact_id"]: entry for entry in document["entries"]}


def _implementation_module():
    return importlib.import_module(build_current_coverage_ledger_v16.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v16 attempted network access")
    with patch.object(socket, "socket", side_effect=blocked), patch.object(
        socket, "create_connection", side_effect=blocked
    ), patch.object(socket, "getaddrinfo", side_effect=blocked), patch.object(
        socket, "gethostbyname", side_effect=blocked
    ):
        yield


def _make_writable(directory: Path) -> None:
    if not directory.exists() or directory.is_symlink():
        return
    directory.chmod(0o755)
    for path in directory.iterdir():
        path.chmod(0o644)


class FrozenCurrentCoverageLedgerV16Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_and_validates_twice_offline(self) -> None:
        self.assertEqual(V16_DEFINITION_SHA256, DEFINITION_SHA256)
        for path, (expected_size, expected_sha256) in FILE_PINS.items():
            self.assertEqual(path.stat().st_size, expected_size, path)
            self.assertEqual(_sha256(path), expected_sha256, path)

        with _offline_guard():
            first = build_current_coverage_ledger_v16(DEFINITION)
            second = build_current_coverage_ledger_v16(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v16(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v16(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V16_LEDGER_ID)
        self.assertEqual(first_manifest["base_ledger"], V14_BASE_LINEAGE)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 45)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_five_replacements_one_addition_and_39_unchanged(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        base_entries = _entry_map(base)
        entries = _entry_map(current)
        self.assertEqual(
            ARTIFACT_REPLACEMENTS,
            {
                "construction-map-public-open-v17": "construction-map-public-open-v21",
                "construction-master-public-open-v17": "construction-master-public-open-v21",
                "coverage-audit-public-open-v19": "coverage-audit-public-open-v21",
                "federation-public-open-v20": "federation-public-open-v22",
                "seed-epoch-official-v44": "seed-epoch-official-v47",
            },
        )
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(
            set(entries) - set(base_entries),
            REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS,
        )
        self.assertEqual(NEW_ARTIFACT_IDS, set(entries) - set(base_entries))
        self.assertEqual(len(entries), 45)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        new_entries = [
            entries[artifact_id]
            for artifact_id in sorted(NEW_ARTIFACT_IDS)
        ]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual(len(unchanged), 39)
        for artifact_id in unchanged_ids:
            self.assertEqual(entries[artifact_id], base_entries[artifact_id])
        self.assertEqual(_component_digest(unchanged), UNCHANGED_39_SHA256)
        self.assertEqual(_component_digest(new_entries), NEW_ENTRIES_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        self.assertEqual(
            hashlib.sha256(_canonical_line(current["parity_gaps"])).hexdigest(),
            PARITY_GAPS_SHA256,
        )

    def test_public_core_metrics_are_exact_and_non_additive(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))

        seed_metrics = {
            row["label"]: row["value"]
            for row in entries["seed-epoch-official-v47"]["metrics"]
        }
        self.assertEqual(
            seed_metrics,
            {
                "capacity_observations": 454,
                "construction_pipeline_records": 313,
                "construction_source_signals": 228,
                "evidence_records": 337,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 601,
            },
        )
        federation_metrics = {
            row["label"]: row["value"]
            for row in entries["federation-public-open-v22"]["metrics"]
        }
        self.assertEqual(federation_metrics["source_scoped_rows"], 16_026)
        self.assertEqual(federation_metrics["construction_pipeline_records"], 6_563)
        self.assertEqual(
            federation_metrics["non_review_construction_pipeline_records"], 433
        )
        self.assertIsNone(federation_metrics["unique_physical_sites"])

        coverage_metrics = {
            row["label"]: row["value"]
            for row in entries["coverage-audit-public-open-v21"]["metrics"]
        }
        self.assertEqual(coverage_metrics["open_gaps"], 3_193)
        self.assertEqual(coverage_metrics["coverage_groups"], 613)

        master_metrics = {
            row["label"]: row["value"]
            for row in entries["construction-master-public-open-v21"]["metrics"]
        }
        self.assertEqual(master_metrics["total_master_rows"], 109_225)
        self.assertEqual(master_metrics["tier_a_rows"], 433)
        self.assertEqual(master_metrics["added_replacement_rows"], 114)
        self.assertEqual(master_metrics["inherited_rows"], 108_912)

        map_metrics = {
            row["label"]: row["value"]
            for row in entries["construction-map-public-open-v21"]["metrics"]
        }
        self.assertEqual(map_metrics["mapped_total_rows"], 108_975)
        self.assertEqual(map_metrics["unmapped_rows"], 250)
        self.assertEqual(map_metrics["default_visible_rows"], 6_481)

    def test_satellite_change_review_is_review_only_and_creates_no_claim(self) -> None:
        current = json.loads(DEFINITION.read_text())
        artifact_id = next(iter(ADDED_ARTIFACT_IDS))
        entry = _entry_map(current)[artifact_id]
        self.assertEqual(entry["artifact_kind"], "analyst_imagery_review")
        self.assertEqual(entry["current_role"], "public_supporting_review_lane")
        self.assertEqual(entry["evidence_scope"], "review_only")
        self.assertEqual(entry["publication_mode"], "public_review_or_discovery")
        self.assertEqual(
            [row["checkpoint_id"] for row in entry["checkpoints"]],
            ["manifest", "source_run_manifest", "summary"],
        )
        self.assertEqual(
            {row["label"]: row["value"] for row in entry["metrics"]},
            {
                "atlas_mutation": False,
                "manual_review_completed": True,
                "review_decisions": 2,
                "site_promotion_rejections": 2,
                "source_artifacts_hash_bound": 12,
                "unique_site_claim_created": False,
            },
        )
        limitations = " ".join(entry["limitations"]).lower()
        for token in (
            "do not negate separately sourced construction facts",
            "not construction areas",
            "not construction, identity, status, type, capacity, power, energy, pue, workload, or unique-site evidence",
        ):
            self.assertIn(token, limitations)

        gaps = {row["gap_id"]: row for row in current["parity_gaps"]}
        self.assertIn(
            artifact_id,
            gaps["global-construction-coverage-partial"]["affected_artifact_ids"],
        )
        self.assertIn(
            artifact_id,
            gaps["satellite-review-backlog"]["affected_artifact_ids"],
        )

    def test_inventory_scope_and_rejected_lineage_guards_are_exact(self) -> None:
        bundle = build_current_coverage_ledger_v16(DEFINITION)
        inventory = bundle.ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 45)
        self.assertEqual(
            inventory["by_access_tier"],
            {"local_restricted": 6, "public_open": 39},
        )
        self.assertEqual(inventory["public_open_review_only_artifacts"], 26)
        self.assertEqual(inventory["by_evidence_scope"]["review_only"], 30)
        self.assertFalse(bundle.ledger["scope"]["global_completeness_claimed"])
        self.assertFalse(bundle.ledger["scope"]["benchmark_parity_claimed"])
        self.assertIsNone(bundle.ledger["scope"]["unique_physical_site_count"])

        rendered = DEFINITION.read_text().lower()
        for forbidden in (
            "current-coverage-2026-07-20-v15",
            "open-seed-2026-07-20-v46",
            "open-seed-2026-07-20-v48",
            "seed-epoch-official-v44",
            "seed-epoch-official-v46",
            "seed-epoch-official-v48",
            "construction-master-public-open-v20",
            "federation-public-open-v21",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_definition_generation_is_order_independent_and_collision_safe(self) -> None:
        canonical = make_v16_definition(ROOT)
        self.assertEqual(canonical, DEFINITION.read_bytes())
        module = _implementation_module()
        base_definition, base_ledger, base_manifest = module._load_v14_base(ROOT)
        shuffled = deepcopy(base_definition)
        shuffled["entries"] = list(reversed(shuffled["entries"]))
        with patch.object(
            module,
            "_load_v14_base",
            return_value=(shuffled, base_ledger, base_manifest),
        ):
            self.assertEqual(module.make_v16_definition(ROOT), canonical)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "definition.json"
            self.assertEqual(write_v16_definition(ROOT, destination), DEFINITION_SHA256)
            self.assertEqual(destination.read_bytes(), canonical)
            with self.assertRaisesRegex(CurrentCoverageV16Error, "refusing existing output"):
                write_v16_definition(ROOT, destination)

            dangling = root / "dangling.json"
            dangling.symlink_to(root / "absent.json")
            with self.assertRaisesRegex(CurrentCoverageV16Error, "refusing existing output"):
                write_v16_definition(ROOT, dangling)
            self.assertTrue(dangling.is_symlink())
            self.assertFalse((root / "absent.json").exists())

    def test_definition_and_input_mutations_fail_closed(self) -> None:
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

        for mutation in mutations:
            mutation_raw = module._canonical_json(mutation)

            def changed_read(path: Path, label: str) -> bytes:
                if Path(path).resolve() == DEFINITION.resolve():
                    return mutation_raw
                return original_read(path, label)

            with patch.object(module, "_read_regular", side_effect=changed_read):
                with self.assertRaises(CurrentCoverageV16Error):
                    build_current_coverage_ledger_v16(DEFINITION)

        seed_manifest = ROOT / "releases/2026-07-20-open-seed-v47/manifest.json"

        def changed_input(path: Path, label: str) -> bytes:
            raw = original_read(path, label)
            if Path(path).resolve() == seed_manifest.resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_input):
            with self.assertRaisesRegex(
                CurrentCoverageV16Error, "official seed v47 manifest changed"
            ):
                build_current_coverage_ledger_v16(DEFINITION)

    def test_writer_refuses_collisions_and_unfrozen_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "fresh"
            write_current_coverage_ledger_v16(DEFINITION, destination, freeze=True)
            try:
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
                validate_current_coverage_ledger_v16(
                    destination, definition_path=DEFINITION
                )
                with self.assertRaisesRegex(
                    CurrentCoverageV16Error, "refusing existing output"
                ):
                    write_current_coverage_ledger_v16(DEFINITION, destination)
            finally:
                _make_writable(destination)

            with self.assertRaisesRegex(CurrentCoverageV16Error, "requires freeze=True"):
                write_current_coverage_ledger_v16(
                    DEFINITION, root / "unfrozen", freeze=False
                )

            locked = root / "locked"
            (root / ".locked.lock").write_text("owned\n")
            with self.assertRaisesRegex(CurrentCoverageV16Error, "active output lock"):
                write_current_coverage_ledger_v16(DEFINITION, locked)

    def test_cli_and_both_import_layouts_validate_offline(self) -> None:
        command = [
            sys.executable,
            str(SCRIPT),
            "--validate-only",
            "--definition",
            str(DEFINITION),
            "--output",
            str(BUNDLE),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "artifacts": 45,
                "ledger_id": V16_LEDGER_ID,
                "output": str(BUNDLE),
                "validated": True,
            },
        )

        code = (
            "from datacenter_atlas.current_coverage_v16 import "
            "validate_current_coverage_ledger_v16 as validate; "
            f"m=validate({str(BUNDLE)!r}, definition_path={str(DEFINITION)!r}); "
            "print(m['ledger_id'], len(m['input_checkpoints']))"
        )
        for cwd, pythonpath in ((WORKSPACE, WORKSPACE), (ROOT, ROOT)):
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(pythonpath)
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"{V16_LEDGER_ID} 45")

    def test_v14_history_remains_byte_identical(self) -> None:
        before = {path: _sha256(path) for path in BASE_HASHES}
        build_current_coverage_ledger_v16(DEFINITION)
        for path, expected in BASE_HASHES.items():
            self.assertEqual(before[path], expected, path)
            self.assertEqual(_sha256(path), expected, path)
        self.assertEqual(stat.S_IMODE(BASE_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in BASE_BUNDLE.iterdir()
            )
        )


if __name__ == "__main__":
    unittest.main()
