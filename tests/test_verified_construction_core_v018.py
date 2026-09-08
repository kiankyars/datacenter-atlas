"""Synthetic-only v0.18 draft contracts; no researched site is accepted here."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from datacenter_atlas import verified_construction_core_v018 as draft


class V018DraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = self.root / draft.BASELINE_RELATIVE_DIR
        shutil.copytree(draft.ROOT / draft.BASELINE_RELATIVE_DIR, self.baseline)
        (self.root / "sources").mkdir()
        (self.root / "definitions").mkdir()
        self.contract_path = self.root / "definitions/synthetic-v018-batch.json"
        self.output = self.root / "draft-output"
        self.source_path = self.root / "sources/curated-synthetic-v018.json"
        self.document = self.source_document("a", [32.6, 0.35], "Uganda")
        self.source_path.write_bytes(draft.core._json_bytes(self.document))
        self.contract = self.make_contract([self.source_path])
        self.pins = self.save_contract()

    @staticmethod
    def evidence(key: str) -> dict:
        return {
            "key": key,
            "kind": "company_disclosure",
            "title": "Synthetic fixture only",
            "source_url": f"https://example.test/{key}",
            "publisher": "Fixture publisher",
            "source_family": "synthetic_unittest",
            "license": "all-rights-reserved",
            "attribution": "Synthetic fixture",
            "published_at": "2026-08-01",
            "retrieved_at": "2026-09-08T01:00:00Z",
            "content_hash": hashlib.sha256(key.encode()).hexdigest(),
            "metadata": {"warning": "No real site or source claim; unit test only"},
        }

    def source_document(self, suffix: str, coordinates: list, country: str) -> dict:
        project_key = f"synthetic:campus-{suffix}:project"
        campus_key = f"synthetic:campus-{suffix}"
        return {
            "evidence": [
                self.evidence(f"status-{suffix}"),
                self.evidence(f"geometry-{suffix}"),
            ],
            "project": {
                "stable_key": project_key,
                "name": f"Synthetic project {suffix}",
                "country": country,
            },
            "campus": {
                "stable_key": campus_key,
                "name": f"Synthetic campus {suffix}",
                "country": country,
            },
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "as_of_date": "2026-08-01",
                    "method": "authoritative_physical_status_update",
                    "evidence_key": f"status-{suffix}",
                }
            ],
            "results": [
                {
                    "project_stable_key": project_key,
                    "parent_campus_stable_key": campus_key,
                    "geometry": {"type": "Point", "coordinates": coordinates},
                    "display_anchor": {"type": "Point", "coordinates": coordinates},
                    "geometry_source_ids": [f"geometry-{suffix}"],
                    "identity_source_ids": [f"status-{suffix}"],
                    "location_basis": "first_party_site_coordinate",
                    "semantics": {
                        "geometry_source_entity_kind": "campus",
                        "geometry_derivation": "direct_geometry",
                        "geometry_method": "first_party_published_point",
                        "geometry_scope_class": "named_campus_reference_point",
                        "geometry_authority_class": "official_source",
                        "geometry_use_scope": "campus_locator",
                        "precision_scope": "Fixture reference point only, not a footprint or survey claim.",
                        "horizontal_uncertainty_metres": None,
                        "horizontal_uncertainty_unknown_reason": "No source accuracy statement.",
                    },
                }
            ],
        }

    def make_contract(self, paths: list[Path]) -> dict:
        base_sites = draft.core._load_csv(
            self.baseline / "sites.csv", draft.core.SITE_FIELDS
        )
        sources, acceptances = [], []
        documents = [json.loads(path.read_text()) for path in paths]
        batch_keys = sorted(document["campus"]["stable_key"] for document in documents)
        for path, document in zip(paths, documents):
            status_id = document["results"][0]["identity_source_ids"][0]
            geometry_id = document["results"][0]["geometry_source_ids"][0]
            raw = path.read_bytes()
            for index, source_id in enumerate((status_id, geometry_id)):
                sources.append(
                    {
                        "source_id": source_id,
                        "path": path.relative_to(self.root).as_posix(),
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "evidence_pointer": f"/evidence/{index}",
                        "evidence_sha256": draft.canonical_sha256(
                            document["evidence"][index]
                        ),
                    }
                )
            acceptances.append(
                {
                    "project_stable_key": document["project"]["stable_key"],
                    "parent_campus_stable_key": document["campus"]["stable_key"],
                    "country_iso_a2": {"Uganda": "UG", "United States": "US"}[
                        document["project"]["country"]
                    ],
                    "identity": {
                        "source_id": status_id,
                        "project_pointer": "/project",
                        "project_sha256": draft.canonical_sha256(document["project"]),
                        "campus_pointer": "/campus",
                        "campus_sha256": draft.canonical_sha256(document["campus"]),
                    },
                    "status": {
                        "source_id": status_id,
                        "record_pointer": "/lifecycle/0",
                        "record_sha256": draft.canonical_sha256(
                            document["lifecycle"][0]
                        ),
                    },
                    "geometry": {
                        "source_id": geometry_id,
                        "record_pointer": "/results/0",
                        "record_sha256": draft.canonical_sha256(document["results"][0]),
                    },
                    "distinctness_review": {
                        "decision": "distinct_physical_site",
                        "scope": "single_physical_site",
                        "equivalent_campus_keys": [document["campus"]["stable_key"]],
                        "baseline_site_keys_sha256": draft.canonical_sha256(
                            sorted(
                                row["physical_site_stable_key"] for row in base_sites
                            )
                        ),
                        "batch_site_keys_sha256": draft.canonical_sha256(batch_keys),
                        "evidence_source_ids": [status_id, geometry_id],
                        "reason": "Synthetic fixture tests comparison scope only; no real physical-site adjudication.",
                    },
                }
            )
        return {
            "schema_version": draft.SCHEMA_VERSION,
            "batch_id": "synthetic-test",
            "base_preview_manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
            "lifecycle_reference_date": "2026-08-20",
            "geometry_identity_reviewed_at": "2026-09-08",
            "sources": sources,
            "acceptances": acceptances,
        }

    def save_contract(
        self,
        *,
        preserve_source_pins: bool = False,
        preserve_acceptance_pins: bool = False,
    ) -> draft.ReviewPins:
        raw = draft.core._json_bytes(self.contract)
        self.contract_path.write_bytes(raw)
        return draft.ReviewPins(
            contract_sha256=hashlib.sha256(raw).hexdigest(),
            source_sha256=self.pins.source_sha256
            if preserve_source_pins
            else {
                item["source_id"]: draft.canonical_sha256(item)
                for item in self.contract["sources"]
            },
            acceptance_sha256=self.pins.acceptance_sha256
            if preserve_acceptance_pins
            else {
                item["project_stable_key"]: draft.canonical_sha256(item)
                for item in self.contract["acceptances"]
            },
        )

    def rewrite_source(self) -> None:
        self.source_path.write_bytes(draft.core._json_bytes(self.document))
        self.contract = self.make_contract([self.source_path])
        self.pins = self.save_contract()

    def validate(self) -> draft.ValidatedBatch:
        return draft.validate_batch(self.contract_path, self.pins, root=self.root)

    def build(self) -> dict:
        return draft.build_draft(
            self.contract_path, self.pins, self.output, root=self.root
        )

    def test_two_phases_preserve_all_baseline_bytes_and_features(self) -> None:
        before = {path.name: path.read_bytes() for path in self.baseline.iterdir()}
        validated = self.validate()
        self.assertEqual(len(validated.acceptances), 1)
        self.assertFalse(self.output.exists())
        manifest = self.build()
        self.assertEqual(
            manifest,
            draft.validate_draft(
                self.output, self.contract_path, self.pins, root=self.root
            ),
        )
        self.assertEqual(
            before, {path.name: path.read_bytes() for path in self.baseline.iterdir()}
        )
        for name in ("projects.csv", "sites.csv", "evidence.csv"):
            self.assertTrue((self.output / name).read_bytes().startswith(before[name]))
        base_features = json.loads(before["sites.geojson"])["features"]
        features = json.loads((self.output / "sites.geojson").read_text())["features"]
        self.assertEqual(features[:100], base_features)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 101,
                "projects": 104,
                "evidence": 254,
                "countries": 41,
                "non_us_sites": 71,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 99,
            },
        )
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        self.assertEqual(manifest["release_status"], "draft")
        self.assertFalse((self.output / "map.html").exists())
        schema = json.loads((self.output / "schema.json").read_text())
        self.assertEqual(
            schema["format"],
            "datacenter-atlas-verified-construction-core-schema-v018-draft",
        )
        self.assertNotIn("map", schema)
        self.assertNotIn("preview_id", schema)
        self.assertFalse(any(key.startswith("v0_") for key in schema))
        inherited = schema["inherited_baseline_annotations"]
        self.assertEqual(inherited["preview_id"], "2026-08-20-preview-v0.17")
        self.assertEqual(
            inherited["annotations"]["v0_17_source_selection_accounting"][
                "artifact_selected_projects"
            ],
            103,
        )
        self.assertIn("not current expanded-cohort accounting", inherited["scope"])

    def test_denominators_country_share_and_unfinished_target_derive_from_rows(
        self,
    ) -> None:
        self.build()
        report = json.loads((self.output / "selection-report.json").read_text())
        gates = report["final_release_gates"]
        self.assertEqual(
            gates["site_count"], {"actual": 101, "required": 200, "passed": False}
        )
        self.assertEqual(
            gates["additional_site_count"],
            {"actual": 1, "required": 100, "passed": False},
        )
        self.assertEqual(
            gates["imagery_outcomes_complete"],
            {"actual": 10, "required": 104, "passed": False},
        )
        self.assertEqual(gates["maximum_single_country_share"]["actual"], 30 / 101)
        self.assertEqual(
            gates["non_us_site_count"],
            {"actual": 71, "required_minimum": 100, "passed": False},
        )
        self.assertFalse(gates["clean_clone_rebuild"]["passed"])
        self.assertFalse(gates["blind_review"]["passed"])
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        self.assertEqual(gates["blind_review"]["eligible_project_count"], 104)
        eligible_keys = gates["blind_review"]["eligible_project_stable_keys"]
        project_rows = draft.core._load_csv(self.output / "projects.csv")
        self.assertEqual(
            eligible_keys, sorted(row["project_stable_key"] for row in project_rows)
        )
        self.assertIn("synthetic:campus-a:project", eligible_keys)
        self.assertEqual(
            gates["blind_review"]["eligible_project_keys_sha256"],
            draft.canonical_sha256(eligible_keys),
        )
        self.assertEqual(report["country_counts"]["Uganda"], 1)
        self.assertEqual(sum(report["country_counts"].values()), 101)

    def test_schema_enum_includes_reviewed_delta_derivation(self) -> None:
        derivation = "synthetic_reviewed_v018_coordinate_derivation"
        self.document["results"][0]["semantics"]["geometry_derivation"] = derivation
        self.rewrite_source()
        self.build()
        schema = json.loads((self.output / "schema.json").read_text())
        field = next(
            item
            for item in schema["tables"]["projects.csv"]["fields"]
            if item["name"] == "geometry_derivation"
        )
        self.assertIn(derivation, field["allowed_values"])
        self.assertEqual(
            field["allowed_values_scope"],
            "frozen baseline schema plus values in reviewed draft rows",
        )
        self.assertIn("direct_geometry", field["allowed_values"])

    def test_successful_legacy_sample_cannot_certify_expanded_population(self) -> None:
        batch = self.validate()
        inherited_report = json.loads(batch.baseline["files"]["selection-report.json"])
        inherited_report["final_release_gates"]["blind_review"].update(
            sample_size=20, agreements=19, passed=True
        )
        batch.baseline["files"]["selection-report.json"] = draft.core._json_bytes(
            inherited_report
        )
        files, _ = draft._payloads(batch)
        gate = json.loads(files["selection-report.json"])["final_release_gates"][
            "blind_review"
        ]
        self.assertTrue(gate["inherited_baseline_review"]["passed"])
        self.assertEqual(gate["sample_size"], 0)
        self.assertEqual(gate["agreements"], 0)
        self.assertEqual(gate["eligible_project_count"], 104)
        self.assertFalse(gate["passed"])

    def test_publication_iso_datetimes_are_preserved_without_source_mutation(
        self,
    ) -> None:
        for value in (
            "2026-04-07T13:00:09Z",
            "2026-04-07T13:00:09+02:00",
            "2026-04-07T13:00:09.125",
            "2026-04-07",
        ):
            evidence = self.evidence("publication-test")
            evidence["published_at"] = value
            original = deepcopy(evidence)
            projected = draft._source_evidence(evidence, "publication-test")
            self.assertEqual(projected["published_at"], value)
            self.assertEqual(evidence, original)
        source_path = (
            draft.ROOT
            / "sources/curated-official-2026-07-22-goodman-databank-lax01-enrichment.json"
        )
        before = source_path.read_bytes()
        evidence = json.loads(before)["evidence"][0]
        projected = draft._source_evidence(evidence, "reviewed DataBank identity")
        self.assertEqual(projected["published_at"], "2026-04-07T13:00:09Z")
        self.assertEqual(source_path.read_bytes(), before)

    def test_invalid_or_post_retrieval_publication_datetimes_are_rejected(self) -> None:
        for value in (
            "2026-02-30T13:00:09Z",
            "2026-04-07T99:00:09Z",
            "not-a-date",
            "2026-09-08T02:00:00Z",
            "2026-09-09T00:00:00",
        ):
            evidence = self.evidence("bad-publication-test")
            evidence["published_at"] = value
            with (
                self.subTest(value=value),
                self.assertRaises(draft.DraftValidationError),
            ):
                draft._source_evidence(evidence, "bad-publication-test")

    def test_new_rows_leave_every_unestablished_claim_unknown(self) -> None:
        self.build()
        rows = draft.core._load_csv(
            self.output / "projects.csv", draft.core.PROJECT_FIELDS
        )
        row = rows[-1]
        for field in (
            "workloads_json",
            "role_claims_json",
            "power_observations_json",
            "annual_energy_observations_json",
            "efficiency_observations_json",
        ):
            self.assertEqual(row[field], "[]")
        for field in (
            "owner",
            "operator",
            "users",
            "tenants",
            "customers",
            "operating_model_evidence_id",
        ):
            self.assertEqual(row[field], "")
        self.assertEqual(row["operating_model"], "unknown")
        self.assertEqual(row["geometry_use_scope"], "campus_locator")
        self.assertEqual(row["independent_imagery_verification"], "false")

    def test_wrong_contract_pin_and_container_only_refresh_are_rejected(self) -> None:
        self.contract_path.write_bytes(self.contract_path.read_bytes() + b" ")
        with self.assertRaisesRegex(draft.DraftValidationError, "SHA-256 differs"):
            self.validate()
        self.pins = self.save_contract()
        self.contract["acceptances"][0]["distinctness_review"]["reason"] = (
            "Changed review"
        )
        self.pins = self.save_contract(preserve_acceptance_pins=True)
        with self.assertRaisesRegex(
            draft.DraftValidationError, "independent acceptance review pin"
        ):
            self.validate()

    def test_source_file_and_independent_source_pin_are_both_required(self) -> None:
        self.source_path.write_bytes(self.source_path.read_bytes() + b" ")
        with self.assertRaisesRegex(
            draft.DraftValidationError, "input SHA-256 differs"
        ):
            self.validate()
        raw = self.source_path.read_bytes()
        for spec in self.contract["sources"]:
            spec["sha256"] = hashlib.sha256(raw).hexdigest()
            spec["bytes"] = len(raw)
        self.pins = self.save_contract(preserve_source_pins=True)
        with self.assertRaisesRegex(
            draft.DraftValidationError, "independent source review pin"
        ):
            self.validate()

    def test_evidence_identity_status_and_geometry_record_pins_fail_closed(
        self,
    ) -> None:
        original = deepcopy(self.contract)
        mutations = [
            lambda item: item["sources"][0].update(evidence_sha256="0" * 64),
            lambda item: item["acceptances"][0]["identity"].update(
                project_sha256="0" * 64
            ),
            lambda item: item["acceptances"][0]["status"].update(
                record_sha256="0" * 64
            ),
            lambda item: item["acceptances"][0]["geometry"].update(
                record_sha256="0" * 64
            ),
        ]
        for mutate in mutations:
            self.contract = deepcopy(original)
            mutate(self.contract)
            self.pins = self.save_contract()
            with (
                self.subTest(contract=self.contract),
                self.assertRaisesRegex(
                    draft.DraftValidationError, "record SHA-256 differs"
                ),
            ):
                self.validate()

    def test_nonphysical_stale_future_or_wrong_project_status_is_rejected(self) -> None:
        original = deepcopy(self.document)
        mutations = [
            lambda item: item["lifecycle"][0].update(value="planned"),
            lambda item: item["lifecycle"][0].update(
                method="authoritative_announcement"
            ),
            lambda item: item["lifecycle"][0].update(as_of_date="2026-05-21"),
            lambda item: item["lifecycle"][0].update(as_of_date="2026-08-21"),
            lambda item: item["lifecycle"][0].update(evidence_key="unrelated-evidence"),
        ]
        for mutate in mutations:
            self.document = deepcopy(original)
            mutate(self.document)
            self.rewrite_source()
            with (
                self.subTest(source=self.document),
                self.assertRaises(draft.DraftValidationError),
            ):
                self.validate()

    def test_cutoff_cannot_move_with_a_later_geometry_review(self) -> None:
        self.contract["lifecycle_reference_date"] = "2026-09-08"
        self.pins = self.save_contract()
        with self.assertRaisesRegex(draft.DraftValidationError, "cutoff cannot move"):
            self.validate()

    def test_point_cannot_be_relocated_by_only_moving_anchor(self) -> None:
        self.document["results"][0]["display_anchor"]["coordinates"] = [0, 0]
        self.rewrite_source()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "Point display anchor differs"
        ):
            self.validate()

    def test_polygon_anchor_inside_and_boundary_semantics_are_required(self) -> None:
        record = self.document["results"][0]
        record["geometry"] = {
            "type": "Polygon",
            "coordinates": [
                [[32.5, 0.2], [32.7, 0.2], [32.7, 0.4], [32.5, 0.4], [32.5, 0.2]]
            ],
        }
        record["location_basis"] = "official_parcel"
        self.rewrite_source()
        self.validate()
        record["display_anchor"]["coordinates"] = [0, 0]
        self.rewrite_source()
        with self.assertRaisesRegex(draft.DraftValidationError, "outside its geometry"):
            self.validate()
        record["display_anchor"]["coordinates"] = [32.6, 0.35]
        record["semantics"]["geometry_use_scope"] = "official_boundary"
        self.rewrite_source()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "boundary evidence/semantics"
        ):
            self.validate()
        record["location_basis"] = "authoritative_site_boundary"
        self.rewrite_source()
        self.assertEqual(self.build()["counts"]["official_boundary_projects"], 6)

    def test_locality_centroids_zero_accuracy_and_unknown_iso_are_rejected(
        self,
    ) -> None:
        original = deepcopy(self.document)
        mutations = [
            lambda item: item["results"][0].update(location_basis="city_centroid"),
            lambda item: item["results"][0]["semantics"].update(
                horizontal_uncertainty_metres=0,
                horizontal_uncertainty_unknown_reason="",
            ),
            lambda item: item["results"][0]["semantics"].update(
                geometry_authority_class="community_source"
            ),
        ]
        for mutate in mutations:
            self.document = deepcopy(original)
            mutate(self.document)
            self.rewrite_source()
            with (
                self.subTest(source=self.document),
                self.assertRaises(draft.DraftValidationError),
            ):
                self.validate()
        self.document = original
        self.rewrite_source()
        self.contract["acceptances"][0]["country_iso_a2"] = "AA"
        self.pins = self.save_contract()
        with self.assertRaisesRegex(draft.DraftValidationError, "invalid ISO"):
            self.validate()

    def test_baseline_alias_and_incomplete_distinctness_review_are_rejected(
        self,
    ) -> None:
        acceptance = self.contract["acceptances"][0]
        original = deepcopy(acceptance["distinctness_review"])
        base_key = draft.core._load_csv(self.baseline / "sites.csv")[0][
            "physical_site_stable_key"
        ]
        mutations = [
            lambda item: item["equivalent_campus_keys"].append(base_key),
            lambda item: item.update(decision="unresolved"),
            lambda item: item.update(scope="regional_program"),
            lambda item: item.update(baseline_site_keys_sha256="0" * 64),
            lambda item: item.update(batch_site_keys_sha256="0" * 64),
            lambda item: item.update(evidence_source_ids=["status-a"]),
        ]
        for mutate in mutations:
            acceptance["distinctness_review"] = deepcopy(original)
            mutate(acceptance["distinctness_review"])
            self.pins = self.save_contract()
            with (
                self.subTest(review=acceptance["distinctness_review"]),
                self.assertRaises(draft.DraftValidationError),
            ):
                self.validate()

    def test_coincident_baseline_locator_is_not_an_additional_site(self) -> None:
        base = draft.core._load_csv(self.baseline / "sites.csv")[0]
        coordinates = [float(base["longitude"]), float(base["latitude"])]
        self.document["results"][0]["geometry"]["coordinates"] = coordinates
        self.document["results"][0]["display_anchor"]["coordinates"] = coordinates
        self.rewrite_source()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "coincident baseline/batch locator"
        ):
            self.validate()

    def test_two_new_projects_with_one_campus_are_rejected(self) -> None:
        second = deepcopy(self.contract["acceptances"][0])
        second["project_stable_key"] = "synthetic:second-project-same-campus"
        self.contract["acceptances"].append(second)
        self.pins = self.save_contract()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "duplicate or invalid batch campus"
        ):
            self.validate()

    def test_shared_new_evidence_is_aggregated_without_inflating_sites(self) -> None:
        second_path = self.root / "sources/curated-synthetic-v018-second.json"
        second = self.source_document("b", [-100.8, 36.2], "United States")
        second["evidence"][0] = deepcopy(self.document["evidence"][0])
        second["lifecycle"][0]["evidence_key"] = self.document["evidence"][0]["key"]
        second_path.write_bytes(draft.core._json_bytes(second))
        self.contract = self.make_contract([self.source_path, second_path])
        self.pins = self.save_contract()
        manifest = self.build()
        self.assertEqual(manifest["counts"]["physical_sites"], 102)
        self.assertEqual(manifest["counts"]["projects"], 105)
        self.assertEqual(manifest["counts"]["evidence"], 255)
        rows = draft.core._load_csv(self.output / "evidence.csv")
        shared = next(
            row for row in rows if row["source_url"] == "https://example.test/status-a"
        )
        self.assertEqual(len(json.loads(shared["project_ids_json"])), 2)
        self.assertEqual(manifest["counts"]["non_us_sites"], 71)

    def test_one_hundred_synthetic_additions_meet_count_not_publication(self) -> None:
        paths = []
        for index in range(100):
            document = self.source_document(
                f"volume-{index}", [32.6 + index * 0.001, 0.35], "Uganda"
            )
            path = self.root / f"sources/curated-synthetic-volume-{index}.json"
            path.write_bytes(draft.core._json_bytes(document))
            paths.append(path)
        self.contract = self.make_contract(paths)
        self.pins = self.save_contract()
        manifest = self.build()
        report = json.loads((self.output / "selection-report.json").read_text())
        self.assertEqual(manifest["counts"]["physical_sites"], 200)
        self.assertEqual(manifest["counts"]["projects"], 203)
        self.assertEqual(
            report["final_release_gates"]["additional_site_count"],
            {"actual": 100, "required": 100, "passed": True},
        )
        self.assertEqual(
            report["final_release_gates"]["imagery_outcomes_complete"],
            {"actual": 10, "required": 203, "passed": False},
        )
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        self.assertEqual(
            report["final_release_gates"]["non_us_site_count"],
            {"actual": 170, "required_minimum": 100, "passed": True},
        )
        self.assertEqual(
            report["final_release_gates"]["blind_review"]["eligible_project_count"],
            203,
        )

    def test_missing_source_attribution_and_future_capture_are_rejected(self) -> None:
        original = deepcopy(self.document)
        for field in (
            "source_url",
            "license",
            "attribution",
            "retrieved_at",
            "content_hash",
            "published_at",
        ):
            self.document = deepcopy(original)
            del self.document["evidence"][0][field]
            self.rewrite_source()
            with (
                self.subTest(field=field),
                self.assertRaises(draft.DraftValidationError),
            ):
                self.validate()
        self.document = original
        self.document["evidence"][0]["retrieved_at"] = "2026-09-09T00:00:00Z"
        self.rewrite_source()
        with self.assertRaisesRegex(draft.DraftValidationError, "retrieval follows"):
            self.validate()

    def test_invalid_polygon_topology_and_polygon_hole_anchor_are_rejected(
        self,
    ) -> None:
        original = deepcopy(self.document)
        polygons = [
            [[[32.5, 0.2], [32.7, 0.4], [32.7, 0.2], [32.5, 0.4], [32.5, 0.2]]],
            [
                [[32.5, 0.2], [32.7, 0.2], [32.7, 0.4], [32.5, 0.4], [32.5, 0.2]],
                [
                    [32.58, 0.3],
                    [32.62, 0.3],
                    [32.62, 0.38],
                    [32.58, 0.38],
                    [32.58, 0.3],
                ],
            ],
            [
                [[32.5, 0.2], [32.7, 0.2], [32.7, 0.4], [32.5, 0.4], [32.5, 0.2]],
                [[33.5, 0.2], [33.7, 0.2], [33.7, 0.4], [33.5, 0.4], [33.5, 0.2]],
            ],
        ]
        for polygon in polygons:
            self.document = deepcopy(original)
            self.document["results"][0]["geometry"] = {
                "type": "Polygon",
                "coordinates": polygon,
            }
            self.rewrite_source()
            with (
                self.subTest(polygon=polygon),
                self.assertRaises(draft.DraftValidationError),
            ):
                self.validate()

    def test_nonfinite_and_duplicate_source_json_are_rejected(self) -> None:
        for raw in (b'{"project":{},"project":{}}', b'{"project":NaN}'):
            self.source_path.write_bytes(raw)
            for spec in self.contract["sources"]:
                spec["sha256"] = hashlib.sha256(raw).hexdigest()
                spec["bytes"] = len(raw)
            self.pins = self.save_contract()
            with self.subTest(raw=raw), self.assertRaises(draft.DraftValidationError):
                self.validate()

    def test_missing_extra_review_pins_and_unsupported_contract_fields_fail_closed(
        self,
    ) -> None:
        self.pins = draft.ReviewPins(
            self.pins.contract_sha256,
            {**self.pins.source_sha256, "extra": "0" * 64},
            self.pins.acceptance_sha256,
        )
        with self.assertRaisesRegex(
            draft.DraftValidationError, "source review pin inventory"
        ):
            self.validate()
        self.pins = self.save_contract()
        self.contract["accepted_into_published_core"] = True
        self.pins = self.save_contract()
        with self.assertRaisesRegex(draft.DraftValidationError, "batch contract keys"):
            self.validate()

    def test_source_role_binding_and_unused_source_are_rejected(self) -> None:
        self.contract["acceptances"][0]["geometry"]["source_id"] = "status-a"
        self.pins = self.save_contract()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "primary geometry source"
        ):
            self.validate()
        self.contract["acceptances"][0]["geometry"]["source_id"] = "geometry-a"
        unused = {**self.contract["sources"][0], "source_id": "unused-source"}
        self.contract["sources"].append(unused)
        self.pins = self.save_contract()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "unused source documents"
        ):
            self.validate()

    def test_portable_source_and_contract_paths_reject_escape_and_symlink(self) -> None:
        self.contract["sources"][0]["path"] = "../outside.json"
        self.pins = self.save_contract()
        with self.assertRaisesRegex(
            draft.DraftValidationError, "nonportable source path"
        ):
            self.validate()
        self.contract = self.make_contract([self.source_path])
        link = self.root / "sources/source-link.json"
        link.symlink_to(self.source_path)
        self.contract["sources"][0]["path"] = "sources/source-link.json"
        self.pins = self.save_contract()
        with self.assertRaisesRegex(draft.DraftValidationError, "symlink"):
            self.validate()

    def test_altered_frozen_baseline_and_existing_output_are_never_overwritten(
        self,
    ) -> None:
        self.output.mkdir()
        marker = self.output / "user-work.txt"
        marker.write_text("preserve me")
        with self.assertRaisesRegex(
            draft.DraftValidationError, "refusing to overwrite"
        ):
            self.build()
        self.assertEqual(marker.read_text(), "preserve me")
        path = self.baseline / "projects.csv"
        path.write_bytes(path.read_bytes() + b"changed\n")
        with self.assertRaisesRegex(
            draft.DraftValidationError, "input SHA-256 differs"
        ):
            self.validate()

    def test_draft_revalidation_detects_tampering_even_with_refreshed_manifest(
        self,
    ) -> None:
        self.build()
        path = self.output / "selection-report.json"
        report = json.loads(path.read_text())
        report["counts"]["physical_sites"] = 200
        path.write_bytes(draft.core._json_bytes(report))
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        manifest_path.write_bytes(draft.core._json_bytes(manifest))
        with self.assertRaisesRegex(
            draft.DraftValidationError, "draft output bytes differ"
        ):
            draft.validate_draft(
                self.output, self.contract_path, self.pins, root=self.root
            )

    def test_staging_failure_leaves_no_output_and_preserves_baseline(self) -> None:
        baseline_hash = hashlib.sha256(
            (self.baseline / "manifest.json").read_bytes()
        ).hexdigest()
        with mock.patch.object(
            draft,
            "validate_draft",
            side_effect=draft.DraftValidationError(
                "injected staged verification failure"
            ),
        ):
            with self.assertRaisesRegex(draft.DraftValidationError, "injected staged"):
                self.build()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".draft-output.*")))
        self.assertEqual(
            hashlib.sha256((self.baseline / "manifest.json").read_bytes()).hexdigest(),
            baseline_hash,
        )

    def test_public_cli_is_not_switched_to_draft(self) -> None:
        source = (
            draft.ROOT / "scripts/build_verified_construction_core.py"
        ).read_text()
        self.assertIn(
            "from datacenter_atlas.verified_construction_core_v017 import", source
        )
        self.assertNotIn("verified_construction_core_v018", source)


if __name__ == "__main__":
    unittest.main()
