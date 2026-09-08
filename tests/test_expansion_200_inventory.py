"""Stdlib fixtures and portable snapshot tests; v97 is optional, not vendored."""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import timedelta
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "expansion_200_inventory", ROOT / "scripts/build_expansion_200_inventory.py"
)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inventory
SPEC.loader.exec_module(inventory)


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode()


class FixtureInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.baseline = self.root / inventory.BASELINE_DIR
        self.baseline.mkdir(parents=True)
        tables = {
            "projects.csv": [{"project_stable_key": "selected", "physical_site_stable_key": "campus-existing"}],
            "sites.csv": [{"physical_site_stable_key": "campus-existing"}],
        }
        files = {}
        for name, rows in tables.items():
            raw = csv_bytes(rows)
            (self.baseline / name).write_bytes(raw)
            files[name] = {"sha256": inventory.sha256(raw), "bytes": len(raw)}
        manifest = inventory.json_bytes({"counts": {"projects": 1, "physical_sites": 1}, "files": files})
        (self.baseline / "manifest.json").write_bytes(manifest)
        self.rows = [
            self.row("selected", "2020-01-01"),
            self.row("a1"), self.row("a2"), self.row("existing"),
            self.row("stale", "2025-08-20"), self.row("planned", status="planned"),
            self.row("unresolved"), self.row("campus", entity_kind="campus"),
        ]
        pipeline = self.root / inventory.PIPELINE_PATH
        pipeline.parent.mkdir(parents=True)
        raw = csv_bytes(self.rows)
        pipeline.write_bytes(raw)
        self.pins = inventory.InputPins(
            pipeline_sha256=inventory.sha256(raw),
            baseline_manifest_sha256=inventory.sha256(manifest),
            baseline_projects=1, baseline_sites=1, pipeline_rows=8,
            pipeline_nonprojects=1, selected_pipeline_projects=1,
        )
        for key, parent in (
            ("a1", "campus-a"), ("a2", "campus-a"),
            ("existing", "campus-existing"), ("stale", "campus-stale"),
            ("planned", "campus-planned"),
        ):
            self.write_source(key, parent)
        self.write_source("a1", "campus-a", suffix="-v2")

    @staticmethod
    def evidence(key: str) -> dict[str, str]:
        return {
            "key": f"evidence-{key}", "content_hash": inventory.sha256(key.encode()),
            "source_url": f"https://example.test/{key}", "publisher": "Fixture publisher",
        }

    def row(
        self, key: str, day: str = "2026-08-01", status: str = "under_construction",
        entity_kind: str = "project",
    ) -> dict[str, str]:
        return {
            "stable_key": key, "entity_kind": entity_kind, "name": f"Project {key}",
            "country": "Fixture country", "status": status, "status_as_of": day,
            "status_method": "authoritative_physical_status_update",
            "status_evidence_id": inventory.evidence_id(self.evidence(key)),
            "source_url": f"https://example.test/{key}", "source_publisher": "Fixture publisher",
        }

    def write_source(self, key: str, parent: str | None, suffix: str = "") -> Path:
        row = next(item for item in self.rows if item["stable_key"] == key)
        document = {
            "project": {"stable_key": key}, "campus": {"stable_key": parent},
            "evidence": [self.evidence(key)],
            "lifecycle": [{
                "entity": "project", "value": row["status"], "as_of_date": row["status_as_of"],
                "method": row["status_method"], "evidence_key": f"evidence-{key}",
            }],
        }
        path = self.sources / f"curated-{key}{suffix}.json"
        path.write_bytes(inventory.json_bytes(document))
        return path

    def build(self) -> dict:
        return inventory.build_inventory(self.root, self.pins)

    def test_deterministic_queue_and_exact_accounting(self) -> None:
        payload = self.build()
        self.assertEqual(inventory.json_bytes(payload), inventory.json_bytes(self.build()))
        self.assertEqual(payload["accounting"], {
            "input_pipeline_rows": 8, "excluded_nonproject_rows": 1,
            "excluded_baseline_selected_project_rows": 1,
            "baseline_post_v97_projects": 0, "candidate_project_rows": 6,
        })
        self.assertEqual([item["project_stable_key"] for item in payload["candidates"]], [
            "a1", "a2", "existing", "planned", "stale", "unresolved",
        ])
        self.assertEqual(payload["summary"]["accepted_new_physical_sites"], 0)
        self.assertEqual(payload["summary"]["verified_additional_physical_sites"], 0)
        self.assertEqual(payload["summary"]["exact_parent_key_groups_not_site_count"], 4)
        self.assertEqual(payload["summary"]["geometry_queue_rows_outside_baseline_by_exact_parent_key"], 2)
        self.assertEqual(payload["summary"]["geometry_queue_parent_key_groups_outside_baseline_not_site_count"], 1)
        self.assertFalse(payload["accepted_into_core"])
        self.assertTrue(all(item["accepted_into_core"] is False for item in payload["candidates"]))
        self.assertNotIn("geometry_json", inventory.json_bytes(payload).decode())

    def test_dedupe_preserves_source_variants_and_baseline_membership(self) -> None:
        rows = {item["project_stable_key"]: item for item in self.build()["candidates"]}
        self.assertEqual(rows["a1"]["same_parent_candidate_project_keys"], ["a2"])
        self.assertEqual(rows["a1"]["source_match_resolution"], "multiple_documents")
        self.assertEqual(len(rows["a1"]["source_matches"]), 2)
        self.assertTrue(rows["existing"]["parent_campus_already_in_baseline"])
        self.assertEqual(rows["existing"]["priority"], "existing_baseline_site_scope_review")
        self.assertIsNone(rows["unresolved"]["parent_campus_already_in_baseline"])
        self.assertIsNone(rows["unresolved"]["parent_campus_key"])

    def test_conflicting_parent_is_unresolved_not_a_new_site(self) -> None:
        self.write_source("a1", "conflicting-campus", suffix="-v2")
        row = next(item for item in self.build()["candidates"] if item["project_stable_key"] == "a1")
        self.assertIsNone(row["parent_campus_key"])
        self.assertIsNone(row["parent_campus_already_in_baseline"])
        self.assertEqual(row["same_parent_candidate_project_keys"], [])
        self.assertIn("parent_campus_missing_or_conflicting_across_matching_sources", row["duplicate_and_scope_reasons"])

    def test_missing_parent_in_one_variant_is_unresolved(self) -> None:
        self.write_source("a1", None, suffix="-v2")
        row = next(item for item in self.build()["candidates"] if item["project_stable_key"] == "a1")
        self.assertIsNone(row["parent_campus_key"])

    def test_project_key_without_status_evidence_id_does_not_bind(self) -> None:
        path = self.write_source("unresolved", "invented-parent")
        source = json.loads(path.read_text())
        source["evidence"][0]["content_hash"] = "a" * 64
        path.write_bytes(inventory.json_bytes(source))
        row = next(item for item in self.build()["candidates"] if item["project_stable_key"] == "unresolved")
        self.assertEqual(row["source_matches"], [])
        self.assertIsNone(row["parent_campus_key"])

    def test_lifecycle_mismatch_is_disclosed_not_preferred(self) -> None:
        path = self.sources / "curated-a1-v2.json"
        source = json.loads(path.read_text())
        source["lifecycle"][0]["value"] = "planned"
        path.write_bytes(inventory.json_bytes(source))
        row = next(item for item in self.build()["candidates"] if item["project_stable_key"] == "a1")
        self.assertEqual(len(row["source_matches"]), 2)
        self.assertEqual(sorted(item["exact_lifecycle_tuple_present"] for item in row["source_matches"]), [False, True])

    def test_cutoff_inclusive_and_failure_order_fixed(self) -> None:
        for age, expected in (
            (0, "not_in_reviewed_site_geometry_allowlist"),
            (90, "not_in_reviewed_site_geometry_allowlist"),
            (-1, "status_outside_90_day_window"), (91, "status_outside_90_day_window"),
        ):
            with self.subTest(age=age):
                day = (inventory.REFERENCE_DATE - timedelta(days=age)).isoformat()
                self.assertEqual(inventory.first_failure(self.row("test", day), set()), expected)
        row = self.row("test", "bad-date")
        self.assertEqual(inventory.first_failure(row, set()), "invalid_status_date")
        row["status_method"] = "announcement"
        self.assertEqual(inventory.first_failure(row, set()), "status_method_not_authoritative")
        row["status"] = "planned"
        self.assertEqual(inventory.first_failure(row, set()), "status_not_physical")
        row["entity_kind"] = "campus"
        self.assertEqual(inventory.first_failure(row, set()), "entity_kind_not_project")

    def test_wrong_pipeline_or_manifest_pin_fails_closed(self) -> None:
        for field in ("pipeline_sha256", "baseline_manifest_sha256"):
            with self.subTest(field=field), self.assertRaisesRegex(inventory.InventoryError, "SHA-256 differs"):
                inventory.build_inventory(self.root, replace(self.pins, **{field: "0" * 64}))

    def test_altered_baseline_table_is_rejected(self) -> None:
        path = self.baseline / "sites.csv"
        path.write_bytes(path.read_bytes() + b"invented-campus\n")
        with self.assertRaisesRegex(inventory.InventoryError, "SHA-256 differs"):
            self.build()

    def test_duplicate_pipeline_keys_are_rejected_even_with_new_fixture_pin(self) -> None:
        raw = csv_bytes(self.rows + [self.rows[-1]])
        (self.root / inventory.PIPELINE_PATH).write_bytes(raw)
        self.pins = replace(self.pins, pipeline_sha256=inventory.sha256(raw), pipeline_rows=9)
        with self.assertRaisesRegex(inventory.InventoryError, "duplicate stable_key"):
            self.build()

    def test_wrong_accounting_is_rejected(self) -> None:
        with self.assertRaisesRegex(inventory.InventoryError, "row accounting differs"):
            inventory.build_inventory(self.root, replace(self.pins, pipeline_nonprojects=2))

    def test_emit_refuses_overwrite_and_check_compares_exact_bytes(self) -> None:
        path = self.root / "output.json"
        inventory.emit(path, b"original\n")
        inventory.emit(path, b"original\n", check=True)
        for check, payload in ((False, b"original\n"), (False, b"changed"), (True, b"changed")):
            with self.subTest(check=check, payload=payload), self.assertRaises(inventory.InventoryError):
                inventory.emit(path, payload, check=check)
            self.assertEqual(path.read_bytes(), b"original\n")
        missing = self.root / "missing.json"
        with self.assertRaises(inventory.InventoryError):
            inventory.emit(missing, b"new", check=True)
        self.assertFalse(missing.exists())

    def test_snapshot_validation_is_corpus_free_but_generation_is_not(self) -> None:
        payload = self.build()
        raw = inventory.json_bytes(payload)
        path = self.root / "snapshot.json"
        path.write_bytes(raw)
        (self.root / inventory.PIPELINE_PATH).unlink()
        result = inventory.validate_snapshot(path, self.root, self.pins, inventory.sha256(raw))
        self.assertEqual(result, payload)
        with self.assertRaisesRegex(inventory.InventoryError, "required input missing"):
            self.build()

    def test_snapshot_rejects_source_mutation_and_acceptance_claim(self) -> None:
        payload = self.build()
        raw = inventory.json_bytes(payload)
        path = self.root / "snapshot.json"
        path.write_bytes(raw)
        source = self.sources / "curated-a1.json"
        original = source.read_bytes()
        source.write_bytes(original + b" ")
        with self.assertRaisesRegex(inventory.InventoryError, "SHA-256 differs"):
            inventory.validate_snapshot(path, self.root, self.pins, inventory.sha256(raw))
        source.write_bytes(original)
        payload["candidates"][0]["accepted_into_core"] = True
        raw = inventory.json_bytes(payload)
        path.write_bytes(raw)
        with self.assertRaisesRegex(inventory.InventoryError, "research-only"):
            inventory.validate_snapshot(path, self.root, self.pins, inventory.sha256(raw))


