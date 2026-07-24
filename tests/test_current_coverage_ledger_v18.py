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

from datacenter_atlas.current_coverage_v18 import (
    ADDED_ARTIFACT_IDS,
    ADDITION_2_SHA256,
    ALL_ENTRIES_SHA256,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    CurrentCoverageV18Error,
    PARITY_GAPS_SHA256,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_5_SHA256,
    REPLACEMENT_ARTIFACT_IDS,
    UNCHANGED_40_SHA256,
    V17_BASE_LINEAGE,
    V18_DEFINITION_SHA256,
    V18_GENERATED_AT,
    V18_LEDGER_ID,
    build_current_coverage_ledger_v18,
    make_v18_definition,
    validate_current_coverage_ledger_v18,
    write_current_coverage_ledger_v18,
    write_v18_definition,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v18.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v17.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v18"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v17"
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v18.py"

DEFINITION_SHA256 = "d8e151cb9b9f38349c5a462a31d91ec70776d5bd25d0228becffb8f0d7546e8c"
LEDGER_SHA256 = "a1c1e6f680db43c7b571bb94846315f756c918b58e2eea31853ef2e6c1740f01"
MANIFEST_SHA256 = "a3fdc74b36ce33f6959c436ecb34f6171614a0e96d8a4f9a8140db9f33a5d2f4"
SIDECAR_SHA256 = "c127cf61d6f889162ca0a11ae12beb950be5fdd00d2a7daf13257bbd74baef96"
V18_TREE_SHA256 = "2e02522427363c2c4bc02cd0d19aa81e6d7fe87e647e06d3b0a7ab6e7e14d420"

FILE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v18.py": (
        62_454,
        "82c2e03a19dbb3253a44e80cdd6279a6c73f20037f3d22ca004330897a974ace",
    ),
    ROOT / "current_coverage_v18.py": (
        150,
        "b516ac0a032f163c27c0f258cefbe18309b05903389ee1a8654acbc7f1f1de5e",
    ),
    SCRIPT: (
        2_781,
        "f84c399c5e49b8576711fcbe013c0244ef8ab119f0edbe81e92c9e40b36baaff",
    ),
    DEFINITION: (142_381, DEFINITION_SHA256),
    BUNDLE / "current-coverage-ledger.json": (98_109, LEDGER_SHA256),
    BUNDLE / "manifest.json": (27_414, MANIFEST_SHA256),
    BUNDLE / "manifest.sha256": (80, SIDECAR_SHA256),
}

