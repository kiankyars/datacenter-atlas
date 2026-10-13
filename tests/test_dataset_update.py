"""Observation dates, provenance and inherited rows survive routine updates."""

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.dataset_update import ROOT, UpdateError, build_update, update_payloads, validate_update


BASE = ROOT / "verified_construction_core/2026-08-20-v0.18-draft-thirty-seventh-reviewed"


class DatasetUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(BASE, self.root / "base")
        source = {
            "id": "work", "kind": "company_disclosure", "title": "Construction progress",
            "source_url": "https://example.org/progress", "publisher": "Example Operator",
            "source_family": "example", "license": "all-rights-reserved", "attribution": "Example Operator",
            "published_at": "2026-09-21", "retrieved_at": "2026-10-13T08:00:00Z",
            "content_hash": hashlib.sha256(b"test primary observation").hexdigest(),
            "summary": "Earthworks were underway at the named campus.",
        }
        self.sources = {"sources": [source]}
        self.spec = {
            "format": "datacenter-atlas-update-input-v1", "updated_at": "2026-10-13", "base_dataset": "base",
            "base_manifest_sha256": hashlib.sha256((BASE / "manifest.json").read_bytes()).hexdigest(),
            "source_files": [], "status_updates": [],
            "additions": [{
                "project_stable_key": "curated:test-campus:construction", "physical_site_stable_key": "curated:test-campus",
                "site_name": "Example campus", "name": "Example construction", "country": "United States", "country_iso_a2": "US",
                "status": {"value": "site_preparation", "as_of": "2026-09-21", "source_id": "work", "summary": "Earthworks were underway."},
                "locator": {"geometry": {"type": "Point", "coordinates": [-100.1, 30.2]}, "source_id": "work",
                            "scope": "campus_locator", "scope_class": "official_address_point", "authority": "official_source",
                            "method": "official_address", "precision": "Campus address point, not a building footprint.",
                            "identity_review": "The operator names the campus and gives this point.", "uncertainty_reason": "No accuracy stated."},
                "distinctness_review": "No existing project uses this campus.", "successor_review": "No later status through the update date.",
            }],
        }
        self.input = self.root / "update.json"

    def write(self):
        raw = json.dumps(self.sources).encode()
        (self.root / "source.json").write_bytes(raw)
        self.spec["source_files"] = [{"path": "source.json", "sha256": hashlib.sha256(raw).hexdigest()}]
        self.input.write_text(json.dumps(self.spec))

    def payloads(self):
        self.write()
        return update_payloads(self.input, root=self.root)

    def test_reproducible_with_real_baseline_and_unchanged_observation_dates(self):
        self.write()
        out = self.root / "out"
        manifest = build_update(self.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.input, out, root=self.root))
        self.assertEqual(manifest["counts"]["physical_sites"], 200)
        self.assertEqual(manifest["observation_window_end"], "2026-09-21")
        self.assertLess(manifest["observation_window_start"], "2026-07-15")
        before = {row["project_id"]: row for row in csv.DictReader(io.StringIO((BASE / "projects.csv").read_text()))}
        after = {row["project_id"]: row for row in csv.DictReader(io.StringIO((out / "projects.csv").read_text()))}
        for identifier, original in before.items():
            changed = copy.deepcopy(after[identifier])
            changed["status_age_days_at_review"] = original["status_age_days_at_review"]
            self.assertEqual(original, changed)
        (out / "projects.csv").write_text("tampered")
        with self.assertRaisesRegex(UpdateError, "not reproducible"):
            validate_update(self.input, out, root=self.root)

    def test_refresh_preserves_old_evidence_and_rejects_backdating(self):
        original = next(csv.DictReader(io.StringIO((BASE / "projects.csv").read_text())))
        self.spec["status_updates"] = [{
            "project_stable_key": original["project_stable_key"], "status": self.spec["additions"][0]["status"],
            "identity_review": "Same named project.", "successor_review": "No later status found.",
        }]
        payloads, _ = self.payloads()
        rows = {row["project_id"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}
        refreshed = rows[original["project_id"]]
        self.assertEqual(refreshed["status_as_of"], "2026-09-21")
        evidence = list(csv.DictReader(io.StringIO(payloads["evidence.csv"].decode())))
        self.assertTrue(any(row["evidence_id"] == original["status_evidence_id"] for row in evidence))
        self.spec["status_updates"][0]["status"] = {**self.spec["status_updates"][0]["status"], "as_of": "2026-01-01"}
        with self.assertRaisesRegex(UpdateError, "must be newer"):
            self.payloads()

    def test_future_and_stale_admissions_fail(self):
        for value, expected in (("2026-11-01", "future"), ("2026-01-01", "older than 90")):
            with self.subTest(value=value):
                self.spec["additions"][0]["status"]["as_of"] = value
                with self.assertRaisesRegex(UpdateError, expected):
                    self.payloads()

    def test_nonphysical_announcement_and_undated_observation_fail(self):
        self.spec["additions"][0]["status"]["value"] = "operational"
        with self.assertRaisesRegex(UpdateError, "needs physical construction"):
            self.payloads()
        self.spec["additions"][0]["status"]["value"] = "under_construction"
        self.sources["sources"][0]["published_at"] = ""
        with self.assertRaisesRegex(UpdateError, "dated source"):
            self.payloads()

    def test_base_and_source_hash_mismatch_fail(self):
        self.write()
        (self.root / "source.json").write_text("{}")
        with self.assertRaisesRegex(UpdateError, "source file hash differs"):
            update_payloads(self.input, root=self.root)
        self.spec["base_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(UpdateError, "base manifest hash differs"):
            self.payloads()

    def test_conflicting_source_metadata_and_capture_before_publication_fail(self):
        source = copy.deepcopy(self.sources["sources"][0])
        source.update(id="same-capture", kind="open_map", published_at="")
        self.sources["sources"].append(source)
        with self.assertRaisesRegex(UpdateError, "conflicting metadata"):
            self.payloads()
        self.sources["sources"].pop()
        self.sources["sources"][0]["retrieved_at"] = "2026-01-01T00:00:00Z"
        with self.assertRaisesRegex(UpdateError, "capture predates publication"):
            self.payloads()

    def test_duplicate_campus_and_host_estate_admission_fail(self):
        self.spec["additions"].append(copy.deepcopy(self.spec["additions"][0]))
        with self.assertRaisesRegex(UpdateError, "only one action"):
            self.payloads()
        self.spec["additions"].pop()
        self.spec["additions"][0]["locator"]["scope"] = "host_estate_context"
        with self.assertRaisesRegex(UpdateError, "must locate the project"):
            self.payloads()

    def test_existing_output_is_never_overwritten(self):
        self.write()
        out = self.root / "out"
        build_update(self.input, out, root=self.root)
        with self.assertRaisesRegex(UpdateError, "new or empty"):
            build_update(self.input, out, root=self.root)

    def test_same_input_cannot_backdate_new_admission_via_correction(self):
        self.spec["status_corrections"] = [{"project_stable_key": self.spec["additions"][0]["project_stable_key"]}]
        with self.assertRaisesRegex(UpdateError, "only one action"):
            self.payloads()

    def test_all_published_codes_are_allowed_by_schema(self):
        original = next(csv.DictReader(io.StringIO((BASE / "projects.csv").read_text())))
        self.spec["status_updates"] = [{
            "project_stable_key": original["project_stable_key"],
            "status": {**self.spec["additions"][0]["status"], "value": "operational"},
            "identity_review": "Same project.", "successor_review": "No later status.",
        }]
        payloads, _ = self.payloads()
        schema = json.loads(payloads["schema.json"])
        for name, table in schema["tables"].items():
            rows = list(csv.DictReader(io.StringIO(payloads[name].decode())))
            for field in table["fields"]:
                if "allowed_values" in field and field["logical_type"] == "string":
                    for row in rows:
                        value = row[field["name"]]
                        if value:
                            self.assertIn(value, field["allowed_values"])

    def test_withdrawal_requires_exact_evidence_and_removes_orphan_references(self):
        original = next(csv.DictReader(io.StringIO((BASE / "projects.csv").read_text())))
        self.spec["withdrawals"] = [{
            "project_stable_key": original["project_stable_key"], "replaces_status_evidence_id": original["status_evidence_id"],
            "reason": "Prior capture date was not an observation date.", "source_ids": ["work"],
        }]
        payloads, manifest = self.payloads()
        self.assertEqual(manifest["counts"]["physical_sites"], 199)
        self.assertNotIn(original["project_id"].encode(), payloads["projects.csv"])
        self.assertNotIn(original["project_id"].encode(), payloads["evidence.csv"])
        self.spec["withdrawals"][0]["replaces_status_evidence_id"] = "wrong"
        with self.assertRaisesRegex(UpdateError, "name the removed status evidence"):
            self.payloads()


if __name__ == "__main__":
    unittest.main()
