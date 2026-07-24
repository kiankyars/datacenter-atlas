from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
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
    write_current_coverage_ledger,
)
ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v13.json"
BASE_DEFINITION = ROOT / "sources/current-coverage-2026-07-20-v12.json"
BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v13"
BASE_BUNDLE = ROOT / "current_coverage_ledgers/2026-07-20-v12"
BASE_LINEAGE = current_coverage_module._V13_BASE_LINEAGE
NEW_CONSTRUCTION_IDS = current_coverage_module._V13_NEW_CONSTRUCTION_IDS
OLD_CONSTRUCTION_IDS = current_coverage_module._V13_OLD_CONSTRUCTION_IDS
V16_CHECKPOINTS = current_coverage_module._V13_EXACT_CURRENT_CHECKPOINTS
V16_METRICS = current_coverage_module._V13_EXACT_METRICS

DEFINITION_SHA256 = "7e23abc7be3c6a3e898c640960912a308297bf02aee22b86638a66b350d19cc5"
LEDGER_SHA256 = "aabbc77b6fad657794b44e8eda6c833bccc694d863602ab8c7efaf79da49e0b7"
MANIFEST_SHA256 = "3ab86c29de2d7a6054a0ec3c941644a639ef89cba7fdf27614ff9ea170f9f034"
SIDECAR_SHA256 = "92cb408e7346fdbcae3a5dd3e70539b88dfcdfde987b255a34b0f0972d23b7f1"
BUNDLE_INVENTORY_SHA256 = "50b954028a163a3066b0ca3570d75b1aca6f25512a6efb8cd50055814d3e1f55"
UNCHANGED_39_SHA256 = "7fa2609112f14690558f3d64fa5dd001c28c2eca797decb977f83f8f52bb33de"
PARITY_GAPS_SHA256 = "22a1f795520f0ce6718bb72b420610e0dec6d40a8d96e56be691b316556a8a1b"
REPLACEMENT_ENTRY_SHA256 = {
    "construction-map-public-open-v16": (
        "14254fb1ac6780a85b0afaa0c85f8507000a3de26db4ff2bcb4a90f876b6c193"
    ),
    "construction-master-public-open-v16": (
        "ae7406eaef2ea947215118ba483109166aba319a6853e9611201e39e10406431"
    ),
}
BASE_HASHES = {
    BASE_DEFINITION: "f1f365a517179b2526911665161c76ff59865b6e4fd14fcddf3361f490a3a72a",
    BASE_BUNDLE / "current-coverage-ledger.json": (
        "ec93020a2794221961639b935003732568c10a5b4158143e7258a1d835d6a988"
    ),
    BASE_BUNDLE / "manifest.json": (
        "a7b5e3522c90301020db2d47fa6e1f10830f82524be559967df9aa18896ff412"
    ),
    BASE_BUNDLE / "manifest.sha256": (
        "5817b471338cc2005f2bbad98282c046a8dfeadc0d98c6bdabe55f774d59c6a5"
    ),
}

