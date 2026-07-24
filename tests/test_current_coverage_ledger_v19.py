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

from datacenter_atlas.current_coverage_v19 import (
    ADDED_ARTIFACT_IDS,
    ALL_ENTRIES_SHA256,
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    CurrentCoverageV19Error,
    PARITY_GAPS_SHA256,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_7_SHA256,
    REPLACEMENT_ARTIFACT_IDS,
    UNCHANGED_40_SHA256,
    V18_BASE_LINEAGE,
    V19_DEFINITION_SHA256,
    V19_GENERATED_AT,
    V19_LEDGER_ID,
    build_current_coverage_ledger_v19,
    make_v19_definition,
    validate_current_coverage_ledger_v19,
    write_current_coverage_ledger_v19,
    write_v19_definition,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v19.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v18.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v19"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v18"
SCRIPT = ROOT / "scripts/build_current_coverage_ledger_v19.py"

DEFINITION_SHA256 = "6ffd11fdeab77cb92c9c820c917f0a0e02f68c417907b70aec8059fbae9dee04"
LEDGER_SHA256 = "143dacb68947f1d6483a47da1ebd294648a40d0ca2aab2deba078ec36fbd124a"
MANIFEST_SHA256 = "bcfe53a5a23e3c8dbca40feb646cfff93abd24614a60382266dd830376074f42"
SIDECAR_SHA256 = "79ff81352c85ae188d5ecd2d9390e1f6a29905452ed60dbdc3bbeef05fcdc5c6"
V19_TREE_SHA256 = "33d455ae9ce493dffdc11a5121cfc222800bc516dba37877434f7545b4365a3e"

FILE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v19.py": (
        55_568,
        "ea6f08c025727d5702f20e6d7c195cd56881fd4fd2861f3f8ce75bb6d39bb378",
    ),
    ROOT / "current_coverage_v19.py": (
        150,
        "5d66572dc18aa43dd6ebe68c20d7316032059100b449916353c7f27c2bf91e8e",
    ),
    SCRIPT: (
        2_781,
        "6b1a6f9f304532b4ed06a93ed8d8b99590b2ea2f215b0047261d9fab6f48a0b8",
    ),
    DEFINITION: (142_460, DEFINITION_SHA256),
    BUNDLE / "current-coverage-ledger.json": (98_188, LEDGER_SHA256),
    BUNDLE / "manifest.json": (27_429, MANIFEST_SHA256),
    BUNDLE / "manifest.sha256": (80, SIDECAR_SHA256),
}

