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

from datacenter_atlas.current_coverage_v15 import (
    ARTIFACT_REPLACEMENTS,
    BUNDLE_FILES,
    CurrentCoverageV15Error,
    REMOVED_ARTIFACT_IDS,
    REPLACEMENT_ARTIFACT_IDS,
    V14_BASE_LINEAGE,
    V15_DEFINITION_SHA256,
    V15_LEDGER_ID,
    build_current_coverage_ledger_v15,
    make_v15_definition,
    validate_current_coverage_ledger_v15,
    write_current_coverage_ledger_v15,
    write_v15_definition,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v15.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v14.json"
V46_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v46.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v15"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v14"

DEFINITION_SHA256 = "ec5ad556c422a5f184c818d8aaca858a8c6ec75ec77318461802301bd4ff54bd"
LEDGER_SHA256 = "acfd2969f7d9ab2faf258abfef97a6a5d254f1a3294f57221d9c7c2fe4b72198"
MANIFEST_SHA256 = "e43aec4405486b1c53870f6b1b6d116ed62885d18e4aed553fd47adcf8e19e47"
SIDECAR_SHA256 = "017258cc72b521a7b1c3c582d73505f860163fe9e3c13de9559b82d69e7d1112"
UNCHANGED_43_SHA256 = "03775eeb2327c1764d5ec88874710bee74925dd5e1ddd506e8edc2815e54e4d5"
NEW_ENTRY_SHA256 = "152c7f7ce322dd3790f1c095b0dfd26c7d1cf4f86928f1b60c642bf66256acd2"
ALL_ENTRIES_SHA256 = "636b4953b71d6995002e7e660f3362eb2df77443a94740744051a0ea566330a4"
PARITY_GAPS_SHA256 = "e81c7a6ee803028c4bffcd94daa9c4c37bb8c9c4a540fb0541ba005311614a77"

FILE_PINS = {
    ROOT / "datacenter_atlas/current_coverage_v15.py": (
        32_342,
        "216335c9a61b7775fad1df45c2d12039339fdb5e7c40b6078be33c0ace8cb298",
    ),
    ROOT / "current_coverage_v15.py": (
        150,
        "6203c3285dab960248a1a9c6ba30d0fe7618519fe9ade25e1f8964c5cff9291a",
    ),
    ROOT / "scripts/build_current_coverage_ledger_v15.py": (
        2_795,
        "e489c504c46e867e74bac830ad9679c1e010f1b3c0d4fffbdd16ce3e941d7efb",
    ),
    DEFINITION: (129_254, DEFINITION_SHA256),
    BUNDLE / "current-coverage-ledger.json": (89_210, LEDGER_SHA256),
    BUNDLE / "manifest.json": (24_814, MANIFEST_SHA256),
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
    return importlib.import_module(build_current_coverage_ledger_v15.__module__)


@contextmanager
def _offline_guard():
    blocked = AssertionError("v15 attempted network access")
    with patch.object(socket, "socket", side_effect=blocked), patch.object(
        socket, "create_connection", side_effect=blocked
    ), patch.object(socket, "getaddrinfo", side_effect=blocked), patch.object(
        socket, "gethostbyname", side_effect=blocked
    ):
        yield


class FrozenCurrentCoverageLedgerV15Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_and_validates_twice_offline(self) -> None:
        self.assertEqual(V15_DEFINITION_SHA256, DEFINITION_SHA256)
        for path, (expected_size, expected_sha256) in FILE_PINS.items():
            self.assertEqual(path.stat().st_size, expected_size, path)
            self.assertEqual(_sha256(path), expected_sha256, path)

        with _offline_guard():
            first = build_current_coverage_ledger_v15(DEFINITION)
            second = build_current_coverage_ledger_v15(DEFINITION)
            first_manifest = validate_current_coverage_ledger_v15(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger_v15(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], V15_LEDGER_ID)
        self.assertEqual(first_manifest["base_ledger"], V14_BASE_LINEAGE)
        self.assertEqual(len(first_manifest["input_checkpoints"]), 44)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_exactly_one_seed_replacement_with_43_unchanged(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        base_entries = _entry_map(base)
        entries = _entry_map(current)
        self.assertEqual(ARTIFACT_REPLACEMENTS, {
            "seed-epoch-official-v44": "seed-epoch-official-v46"
        })
        self.assertEqual(set(base_entries) - set(entries), REMOVED_ARTIFACT_IDS)
        self.assertEqual(set(entries) - set(base_entries), REPLACEMENT_ARTIFACT_IDS)
        self.assertEqual(len(entries), 44)

        unchanged_ids = sorted(set(base_entries) & set(entries))
        unchanged = [entries[artifact_id] for artifact_id in unchanged_ids]
        self.assertEqual(len(unchanged), 43)
        for artifact_id in unchanged_ids:
            self.assertEqual(entries[artifact_id], base_entries[artifact_id])
        self.assertEqual(_component_digest(unchanged), UNCHANGED_43_SHA256)

        new_entry = entries["seed-epoch-official-v46"]
        ordered = [entries[artifact_id] for artifact_id in sorted(entries)]
        self.assertEqual(_component_digest([new_entry]), NEW_ENTRY_SHA256)
        self.assertEqual(_component_digest(ordered), ALL_ENTRIES_SHA256)
        self.assertEqual(
            hashlib.sha256(_canonical_line(current["parity_gaps"])).hexdigest(),
            PARITY_GAPS_SHA256,
        )

    def test_v46_metrics_inventory_scope_and_parity_remap_are_exact(self) -> None:
        current = json.loads(DEFINITION.read_text())
        base = json.loads(BASE_DEFINITION.read_text())
        entry = _entry_map(current)["seed-epoch-official-v46"]
        metrics = {row["label"]: row["value"] for row in entry["metrics"]}
        self.assertEqual(
            metrics,
            {
                "capacity_observations": 451,
                "construction_pipeline_records": 317,
                "construction_source_signals": 223,
                "evidence_records": 329,
                "resolution_candidates": 4,
                "source_scoped_entity_rows": 603,
            },
        )
        limitations = " ".join(entry["limitations"])
        self.assertIn(
            "603 source-scoped entity rows comprise 324 campus observations and 279 project observations",
            limitations,
        )

        base_gaps = deepcopy(base["parity_gaps"])
        expected_references = 0
        for gap in base_gaps:
            remapped = []
            for artifact_id in gap["affected_artifact_ids"]:
                if artifact_id == "seed-epoch-official-v44":
                    artifact_id = "seed-epoch-official-v46"
                    expected_references += 1
                remapped.append(artifact_id)
            gap["affected_artifact_ids"] = sorted(remapped)
        self.assertEqual(expected_references, 1)
        self.assertEqual(current["parity_gaps"], base_gaps)

        bundle = build_current_coverage_ledger_v15(DEFINITION)
        base_ledger = json.loads(
            (BASE_BUNDLE / "current-coverage-ledger.json").read_text()
        )
        self.assertEqual(
            bundle.ledger["artifact_inventory_counts"],
            base_ledger["artifact_inventory_counts"],
        )
        inventory = bundle.ledger["artifact_inventory_counts"]
        self.assertEqual(inventory["artifacts"], 44)
        self.assertEqual(
            inventory["by_access_tier"],
            {"local_restricted": 6, "public_open": 38},
        )
        self.assertEqual(inventory["public_open_review_only_artifacts"], 25)
        self.assertFalse(bundle.ledger["scope"]["global_completeness_claimed"])
        self.assertFalse(bundle.ledger["scope"]["benchmark_parity_claimed"])

    def test_v47_and_rejected_goodman_v2_inputs_do_not_leak(self) -> None:
        definition_text = DEFINITION.read_text(encoding="utf-8").lower()
        self.assertNotIn("seed-epoch-official-v47", definition_text)
        self.assertNotIn("open-seed-v47", definition_text)
        v46 = json.loads(V46_DEFINITION.read_text())
        curated_paths = [row["path"] for row in v46["curated_inputs"]]
        goodman = [path for path in curated_paths if "goodman-" in path]
        self.assertEqual(len(goodman), 10)
        self.assertTrue(all(not path.endswith("-v2.json") for path in goodman))
        self.assertTrue(all("open-seed-2026-07-20-v47" not in path for path in curated_paths))

        module = _implementation_module()
        original_read = module._read_regular

        def reject_unaccepted(path: Path, label: str) -> bytes:
            rendered = str(path).lower()
            self.assertNotIn("open-seed-v47", rendered)
            self.assertNotIn("goodman-", rendered)
            return original_read(path, label)

        with patch.object(module, "_read_regular", side_effect=reject_unaccepted):
            self.assertEqual(module.make_v15_definition(ROOT), DEFINITION.read_bytes())

    def test_historical_v43_satellite_lineage_is_byte_semantically_preserved(self) -> None:
        base_entries = _entry_map(json.loads(BASE_DEFINITION.read_text()))
        entries = _entry_map(json.loads(DEFINITION.read_text()))
        v43_ids = {
            "satellite-catalog-open-seed-v43-active-001",
            "satellite-catalog-reselection-open-seed-v43-active-v2-001",
            "satellite-queue-open-seed-v43",
        }
        for artifact_id in v43_ids:
            self.assertEqual(entries[artifact_id], base_entries[artifact_id])
            self.assertIn("v43", json.dumps(entries[artifact_id], sort_keys=True).lower())

    def test_definition_generation_is_order_independent_and_collision_safe(self) -> None:
        canonical = make_v15_definition(ROOT)
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
            self.assertEqual(module.make_v15_definition(ROOT), canonical)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "definition.json"
            self.assertEqual(write_v15_definition(ROOT, destination), DEFINITION_SHA256)
            self.assertEqual(destination.read_bytes(), canonical)
            self.assertFalse((destination.parent / ".definition.json.lock").exists())
            with self.assertRaisesRegex(CurrentCoverageV15Error, "refusing existing output"):
                write_v15_definition(ROOT, destination)

            dangling = root / "dangling.json"
            dangling.symlink_to(root / "absent.json")
            with self.assertRaisesRegex(CurrentCoverageV15Error, "refusing existing output"):
                write_v15_definition(ROOT, dangling)
            self.assertTrue(dangling.is_symlink())
            self.assertFalse((root / "absent.json").exists())

            raced = root / "raced.json"
            real_promote = module._promote_noreplace

            def inject_file_collision(stage: Path, target: Path) -> None:
                target.write_bytes(b"intruder\n")
                real_promote(stage, target)

            with patch.object(
                module, "_promote_noreplace", side_effect=inject_file_collision
            ):
                with self.assertRaisesRegex(
                    CurrentCoverageV15Error, "late output collision"
                ):
                    write_v15_definition(ROOT, raced)
            self.assertEqual(raced.read_bytes(), b"intruder\n")
            self.assertFalse((root / ".raced.json.lock").exists())
            self.assertFalse(list(root.glob(".raced.json.*.tmp")))

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
        changed = deepcopy(document)
        next(
            row
            for row in changed["entries"]
            if row["artifact_id"] == "seed-epoch-official-v46"
        )["metrics"][0]["value"] += 1
        mutations.append(changed)

        for mutation in mutations:
            mutation_raw = module._canonical_json(mutation)

            def changed_read(path: Path, label: str) -> bytes:
                if Path(path).resolve() == DEFINITION.resolve():
                    return mutation_raw
                return original_read(path, label)

            with patch.object(module, "_read_regular", side_effect=changed_read):
                with self.assertRaises(CurrentCoverageV15Error):
                    build_current_coverage_ledger_v15(DEFINITION)

        v46_manifest = ROOT / "releases/2026-07-20-open-seed-v46/manifest.json"

        def changed_input(path: Path, label: str) -> bytes:
            raw = original_read(path, label)
            if Path(path).resolve() == v46_manifest.resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_input):
            with self.assertRaisesRegex(CurrentCoverageV15Error, "v15 v46 manifest changed"):
                build_current_coverage_ledger_v15(DEFINITION)

    def test_writer_refuses_collisions_locks_late_races_and_unfrozen_output(self) -> None:
        module = _implementation_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "fresh"
            real_promote = module._promote_noreplace

            def assert_frozen_before_promotion(stage: Path, target: Path) -> None:
                self.assertTrue((root / ".fresh.lock").is_file())
                self.assertEqual(stat.S_IMODE(stage.stat().st_mode), 0o555)
                self.assertEqual({path.name for path in stage.iterdir()}, BUNDLE_FILES)
                self.assertTrue(
                    all(
                        stat.S_IMODE(path.stat().st_mode) == 0o444
                        for path in stage.iterdir()
                    )
                )
                real_promote(stage, target)

            with patch.object(
                module,
                "_promote_noreplace",
                side_effect=assert_frozen_before_promotion,
            ):
                write_current_coverage_ledger_v15(
                    DEFINITION, destination, freeze=True
                )
            try:
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o555)
                validate_current_coverage_ledger_v15(
                    destination, definition_path=DEFINITION
                )
                self.assertFalse((root / ".fresh.lock").exists())
                with self.assertRaisesRegex(CurrentCoverageV15Error, "refusing existing output"):
                    write_current_coverage_ledger_v15(DEFINITION, destination)
            finally:
                destination.chmod(0o755)
                for path in destination.iterdir():
                    path.chmod(0o644)

            with self.assertRaisesRegex(CurrentCoverageV15Error, "requires freeze=True"):
                write_current_coverage_ledger_v15(
                    DEFINITION, root / "unfrozen", freeze=False
                )

            locked = root / "locked"
            (root / ".locked.lock").write_text("owned\n")
            with self.assertRaisesRegex(CurrentCoverageV15Error, "active output lock"):
                write_current_coverage_ledger_v15(DEFINITION, locked)

            dangling = root / "dangling"
            dangling.symlink_to(root / "absent", target_is_directory=True)
            with self.assertRaisesRegex(CurrentCoverageV15Error, "refusing existing output"):
                write_current_coverage_ledger_v15(DEFINITION, dangling)
            self.assertTrue(dangling.is_symlink())
            self.assertFalse((root / "absent").exists())

            late = root / "late"
            original_write = module._write_file
            calls = 0

            def late_collision(path: Path, raw: bytes) -> None:
                nonlocal calls
                original_write(path, raw)
                calls += 1
                if calls == len(BUNDLE_FILES):
                    late.mkdir()

            with patch.object(module, "_write_file", side_effect=late_collision):
                with self.assertRaisesRegex(CurrentCoverageV15Error, "late output collision"):
                    write_current_coverage_ledger_v15(DEFINITION, late)
            self.assertTrue(late.is_dir())
            self.assertFalse((root / ".late.lock").exists())
            self.assertFalse(
                [path for path in root.iterdir() if path.name.startswith(".late.")]
            )

            atomic_late = root / "atomic-late"

            def inject_directory_collision(stage: Path, target: Path) -> None:
                target.mkdir()
                (target / "intruder.txt").write_text("intruder\n")
                real_promote(stage, target)

            with patch.object(
                module,
                "_promote_noreplace",
                side_effect=inject_directory_collision,
            ):
                with self.assertRaisesRegex(
                    CurrentCoverageV15Error, "late output collision"
                ):
                    write_current_coverage_ledger_v15(DEFINITION, atomic_late)
            self.assertEqual(
                (atomic_late / "intruder.txt").read_text(), "intruder\n"
            )
            self.assertFalse((root / ".atomic-late.lock").exists())
            self.assertFalse(
                [
                    path
                    for path in root.iterdir()
                    if path.name.startswith(".atomic-late.")
                ]
            )

    def test_v14_definition_and_bundle_remain_byte_stable(self) -> None:
        before = {path: path.read_bytes() for path in BASE_HASHES}
        for path, expected_sha256 in BASE_HASHES.items():
            self.assertEqual(_sha256(path), expected_sha256)
        module = _implementation_module()
        with _offline_guard():
            make_v15_definition(ROOT)
            build_current_coverage_ledger_v15(DEFINITION)
            base_built = module._v14.build_current_coverage_ledger_v14(BASE_DEFINITION)
            base_manifest = module._v14.validate_current_coverage_ledger_v14(
                BASE_BUNDLE, definition_path=BASE_DEFINITION
            )
        self.assertEqual(base_manifest["ledger_id"], "current-coverage-2026-07-20-v14")
        self.assertEqual(
            base_built.ledger_bytes,
            before[BASE_BUNDLE / "current-coverage-ledger.json"],
        )
        self.assertEqual(before, {path: path.read_bytes() for path in BASE_HASHES})

    def test_root_and_nested_import_layouts_and_cli_reproduce(self) -> None:
        code = "\n".join(
            [
                "import hashlib",
                "from datacenter_atlas.current_coverage_v15 import build_current_coverage_ledger_v15",
                f"bundle = build_current_coverage_ledger_v15({str(DEFINITION)!r})",
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

            cli = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_current_coverage_ledger_v15.py"),
                    "--validate-only",
                ],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                env=dict(os.environ),
            )
            result = json.loads(cli.stdout)
            self.assertEqual(result["ledger_id"], V15_LEDGER_ID)
            self.assertEqual(result["artifacts"], 44)
            self.assertTrue(result["validated"])


if __name__ == "__main__":
    unittest.main()
