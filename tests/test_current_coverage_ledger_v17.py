from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
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

from datacenter_atlas.current_coverage_v17 import (
    ALL_ENTRIES_SHA256,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    CurrentCoverageV17Error,
    PARITY_GAPS_SHA256,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_5_SHA256,
    REPLACEMENT_ARTIFACT_IDS,
    UNCHANGED_40_SHA256,
    V16_BASE_LINEAGE,
    V17_DEFINITION_SHA256,
    V17_GENERATED_AT,
    V17_LEDGER_ID,
    build_current_coverage_ledger_v17,
    make_v17_definition,
    validate_current_coverage_ledger_v17,
    write_current_coverage_ledger_v17,
    write_v17_definition,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v17.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v16.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v17"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v16"
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v17.py"

DEFINITION_SHA256 = "6ddeea2d789d8dbbf09df12fc4739e67d1f5ee04b6a99c98a27366f9a965ad0f"
LEDGER_SHA256 = "d87e0cc5869e5887c5336449cd98859075065cb56bfe620499c8d4e64e863fa6"
MANIFEST_SHA256 = "f782fd93681c0a66527f033f304554d288128f0209db7437ef8fd28c1cebe1e2"
SIDECAR_SHA256 = "21d1d134176a55fdbb844294ff6508f6023a563c348345ef3e5fe115893f0ce7"

FILE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v17.py": (
        44_652,
        "f5933e7a77b1ec437a09ff71b806baf2ce5996a037c4ace25dc01f2c77516770",
    ),
    ROOT / "current_coverage_v17.py": (
        150,
        "1cba63622aa9cd23b6b1fb534e61ade356dac8bc1c0df0482f1cc7f9c0fa29ba",
    ),
    SCRIPT: (
        2_795,
        "4b9b9ff56eba49f35884cb181eaa2fcd2a9b91cfc5c4f2f39f038a5fee65950c",
    ),
    DEFINITION: (133_016, DEFINITION_SHA256),
    BUNDLE / "current-coverage-ledger.json": (92_132, LEDGER_SHA256),
    BUNDLE / "manifest.json": (25_659, MANIFEST_SHA256),
    BUNDLE / "manifest.sha256": (80, SIDECAR_SHA256),
}

