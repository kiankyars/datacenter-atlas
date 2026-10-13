"""The import preserves source objects and dates without duplicating site identities."""

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas.consolidation import (
    ROOT, ConsolidationError, LOCATION_SCOPES, SNAPSHOT_ONLY, build_consolidation,
    consolidation_payloads, validate_consolidation,
)
from datacenter_atlas.dataset_update import build_update, update_payloads, validate_update
from datacenter_atlas.public_site import discover_versions, load_atlas


INPUT = ROOT / "definitions/atlas-consolidation-2026-10-13.json"
OUTPUT = ROOT / "verified_construction_core/2026-10-13-consolidated"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def rows(payloads, name):
    return list(csv.DictReader(io.StringIO(payloads[name].decode())))


class ConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads, cls.manifest = consolidation_payloads(INPUT)
        cls.projects = rows(cls.payloads, "projects.csv")
        cls.sites = rows(cls.payloads, "sites.csv")
        cls.evidence = rows(cls.payloads, "evidence.csv")
        cls.snapshot = json.loads(cls.payloads["source-records.json"])
        cls.mapping = json.loads(cls.payloads["identity-mapping.json"])
        cls.report = json.loads(cls.payloads["selection-report.json"])
        cls.records = {entry["record"]["id"]: entry for entry in cls.snapshot["records"]}
        cls.resolved = {item["source_record_id"]: item for item in cls.report["source_record_resolutions"]}
        cls.by_id = {project["project_id"]: project for project in cls.projects}
        cls.base = list(csv.DictReader(io.StringIO((ROOT / "verified_construction_core/2026-10-13/projects.csv").read_text())))

    def workspace(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        spec = json.loads(INPUT.read_bytes())
        source_paths = [spec["source_snapshot"]["path"], spec["identity_mapping"]["path"]]
        for relative in source_paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        shutil.copytree(ROOT / spec["base_dataset"], root / spec["base_dataset"])
        input_path = root / "input.json"
        input_path.write_bytes(canonical(spec))
        return root, input_path, spec

    def mutate(self, root, input_path, spec, key, obj):
        path = root / spec[key]["path"]
        path.write_bytes(canonical(obj))
        spec[key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        input_path.write_bytes(canonical(spec))

    def test_full_inventory_is_lossless_and_all_sources_resolve(self):
        self.assertEqual(len(self.records), 231)
        self.assertEqual(len(self.resolved), 231)
        details = {}
        for project in self.projects:
            for detail in json.loads(project["project_details_json"]):
                identifier = detail["source_record_id"]
                original = self.records[identifier]
                self.assertEqual(detail["record"], original["record"])
                self.assertEqual(detail["source_sha256"], original["source_sha256"])
                self.assertEqual(detail["source_record_sha256"], hashlib.sha256(canonical(original["record"])).hexdigest())
                self.assertEqual(detail["source_repository_commit"], self.snapshot["source_repository_commit"])
                self.assertEqual(set(detail["source_evidence_ids"]), {source["id"] for source in original["record"]["sources"]})
                details[identifier] = detail
        for identifier, resolved in self.resolved.items():
            if resolved["project_id"] or resolved["related_project_ids"]:
                self.assertIn(identifier, details)
            else:
                self.assertIn(resolved["decision"], SNAPSHOT_ONLY)
        imported_evidence = [item for item in self.evidence if item["source_record_id"]]
        self.assertEqual(len(imported_evidence), 1109)
        self.assertEqual({row["source_record_id"] for row in imported_evidence}, set(self.records))
        for item in imported_evidence:
            entry = self.records[item["source_record_id"]]
            source = next(source for source in entry["record"]["sources"] if source["id"] == item["source_local_id"])
            self.assertEqual(item["source_url"], source["url"])
            self.assertEqual(item["published_at"], source.get("published") or "")
            self.assertEqual(item["retrieved_at"], source["accessed"])
            projection = {"source_record_id": item["source_record_id"], "source_record_sha256": entry["source_record_sha256"], "source": source}
            self.assertEqual(item["content_hash"], hashlib.sha256(canonical(projection)).hexdigest())
            self.assertEqual(item["content_hash_scope"], "source_record_projection")
            self.assertIn("imported:record", json.loads(item["roles_json"]))
        self.assertEqual(sum(row["publication_date_precision"] == "month" for row in imported_evidence), 16)
        self.assertEqual(sum(row["publication_date_precision"] == "unknown" for row in imported_evidence), 265)

    def test_existing_identity_status_geometry_and_source_rows_survive(self):
        stable = ("project_id", "project_stable_key", "site_id", "physical_site_stable_key", "name", "country",
                  "status_as_of", "status_age_days_at_review", "last_observed_physical_status", "status_evidence_id",
                  "status_source_url", "status_method", "verification_posture", "latitude", "longitude", "geometry_json",
                  "geometry_use_scope", "geometry_precision_scope", "geometry_evidence_id", "geometry_source_url")
        for original in self.base:
            actual = self.by_id[original["project_id"]]
            self.assertEqual({key: original[key] for key in stable}, {key: actual[key] for key in stable})
        baseline_evidence = list(csv.DictReader(io.StringIO((ROOT / "verified_construction_core/2026-10-13/evidence.csv").read_text())))
        by_evidence = {row["evidence_id"]: row for row in self.evidence}
        for original in baseline_evidence:
            self.assertEqual(original, {key: by_evidence[original["evidence_id"]][key] for key in original})

    def test_identity_decisions_preserve_campus_phase_and_program_scope(self):
        by_base = {row["project_stable_key"]: row for row in self.base}
        base_sites = {row["physical_site_stable_key"]: row["site_id"] for row in self.base}
        unique = exact = phases = programs = unresolved = 0
        for decision in self.mapping["decisions"]:
            result = self.resolved[decision["source_record_id"]]
            kind = decision["decision"]
            if kind == "exact_project":
                exact += 1
                target = by_base[decision["target_project_stable_key"]]
                self.assertEqual((result["project_id"], result["site_id"]), (target["project_id"], target["site_id"]))
            elif kind == "same_site_distinct_scope":
                phases += 1
                self.assertEqual(result["site_id"], base_sites[decision["target_physical_site_stable_key"]])
                self.assertNotIn(result["project_id"], {row["project_id"] for row in self.base})
            elif kind == "unique_site":
                unique += 1
                self.assertNotIn(result["site_id"], set(base_sites.values()))
            else:
                programs += kind == "multi_site_program"
                unresolved += kind == "unresolved"
                self.assertIsNone(result["project_id"])
                self.assertIsNone(result["site_id"])
        self.assertEqual((exact, phases, unique, programs, unresolved), (11, 21, 191, 6, 2))
        self.assertEqual(len(self.projects), len(self.base) + phases + unique)
        self.assertEqual(len(self.sites), len(base_sites) + unique)
        licking = self.resolved["microsoft-licking-county-ohio"]
        self.assertEqual(len(licking["related_site_ids"]), 3)
        for project_id in licking["related_project_ids"]:
            self.assertTrue(any(detail["source_record_id"] == "microsoft-licking-county-ohio" for detail in json.loads(self.by_id[project_id]["project_details_json"])))
        lancaster = next(item for item in self.mapping["decisions"] if item["source_record_id"] == "coreweave-lancaster-pennsylvania")
        self.assertEqual(lancaster["unmapped_components"][0]["name"], "1375 Harrisburg Pike planned site")

    def test_imported_dates_precision_and_verification_are_not_upgraded(self):
        for identifier, result in self.resolved.items():
            if result["decision"] not in {"unique_site", "same_site_distinct_scope"}:
                continue
            original, actual = self.records[identifier]["record"], self.by_id[result["project_id"]]
            self.assertEqual(actual["last_observed_physical_status"], original["status"])
            self.assertEqual(actual["status_as_of"], original["status_as_of"])
            self.assertEqual(actual["status_method"], "imported_documented_status")
            self.assertEqual(actual["verification_posture"], "imported_source_record")
            self.assertEqual(actual["geometry_authority_class"], "compiled_reference")
            self.assertEqual(actual["geometry_use_scope"], LOCATION_SCOPES[original["location"]["precision"]])
            self.assertEqual(actual["independent_imagery_verification"], "false")
            self.assertEqual(json.loads(actual["power_observations_json"]), [])

    def test_site_memberships_and_aggregate_lists_are_recomputed(self):
        base_sites = {row["site_id"]: row for row in csv.DictReader(io.StringIO(
            (ROOT / "verified_construction_core/2026-10-13/sites.csv").read_text()))}
        for site in self.sites:
            members = [row for row in self.projects if row["site_id"] == site["site_id"]]
            self.assertEqual(int(site["project_count"]), len(members))
            for site_key, project_key in (("project_ids_json", "project_id"), ("project_stable_keys_json", "project_stable_key"),
                                          ("statuses_json", "last_observed_physical_status"), ("geometry_evidence_ids_json", "geometry_evidence_id"),
                                          ("geometry_use_scopes_json", "geometry_use_scope")):
                if site["site_id"] in base_sites and site_key.startswith("geometry_"):
                    self.assertEqual(site[site_key], base_sites[site["site_id"]][site_key])
                    continue
                self.assertEqual(set(json.loads(site[site_key])), {row[project_key] for row in members})
            if site["site_id"] in base_sites:
                for key, value in base_sites[site["site_id"]].items():
                    if key.startswith("geometry_") or key in ("latitude", "longitude", "horizontal_uncertainty_metres", "horizontal_uncertainty_unknown_reason"):
                        self.assertEqual(site[key], value, key)
            self.assertEqual(site["oldest_status_as_of"], min(row["status_as_of"] for row in members))
            self.assertEqual(site["newest_status_as_of"], max(row["status_as_of"] for row in members))

    def test_release_is_reproducible_and_never_overwrites(self):
        self.assertEqual(validate_consolidation(INPUT, OUTPUT), self.manifest)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            build_consolidation(INPUT, output)
            with self.assertRaisesRegex(ConsolidationError, "new or empty"):
                build_consolidation(INPUT, output)
            (output / "projects.csv").write_text("tampered")
            with self.assertRaisesRegex(ConsolidationError, "not reproducible"):
                validate_consolidation(INPUT, output)

    def test_incomplete_or_duplicate_mapping_fails_closed(self):
        for mode in ("missing", "duplicate"):
            with self.subTest(mode=mode):
                root, input_path, spec = self.workspace()
                mapping = copy.deepcopy(self.mapping)
                if mode == "missing":
                    mapping["decisions"].pop()
                else:
                    mapping["decisions"].append(copy.deepcopy(mapping["decisions"][0]))
                self.mutate(root, input_path, spec, "identity_mapping", mapping)
                with self.assertRaisesRegex(ConsolidationError, "cover every|duplicate identity"):
                    consolidation_payloads(input_path, root=root)

    def test_snapshot_mapping_and_source_object_tampering_is_detected(self):
        for key in ("source_snapshot", "identity_mapping"):
            root, input_path, spec = self.workspace()
            (root / spec[key]["path"]).write_text("{}")
            with self.assertRaisesRegex(ConsolidationError, key + " hash differs"):
                consolidation_payloads(input_path, root=root)
        root, input_path, spec = self.workspace()
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["records"][0]["record"]["name"] = "changed source object"
        self.mutate(root, input_path, spec, "source_snapshot", snapshot)
        with self.assertRaisesRegex(ConsolidationError, "source record hash differs"):
            consolidation_payloads(input_path, root=root)

    def test_source_content_change_does_not_change_project_or_site_identity(self):
        root, input_path, spec = self.workspace()
        snapshot = copy.deepcopy(self.snapshot)
        entry = snapshot["records"][0]
        identifier = entry["record"]["id"]
        entry["record"]["notes"] = "An additional review note; identity remains the same."
        entry["source_record_sha256"] = hashlib.sha256(canonical(entry["record"])).hexdigest()
        self.mutate(root, input_path, spec, "source_snapshot", snapshot)
        payloads, _ = consolidation_payloads(input_path, root=root)
        changed = next(row for row in json.loads(payloads["selection-report.json"])["source_record_resolutions"] if row["source_record_id"] == identifier)
        for key in ("project_id", "site_id"):
            self.assertEqual(changed[key], self.resolved[identifier][key])
        self.assertNotEqual(changed["source_evidence_ids"], self.resolved[identifier]["source_evidence_ids"])

    def test_unresolved_record_local_source_references_fail(self):
        root, input_path, spec = self.workspace()
        snapshot = copy.deepcopy(self.snapshot)
        entry = snapshot["records"][0]
        entry["record"]["metrics"][0]["source_ids"] = ["missing"]
        entry["source_record_sha256"] = hashlib.sha256(canonical(entry["record"])).hexdigest()
        self.mutate(root, input_path, spec, "source_snapshot", snapshot)
        with self.assertRaisesRegex(ConsolidationError, "unresolved source reference"):
            consolidation_payloads(input_path, root=root)

    def test_schema_describes_every_published_code(self):
        schema = json.loads(self.payloads["schema.json"])
        for name, table in schema["tables"].items():
            values = rows(self.payloads, name)
            for field in table["fields"]:
                if field["logical_type"] == "string" and "allowed_values" in field:
                    self.assertTrue({row[field["name"]] for row in values if row[field["name"]]} <= set(field["allowed_values"]))

    def followup_update(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        shutil.copytree(OUTPUT, root / "base")
        source = {
            "id": "new", "kind": "company_disclosure", "title": "New construction observation",
            "source_url": "https://example.org/new-construction", "publisher": "Example Operator",
            "source_family": "example", "license": "all-rights-reserved", "attribution": "Example Operator",
            "published_at": "2026-10-14", "retrieved_at": "2026-10-14T08:00:00Z",
            "content_hash": hashlib.sha256(b"new source observation").hexdigest(),
            "summary": "Physical work was observed at the named project.",
        }
        (root / "source.json").write_bytes(canonical({"sources": [source]}))
        spec = {
            "format": "datacenter-atlas-update-input-v1", "updated_at": "2026-10-14", "base_dataset": "base",
            "base_manifest_sha256": hashlib.sha256((root / "base/manifest.json").read_bytes()).hexdigest(),
            "source_files": [{"path": "source.json", "sha256": hashlib.sha256((root / "source.json").read_bytes()).hexdigest()}],
            "additions": [{
                "project_stable_key": "curated:new-example:construction", "physical_site_stable_key": "curated:new-example",
                "name": "New example construction", "site_name": "New example campus", "country": "United States", "country_iso_a2": "US",
                "status": {"value": "under_construction", "as_of": "2026-10-14", "source_id": "new", "summary": source["summary"]},
                "locator": {"geometry": {"type": "Point", "coordinates": [-100, 30]}, "source_id": "new",
                            "scope": "campus_locator", "scope_class": "official_address_point", "authority": "official_source",
                            "method": "official_address", "precision": "Campus address point, not footprint.",
                            "identity_review": "The source names the campus.", "uncertainty_reason": "No measured accuracy stated."},
                "distinctness_review": "Distinct named development.", "successor_review": "No later status through the update date.",
            }],
        }
        path = root / "update.json"
        path.write_bytes(canonical(spec))
        return root, path, spec

    def test_followup_update_preserves_records_and_loads_new_schema_fields(self):
        root, input_path, _ = self.followup_update()
        output = root / "updates/2026-10-14"
        build_update(input_path, output, root=root)
        validate_update(input_path, output, root=root)
        version = discover_versions(output.parent)[0]
        atlas = load_atlas(version, "https://example.org/")
        self.assertEqual(len(atlas.projects), len(self.projects) + 1)
        new = next(row for row in atlas.projects if row["project_stable_key"] == "curated:new-example:construction")
        self.assertEqual(new["project_details"], [])
        source = atlas.evidence_by_id[new["status_evidence_id"]]
        self.assertEqual(source["publication_date_precision"], "day")
        self.assertEqual(source["content_hash_scope"], "source_provided_digest")
        for name in ("source-records.json", "identity-mapping.json"):
            self.assertEqual((output / name).read_bytes(), self.payloads[name])
        report = json.loads((output / "selection-report.json").read_bytes())
        self.assertEqual(report["source_record_resolutions"], self.report["source_record_resolutions"])
        for project in self.projects:
            self.assertEqual(atlas.project_by_id[project["project_id"]]["project_details"], json.loads(project["project_details_json"]))
        self.assertEqual(atlas.counts["imported_source_records"], 231)
        self.assertEqual(atlas.counts["imported_source_references"], 1109)

    def test_followup_withdrawal_keeps_source_evidence_and_updates_resolutions(self):
        root, input_path, spec = self.followup_update()
        spec["additions"] = []
        identifier = "acs-la-puebla-de-alfinden"
        project = self.by_id[self.resolved[identifier]["project_id"]]
        spec["withdrawals"] = [{"project_stable_key": project["project_stable_key"],
                               "replaces_status_evidence_id": project["status_evidence_id"],
                               "reason": "Identity requires further reconciliation.", "source_ids": ["new"]}]
        input_path.write_bytes(canonical(spec))
        payloads, manifest = update_payloads(input_path, root=root)
        self.assertEqual(manifest["counts"]["imported_source_references"], 1109)
        self.assertEqual(manifest["counts"]["snapshot_only_records"], 9)
        imported_before = {row["evidence_id"] for row in self.evidence if row["source_record_id"]}
        imported_after = {row["evidence_id"] for row in rows(payloads, "evidence.csv") if row["source_record_id"]}
        self.assertEqual(imported_before, imported_after)
        report = json.loads(payloads["selection-report.json"])
        resolution = next(item for item in report["source_record_resolutions"] if item["source_record_id"] == identifier)
        self.assertIsNone(resolution["project_id"])
        self.assertIsNone(resolution["site_id"])
        self.assertEqual(resolution["previous_project_id"], project["project_id"])
        for row in rows(payloads, "evidence.csv"):
            self.assertNotIn(project["project_id"], json.loads(row["project_ids_json"]))


if __name__ == "__main__":
    unittest.main()