BASE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v18.py": (
        62_454,
        "82c2e03a19dbb3253a44e80cdd6279a6c73f20037f3d22ca004330897a974ace",
    ),
    ROOT / "current_coverage_v18.py": (
        150,
        "b516ac0a032f163c27c0f258cefbe18309b05903389ee1a8654acbc7f1f1de5e",
    ),
    BASE_DEFINITION: (
        142_381,
        "d8e151cb9b9f38349c5a462a31d91ec70776d5bd25d0228becffb8f0d7546e8c",
    ),
    BASE_BUNDLE / "current-coverage-ledger.json": (
        98_109,
        "a1c1e6f680db43c7b571bb94846315f756c918b58e2eea31853ef2e6c1740f01",
    ),
    BASE_BUNDLE / "manifest.json": (
        27_414,
        "a3fdc74b36ce33f6959c436ecb34f6171614a0e96d8a4f9a8140db9f33a5d2f4",
    ),
    BASE_BUNDLE / "manifest.sha256": (
        80,
        "c127cf61d6f889162ca0a11ae12beb950be5fdd00d2a7daf13257bbd74baef96",
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
    return importlib.import_module(build_current_coverage_ledger_v19.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v19 attempted network access")
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


class FrozenCurrentCoverageLedgerV19Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_and_pins_v18(self) -> None:
        self.assertEqual(V19_DEFINITION_SHA256, DEFINITION_SHA256)
        for path, expected in {**FILE_PINS, **BASE_PINS}.items():
            self.assertEqual(_checkpoint(path), expected, path)

        module = _implementation_module()
        with _offline_guard():
            module._v18.validate_current_coverage_ledger_v18(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
            first = build_current_coverage_ledger_v19(DEFINITION)
            second = build_current_coverage_ledger_v19(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v19(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v19(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V19_LEDGER_ID)
        self.assertEqual(first_manifest["base_ledger"], V18_BASE_LINEAGE)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 47)
        self.assertEqual(
            module._v14._tree_digest(BUNDLE, "v19 bundle"),
            (3, 1, V19_TREE_SHA256),
        )
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_exactly_40_inherited_and_seven_replacements(self) -> None:
        base_entries = _entry_map(json.loads(BASE_DEFINITION.read_text()))
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        self.assertEqual(
            ARTIFACT_REPLACEMENTS,
            {
                "construction-map-public-open-v23": "construction-map-public-open-v24",
                "construction-master-public-open-v23": "construction-master-public-open-v24",
                "coverage-audit-public-open-v23": "coverage-audit-public-open-v24",
                "exact-identity-decisions-public-open-v2": "exact-identity-decisions-public-open-v3",
                "federation-public-open-v24": "federation-public-open-v25",
                "satellite-change-review-open-seed-v55-active-review-v1": "satellite-change-review-open-seed-v56-active-review-v1",
                "seed-epoch-official-v55": "seed-epoch-official-v56",
            },
        )
        self.assertEqual(ADDED_ARTIFACT_IDS, set())
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(set(entries) - set(base_entries), REPLACEMENT_ARTIFACT_IDS)
        self.assertEqual(len(entries), 47)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        replacements = [
            entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
        ]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual((len(unchanged), len(replacements)), (40, 7))
        for artifact_id in unchanged_ids:
            self.assertEqual(
                _canonical_line(entries[artifact_id]),
                _canonical_line(base_entries[artifact_id]),
            )
        self.assertEqual(_component_digest(unchanged), UNCHANGED_40_SHA256)
        self.assertEqual(_component_digest(replacements), REPLACEMENT_7_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        self.assertEqual(
            hashlib.sha256(
                _canonical_line(json.loads(DEFINITION.read_text())["parity_gaps"])
            ).hexdigest(),
            PARITY_GAPS_SHA256,
        )

    def test_retained_resolution_and_v43_review_are_byte_exact(self) -> None:
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

    def test_identity_is_authoritative_nonadditive_and_review_is_review_only(
        self,
    ) -> None:
        definition_entries = _entry_map(json.loads(DEFINITION.read_text()))
        ledger_entries = {
            row["artifact_id"]: row
            for row in json.loads(
                (BUNDLE / "current-coverage-ledger.json").read_text()
            )["artifacts"]
        }
        identity_id = "exact-identity-decisions-public-open-v3"
        identity = definition_entries[identity_id]
        self.assertEqual(identity["artifact_kind"], "cross_release_resolution")
        self.assertEqual(identity["current_role"], "authoritative_public_core")
        self.assertEqual(identity["evidence_scope"], "source_scoped")
        self.assertEqual(identity["record_units"], ["crosswalk_link"])
        self.assertFalse(ledger_entries[identity_id]["review_only"])
        identity_metrics = {row["label"]: row["value"] for row in identity["metrics"]}
        self.assertEqual(identity_metrics["exact_source_record_components"], 8_230)
        self.assertEqual(identity_metrics["exact_component_reductions"], 1_732)
        self.assertEqual(identity_metrics["canonical_topology_links"], 2_317)
        self.assertEqual(identity_metrics["raw_topology_links"], 2_722)
        self.assertIsNone(identity_metrics["unique_physical_sites"])
        self.assertIn("non-additive", " ".join(identity["limitations"]).lower())

        review_id = "satellite-change-review-open-seed-v56-active-review-v1"
        review = definition_entries[review_id]
        self.assertEqual(review["artifact_kind"], "analyst_imagery_review")
        self.assertEqual(review["current_role"], "public_supporting_review_lane")
        self.assertEqual(review["evidence_scope"], "review_only")
        self.assertTrue(ledger_entries[review_id]["review_only"])
        review_metrics = {row["label"]: row["value"] for row in review["metrics"]}
        self.assertEqual(review_metrics["review_decisions"], 6)
        self.assertEqual(review_metrics["site_aligned_follow_up_retained"], 3)
        self.assertEqual(review_metrics["site_promotion_rejections"], 3)
        self.assertEqual(review_metrics["source_artifacts_hash_bound"], 36)
        self.assertEqual(review_metrics["technical_multitile_failures"], 1)
        self.assertFalse(review_metrics["capacity_claim_created"])
        self.assertFalse(review_metrics["site_count_claim_created"])

        artifact_ids = set(definition_entries)
        self.assertFalse(
            any(
                token in artifact_id
                for artifact_id in artifact_ids
                for token in (
                    "satellite-review-queue-open-seed-v56",
                    "satellite-catalog-open-seed-v56",
                    "active-runtime-retry-001",
                    "no-raster",
                )
            )
        )

    def test_successor_metrics_and_limitations_are_live_exact(self) -> None:
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        expected_metrics = {
            "seed-epoch-official-v56": {
                "capacity_observations": 484,
                "construction_pipeline_records": 348,
                "construction_source_signals": 254,
                "evidence_records": 388,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 667,
            },
            "federation-public-open-v25": {
                "capacity_observations": 1_270,
                "construction_pipeline_records": 6_598,
                "non_review_construction_pipeline_records": 468,
                "non_review_source_scoped_rows": 9_962,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 16_092,
                "unique_physical_sites": None,
            },
            "coverage-audit-public-open-v24": {
                "coverage_groups": 679,
                "non_review_source_scoped_rows": 9_962,
                "open_gaps": 3_452,
                "review_only_source_scoped_rows": 6_130,
                "source_scoped_rows": 16_092,
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
            for row in entries["construction-master-public-open-v24"]["metrics"]
        }
        self.assertEqual(master["total_master_rows"], 109_260)
        self.assertEqual(master["tier_a_rows"], 468)
        self.assertEqual(master["added_replacement_rows"], 149)
        self.assertEqual(master["replacement_rows"], 348)
        self.assertEqual(master["role_rows_with_any_role"], 126)
        self.assertIsNone(master["unique_physical_sites"])
        map_metrics = {
            row["label"]: row["value"]
            for row in entries["construction-map-public-open-v24"]["metrics"]
        }
        self.assertEqual(map_metrics["mapped_total_rows"], 108_980)
        self.assertEqual(map_metrics["unmapped_rows"], 280)
        self.assertEqual(map_metrics["mapped_replacement_rows"], 87)
        self.assertEqual(map_metrics["default_visible_rows"], 6_486)
        self.assertIsNone(map_metrics["unique_physical_sites"])

        limitations = " ".join(
            limitation
            for artifact_id in REPLACEMENT_ARTIFACT_IDS
            for limitation in entries[artifact_id]["limitations"]
        ).lower()
        for phrase in (
            "not unique physical sites",
            "historical lifecycle statuses",
            "not globally additive",
            "not all confirmed construction sites",
            "not a model result",
        ):
            self.assertIn(phrase, limitations)

    def test_parity_ids_advance_with_summaries_and_inventory_unchanged(self) -> None:
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

        base_ledger = json.loads(
            (BASE_BUNDLE / "current-coverage-ledger.json").read_text()
        )
        current_ledger = json.loads(
            (BUNDLE / "current-coverage-ledger.json").read_text()
        )
        self.assertEqual(
            current_ledger["artifact_inventory_counts"],
            base_ledger["artifact_inventory_counts"],
        )
        self.assertFalse(current_ledger["scope"]["global_completeness_claimed"])
        self.assertFalse(current_ledger["scope"]["benchmark_parity_claimed"])
        self.assertFalse(current_ledger["scope"]["cross_artifact_counts_are_additive"])
        self.assertIsNone(current_ledger["scope"]["unique_physical_site_count"])
        benchmark_gap = next(
            gap
            for gap in current_ledger["parity_gaps"]
            if gap["gap_id"] == "benchmark-parity-not-computed"
        )
        self.assertEqual(benchmark_gap["status"], "not_computed")
        self.assertIn("SemiAnalysis", benchmark_gap["summary"])

    def test_timestamps_exclusions_and_input_mutations_fail_closed(self) -> None:
        generated_at = datetime.fromisoformat(V19_GENERATED_AT.replace("Z", "+00:00"))
        self.assertLessEqual(generated_at, datetime.now(UTC))
        module = _implementation_module()
        for _label, (_path, _field, expected) in module._SOURCE_TIMESTAMPS.items():
            source_time = datetime.fromisoformat(expected.replace("Z", "+00:00"))
            self.assertLessEqual(source_time, generated_at)

        rendered = DEFINITION.read_text()
        for forbidden in (
            *REMOVED_ARTIFACT_IDS,
            "curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json",
            "curated-official-2026-07-20-aligned-iad06-frederick-topout.json",
        ):
            self.assertNotIn(forbidden, rendered)

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
            mutation_raw = _canonical_json(mutation)

            def changed_read(path: Path, label: str) -> bytes:
                if Path(path).resolve() == DEFINITION.resolve():
                    return mutation_raw
                return original_read(path, label)

            with patch.object(module, "_read_regular", side_effect=changed_read):
                with self.assertRaises(CurrentCoverageV19Error):
                    build_current_coverage_ledger_v19(DEFINITION)

        seed_manifest = ROOT / "releases/2026-07-20-open-seed-v56/manifest.json"

        def changed_input(path: Path, label: str) -> bytes:
            raw = original_read(path, label)
            if Path(path).resolve() == seed_manifest.resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_input):
            with self.assertRaisesRegex(
                CurrentCoverageV19Error, "official seed v56 manifest changed"
            ):
                build_current_coverage_ledger_v19(DEFINITION)

        original_tree = module._v14._tree_digest

        def changed_tree(path: Path, label: str):
            files, directories, digest = original_tree(path, label)
            if "exact-identity-decisions-v3" in label:
                files += 1
            return files, directories, digest

        with patch.object(module._v14, "_tree_digest", side_effect=changed_tree):
            with self.assertRaisesRegex(
                CurrentCoverageV19Error,
                "exact-identity-decisions-v3 closed tree changed",
            ):
                build_current_coverage_ledger_v19(DEFINITION)

    def test_generation_order_collisions_lock_and_unfrozen_fail_closed(self) -> None:
        canonical = make_v19_definition(ROOT)
        self.assertEqual(canonical, DEFINITION.read_bytes())
        module = _implementation_module()
        base_definition, base_ledger, base_manifest = module._load_v18_base(ROOT)
        shuffled = deepcopy(base_definition)
        shuffled["entries"] = list(reversed(shuffled["entries"]))
        with patch.object(
            module,
            "_load_v18_base",
            return_value=(shuffled, base_ledger, base_manifest),
        ):
            self.assertEqual(module.make_v19_definition(ROOT), canonical)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            definition = root / "definition.json"
            self.assertEqual(write_v19_definition(ROOT, definition), DEFINITION_SHA256)
            self.assertEqual(definition.read_bytes(), canonical)
            with self.assertRaisesRegex(
                CurrentCoverageV19Error, "refusing existing output"
            ):
                write_v19_definition(ROOT, definition)

            destination = root / "fresh"
            write_current_coverage_ledger_v19(DEFINITION, destination, freeze=True)
            try:
                validate_current_coverage_ledger_v19(
                    destination, definition_path=DEFINITION
                )
                with self.assertRaisesRegex(
                    CurrentCoverageV19Error, "refusing existing output"
                ):
                    write_current_coverage_ledger_v19(DEFINITION, destination)
            finally:
                _make_writable(destination)

            with self.assertRaisesRegex(
                CurrentCoverageV19Error, "requires freeze=True"
            ):
                write_current_coverage_ledger_v19(
                    DEFINITION, root / "unfrozen", freeze=False
                )
            locked = root / "locked"
            (root / ".locked.lock").write_text("owned\n")
            with self.assertRaisesRegex(CurrentCoverageV19Error, "active output lock"):
                write_current_coverage_ledger_v19(DEFINITION, locked)

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
            timeout=120,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "artifacts": 47,
                "ledger_id": V19_LEDGER_ID,
                "output": str(BUNDLE),
                "validated": True,
            },
        )

        code = (
            "from datacenter_atlas.current_coverage_v19 import "
            "validate_current_coverage_ledger_v19 as validate; "
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
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"{V19_LEDGER_ID} 47")

    def test_v18_history_remains_byte_identical(self) -> None:
        before = {path: _checkpoint(path) for path in BASE_PINS}
        build_current_coverage_ledger_v19(DEFINITION)
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