BASE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v16.py": (
        50_693,
        "e5d385c5caf6dfa56a45b10a8150d46360413e99abdb594b86d5f370f6a35b90",
    ),
    BASE_DEFINITION: (
        132_723,
        "df337239c05f02ebd40847c22a214230ada51730f35444b6b13b8fc2e6e05137",
    ),
    BASE_BUNDLE / "current-coverage-ledger.json": (
        91_839,
        "1e9368fd910653edc116070710e08d49033110c6c448fcc715e9d3fbde603d95",
    ),
    BASE_BUNDLE / "manifest.json": (
        25_659,
        "3745f27ef5cf631dccd1ac0c894ea59d1e31751825ad05acf0d2243e9b971dad",
    ),
    BASE_BUNDLE / "manifest.sha256": (
        80,
        "92989e32ccbd8a40b633d4aeb7728ef152ca0898de16567967fa936427af4f38",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, _sha256(path)


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
    return importlib.import_module(build_current_coverage_ledger_v17.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v17 attempted network access")
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


class FrozenCurrentCoverageLedgerV17Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_and_pins_v16(self) -> None:
        self.assertEqual(V17_DEFINITION_SHA256, DEFINITION_SHA256)
        for path, expected in {**FILE_PINS, **BASE_PINS}.items():
            self.assertEqual(_checkpoint(path), expected, path)

        module = _implementation_module()
        with _offline_guard():
            module._v16.validate_current_coverage_ledger_v16(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
            first = build_current_coverage_ledger_v17(DEFINITION)
            second = build_current_coverage_ledger_v17(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v17(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v17(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V17_LEDGER_ID)
        self.assertEqual(first_manifest["base_ledger"], V16_BASE_LINEAGE)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 45)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_exactly_five_replacements_and_40_unchanged(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        base_entries = _entry_map(base)
        entries = _entry_map(current)
        self.assertEqual(ARTIFACT_REPLACEMENTS, {
            "construction-map-public-open-v21": "construction-map-public-open-v22",
            "construction-master-public-open-v21": "construction-master-public-open-v22",
            "coverage-audit-public-open-v21": "coverage-audit-public-open-v22",
            "federation-public-open-v22": "federation-public-open-v23",
            "seed-epoch-official-v47": "seed-epoch-official-v49",
        })
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(set(entries) - set(base_entries), REPLACEMENT_ARTIFACT_IDS)
        self.assertEqual(len(entries), 45)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        replacements = [entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual(len(unchanged), 40)
        self.assertEqual(len(replacements), 5)
        for artifact_id in unchanged_ids:
            self.assertEqual(
                _canonical_line(entries[artifact_id]),
                _canonical_line(base_entries[artifact_id]),
            )
        self.assertEqual(_component_digest(unchanged), UNCHANGED_40_SHA256)
        self.assertEqual(_component_digest(replacements), REPLACEMENT_5_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        self.assertEqual(
            hashlib.sha256(_canonical_line(current["parity_gaps"])).hexdigest(),
            PARITY_GAPS_SHA256,
        )
        review_id = (
            "satellite-change-review-open-seed-v43-active-reselected-v2-review-v1"
        )
        self.assertEqual(entries[review_id], base_entries[review_id])

    def test_only_affected_parity_gap_ids_advance(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        self.assertEqual(len(base["parity_gaps"]), len(current["parity_gaps"]))
        for old, new in zip(base["parity_gaps"], current["parity_gaps"], strict=True):
            old_rest = deepcopy(old)
            new_rest = deepcopy(new)
            old_affected = old_rest.pop("affected_artifact_ids")
            new_affected = new_rest.pop("affected_artifact_ids")
            self.assertEqual(old_rest, new_rest)
            self.assertEqual(
                new_affected,
                sorted(
                    ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                    for artifact_id in old_affected
                ),
            )

    def test_successor_metrics_limitations_inventory_and_scope_are_exact(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        expected_metrics = {
            "seed-epoch-official-v49": {
                "capacity_observations": 467,
                "construction_pipeline_records": 327,
                "construction_source_signals": 235,
                "evidence_records": 352,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 629,
            },
            "federation-public-open-v23": {
                "capacity_observations": 1_253,
                "construction_pipeline_records": 6_577,
                "non_review_construction_pipeline_records": 447,
                "non_review_source_scoped_rows": 9_924,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 16_054,
                "unique_physical_sites": None,
            },
            "coverage-audit-public-open-v22": {
                "coverage_groups": 633,
                "non_review_source_scoped_rows": 9_924,
                "open_gaps": 3_293,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 16_054,
                "unique_physical_sites": None,
            },
        }
        for artifact_id, expected in expected_metrics.items():
            actual = {row["label"]: row["value"] for row in entries[artifact_id]["metrics"]}
            self.assertEqual(actual, expected)

        master = {
            row["label"]: row["value"]
            for row in entries["construction-master-public-open-v22"]["metrics"]
        }
        self.assertEqual(master["total_master_rows"], 109_239)
        self.assertEqual(master["tier_a_rows"], 447)
        self.assertEqual(master["added_replacement_rows"], 128)
        self.assertIsNone(master["unique_physical_sites"])
        map_metrics = {
            row["label"]: row["value"]
            for row in entries["construction-map-public-open-v22"]["metrics"]
        }
        self.assertEqual(map_metrics["mapped_total_rows"], 108_975)
        self.assertEqual(map_metrics["unmapped_rows"], 264)
        self.assertIsNone(map_metrics["unique_physical_sites"])

        limitations = " ".join(
            limitation
            for artifact_id in REPLACEMENT_ARTIFACT_IDS
            for limitation in entries[artifact_id]["limitations"]
        ).lower()
        for phrase in (
            "not unique physical sites",
            "historical lifecycle statuses",
            "review and structural-discovery rows",
            "not globally additive",
            "no annual energy is inferred",
            "not all confirmed construction sites",
        ):
            self.assertIn(phrase, limitations)

        base_ledger = json.loads(
            (BASE_BUNDLE / "current-coverage-ledger.json").read_text()
        )
        bundle = build_current_coverage_ledger_v17(DEFINITION)
        self.assertEqual(
            bundle.ledger["artifact_inventory_counts"],
            base_ledger["artifact_inventory_counts"],
        )
        inventory = bundle.ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 45)
        self.assertEqual(inventory["by_access_tier"], {
            "local_restricted": 6,
            "public_open": 39,
        })
        self.assertEqual(inventory["public_open_review_only_artifacts"], 26)
        self.assertEqual(inventory["by_evidence_scope"]["review_only"], 30)
        self.assertFalse(bundle.ledger["scope"]["global_completeness_claimed"])
        self.assertFalse(bundle.ledger["scope"]["benchmark_parity_claimed"])
        self.assertIsNone(bundle.ledger["scope"]["unique_physical_site_count"])
        benchmark_gap = next(
            gap
            for gap in bundle.ledger["parity_gaps"]
            if gap["gap_id"] == "benchmark-parity-not-computed"
        )
        self.assertEqual(benchmark_gap["status"], "not_computed")
        self.assertIn("SemiAnalysis", benchmark_gap["summary"])

    def test_timestamps_and_rejected_lineage_are_fail_closed(self) -> None:
        generated_at = datetime.fromisoformat(V17_GENERATED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(generated_at, datetime.now(UTC))
        module = _implementation_module()
        for _label, (_path, _field, expected) in module._SOURCE_TIMESTAMPS.items():
            source_time = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            self.assertLessEqual(source_time, generated_at)

        rendered = DEFINITION.read_text().lower()
        for forbidden in (
            "current-coverage-2026-07-20-v15",
            "open-seed-2026-07-20-v45",
            "open-seed-2026-07-20-v46",
            "open-seed-2026-07-20-v48",
            "seed-epoch-official-v45",
            "seed-epoch-official-v46",
            "seed-epoch-official-v47",
            "seed-epoch-official-v48",
            "construction-master-public-open-v20",
            "construction-master-public-open-v21",
            "construction-map-public-open-v21",
            "coverage-audit-public-open-v21",
            "federation-public-open-v21",
            "federation-public-open-v22",
        ):
            self.assertNotIn(forbidden, rendered)
        self.assertIn("construction_master_v6.py", module._PINNED_FILES[
            "construction master v22 implementation"
        ][0])
        self.assertIn("construction_map_v6.py", module._PINNED_FILES[
            "construction map v22 implementation"
        ][0])

    def test_definition_generation_is_order_independent_and_collision_safe(self) -> None:
        canonical = make_v17_definition(ROOT)
        self.assertEqual(canonical, DEFINITION.read_bytes())
        module = _implementation_module()
        base_definition, base_ledger, base_manifest = module._load_v16_base(ROOT)
        shuffled = deepcopy(base_definition)
        shuffled["entries"] = list(reversed(shuffled["entries"]))
        with patch.object(
            module,
            "_load_v16_base",
            return_value=(shuffled, base_ledger, base_manifest),
        ):
            self.assertEqual(module.make_v17_definition(ROOT), canonical)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "definition.json"
            self.assertEqual(write_v17_definition(ROOT, destination), DEFINITION_SHA256)
            self.assertEqual(destination.read_bytes(), canonical)
            with self.assertRaisesRegex(CurrentCoverageV17Error, "refusing existing output"):
                write_v17_definition(ROOT, destination)
            dangling = root / "dangling.json"
            dangling.symlink_to(root / "absent.json")
            with self.assertRaisesRegex(CurrentCoverageV17Error, "refusing existing output"):
                write_v17_definition(ROOT, dangling)
            self.assertTrue(dangling.is_symlink())

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
        changed["base_ledger"]["ledger"]["sha256"] = "0" * 64
        mutations.append(changed)

        for mutation in mutations:
            mutation_raw = module._canonical_json(mutation)

            def changed_read(path: Path, label: str) -> bytes:
                if Path(path).resolve() == DEFINITION.resolve():
                    return mutation_raw
                return original_read(path, label)

            with patch.object(module, "_read_regular", side_effect=changed_read):
                with self.assertRaises(CurrentCoverageV17Error):
                    build_current_coverage_ledger_v17(DEFINITION)

        seed_manifest = ROOT / "releases/2026-07-20-open-seed-v49/manifest.json"

        def changed_input(path: Path, label: str) -> bytes:
            raw = original_read(path, label)
            if Path(path).resolve() == seed_manifest.resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_input):
            with self.assertRaisesRegex(
                CurrentCoverageV17Error, "official seed v49 manifest changed"
            ):
                build_current_coverage_ledger_v17(DEFINITION)

    def test_writer_refuses_existing_active_lock_late_collision_and_unfrozen(self) -> None:
        module = _implementation_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "fresh"
            write_current_coverage_ledger_v17(DEFINITION, destination, freeze=True)
            try:
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
                validate_current_coverage_ledger_v17(
                    destination, definition_path=DEFINITION
                )
                with self.assertRaisesRegex(
                    CurrentCoverageV17Error, "refusing existing output"
                ):
                    write_current_coverage_ledger_v17(DEFINITION, destination)
            finally:
                _make_writable(destination)

            with self.assertRaisesRegex(CurrentCoverageV17Error, "requires freeze=True"):
                write_current_coverage_ledger_v17(
                    DEFINITION, root / "unfrozen", freeze=False
                )
            locked = root / "locked"
            (root / ".locked.lock").write_text("owned\n")
            with self.assertRaisesRegex(CurrentCoverageV17Error, "active output lock"):
                write_current_coverage_ledger_v17(DEFINITION, locked)

            late = root / "late"
            original_promote = module._promote_noreplace

            def late_promote(stage: Path, target: Path) -> None:
                target.mkdir()
                original_promote(stage, target)

            with patch.object(module, "_promote_noreplace", side_effect=late_promote):
                with self.assertRaisesRegex(
                    CurrentCoverageV17Error, "late output collision"
                ):
                    write_current_coverage_ledger_v17(DEFINITION, late)

    def test_cli_and_both_import_layouts_validate(self) -> None:
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
        self.assertEqual(json.loads(result.stdout), {
            "artifacts": 45,
            "ledger_id": V17_LEDGER_ID,
            "output": str(BUNDLE),
            "validated": True,
        })

        code = (
            "from datacenter_atlas.current_coverage_v17 import "
            "validate_current_coverage_ledger_v17 as validate; "
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
            self.assertEqual(result.stdout.strip(), f"{V17_LEDGER_ID} 45")

    def test_v16_history_remains_byte_identical(self) -> None:
        before = {path: _checkpoint(path) for path in BASE_PINS}
        build_current_coverage_ledger_v17(DEFINITION)
        for path, expected in BASE_PINS.items():
            self.assertEqual(before[path], expected, path)
            self.assertEqual(_checkpoint(path), expected, path)
        self.assertEqual(stat.S_IMODE(BASE_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in BASE_BUNDLE.iterdir()
            )
        )


if __name__ == "__main__":
    unittest.main()