REJECTED_PATH_FRAGMENTS = (
    "sources/current-coverage-2026-07-20-v10.json",
    "current_coverage_ledgers/2026-07-20-v10",
    "sources/current-coverage-2026-07-20-v11.json",
    "current_coverage_ledgers/2026-07-20-v11",
    "construction_maps/2026-07-19-public-open-v14",
    "construction_master/2026-07-19-public-open-v14",
    "construction-map-2026-07-19-public-open-v14.json",
    "construction-master-2026-07-19-public-open-v14.json",
    "construction_maps/2026-07-20-public-open-v15",
    "construction_master/2026-07-20-public-open-v15",
    "construction-map-2026-07-20-public-open-v15.json",
    "construction-master-2026-07-20-public-open-v15.json",
    "construction_maps/2026-07-20-public-open-v18",
    "construction_master/2026-07-20-public-open-v18",
    "construction-map-2026-07-20-public-open-v18.json",
    "construction-master-2026-07-20-public-open-v18.json",
    "construction_map_v5.py",
    "construction-map-v5",
    "sources/open-seed-2026-07-20-v41.json",
    "releases/2026-07-20-open-seed-v41",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


def _entry_map(document: dict) -> dict[str, dict]:
    return {entry["artifact_id"]: entry for entry in document["entries"]}


def _replace_gap_ids(gaps: list[dict]) -> list[dict]:
    replacements = {
        "construction-map-public-open-v14": "construction-map-public-open-v16",
        "construction-master-public-open-v14": "construction-master-public-open-v16",
    }
    result = deepcopy(gaps)
    for gap in result:
        gap["affected_artifact_ids"] = [
            replacements.get(artifact_id, artifact_id)
            for artifact_id in gap["affected_artifact_ids"]
        ]
    return result


@contextmanager
def _offline_rejected_path_guard():
    original_read = current_coverage_module._regular_bytes
    paths_read: list[Path] = []

    def guarded_read(path: Path, label: str) -> bytes:
        normalized = Path(path).resolve().as_posix().lower()
        if any(fragment.lower() in normalized for fragment in REJECTED_PATH_FRAGMENTS):
            raise AssertionError(f"v13 attempted rejected path access: {path}")
        paths_read.append(Path(path))
        return original_read(path, label)

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


class FrozenCurrentCoverageLedgerV13Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_through_main_builder(self) -> None:
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(_sha256(BUNDLE / "current-coverage-ledger.json"), LEDGER_SHA256)
        self.assertEqual(_sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_sha256(BUNDLE / "manifest.sha256"), SIDECAR_SHA256)
        self.assertEqual(_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertLessEqual(
            datetime.fromisoformat("2026-07-20T06:51:51+00:00"),
            datetime.now(UTC),
        )

        with _offline_rejected_path_guard() as paths_read:
            first = build_current_coverage_ledger(DEFINITION)
            second = build_current_coverage_ledger(DEFINITION)
            first_manifest = validate_current_coverage_ledger(
                BUNDLE, definition_path=DEFINITION
            )
            second_manifest = validate_current_coverage_ledger(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertTrue(paths_read)
        self.assertEqual(first.ledger_bytes, second.ledger_bytes)
        self.assertEqual(first.manifest_bytes, second.manifest_bytes)
        self.assertEqual(first.manifest_hash_bytes, second.manifest_hash_bytes)
        self.assertEqual(first_manifest, second_manifest)
        self.assertEqual(first_manifest["ledger_id"], "current-coverage-2026-07-20-v13")
        self.assertEqual(len(first_manifest["input_checkpoints"]), 41)
        self.assertEqual(first_manifest["base_ledger"], BASE_LINEAGE)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in BUNDLE.iterdir())
        )

    def test_delta_is_exactly_two_entries_and_gap_id_references(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text())
        definition = json.loads(DEFINITION.read_text())
        base_entries = _entry_map(base_definition)
        entries = _entry_map(definition)
        self.assertEqual(set(base_entries) - set(entries), OLD_CONSTRUCTION_IDS)
        self.assertEqual(set(entries) - set(base_entries), NEW_CONSTRUCTION_IDS)

        inherited_ids = sorted(set(base_entries) - OLD_CONSTRUCTION_IDS)
        self.assertEqual(len(inherited_ids), 39)
        digest = hashlib.sha256()
        for artifact_id in inherited_ids:
            self.assertEqual(entries[artifact_id], base_entries[artifact_id])
            digest.update(_canonical_line(entries[artifact_id]))
        self.assertEqual(digest.hexdigest(), UNCHANGED_39_SHA256)

        expected_gaps = _replace_gap_ids(base_definition["parity_gaps"])
        self.assertEqual(definition["parity_gaps"], expected_gaps)
        self.assertEqual(
            hashlib.sha256(_canonical_line(definition["parity_gaps"])).hexdigest(),
            PARITY_GAPS_SHA256,
        )
        self.assertEqual(
            [(gap["gap_id"], gap["status"], gap["summary"]) for gap in expected_gaps],
            [
                (gap["gap_id"], gap["status"], gap["summary"])
                for gap in base_definition["parity_gaps"]
            ],
        )

        base_ledger = json.loads(
            (BASE_BUNDLE / "current-coverage-ledger.json").read_text()
        )
        ledger = json.loads((BUNDLE / "current-coverage-ledger.json").read_text())
        base_artifacts = {row["artifact_id"]: row for row in base_ledger["artifacts"]}
        artifacts = {row["artifact_id"]: row for row in ledger["artifacts"]}
        for artifact_id in inherited_ids:
            self.assertEqual(artifacts[artifact_id], base_artifacts[artifact_id])
        self.assertEqual(
            ledger["artifact_inventory_counts"],
            base_ledger["artifact_inventory_counts"],
        )

    def test_v16_lineage_hashes_metric_pointers_and_deltas_are_explicit(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        entries = _entry_map(definition)
        for artifact_id in sorted(NEW_CONSTRUCTION_IDS):
            entry = entries[artifact_id]
            self.assertEqual(
                hashlib.sha256(_canonical_line(entry)).hexdigest(),
                REPLACEMENT_ENTRY_SHA256[artifact_id],
            )
            checkpoints = {
                row["checkpoint_id"]: (row["path"], row["sha256"])
                for row in entry["checkpoints"]
            }
            metrics = {row["label"]: row["value"] for row in entry["metrics"]}
            self.assertEqual(checkpoints, V16_CHECKPOINTS[artifact_id])
            self.assertEqual(metrics, V16_METRICS[artifact_id])

        master_metrics = {
            row["label"]: (row["json_pointer"], row["value"])
            for row in entries["construction-master-public-open-v16"]["metrics"]
        }
        self.assertEqual(
            master_metrics["added_replacement_rows"],
            ("/replacement_invariants/added_replacement_rows", 63),
        )
        self.assertEqual(
            master_metrics["base_rows"],
            ("/replacement_invariants/base_rows", 109_111),
        )
        self.assertEqual(
            master_metrics["unchanged_replacement_rows"],
            ("/replacement_invariants/unchanged_replacement_rows", 199),
        )
        map_metrics = {
            row["label"]: (row["json_pointer"], row["value"])
            for row in entries["construction-map-public-open-v16"]["metrics"]
        }
        self.assertEqual(
            map_metrics["added_replacement_rows_unmapped"],
            ("/projection/added_replacement_rows_unmapped", 63),
        )

        base_ledger = json.loads(
            (BASE_BUNDLE / "current-coverage-ledger.json").read_text()
        )
        ledger = json.loads((BUNDLE / "current-coverage-ledger.json").read_text())
        base_artifacts = {row["artifact_id"]: row for row in base_ledger["artifacts"]}
        artifacts = {row["artifact_id"]: row for row in ledger["artifacts"]}
        base_map = base_artifacts["construction-map-public-open-v14"]["reported_metrics"]
        current_map = artifacts["construction-map-public-open-v16"]["reported_metrics"]
        base_master = base_artifacts["construction-master-public-open-v14"][
            "reported_metrics"
        ]
        current_master = artifacts["construction-master-public-open-v16"][
            "reported_metrics"
        ]
        self.assertEqual(current_master["total_master_rows"] - base_master["total_master_rows"], 63)
        self.assertEqual(current_map["master_total_rows"] - base_map["master_total_rows"], 63)
        self.assertEqual(current_map["unmapped_rows"] - base_map["unmapped_rows"], 63)
        self.assertEqual(current_map["mapped_total_rows"], base_map["mapped_total_rows"])

        documents = {
            label: json.loads((ROOT / relative).read_text())
            for label, (relative, _bytes, _sha256_value) in (
                current_coverage_module._V13_EXACT_FILES.items()
            )
        }
        current_coverage_module._validate_v13_publication_contract(ROOT)
        self.assertEqual(
            documents["construction-master definition"]["expected"],
            documents["construction-master coverage"]["replacement_invariants"],
        )
        self.assertEqual(
            documents["construction-map definition"]["expected_projection"],
            documents["construction-map coverage"]["projection"],
        )
        self.assertTrue(current_coverage_module._is_exact_v4_publication_marker(4))
        for marker in (3, 4.0, True, "4", None):
            self.assertFalse(
                current_coverage_module._is_exact_v4_publication_marker(marker)
            )

    def test_definition_mutations_fail_closed(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        mutations = []

        changed = deepcopy(definition)
        changed["generated_at"] = "2026-07-20T06:51:52Z"
        mutations.append(changed)
        changed = deepcopy(definition)
        changed["base_ledger"]["ledger"]["sha256"] = "0" * 64
        mutations.append(changed)
        changed = deepcopy(definition)
        changed["scope"]["global_completeness_claimed"] = True
        mutations.append(changed)
        changed = deepcopy(definition)
        next(
            row
            for row in changed["entries"]
            if row["artifact_id"] == "construction-map-public-open-v16"
        )["metrics"][0]["value"] = 62
        mutations.append(changed)
        changed = deepcopy(definition)
        next(
            row
            for row in changed["entries"]
            if row["artifact_id"] == "construction-master-public-open-v16"
        )["metrics"][0]["json_pointer"] = "/replacement_invariants/base_rows"
        mutations.append(changed)
        changed = deepcopy(definition)
        next(
            row for row in changed["entries"] if row["artifact_id"] == "global-open-v3"
        )["limitations"].append("drift")
        mutations.append(changed)
        changed = deepcopy(definition)
        changed["parity_gaps"][0]["summary"] += " drift"
        mutations.append(changed)
        changed = deepcopy(definition)
        changed["unexpected"] = True
        mutations.append(changed)

        for document in mutations:
            raw = current_coverage_module._canonical_json(document)
            with self.assertRaises(CurrentCoverageError):
                current_coverage_module._validate_v13_definition_contract(
                    document, raw, ROOT
                )

    def test_main_writer_collision_and_freeze_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(CurrentCoverageError, "refusing existing output"):
                write_current_coverage_ledger(DEFINITION, existing, freeze=True)

            fresh = root / "fresh"
            write_current_coverage_ledger(DEFINITION, fresh, freeze=True)
            try:
                self.assertEqual(stat.S_IMODE(fresh.stat().st_mode), 0o555)
                self.assertTrue(
                    all(
                        stat.S_IMODE(path.stat().st_mode) == 0o444
                        for path in fresh.iterdir()
                    )
                )
                validate_current_coverage_ledger(fresh, definition_path=DEFINITION)
                with self.assertRaisesRegex(
                    CurrentCoverageError, "refusing existing output"
                ):
                    write_current_coverage_ledger(DEFINITION, fresh, freeze=True)
            finally:
                fresh.chmod(0o755)
                for path in fresh.iterdir():
                    path.chmod(0o644)

    def test_accepted_v12_bytes_and_generic_reproduction_are_stable(self) -> None:
        before = {path: path.read_bytes() for path in BASE_HASHES}
        for path, expected_sha256 in BASE_HASHES.items():
            self.assertEqual(hashlib.sha256(before[path]).hexdigest(), expected_sha256)
        self.assertEqual(stat.S_IMODE(BASE_BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in BASE_BUNDLE.iterdir()
            )
        )

        built = build_current_coverage_ledger(BASE_DEFINITION)
        manifest = validate_current_coverage_ledger(
            BASE_BUNDLE, definition_path=BASE_DEFINITION
        )
        self.assertEqual(built.ledger_bytes, before[BASE_BUNDLE / "current-coverage-ledger.json"])
        self.assertEqual(built.manifest_bytes, before[BASE_BUNDLE / "manifest.json"])
        self.assertEqual(manifest["ledger_id"], "current-coverage-2026-07-20-v12")
        self.assertEqual(before, {path: path.read_bytes() for path in BASE_HASHES})


if __name__ == "__main__":
    unittest.main()
