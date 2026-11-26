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
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from datacenter_atlas.dataset_update import ROOT, UpdateError, _inherited_campus_locator, build_update, update_payloads, validate_update
from datacenter_atlas import models, public_site


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

    def test_cdla_source_includes_license_text_and_credit_in_later_snapshots(self):
        filename = "CDLA-Permissive-2.0.txt"
        self.assertNotIn(filename, self.payloads()[0])
        self.sources["sources"][0].update(license="CDLA-Permissive-2.0", attribution="Foundation and provider")
        first = self.root / "first"
        self.write()
        build_update(self.input, first, root=self.root)
        expected = (ROOT / "datacenter_atlas" / "licenses" / filename).read_bytes()
        self.assertEqual(hashlib.sha256(expected).hexdigest(), "4531a67d443284d93ffed0803df5b10634aff21c3d77e381f2d48af01d875868")
        self.assertEqual((first / filename).read_bytes(), expected)
        self.assertIn(f"Foundation and provider. Full licence in {filename}", (first / "ATTRIBUTION.txt").read_text())

        self.spec.update(base_dataset="first", base_manifest_sha256=hashlib.sha256((first / "manifest.json").read_bytes()).hexdigest())
        self.spec["additions"][0].update(physical_site_stable_key="curated:another-site", project_stable_key="curated:another-site:construction")
        self.spec["additions"][0]["locator"]["geometry"]["coordinates"] = [-99.0, 30.2]
        self.sources["sources"][0].update(license="all-rights-reserved", source_url="https://example.org/another-site")
        payloads, manifest = self.payloads()
        self.assertEqual(payloads[filename], expected)
        self.assertEqual(manifest["files"][filename]["sha256"], hashlib.sha256(expected).hexdigest())

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

    def test_status_change_links_corroboration_to_the_project_only(self):
        original = next(csv.DictReader((BASE / "projects.csv").read_text().splitlines()))
        context = {**self.sources["sources"][0], "id": "company-spec", "source_url": "https://example.org/spec"}
        self.sources["sources"].append(context)
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        action = {"project_stable_key": original["project_stable_key"], "context_source_ids": ["company-spec"],
                  "status": self.spec["additions"][0]["status"], "identity_review": "Same project.",
                  "successor_review": "Latest dated construction report."}
        self.spec["status_updates"] = [action]
        payloads, _ = self.payloads()
        record = next(r for r in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode())) if r["source_url"] == context["source_url"])
        self.assertEqual(json.loads(record["project_ids_json"]), [original["project_id"]])
        self.assertEqual(json.loads(record["roles_json"]), ["context:identity"])
        project = next(r for r in csv.DictReader(io.StringIO(payloads["projects.csv"].decode())) if r["project_id"] == original["project_id"])
        self.assertNotEqual(record["evidence_id"], project["status_evidence_id"])
        for invalid in ("company-spec", ["unknown"], ["company-spec", "company-spec"]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(UpdateError, "unique reviewed source IDs"):
                action["context_source_ids"] = invalid
                self.payloads()
        self.spec["format"] = "datacenter-atlas-update-input-v1"
        action["context_source_ids"] = ["company-spec"]
        with self.assertRaisesRegex(UpdateError, "require v2"):
            self.payloads()

    def prepare_existing_campus(self):
        self.write()
        out = self.root / "first"
        build_update(self.input, out, root=self.root)
        project = next(row for row in csv.DictReader(io.StringIO((out / "projects.csv").read_text()))
                       if row["project_stable_key"] == "curated:test-campus:construction")
        self.spec.update(base_dataset="first", base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
        addition = self.spec["additions"][0]
        addition.update(project_stable_key="curated:test-campus:phase2", name="Example Phase 2",
                        existing_site_id=project["site_id"],
                        site_identity_review="The new phase is explicitly on the same named campus.")
        addition["status"].update(value="commissioning")
        return project

    def test_existing_campus_adds_phase_without_duplicating_site_or_rewriting_first_phase(self):
        original = self.prepare_existing_campus()
        self.write()
        out = self.root / "second"
        manifest = build_update(self.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.input, out, root=self.root))
        self.assertEqual(manifest["counts"]["physical_sites"], 200)
        rows = list(csv.DictReader(io.StringIO((out / "projects.csv").read_text())))
        members = [row for row in rows if row["site_id"] == original["site_id"]]
        self.assertEqual(len(members), 2)
        self.assertIn(original, members)
        site = next(row for row in csv.DictReader(io.StringIO((out / "sites.csv").read_text())) if row["site_id"] == original["site_id"])
        self.assertEqual(site["project_count"], "2")
        self.assertEqual(json.loads(site["statuses_json"]), ["commissioning", "site_preparation"])
        self.assertEqual(set(json.loads(site["project_ids_json"])), {row["project_id"] for row in members})
        self.assertEqual(set(json.loads(site["project_stable_keys_json"])), {row["project_stable_key"] for row in members})
        self.assertEqual(site["geometry_json"], original["geometry_json"])
        report = json.loads((out / "selection-report.json").read_bytes())
        self.assertEqual(report["added_sites"], [])
        self.assertEqual(report["expanded_sites"], ["curated:test-campus"])
        self.assertEqual(report["added_projects"], ["curated:test-campus:phase2"])

    def test_existing_campus_requires_explicit_identity_and_unchanged_scoped_point(self):
        self.prepare_existing_campus()
        valid = copy.deepcopy(self.spec["additions"][0])
        self.sources["sources"].append({**self.sources["sources"][0], "id": "different-map", "source_url": "https://example.org/other-map"})
        cases = [
            ({"existing_site_id": None}, "explicit matching"),
            ({"existing_site_id": "wrong-site"}, "explicit matching"),
            ({"site_identity_review": ""}, "site identity review"),
            ({"country_iso_a2": "CA"}, "name and country"),
            ({"site_name": "A different campus"}, "name and country"),
            ({"project_stable_key": "curated:test-campus:construction"}, "duplicate project"),
            ({"physical_site_stable_key": "curated:different-campus"}, "does not resolve"),
            ({"locator": {**valid["locator"], "scope": "project_locator"}}, "reviewed campus point"),
            ({"locator": {**valid["locator"], "geometry": {"type": "Point", "coordinates": [-100, 30]}}}, "reviewed campus point"),
            ({"locator": {**valid["locator"], "horizontal_uncertainty_metres": 5}}, "uncertainty must be preserved"),
            ({"locator": {**valid["locator"], "source_id": "different-map"}}, "provenance and precision"),
        ]
        for field, value in (("method", "different_method"), ("scope_class", "different_scope"),
                             ("authority", "compiled_reference"), ("precision", "Surveyed building point")):
            cases.append(({"locator": {**valid["locator"], field: value}}, "provenance and precision"))
        cases.append(({"locator": {**valid["locator"], "derivation": "georeferenced_source_map", "authority": "compiled_reference"}}, "provenance and precision"))
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.spec["additions"] = [{**valid, **changes}]
                with self.assertRaisesRegex(UpdateError, expected):
                    self.payloads()

    def test_explicit_existing_point_locator_reuse_preserves_original_fields(self):
        original = self.prepare_existing_campus()
        self.spec["additions"][0]["locator"] = {
            "reuse_from_project_id": original["project_id"], "geometry_evidence_id": original["geometry_evidence_id"],
            "geometry_identity_evidence_ids": [], "scope": "campus_locator",
            "identity_review": "The second phase is on the same reviewed campus.",
        }
        payloads, manifest = self.payloads()
        members = [row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                   if row["site_id"] == original["site_id"]]
        self.assertEqual(manifest["counts"]["physical_sites"], 200)
        self.assertEqual(len(members), 2)
        self.assertIn(original, members)
        added = next(row for row in members if row != original)
        for field in original:
            if field.startswith("geometry_") or field.startswith("horizontal_uncertainty") or field in {"latitude", "longitude"}:
                self.assertEqual(added[field], original[field], field)

    def test_reports_require_attributed_firsthand_physical_status_and_preserve_kind(self):
        for kind in ("news", "analyst_report"):
            with self.subTest(kind=kind):
                source = self.sources["sources"][0]
                source["kind"] = kind
                self.spec["additions"][0]["status"]["value"] = "site_preparation"
                source.pop("firsthand_status_statement", None)
                with self.assertRaisesRegex(UpdateError, "primary source"):
                    self.payloads()
                statement = {
                    "basis": "attributed_project_participant_statement", "speaker": "Named project manager",
                    "speaker_role": "Manager responsible for the named project", "project_identity": "Example campus construction",
                    "statement": "The manager says earthworks are currently in progress.", "date_semantics": "Dated on-site interview.",
                    "observed_on": "2026-09-21", "supported_status": "site_preparation",
                    "review": "Reviewed the original report and explicit attribution; no forecast treated as achieved work.",
                }
                source["firsthand_status_statement"] = statement
                payloads, _ = self.payloads()
                row = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode())) if row["project_stable_key"] == self.spec["additions"][0]["project_stable_key"])
                self.assertEqual(row["status_method"], "attributed_firsthand_physical_status_report")
                evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode())) if row["source_url"] == source["source_url"])
                self.assertEqual(evidence["kind"], kind)
                for changes, expected in (
                    ({"basis": "reporter_narrative"}, "primary source"),
                    ({"speaker": ""}, "firsthand status speaker"),
                    ({"speaker_role": ""}, "firsthand status speaker_role"),
                    ({"project_identity": ""}, "firsthand status project_identity"),
                    ({"statement": ""}, "firsthand status statement"),
                    ({"date_semantics": ""}, "firsthand status date_semantics"),
                    ({"review": ""}, "firsthand status review"),
                    ({"observed_on": "2026-09-20"}, "selected status and observation date"),
                    ({"supported_status": "operational"}, "selected status and observation date"),
                ):
                    with self.subTest(changes=changes):
                        source["firsthand_status_statement"] = {**statement, **changes}
                        with self.assertRaisesRegex(UpdateError, expected):
                            self.payloads()
                source["firsthand_status_statement"] = statement
                for value in ("announced", "permitted"):
                    self.spec["additions"][0]["status"]["value"] = value
                    with self.assertRaisesRegex(UpdateError, "primary source"):
                        self.payloads()

    def test_analyst_firsthand_update_preserves_source_and_rejects_ordinary_analysis(self):
        source = self.sources["sources"][0]
        source.update(kind="analyst_report", publisher="Research House", attribution="Research House")
        source["firsthand_status_statement"] = {
            "basis": "attributed_project_participant_statement", "speaker": "Named research analyst",
            "speaker_role": "Participant in the dated campus visit", "project_identity": "Example campus",
            "statement": "The visit report states that the named campus is operating.",
            "date_semantics": "Explicit date of the participant's visit, not publication or retrieval.",
            "observed_on": "2026-09-21", "supported_status": "operational",
            "review": "Original dated visit report reviewed; forecast capacity is excluded.",
        }
        statement = copy.deepcopy(source["firsthand_status_statement"])
        baseline = next(csv.DictReader((BASE / "projects.csv").open()))
        self.spec["additions"] = []
        self.spec["status_updates"] = [{
            "project_stable_key": baseline["project_stable_key"],
            "status": {"value": "operational", "as_of": "2026-09-21", "source_id": "work",
                       "summary": "The visit report identifies existing operation."},
            "identity_review": "The named campus is unchanged.", "successor_review": "No later report.",
        }]
        payloads, _ = self.payloads()
        row = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                   if row["project_stable_key"] == baseline["project_stable_key"])
        self.assertEqual(row["status_method"], "attributed_firsthand_physical_status_report")
        self.assertEqual(row["status_as_of"], "2026-09-21")
        evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                        if row["source_url"] == source["source_url"])
        self.assertEqual((evidence["kind"], evidence["publisher"], evidence["attribution"]),
                         ("analyst_report", "Research House", "Research House"))
        provenance = json.loads(payloads["review-provenance.json"])
        self.assertEqual(provenance["source_projections"]["work"]["firsthand_status_statement"], statement)
        for invalid in ({}, {**statement, "basis": "analyst_estimate"}):
            source["firsthand_status_statement"] = invalid
            with self.assertRaisesRegex(UpdateError, "primary source"):
                self.payloads()
        source["firsthand_status_statement"] = statement
        source["kind"] = "trade_press"
        with self.assertRaisesRegex(UpdateError, "primary source"):
            self.payloads()
        source.update(kind="analyst_report", published_at=None, source_observation_date="2026-09-21",
                      source_observation_date_precision="day", date_semantics="Explicit visit date.")
        with self.assertRaisesRegex(UpdateError, "primary source"):
            self.payloads()

    def test_future_and_stale_admissions_fail(self):
        for value, expected in (("2026-11-01", "future"), ("2026-01-01", "older than 90")):
            with self.subTest(value=value):
                self.spec["additions"][0]["status"]["as_of"] = value
                with self.assertRaisesRegex(UpdateError, expected):
                    self.payloads()

    def test_derived_locator_preserves_derivation_and_compiled_authority(self):
        locator = self.spec["additions"][0]["locator"]
        for derivation, method in (
            ("georeferenced_source_map", "source_map_registered_to_reference_tiles"),
            ("coordinate_transform", "operator_marker_converted_to_wgs84"),
        ):
            with self.subTest(derivation=derivation):
                locator.update(derivation=derivation, authority="compiled_reference", method=method)
                payloads, _ = self.payloads()
                project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                               if row["project_stable_key"] == self.spec["additions"][0]["project_stable_key"])
                site = next(row for row in csv.DictReader(io.StringIO(payloads["sites.csv"].decode()))
                            if row["site_id"] == project["site_id"])
                self.assertEqual(project["geometry_derivation"], derivation)
                self.assertEqual(project["geometry_authority_class"], "compiled_reference")
                self.assertEqual(json.loads(site["geometry_derivations_json"]), [derivation])
                locator["authority"] = "official_source"
                with self.assertRaisesRegex(UpdateError, "must be a compiled reference"):
                    self.payloads()
        locator["derivation"] = "unreviewed_guess"
        with self.assertRaisesRegex(UpdateError, "unsupported locator derivation"):
            self.payloads()

    def test_grid_context_preserves_project_status_geometry_and_capacity(self):
        original = next(csv.DictReader(io.StringIO((BASE / "projects.csv").read_text())))
        self.spec["additions"] = []
        self.sources["sources"][0]["kind"] = "utility_record"
        self.spec["context_updates"] = [{
            "project_stable_key": original["project_stable_key"],
            "source_ids": ["work"], "context_kind": "power_readiness",
            "identity_review": "Utility names this project as the intended connected customer.",
            "summary": "Upstream substation works; no data-centre stage or energized capacity established.",
            "preserve_status_as_of": original["status_as_of"],
        }]
        payloads, _ = self.payloads()
        project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                       if row["project_id"] == original["project_id"])
        project["status_age_days_at_review"] = original["status_age_days_at_review"]
        self.assertEqual(project, original)
        evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                        if row["source_url"] == "https://example.org/progress")
        self.assertEqual(json.loads(evidence["roles_json"]), ["context:power_readiness"])
        self.assertEqual(json.loads(evidence["project_ids_json"]), [original["project_id"]])
        report = json.loads(payloads["selection-report.json"])
        self.assertEqual(report["refreshed_projects"], [])
        self.assertEqual(report["context_enriched_projects"], [original["project_stable_key"]])
        self.spec["context_updates"][0]["source_ids"] = ["missing"]
        with self.assertRaisesRegex(UpdateError, "needs reviewed sources"):
            self.payloads()
        self.spec["context_updates"][0]["source_ids"] = ["work"]
        self.spec["context_updates"][0]["preserve_status_as_of"] = "2026-10-13"
        with self.assertRaisesRegex(UpdateError, "preserve the existing"):
            self.payloads()
        self.spec["context_updates"][0]["project_stable_key"] = "unknown"
        with self.assertRaisesRegex(UpdateError, "unknown context project"):
            self.payloads()

    def test_environmental_performance_attaches_only_evidence_in_v2(self):
        with (BASE / "projects.csv").open() as f:
            project = next(row for row in csv.DictReader(f) if json.loads(row["power_observations_json"]))
        self.spec.update(format="datacenter-atlas-update-input-v2", additions=[])
        summary = "The operator reports that industrial water supplies over 90% of this site's cooling water."
        self.sources["sources"][0].update(title="Site water use", summary=summary)
        control, _ = self.payloads()
        self.spec["context_updates"] = [{
            "project_stable_key": project["project_stable_key"], "source_ids": ["work"],
            "context_kind": "environmental_performance", "preserve_status_as_of": project["status_as_of"],
            "identity_review": "The operator identifies this site in its water disclosure.", "summary": summary,
        }]
        payloads, _ = self.payloads()
        for file in ("projects.csv", "sites.csv", "sites.geojson", "schema.json"):
            self.assertEqual(payloads[file], control[file], file)
        record = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                      if row["source_url"] == self.sources["sources"][0]["source_url"])
        self.assertEqual(json.loads(record["project_ids_json"]), [project["project_id"]])
        self.assertEqual(json.loads(record["roles_json"]), ["context:environmental_performance"])
        self.spec["format"] = "datacenter-atlas-update-input-v1"
        with self.assertRaisesRegex(UpdateError, "unsupported context kind"):
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

    def use_facility_award(self, key):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        url = "https://example.org/awards/101"
        award = {
            "certificate_id": "CF-101", "issuer": "Example Certifier", "scheme_owner": "Example Standards Body",
            "certification_type": "constructed_facility", "assessment_type": "assessed_recertification",
            "project_stable_key": key, "certified_scope": "The first hall at Example campus.",
            "identity_review": "The named project covers exactly this hall.",
            "assessment_review": "The issuer assessed the constructed hall under the scheme's recertification rules.",
            "award_date": "2026-09-21", "award_url": url,
        }
        source = {**self.sources["sources"][0], "id": "award", "kind": "certification_registry",
                  "publisher": award["issuer"], "source_url": url, "published_at": None,
                  "constructed_facility_award": award, "source_observation_date": "2026-09-21",
                  "source_observation_date_precision": "day", "date_semantics": "The award attests to completion by this day."}
        self.sources["sources"].append(source)
        status = {"value": "completed", "as_of": "2026-09-21", "source_id": "award",
                  "summary": "The issuer recertified the constructed hall."}
        return source, award, status

    def test_constructed_facility_awards_attest_completion_by_award_date(self):
        item = self.spec["additions"][0]
        source, award, item["status"] = self.use_facility_award(item["project_stable_key"])
        for assessment, publisher, publication in (("assessed_recertification", award["issuer"], None),
                                                   ("initial_assessed_award", award["scheme_owner"], "2026-09-28")):
            with self.subTest(assessment=assessment):
                award["assessment_type"] = assessment
                source.update(publisher=publisher, published_at=publication)
                payloads, _ = self.payloads()
                project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                               if row["project_stable_key"] == item["project_stable_key"])
                evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                                if row["evidence_id"] == project["status_evidence_id"])
                self.assertEqual((project["last_observed_physical_status"], project["status_as_of"], project["status_method"]),
                                 ("completed", "2026-09-21", "constructed_facility_certification"))
                self.assertEqual((evidence["kind"], evidence["published_at"], json.loads(evidence["roles_json"])),
                                 ("certification_registry", publication or "", ["physical_status"]))
                self.assertEqual(json.loads(payloads["review-provenance.json"])["source_projections"]["award"]
                                 ["constructed_facility_award"], award)

    def test_constructed_facility_awards_require_reviewed_original_project_scope_and_event(self):
        item = self.spec["additions"][0]
        source, award, status = self.use_facility_award(item["project_stable_key"])
        item["status"] = status
        for target, changes, message in (
                (self.spec, {"format": "datacenter-atlas-update-input-v1"}, "requires a v2"),
                (source, {"constructed_facility_award": None}, "assessed constructed-facility"),
                (source, {"kind": "company_disclosure", "published_at": "2026-09-21"}, "certification registry source"),
                (source, {"publisher": "Reseller"}, "original issuer or scheme owner"),
                (award, {"award_url": "https://example.org/awards/102"}, "original award record"),
                (award, {"certificate_id": ""}, "award certificate_id"),
                (award, {"certification_type": "design"}, "assessed constructed-facility"),
                (award, {"assessment_type": "administrative_renewal"}, "assessed constructed-facility"),
                (award, {"assessment_type": "annual_surveillance"}, "assessed constructed-facility"),
                (award, {"assessment_review": ""}, "award assessment_review"),
                (award, {"project_stable_key": "other:phase"}, "cover the selected project"),
                (award, {"certified_scope": ""}, "award certified_scope"),
                (award, {"identity_review": ""}, "award identity_review"),
                (award, {"award_date": None, "issue_date": status["as_of"]}, "explicitly dated assessment award"),
                (award, {"award_date": None, "expiry_date": status["as_of"]}, "explicitly dated assessment award"),
                (source, {"source_observation_date_precision": "month"}, "explicitly dated assessment award"),
                (source, {"source_observation_date": "2026-09-20", "published_at": status["as_of"]}, "explicitly dated assessment award"),
                (source, {"published_at": "2026-09-20"}, "postdates its source"),
                (source, {"retrieved_at": "2026-09-20T12:00:00Z"}, "capture predates observation"),
                (source, {"date_semantics": ""}, "date semantics"),
                (status, {"value": "operational"}, "for completed status"),
                (status, {"value": "under_construction"}, "for completed status"),
                (status, {"as_of": "2026-01-01"}, "older than 90")):
            with self.subTest(changes=changes), patch.dict(target, changes), self.assertRaisesRegex(UpdateError, message):
                self.payloads()

    def test_award_updates_preserve_operating_and_terminal_statuses(self):
        # This published base includes partially operating projects. Add three terminal
        # states using ordinary primary evidence before exercising the award pathway.
        original = ROOT / "verified_construction_core/2026-10-14-research-ninth"
        shutil.copytree(original, self.root / "ninth")
        rows = list(csv.DictReader(io.StringIO((original / "projects.csv").read_text())))
        keys = {r["last_observed_physical_status"]: r["project_stable_key"] for r in rows}
        construction = iter(row for row in rows if row["last_observed_physical_status"] == "under_construction")
        self.spec.update(base_dataset="ninth", base_manifest_sha256=hashlib.sha256((original / "manifest.json").read_bytes()).hexdigest(),
                         additions=[], updated_at="2026-10-30")
        self.sources["sources"][0].update(published_at="2026-10-20", retrieved_at="2026-10-28T12:00:00Z")
        for state in ("decommissioned", "demolished", "repurposed"):
            keys[state] = next(construction)["project_stable_key"]
            self.spec["status_updates"].append({
                "project_stable_key": keys[state], "identity_review": "Same project.", "successor_review": "Later status checked.",
                "status": {"value": state, "as_of": "2026-10-20", "source_id": "work", "summary": f"The project was {state}."},
            })
        self.write()
        interim = self.root / "interim"
        build_update(self.input, interim, root=self.root)
        self.spec.update(base_dataset="interim", base_manifest_sha256=hashlib.sha256((interim / "manifest.json").read_bytes()).hexdigest())
        source, award, status = self.use_facility_award(keys["permitted"])
        status["as_of"] = source["source_observation_date"] = award["award_date"] = "2026-10-25"
        action = {"project_stable_key": keys["permitted"], "status": status,
                  "identity_review": "The certificate covers this property.", "successor_review": "Checked later records."}
        self.spec["status_updates"] = [action]
        payloads, _ = self.payloads()
        promoted = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                        if row["project_stable_key"] == keys["permitted"])
        self.assertEqual((promoted["last_observed_physical_status"], promoted["status_method"]),
                         ("completed", "constructed_facility_certification"))
        prior = {row["project_stable_key"]: row for row in csv.DictReader(io.StringIO((interim / "projects.csv").read_text()))}
        for group in ("status_updates", "status_corrections"):
            self.spec["status_updates"] = []
            self.spec[group] = [action]
            for state in ("partially_operational", "operational", "cancelled", "decommissioned", "demolished", "repurposed"):
                with self.subTest(group=group, state=state):
                    action["project_stable_key"] = award["project_stable_key"] = keys[state]
                    action.update(replaces_status_evidence_id=prior[keys[state]]["status_evidence_id"], reason="Certification review.")
                    with self.assertRaisesRegex(UpdateError, "cannot supersede"):
                        self.payloads()

    def test_published_physical_snapshot_remains_byte_reproducible(self):
        validate_update(ROOT / "definitions/atlas-update-2026-10-13.json",
                        ROOT / "verified_construction_core/2026-10-13")

    def test_point_addition_locator_identity_sources_are_associated_from_v2(self):
        identity = {**self.sources["sources"][0], "id": "directory", "source_url": "https://example.org/directory"}
        self.sources["sources"].append(identity)
        addition = self.spec["additions"][0]
        addition["locator"]["identity_source_ids"] = ["directory"]
        project_id = str(uuid5(NAMESPACE_URL, addition["project_stable_key"]))
        expected = [(["context:identity"], [project_id])]
        for version, context_ids, expected_links in (
            ("v1", [], []),
            ("v2", [], expected),
            ("v2", ["directory"], expected),
        ):
            with self.subTest(version=version, context_ids=context_ids):
                self.spec["format"] = "datacenter-atlas-update-input-" + version
                addition["context_source_ids"] = context_ids
                payloads, _ = self.payloads()
                rows = csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                links = [(json.loads(row["roles_json"]), json.loads(row["project_ids_json"]))
                         for row in rows if row["source_url"] == identity["source_url"]]
                self.assertEqual(links, expected_links)

    def test_v2_point_addition_validates_optional_locator_identity_sources(self):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        locator = self.spec["additions"][0]["locator"]
        omitted, _ = self.payloads()
        locator["identity_source_ids"] = []
        empty, _ = self.payloads()
        self.assertEqual(omitted["evidence.csv"], empty["evidence.csv"])
        for invalid in ("work", None, ["work", "work"], [""], ["missing"], [1], [{}]):
            with self.subTest(invalid=invalid):
                locator["identity_source_ids"] = invalid
                with self.assertRaisesRegex(UpdateError, "identity_source_ids"):
                    self.payloads()

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

    def test_operational_entry_preserves_observation_without_inventing_publication(self):
        source = self.sources["sources"][0]
        source.update(published_at=None, source_observation_date="2026-09-29",
                      source_observation_date_precision="day",
                      date_semantics="Operator status panel explicitly reports Available on September29.")
        self.spec["additions"][0]["status"].update(
            value="operational", as_of="2026-09-29", summary="The operator reports the facility in service.")
        payloads, _ = self.payloads()
        project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                       if row["project_stable_key"] == self.spec["additions"][0]["project_stable_key"])
        self.assertEqual(project["last_observed_physical_status"], "operational")
        self.assertEqual(project["status_as_of"], "2026-09-29")
        evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                        if row["evidence_id"] == project["status_evidence_id"])
        self.assertEqual(evidence["published_at"], "")
        self.assertEqual(evidence["retrieved_at"], "2026-10-13T08:00:00Z")

    def test_undated_operational_entry_requires_primary_evidence_and_exact_observation(self):
        valid_source = {**self.sources["sources"][0], "published_at": None,
                        "source_observation_date": "2026-09-29", "source_observation_date_precision": "day",
                        "date_semantics": "Operator status panel explicitly reports Available on September29."}
        valid_status = {**self.spec["additions"][0]["status"], "value": "operational", "as_of": "2026-09-29"}
        cases = [
            ({"source_observation_date": None}, {}, "dated source"),
            ({"source_observation_date_precision": "month"}, {}, "dated source"),
            ({"source_observation_date": "2026-09-28"}, {}, "explicit source observation"),
            ({"date_semantics": ""}, {}, "date semantics"),
            ({"retrieved_at": "2026-09-28T08:00:00Z"}, {}, "capture predates observation"),
            ({"kind": "news"}, {}, "primary source"),
            ({"kind": "map"}, {}, "primary source"),
            ({"source_observation_date": "2026-10-14"}, {"as_of": "2026-10-14"}, "future status"),
            ({"source_observation_date": "2026-01-01"}, {"as_of": "2026-01-01"}, "older than 90"),
        ]
        for source_changes, status_changes, error in cases:
            with self.subTest(source=source_changes, status=status_changes):
                self.sources["sources"][0] = {**valid_source, **source_changes}
                self.spec["additions"][0]["status"] = {**valid_status, **status_changes}
                with self.assertRaisesRegex(UpdateError, error):
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

    def test_reviewed_status_transition_promotes_the_project_and_site_in_v2(self):
        addition = self.spec["additions"][0]
        addition.update(name="Example — announced conversion")
        addition["status"]["value"] = "announced"
        original = self.prepare_existing_campus()
        self.spec["additions"] = []
        self.sources["sources"][0].update(published_at="2026-10-01", content_hash=hashlib.sha256(b"new report").hexdigest())
        planned = original["verification_posture"]
        physical = "authoritative_physical_observation_plus_reviewed_site_locator"
        for version, group, value, name, posture in (
            ("v1", "status_updates", "under_construction", None, planned),
            ("v2", "status_updates", "under_construction", "Example conversion", physical),
            ("v2", "status_corrections", "completed", None, physical),
            ("v2", "status_updates", "paused", None, planned),
        ):
            with self.subTest(version=version, group=group, status=value):
                self.spec["format"] = "datacenter-atlas-update-input-" + version
                action = {"project_stable_key": original["project_stable_key"],
                          "identity_review": "Same campus conversion.", "successor_review": "Latest report.",
                          "status": {"value": value, "as_of": "2026-10-01", "source_id": "work",
                                     "summary": f"The operator reports the conversion is {value}."}}
                if name:
                    action["name"] = name
                if group == "status_corrections":
                    action.update(replaces_status_evidence_id=original["status_evidence_id"], reason="Reviewed operator report.")
                self.spec[group] = [action]
                payloads, _ = self.payloads()
                del self.spec[group]
                project = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                               if row["project_id"] == original["project_id"])
                site = next(row for row in csv.DictReader(io.StringIO(payloads["sites.csv"].decode()))
                            if row["site_id"] == original["site_id"])
                self.assertEqual((project["name"], project["verification_posture"]), (name or original["name"], posture))
                self.assertEqual((site["name"], site["verification_posture"]), ("Example campus", posture))
                self.assertEqual(project["geometry_evidence_id"], original["geometry_evidence_id"])

    def test_status_action_requires_a_valid_v2_project_name_when_supplied(self):
        original = next(csv.DictReader((BASE / "projects.csv").read_text().splitlines()))
        action = {"project_stable_key": original["project_stable_key"], "status": self.spec["additions"][0]["status"],
                  "identity_review": "Same project.", "successor_review": "Latest report."}
        self.spec["status_updates"] = [action]
        for version, name, message in (("v1", "New name", "requires v2"), ("v2", " ", "project name"),
                                       ("v2", None, "project name"), ("v2", 123, "project name")):
            self.spec["format"] = "datacenter-atlas-update-input-" + version
            action["name"] = name
            with self.subTest(version=version, name=name), self.assertRaisesRegex(UpdateError, message):
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

    def test_map_features_in_one_download_keep_their_own_credit_and_license(self):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        download = self.sources["sources"][0]
        phases = self.spec["additions"]
        other = copy.deepcopy(phases[0])
        other.update(physical_site_stable_key="curated:second", project_stable_key="curated:second:construction")
        other["locator"]["geometry"]["coordinates"] = [-99.0, 30.2]
        phases.append(other)
        for phase, feature, provider, license_id in zip(
            phases, ("first", "second"), ("Provider A", "Provider B"), ("Apache-2.0", "CDLA-Permissive-2.0"), strict=True
        ):
            self.sources["sources"].append({
                **download, "id": feature, "source_feature_id": feature, "kind": "open_map",
                "title": f"Map feature {feature}", "license": license_id, "attribution": provider,
                "extraction": {"feature_id": feature, "source_license": license_id},
            })
            phase["locator"]["source_id"] = feature
        payloads, _ = self.payloads()
        evidence = {r["evidence_id"]: r for r in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
        projects = {r["project_stable_key"]: r for r in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}
        identity = f"{download['source_url']}#{download['content_hash']}"
        for phase, source in zip(phases, self.sources["sources"][1:], strict=True):
            row = projects[phase["project_stable_key"]]
            feature_id = str(uuid5(NAMESPACE_URL, identity + "#feature=" + source["source_feature_id"]))
            self.assertEqual(row["geometry_evidence_id"], feature_id)
            self.assertEqual(row["status_evidence_id"], str(uuid5(NAMESPACE_URL, identity)))
            self.assertEqual(json.loads(evidence[feature_id]["project_ids_json"]), [row["project_id"]])
            for key in ("source_url", "content_hash", "license", "attribution"):
                self.assertEqual(evidence[feature_id][key], source[key])
        self.assertIn(b"Provider B. Full licence in CDLA-Permissive-2.0.txt", payloads["ATTRIBUTION.txt"])

    def test_feature_scoped_sources_reject_mismatched_identity_license_or_reuse(self):
        source = self.sources["sources"][0]
        source.update(title="Map feature first", source_feature_id="first",
                      extraction={"feature_id": "first", "source_license": source["license"]})
        with self.assertRaisesRegex(UpdateError, "requires a v2 update"):
            self.payloads()
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        for patch_values, message in [
            ({"extraction": {}}, "match the extracted feature"),
            ({"source_feature_id": "different"}, "match the extracted feature"),
            ({"license": "Apache-2.0"}, "extracted feature license"),
            ({"title": "Map record", "content_hash_scope": "file for first"}, "published title or hash scope"),
            ({"reuse_evidence_id": "another-feature"}, "only reuse the same feature"),
        ]:
            with self.subTest(patch_values=patch_values), patch.dict(source, patch_values):
                with self.assertRaisesRegex(UpdateError, message):
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
        self.spec["withdrawal_note"] = "Experimental installations are outside the inventory scope; no physical status change is inferred."
        payloads, _ = self.payloads()
        self.assertEqual(json.loads(payloads["selection-report.json"])["withdrawal_note"], self.spec["withdrawal_note"])
        self.spec["withdrawals"][0]["replaces_status_evidence_id"] = "wrong"
        with self.assertRaisesRegex(UpdateError, "name the removed status evidence"):
            self.payloads()


class NewCampusAdmissionTests(unittest.TestCase):
    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def setUp(self):
        DatasetUpdateTests.setUp(self)
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        first = self.spec["additions"][0]
        first["site_identity_review"] = "The first building is part of the named campus."
        for name in ("survey", "address", "deed", "announcement"):
            self.sources["sources"].append({**self.sources["sources"][0], "id": name,
                                           "source_url": f"https://example.org/{name}"})
        first["locator"].update(source_id="survey", identity_source_ids=["address", "deed"])
        second = copy.deepcopy(first)
        second.update(project_stable_key="curated:test-campus:phase2", name="Second building",
                      site_identity_review="The announced second building shares the same campus parcel.")
        second["status"].update(value="announced", as_of="2026-09-18", source_id="announcement",
                                summary="The developer announced a second building on the campus.")
        second["locator"]["identity_source_ids"].reverse()
        self.spec["additions"].append(second)

    def prepare_duplicate_review(self):
        first, second = self.spec["additions"]
        self.write()
        out = self.root / "campus"
        manifest = build_update(self.input, out, root=self.root)
        with (out / "projects.csv").open() as stream:
            rows = {r["project_stable_key"]: r for r in csv.DictReader(stream)}
        original, repeated = (rows[action["project_stable_key"]] for action in (first, second))
        self.spec.update(additions=[], base_dataset="campus",
                         base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
        self.spec["withdrawals"] = [{
            "project_stable_key": repeated["project_stable_key"], "duplicate_of": original["project_stable_key"],
            "replaces_status_evidence_id": repeated["status_evidence_id"], "reason": "Same building and phase.", "source_ids": ["work"],
        }]
        return original, repeated, manifest

    def test_duplicate_with_a_water_measurement_must_retain_it_on_the_surviving_project(self):
        first, second = self.spec["additions"]
        second["status"] = copy.deepcopy(first["status"])
        self.sources["sources"][0].update(source_reporting_period="2025", date_semantics="Calendar year 2025.")
        water = {"project_stable_key": second["project_stable_key"], "source_id": "work",
                 "metric": "annual_water_consumption_m3", "stage": "measured", "as_of_date": "2025-12-31",
                 "target_date": None, "low": 0, "base": 0, "high": 0, "unit": "m³/year",
                 "method": "reported", "confidence": 1, "notes": "Reported facility water consumption."}
        self.spec["annual_water_observations"] = [water]
        keeper, duplicate, _ = self.prepare_duplicate_review()
        del self.spec["annual_water_observations"]
        with self.assertRaisesRegex(UpdateError, "distinct project field: annual_water_observations_json"):
            self.payloads()
        self.spec["annual_water_observations"] = [{**water, "project_stable_key": keeper["project_stable_key"]}]
        payloads, _ = self.payloads()
        projects = {row["project_id"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}
        self.assertNotIn(duplicate["project_id"], projects)
        self.assertEqual(projects[keeper["project_id"]]["annual_water_observations_json"],
                         duplicate["annual_water_observations_json"])

    def test_withdraw_duplicate_preserves_campus_source_links_and_original_project(self):
        first, second = self.spec["additions"]
        second["status"] = copy.deepcopy(first["status"])
        original, repeated, manifest = self.prepare_duplicate_review()
        payloads, corrected = self.payloads()
        projects = list(csv.DictReader(io.StringIO(payloads["projects.csv"].decode())))
        self.assertIn(original, projects)
        self.assertNotIn(repeated["project_id"], {r["project_id"] for r in projects})
        self.assertEqual(corrected["counts"]["projects"], manifest["counts"]["projects"] - 1)
        self.assertEqual(corrected["counts"]["physical_sites"], manifest["counts"]["physical_sites"])
        self.assertEqual(corrected["counts"]["evidence"], manifest["counts"]["evidence"])
        site = next(r for r in csv.DictReader(io.StringIO(payloads["sites.csv"].decode())) if r["site_id"] == original["site_id"])
        self.assertEqual(site["project_count"], "1")
        self.assertEqual(json.loads(site["project_ids_json"]), [original["project_id"]])
        self.assertEqual(json.loads(site["project_stable_keys_json"]), [original["project_stable_key"]])
        feature = next(f for f in json.loads(payloads["sites.geojson"])["features"] if f["id"] == site["site_id"])
        self.assertEqual(feature["properties"]["project_count"], 1)
        self.assertEqual(feature["properties"]["statuses"], [original["last_observed_physical_status"]])
        self.assertEqual(feature["properties"]["newest_status_as_of"], original["status_as_of"])
        self.assertEqual(json.loads(payloads["selection-report.json"])["duplicate_project_replacements"],
                         {repeated["project_id"]: original["project_id"]})
        for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode())):
            self.assertNotIn(repeated["project_id"], json.loads(row["project_ids_json"]))
        withdrawal = self.spec["withdrawals"][0]
        withdrawal["source_ids"] = ["announcement"]
        with self.assertRaisesRegex(UpdateError, "cite evidence linked to the retained project"):
            self.payloads()
        withdrawal.update(duplicate_of=repeated["project_stable_key"], source_ids=["work"])
        with self.assertRaisesRegex(UpdateError, "surviving baseline project"):
            self.payloads()

    def test_withdraw_duplicate_rejects_distinct_phase_observations(self):
        self.prepare_duplicate_review()
        with self.assertRaisesRegex(UpdateError, "distinct project field"):
            self.payloads()

    def test_withdraw_duplicate_rejects_unique_evidence(self):
        first, second = self.spec["additions"]
        second["status"] = copy.deepcopy(first["status"])
        second["context_source_ids"] = ["announcement"]
        self.prepare_duplicate_review()
        with self.assertRaisesRegex(UpdateError, "evidence absent from retained project"):
            self.payloads()

    def test_members_share_one_site_and_keep_their_own_evidence_and_dates(self):
        payloads, manifest = self.payloads()
        self.spec["additions"].reverse()
        reversed_payloads, _ = self.payloads()
        for filename in ("sites.csv", "sites.geojson", "projects.csv", "evidence.csv", "selection-report.json"):
            self.assertEqual(payloads[filename], reversed_payloads[filename], filename)

        key = "curated:test-campus"
        def rows(name):
            return list(csv.DictReader(io.StringIO(payloads[name].decode())))
        site, = (r for r in rows("sites.csv") if r["physical_site_stable_key"] == key)
        members = [r for r in rows("projects.csv") if r["site_id"] == site["site_id"]]
        by_id = {r["project_id"]: r for r in members}
        self.assertEqual(manifest["counts"]["physical_sites"], 200)
        self.assertEqual((site["project_count"], len(members)), ("2", 2))
        self.assertEqual(set(json.loads(site["project_ids_json"])), set(by_id))
        self.assertEqual(set(json.loads(site["project_stable_keys_json"])), {r["project_stable_key"] for r in members})
        self.assertEqual((site["oldest_status_as_of"], site["newest_status_as_of"]), ("2026-09-18", "2026-09-21"))
        self.assertEqual(json.loads(site["statuses_json"]), ["announced", "site_preparation"])
        self.assertEqual(site["verification_posture"], "mixed_review_postures")
        feature, = (r for r in json.loads(payloads["sites.geojson"])["features"] if r["id"] == site["site_id"])
        self.assertEqual(feature["properties"]["statuses"], ["announced", "site_preparation"])
        self.assertEqual(feature["properties"]["project_count"], 2)
        self.assertEqual(feature["geometry"], json.loads(site["geometry_json"]))
        report = json.loads(payloads["selection-report.json"])
        self.assertEqual(report["added_sites"], [key])
        self.assertNotIn("expanded_sites", report)
        evidence = {r["evidence_id"]: r for r in rows("evidence.csv")}
        for r in members:
            self.assertEqual(json.loads(evidence[r["status_evidence_id"]]["project_ids_json"]), [r["project_id"]])
        locator_ids = []
        for source in evidence.values():
            if source["source_url"] in {"https://example.org/address", "https://example.org/deed"}:
                self.assertIn("context:geometry_identity", json.loads(source["roles_json"]))
                self.assertEqual(set(json.loads(source["project_ids_json"])), set(by_id))
                locator_ids.append(source["evidence_id"])
        self.assertEqual(len(locator_ids), 2)

        # A later phase can inherit the complete locator from either original member.
        out = self.root / "campus"
        built = build_update(self.input, out, root=self.root)
        self.assertEqual(validate_update(self.input, out, root=self.root), built)
        action = self.spec["additions"][0]
        action.update(project_stable_key="curated:test-campus:phase3", existing_site_id=site["site_id"])
        self.spec.update(additions=[action], base_dataset="campus",
                         base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
        for donor in members:
            action["locator"] = {"reuse_from_project_id": donor["project_id"], "scope": "campus_locator",
                                 "identity_review": "The third phase is on the same parcel.",
                                 "geometry_evidence_id": donor["geometry_evidence_id"],
                                 "geometry_identity_evidence_ids": locator_ids}
            after, _ = self.payloads()
            report = json.loads(after["selection-report.json"])
            self.assertEqual((report["added_sites"], report["expanded_sites"]), ([], [key]))
            self.assertTrue(all(len(json.loads(r["project_ids_json"])) == 3 for r in
                                csv.DictReader(io.StringIO(after["evidence.csv"].decode())) if r["evidence_id"] in locator_ids))

    def test_all_members_require_matching_identity_and_explicit_campus_provenance(self):
        self.spec["format"] = "datacenter-atlas-update-input-v1"
        with self.assertRaisesRegex(UpdateError, "requires v2"):
            self.payloads()
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        first, second = self.spec["additions"]
        for item_change, locator_change, error in [
            ({"site_identity_review": ""}, {}, "site identity review"),
            ({"existing_site_id": "invented"}, {}, "existing site ID"),
            ({"site_name": "Another estate"}, {}, "name and country"),
            ({"country_iso_a2": "CA"}, {}, "name and country"),
            ({}, {"scope": "project_locator"}, "explicit campus locators"),
            ({}, {"reuse_from_project_id": "invented"}, "explicit campus locators"),
            ({}, {"geometry": {"type": "Point", "coordinates": [-100.11, 30.2]}}, "same locator"),
            ({}, {"source_id": "deed"}, "same locator"),
            ({}, {"precision": "Different precision"}, "same locator"),
            ({}, {"horizontal_uncertainty_metres": 50}, "same locator"),
            ({}, {"identity_source_ids": ["address"]}, "same locator"),
        ]:
            modified = {**second, **item_change, "locator": {**second["locator"], **locator_change}}
            for pair in ([first, modified], [modified, first]):
                with self.subTest(changes=(item_change, locator_change), first=pair[0]["name"]):
                    self.spec["additions"] = pair
                    with self.assertRaisesRegex(UpdateError, error):
                        self.payloads()


class InheritedCampusLocatorTests(unittest.TestCase):
    """Exercise the actual legacy Shiroi polygon and evidence, not a reimported facsimile."""

    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def setUp(self):
        DatasetUpdateTests.setUp(self)
        self.baseline = ROOT / "verified_construction_core/2026-10-14-research-ninth"
        shutil.copytree(self.baseline, self.root / "ninth")
        self.tables = {name: list(csv.DictReader(io.StringIO((self.baseline / name).read_text())))
                       for name in ("sites.csv", "projects.csv", "evidence.csv")}
        self.reference = next(row for row in self.tables["projects.csv"]
                              if row["project_id"] == "1f33fed8-b0f9-50e2-8fac-56d135325c27")
        self.site = next(row for row in self.tables["sites.csv"] if row["site_id"] == self.reference["site_id"])
        self.identity_id = "846dc1a1-5268-544e-92c2-2df087877703"
        source_ids = {"jp-ninth-iij-matsue-operating-inventory-ja", "jp-ninth-iij-matsue-operating-inventory-en",
                      "jp-ninth-iij-financial-library"}
        packet = json.loads((ROOT / "sources/research-countries-2026-10-14-jp-ninth-iij-primary-sources.json").read_bytes())
        self.sources = {"sources": [source for source in packet["sources"] if source["id"] in source_ids]}
        self.spec.update(updated_at="2026-10-14", base_dataset="ninth",
                         base_manifest_sha256=hashlib.sha256((self.baseline / "manifest.json").read_bytes()).hexdigest())
        self.addition = {
            "project_stable_key": "curated:iij-shiroi-data-center-campus:existing-operations",
            "physical_site_stable_key": self.reference["physical_site_stable_key"],
            "existing_site_id": self.site["site_id"], "site_name": self.site["name"],
            "country": "Japan", "country_iso_a2": "JP", "name": "IIJ Shiroi Existing Operations (Phases 1 and 2)",
            "site_identity_review": "Same Shiroi campus, operating phases distinct from Phase 3 construction.",
            "distinctness_review": "Existing operations at the same campus; Phase 3 remains a separate project.",
            "successor_review": "August inventory explicitly separates existing operations and Phase 3.",
            "status": {"value": "operational", "as_of": "2026-08-07", "source_id": "jp-ninth-iij-matsue-operating-inventory-ja",
                       "summary": "The August inventory confirms operation of Shiroi Phases 1 and 2."},
            "locator": {"reuse_from_project_id": self.reference["project_id"],
                        "geometry_evidence_id": self.reference["geometry_evidence_id"],
                        "geometry_identity_evidence_ids": [self.identity_id], "scope": "campus_locator",
                        "identity_review": "Retain the reviewed broad Sakuradai 5-chome address-area locator and all caveats."},
            "roles": [{"party": "Internet Initiative Japan", "role": role, "relationship_scope": "current",
                       "source_id": "jp-ninth-iij-matsue-operating-inventory-ja"} for role in ("owner", "operator")],
            "context_source_ids": ["jp-ninth-iij-matsue-operating-inventory-en", "jp-ninth-iij-financial-library"],
        }
        self.spec["additions"] = [copy.deepcopy(self.addition)]

    def replace_baseline_table(self, name, rows):
        """Repin a corrupted baseline fixture so inheritance itself must reject it."""
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, fieldnames=list(self.tables[name][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        raw = out.getvalue().encode()
        (self.root / "ninth" / name).write_bytes(raw)
        manifest_path = self.root / "ninth/manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        manifest_path.write_text(json.dumps(manifest))
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        (manifest_path.parent / "manifest.sha256").write_text(digest + "  manifest.json\n")
        self.spec["base_manifest_sha256"] = digest

    def test_shiroi_preserves_polygon_legacy_evidence_and_independent_phase(self):
        payloads, manifest = self.payloads()
        self.assertEqual(manifest["counts"]["physical_sites"], 412)
        self.assertEqual(manifest["counts"]["projects"], 438)
        self.assertEqual(manifest["counts"]["evidence"], 2192)
        projects = {row["project_id"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}
        for original in self.tables["projects.csv"]:
            self.assertEqual(projects[original["project_id"]], original)
        added = next(row for row in projects.values() if row["project_stable_key"] == self.addition["project_stable_key"])
        self.assertEqual(added["last_observed_physical_status"], "operational")
        self.assertEqual(added["status_as_of"], "2026-08-07")
        for field in self.reference:
            if field.startswith("geometry_") or field.startswith("horizontal_uncertainty") or field in {"latitude", "longitude"}:
                self.assertEqual(added[field], self.reference[field], field)
        self.assertEqual(added["geometry_type"], "Polygon")
        self.assertEqual(added["geometry_source_entity_kind"], "address_area")
        self.assertEqual((added["longitude"], added["latitude"]), ("140.099553", "35.799113"))
        for field in ("power_observations_json", "annual_energy_observations_json", "efficiency_observations_json", "workloads_json", "project_details_json"):
            self.assertEqual(added[field], "[]")
        self.assertEqual(added["independent_imagery_verification"], "false")
        site = next(row for row in csv.DictReader(io.StringIO(payloads["sites.csv"].decode())) if row["site_id"] == self.site["site_id"])
        self.assertEqual(site["project_count"], "2")
        self.assertEqual(json.loads(site["statuses_json"]), ["operational", "under_construction"])
        for field in self.site:
            if field.startswith("geometry_") or field.startswith("horizontal_uncertainty") or field in {"latitude", "longitude"}:
                self.assertEqual(site[field], self.site[field], field)
        evidence = {row["evidence_id"]: row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
        selected_ids = {self.reference["geometry_evidence_id"], self.identity_id}
        selected_ids.update(str(uuid5(NAMESPACE_URL, source["source_url"] + "#" + source["content_hash"]))
                            for source in self.sources["sources"])
        for original in self.tables["evidence.csv"]:
            expected = copy.deepcopy(original)
            if original["evidence_id"] in selected_ids:
                expected["project_ids_json"] = json.dumps(sorted(set(json.loads(original["project_ids_json"])) | {added["project_id"]}), separators=(",", ":"))
            self.assertEqual(evidence[original["evidence_id"]], expected)
        for evidence_id in (self.reference["geometry_evidence_id"], self.identity_id):
            self.assertEqual(evidence[evidence_id]["retrieved_at"], "2026-08-23")
        feature = next(feature for feature in json.loads(payloads["sites.geojson"])["features"] if feature["id"] == self.site["site_id"])
        self.assertEqual(feature["geometry"], json.loads(self.site["geometry_json"]))
        self.assertEqual(feature["properties"]["project_count"], 2)
        out = self.root / "2026-10-14-shiroi-test"
        out.mkdir()
        for name, raw in payloads.items():
            (out / name).write_bytes(raw)
        atlas = public_site.load_atlas(public_site._load_version(out), "https://example.org")
        self.assertEqual(len(atlas.projects_by_site[self.site["site_id"]]), 2)
        self.assertEqual(atlas.site_by_id[self.site["site_id"]]["geometry"], feature["geometry"])
        self.assertTrue(selected_ids <= {row["evidence_id"] for row in atlas.evidence_by_project[added["project_id"]]})

    def test_reuse_requires_explicit_baseline_site_and_project(self):
        wrong_project = next(row for row in self.tables["projects.csv"] if row["site_id"] != self.site["site_id"])
        for changes, message in (
            ({"existing_site_id": None}, "explicit matching"),
            ({"existing_site_id": "wrong"}, "explicit matching"),
            ({"site_identity_review": ""}, "site identity review"),
            ({"site_name": "Wrong campus"}, "name and country"),
            ({"country": "China"}, "name and country"),
            ({"country_iso_a2": "CN"}, "name and country"),
            ({"physical_site_stable_key": "new-site", "existing_site_id": None}, "existing baseline site"),
            ({"locator": {**self.addition["locator"], "reuse_from_project_id": ""}}, "project reference"),
            ({"locator": {**self.addition["locator"], "reuse_from_project_id": "unknown"}}, "baseline project"),
            ({"locator": {**self.addition["locator"], "reuse_from_project_id": wrong_project["project_id"]}}, "same baseline site"),
        ):
            with self.subTest(changes=changes):
                self.spec["additions"] = [{**self.addition, **changes}]
                with self.assertRaisesRegex(UpdateError, message):
                    self.payloads()
        first = copy.deepcopy(self.addition)
        second = copy.deepcopy(self.addition)
        second["project_stable_key"] += ":later"
        second["locator"]["reuse_from_project_id"] = str(uuid5(NAMESPACE_URL, first["project_stable_key"]))
        self.spec["additions"] = [first, second]
        with self.assertRaisesRegex(UpdateError, "baseline project"):
            self.payloads()

    def test_reuse_rejects_missing_or_substituted_evidence_and_overrides(self):
        valid = self.addition["locator"]
        cases = [
            ({**valid, "geometry_evidence_id": "wrong"}, "must match"),
            ({**valid, "geometry_identity_evidence_ids": ["unknown"]}, "exist in the baseline"),
            ({**valid, "geometry_identity_evidence_ids": [self.reference["status_evidence_id"]]}, "association and geometry role"),
            ({**valid, "geometry_identity_evidence_ids": [self.identity_id, self.identity_id]}, "unique list"),
            ({**valid, "geometry_identity_evidence_ids": []}, "pin all baseline"),
            ({**valid, "scope": "official_boundary"}, "campus scope"),
            ({**valid, "identity_review": ""}, "locator identity review"),
        ]
        for field, message in (("reuse_from_project_id", "explicit baseline project reference"),
                               ("geometry_evidence_id", "geometry evidence ID"),
                               ("geometry_identity_evidence_ids", "explicit unique list")):
            cases.append(({key: value for key, value in valid.items() if key != field}, message))
        for field in ("geometry", "latitude", "longitude", "source_id", "method", "derivation", "authority",
                      "precision", "scope_class", "horizontal_uncertainty_metres", "uncertainty_reason"):
            cases.append(({**valid, field: "override"}, "does not permit"))
        for locator, message in cases:
            with self.subTest(locator=locator):
                self.spec["additions"] = [{**self.addition, "locator": locator}]
                with self.assertRaisesRegex(UpdateError, message):
                    self.payloads()

    def test_reuse_rejects_invalid_baseline_evidence_roles_associations_and_urls(self):
        for evidence_id in (self.reference["geometry_evidence_id"], self.identity_id):
            for field, value, message in ((None, None, "exist in the baseline"),
                                          ("roles_json", "[]", "association and geometry role"),
                                          ("project_ids_json", "[]", "association and geometry role")):
                with self.subTest(evidence=evidence_id, field=field):
                    rows = copy.deepcopy(self.tables["evidence.csv"])
                    if field is None:
                        rows = [row for row in rows if row["evidence_id"] != evidence_id]
                    else:
                        next(row for row in rows if row["evidence_id"] == evidence_id)[field] = value
                    self.replace_baseline_table("evidence.csv", rows)
                    with self.assertRaisesRegex(UpdateError, message):
                        self.payloads()
        rows = copy.deepcopy(self.tables["evidence.csv"])
        next(row for row in rows if row["evidence_id"] == self.reference["geometry_evidence_id"])["source_url"] = "https://example.org/wrong-map"
        self.replace_baseline_table("evidence.csv", rows)
        with self.assertRaisesRegex(UpdateError, "source URL"):
            self.payloads()

    def test_evidence_introduced_earlier_in_update_cannot_backfill_baseline_locator(self):
        new_source = {**self.sources["sources"][0], "id": "new-map", "source_url": "https://example.org/new-map"}
        self.sources["sources"].append(new_source)
        new_evidence_id = str(uuid5(NAMESPACE_URL, new_source["source_url"] + "#" + new_source["content_hash"]))
        rows = copy.deepcopy(self.tables["projects.csv"])
        reference = next(row for row in rows if row["project_id"] == self.reference["project_id"])
        reference.update(geometry_evidence_id=new_evidence_id, geometry_source_url=new_source["source_url"])
        self.replace_baseline_table("projects.csv", rows)
        rows = copy.deepcopy(self.tables["sites.csv"])
        next(row for row in rows if row["site_id"] == self.site["site_id"])["geometry_evidence_ids_json"] = json.dumps([new_evidence_id])
        self.replace_baseline_table("sites.csv", rows)
        first = copy.deepcopy(self.addition)
        first.update(project_stable_key="curated:new-campus:operations", physical_site_stable_key="curated:new-campus")
        first.pop("existing_site_id")
        first["locator"] = {
            "geometry": {"type": "Point", "coordinates": [130, 30]}, "source_id": "new-map",
            "scope": "campus_locator", "scope_class": "official_address_point", "authority": "official_source",
            "method": "official_address", "precision": "Campus locator only.",
            "identity_review": "Separate named campus.", "uncertainty_reason": "No accuracy stated.",
        }
        second = copy.deepcopy(self.addition)
        second["locator"]["geometry_evidence_id"] = new_evidence_id
        self.spec["additions"] = [first, second]
        with self.assertRaisesRegex(UpdateError, "exist in the baseline"):
            self.payloads()

    def test_reuse_rejects_incoherent_baseline_geometry_and_provenance(self):
        fields = ("latitude", "longitude", "geometry_json", "geometry_type", "horizontal_uncertainty_metres",
                  "horizontal_uncertainty_unknown_reason")
        provenance = tuple(field for field in self.site if field.startswith("geometry_") and field.endswith("_json"))
        for field in fields + provenance:
            with self.subTest(field=field):
                rows = copy.deepcopy(self.tables["sites.csv"])
                next(row for row in rows if row["site_id"] == self.site["site_id"])[field] = '["changed"]' if field in provenance else "changed"
                self.replace_baseline_table("sites.csv", rows)
                with self.assertRaisesRegex(UpdateError, "must agree exactly"):
                    self.payloads()
        self.replace_baseline_table("sites.csv", self.tables["sites.csv"])
        for field, value, message in (("geometry_use_scope", "official_boundary", "campus scope"),
                                      ("geometry_type", "MultiPolygon", "Point or Polygon")):
            rows = copy.deepcopy(self.tables["projects.csv"])
            next(row for row in rows if row["project_id"] == self.reference["project_id"])[field] = value
            self.replace_baseline_table("projects.csv", rows)
            with self.assertRaisesRegex(UpdateError, message):
                self.payloads()

    def test_inheritance_keeps_freshness_and_new_geometry_admission_gates(self):
        for observed, message in (("2026-07-01", "older than 90"), ("2026-10-15", "future")):
            with self.subTest(observed=observed):
                self.spec["additions"][0]["status"]["as_of"] = observed
                with self.assertRaisesRegex(UpdateError, message):
                    self.payloads()
        self.spec["additions"] = [copy.deepcopy(self.addition)]
        self.sources["sources"].append({**self.sources["sources"][0], "id": "unreviewed-status", "kind": "news",
                                        "source_url": "https://example.org/unreviewed-status"})
        self.spec["additions"][0]["status"]["source_id"] = "unreviewed-status"
        with self.assertRaisesRegex(UpdateError, "primary source"):
            self.payloads()
        self.spec["additions"] = [copy.deepcopy(self.addition)]
        addition = self.spec["additions"][0]
        addition.pop("existing_site_id")
        addition["physical_site_stable_key"] = "curated:new-polygon"
        addition["locator"] = {"geometry": json.loads(self.reference["geometry_json"])}
        with self.assertRaisesRegex(UpdateError, "new point admissions only"):
            self.payloads()

    def test_roles_use_published_role_and_relationship_scope_codes(self):
        for scope in ("current", "intended", "unknown"):
            with self.subTest(scope=scope):
                self.spec["additions"] = [copy.deepcopy(self.addition)]
                for role in self.spec["additions"][0]["roles"]:
                    role["relationship_scope"] = scope
                payloads, _ = self.payloads()
                added = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                             if row["project_stable_key"] == self.addition["project_stable_key"])
                self.assertEqual({claim["relationship_scope"] for claim in json.loads(added["role_claims_json"])}, {scope})
        for field, value, expected in (("relationship_scope", "intended; consent applicant", "unknown relationship scope"),
                                       ("relationship_scope", "Current", "unknown relationship scope"),
                                       ("role", "developer", "unknown party role")):
            with self.subTest(field=field, value=value):
                self.spec["additions"] = [copy.deepcopy(self.addition)]
                self.spec["additions"][0]["roles"][0][field] = value
                with self.assertRaisesRegex(UpdateError, expected):
                    self.payloads()


class InheritedGeometryBundleTests(unittest.TestCase):
    """One primary point and two coordinate-contract sources from the real Yguazú baseline."""

    BASELINE = ROOT / "verified_construction_core/2026-11-11-research-hundredsixtieth"
    REFERENCE_ID = "20a32e9d-3c57-520d-aeb8-ad999d43fee3"

    @classmethod
    def setUpClass(cls):
        cls.tables = {name: list(csv.DictReader(io.StringIO((cls.BASELINE / name).read_text())))
                      for name in ("sites.csv", "projects.csv", "evidence.csv")}

    def setUp(self):
        self.projects = {row["project_id"]: copy.deepcopy(row) for row in self.tables["projects.csv"]}
        self.evidence = {row["evidence_id"]: copy.deepcopy(row) for row in self.tables["evidence.csv"]}
        self.reference = self.projects[self.REFERENCE_ID]
        self.site = copy.deepcopy(next(row for row in self.tables["sites.csv"] if row["site_id"] == self.reference["site_id"]))
        self.geometry_ids = json.loads(self.site["geometry_evidence_ids_json"])
        self.identity_ids = sorted(key for key, row in self.evidence.items()
                                   if self.REFERENCE_ID in json.loads(row["project_ids_json"])
                                   and "context:geometry_identity" in json.loads(row["roles_json"]))
        self.locator = {"reuse_from_project_id": self.REFERENCE_ID,
                        "geometry_evidence_id": self.reference["geometry_evidence_id"],
                        "geometry_evidence_ids": self.geometry_ids, "geometry_identity_evidence_ids": self.identity_ids,
                        "scope": "campus_locator", "identity_review": "Same combined Zunz data-centre/substation campus."}

    def inherit(self, locator=None):
        return _inherited_campus_locator(self.locator if locator is None else locator,
                                         self.site, self.projects, self.evidence)

    def test_bundle_requires_explicit_complete_unique_ids_and_primary(self):
        with self.assertRaisesRegex(UpdateError, "must agree exactly"):
            self.inherit({key: value for key, value in self.locator.items() if key != "geometry_evidence_ids"})
        for values, message in (
            (None, "nonempty unique list"), ([], "nonempty unique list"),
            (self.geometry_ids[0], "nonempty unique list"),
            ([*self.geometry_ids, self.geometry_ids[0]], "nonempty unique list"),
            ([*self.geometry_ids, " "], "nonempty unique list"), ([*self.geometry_ids, 1], "nonempty unique list"),
            (self.geometry_ids[1:], "include its primary"),
            (self.geometry_ids[:1], "exact baseline site bundle"),
            ([*self.geometry_ids, "unknown"], "exact baseline site bundle"),
        ):
            with self.subTest(values=values), self.assertRaisesRegex(UpdateError, message):
                self.inherit({**self.locator, "geometry_evidence_ids": values})

    def test_supporting_geometry_requires_baseline_row_role_and_donor(self):
        for evidence_id in self.geometry_ids:
            original = self.evidence[evidence_id]
            for field in (None, "roles_json", "project_ids_json"):
                with self.subTest(evidence_id=evidence_id, field=field):
                    if field is None:
                        del self.evidence[evidence_id]
                    else:
                        self.evidence[evidence_id] = {**original, field: "[]"}
                    with self.assertRaisesRegex(UpdateError, "exist in the baseline" if field is None else "association and geometry role"):
                        self.inherit()
                    self.evidence[evidence_id] = original

    def test_site_and_donor_geometry_bundles_must_agree_exactly(self):
        original = self.site["geometry_evidence_ids_json"]
        for values, message in ((self.geometry_ids[:1], "exact baseline site bundle"),
                                ([*self.geometry_ids, self.geometry_ids[0]], "nonempty unique list")):
            with self.subTest(values=values), self.assertRaisesRegex(UpdateError, message):
                self.site["geometry_evidence_ids_json"] = json.dumps(values)
                self.inherit()
        self.site["geometry_evidence_ids_json"] = original
        extra = self.evidence[self.reference["status_evidence_id"]]
        extra["roles_json"] = json.dumps([*json.loads(extra["roles_json"]), "geometry"])
        with self.assertRaisesRegex(UpdateError, "pin all baseline project geometry evidence"):
            self.inherit()

    def test_bundle_cannot_promote_unrelated_or_same_batch_sources(self):
        unrelated = next(row for row in self.evidence.values()
                         if self.REFERENCE_ID not in json.loads(row["project_ids_json"])
                         and "geometry" in json.loads(row["roles_json"]))
        for evidence_id, message in ((unrelated["evidence_id"], "association and geometry role"),
                                     ("new-in-this-update", "exist in the baseline")):
            with self.subTest(evidence_id=evidence_id), self.assertRaisesRegex(UpdateError, message):
                bundle = [*self.geometry_ids, evidence_id]
                self.site["geometry_evidence_ids_json"] = json.dumps(bundle)
                self.inherit({**self.locator, "geometry_evidence_ids": bundle})

    def test_bundle_preserves_scalar_provenance_and_source_url_guards(self):
        fields = ("latitude", "longitude", "geometry_json", "geometry_type", "horizontal_uncertainty_metres",
                  "horizontal_uncertainty_unknown_reason")
        fields += tuple(field for field in self.site if field.startswith("geometry_")
                        and field.endswith("_json") and field != "geometry_evidence_ids_json")
        for field in fields:
            original = self.site[field]
            with self.subTest(field=field), self.assertRaisesRegex(UpdateError, "must agree exactly"):
                self.site[field] = '["changed"]' if field.endswith("_json") else "changed"
                self.inherit()
            self.site[field] = original
        self.reference["geometry_source_url"] = "https://example.org/different-source"
        with self.assertRaisesRegex(UpdateError, "source URL must match"):
            self.inherit()

    def test_bundle_preserves_identity_scope_and_override_guards(self):
        other = next(row for row in self.projects.values() if row["site_id"] != self.site["site_id"])
        for change, message in (
            ({"geometry_evidence_id": self.geometry_ids[1]}, "must match the baseline project"),
            ({"geometry_identity_evidence_ids": []}, "pin all baseline geometry identity"),
            ({"geometry_identity_evidence_ids": [self.identity_ids[0]] * 2}, "explicit unique list"),
            ({"geometry_identity_evidence_ids": ["unknown"]}, "exist in the baseline"),
            ({"reuse_from_project_id": other["project_id"]}, "same baseline site"),
            ({"scope": "project_locator"}, "campus scope"), ({"identity_review": ""}, "locator identity review"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(UpdateError, message):
                self.inherit({**self.locator, **change})
        for field in ("geometry", "source_id", "method", "derivation", "authority", "precision", "horizontal_uncertainty_metres"):
            with self.subTest(field=field), self.assertRaisesRegex(UpdateError, "does not permit"):
                self.inherit({**self.locator, field: "override"})

    def test_actual_update_preserves_bundle_metadata_and_all_existing_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copytree(self.BASELINE, root / "base")
            packet = json.loads((ROOT / "sources/research-countries-2026-11-11-hundredsixtieth-primary-sources.json").read_bytes())
            source = next(row for row in packet["sources"] if row["id"] == "root160-hive-q2-10q")
            raw = json.dumps({"sources": [source]}).encode()
            (root / "source.json").write_bytes(raw)
            addition = {
                "project_stable_key": "curated:hive-yguazu-paraguay-campus:existing-operations",
                "physical_site_stable_key": self.reference["physical_site_stable_key"],
                "existing_site_id": self.site["site_id"], "site_name": self.site["name"],
                "name": "HIVE Yguazú existing operations", "country": "Paraguay", "country_iso_a2": "PY",
                "site_identity_review": "Same combined campus; existing operations are distinct from unfinished expansion.",
                "distinctness_review": "One existing site with an additional project, not a new campus.",
                "successor_review": "The November report separates active operations from ongoing expansion.",
                "status": {"value": "operational", "as_of": "2026-10-31", "source_id": source["id"],
                           "summary": "The October31 portfolio table reports actual operating equipment at Yguazú."},
                "locator": self.locator, "context_source_ids": [source["id"]],
                "roles": [{"party": "HIVE Digital Technologies Ltd.", "role": "owner", "relationship_scope": "current", "source_id": source["id"]}],
            }
            spec = {"format": "datacenter-atlas-update-input-v1", "updated_at": "2026-11-11", "base_dataset": "base",
                    "base_manifest_sha256": hashlib.sha256((self.BASELINE / "manifest.json").read_bytes()).hexdigest(),
                    "source_files": [{"path": "source.json", "sha256": hashlib.sha256(raw).hexdigest()}], "additions": [addition]}
            path = root / "input.json"
            path.write_text(json.dumps(spec))
            payloads, manifest = update_payloads(path, root=root)
            self.assertEqual((payloads, manifest), update_payloads(path, root=root))
            self.assertEqual([manifest["counts"][key] for key in ("physical_sites", "projects", "evidence")], [1315, 1428, 7373])
            projects = {row["project_id"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}
            for original in self.tables["projects.csv"]:
                self.assertEqual(projects[original["project_id"]], original)
            pid = str(uuid5(NAMESPACE_URL, addition["project_stable_key"]))
            site = next(row for row in csv.DictReader(io.StringIO(payloads["sites.csv"].decode())) if row["site_id"] == self.site["site_id"])
            for original, actual in ((self.reference, projects[pid]), (self.site, site)):
                for field in original:
                    if field.startswith(("geometry_", "horizontal_uncertainty")) or field in {"latitude", "longitude"}:
                        self.assertEqual(actual[field], original[field], field)
            selected = set(self.geometry_ids + self.identity_ids + [self.reference["status_evidence_id"]])
            self.assertEqual(len(selected), 11)
            evidence = {row["evidence_id"]: row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
            self.assertEqual(set(evidence), set(self.evidence))
            for original in self.tables["evidence.csv"]:
                expected = copy.deepcopy(original)
                if original["evidence_id"] in selected:
                    expected["project_ids_json"] = json.dumps(sorted(set(json.loads(original["project_ids_json"])) | {pid}), separators=(",", ":"))
                self.assertEqual(evidence[original["evidence_id"]], expected)
            feature = next(row for row in json.loads(payloads["sites.geojson"])["features"] if row["id"] == self.site["site_id"])
            self.assertEqual(feature["geometry"], json.loads(self.site["geometry_json"]))
            self.assertEqual(feature["properties"]["project_count"], 2)
            addition["locator"]["geometry_evidence_ids"] = list(reversed(self.geometry_ids))
            path.write_text(json.dumps(spec))
            reordered, _ = update_payloads(path, root=root)
            for name in ("sites.csv", "projects.csv", "evidence.csv", "sites.geojson", "source-records.json", "identity-mapping.json"):
                self.assertEqual(payloads[name], reordered[name], name)
            for observed, message in (("2026-07-01", "older than 90"), ("2026-11-12", "future")):
                addition["status"]["as_of"] = observed
                path.write_text(json.dumps(spec))
                with self.subTest(observed=observed), self.assertRaisesRegex(UpdateError, message):
                    update_payloads(path, root=root)


class RetainedImportedStatusTests(unittest.TestCase):
    """Imported partially_operational and proposed records: refreshed, never admitted or assigned."""

    BASELINE = ROOT / "verified_construction_core/2026-10-14-research-ninth"
    PARTIAL = "imported:semiconductor-atlas:riot-corsicana"
    PROPOSED = "imported:semiconductor-atlas:airtrunk-kurri-kurri"
    BUILDING = "imported:semiconductor-atlas:datavolt-oxagon"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(self.BASELINE, self.root / "ninth")
        self.base = {row["project_stable_key"]: row
                     for row in csv.DictReader(io.StringIO((self.BASELINE / "projects.csv").read_text()))}
        self.sources = {"sources": [{
            "id": "report", "kind": "company_disclosure", "title": "Quarterly project report",
            "source_url": "https://example.org/quarterly-report", "publisher": "Example Operator",
            "source_family": "example", "license": "all-rights-reserved", "attribution": "Example Operator",
            "published_at": "2026-10-01", "retrieved_at": "2026-10-02T08:00:00Z",
            "content_hash": hashlib.sha256(b"quarterly project report").hexdigest(),
            "summary": "The report states the project status.",
        }]}
        self.spec = {
            "format": "datacenter-atlas-update-input-v1", "updated_at": "2026-10-14", "base_dataset": "ninth",
            "base_manifest_sha256": hashlib.sha256((self.BASELINE / "manifest.json").read_bytes()).hexdigest(),
            "source_files": [], "status_updates": [],
        }
        self.input = self.root / "update.json"

    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def refresh(self, key, value, *, correction=False, **status):
        item = {"project_stable_key": key,
                "status": {"value": value, "as_of": "2026-10-01", "source_id": "report",
                           "summary": f"The operator reports the project as {value}.", **status},
                "identity_review": "Same named project and campus.", "successor_review": "No later report."}
        if correction:
            item.update(replaces_status_evidence_id=self.base[key]["status_evidence_id"], reason="Corrected source.")
            self.spec["status_corrections"] = [item]
        else:
            self.spec["status_updates"] = [item]

    def projects(self, payloads):
        return {row["project_stable_key"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}

    def test_partially_operational_record_refreshes_as_an_operating_status(self):
        self.assertEqual(self.base[self.PARTIAL]["last_observed_physical_status"], "partially_operational")
        self.refresh(self.PARTIAL, "partially_operational")
        payloads, manifest = self.payloads()
        row = self.projects(payloads)[self.PARTIAL]
        self.assertEqual((row["last_observed_physical_status"], row["status_as_of"]), ("partially_operational", "2026-10-01"))
        self.assertEqual(row["status_method"], "authoritative_physical_status_update")
        self.assertEqual(row["verification_posture"], self.base[self.PARTIAL]["verification_posture"])
        evidence = {item["evidence_id"]: item for item in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
        self.assertIn("physical_status", json.loads(evidence[row["status_evidence_id"]]["roles_json"]))
        self.assertIn(self.base[self.PARTIAL]["status_evidence_id"], evidence, "earlier evidence is retained")
        self.assertEqual(json.loads(payloads["selection-report.json"])["refreshed_projects"], [self.PARTIAL])
        out = self.root / "out"
        build_update(self.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.input, out, root=self.root))

    def test_proposed_record_is_refreshed_as_announced_never_as_proposed(self):
        # The published vocabulary defines the rule: a dated primary source identifying the project
        # establishes "announced", while "proposed" says that announcement is not established.
        vocabulary = json.loads((ROOT / "site/vocabulary.json").read_text())
        self.assertIn("announcement, permission or physical work is not established",
                      vocabulary["statuses"]["proposed"]["description"])
        self.assertIn("A dated primary source identifies the proposed data-centre project",
                      vocabulary["statuses"]["announced"]["description"])
        self.assertNotIn("authoritative_project_proposal", vocabulary["status_methods"])
        self.assertEqual(self.base[self.PROPOSED]["last_observed_physical_status"], "proposed")
        self.refresh(self.PROPOSED, "proposed")
        with self.assertRaisesRegex(UpdateError, "proposed means announcement, permission and physical work are not"):
            self.payloads()
        self.spec["status_updates"] = []
        self.refresh(self.PROPOSED, "announced")
        payloads, _ = self.payloads()
        row = self.projects(payloads)[self.PROPOSED]
        self.assertEqual((row["last_observed_physical_status"], row["status_as_of"]), ("announced", "2026-10-01"))
        self.assertEqual(row["status_method"], "authoritative_project_announcement")
        self.assertEqual(row["verification_posture"], "authoritative_project_record_plus_scoped_location")
        evidence = {item["evidence_id"]: item for item in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
        self.assertEqual(json.loads(evidence[row["status_evidence_id"]]["roles_json"]), ["announcement"])
        schema = json.loads(payloads["schema.json"])
        allowed = next(field["allowed_values"] for field in schema["tables"]["projects.csv"]["fields"]
                       if field["name"] == "last_observed_physical_status")
        # Codes that other imported records still carry stay documented in the schema.
        self.assertTrue({"proposed", "partially_operational"} <= set(allowed))

    def test_retained_records_can_move_to_other_statuses(self):
        self.refresh(self.PROPOSED, "announced")
        row = self.projects(self.payloads()[0])[self.PROPOSED]
        self.assertEqual((row["last_observed_physical_status"], row["status_method"]),
                         ("announced", "authoritative_project_announcement"))
        self.refresh(self.PARTIAL, "operational")
        self.assertEqual(self.projects(self.payloads()[0])[self.PARTIAL]["last_observed_physical_status"], "operational")

    def test_v2_construction_at_a_locality_does_not_claim_a_reviewed_site_locator(self):
        self.refresh(self.PROPOSED, "announced")
        self.write()
        baseline = self.root / "announced"
        build_update(self.input, baseline, root=self.root)
        self.spec.update(format="datacenter-atlas-update-input-v2", base_dataset="announced",
                         base_manifest_sha256=hashlib.sha256((baseline / "manifest.json").read_bytes()).hexdigest())
        self.sources["sources"][0].update(published_at="2026-10-12", retrieved_at="2026-10-12T08:00:00Z",
                                          content_hash=hashlib.sha256(b"construction report").hexdigest())
        self.refresh(self.PROPOSED, "under_construction", as_of="2026-10-12")
        project = self.projects(self.payloads()[0])[self.PROPOSED]
        self.assertEqual(project["geometry_use_scope"], "locality_context")
        self.assertEqual(project["verification_posture"], "authoritative_project_record_plus_scoped_location")

    def test_other_records_cannot_move_to_retained_statuses(self):
        messages = {"partially_operational": "retained imported status", "proposed": "proposed means announcement"}
        for value, message in messages.items():
            for correction in (False, True):
                with self.subTest(value=value, correction=correction):
                    self.spec.pop("status_updates", None)
                    self.spec.pop("status_corrections", None)
                    self.refresh(self.BUILDING, value, correction=correction)
                    with self.assertRaisesRegex(UpdateError, message):
                        self.payloads()
        self.spec.pop("status_corrections", None)
        self.refresh(self.PROPOSED, "partially_operational")
        with self.assertRaisesRegex(UpdateError, "retained imported status"):
            self.payloads()

    def test_retained_statuses_are_not_admission_statuses(self):
        reference = self.base[self.BUILDING]
        for value, message in (("partially_operational", "new admission needs"), ("proposed", "proposed means")):
            with self.subTest(value=value):
                self.spec["additions"] = [{
                    "project_stable_key": f"curated:new-{value}", "physical_site_stable_key": f"curated:new-{value}",
                    "site_name": "New campus", "name": "New project", "country": reference["country"],
                    "country_iso_a2": reference["country_iso_a2"],
                    "status": {"value": value, "as_of": "2026-10-01", "source_id": "report", "summary": "Reported."},
                    "locator": {"geometry": {"type": "Point", "coordinates": [10.0, 20.0]}, "source_id": "report",
                                "scope": "campus_locator", "scope_class": "official_address_point",
                                "authority": "official_source", "method": "official_address",
                                "precision": "Campus address point.", "identity_review": "Named campus.",
                                "uncertainty_reason": "No accuracy stated."},
                    "distinctness_review": "New campus.", "successor_review": "No later report.",
                }]
                with self.assertRaisesRegex(UpdateError, message):
                    self.payloads()

    def test_dated_entries_and_firsthand_reports_establish_partial_operation_never_proposed(self):
        source = self.sources["sources"][0]
        source.pop("published_at")
        source.update(source_observation_date="2026-10-01", source_observation_date_precision="day",
                      date_semantics="Dated project register entry.")
        # A dated operating-status entry can establish partial operation, as it can full operation.
        self.refresh(self.PARTIAL, "partially_operational")
        row = self.projects(self.payloads()[0])[self.PARTIAL]
        self.assertEqual(row["status_as_of"], "2026-10-01")
        self.spec["status_updates"] = []
        self.refresh(self.PROPOSED, "proposed")
        with self.assertRaisesRegex(UpdateError, "proposed means"):
            self.payloads()
        source.update(kind="news", published_at="2026-10-01")
        for key in ("source_observation_date", "source_observation_date_precision", "date_semantics"):
            source.pop(key)
        with self.assertRaisesRegex(UpdateError, "proposed means"):
            self.payloads()
        self.spec["status_updates"] = []
        self.refresh(self.PARTIAL, "partially_operational")
        with self.assertRaisesRegex(UpdateError, "primary source or reviewed firsthand"):
            self.payloads()


class LocatorCorrectionTests(unittest.TestCase):
    """An existing site's point is replaced from a better source; nothing else about it changes."""

    def setUp(self):
        self.case = DatasetUpdateTests("test_reproducible_with_real_baseline_and_unchanged_observation_dates")
        self.case.setUp()
        self.addCleanup(self.case.temp.cleanup)
        self.root = self.case.root
        map_source = {**self.case.sources["sources"][0], "id": "old-map", "kind": "map",
                      "title": "Map feature", "source_url": "https://maps.example.net/feature/1",
                      "content_hash": hashlib.sha256(b"old map feature").hexdigest()}
        self.old_map_source = copy.deepcopy(map_source)
        self.case.sources["sources"].append(map_source)
        first = self.case.spec["additions"][0]
        first["locator"]["source_id"] = "old-map"
        second = copy.deepcopy(first)
        second.update(project_stable_key="curated:test-campus:phase2", name="Example Phase 2")
        self.case.spec["additions"] = [first]
        self.case.write()
        build_update(self.case.input, self.root / "first", root=self.root)
        self.project = self.rows("first", "projects.csv")["curated:test-campus:construction"]
        self.base("first")
        self.case.spec["additions"] = []
        self.parcel = {**self.case.sources["sources"][0], "id": "parcel", "kind": "government_record",
                       "title": "Parcel record", "source_url": "https://gis.example.gov/parcels/42",
                       "publisher": "Example County", "license": "public-domain",
                       "content_hash": hashlib.sha256(b"parcel 42").hexdigest()}
        self.case.sources["sources"] = [self.case.sources["sources"][0], self.parcel]
        self.correction = {
            "physical_site_stable_key": "curated:test-campus", "site_id": self.project["site_id"],
            "replaces_geometry_evidence_id": self.project["geometry_evidence_id"],
            "reason": "The point was copied from a map service whose terms do not allow reuse.",
            "displacement_review": "About 147 m south-east of the old point; the county parcel is the named campus.",
            "locator": {"geometry": {"type": "Point", "coordinates": [-100.099, 30.199]}, "source_id": "parcel",
                        "scope": "campus_locator", "scope_class": "official_parcel_centroid", "authority": "official_source",
                        "method": "centroid_of_county_parcel_42", "precision": "Parcel centroid, not a building footprint.",
                        "horizontal_uncertainty_metres": 60,
                        "identity_review": "The county record names the operator and the campus address."},
        }
        self.second = second

    def rows(self, dataset, name, key="project_stable_key"):
        return {row[key]: row for row in csv.DictReader(io.StringIO((self.root / dataset / name).read_text()))}

    def base(self, dataset):
        self.case.spec.update(base_dataset=dataset, base_manifest_sha256=hashlib.sha256(
            (self.root / dataset / "manifest.json").read_bytes()).hexdigest())

    def corrected(self, **spec):
        self.case.spec.update(spec)
        self.case.spec["locator_corrections"] = [self.correction]
        payloads, manifest = self.case.payloads()
        tables = {name: list(csv.DictReader(io.StringIO(payloads[name].decode())))
                  for name in ("sites.csv", "projects.csv", "evidence.csv")}
        return payloads, manifest, tables

    def test_correction_replaces_point_and_provenance_and_drops_the_unused_capture(self):
        payloads, manifest, tables = self.corrected()
        project = next(row for row in tables["projects.csv"] if row["project_id"] == self.project["project_id"])
        site = next(row for row in tables["sites.csv"] if row["site_id"] == self.project["site_id"])
        new_id = str(uuid5(NAMESPACE_URL, f"{self.parcel['source_url']}#{self.parcel['content_hash']}"))
        self.assertEqual((project["latitude"], project["longitude"]), ("30.199", "-100.099"))
        self.assertEqual((site["latitude"], site["longitude"], site["geometry_json"]),
                         ("30.199", "-100.099", '{"coordinates":[-100.099,30.199],"type":"Point"}'))
        self.assertEqual(project["geometry_evidence_id"], new_id)
        self.assertEqual(project["geometry_source_url"], self.parcel["source_url"])
        self.assertEqual(project["geometry_method"], "centroid_of_county_parcel_42")
        self.assertEqual((project["horizontal_uncertainty_metres"], project["horizontal_uncertainty_unknown_reason"]), ("60", ""))
        self.assertEqual(json.loads(site["geometry_evidence_ids_json"]), [new_id])
        self.assertEqual(json.loads(site["geometry_methods_json"]), ["centroid_of_county_parcel_42"])
        for field in ("last_observed_physical_status", "status_as_of", "status_evidence_id", "name", "role_claims_json"):
            self.assertEqual(project[field], self.project[field], field)
        evidence = {row["evidence_id"]: row for row in tables["evidence.csv"]}
        self.assertNotIn(self.project["geometry_evidence_id"], evidence)
        self.assertEqual(json.loads(evidence[new_id]["roles_json"]), ["geometry"])
        self.assertEqual(manifest["counts"]["evidence"], len(self.rows("first", "evidence.csv", "evidence_id")))
        report = json.loads(payloads["selection-report.json"])
        self.assertEqual(report["corrected_locators"], [{
            "physical_site_stable_key": "curated:test-campus", "site_id": self.project["site_id"],
            "previous_geometry_evidence_id": self.project["geometry_evidence_id"], "geometry_evidence_id": new_id,
            "displacement_metres": 147.0}])
        feature = next(item for item in json.loads(payloads["sites.geojson"])["features"] if item["id"] == self.project["site_id"])
        self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [-100.099, 30.199]})

    def test_correction_keeps_a_shared_capture_for_its_other_roles(self):
        self.case.sources["sources"][0]["id"] = "work"
        self.case.spec["additions"] = []
        # Rebuild a base whose locator and status come from the same capture.
        self.case.spec.update(base_dataset="base", base_manifest_sha256=hashlib.sha256((BASE / "manifest.json").read_bytes()).hexdigest())
        addition = copy.deepcopy(self.second)
        addition.update(project_stable_key="curated:shared:construction", physical_site_stable_key="curated:shared",
                        site_name="Shared capture campus", name="Shared capture construction")
        addition["locator"]["source_id"] = "work"
        self.case.spec["additions"] = [addition]
        self.case.write()
        build_update(self.case.input, self.root / "shared", root=self.root)
        project = self.rows("shared", "projects.csv")["curated:shared:construction"]
        self.assertEqual(project["geometry_evidence_id"], project["status_evidence_id"])
        self.base("shared")
        self.case.spec["additions"] = []
        self.correction.update(physical_site_stable_key="curated:shared", site_id=project["site_id"],
                               replaces_geometry_evidence_id=project["geometry_evidence_id"])
        _, _, tables = self.corrected()
        evidence = {row["evidence_id"]: row for row in tables["evidence.csv"]}
        kept = evidence[project["status_evidence_id"]]
        self.assertEqual(json.loads(kept["roles_json"]), ["physical_status"])
        self.assertIn(project["project_id"], json.loads(kept["project_ids_json"]))

    def replace_first_tables(self, tables):
        manifest_path = self.root / "first/manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        for name, rows in tables.items():
            out = io.StringIO(newline="")
            writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            raw = out.getvalue().encode()
            (self.root / "first" / name).write_bytes(raw)
            manifest["files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        manifest_path.write_text(json.dumps(manifest))
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        (manifest_path.parent / "manifest.sha256").write_text(digest + "  manifest.json\n")
        self.base("first")

    def legacy_geometry_evidence(self):
        original_id = self.project["geometry_evidence_id"]
        legacy_id = str(uuid5(NAMESPACE_URL, "legacy:site-locator:original-row"))
        projects = self.rows("first", "projects.csv", "project_id")
        sites = self.rows("first", "sites.csv", "site_id")
        evidence = self.rows("first", "evidence.csv", "evidence_id")
        projects[self.project["project_id"]]["geometry_evidence_id"] = legacy_id
        sites[self.project["site_id"]]["geometry_evidence_ids_json"] = json.dumps([legacy_id])
        evidence[original_id]["evidence_id"] = legacy_id
        self.replace_first_tables({"projects.csv": list(projects.values()), "sites.csv": list(sites.values()),
                                   "evidence.csv": list(evidence.values())})
        self.project = projects[self.project["project_id"]]
        self.correction["replaces_geometry_evidence_id"] = legacy_id
        self.old_map_source.update(reuse_evidence_id=legacy_id,
                                   content_hash_scope=evidence[original_id].get("content_hash_scope", ""))

    def provenance_correction(self):
        self.case.sources["sources"].append(copy.deepcopy(self.old_map_source))
        self.correction.update(
            provenance_only=True,
            reason="The unchanged source point was projected; correct its derivation and authority.",
            displacement_review="The exact point, scope and uncertainty remain unchanged.",
            locator={**self.second["locator"], "derivation": "coordinate_transform",
                     "authority": "compiled_reference", "method": "published_native_point_inverse_projection"},
        )

    def test_provenance_only_preserves_geometry_evidence_and_reproduces(self):
        self.provenance_correction()
        before_files = {path.name: path.read_bytes() for path in (self.root / "first").iterdir()}
        payloads, manifest, tables = self.corrected()
        before = self.rows("first", "projects.csv", "project_id")
        changed_fields = {"geometry_derivation", "geometry_authority_class", "geometry_method"}
        for row in tables["projects.csv"]:
            prior = before[row["project_id"]]
            differences = {field for field in row if row[field] != prior[field]}
            self.assertEqual(differences, changed_fields if row["project_id"] == self.project["project_id"] else set())
        self.assertEqual({row["evidence_id"]: row for row in tables["evidence.csv"]},
                         self.rows("first", "evidence.csv", "evidence_id"))
        before_sites = self.rows("first", "sites.csv", "site_id")
        for row in tables["sites.csv"]:
            differences = {field for field in row if row[field] != before_sites[row["site_id"]][field]}
            self.assertEqual(differences, {"geometry_derivations_json", "geometry_authority_classes_json", "geometry_methods_json"}
                             if row["site_id"] == self.project["site_id"] else set())
        report = json.loads(payloads["selection-report.json"])["corrected_locators"][0]
        self.assertEqual(report["displacement_metres"], 0)
        self.assertEqual(report["previous_geometry_evidence_id"], report["geometry_evidence_id"])
        self.assertEqual(manifest["counts"]["evidence"], len(self.rows("first", "evidence.csv", "evidence_id")))
        out = self.root / "provenance"
        build_update(self.case.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.case.input, out, root=self.root))
        self.assertEqual(before_files, {path.name: path.read_bytes() for path in (self.root / "first").iterdir()})

    def test_provenance_only_retains_old_associations_when_adding_identity_context(self):
        self.provenance_correction()
        self.correction["locator"]["identity_source_ids"] = ["work"]
        _, _, tables = self.corrected()
        evidence = {row["evidence_id"]: row for row in tables["evidence.csv"]}
        prior = self.rows("first", "evidence.csv", "evidence_id")
        status_id = self.project["status_evidence_id"]
        expected = copy.deepcopy(prior)
        expected[status_id]["roles_json"] = json.dumps(
            sorted(set(json.loads(prior[status_id]["roles_json"])) | {"context:geometry_identity"}), separators=(",", ":"))
        self.assertEqual(evidence, expected)

    def test_provenance_corrected_snapshot_supports_a_later_inherited_phase(self):
        self.legacy_geometry_evidence()
        self.provenance_correction()
        self.correction["locator"]["identity_source_ids"] = ["work", "parcel"]
        self.corrected()
        build_update(self.case.input, self.root / "provenance", root=self.root)
        self.base("provenance")
        reference = self.rows("provenance", "projects.csv")[self.project["project_stable_key"]]
        before_projects = self.rows("provenance", "projects.csv", "project_id")
        before_evidence = self.rows("provenance", "evidence.csv", "evidence_id")
        identity_ids = sorted(identifier for identifier, row in before_evidence.items()
                              if reference["project_id"] in json.loads(row["project_ids_json"])
                              and "context:geometry_identity" in json.loads(row["roles_json"]))
        self.assertEqual(len(identity_ids), 2)
        phase = {**self.second, "existing_site_id": reference["site_id"],
                 "site_identity_review": "A separate phase on the same reviewed campus.",
                 "locator": {"reuse_from_project_id": reference["project_id"],
                             "geometry_evidence_id": reference["geometry_evidence_id"],
                             "geometry_identity_evidence_ids": identity_ids, "scope": "campus_locator",
                             "identity_review": "Inherit the exact corrected locator and all identity evidence."}}
        self.case.spec.update(additions=[phase], locator_corrections=[])
        self.case.write()
        out = self.root / "phase"
        manifest = build_update(self.case.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.case.input, out, root=self.root))
        after_projects = self.rows("phase", "projects.csv", "project_id")
        for identifier, row in before_projects.items():
            self.assertEqual(after_projects[identifier], row)
        added_id = str(uuid5(NAMESPACE_URL, phase["project_stable_key"]))
        added = after_projects[added_id]
        self.assertEqual(added["site_id"], reference["site_id"])
        for field in reference:
            if field.startswith(("geometry_", "horizontal_uncertainty")) or field in {"latitude", "longitude"}:
                self.assertEqual(added[field], reference[field], field)
        self.assertEqual((added["geometry_derivation"], added["geometry_authority_class"]),
                         ("coordinate_transform", "compiled_reference"))
        after_evidence = self.rows("phase", "evidence.csv", "evidence_id")
        associated = {reference["geometry_evidence_id"], *identity_ids}
        for identifier, row in before_evidence.items():
            expected = copy.deepcopy(row)
            if identifier in associated:
                expected["project_ids_json"] = json.dumps(
                    sorted(set(json.loads(row["project_ids_json"])) | {added_id}), separators=(",", ":"))
            self.assertEqual(after_evidence[identifier], expected)
        self.assertEqual(set(after_evidence), set(before_evidence))

    def test_legacy_evidence_reuse_rejects_missing_wrong_or_changed_captures(self):
        self.legacy_geometry_evidence()
        self.provenance_correction()
        valid = copy.deepcopy(self.case.sources["sources"][-1])
        cases = [
            ({"reuse_evidence_id": ""}, "reused baseline evidence ID"),
            ({"reuse_evidence_id": "missing"}, "must exist in the baseline"),
            ({"reuse_evidence_id": self.project["status_evidence_id"]}, "exactly match the baseline capture"),
            ({"source_url": "https://maps.example.net/feature/2"}, "exactly match the baseline capture"),
            ({"content_hash": hashlib.sha256(b"different capture").hexdigest()}, "exactly match the baseline capture"),
        ]
        for field in ("kind", "title", "publisher", "source_family", "license", "attribution", "content_hash_scope"):
            cases.append(({field: "different"}, "exactly match the baseline capture"))
        cases.extend([
            ({"published_at": "2026-09-20"}, "exactly match the baseline capture"),
            ({"retrieved_at": "2026-10-12T08:00:00Z"}, "exactly match the baseline capture"),
        ])
        for changes, message in cases:
            with self.subTest(changes=changes):
                self.case.sources["sources"][-1] = {**valid, **changes}
                with self.assertRaisesRegex(UpdateError, message):
                    self.corrected()
        self.case.sources["sources"][-1] = {key: value for key, value in valid.items() if key != "reuse_evidence_id"}
        with self.assertRaisesRegex(UpdateError, "preserve the geometry evidence"):
            self.corrected()
        self.case.sources["sources"][-1] = valid
        _, _, tables = self.corrected()
        self.assertEqual({row["evidence_id"]: row for row in tables["evidence.csv"]},
                         self.rows("first", "evidence.csv", "evidence_id"))

    def test_provenance_only_rejects_geometry_source_scope_uncertainty_and_invalid_flags(self):
        self.provenance_correction()
        valid = copy.deepcopy(self.correction)
        locator = valid["locator"]
        cases = [
            ({"geometry": {"type": "Point", "coordinates": [-100.099, 30.2]}}, "preserve exact geometry"),
            ({"source_id": "parcel"}, "preserve the geometry evidence"),
            ({"scope": "project_locator"}, "preserve exact geometry"),
            ({"scope_class": "building_centroid"}, "preserve exact geometry"),
            ({"horizontal_uncertainty_metres": 5}, "preserve exact geometry"),
            ({"uncertainty_reason": "Different uncertainty."}, "preserve exact geometry"),
            ({"derivation": "direct_geometry"}, "needs a derived point"),
            ({"authority": "official_source"}, "derived locator must be a compiled reference"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                self.correction = {**valid, "locator": {**locator, **changes}}
                with self.assertRaisesRegex(UpdateError, message):
                    self.corrected()
        for flag in ("true", 1, None):
            with self.subTest(flag=flag):
                self.correction = {**valid, "provenance_only": flag}
                with self.assertRaisesRegex(UpdateError, "provenance_only must be a boolean"):
                    self.corrected()
        self.correction = valid
        self.case.sources["sources"][-1]["publisher"] = "Changed publisher"
        with self.assertRaisesRegex(UpdateError, "conflicting metadata for the same evidence capture"):
            self.corrected()

    def test_provenance_only_requires_an_actual_change_and_explicit_opt_in(self):
        self.provenance_correction()
        for flag in (None, False):
            with self.subTest(flag=flag):
                self.correction.pop("provenance_only", None)
                if flag is not None:
                    self.correction["provenance_only"] = flag
                with self.assertRaisesRegex(UpdateError, "different geometry source"):
                    self.corrected()
        self.correction["provenance_only"] = True
        self.corrected()
        build_update(self.case.input, self.root / "provenance", root=self.root)
        self.base("provenance")
        with self.assertRaisesRegex(UpdateError, "must change locator provenance"):
            self.corrected()

    def test_provenance_only_cannot_share_a_campus_with_an_addition_or_second_correction(self):
        self.provenance_correction()
        self.case.spec["additions"] = [{**self.second, "existing_site_id": self.project["site_id"],
                                       "site_identity_review": "Same campus, separately scoped phase."}]
        with self.assertRaisesRegex(UpdateError, "no addition or other correction"):
            self.corrected()
        self.case.spec["additions"] = []
        self.case.spec["locator_corrections"] = [self.correction, copy.deepcopy(self.correction)]
        with self.assertRaisesRegex(UpdateError, "no addition or other correction"):
            self.case.payloads()

    def test_provenance_only_cannot_reclassify_the_baseline_source_entity(self):
        self.provenance_correction()
        tables = {}
        for name, key, field, value in (
            ("projects.csv", "project_id", "geometry_source_entity_kind", "project"),
            ("sites.csv", "site_id", "geometry_source_entity_kinds_json", '["project"]'),
        ):
            rows = self.rows("first", name, key)
            rows[self.project[key]][field] = value
            tables[name] = list(rows.values())
        self.replace_first_tables(tables)
        with self.assertRaisesRegex(UpdateError, "preserve exact geometry, scope, source entity"):
            self.corrected()

    def test_multi_project_campus_moves_every_project_and_needs_campus_scope(self):
        self.second.update(existing_site_id=self.project["site_id"],
                           site_identity_review="The second phase is on the same named campus.")
        self.second["locator"]["source_id"] = "old-map"
        self.case.sources["sources"].append({**self.parcel, "id": "old-map", "kind": "map", "title": "Map feature",
                                             "source_url": "https://maps.example.net/feature/1",
                                             "publisher": "Example Operator", "license": "all-rights-reserved",
                                             "content_hash": hashlib.sha256(b"old map feature").hexdigest()})
        self.case.spec["additions"] = [self.second]
        self.case.write()
        build_update(self.case.input, self.root / "second", root=self.root)
        self.base("second")
        self.case.spec["additions"] = []
        self.case.sources["sources"].pop()
        _, _, tables = self.corrected()
        members = [row for row in tables["projects.csv"] if row["site_id"] == self.project["site_id"]]
        self.assertEqual(len(members), 2)
        self.assertEqual({(row["latitude"], row["longitude"], row["geometry_source_url"]) for row in members},
                         {("30.199", "-100.099", self.parcel["source_url"])})
        self.correction["locator"] = {**self.correction["locator"], "scope": "project_locator"}
        with self.assertRaisesRegex(UpdateError, "multi-project site needs a campus locator"):
            self.corrected()

    def test_correction_rejects_mismatched_or_unsafe_requests(self):
        valid = copy.deepcopy(self.correction)
        far = {**valid["locator"], "geometry": {"type": "Point", "coordinates": [-99.8, 30.2]}}
        cases = [
            ({"site_id": "vcc-site-wrong"}, "site ID must match"),
            ({"physical_site_stable_key": "curated:missing"}, "existing site"),
            ({"replaces_geometry_evidence_id": self.project["status_evidence_id"]}, "geometry evidence of every project"),
            ({"reason": ""}, "locator correction reason"),
            ({"displacement_review": " "}, "displacement review"),
            ({"locator": far}, "farther than 25 km"),
            ({"locator": {**valid["locator"], "source_id": "old-map"}}, "different geometry source"),
            ({"locator": {**valid["locator"], "reuse_from_project_id": self.project["project_id"]}}, "unsupported locator correction field"),
            ({"locator": {**valid["locator"], "geometry": {"type": "Polygon", "coordinates": []}}}, "new point admissions only"),
            ({"locator": {**valid["locator"], "identity_source_ids": ["missing"]}}, "identity sources"),
        ]
        old_map = {**self.parcel, "id": "old-map", "kind": "map", "title": "Map feature",
                   "source_url": "https://maps.example.net/feature/1", "publisher": "Example Operator",
                   "license": "all-rights-reserved", "content_hash": hashlib.sha256(b"old map feature").hexdigest()}
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.correction = {**valid, **changes}
                self.case.sources["sources"] = [self.case.sources["sources"][0], self.parcel]
                if changes.get("locator", {}).get("source_id") == "old-map":
                    self.case.sources["sources"].append(old_map)
                with self.assertRaisesRegex(UpdateError, expected):
                    self.corrected()
        self.correction = valid
        self.case.sources["sources"] = [self.case.sources["sources"][0], self.parcel, old_map]
        self.case.spec["additions"] = [{**self.second, "existing_site_id": self.project["site_id"],
                                        "site_identity_review": "Same campus."}]
        with self.assertRaisesRegex(UpdateError, "no addition or other correction"):
            self.corrected()
        self.case.spec["additions"] = []
        self.case.spec["locator_corrections"] = [valid, valid]
        self.case.write()
        with self.assertRaisesRegex(UpdateError, "no addition or other correction"):
            update_payloads(self.case.input, root=self.root)

    def test_new_locators_may_not_copy_map_services_after_the_policy_date(self):
        urls = {
            "https://www.google.com/search?tbm=map&q=Example+campus": "Google Maps",
            "https://www.google.com/maps/place/Example/@30.2,-100.1,17z": "Google Maps",
            "https://maps.google.com/?cid=123": "Google Maps",
            "https://maps.app.goo.gl/abc": "Google Maps",
            "https://www.peeringdb.com/fac/1": "PeeringDB",
            "https://www.waze.com/live-map/directions?to=ll.30.2,-100.1": "Waze",
            "https://yandex.ru/maps/-/abc": "Yandex Maps",
            "https://map.naver.com/p/entry/place/1": "Naver Map",
        }
        for url, service in urls.items():
            with self.subTest(url=url):
                self.parcel["source_url"] = url
                self.case.sources["sources"][1] = self.parcel
                self.corrected(updated_at="2026-11-06")
                with self.assertRaisesRegex(UpdateError, f"copied from {service}"):
                    self.corrected(updated_at="2026-11-07")
        self.parcel["source_url"] = "https://gis.example.gov/parcels/42"
        self.correction["locator"] = {**self.correction["locator"], "method": "native_Google_Maps_named_feature"}
        with self.assertRaisesRegex(UpdateError, "copied from Google Maps"):
            self.corrected(updated_at="2026-11-07")
        # Google's own campuses and operator pages with ordinary paths remain usable.
        self.correction["locator"]["method"] = "centroid_of_google_llc_county_parcel"
        for url in ("https://gis.example.gov/parcels/42", "https://www.google.com/about/datacenters/locations/",
                    "https://blog.google/around-the-globe/new-campus/"):
            with self.subTest(url=url):
                self.parcel["source_url"] = url
                self.case.sources["sources"][1] = self.parcel
                self.corrected(updated_at="2026-11-07")
        addition = copy.deepcopy(self.second)
        addition.update(project_stable_key="curated:mapped:construction", physical_site_stable_key="curated:mapped",
                        site_name="Mapped campus", name="Mapped construction")
        addition["locator"]["source_id"] = "parcel"
        self.parcel["source_url"] = "https://maps.app.goo.gl/abc"
        self.case.sources["sources"][1] = self.parcel
        self.case.spec.update(updated_at="2026-11-07", additions=[addition], locator_corrections=[])
        with self.assertRaisesRegex(UpdateError, "copied from Google Maps"):
            self.case.payloads()


class ImportedReferenceCorrectionTests(unittest.TestCase):
    """A town-level imported point can move to the campus it stands for, within a scaled limit."""

    def setUp(self):
        self.case = RetainedImportedStatusTests("test_retained_statuses_are_not_admission_statuses")
        self.case.setUp()
        self.addCleanup(self.case.temp.cleanup)
        self.project = self.case.base[RetainedImportedStatusTests.BUILDING]
        self.assertEqual((self.project["geometry_method"], self.project["geometry_scope_class"]),
                         ("imported_reference_point", "locality"))
        self.case.sources["sources"].append({
            **self.case.sources["sources"][0], "id": "plan", "kind": "government_record", "title": "Site plan",
            "source_url": "https://example.gov/site-plan", "publisher": "Example Authority",
            "content_hash": hashlib.sha256(b"site plan").hexdigest()})

    def correct(self, north_km):
        lat = float(self.project["latitude"]) + north_km / 111.2
        self.case.spec["locator_corrections"] = [{
            "physical_site_stable_key": self.project["physical_site_stable_key"], "site_id": self.project["site_id"],
            "replaces_geometry_evidence_id": self.project["geometry_evidence_id"],
            "reason": "The imported point names only the nearest town.",
            "displacement_review": f"About {north_km} km north of the town point; the plan names the campus.",
            "locator": {"geometry": {"type": "Point", "coordinates": [float(self.project["longitude"]), lat]},
                        "source_id": "plan", "scope": "campus_locator", "scope_class": "georeferenced_site_plan",
                        "authority": "compiled_reference", "derivation": "georeferenced_source_map",
                        "method": "centroid_of_published_site_plan", "precision": "Plan centroid.",
                        "horizontal_uncertainty_metres": 100, "identity_review": "The plan names the project."}}]
        return self.case.payloads()

    def test_locality_point_moves_up_to_fifty_km_and_keeps_its_imported_source(self):
        payloads, _ = self.correct(40)
        rows = {row["project_id"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}
        corrected = rows[self.project["project_id"]]
        self.assertEqual(corrected["geometry_method"], "centroid_of_published_site_plan")
        self.assertEqual(corrected["status_evidence_id"], self.project["status_evidence_id"])
        evidence = {row["evidence_id"]: row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
        if self.project["geometry_evidence_id"] in evidence:
            self.assertNotIn("geometry", json.loads(evidence[self.project["geometry_evidence_id"]]["roles_json"]))
        with self.assertRaisesRegex(UpdateError, "farther than 50 km from a locality point"):
            self.correct(60)

class MetricDateCorrectionTests(unittest.TestCase):
    """Correct the date and capture of one exact observation, never its measured claim."""

    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def setUp(self):
        DatasetUpdateTests.setUp(self)
        self.addition = copy.deepcopy(self.spec["additions"][0])
        self.spec["additions"] = []
        self.rows = list(csv.DictReader(io.StringIO((BASE / "projects.csv").read_text())))
        self.project = next(row for row in self.rows if "goodman-hkg09" in row["project_stable_key"])
        self.observations = json.loads(self.project["power_observations_json"])
        self.correction = self.request(self.project, "power_observations_json", self.observations[0])
        self.spec["metric_date_corrections"] = [self.correction]

    def request(self, project, field, observation):
        return {"project_stable_key": project["project_stable_key"], "field": field,
                "replaces_observation": copy.deepcopy(observation), "as_of_date": "2025-11-12", "source_id": "work",
                "reason": "The previous date was a CMS modification, not the original publication.",
                "identity_review": "The original source names the same project and metric scope."}

    def projects(self, payloads):
        return {row["project_stable_key"]: row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))}

    def replace_baseline_projects(self):
        out = io.StringIO(newline="")
        writer = csv.DictWriter(out, fieldnames=list(self.rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows)
        raw = out.getvalue().encode()
        (self.root / "base/projects.csv").write_bytes(raw)
        path = self.root / "base/manifest.json"
        manifest = json.loads(path.read_bytes())
        manifest["files"]["projects.csv"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        path.write_text(json.dumps(manifest))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (path.parent / "manifest.sha256").write_text(digest + "  manifest.json\n")
        self.spec["base_manifest_sha256"] = digest

    def test_water_dates_must_match_the_correction_source_and_remain_unique_after_all_corrections(self):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        self.spec.pop("metric_date_corrections")
        key = self.project["project_stable_key"]
        field = "annual_water_observations_json"
        self.spec["annual_water_observations"] = []
        for year, amount in [(2023, 0), (2024, 10)]:
            source = {**self.sources["sources"][0], "id": str(year), "source_url": f"https://example.org/{year}",
                      "source_reporting_period": str(year), "date_semantics": f"Calendar year {year}."}
            self.sources["sources"].append(source)
            self.spec["annual_water_observations"].append({
                "project_stable_key": key, "source_id": source["id"], "metric": "annual_water_withdrawal_m3",
                "stage": "measured", "as_of_date": f"{year}-12-31", "target_date": None, "low": amount,
                "base": amount, "high": amount, "unit": "m³/year", "method": "reported", "confidence": 1,
                "notes": "Reported facility water withdrawal.",
            })
        self.write()
        out = self.root / "water"
        build_update(self.input, out, root=self.root)
        self.spec.pop("annual_water_observations")
        self.spec.update(base_dataset=out.name, base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
        with (out / "projects.csv").open() as stream:
            project = next(row for row in csv.DictReader(stream) if row["project_stable_key"] == key)
        first, second = json.loads(project[field])
        correction = self.request(project, field, first)
        correction.update(as_of_date="2024-06-30", source_id="2024")
        self.spec["metric_date_corrections"] = [correction]
        with self.assertRaisesRegex(UpdateError, "end of its measured reporting period"):
            self.payloads()
        correction["as_of_date"] = second["as_of_date"]
        with self.assertRaisesRegex(UpdateError, "duplicate or conflicting annual_water"):
            self.payloads()
        swap = {**self.request(project, field, second), "as_of_date": first["as_of_date"], "source_id": "2023"}
        self.spec["metric_date_corrections"].append(swap)
        payloads, _ = self.payloads()
        corrected = json.loads(self.projects(payloads)[key][field])
        self.assertEqual(corrected, [{**first, "as_of_date": second["as_of_date"], "evidence_id": second["evidence_id"]},
                                     {**second, "as_of_date": first["as_of_date"], "evidence_id": first["evidence_id"]}])
        del self.sources["sources"][-1]["source_reporting_period"]
        with self.assertRaisesRegex(UpdateError, "explicit observation date"):
            self.payloads()

    def test_date_correction_preserves_claim_other_observations_history_and_reproduces(self):
        before = {path.name: path.read_bytes() for path in (self.root / "base").iterdir() if path.is_file()}
        self.write()
        out = self.root / "corrected"
        manifest = build_update(self.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.input, out, root=self.root))
        payloads, _ = update_payloads(self.input, root=self.root)
        projects = self.projects(payloads)
        observation = json.loads(projects[self.project["project_stable_key"]]["power_observations_json"])[0]
        new_id = str(uuid5(NAMESPACE_URL, self.sources["sources"][0]["source_url"] + "#" + self.sources["sources"][0]["content_hash"]))
        self.assertEqual(observation, {**self.observations[0], "as_of_date": "2025-11-12", "evidence_id": new_id})
        for original in self.rows:
            changed = copy.deepcopy(projects[original["project_stable_key"]])
            changed["status_age_days_at_review"] = original["status_age_days_at_review"]
            if original["project_id"] == self.project["project_id"]:
                remaining = json.loads(changed["power_observations_json"])
                self.assertEqual(remaining[1:], self.observations[1:])
                changed["power_observations_json"] = original["power_observations_json"]
            self.assertEqual(changed, original)
        evidence = {row["evidence_id"]: row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))}
        for original in csv.DictReader(io.StringIO(before["evidence.csv"].decode())):
            self.assertEqual(evidence[original["evidence_id"]], original)
        self.assertEqual(json.loads(evidence[new_id]["roles_json"]), ["typed_metric:critical_it_mw"])
        self.assertEqual(json.loads(evidence[new_id]["project_ids_json"]), [self.project["project_id"]])
        self.assertEqual(before, {path.name: path.read_bytes() for path in (self.root / "base").iterdir() if path.is_file()})
        report = json.loads(payloads["selection-report.json"])
        self.assertEqual(report["refreshed_projects"], [])
        self.assertEqual(report["corrected_metric_observations"], [{
            "project_stable_key": self.project["project_stable_key"], "field": "power_observations_json",
            "observation_index": 0, "metric": "critical_it_mw", "previous_as_of_date": "2026-07-20",
            "as_of_date": "2025-11-12", "previous_evidence_id": self.observations[0]["evidence_id"], "evidence_id": new_id}])
        provenance = json.loads(payloads["review-provenance.json"])
        self.assertEqual(provenance["update"]["metric_date_corrections"], [self.correction])
        self.assertEqual(provenance["source_projections"]["work"], self.sources["sources"][0])

    def test_all_metric_fields_and_multiple_observations_keep_their_order_and_roles(self):
        annual = {**self.observations[0], "metric": "annual_energy_gwh", "unit": "GWh/year"}
        self.project["annual_energy_observations_json"] = json.dumps([annual])
        self.replace_baseline_projects()
        efficiency = next(row for row in self.rows if json.loads(row["efficiency_observations_json"]))
        requests = [self.request(self.project, "power_observations_json", observation) for observation in self.observations]
        requests += [self.request(self.project, "annual_energy_observations_json", annual),
                     self.request(efficiency, "efficiency_observations_json", json.loads(efficiency["efficiency_observations_json"])[0])]
        self.spec["metric_date_corrections"] = requests
        payloads, _ = self.payloads()
        projects = self.projects(payloads)
        for request in requests:
            observations = json.loads(projects[request["project_stable_key"]][request["field"]])
            corrected = next(value for value in observations if value["metric"] == request["replaces_observation"]["metric"])
            self.assertEqual(corrected, {**request["replaces_observation"], "as_of_date": "2025-11-12", "evidence_id": corrected["evidence_id"]})
        self.assertEqual([value["metric"] for value in json.loads(projects[self.project["project_stable_key"]]["power_observations_json"])],
                         [value["metric"] for value in self.observations])
        new_id = json.loads(projects[self.project["project_stable_key"]]["annual_energy_observations_json"])[0]["evidence_id"]
        evidence = next(row for row in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode())) if row["evidence_id"] == new_id)
        self.assertEqual(json.loads(evidence["roles_json"]), ["typed_metric:annual_energy_gwh", "typed_metric:critical_it_mw",
                                                             "typed_metric:grid_connection_mw", "typed_metric:pue"])
        self.spec["metric_date_corrections"].reverse()
        reordered, _ = self.payloads()
        for name in ("projects.csv", "evidence.csv", "selection-report.json"):
            self.assertEqual(payloads[name], reordered[name])

    def test_metric_date_and_status_corrections_can_coexist(self):
        self.spec["status_corrections"] = [{
            "project_stable_key": self.project["project_stable_key"],
            "replaces_status_evidence_id": self.project["status_evidence_id"], "reason": "Correct publication date.",
            "status": self.addition["status"], "identity_review": "Same project.", "successor_review": "No later status."}]
        payloads, _ = self.payloads()
        row = self.projects(payloads)[self.project["project_stable_key"]]
        self.assertEqual(row["status_as_of"], "2026-09-21")
        metric = json.loads(row["power_observations_json"])[0]
        self.assertEqual(metric["as_of_date"], "2025-11-12")
        self.assertEqual(metric["evidence_id"], row["status_evidence_id"])
        evidence = next(value for value in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                        if value["evidence_id"] == row["status_evidence_id"])
        self.assertEqual(json.loads(evidence["roles_json"]), ["physical_status", "typed_metric:critical_it_mw"])

    def test_unknown_unsafe_incomplete_and_noop_requests_fail(self):
        cases = [
            ({"project_stable_key": "missing"}, "baseline project"),
            ({"project_stable_key": None}, "baseline project"),
            ({"field": "workloads_json"}, "unsupported metric observation field"),
            ({"field": None}, "unsupported metric observation field"),
            ({"value": 999}, "unsupported metric date correction field"),
            ({"replaces_observation": None}, "exact baseline observation"),
            ({"replaces_observation": {}}, "uniquely match"),
            ({"reason": " "}, "metric date correction reason"),
            ({"identity_review": None}, "metric identity review"),
            ({"source_id": None}, "metric correction source"),
            ({"source_id": "missing"}, "reviewed source"),
            ({"as_of_date": None}, "ISO date string"),
            ({"as_of_date": "2026-10-14"}, "future metric observation"),
            ({"as_of_date": "2026-10-01"}, "postdates its source"),
            ({"as_of_date": self.observations[0]["as_of_date"]}, "different observation date"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                self.spec["metric_date_corrections"] = [{**self.correction, **changes}]
                with self.assertRaisesRegex(UpdateError, message):
                    self.payloads()
        for key in self.correction:
            with self.subTest(missing=key):
                request = copy.deepcopy(self.correction)
                del request[key]
                self.spec["metric_date_corrections"] = [request]
                with self.assertRaises(UpdateError):
                    self.payloads()

    def test_changed_claim_or_stale_observation_cannot_be_matched(self):
        for field, value in {"base": 29, "low": 27, "high": 30, "stage": "operational", "metric": "grid_connection_mw",
                             "unit": "GW", "notes": "Changed scope", "target_date": "2028-01-01", "evidence_id": "different",
                             "as_of_date": "2026-07-19", "scope": "campus"}.items():
            with self.subTest(field=field):
                self.spec["metric_date_corrections"] = [{**self.correction, "replaces_observation": {**self.observations[0], field: value}}]
                with self.assertRaisesRegex(UpdateError, "uniquely match"):
                    self.payloads()

    def test_metric_correction_requires_publication_date_and_primary_source_kind(self):
        original = copy.deepcopy(self.sources["sources"][0])
        cases = [{"published_at": value} for value in (None, "")]
        cases += [{"kind": kind} for kind in ("news", "analyst_report", "map", "unknown")]
        cases.append({"published_at": None, "source_observation_date": "2025-11-12",
                      "source_observation_date_precision": "day", "date_semantics": "Dated entry on an undated page."})
        for changes in cases:
            with self.subTest(changes=changes):
                self.sources["sources"][0] = {**original, **changes}
                with self.assertRaisesRegex(UpdateError, "dated primary source"):
                    self.payloads()
        for kind in ("company_disclosure", "government_record", "regulatory_filing"):
            with self.subTest(accepted_kind=kind):
                self.sources["sources"][0] = {**original, "kind": kind}
                payloads, _ = self.payloads()
                observation = json.loads(self.projects(payloads)[self.project["project_stable_key"]]["power_observations_json"])[0]
                self.assertEqual(observation["as_of_date"], "2025-11-12")

    def test_duplicate_ambiguous_and_chained_requests_fail(self):
        self.spec["metric_date_corrections"] = [self.correction, copy.deepcopy(self.correction)]
        with self.assertRaisesRegex(UpdateError, "duplicate metric observation correction"):
            self.payloads()
        self.spec["metric_date_corrections"] = [self.correction]
        payloads, _ = self.payloads()
        corrected = json.loads(self.projects(payloads)[self.project["project_stable_key"]]["power_observations_json"])[0]
        self.spec["metric_date_corrections"].append({**self.correction, "replaces_observation": corrected, "as_of_date": "2025-11-11"})
        with self.assertRaisesRegex(UpdateError, "uniquely match"):
            self.payloads()
        self.project["power_observations_json"] = json.dumps(self.observations + [self.observations[0]])
        self.replace_baseline_projects()
        self.spec["metric_date_corrections"] = [self.correction]
        with self.assertRaisesRegex(UpdateError, "uniquely match"):
            self.payloads()

    def test_new_and_withdrawn_projects_cannot_have_metric_dates_corrected(self):
        self.spec["additions"] = [self.addition]
        self.spec["metric_date_corrections"] = [{**self.correction, "project_stable_key": self.addition["project_stable_key"]}]
        with self.assertRaisesRegex(UpdateError, "baseline project"):
            self.payloads()
        self.spec["additions"] = []
        self.spec["metric_date_corrections"] = [self.correction]
        self.spec["withdrawals"] = [{"project_stable_key": self.project["project_stable_key"],
                                     "replaces_status_evidence_id": self.project["status_evidence_id"],
                                     "reason": "Unsupported selection.", "source_ids": ["work"]}]
        with self.assertRaisesRegex(UpdateError, "non-withdrawn baseline project"):
            self.payloads()

    def test_rebased_correction_rejects_stale_matches_and_reused_evidence(self):
        self.write()
        out = self.root / "corrected"
        build_update(self.input, out, root=self.root)
        self.spec.update(base_dataset="corrected", base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
        with self.assertRaisesRegex(UpdateError, "uniquely match"):
            self.payloads()
        row = next(row for row in csv.DictReader(io.StringIO((out / "projects.csv").read_text()))
                   if row["project_id"] == self.project["project_id"])
        self.correction.update(replaces_observation=json.loads(row["power_observations_json"])[0], as_of_date="2025-11-11")
        with self.assertRaisesRegex(UpdateError, "different evidence capture"):
            self.payloads()


class OperatingModelUpdateTests(unittest.TestCase):
    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def setUp(self):
        DatasetUpdateTests.setUp(self)
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        self.key = self.spec["additions"][0]["project_stable_key"]
        self.sheet = {
            **self.sources["sources"][0], "id": "sheet", "title": "Facility service sheet",
            "kind": "company_facility_page", "source_url": "https://example.org/facilities",
            "published_at": None, "content_hash": hashlib.sha256(b"facility service sheet").hexdigest(),
            "summary": "The operator offers rack colocation at Example campus and Second campus.",
        }
        self.sources["sources"].append(self.sheet)
        self.action = {"project_stable_key": self.key, "operating_model": "colocation", "source_id": "sheet",
                       "identity_review": "The sheet lists rack colocation at the named Example campus."}
        self.spec["operating_model_updates"] = [self.action]

    def test_existing_and_new_projects_retain_scope_sources_and_status(self):
        self.spec.pop("operating_model_updates")
        self.spec["additions"][0]["context_source_ids"] = ["sheet"]
        self.write()
        first = self.root / "2026-10-13-first"
        build_update(self.input, first, root=self.root)
        original = public_site.load_atlas(public_site._load_version(first), "https://example.org/")
        before = next(p for p in original.projects if p["project_stable_key"] == self.key)
        eid = next(e["evidence_id"] for e in original.evidence if e["source_url"] == self.sheet["source_url"])
        self.sheet["reuse_evidence_id"] = eid

        new_key = "curated:second-campus:construction"
        addition = self.spec["additions"][0]
        addition.update(project_stable_key=new_key, physical_site_stable_key="curated:second-campus",
                        site_name="Second campus", name="Second campus construction", context_source_ids=[])
        addition["locator"]["geometry"]["coordinates"] = [-99.0, 30.2]
        self.spec.update(base_dataset=first.name, base_manifest_sha256=hashlib.sha256((first / "manifest.json").read_bytes()).hexdigest(),
                         operating_model_updates=[self.action, {**self.action, "project_stable_key": new_key,
                             "identity_review": "The sheet also lists the service at Second campus."}])
        self.write()
        out = self.root / "2026-10-13-next"
        manifest = build_update(self.input, out, root=self.root)
        self.assertEqual(manifest, validate_update(self.input, out, root=self.root))
        atlas = public_site.load_atlas(public_site._load_version(out), "https://example.org/")
        project = atlas.project_by_id[before["project_id"]]
        second = next(p for p in atlas.projects if p["project_stable_key"] == new_key)
        for row in (project, second):
            self.assertEqual(row["operating_model"], "colocation")
            self.assertIsNone(row["operating_model_unknown_reason"])
            self.assertEqual(row["operating_model_evidence_id"], eid)
        for field in before.keys() - {"operating_model", "operating_model_unknown_reason", "operating_model_evidence_id"}:
            self.assertEqual(before[field], project[field], field)
        evidence = atlas.evidence_by_id[eid]
        self.assertEqual(set(evidence["roles"]), {*original.evidence_by_id[eid]["roles"], "operating_model"})
        self.assertEqual(set(evidence["project_ids"]), {project["project_id"], second["project_id"]})
        self.assertEqual(len(atlas.evidence), len(original.evidence))
        report = json.loads((out / "selection-report.json").read_bytes())
        self.assertEqual(report["refreshed_projects"], [])
        self.assertEqual(report["operating_model_updates"], [
            {"project_stable_key": key, "operating_model": "colocation", "evidence_id": eid}
            for key in sorted((self.key, new_key))
        ])
        facts = public_site._project_facts(SimpleNamespace(vocabulary=public_site.Vocabulary({}), atlas=atlas),
                                           project, public_site._EvidenceAnchors(project["evidence_ids"]))
        self.assertIn(f'href="#evidence-{eid}"', dict(facts)["Operating model"])

        self.spec.update(base_dataset=out.name, base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest(),
                         additions=[], operating_model_updates=[{**self.action, "operating_model": "retail_colocation"}])
        with self.assertRaisesRegex(UpdateError, "already established"):
            self.payloads()

    def test_invalid_duplicate_or_conflicting_updates_fail(self):
        for changes, message in [
            ({"operating_model": "unknown"}, "known model"), ({"operating_model": "colo"}, "known model"),
            ({"project_stable_key": "missing"}, "non-withdrawn project"), ({"source_id": "missing"}, "reviewed source"),
            ({"identity_review": ""}, "evidence scope"), ({"evidence_id": "injected"}, "requires project_stable_key"),
        ]:
            with self.subTest(changes=changes), self.assertRaisesRegex(UpdateError, message):
                self.spec["operating_model_updates"] = [{**self.action, **changes}]
                self.payloads()
        for model in ("colocation", "wholesale_colocation"):
            with self.subTest(model=model), self.assertRaisesRegex(UpdateError, "duplicate or conflicting"):
                self.spec["operating_model_updates"] = [self.action, {**self.action, "operating_model": model}]
                self.payloads()
        self.spec["operating_model_updates"] = [self.action]
        self.sheet["kind"] = "map"
        with self.assertRaisesRegex(UpdateError, "primary facility or project evidence"):
            self.payloads()
        self.spec["format"] = "datacenter-atlas-update-input-v1"
        with self.assertRaisesRegex(UpdateError, "v2 action list"):
            self.payloads()

    def test_model_cannot_be_assigned_to_a_withdrawn_project(self):
        with (BASE / "projects.csv").open() as f:
            original = next(csv.DictReader(f))
        key = original["project_stable_key"]
        self.spec["withdrawals"] = [{"project_stable_key": key}]
        self.spec["operating_model_updates"] = [{**self.action, "project_stable_key": key}]
        with self.assertRaisesRegex(UpdateError, "non-withdrawn project"):
            self.payloads()


class PowerObservationTests(unittest.TestCase):
    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def setUp(self):
        DatasetUpdateTests.setUp(self)
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        self.project_key = self.spec["additions"][0]["project_stable_key"]
        self.action = {
            "project_stable_key": self.project_key, "source_id": "work", "metric": "critical_it_mw",
            "stage": "planned", "low": 2.5, "base": 2.5, "high": 2.5, "unit": "MW", "method": "reported",
            "confidence": 0.99, "as_of_date": "2026-09-20", "target_date": None,
            "notes": "The developer reports 2.5 MW of planned IT capacity for the project.",
        }
        self.sources["sources"][0]["summary"] += " The project has 2.5 MW planned IT capacity as of September 20."
        self.spec["power_observations"] = [self.action]

    def test_power_on_new_and_existing_projects_preserves_status_and_prior_observations(self):
        with (BASE / "projects.csv").open() as f:
            original = next(row for row in csv.DictReader(f) if json.loads(row["power_observations_json"]))
        old = json.loads(original["power_observations_json"])
        key = original["project_stable_key"]
        self.spec["power_observations"].append({**self.action, "project_stable_key": key})
        self.write()
        out = self.root / "out"
        manifest = build_update(self.input, out, root=self.root)
        self.assertEqual(validate_update(self.input, out, root=self.root), manifest)
        with (out / "projects.csv").open() as f:
            rows = {r["project_stable_key"]: r for r in csv.DictReader(f)}
        added = rows[self.project_key]
        ref = added["status_evidence_id"]
        expected = {k: v for k, v in self.action.items() if k not in {"project_stable_key", "source_id"}}
        expected["evidence_id"] = ref
        self.assertEqual(json.loads(added["power_observations_json"]), [expected])
        self.assertEqual(json.loads(rows[key]["power_observations_json"]), [*old, expected])
        self.assertEqual(added["power_unknown_reason"], "")
        self.assertEqual(rows[key]["power_unknown_reason"], "")
        for field in original.keys() - {"power_observations_json", "power_unknown_reason", "status_age_days_at_review"}:
            self.assertEqual(rows[key][field], original[field], field)
        with (out / "evidence.csv").open() as f:
            source = next(r for r in csv.DictReader(f) if r["evidence_id"] == ref)
        self.assertIn("typed_metric:critical_it_mw", json.loads(source["roles_json"]))
        self.assertIn("physical_status", json.loads(source["roles_json"]))
        self.assertEqual(set(json.loads(source["project_ids_json"])), {added["project_id"], original["project_id"]})
        report = json.loads((out / "selection-report.json").read_bytes())
        self.assertEqual([a["project_stable_key"] for a in report["added_power_observations"]], [self.project_key, key])
        self.assertNotIn(key, report["refreshed_projects"])
        provenance = json.loads((out / "review-provenance.json").read_bytes())
        self.assertEqual(provenance["update"]["power_observations"], self.spec["power_observations"])

        self.spec.update(base_dataset="out", base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest(),
                         additions=[], power_observations=[self.action])
        with self.assertRaisesRegex(UpdateError, "duplicate or conflicting"):
            self.payloads()

    def test_different_values_or_sources_collide_for_the_same_project_metric_stage_and_dates(self):
        self.sources["sources"].append({**self.sources["sources"][0], "id": "other", "source_url": "https://example.org/other"})
        self.spec["power_observations"].append({**self.action, "source_id": "other", "low": 3, "base": 3, "high": 3})
        with self.assertRaisesRegex(UpdateError, "duplicate or conflicting"):
            self.payloads()
        self.spec["power_observations"][1]["as_of_date"] = "2026-09-21"
        self.payloads()

    def test_invalid_units_scope_intervals_and_date_are_rejected(self):
        for changes, error in [
            ({"stage": "unknown"}, "known stage"), ({"metric": "power_mw"}, "metric/unit"),
            ({"unit": "MVA"}, "metric/unit"), ({"high": 1}, "interval"), ({"confidence": True}, "confidence"),
            ({"as_of_date": "2026-09-22"}, "postdates its source"), ({"source_id": "missing"}, "reviewed source"),
            ({"project_stable_key": "absent"}, "non-withdrawn project"), ({"notes": ""}, "scope"),
            ({"evidence_id": "unreviewed"}, "source_id"),
        ]:
            with self.subTest(changes=changes), self.assertRaisesRegex(UpdateError, error):
                self.spec["power_observations"] = [{**self.action, **changes}]
                self.payloads()

    def test_undated_page_needs_a_dated_statement_for_the_observation(self):
        power = {**self.sources["sources"][0], "id": "spec", "source_url": "https://example.org/spec", "published_at": None}
        self.sources["sources"].append(power)
        self.action["source_id"] = "spec"
        with self.assertRaisesRegex(UpdateError, "explicit observation date"):
            self.payloads()
        power.update(source_observation_date=self.action["as_of_date"], source_observation_date_precision="day",
                     date_semantics="The facility specification explicitly dates its capacity statement.")
        self.payloads()
        self.spec["format"] = "datacenter-atlas-update-input-v1"
        with self.assertRaisesRegex(UpdateError, "v2 action list"):
            self.payloads()


class EfficiencyObservationTests(unittest.TestCase):
    setUp = DatasetUpdateTests.setUp
    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def quarterly_observation(self):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        source = {**self.sources["sources"][0], "id": "report", "source_url": "https://example.org/efficiency",
                  "published_at": None, "source_reporting_period": "2026-Q2",
                  "date_semantics": "Q2 is the measured April–June reporting period."}
        self.sources["sources"].append(source)
        action = {
            "project_stable_key": self.spec["additions"][0]["project_stable_key"], "source_id": "report",
            "metric": "pue", "stage": "measured", "as_of_date": "2026-06-30", "target_date": None,
            "low": 1.09, "base": 1.09, "high": 1.09, "method": "reported", "confidence": 1,
            "unit": "ratio", "notes": "Mean PUE for the campus in the second quarter.",
        }
        self.spec["efficiency_observations"] = [action]
        return action, source

    def test_efficiency_replays_with_its_own_evidence_and_reporting_date(self):
        action, _ = self.quarterly_observation()
        self.write()
        out = self.root / "out"
        self.assertEqual(build_update(self.input, out, root=self.root), validate_update(self.input, out, root=self.root))
        with (out / "projects.csv").open() as f:
            row = next(r for r in csv.DictReader(f) if r["project_stable_key"] == action["project_stable_key"])
        obs, = json.loads(row["efficiency_observations_json"])
        with (out / "evidence.csv").open() as f:
            source = next(r for r in csv.DictReader(f) if r["evidence_id"] == obs["evidence_id"])
        self.assertEqual(obs, {**{k: v for k, v in action.items() if k not in {"source_id", "project_stable_key"}},
                               "evidence_id": source["evidence_id"]})
        self.assertEqual(json.loads(source["roles_json"]), ["typed_metric:pue"])
        self.assertEqual(json.loads(source["project_ids_json"]), [row["project_id"]])
        self.assertEqual(row["efficiency_unknown_reason"], "")
        self.assertEqual(row["status_as_of"], self.spec["additions"][0]["status"]["as_of"])
        self.assertEqual(json.loads(row["power_observations_json"]), [])
        self.spec["efficiency_observations"].append(action.copy())
        with self.assertRaisesRegex(UpdateError, "duplicate or conflicting"):
            self.payloads()

    def test_annual_wue_accepts_reported_zero_alongside_pue(self):
        pue, source = self.quarterly_observation()
        source.update(source_reporting_period="2025", date_semantics="The full 2025 calendar year.")
        pue["as_of_date"] = "2025-12-31"
        legacy = json.loads(self.payloads()[0]["schema.json"])
        field = "projects.csv:efficiency_observations_json"
        self.assertEqual(legacy["embedded_array_items"][field]["allowed_metrics"], ["pue"])
        self.assertNotIn("wue", legacy["embedded_types"]["typed_metric_observation"]["unit_by_metric"])
        wue = {**pue, "metric": "wue", "unit": "L/kWh", "low": 0, "base": 0, "high": 0,
               "notes": "Annual WUE for the campus at the register's reported precision."}
        self.spec["efficiency_observations"].append(wue)
        payloads, _ = self.payloads()
        schema = json.loads(payloads["schema.json"])
        self.assertEqual(schema["embedded_array_items"][field]["allowed_metrics"], ["pue", "wue"])
        self.assertEqual(schema["embedded_types"]["typed_metric_observation"]["unit_by_metric"]["wue"], "L/kWh")
        project = next(r for r in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                       if r["project_stable_key"] == wue["project_stable_key"])
        power, water = json.loads(project["efficiency_observations_json"])
        self.assertEqual((power["metric"], power["base"], power["unit"]), ("pue", 1.09, "ratio"))
        self.assertEqual((water["metric"], water["base"], water["unit"]), ("wue", 0, "L/kWh"))
        self.assertEqual(power["evidence_id"], water["evidence_id"])
        evidence = next(r for r in csv.DictReader(io.StringIO(payloads["evidence.csv"].decode()))
                        if r["evidence_id"] == water["evidence_id"])
        self.assertEqual(json.loads(evidence["roles_json"]), ["typed_metric:pue", "typed_metric:wue"])
        self.assertEqual(json.loads(evidence["project_ids_json"]), [project["project_id"]])
        for changes, error in (({"unit": "ratio"}, "metric/unit"), ({"base": None}, "not finite"),
                               ({"low": -0.1}, "interval"), ({"as_of_date": "2025-06-30"}, "reporting period")):
            with self.subTest(changes=changes), self.assertRaisesRegex(UpdateError, error):
                self.spec["efficiency_observations"] = [pue, {**wue, **changes}]
                self.payloads()
        self.spec["efficiency_observations"] = [pue, wue, wue.copy()]
        with self.assertRaisesRegex(UpdateError, "duplicate or conflicting"):
            self.payloads()

    def test_annual_average_uses_calendar_year_end(self):
        action, source = self.quarterly_observation()
        source.update(source_reporting_period="2025", date_semantics="Calendar year average reported for 2025.")
        action["as_of_date"] = "2025-12-31"
        self.payloads()
        action["as_of_date"] = "2025-09-30"
        with self.assertRaisesRegex(UpdateError, "end of its measured reporting period"):
            self.payloads()

    def test_quarterly_efficiency_requires_matching_period_stage_and_units(self):
        action, source = self.quarterly_observation()
        for changes, error in [
            ({"as_of_date": "2026-06-29"}, "end of its measured reporting period"),
            ({"as_of_date": "2026-03-31"}, "end of its measured reporting period"),
            ({"stage": "design"}, "end of its measured reporting period"),
            ({"target_date": "2026-09-30"}, "end of its measured reporting period"),
            ({"unit": "MW"}, "metric/unit"), ({"metric": "critical_it_mw", "unit": "MW"}, "metric/unit"),
            ({"low": 0.95}, "PUE must be at least one"),
        ]:
            with self.subTest(changes=changes), self.assertRaisesRegex(UpdateError, error):
                self.spec["efficiency_observations"] = [{**action, **changes}]
                self.payloads()
        self.spec["efficiency_observations"] = [action]
        del source["source_reporting_period"]
        with self.assertRaisesRegex(UpdateError, "explicit observation date"):
            self.payloads()
        source["published_at"] = "2026-07-07"
        self.payloads()
        self.spec["format"] = "datacenter-atlas-update-input-v1"
        with self.assertRaisesRegex(UpdateError, "v2 action list"):
            self.payloads()


class AnnualEnergyObservationTests(unittest.TestCase):
    setUp = DatasetUpdateTests.setUp
    write = DatasetUpdateTests.write
    payloads = DatasetUpdateTests.payloads

    def test_annual_water_migrates_existing_projects_and_survives_subsequent_admissions(self):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        source = self.sources["sources"][0]
        source.update(source_reporting_period="2025", date_semantics="Calendar year 2025.")
        admission = self.spec["additions"][0]
        self.spec["annual_water_observations"] = [
            {"project_stable_key": admission["project_stable_key"], "source_id": source["id"],
             "metric": metric, "stage": "measured", "as_of_date": "2025-12-31", "target_date": None,
             "low": value, "base": value, "high": value, "unit": "m³/year",
             "method": "reported", "confidence": 1, "notes": "Reported facility volume for calendar 2025."}
            for metric, value in (("annual_water_withdrawal_m3", 8000), ("annual_water_consumption_m3", 0))
        ]
        self.write()
        out = self.root / "with-water"
        build_update(self.input, out, root=self.root)
        schema = json.loads((out / "schema.json").read_bytes())
        field = "annual_water_observations_json"
        self.assertIn(["projects.csv", field, "evidence_id"], schema["json_embedded_evidence_fields"])
        expected_metrics = {a["metric"] for a in self.spec["annual_water_observations"]}
        self.assertEqual(set(schema["embedded_array_items"]["projects.csv:" + field]["allowed_metrics"]), expected_metrics)
        with (out / "projects.csv").open() as f:
            for row in csv.DictReader(f):
                observations = json.loads(row[field])
                if row["project_stable_key"] == admission["project_stable_key"]:
                    self.assertEqual([o["base"] for o in observations], [8000, 0])
                    self.assertEqual([o["evidence_id"] for o in observations], [row["status_evidence_id"]] * 2)
                    self.assertEqual(row["annual_water_unknown_reason"], "")
                else:
                    self.assertEqual(observations, [])
                    self.assertTrue(row["annual_water_unknown_reason"])
        with patch.dict(self.spec["annual_water_observations"][0], {"unit": "L/kWh"}):
            with self.assertRaisesRegex(UpdateError, "metric/unit"):
                self.payloads()
        original_water = self.spec.pop("annual_water_observations")
        self.spec.update(base_dataset=out.name, base_manifest_sha256=hashlib.sha256((out / "manifest.json").read_bytes()).hexdigest())
        admission.update(project_stable_key="curated:second:construction", physical_site_stable_key="curated:second")
        payloads, _ = self.payloads()
        rows = list(csv.DictReader(io.StringIO(payloads["projects.csv"].decode())))
        new = next(r for r in rows if r["project_stable_key"] == admission["project_stable_key"])
        self.assertEqual(json.loads(new[field]), [])
        self.assertTrue(new["annual_water_unknown_reason"])
        discharge = "annual_water_discharge_m3"
        self.spec["annual_water_observations"] = [{**original_water[0], "metric": discharge}]
        payloads, _ = self.payloads()
        schema = json.loads(payloads["schema.json"])
        self.assertEqual(set(schema["embedded_array_items"]["projects.csv:" + field]["allowed_metrics"]),
                         expected_metrics | {discharge})
        self.assertEqual(schema["embedded_types"]["typed_metric_observation"]["unit_by_metric"][discharge], "m³/year")
        original = next(row for row in csv.DictReader(io.StringIO(payloads["projects.csv"].decode()))
                        if row["project_stable_key"] == original_water[0]["project_stable_key"])
        self.assertEqual([obs["metric"] for obs in json.loads(original[field])],
                         [original_water[0]["metric"], original_water[1]["metric"], discharge])

    def test_facility_electricity_uses_the_reported_year_and_its_own_source(self):
        self.spec["format"] = "datacenter-atlas-update-input-v2"
        project = self.spec["additions"][0]
        report = {**self.sources["sources"][0], "id": "annual-report",
                  "source_url": "https://example.org/annual-report", "published_at": None,
                  "source_reporting_period": "2025", "date_semantics": "Calendar year 2025."}
        self.sources["sources"].append(report)
        action = {"project_stable_key": project["project_stable_key"], "source_id": report["id"],
                  "metric": "annual_energy_mwh", "stage": "measured", "as_of_date": "2025-12-31",
                  "target_date": None, "low": 1250, "base": 1250, "high": 1250, "unit": "MWh/year",
                  "method": "reported", "confidence": 1, "notes": "Calendar-year electricity used at the campus."}
        self.spec["annual_energy_observations"] = [action]
        self.write()
        out = self.root / "out"
        self.assertEqual(build_update(self.input, out, root=self.root), validate_update(self.input, out, root=self.root))
        with (out / "projects.csv").open() as f:
            row = next(r for r in csv.DictReader(f) if r["project_stable_key"] == project["project_stable_key"])
        obs, = json.loads(row["annual_energy_observations_json"])
        with (out / "evidence.csv").open() as f:
            evidence = next(r for r in csv.DictReader(f) if r["evidence_id"] == obs["evidence_id"])
        self.assertEqual(obs, {**{k: v for k, v in action.items() if k not in {"source_id", "project_stable_key"}},
                               "evidence_id": evidence["evidence_id"]})
        self.assertEqual(json.loads(evidence["roles_json"]), ["typed_metric:annual_energy_mwh"])
        self.assertEqual(json.loads(evidence["project_ids_json"]), [row["project_id"]])
        self.assertEqual(row["annual_energy_unknown_reason"], "")
        self.assertEqual(row["status_as_of"], project["status"]["as_of"])
        self.assertEqual(json.loads(row["power_observations_json"]), [])
        self.assertEqual(json.loads(row["efficiency_observations_json"]), [])
        self.spec["annual_energy_observations"].append(action.copy())
        with self.assertRaisesRegex(UpdateError, "duplicate or conflicting"):
            self.payloads()
        self.spec["annual_energy_observations"] = [action]
        report["source_reporting_period"] = "2025-Q4"
        with self.assertRaisesRegex(UpdateError, "end of its measured reporting period"):
            self.payloads()
        report["source_reporting_period"] = "2025"
        action["unit"] = "MW"
        with self.assertRaisesRegex(UpdateError, "metric/unit"):
            self.payloads()
        action["unit"] = "MWh/year"
        del report["source_reporting_period"]
        report["published_at"] = "2026-02-01"
        with self.assertRaisesRegex(UpdateError, "explicit observation date"):
            self.payloads()
        action["as_of_date"] = "2025-06-30"
        report.update(source_observation_date="2025-06-30", source_observation_date_precision="day",
                      date_semantics="The report covers the fiscal year ending June 30.")
        self.payloads()
        action["target_date"] = "2026-06-30"
        with self.assertRaisesRegex(UpdateError, "target date"):
            self.payloads()


if __name__ == "__main__":
    unittest.main()
