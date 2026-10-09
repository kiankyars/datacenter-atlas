"""Schema-v2 baseline corrections over synthetic records; no research is applied.

The fixture re-scopes the frozen v0.17 Digital Edge CGK rows to host-estate
context in a temporary root. The correction record, its extra geometry source,
the synthetic acceptance and the inherited-through release are test fixtures;
only tracked frozen inputs (the v0.17 baseline, the v0.16 site facts and the
CGK1 curated source) are read from the repository.
"""

from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from datacenter_atlas import verified_construction_core_v018 as draft


FACTS = "sources/verified-construction-core-v0.16-seven-country-diversity-site-facts.json"
IDENTITY = "sources/curated-official-2026-07-20-digital-edge-cgk1-bekasi.json"
ACCEPTANCE = "sources/curated-synthetic-v018-v2-acceptance.json"
CORRECTION = "sources/synthetic-v018-baseline-correction.json"
INHERITED = "verified_construction_core/2026-08-20-v0.18-draft-synthetic-inherited"
PROJECT_KEY = "curated:digital-edge-cgk-campus-bekasi:cgk1"
SITE_KEY = "curated:digital-edge-cgk-campus-bekasi"
PROJECT_ID = "b2e4945f-3d75-5d9b-b2bb-d65deb74c405"
SUPERSEDED_ID = "8acab3b0-70c6-5dae-9ca3-3cbf6ae3b975"
STT_KEY = "curated:stt-jakarta-data-centre-campus"
HOST_POSTURE = "recent_authoritative_physical_observation_plus_host_estate_context_only"
CORRECTION_ID = "synthetic-host-estate-rescope"
CSV_NAMES = ("projects.csv", "sites.csv", "evidence.csv")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cell(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evidence_id(record: dict) -> str:
    return draft.core.atlas_stable_id(
        "evidence", "curated-official", record["key"], record["content_hash"]
    )


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class BaselineCorrectionV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.baseline = self.root / draft.BASELINE_RELATIVE_DIR
        shutil.copytree(draft.ROOT / draft.BASELINE_RELATIVE_DIR, self.baseline)
        (self.root / "sources").mkdir()
        (self.root / "definitions").mkdir()
        for relative in (FACTS, IDENTITY):
            shutil.copyfile(draft.ROOT / relative, self.root / relative)
        self.inherited_manifest_sha256 = self.write_inherited_release()
        self.contract_path = self.root / "definitions/synthetic-v018-v2-batch.json"
        self.output = self.root / "draft-output"
        self.acceptance_document = self.make_acceptance_document()
        self.refresh()

    # Fixture construction -------------------------------------------------

    @staticmethod
    def evidence(key: str, retrieved_at: str = "2026-09-08T01:00:00Z") -> dict:
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
            "retrieved_at": retrieved_at,
            "content_hash": sha256(key.encode()),
            "metadata": {"warning": "No real site or source claim; unit test only"},
        }

    def make_acceptance_document(self) -> dict:
        return {
            "evidence": [
                self.evidence("status-a"),
                self.evidence("geometry-a"),
                self.evidence("crs-a"),
            ],
            "project": {
                "stable_key": "synthetic:campus-a:project",
                "name": "Synthetic project a",
                "country": "Uganda",
            },
            "campus": {
                "stable_key": "synthetic:campus-a",
                "name": "Synthetic campus a",
                "country": "Uganda",
            },
            "lifecycle": [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "as_of_date": "2026-08-01",
                    "method": "authoritative_physical_status_update",
                    "evidence_key": "status-a",
                }
            ],
            "results": [
                {
                    "project_stable_key": "synthetic:campus-a:project",
                    "parent_campus_stable_key": "synthetic:campus-a",
                    "geometry": {"type": "Point", "coordinates": [32.6, 0.35]},
                    "display_anchor": {"type": "Point", "coordinates": [32.6, 0.35]},
                    "geometry_source_ids": ["geometry-a", "crs-a"],
                    "identity_source_ids": ["status-a"],
                    "location_basis": "first_party_site_coordinate",
                    "semantics": {
                        "geometry_source_entity_kind": "campus",
                        "geometry_derivation": "direct_geometry",
                        "geometry_method": "first_party_published_point",
                        "geometry_scope_class": "named_campus_reference_point",
                        "geometry_authority_class": "official_source",
                        "geometry_use_scope": "campus_locator",
                        "precision_scope": "Fixture reference point only.",
                        "horizontal_uncertainty_metres": None,
                        "horizontal_uncertainty_unknown_reason": "No accuracy statement.",
                    },
                }
            ],
        }

    def write_inherited_release(self, **overrides: object) -> str:
        directory = self.root / INHERITED
        directory.mkdir(parents=True, exist_ok=True)
        files = {}
        for name in (*CSV_NAMES, "sites.geojson"):
            data = (self.baseline / name).read_bytes()
            (directory / name).write_bytes(data)
            files[name] = {"bytes": len(data), "sha256": sha256(data)}
        manifest = draft.core._json_bytes({
            "format": draft.DRAFT_MANIFEST_FORMAT_V1,
            "release_status": "draft",
            "base_preview_manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
            "base_preview_path": draft.BASELINE_RELATIVE_DIR,
            "files": files,
            **overrides,
        })
        (directory / "manifest.json").write_bytes(manifest)
        return sha256(manifest)

    def frozen(self) -> dict:
        rows = {name: table(self.baseline / name) for name in CSV_NAMES}
        lines = {name: (self.baseline / name).read_bytes().split(b"\n") for name in CSV_NAMES}
        features = json.loads((self.baseline / "sites.geojson").read_text())["features"]
        index = {
            "projects.csv": next(
                i for i, r in enumerate(rows["projects.csv"])
                if r["project_stable_key"] == PROJECT_KEY
            ),
            "sites.csv": next(
                i for i, r in enumerate(rows["sites.csv"])
                if r["physical_site_stable_key"] == SITE_KEY
            ),
            "evidence.csv": next(
                i for i, r in enumerate(rows["evidence.csv"])
                if r["evidence_id"] == SUPERSEDED_ID
            ),
        }
        feature_index = next(
            i for i, f in enumerate(features)
            if f["properties"]["physical_site_stable_key"] == SITE_KEY
        )

        def spec(name: str, id_field: str) -> dict:
            row = rows[name][index[name]]
            return {
                "file_line_number": index[name] + 2,
                id_field: row[id_field],
                "row_canonical_sha256": draft.canonical_sha256(row),
                "raw_line_sha256": sha256(lines[name][index[name] + 1]),
            }

        return {
            "project": rows["projects.csv"][index["projects.csv"]],
            "site": rows["sites.csv"][index["sites.csv"]],
            "feature": features[feature_index],
            "rows": {
                "release_path": draft.BASELINE_RELATIVE_DIR,
                "manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
                "projects_csv": spec("projects.csv", "project_stable_key"),
                "sites_csv": spec("sites.csv", "physical_site_stable_key"),
                "evidence_csv": spec("evidence.csv", "evidence_id"),
                "sites_geojson": {
                    "feature_index": feature_index,
                    "feature_canonical_sha256": draft.canonical_sha256(
                        features[feature_index]
                    ),
                },
            },
        }

    def make_correction_document(self) -> dict:
        facts_raw = (self.root / FACTS).read_bytes()
        facts = json.loads(facts_raw)
        superseded, result = facts["source_documents"][7], facts["results"][6]
        frozen = self.frozen()
        project, site, feature = frozen["project"], frozen["site"], frozen["feature"]
        reused = {
            "key": "synthetic-cgk-host-estate-context-reused-capture",
            "title": "Synthetic fixture: reused frozen host-estate capture",
            **{
                field: superseded[field]
                for field in (
                    "kind", "source_url", "publisher", "source_family", "license",
                    "attribution", "published_at", "retrieved_at", "content_hash",
                )
            },
            "metadata": {"warning": "Synthetic fixture; no real correction is applied"},
        }
        second = self.evidence("synthetic-cgk-reverification", "2026-10-09T11:10:37Z")
        acceptance_raw = (self.root / ACCEPTANCE).read_bytes()
        crs = json.loads(acceptance_raw)["evidence"][2]
        ids = {"reused": evidence_id(reused), "second": evidence_id(second), "crs": evidence_id(crs)}
        semantics = {
            "geometry_source_entity_kind": "host_estate",
            "geometry_derivation": project["geometry_derivation"],
            "geometry_method": "synthetic_host_estate_polygon_kept_as_context",
            "geometry_scope_class": "synthetic_host_estate_polygon_context_only",
            "geometry_authority_class": project["geometry_authority_class"],
            "geometry_use_scope": "host_estate_context",
            "precision_scope": "Synthetic fixture: the whole host estate, not a campus locator.",
            "horizontal_uncertainty_metres": None,
            "horizontal_uncertainty_unknown_reason": "Synthetic fixture: position in the estate is unknown.",
        }
        anchor = [float(project["longitude"]), float(project["latitude"])]
        record = {
            "project_stable_key": PROJECT_KEY,
            "parent_campus_stable_key": SITE_KEY,
            "geometry": json.loads(project["geometry_json"]),
            "display_anchor": {"type": "Point", "coordinates": anchor},
            "geometry_source_ids": [
                "fixture-host-estate",
                "fixture-reverification",
                "fixture-correction-crs",
            ],
            "identity_source_ids": ["fixture-cgk1-identity"],
            "location_basis": "host_estate_locality_context",
            "semantics": semantics,
        }
        identity_raw = (self.root / IDENTITY).read_bytes()
        identity = json.loads(identity_raw)
        properties = feature["properties"]
        precision, method = semantics["precision_scope"], semantics["geometry_method"]
        scope_class = semantics["geometry_scope_class"]
        reason = semantics["horizontal_uncertainty_unknown_reason"]
        return {
            "schema_version": "synthetic-baseline-correction-fixture-1",
            "reviewed_at": "2026-10-09",
            "lifecycle_reference_date": "2026-08-20",
            "accepted_additional_sites": 0,
            "source_bindings": [
                {"source_id": "fixture-host-estate", "evidence_pointer": "/evidence/0"},
                {"source_id": "fixture-reverification", "evidence_pointer": "/evidence/1"},
                {"source_id": "fixture-correction-crs", "evidence_pointer": "/evidence/2"},
            ],
            "evidence": [reused, second, crs],
            "results": [record],
            "supersedes": {
                "source_path": FACTS,
                "source_file_sha256": sha256(facts_raw),
                "source_file_bytes": len(facts_raw),
                "evidence_pointer": "/source_documents/7",
                "evidence_record_sha256": draft.canonical_sha256(superseded),
                "evidence_source_id": superseded["source_id"],
                "evidence_id": superseded["evidence_id"],
                "geometry_pointer": "/results/6",
                "geometry_record_sha256": draft.canonical_sha256(result),
                "locator_id": result["locator_id"],
                "frozen_baseline_rows": frozen["rows"],
                "inherited_unchanged_through": {
                    "release_path": INHERITED,
                    "manifest_sha256": self.inherited_manifest_sha256,
                    "rows_byte_identical_to_v017": True,
                },
                "correction_reason": "Synthetic fixture reason.",
                "frozen_artifact_mutated": False,
            },
            "required_unchanged_identity_bindings": [
                {
                    "source_id": "fixture-cgk1-identity",
                    "source_path": IDENTITY,
                    "source_file_sha256": sha256(identity_raw),
                    "source_file_bytes": len(identity_raw),
                    "evidence_pointer": "/evidence/0",
                    "evidence_record_sha256": draft.canonical_sha256(identity["evidence"][0]),
                    "project_pointer": "/project",
                    "project_sha256": draft.canonical_sha256(identity["project"]),
                    "campus_pointer": "/campus",
                    "campus_sha256": draft.canonical_sha256(identity["campus"]),
                    "lifecycle_pointer": "/lifecycle/0",
                    "lifecycle_sha256": draft.canonical_sha256(identity["lifecycle"][0]),
                },
                {
                    "source_id": "fixture-correction-crs",
                    "source_path": ACCEPTANCE,
                    "source_file_sha256": sha256(acceptance_raw),
                    "source_file_bytes": len(acceptance_raw),
                    "evidence_pointer": "/evidence/2",
                    "evidence_record_sha256": draft.canonical_sha256(crs),
                    "note": "Shared fixture CRS record copied byte-identically.",
                },
            ],
            "exact_row_deltas": {
                "projects.csv": {
                    "file_line_number": frozen["rows"]["projects_csv"]["file_line_number"],
                    "changed": {
                        "geometry_source_entity_kind": [project["geometry_source_entity_kind"], "host_estate"],
                        "geometry_method": [project["geometry_method"], method],
                        "geometry_scope_class": [project["geometry_scope_class"], scope_class],
                        "geometry_use_scope": [project["geometry_use_scope"], "host_estate_context"],
                        "geometry_precision_scope": [project["geometry_precision_scope"], precision],
                        "horizontal_uncertainty_unknown_reason": [
                            project["horizontal_uncertainty_unknown_reason"], reason,
                        ],
                        "geometry_evidence_id": [SUPERSEDED_ID, ids["reused"]],
                        "verification_posture": [project["verification_posture"], HOST_POSTURE],
                    },
                    "unchanged_includes": ["latitude", "longitude", "geometry_json"],
                },
                "sites.csv": {
                    "file_line_number": frozen["rows"]["sites_csv"]["file_line_number"],
                    "changed": {
                        "geometry_source_entity_kinds_json": [
                            site["geometry_source_entity_kinds_json"], cell(["host_estate"]),
                        ],
                        "geometry_methods_json": [site["geometry_methods_json"], cell([method])],
                        "geometry_scope_classes_json": [
                            site["geometry_scope_classes_json"], cell([scope_class]),
                        ],
                        "geometry_use_scopes_json": [
                            site["geometry_use_scopes_json"], cell(["host_estate_context"]),
                        ],
                        "geometry_precision_scopes_json": [
                            site["geometry_precision_scopes_json"], cell([precision]),
                        ],
                        "horizontal_uncertainty_unknown_reason": [
                            site["horizontal_uncertainty_unknown_reason"], reason,
                        ],
                        "geometry_evidence_ids_json": [
                            site["geometry_evidence_ids_json"], cell(sorted(ids.values())),
                        ],
                        "verification_posture": [site["verification_posture"], HOST_POSTURE],
                    },
                    "unchanged_includes": ["site_id", "project_ids_json"],
                },
                "sites.geojson": {
                    "feature_index": frozen["rows"]["sites_geojson"]["feature_index"],
                    "changed_properties": {
                        "geometry_scope_classes": [properties["geometry_scope_classes"], [scope_class]],
                        "geometry_use_scopes": [properties["geometry_use_scopes"], ["host_estate_context"]],
                        "geometry_precision_scopes": [properties["geometry_precision_scopes"], [precision]],
                        "verification_posture": [properties["verification_posture"], HOST_POSTURE],
                    },
                    "geometry_unchanged": True,
                },
                "evidence.csv": {
                    "removed": [
                        {
                            "evidence_id": SUPERSEDED_ID,
                            "file_line_number": frozen["rows"]["evidence_csv"]["file_line_number"],
                            "row_canonical_sha256": frozen["rows"]["evidence_csv"]["row_canonical_sha256"],
                        }
                    ],
                    "added": [
                        {"evidence_id": ids[name], "key": source["key"], "roles": ["geometry"], "project_ids": [PROJECT_ID]}
                        for name, source in (("reused", reused), ("second", second))
                    ],
                    "association_only": [
                        {
                            "evidence_id": ids["crs"],
                            "key": crs["key"],
                            "changed_field": "project_ids_json",
                            "after_adds_project_id": PROJECT_ID,
                            "note": "Shared with the synthetic acceptance.",
                        }
                    ],
                },
                "counts_relative_to_previous": {
                    "physical_sites": 0,
                    "projects": 0,
                    "evidence": 1,
                    "reviewed_site_locator_projects": -1,
                    "host_estate_context_projects": 1,
                    "official_boundary_projects": 0,
                    "countries": 0,
                    "non_us_sites": 0,
                },
            },
            "preservation_invariants": {
                "raw_evidence_body_sha256_unchanged": superseded["content_hash"],
                "raw_capture_retrieved_at_unchanged": superseded["retrieved_at"],
                "numeric_geometry_unchanged": True,
                "display_anchor_unchanged": anchor,
                "geometry_authority_class_unchanged": project["geometry_authority_class"],
                "physical_campus_key_unchanged": True,
                "construction_project_key_unchanged": True,
                "lifecycle_observation_unchanged": {
                    "value": project["last_observed_physical_status"],
                    "as_of_date": project["status_as_of"],
                    "method": project["status_method"],
                },
                "horizontal_uncertainty_metres": None,
                "site_count_unchanged": True,
                "old_file_not_modified": True,
                "frozen_v017_not_modified": True,
                "osm_way_version_unchanged": superseded["facts"]["version"],
                "intersecting_site_rows_unchanged": [STT_KEY],
            },
        }

    def make_contract(self) -> dict:
        def spec(source_id: str, relative: str, index: int) -> dict:
            raw = (self.root / relative).read_bytes()
            return {
                "source_id": source_id,
                "path": relative,
                "bytes": len(raw),
                "sha256": sha256(raw),
                "evidence_pointer": f"/evidence/{index}",
                "evidence_sha256": draft.canonical_sha256(json.loads(raw)["evidence"][index]),
            }

        acceptance = json.loads((self.root / ACCEPTANCE).read_bytes())
        correction = json.loads((self.root / CORRECTION).read_bytes())
        base_sites = table(self.baseline / "sites.csv")
        return {
            "schema_version": draft.SCHEMA_VERSION_V2,
            "batch_id": "synthetic-v2-test",
            "base_preview_manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
            "lifecycle_reference_date": "2026-08-20",
            "geometry_identity_reviewed_at": "2026-10-09",
            "sources": [
                spec("status-a", ACCEPTANCE, 0),
                spec("geometry-a", ACCEPTANCE, 1),
                spec("crs-a", ACCEPTANCE, 2),
                spec("fixture-host-estate", CORRECTION, 0),
                spec("fixture-reverification", CORRECTION, 1),
                spec("fixture-correction-crs", CORRECTION, 2),
            ],
            "acceptances": [
                {
                    "project_stable_key": "synthetic:campus-a:project",
                    "parent_campus_stable_key": "synthetic:campus-a",
                    "country_iso_a2": "UG",
                    "identity": {
                        "source_id": "status-a",
                        "project_pointer": "/project",
                        "project_sha256": draft.canonical_sha256(acceptance["project"]),
                        "campus_pointer": "/campus",
                        "campus_sha256": draft.canonical_sha256(acceptance["campus"]),
                    },
                    "status": {
                        "source_id": "status-a",
                        "record_pointer": "/lifecycle/0",
                        "record_sha256": draft.canonical_sha256(acceptance["lifecycle"][0]),
                    },
                    "geometry": {
                        "source_id": "geometry-a",
                        "record_pointer": "/results/0",
                        "record_sha256": draft.canonical_sha256(acceptance["results"][0]),
                    },
                    "distinctness_review": {
                        "decision": "distinct_physical_site",
                        "scope": "single_physical_site",
                        "equivalent_campus_keys": ["synthetic:campus-a"],
                        "baseline_site_keys_sha256": draft.canonical_sha256(
                            sorted(row["physical_site_stable_key"] for row in base_sites)
                        ),
                        "batch_site_keys_sha256": draft.canonical_sha256(["synthetic:campus-a"]),
                        "evidence_source_ids": ["status-a", "geometry-a"],
                        "reason": "Synthetic fixture tests comparison scope only.",
                    },
                }
            ],
            "baseline_corrections": [
                {
                    "correction_id": CORRECTION_ID,
                    "physical_site_stable_key": SITE_KEY,
                    "project_stable_key": PROJECT_KEY,
                    "frozen_rows": self.frozen()["rows"],
                    "geometry": {
                        "source_id": "fixture-host-estate",
                        "record_pointer": "/results/0",
                        "record_sha256": draft.canonical_sha256(correction["results"][0]),
                    },
                    "identity_source_id": "fixture-cgk1-identity",
                    "evidence_source_ids": [
                        "fixture-host-estate",
                        "fixture-reverification",
                        "fixture-correction-crs",
                    ],
                    "reason": "Synthetic fixture: inherited host-estate polygon is context only.",
                }
            ],
        }

    @staticmethod
    def pins_for(contract: dict, raw: bytes) -> draft.ReviewPins:
        return draft.ReviewPins(
            contract_sha256=sha256(raw),
            source_sha256={
                item["source_id"]: draft.canonical_sha256(item) for item in contract["sources"]
            },
            acceptance_sha256={
                item["project_stable_key"]: draft.canonical_sha256(item)
                for item in contract["acceptances"]
            },
            baseline_correction_sha256={
                item["correction_id"]: draft.canonical_sha256(item)
                for item in contract.get("baseline_corrections", [])
            },
        )

    def refresh(self, *, acceptance=None, correction=None, contract=None) -> None:
        """Rewrite every fixture link with correct hashes, then apply one tamper."""
        document = deepcopy(self.acceptance_document)
        if acceptance is not None:
            acceptance(document)
        (self.root / ACCEPTANCE).write_bytes(draft.core._json_bytes(document))
        record = self.make_correction_document()
        if correction is not None:
            correction(record)
        (self.root / CORRECTION).write_bytes(draft.core._json_bytes(record))
        value = self.make_contract()
        if contract is not None:
            contract(value)
        raw = draft.core._json_bytes(value)
        self.contract_path.write_bytes(raw)
        self.contract = value
        self.pins = self.pins_for(value, raw)

    def validate(self, pins: draft.ReviewPins | None = None) -> draft.ValidatedBatch:
        return draft.validate_batch(self.contract_path, pins or self.pins, root=self.root)

    def build(self) -> dict:
        return draft.build_draft(self.contract_path, self.pins, self.output, root=self.root)

    def assert_rejected(self, message: str, pins: draft.ReviewPins | None = None) -> None:
        with self.assertRaisesRegex(draft.DraftValidationError, message):
            self.validate(pins)

    # Acceptance of a valid v2 correction -----------------------------------

    def test_fixture_targets_the_frozen_rows_named_by_the_cgk_research(self) -> None:
        rows = self.frozen()["rows"]
        self.assertEqual(rows["projects_csv"]["file_line_number"], 37)
        self.assertEqual(rows["sites_csv"]["file_line_number"], 36)
        self.assertEqual(rows["evidence_csv"]["file_line_number"], 136)
        self.assertEqual(rows["sites_geojson"]["feature_index"], 34)
        self.assertEqual(
            rows["projects_csv"]["raw_line_sha256"],
            "9ff76443726b907a354edbbbdf25449ad34a7e848e8618d1dc50136f87d58a28",
        )
        self.assertEqual(
            rows["evidence_csv"]["row_canonical_sha256"],
            "f3eaf14176e5f432de34815a911d7a658817e47bb0c469d669edd440a39a15b9",
        )

    def test_valid_v2_correction_changes_only_the_enumerated_bytes(self) -> None:
        before = {path.name: path.read_bytes() for path in self.baseline.iterdir()}
        self.assertEqual(len(self.validate().baseline_corrections), 1)
        manifest = self.build()
        self.assertEqual(
            manifest,
            draft.validate_draft(self.output, self.contract_path, self.pins, root=self.root),
        )
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.baseline.iterdir()})
        self.assertEqual(manifest["format"], "datacenter-atlas-verified-construction-core-v018-draft-v2")
        self.assertEqual(manifest["counts"], {
            "physical_sites": 101, "projects": 104, "evidence": 256, "countries": 41,
            "non_us_sites": 71, "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 98, "host_estate_context_projects": 1,
        })
        self.assertFalse(manifest["publishable_as_final"])
        deltas = json.loads((self.root / CORRECTION).read_text())["exact_row_deltas"]
        for name, line, key in (
            ("projects.csv", 37, "project_stable_key"),
            ("sites.csv", 36, "physical_site_stable_key"),
        ):
            old = before[name].split(b"\n")
            new = (self.output / name).read_bytes().split(b"\n")
            self.assertEqual(new[: line - 1], old[: line - 1])
            self.assertEqual(new[line : len(old) - 1], old[line:-1])
            self.assertNotEqual(new[line - 1], old[line - 1])
            frozen = table(self.baseline / name)[line - 2]
            corrected = table(self.output / name)[line - 2]
            self.assertEqual(corrected[key], frozen[key])
            self.assertEqual(
                {field: [frozen[field], corrected[field]] for field in frozen if frozen[field] != corrected[field]},
                deltas[name]["changed"],
            )
            for field in ("latitude", "longitude", "geometry_json", "geometry_type"):
                self.assertEqual(corrected[field], frozen[field])
        old = before["evidence.csv"].split(b"\n")
        new = (self.output / "evidence.csv").read_bytes().split(b"\n")
        self.assertEqual(new[:135], old[:135])
        self.assertEqual(new[135:252], old[136:253])
        evidence = {row["evidence_id"]: row for row in table(self.output / "evidence.csv")}
        self.assertNotIn(SUPERSEDED_ID, evidence)
        for item in deltas["evidence.csv"]["added"]:
            self.assertEqual(json.loads(evidence[item["evidence_id"]]["roles_json"]), ["geometry"])
            self.assertEqual(json.loads(evidence[item["evidence_id"]]["project_ids_json"]), [PROJECT_ID])
        reused = evidence[deltas["evidence.csv"]["added"][0]["evidence_id"]]
        self.assertEqual(reused["retrieved_at"], "2026-08-23")
        self.assertEqual(reused["content_hash"], "659203fa82ba61ebea2778c64171289fb045adff8acb07c5e0552832a17c6a57")
        shared = evidence[deltas["evidence.csv"]["association_only"][0]["evidence_id"]]
        self.assertEqual(json.loads(shared["roles_json"]), ["geometry"])
        self.assertEqual(len(json.loads(shared["project_ids_json"])), 2)
        self.assertIn(PROJECT_ID, json.loads(shared["project_ids_json"]))
        base_features = json.loads(before["sites.geojson"])["features"]
        features = json.loads((self.output / "sites.geojson").read_text())["features"]
        for index, feature in enumerate(base_features):
            if index != 34:
                self.assertEqual(features[index], feature)
        self.assertEqual(features[34]["geometry"], base_features[34]["geometry"])
        self.assertEqual(features[34]["id"], base_features[34]["id"])
        old_props, new_props = base_features[34]["properties"], features[34]["properties"]
        self.assertEqual(
            {key: [old_props[key], new_props[key]] for key in old_props if old_props[key] != new_props[key]},
            deltas["sites.geojson"]["changed_properties"],
        )

    def test_v2_report_schema_readme_and_provenance_disclose_the_exception(self) -> None:
        self.build()
        report = json.loads((self.output / "selection-report.json").read_text())
        self.assertEqual(report["format"], "datacenter-atlas-v018-draft-selection-v2")
        (correction,) = report["baseline_corrections"]
        self.assertEqual(correction["correction_id"], CORRECTION_ID)
        self.assertEqual(correction["evidence_rows"]["removed"], [SUPERSEDED_ID])
        self.assertEqual(len(correction["evidence_rows"]["added"]), 2)
        self.assertEqual(correction["count_effect"]["reviewed_site_locator_projects"], -1)
        self.assertEqual(correction["additional_sites"], 0)
        exceptions = report["locator_exceptions"]
        self.assertEqual(exceptions["host_estate_context_projects"], 1)
        (row,) = exceptions["projects"]
        self.assertEqual(row["project_stable_key"], PROJECT_KEY)
        self.assertEqual(row["verification_posture"], HOST_POSTURE)
        self.assertFalse(row["counted_as_reviewed_site_locator"])
        self.assertFalse(row["display_anchor_is_site_position"])
        self.assertEqual(row["geometry_intersects_site_keys"], [STT_KEY])
        schema = json.loads((self.output / "schema.json").read_text())
        fields = {f["name"]: f for f in schema["tables"]["projects.csv"]["fields"]}
        self.assertIn("host_estate_context", fields["geometry_use_scope"]["allowed_values"])
        self.assertIn("host_estate", fields["geometry_source_entity_kind"]["allowed_values"])
        contract = schema["v018_draft_contract"]
        self.assertEqual(contract["schema_version"], draft.SCHEMA_VERSION_V2)
        self.assertEqual(contract["baseline_correction_geometry_use_scopes"], ["host_estate_context"])
        self.assertNotIn("host_estate_context", contract["geometry_use_scopes"])
        readme = (self.output / "README.md").read_text()
        self.assertIn("host-estate locality context only", readme)
        self.assertIn(CORRECTION_ID, readme)
        self.assertIn(
            "All inherited rows and features are preserved, except the changes made by "
            "pinned baseline corrections: the enumerated fields of 1 re-scoped project row, "
            "1 site row and 1 feature; 1 superseded evidence row dropped; and 1 shared "
            "evidence row gaining only the corrected project association.",
            readme,
        )
        provenance = json.loads((self.output / "review-provenance.json").read_text())
        self.assertEqual(provenance["baseline_corrections"], self.contract["baseline_corrections"])
        self.assertEqual(
            provenance["independent_baseline_correction_review_sha256"],
            dict(self.pins.baseline_correction_sha256),
        )

    def test_v1_contract_shape_and_bytes_are_unchanged_by_v2_support(self) -> None:
        def v1(value: dict) -> None:
            value["schema_version"] = draft.SCHEMA_VERSION
            value["geometry_identity_reviewed_at"] = "2026-09-08"
            value["sources"] = value["sources"][:3]
            del value["baseline_corrections"]

        self.refresh(contract=v1)
        manifest = self.build()
        self.assertEqual(manifest["format"], "datacenter-atlas-verified-construction-core-v018-draft-v1")
        self.assertNotIn("host_estate_context_projects", manifest["counts"])
        self.assertEqual(manifest["counts"]["reviewed_site_locator_projects"], 99)
        for name in CSV_NAMES:
            self.assertTrue(
                (self.output / name).read_bytes().startswith((self.baseline / name).read_bytes())
            )
        report = json.loads((self.output / "selection-report.json").read_text())
        self.assertNotIn("baseline_corrections", report)
        self.assertNotIn("locator_exceptions", report)
        self.assertIn(
            "All inherited rows and features are preserved. Locators",
            (self.output / "README.md").read_text(),
        )

    # Rejections ----------------------------------------------------------

    def test_v1_contract_keeps_rejecting_baseline_corrections(self) -> None:
        self.refresh(contract=lambda value: value.update(schema_version=draft.SCHEMA_VERSION))
        self.assert_rejected("batch contract keys differ")
        self.refresh(contract=lambda value: value.pop("baseline_corrections"))
        self.assert_rejected("batch contract keys differ")
        self.refresh(contract=lambda value: value.update(baseline_corrections=[]))
        self.assert_rejected("at least one baseline correction")

        def v1(value: dict) -> None:
            value["schema_version"] = draft.SCHEMA_VERSION
            value["sources"] = value["sources"][:3]
            del value["baseline_corrections"]

        self.refresh(contract=v1)
        pins = draft.ReviewPins(
            self.pins.contract_sha256,
            self.pins.source_sha256,
            self.pins.acceptance_sha256,
            {CORRECTION_ID: "0" * 64},
        )
        self.assert_rejected("require a v2 contract", pins)

    def test_tampered_frozen_row_hashes_fail_closed(self) -> None:
        for key, field, value, message in (
            ("projects_csv", "row_canonical_sha256", "0" * 64, "frozen projects row SHA-256 differs"),
            ("projects_csv", "raw_line_sha256", "0" * 64, "frozen projects raw line SHA-256 differs"),
            ("projects_csv", "file_line_number", 38, "frozen projects row identity differs"),
            ("sites_csv", "row_canonical_sha256", "0" * 64, "frozen sites row SHA-256 differs"),
            ("evidence_csv", "raw_line_sha256", "0" * 64, "frozen evidence raw line SHA-256 differs"),
            ("sites_geojson", "feature_canonical_sha256", "0" * 64, "frozen GeoJSON feature SHA-256 differs"),
        ):
            def tamper(contract: dict) -> None:
                contract["baseline_corrections"][0]["frozen_rows"][key][field] = value

            self.refresh(contract=tamper)
            with self.subTest(key=key, field=field):
                self.assert_rejected(message)

    def test_superseded_and_inherited_records_must_reproduce_the_frozen_rows(self) -> None:
        mutations = (
            (
                lambda doc: doc["supersedes"].update(evidence_record_sha256="0" * 64),
                "superseded evidence record SHA-256 differs",
            ),
            (
                lambda doc: doc["supersedes"].update(source_file_sha256="0" * 64),
                "not a pinned v0.17 portable input",
            ),
            (
                lambda doc: doc["supersedes"]["frozen_baseline_rows"]["evidence_csv"].update(
                    file_line_number=137
                ),
                "contract frozen rows differ from the correction record",
            ),
        )
        for mutate, message in mutations:
            self.refresh(correction=mutate)
            with self.subTest(message=message):
                self.assert_rejected(message)
        inherited = self.root / INHERITED
        lines = (inherited / "projects.csv").read_bytes().split(b"\n")
        lines[36] = lines[36].replace(b"campus_locator", b"project_locator", 1)
        (inherited / "projects.csv").write_bytes(b"\n".join(lines))
        manifest = json.loads((inherited / "manifest.json").read_text())
        raw = (inherited / "projects.csv").read_bytes()
        manifest["files"]["projects.csv"] = {"bytes": len(raw), "sha256": sha256(raw)}
        (inherited / "manifest.json").write_bytes(draft.core._json_bytes(manifest))
        self.inherited_manifest_sha256 = sha256((inherited / "manifest.json").read_bytes())
        self.refresh()
        self.assert_rejected("inherited projects row changed after v0.17")

    def test_changed_geometry_or_display_anchor_is_rejected(self) -> None:
        def move_anchor(doc: dict) -> None:
            doc["results"][0]["display_anchor"]["coordinates"][0] = 107.187

        def drop_vertex(doc: dict) -> None:
            del doc["results"][0]["geometry"]["coordinates"][0][1]

        for mutate, message in (
            (move_anchor, "display anchor differs from the frozen row"),
            (drop_vertex, "geometry differs from the frozen row"),
        ):
            self.refresh(correction=mutate)
            with self.subTest(message=message):
                self.assert_rejected(message)

    def test_correction_validator_requires_host_estate_and_frozen_authority(self) -> None:
        mutations = (
            (lambda s: s.update(geometry_use_scope="campus_locator"), "host-estate locality context"),
            (lambda s: s.update(geometry_source_entity_kind="campus"), "host-estate locality context"),
            (lambda s: s.update(geometry_authority_class="official_source"), "cannot change geometry authority"),
            (
                lambda s: s.update(horizontal_uncertainty_metres=50.0, horizontal_uncertainty_unknown_reason=""),
                "numeric site uncertainty",
            ),
        )
        for mutate, message in mutations:
            self.refresh(correction=lambda doc: mutate(doc["results"][0]["semantics"]))
            with self.subTest(message=message):
                self.assert_rejected(message)

    def test_host_estate_semantics_are_never_accepted_for_an_acceptance(self) -> None:
        record = json.loads((self.root / CORRECTION).read_text())["results"][0]
        with self.assertRaisesRegex(draft.DraftValidationError, "pinned baseline correction"):
            draft._geometry(record)
        for path, value in (
            (("location_basis",), "host_estate_locality_context"),
            (("semantics", "geometry_use_scope"), "host_estate_context"),
            (("semantics", "geometry_source_entity_kind"), "host_estate"),
        ):
            def mutate(document: dict) -> None:
                target = document["results"][0]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value

            for schema_version in (draft.SCHEMA_VERSION_V2, draft.SCHEMA_VERSION):
                def contract(value: dict) -> None:
                    if schema_version == draft.SCHEMA_VERSION:
                        value["schema_version"] = schema_version
                        value["sources"] = value["sources"][:3]
                        del value["baseline_corrections"]

                self.refresh(acceptance=mutate, contract=contract)
                with self.subTest(field=path[-1], schema=schema_version):
                    self.assert_rejected("only through a pinned baseline correction")

    def test_missing_extra_or_stale_correction_pins_fail_closed(self) -> None:
        missing = draft.ReviewPins(
            self.pins.contract_sha256, self.pins.source_sha256, self.pins.acceptance_sha256
        )
        self.assertEqual(dict(missing.baseline_correction_sha256), {})
        self.assert_rejected("independent baseline correction review pin differs", missing)
        extra = draft.ReviewPins(
            self.pins.contract_sha256,
            self.pins.source_sha256,
            self.pins.acceptance_sha256,
            {**self.pins.baseline_correction_sha256, "extra-correction": "0" * 64},
        )
        self.assert_rejected("baseline correction review pin inventory differs", extra)
        original = self.pins
        self.refresh(
            contract=lambda value: value["baseline_corrections"][0].update(reason="Changed review")
        )
        stale = draft.ReviewPins(
            self.pins.contract_sha256,
            self.pins.source_sha256,
            self.pins.acceptance_sha256,
            original.baseline_correction_sha256,
        )
        self.assert_rejected("independent baseline correction review pin differs", stale)

    def test_date_only_retrieval_is_accepted_only_for_the_reused_capture(self) -> None:
        self.refresh(correction=lambda doc: doc["evidence"][1].update(retrieved_at="2026-10-09"))
        self.assert_rejected("accepted only for a baseline correction's reused frozen capture")
        self.refresh(correction=lambda doc: doc["evidence"][0].update(content_hash="0" * 64))
        self.assert_rejected("not the reused frozen capture")

    def test_exact_deltas_must_equal_the_derived_correction(self) -> None:
        def drop_project_field(doc: dict) -> None:
            del doc["exact_row_deltas"]["projects.csv"]["changed"]["geometry_method"]

        def wrong_site_posture(doc: dict) -> None:
            doc["exact_row_deltas"]["sites.csv"]["changed"]["verification_posture"][1] = (
                "recent_authoritative_physical_observation_plus_reviewed_site_locator"
            )

        def drop_feature_property(doc: dict) -> None:
            del doc["exact_row_deltas"]["sites.geojson"]["changed_properties"]["verification_posture"]

        def keep_superseded_row(doc: dict) -> None:
            doc["exact_row_deltas"]["evidence.csv"]["removed"] = []

        def wrong_count_effect(doc: dict) -> None:
            doc["exact_row_deltas"]["counts_relative_to_previous"]["reviewed_site_locator_projects"] = 0

        def shared_row_declared_added(doc: dict) -> None:
            evidence = doc["exact_row_deltas"]["evidence.csv"]
            (shared,) = evidence.pop("association_only")
            evidence["association_only"] = []
            evidence["added"].append({
                "evidence_id": shared["evidence_id"], "key": shared["key"],
                "roles": ["geometry"], "project_ids": [PROJECT_ID],
            })
            doc["exact_row_deltas"]["counts_relative_to_previous"]["evidence"] = 2

        for mutate, message in (
            (drop_project_field, "projects.csv correction differs"),
            (wrong_site_posture, "sites.csv correction differs"),
            (drop_feature_property, "sites.geojson correction differs"),
            (keep_superseded_row, "remove exactly the superseded row"),
            (wrong_count_effect, "count effect differs"),
            (shared_row_declared_added, "already used by an acceptance"),
        ):
            self.refresh(correction=mutate)
            with self.subTest(mutation=mutate.__name__):
                self.assert_rejected(message)

    def test_record_header_bindings_and_invariants_fail_closed(self) -> None:
        def moved_anchor_invariant(doc: dict) -> None:
            doc["preservation_invariants"]["display_anchor_unchanged"] = [107.0, -6.0]

        def missing_invariant(doc: dict) -> None:
            del doc["preservation_invariants"]["frozen_v017_not_modified"]

        def unbound_source(doc: dict) -> None:
            doc["source_bindings"].pop()

        for mutate, message in (
            (lambda doc: doc.update(accepted_additional_sites=1), "cannot add sites"),
            (lambda doc: doc.update(lifecycle_reference_date="2026-09-01"), "cutoff cannot move"),
            (lambda doc: doc.update(reviewed_at="2026-10-10"), "outside the checkpoint review"),
            (unbound_source, "source bindings differ"),
            (moved_anchor_invariant, "invariant differs: display_anchor_unchanged"),
            (missing_invariant, "invariant differs: frozen_v017_not_modified"),
        ):
            self.refresh(correction=mutate)
            with self.subTest(message=message):
                self.assert_rejected(message)

    def test_every_invariant_key_is_machine_checked(self) -> None:
        def invariant(key: str, value: object):
            return lambda doc: doc["preservation_invariants"].update({key: value})

        def reused_version(doc: dict) -> None:
            doc["evidence"][0]["metadata"]["osm_version"] = 12

        for mutate, message in (
            (invariant("reviewer_note", "anything"), "not machine-checked: reviewer_note"),
            (invariant("stt_jakarta_rows_unchanged", True), "not machine-checked"),
            (invariant("osm_way_version_unchanged", 12), "invariant differs: osm_way_version_unchanged"),
            (invariant("osm_way_version_unchanged", "13"), "invariant differs: osm_way_version_unchanged"),
            (reused_version, "invariant differs: osm_way_version_unchanged"),
            (invariant("intersecting_site_rows_unchanged", [SITE_KEY]),
             "invariant differs: intersecting_site_rows_unchanged"),
            (invariant("intersecting_site_rows_unchanged", [STT_KEY, "curated:a"]),
             "invariant differs: intersecting_site_rows_unchanged"),
            (invariant("intersecting_site_rows_unchanged", ["synthetic:campus-a"]),
             "does not intersect the correction: synthetic:campus-a"),
        ):
            self.refresh(correction=mutate)
            with self.subTest(message=message):
                self.assert_rejected(message)

        def reused_matches(doc: dict) -> None:
            doc["evidence"][0]["metadata"]["osm_version"] = 13

        def optional_absent(doc: dict) -> None:
            del doc["preservation_invariants"]["osm_way_version_unchanged"]
            del doc["preservation_invariants"]["intersecting_site_rows_unchanged"]

        for mutate in (reused_matches, optional_absent):
            self.refresh(correction=mutate)
            with self.subTest(accepted=mutate.__name__):
                self.assertEqual(len(self.validate().baseline_corrections), 1)

    def test_intersecting_site_rows_must_match_the_inherited_through_draft(self) -> None:
        inherited = self.root / INHERITED
        names = [row["physical_site_stable_key"] for row in table(inherited / "sites.csv")]
        number = names.index(STT_KEY) + 1
        lines = (inherited / "sites.csv").read_bytes().split(b"\n")
        lines[number] = lines[number].replace(b"STT Jakarta", b"STT Jakarta (edited)", 1)
        (inherited / "sites.csv").write_bytes(b"\n".join(lines))
        manifest = json.loads((inherited / "manifest.json").read_text())
        raw = (inherited / "sites.csv").read_bytes()
        manifest["files"]["sites.csv"] = {"bytes": len(raw), "sha256": sha256(raw)}
        (inherited / "manifest.json").write_bytes(draft.core._json_bytes(manifest))
        self.inherited_manifest_sha256 = sha256((inherited / "manifest.json").read_bytes())
        self.refresh()
        self.assert_rejected(f"intersecting site rows changed after the inherited-through draft: {STT_KEY}")

    def test_inherited_through_release_must_be_a_later_v018_draft(self) -> None:
        def baseline_itself(doc: dict) -> None:
            doc["supersedes"]["inherited_unchanged_through"].update(
                release_path=draft.BASELINE_RELATIVE_DIR,
                manifest_sha256=draft.BASELINE_MANIFEST_SHA256,
            )

        self.refresh(correction=baseline_itself)
        self.assert_rejected("must be a later v0.18 draft, not the frozen baseline")
        for overrides in (
            {"format": "datacenter-atlas-verified-construction-core-preview-v17"},
            {"release_status": "preview"},
            {"base_preview_manifest_sha256": "0" * 64},
            {"base_preview_path": "verified_construction_core/2026-08-20-preview-v0.16"},
        ):
            self.inherited_manifest_sha256 = self.write_inherited_release(**overrides)
            self.refresh()
            with self.subTest(overrides=overrides):
                self.assert_rejected("not a v0.18 draft of the pinned v0.17 baseline")
        self.inherited_manifest_sha256 = self.write_inherited_release(
            format=draft.DRAFT_MANIFEST_FORMAT_V2
        )
        self.refresh()
        self.assertEqual(len(self.validate().baseline_corrections), 1)

    def test_unchanged_includes_must_name_columns(self) -> None:
        def free_text(doc: dict) -> None:
            doc["exact_row_deltas"]["sites.csv"]["unchanged_includes"].append("imagery fields")

        self.refresh(correction=free_text)
        self.assert_rejected("sites.csv exact delta lists an unchanged field that is not a column")

    def test_identity_binding_must_reproduce_the_frozen_status(self) -> None:
        def wrong_lifecycle(doc: dict) -> None:
            binding = doc["required_unchanged_identity_bindings"][0]
            identity = json.loads((self.root / IDENTITY).read_text())
            binding["lifecycle_pointer"] = "/project"
            binding["lifecycle_sha256"] = draft.canonical_sha256(identity["project"])

        self.refresh(correction=wrong_lifecycle)
        self.assert_rejected("frozen lifecycle observation differs")


if __name__ == "__main__":
    unittest.main()
