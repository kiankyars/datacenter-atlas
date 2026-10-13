"""Observation dates, provenance and inherited rows survive routine updates."""

import copy
from contextlib import redirect_stdout
import csv
from datetime import date, timedelta
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.dataset_update import ROOT, UpdateError, build_update, update_payloads, validate_update
    from datacenter_atlas import models, public_site
except ImportError:
    from datacenter_atlas.datacenter_atlas.dataset_update import ROOT, UpdateError, build_update, update_payloads, validate_update
    from datacenter_atlas.datacenter_atlas import models, public_site


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

    def test_exact_ninety_day_admission_boundary(self):
        self.spec["additions"][0]["status"]["as_of"] = "2026-07-15"
        self.payloads()
        self.spec["additions"][0]["status"]["as_of"] = "2026-07-14"
        with self.assertRaisesRegex(UpdateError, "older than 90"):
            self.payloads()

    def test_closed_admission_and_undated_observation_fail(self):
        self.spec["additions"][0]["status"]["value"] = "demolished"
        with self.assertRaisesRegex(UpdateError, "new admission needs"):
            self.payloads()
        self.spec["additions"][0]["status"]["value"] = "under_construction"
        self.sources["sources"][0]["published_at"] = ""
        with self.assertRaisesRegex(UpdateError, "dated source"):
            self.payloads()

    def test_completed_and_operating_admissions_keep_primary_and_freshness_gates(self):
        for status in ("completed", "operational"):
            with self.subTest(status=status):
                self.spec["additions"][0]["status"]["value"] = status
                payloads, _ = self.payloads()
                project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                               if row["project_stable_key"] == self.spec["additions"][0]["project_stable_key"])
                self.assertEqual(project["last_observed_physical_status"], status)
                self.assertEqual(project["status_as_of"], "2026-09-21")
                self.sources["sources"][0]["kind"] = "news"
                with self.assertRaisesRegex(UpdateError, "primary source"):
                    self.payloads()
                self.sources["sources"][0]["kind"] = "company_disclosure"
                self.spec["additions"][0]["status"]["as_of"] = "2026-01-01"
                with self.assertRaisesRegex(UpdateError, "older than 90"):
                    self.payloads()
                self.spec["additions"][0]["status"]["as_of"] = "2026-09-21"

    def test_published_physical_snapshot_remains_byte_reproducible(self):
        validate_update(ROOT / "definitions/atlas-update-2026-10-13.json",
                        ROOT / "verified_construction_core/2026-10-13")

    def test_dated_media_observation_does_not_invent_publication_date(self):
        source = self.sources["sources"][0]
        source.update(published_at=None, source_observation_date="2026-09-21",
                      source_observation_date_precision="day",
                      date_semantics="Operator construction photograph caption gives September21.")
        payloads, _ = self.payloads()
        evidence = list(csv.DictReader(io.StringIO(payloads["evidence.csv"].decode())))
        selected = next(row for row in evidence if row["source_url"] == source["source_url"])
        self.assertEqual(selected["published_at"], "")
        source["source_observation_date"] = "2026-09-20"
        with self.assertRaisesRegex(UpdateError, "explicit source observation"):
            self.payloads()
        source["source_observation_date"] = "2026-09-21"
        source["source_observation_date_precision"] = "month"
        with self.assertRaisesRegex(UpdateError, "dated source"):
            self.payloads()
        source["source_observation_date_precision"] = "day"
        source["retrieved_at"] = "2026-09-20T08:00:00Z"
        with self.assertRaisesRegex(UpdateError, "capture predates observation"):
            self.payloads()

    def test_announced_and_permitted_admissions_do_not_claim_physical_work(self):
        for status, method, role in (
            ("announced", "authoritative_project_announcement", "announcement"),
            ("permitted", "authoritative_construction_permit", "permit"),
        ):
            with self.subTest(status=status):
                self.spec["additions"][0]["status"].update(
                    value=status, summary="The named project is announced or has planning permission; no physical work reported.",
                    permit_scope="data_center_development", permit_type="planning_permission", permit_decision="granted",
                    permit_reference="DC/2026/123", permit_identity_review="The decision names this data-centre campus and address.",
                )
                payloads, _ = self.payloads()
                project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                               if row["project_stable_key"] == self.spec["additions"][0]["project_stable_key"])
                self.assertEqual(project["last_observed_physical_status"], status)
                self.assertEqual(project["status_method"], method)
                self.assertEqual(project["verification_posture"], "authoritative_project_record_plus_scoped_location")
                evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                                if row["evidence_id"] == project["status_evidence_id"])
                self.assertIn(role, json.loads(evidence["roles_json"]))
                self.assertNotIn("physical_status", json.loads(evidence["roles_json"]))
        self.sources["sources"][0]["kind"] = "news"
        with self.assertRaisesRegex(UpdateError, "primary source"):
            self.payloads()

    def test_permitted_requires_a_granted_data_center_permission(self):
        status = self.spec["additions"][0]["status"]
        valid = {
            **status, "value": "permitted", "permit_scope": "data_center_development",
            "permit_type": "building_permit", "permit_decision": "granted", "permit_reference": "DC/2026/123",
            "permit_identity_review": "The granted building permit identifies this exact data-centre building.",
        }
        for changes, message in (
            ({"permit_scope": "power_plant"}, "data-center development"),
            ({"permit_type": "air_permit"}, "authorize the planned development"),
            ({"permit_decision": "pending"}, "granted decision"),
            ({"permit_reference": ""}, "permit reference"),
            ({"permit_identity_review": ""}, "permit identity review"),
        ):
            with self.subTest(changes=changes):
                self.spec["additions"][0]["status"] = {**valid, **changes}
                with self.assertRaisesRegex(UpdateError, message):
                    self.payloads()

    def test_lifecycle_transitions_retain_site_identity_and_previous_evidence(self):
        key = self.spec["additions"][0]["project_stable_key"]
        summaries = {
            "announced": "The operator announced the named campus; no physical work is reported.",
            "permitted": "The authority granted planning permission for this data-centre campus; no physical work is reported.",
            "under_construction": "The operator reports construction work underway at the campus.",
            "completed": "Construction of the data-centre building is complete. Operation is not yet established.",
            "operational": "The operator reports that this data-centre facility is open and operating.",
        }
        identities, evidence_ids = None, set()
        for offset, (status, summary) in enumerate(summaries.items()):
            updated = (date(2026, 10, 13) + timedelta(days=offset)).isoformat()
            source = self.sources["sources"][0]
            source.update(title=status, summary=summary, published_at=updated, retrieved_at=updated + "T08:00:00Z",
                          content_hash=hashlib.sha256(summary.encode()).hexdigest())
            self.spec["updated_at"] = updated
            observation = {"value": status, "as_of": updated, "source_id": "work", "summary": summary}
            if status == "permitted":
                observation.update(permit_scope="data_center_development", permit_type="planning_permission",
                                   permit_decision="granted", permit_reference="DC/2026/123",
                                   permit_identity_review="The permission is for the named campus, not its power plant.")
            if offset == 0:
                self.spec["additions"][0]["status"] = observation
            else:
                self.spec["additions"] = []
                self.spec["status_updates"] = [{"project_stable_key": key, "status": observation,
                                                "identity_review": "Same campus and project.",
                                                "successor_review": "Latest dated primary observation."}]
            self.write()
            output = self.root / "updates" / updated
            manifest = build_update(self.input, output, root=self.root)
            self.assertEqual(manifest["counts"]["physical_sites"], 200)
            atlas = public_site.load_atlas(public_site.discover_versions(output.parent)[-1], "https://example.org/")
            project = next(row for row in atlas.projects if row["project_stable_key"] == key)
            identity = (project["project_id"], project["site_id"], project["physical_site_stable_key"])
            if identities is None:
                identities = identity
            self.assertEqual(identity, identities)
            self.assertEqual(project["last_observed_physical_status"], status)
            self.assertEqual(atlas.site_by_id[project["site_id"]]["statuses"], [status])
            self.assertTrue(evidence_ids <= set(atlas.evidence_by_id))
            evidence_ids.add(project["status_evidence_id"])
            self.assertEqual(len(evidence_ids), offset + 1)
            if status == "completed":
                self.assertEqual(models.LifecycleStatus.COMPLETED.value, status)
                self.assertNotEqual(status, models.LifecycleStatus.OPERATIONAL.value)
            self.spec["base_dataset"] = output.relative_to(self.root).as_posix()
            self.spec["base_manifest_sha256"] = hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()

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

    def test_cli_uses_definition_output_unless_explicitly_overridden(self):
        self.spec["output"] = "verified_construction_core/2026-10-13-research"
        self.write()
        script = ROOT / "scripts/build_dataset_update.py"
        module = build_update.__module__
        for override in (None, self.root / "explicit-output"):
            argv = [str(script), "--input", str(self.input)]
            if override:
                argv += ["--output", str(override)]
            with patch("sys.argv", argv), patch(module + ".build_update", return_value={"counts": {}}) as build, redirect_stdout(io.StringIO()):
                runpy.run_path(str(script), run_name="__main__")
            self.assertEqual(build.call_args.args, (self.input.resolve(), override or ROOT / self.spec["output"]))
        self.spec["output"] = "../outside-repository"
        self.write()
        with patch("sys.argv", [str(script), "--input", str(self.input)]), self.assertRaisesRegex(UpdateError, "unsafe input path"):
            runpy.run_path(str(script), run_name="__main__")

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
