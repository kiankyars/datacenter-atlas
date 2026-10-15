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
from uuid import NAMESPACE_URL, uuid5

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

    def test_news_requires_attributed_firsthand_physical_status_and_preserves_kind(self):
        source = self.sources["sources"][0]
        source["kind"] = "news"
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
        self.assertEqual(evidence["kind"], "news")
        for changes, expected in (
            ({"basis": "reporter_narrative"}, "primary source"),
            ({"speaker": ""}, "firsthand status speaker"),
            ({"observed_on": "2026-09-20"}, "selected status and observation date"),
            ({"supported_status": "operational"}, "selected status and observation date"),
        ):
            with self.subTest(changes=changes):
                source["firsthand_status_statement"] = {**statement, **changes}
                with self.assertRaisesRegex(UpdateError, expected):
                    self.payloads()
        source["firsthand_status_statement"] = statement
        self.spec["additions"][0]["status"]["value"] = "announced"
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
        self.spec["withdrawal_note"] = "Experimental installations are outside the inventory scope; no physical status change is inferred."
        payloads, _ = self.payloads()
        self.assertEqual(json.loads(payloads["selection-report.json"])["withdrawal_note"], self.spec["withdrawal_note"])
        self.spec["withdrawals"][0]["replaces_status_evidence_id"] = "wrong"
        with self.assertRaisesRegex(UpdateError, "name the removed status evidence"):
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


if __name__ == "__main__":
    unittest.main()