BASE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v17.py": (
        44_652,
        "f5933e7a77b1ec437a09ff71b806baf2ce5996a037c4ace25dc01f2c77516770",
    ),
    ROOT / "current_coverage_v17.py": (
        150,
        "1cba63622aa9cd23b6b1fb534e61ade356dac8bc1c0df0482f1cc7f9c0fa29ba",
    ),
    ROOT / "scripts/build_current_coverage_ledger_v17.py": (
        2_795,
        "4b9b9ff56eba49f35884cb181eaa2fcd2a9b91cfc5c4f2f39f038a5fee65950c",
    ),
    BASE_DEFINITION: (
        133_016,
        "6ddeea2d789d8dbbf09df12fc4739e67d1f5ee04b6a99c98a27366f9a965ad0f",
    ),
    BASE_BUNDLE / "current-coverage-ledger.json": (
        92_132,
        "d87e0cc5869e5887c5336449cd98859075065cb56bfe620499c8d4e64e863fa6",
    ),
    BASE_BUNDLE / "manifest.json": (
        25_659,
        "f782fd93681c0a66527f033f304554d288128f0209db7437ef8fd28c1cebe1e2",
    ),
    BASE_BUNDLE / "manifest.sha256": (
        80,
        "21d1d134176a55fdbb844294ff6508f6023a563c348345ef3e5fe115893f0ce7",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, _sha256(path)


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


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
    return importlib.import_module(build_current_coverage_ledger_v18.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v18 attempted network access")
    with (
        patch.object(socket, "socket", side_effect=blocked),
        patch.object(socket, "create_connection", side_effect=blocked),
        patch.object(socket, "getaddrinfo", side_effect=blocked),
        patch.object(socket, "gethostbyname", side_effect=blocked),
    ):
        yield


def _make_writable(directory: Path) -> None:
    if not directory.exists() or directory.is_symlink():
        return
    directory.chmod(0o755)
    for path in directory.iterdir():
        path.chmod(0o644)


class FrozenCurrentCoverageLedgerV18Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_and_pins_v17(self) -> None:
        self.assertEqual(V18_DEFINITION_SHA256, DEFINITION_SHA256)
        for path, expected in {**FILE_PINS, **BASE_PINS}.items():
            self.assertEqual(_checkpoint(path), expected, path)

        module = _implementation_module()
        with _offline_guard():
            module._v17.validate_current_coverage_ledger_v17(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
            first = build_current_coverage_ledger_v18(DEFINITION)
            second = build_current_coverage_ledger_v18(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v18(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v18(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V18_LEDGER_ID)
        self.assertEqual(first_manifest["base_ledger"], V17_BASE_LINEAGE)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 47)
        self.assertEqual(
            module._v14._tree_digest(BUNDLE, "v18 bundle"),
            (3, 1, V18_TREE_SHA256),
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_40_inherited_five_replacements_and_two_additions(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        base_entries = _entry_map(base)
        entries = _entry_map(current)
        self.assertEqual(
            ARTIFACT_REPLACEMENTS,
            {
                "construction-map-public-open-v22": "construction-map-public-open-v23",
                "construction-master-public-open-v22": "construction-master-public-open-v23",
                "coverage-audit-public-open-v22": "coverage-audit-public-open-v23",
                "federation-public-open-v23": "federation-public-open-v24",
                "seed-epoch-official-v49": "seed-epoch-official-v55",
            },
        )
        self.assertEqual(
            ADDED_ARTIFACT_IDS,
            {
                "exact-identity-decisions-public-open-v2",
                "satellite-change-review-open-seed-v55-active-review-v1",
            },
        )
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(
            set(entries) - set(base_entries),
            REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS,
        )
        self.assertEqual(len(entries), 47)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        replacements = [
            entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
        ]
        additions = [entries[artifact_id] for artifact_id in sorted(ADDED_ARTIFACT_IDS)]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual(
            (len(unchanged), len(replacements), len(additions)), (40, 5, 2)
        )
        for artifact_id in unchanged_ids:
            self.assertEqual(
                _canonical_line(entries[artifact_id]),
                _canonical_line(base_entries[artifact_id]),
            )
        self.assertEqual(_component_digest(unchanged), UNCHANGED_40_SHA256)
        self.assertEqual(_component_digest(replacements), REPLACEMENT_5_SHA256)
        self.assertEqual(_component_digest(additions), ADDITION_2_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        self.assertEqual(
            hashlib.sha256(_canonical_line(current["parity_gaps"])).hexdigest(),
            PARITY_GAPS_SHA256,
        )

    def test_v1_resolution_and_v43_review_are_retained_byte_exact(self) -> None:
        base_entries = _entry_map(json.loads(BASE_DEFINITION.read_text()))
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        retained = {
            "within-release-resolution-public-open-v1",
            "satellite-change-review-open-seed-v43-active-reselected-v2-review-v1",
        }
        for artifact_id in retained:
            self.assertEqual(
                _canonical_line(entries[artifact_id]),
                _canonical_line(base_entries[artifact_id]),
            )

    def test_added_identity_is_authoritative_nonadditive_and_review_is_review_only(
        self,
    ) -> None:
        definition_entries = _entry_map(json.loads(DEFINITION.read_text()))
        ledger_entries = _entry_map(
            {
                "entries": json.loads(
                    (BUNDLE / "current-coverage-ledger.json").read_text()
                )["artifacts"]
            }
        )
        identity_id = "exact-identity-decisions-public-open-v2"
        identity = definition_entries[identity_id]
        self.assertEqual(identity["artifact_kind"], "cross_release_resolution")
        self.assertEqual(identity["current_role"], "authoritative_public_core")
        self.assertEqual(identity["evidence_scope"], "source_scoped")
        self.assertEqual(identity["publication_mode"], "public_index_or_audit")
        self.assertEqual(identity["record_units"], ["crosswalk_link"])
        self.assertFalse(ledger_entries[identity_id]["review_only"])
        identity_metrics = {row["label"]: row["value"] for row in identity["metrics"]}
        self.assertEqual(identity_metrics["exact_source_record_components"], 8_226)
        self.assertEqual(identity_metrics["exact_component_reductions"], 1_732)
        self.assertEqual(identity_metrics["canonical_topology_links"], 2_315)
        self.assertEqual(identity_metrics["unresolved_candidate_references"], 100_536)
        self.assertIsNone(identity_metrics["unique_physical_sites"])
        self.assertFalse(identity_metrics["review_only_rows_in_public_accounting"])
        self.assertIn("non-additive", " ".join(identity["limitations"]).lower())

        review_id = "satellite-change-review-open-seed-v55-active-review-v1"
        review = definition_entries[review_id]
        self.assertEqual(review["artifact_kind"], "analyst_imagery_review")
        self.assertEqual(review["current_role"], "public_supporting_review_lane")
        self.assertEqual(review["evidence_scope"], "review_only")
        self.assertEqual(review["publication_mode"], "public_review_or_discovery")
        self.assertEqual(
            review["record_units"], ["aggregate_report_metric", "review_record"]
        )
        self.assertTrue(ledger_entries[review_id]["review_only"])
        review_metrics = {row["label"]: row["value"] for row in review["metrics"]}
        self.assertEqual(review_metrics["review_decisions"], 5)
        self.assertEqual(review_metrics["site_aligned_follow_up_retained"], 3)
        self.assertEqual(review_metrics["site_promotion_rejections"], 2)
        self.assertEqual(review_metrics["source_artifacts_hash_bound"], 30)
        self.assertEqual(review_metrics["technical_multitile_failures"], 2)
        self.assertFalse(review_metrics["capacity_claim_created"])
        self.assertFalse(review_metrics["site_count_claim_created"])

    def test_successor_metrics_and_limitations_are_live_exact(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        expected_metrics = {
            "seed-epoch-official-v55": {
                "capacity_observations": 482,
                "construction_pipeline_records": 346,
                "construction_source_signals": 252,
                "evidence_records": 383,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 663,
            },
            "federation-public-open-v24": {
                "capacity_observations": 1_268,
                "construction_pipeline_records": 6_596,
                "non_review_construction_pipeline_records": 466,
                "non_review_source_scoped_rows": 9_958,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 16_088,
                "unique_physical_sites": None,
            },
            "coverage-audit-public-open-v23": {
                "coverage_groups": 675,
                "non_review_source_scoped_rows": 9_958,
                "open_gaps": 3_435,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 16_088,
                "unique_physical_sites": None,
            },
        }
        for artifact_id, expected in expected_metrics.items():
            actual = {
                row["label"]: row["value"] for row in entries[artifact_id]["metrics"]
            }
            self.assertEqual(actual, expected)

        master = {
            row["label"]: row["value"]
            for row in entries["construction-master-public-open-v23"]["metrics"]
        }
        self.assertEqual(master["total_master_rows"], 109_258)
        self.assertEqual(master["tier_a_rows"], 466)
        self.assertEqual(master["added_replacement_rows"], 147)
        self.assertEqual(master["replacement_rows"], 346)
        self.assertEqual(master["role_rows_with_any_role"], 124)
        self.assertIsNone(master["unique_physical_sites"])
        map_metrics = {
            row["label"]: row["value"]
            for row in entries["construction-map-public-open-v23"]["metrics"]
        }
        self.assertEqual(map_metrics["mapped_total_rows"], 108_978)
        self.assertEqual(map_metrics["unmapped_rows"], 280)
        self.assertEqual(map_metrics["added_replacement_rows_unmapped"], 144)
        self.assertEqual(map_metrics["default_visible_rows"], 6_484)
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

    def test_only_affected_parity_ids_advance_and_additions_are_scoped(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        additions_by_gap = {
            "global-construction-coverage-partial": {
                "satellite-change-review-open-seed-v55-active-review-v1"
            },
            "satellite-review-backlog": {
                "satellite-change-review-open-seed-v55-active-review-v1"
            },
            "site-resolution-partial": {"exact-identity-decisions-public-open-v2"},
        }
        self.assertEqual(len(base["parity_gaps"]), len(current["parity_gaps"]))
        for old, new in zip(base["parity_gaps"], current["parity_gaps"], strict=True):
            old_rest = deepcopy(old)
            new_rest = deepcopy(new)
            old_affected = old_rest.pop("affected_artifact_ids")
            new_affected = new_rest.pop("affected_artifact_ids")
            self.assertEqual(old_rest, new_rest)
            expected = {
                ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in old_affected
            }
            expected.update(additions_by_gap.get(old["gap_id"], set()))
            self.assertEqual(new_affected, sorted(expected))

    def test_inventory_scope_and_benchmark_blocker_remain_explicit(self) -> None:
        bundle = build_current_coverage_ledger_v18(DEFINITION)
        inventory = bundle.ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 47)
        self.assertEqual(
            inventory["by_access_tier"],
            {"local_restricted": 6, "public_open": 41},
        )
        self.assertEqual(inventory["by_evidence_scope"]["source_scoped"], 5)
        self.assertEqual(inventory["by_evidence_scope"]["review_only"], 31)
        self.assertEqual(inventory["by_publication_mode"]["public_index_or_audit"], 5)
        self.assertEqual(inventory["by_record_unit"]["crosswalk_link"], 4)
        self.assertEqual(inventory["public_open_review_only_artifacts"], 27)
        self.assertFalse(bundle.ledger["scope"]["global_completeness_claimed"])
        self.assertFalse(bundle.ledger["scope"]["benchmark_parity_claimed"])
        self.assertFalse(bundle.ledger["scope"]["cross_artifact_counts_are_additive"])
        self.assertIsNone(bundle.ledger["scope"]["unique_physical_site_count"])
        benchmark_gap = next(
            gap
            for gap in bundle.ledger["parity_gaps"]
            if gap["gap_id"] == "benchmark-parity-not-computed"
        )
        self.assertEqual(benchmark_gap["status"], "not_computed")
        self.assertIn("SemiAnalysis", benchmark_gap["summary"])

    def test_timestamps_and_paix_pentapoint_v56_are_fail_closed(self) -> None:
        generated_at = datetime.fromisoformat(V18_GENERATED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(generated_at, datetime.now(UTC))
        module = _implementation_module()
        for _label, (_path, _field, expected) in module._SOURCE_TIMESTAMPS.items():
            source_time = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            self.assertLessEqual(source_time, generated_at)

        rendered = DEFINITION.read_text().lower()
        for forbidden in (
            "paix",
            "pentapoint",
            "open-seed-2026-07-20-v56",
            "seed-epoch-official-v56",
            "construction-map-public-open-v22",
            "construction-master-public-open-v22",
            "coverage-audit-public-open-v22",
            "federation-public-open-v23",
            "seed-epoch-official-v49",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_definition_generation_is_order_independent_and_collision_safe(
        self,
    ) -> None:
        canonical = make_v18_definition(ROOT)
        self.assertEqual(canonical, DEFINITION.read_bytes())
        module = _implementation_module()
        base_definition, base_ledger, base_manifest = module._load_v17_base(ROOT)
        shuffled = deepcopy(base_definition)
        shuffled["entries"] = list(reversed(shuffled["entries"]))
        with patch.object(
            module,
            "_load_v17_base",
            return_value=(shuffled, base_ledger, base_manifest),
        ):
            self.assertEqual(module.make_v18_definition(ROOT), canonical)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "definition.json"
            self.assertEqual(write_v18_definition(ROOT, destination), DEFINITION_SHA256)
            self.assertEqual(destination.read_bytes(), canonical)
            with self.assertRaisesRegex(
                CurrentCoverageV18Error, "refusing existing output"
            ):
                write_v18_definition(ROOT, destination)
            dangling = root / "dangling.json"
            dangling.symlink_to(root / "absent.json")
            with self.assertRaisesRegex(
                CurrentCoverageV18Error, "refusing existing output"
            ):
                write_v18_definition(ROOT, dangling)
            self.assertTrue(dangling.is_symlink())

    def test_definition_input_and_tree_mutations_fail_closed(self) -> None:
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
        identity = next(
            row
            for row in changed["entries"]
            if row["artifact_id"] == "exact-identity-decisions-public-open-v2"
        )
        identity["evidence_scope"] = "review_only"
        mutations.append(changed)
        changed = deepcopy(document)
        changed["base_ledger"]["ledger"]["sha256"] = "0" * 64
        mutations.append(changed)

        for mutation in mutations:
            mutation_raw = _canonical_json(mutation)

            def changed_read(path: Path, label: str) -> bytes:
                if Path(path).resolve() == DEFINITION.resolve():
                    return mutation_raw
                return original_read(path, label)

            with patch.object(module, "_read_regular", side_effect=changed_read):
                with self.assertRaises(CurrentCoverageV18Error):
                    build_current_coverage_ledger_v18(DEFINITION)

        seed_manifest = ROOT / "releases/2026-07-20-open-seed-v55/manifest.json"

        def changed_input(path: Path, label: str) -> bytes:
            raw = original_read(path, label)
            if Path(path).resolve() == seed_manifest.resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_input):
            with self.assertRaisesRegex(
                CurrentCoverageV18Error, "official seed v55 manifest changed"
            ):
                build_current_coverage_ledger_v18(DEFINITION)

        original_tree = module._v14._tree_digest

        def changed_tree(path: Path, label: str):
            files, directories, digest = original_tree(path, label)
            if "exact-identity-decisions-v2" in label:
                files += 1
            return files, directories, digest

        with patch.object(module._v14, "_tree_digest", side_effect=changed_tree):
            with self.assertRaisesRegex(
                CurrentCoverageV18Error,
                "exact-identity-decisions-v2 closed tree changed",
            ):
                build_current_coverage_ledger_v18(DEFINITION)

    def test_writer_refuses_collisions_lock_unfrozen_and_cleans_faults(self) -> None:
        module = _implementation_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "fresh"
            write_current_coverage_ledger_v18(DEFINITION, destination, freeze=True)
            try:
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
                validate_current_coverage_ledger_v18(
                    destination, definition_path=DEFINITION
                )
                with self.assertRaisesRegex(
                    CurrentCoverageV18Error, "refusing existing output"
                ):
                    write_current_coverage_ledger_v18(DEFINITION, destination)
            finally:
                _make_writable(destination)

            with self.assertRaisesRegex(
                CurrentCoverageV18Error, "requires freeze=True"
            ):
                write_current_coverage_ledger_v18(
                    DEFINITION, root / "unfrozen", freeze=False
                )
            locked = root / "locked"
            (root / ".locked.lock").write_text("owned\n")
            with self.assertRaisesRegex(CurrentCoverageV18Error, "active output lock"):
                write_current_coverage_ledger_v18(DEFINITION, locked)

            late = root / "late"
            original_promote = module._promote_noreplace

            def late_promote(stage: Path, target: Path) -> None:
                target.mkdir()
                original_promote(stage, target)

            with patch.object(module, "_promote_noreplace", side_effect=late_promote):
                with self.assertRaisesRegex(
                    CurrentCoverageV18Error, "late output collision"
                ):
                    write_current_coverage_ledger_v18(DEFINITION, late)

            failed = root / "fault"
            original_write = module._write_file
            calls = 0

            def fail_second_write(path: Path, raw: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected write fault")
                original_write(path, raw)

            with patch.object(module, "_write_file", side_effect=fail_second_write):
                with self.assertRaisesRegex(OSError, "injected write fault"):
                    write_current_coverage_ledger_v18(DEFINITION, failed)
            self.assertFalse(failed.exists())
            self.assertFalse((root / ".fault.lock").exists())
            self.assertFalse(
                any(path.name.startswith(".fault.") for path in root.iterdir())
            )

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
            timeout=90,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "artifacts": 47,
                "ledger_id": V18_LEDGER_ID,
                "output": str(BUNDLE),
                "validated": True,
            },
        )

        code = (
            "from datacenter_atlas.current_coverage_v18 import "
            "validate_current_coverage_ledger_v18 as validate; "
            f"m=validate({str(BUNDLE)!r}, definition_path={str(DEFINITION)!r}); "
            "print(m['ledger_id'], len(m['input_checkpoints']))"
        )
        for cwd, pythonpath in ((WORKSPACE, WORKSPACE), (ROOT, ROOT)):
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(pythonpath)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"{V18_LEDGER_ID} 47")

    def test_v17_history_remains_byte_identical(self) -> None:
        before = {path: _checkpoint(path) for path in BASE_PINS}
        build_current_coverage_ledger_v18(DEFINITION)
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