class TrackedInventoryTests(unittest.TestCase):
    def test_portable_snapshot_and_all_curated_source_pins(self) -> None:
        payload = inventory.validate_snapshot(ROOT / inventory.OUTPUT_PATH)
        self.assertEqual(payload["baseline"]["physical_sites"], 100)
        self.assertEqual(payload["baseline"]["projects"], 103)
        self.assertEqual(payload["accounting"]["candidate_project_rows"], 385)
        self.assertEqual(payload["summary"]["first_failure_counts"], {
            "not_in_reviewed_site_geometry_allowlist": 48,
            "status_not_physical": 12, "status_outside_90_day_window": 325,
        })
        self.assertEqual(payload["summary"]["geometry_queue_parent_key_groups_outside_baseline_not_site_count"], 43)
        self.assertEqual(payload["summary"]["accepted_new_physical_sites"], 0)
        self.assertEqual(len(payload["input_source_documents"]), 420)

    @unittest.skipUnless((ROOT / inventory.PIPELINE_PATH).is_file(), "ignored v97 pipeline not hydrated")
    def test_hydrated_regeneration_matches_tracked_snapshot_exactly(self) -> None:
        inventory.emit(
            ROOT / inventory.OUTPUT_PATH, inventory.json_bytes(inventory.build_inventory()), check=True,
        )


if __name__ == "__main__":
    unittest.main()
