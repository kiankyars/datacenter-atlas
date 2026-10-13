"""Schema-v3 blind-review gate over synthetic records; no real review result is claimed.

The fixture builds a synthetic population release (the frozen v0.17 baseline
plus two synthetic campuses) in a temporary root, pre-registers a 20-project
sample over it with the same seed and ranking rule as the real
pre-registration, registers that synthetic pre-registration in a patched
builder registry, and records simulated reviewer outputs. Only the frozen v0.17
baseline is read from the repository, except by the last two test classes:
one recomputes the real pre-registration against the real thirty-sixth
checkpoint, and one rebuilds the thirty-sixth contract, with its CGK baseline
correction, as a v3 checkpoint that pins the real pre-registration and a
synthetic results record.
"""

from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock

from datacenter_atlas import expansion_200_thirty_sixth_reviewed as thirty_sixth
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
POPULATION = "verified_construction_core/2026-08-20-v0.18-draft-synthetic-blind-population"
POPULATION_CONTRACT = "definitions/synthetic-blind-population-batch.json"
PREREGISTRATION = "definitions/synthetic-blind-review-preregistration.json"
RESULTS = "sources/synthetic-blind-review-results.json"
CONTRACT = "definitions/synthetic-v018-v3-batch.json"
REAL_PREREGISTRATION = (
    "definitions/verified-construction-core-v0.18-blind-review-preregistration-v1.json"
)
# A synthetic publishing commit (sha1 of "synthetic-population-11"). With it the
# fixture sample covers both baseline MultiPolygons, several Polygons and the
# synthetic polygon campus b; test_fixture_sample_covers_the_geometry_kinds pins that.
COMMIT = "d8c73b8df7ea7298648466bc7ab58ea58754468a"
SYNTHETIC_B = "synthetic:blind-campus-b:project"
SYNTHETIC_C = "synthetic:blind-campus-c:project"
ADJUDICATOR = "synthetic-comparator"
METRES_PER_DEGREE_LATITUDE = 111132.0
OFFSETS = {"near": 300.0, "band_same": 2000.0, "band_different": 2000.0, "far": 5000.0}
EXPECTED_BANDS = {
    "near": "within_1000m",
    "band_same": "adjudication_band",
    "band_different": "adjudication_band",
    "far": "beyond_3000m",
}
DETERMINATIONS = {
    "uc": "under_construction_in_window",
    "not": "not_under_construction_in_window",
    "unknown": "unable_to_verify",
}
SUCCESSORS = {
    "uc": "none_found_on_or_before_cutoff",
    "not": "found_on_or_before_cutoff",
    "unknown": "not_checked",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def release_rows(release: Path) -> tuple[dict, dict]:
    projects = {row["project_stable_key"]: row for row in table(release / "projects.csv")}
    sites = {row["physical_site_stable_key"]: row for row in table(release / "sites.csv")}
    return projects, sites


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
        "content_hash": sha256(key.encode()),
        "metadata": {"warning": "No real site or source claim; unit test only"},
    }


def source_document(suffix: str, geometry: dict, anchor: list, basis: str) -> dict:
    project_key = f"synthetic:blind-campus-{suffix}:project"
    campus_key = f"synthetic:blind-campus-{suffix}"
    return {
        "evidence": [evidence(f"status-{suffix}"), evidence(f"geometry-{suffix}")],
        "project": {
            "stable_key": project_key,
            "name": f"Synthetic project {suffix}",
            "country": "Uganda",
        },
        "campus": {
            "stable_key": campus_key,
            "name": f"Synthetic campus {suffix}",
            "country": "Uganda",
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
                "geometry": geometry,
                "display_anchor": {"type": "Point", "coordinates": anchor},
                "geometry_source_ids": [f"geometry-{suffix}"],
                "identity_source_ids": [f"status-{suffix}"],
                "location_basis": basis,
                "semantics": {
                    "geometry_source_entity_kind": "campus",
                    "geometry_derivation": "direct_geometry",
                    "geometry_method": "synthetic_fixture_locator",
                    "geometry_scope_class": "named_campus_reference_point",
                    "geometry_authority_class": "official_source",
                    "geometry_use_scope": "campus_locator",
                    "precision_scope": "Fixture locator only, not a footprint or survey claim.",
                    "horizontal_uncertainty_metres": None,
                    "horizontal_uncertainty_unknown_reason": "No source accuracy statement.",
                },
            }
        ],
    }


DOCUMENTS = {
    "a": source_document(
        "a", {"type": "Point", "coordinates": [32.6, 0.35]}, [32.6, 0.35],
        "first_party_site_coordinate",
    ),
    "b": source_document(
        "b",
        {
            "type": "Polygon",
            "coordinates": [
                [[32.7, 0.5], [32.71, 0.5], [32.71, 0.51], [32.7, 0.51], [32.7, 0.5]]
            ],
        },
        [32.705, 0.505],
        "official_parcel",
    ),
    "c": source_document(
        "c", {"type": "Point", "coordinates": [32.8, 0.6]}, [32.8, 0.6],
        "first_party_site_coordinate",
    ),
}


def source_path(suffix: str) -> str:
    return f"sources/curated-synthetic-blind-{suffix}.json"


def make_contract(root: Path, suffixes: list[str], documents: dict = DOCUMENTS) -> dict:
    """A v1 contract accepting the synthetic campuses, as earlier tests build it."""
    base_sites = table(root / draft.BASELINE_RELATIVE_DIR / "sites.csv")
    documents = {suffix: documents[suffix] for suffix in suffixes}
    batch_keys = sorted(document["campus"]["stable_key"] for document in documents.values())
    sources, acceptances = [], []
    for suffix, document in documents.items():
        raw = (root / source_path(suffix)).read_bytes()
        status_id, geometry_id = f"status-{suffix}", f"geometry-{suffix}"
        for index, source_id in enumerate((status_id, geometry_id)):
            sources.append(
                {
                    "source_id": source_id,
                    "path": source_path(suffix),
                    "bytes": len(raw),
                    "sha256": sha256(raw),
                    "evidence_pointer": f"/evidence/{index}",
                    "evidence_sha256": draft.canonical_sha256(document["evidence"][index]),
                }
            )
        acceptances.append(
            {
                "project_stable_key": document["project"]["stable_key"],
                "parent_campus_stable_key": document["campus"]["stable_key"],
                "country_iso_a2": "UG",
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
                    "record_sha256": draft.canonical_sha256(document["lifecycle"][0]),
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
                        sorted(row["physical_site_stable_key"] for row in base_sites)
                    ),
                    "batch_site_keys_sha256": draft.canonical_sha256(batch_keys),
                    "evidence_source_ids": [status_id, geometry_id],
                    "reason": "Synthetic fixture tests comparison scope only.",
                },
            }
        )
    return {
        "schema_version": draft.SCHEMA_VERSION,
        "batch_id": "synthetic-blind-population",
        "base_preview_manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
        "lifecycle_reference_date": "2026-08-20",
        "geometry_identity_reviewed_at": "2026-09-08",
        "sources": sources,
        "acceptances": acceptances,
    }


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
        blind_review_sha256=draft.canonical_sha256(contract["blind_review"])
        if "blind_review" in contract
        else None,
    )


def point_at_distance(geometry: dict, metres: float) -> list[float]:
    """A point due north of the geometry's top vertex at ``metres`` (builder method)."""
    top = max(draft._geometry_positions(geometry), key=lambda position: position[1])
    low, high = 0.0, 0.2
    for _ in range(80):
        middle = (low + high) / 2
        found = draft.blind_review_location_comparison([top[0], top[1] + middle], geometry)
        low, high = (middle, high) if found["distance_m"] < metres else (low, middle)
    return [top[0], top[1] + (low + high) / 2]


class BlindReviewV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.template_directory.cleanup)
        template = Path(cls.template_directory.name) / "root"
        shutil.copytree(
            draft.ROOT / draft.BASELINE_RELATIVE_DIR, template / draft.BASELINE_RELATIVE_DIR
        )
        (template / "sources").mkdir()
        (template / "definitions").mkdir()
        for suffix, document in DOCUMENTS.items():
            (template / source_path(suffix)).write_bytes(draft.core._json_bytes(document))
        contract = make_contract(template, ["a", "b"])
        raw = draft.core._json_bytes(contract)
        (template / POPULATION_CONTRACT).write_bytes(raw)
        draft.build_draft(
            template / POPULATION_CONTRACT, pins_for(contract, raw), template / POPULATION,
            root=template,
        )
        cls.template = template

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "root"
        shutil.copytree(self.template, self.root)
        self.output = Path(self.temporary.name) / "draft-output"
        self.suffixes = ["a", "b"]
        self.documents = dict(DOCUMENTS)
        self.commit = COMMIT
        self.outcomes: dict[int, tuple[str, str]] = {}
        # The builder accepts only registered pre-registrations; the fixture
        # registers its synthetic one in a patched registry on every refresh.
        self.registry: dict[str, dict] = {}
        self.real_registry = draft.BLIND_REVIEW_PREREGISTRATIONS
        patcher = mock.patch.object(draft, "BLIND_REVIEW_PREREGISTRATIONS", self.registry)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.refresh()

    # Fixture construction -------------------------------------------------

    def make_preregistration(self) -> dict:
        projects, sites = release_rows(self.root / POPULATION)
        keys = sorted(projects)
        keys_sha256 = draft.canonical_sha256(keys)
        material = f"datacenter-atlas-blind-review-v1|{keys_sha256}|{self.commit}"
        seed = sha256(material.encode())
        # The fixture ranks independently of the builder.
        self.ranked = sorted((sha256(f"{seed}|{key}".encode()), key) for key in keys)
        sample = []
        for position, (rank, key) in enumerate(self.ranked[:20], 1):
            project = projects[key]
            sample.append(
                {
                    "position": position,
                    "project_stable_key": key,
                    "rank_sha256": rank,
                    "blind_inputs": {
                        "project_name": project["name"],
                        "campus_name": sites[project["physical_site_stable_key"]]["name"],
                        "country": project["country"],
                    },
                }
            )
        return {
            "schema_version": draft.BLIND_REVIEW_PREREGISTRATION_SCHEMA,
            "registered_at": "2026-10-09",
            "purpose": "Synthetic fixture only; no review is pre-registered.",
            "population": {
                "release_path": POPULATION,
                "manifest_sha256": sha256((self.root / POPULATION / "manifest.json").read_bytes()),
                "published_in_commit": self.commit,
                "eligible_project_count": len(keys),
                "eligible_project_keys_sha256": keys_sha256,
                "population_scope": draft.BLIND_REVIEW_POPULATION_SCOPE,
            },
            "sampling": {
                "method": "Synthetic fixture: rank by sha256(seed + '|' + key); take 20.",
                "seed_material": material,
                "seed_sha256": seed,
                "sample_size": 20,
                "formula_fixed_before_draw": True,
            },
            "protocol": {
                "lifecycle_reference_date": "2026-08-20",
                "physical_observation_window": ["2026-05-22", "2026-08-20"],
                "reviewers": "Synthetic fixture: simulated AI agents, not human reviewers.",
                "blind_inputs": [
                    "project_name", "campus_name", "country", "physical_observation_window",
                ],
                "withheld_from_reviewers": "Synthetic fixture: every Atlas field.",
                "reviewer_outputs": {
                    "construction_determination": "Synthetic fixture.",
                    "location": "Synthetic fixture.",
                    "identity_notes": "Synthetic fixture.",
                },
                "agreement_rules": {
                    "construction": "Synthetic fixture.",
                    "location": "Synthetic fixture.",
                    "agreement": "Synthetic fixture.",
                    "gate": "Synthetic fixture.",
                },
                "after_review": "Synthetic fixture.",
            },
            "sample": sample,
        }

    def review(self, position: int, key: str, site: dict, construction: str, location: str):
        geometry = json.loads(site["geometry_json"])
        top = max(draft._geometry_positions(geometry), key=lambda point: point[1])
        if location == "inside":
            point = [float(site["longitude"]), float(site["latitude"])]
        elif location == "unlocated":
            point = None
        else:
            point = [top[0], top[1] + OFFSETS[location] / METRES_PER_DEGREE_LATITUDE]
        determination = DETERMINATIONS[construction]
        evidence_rows = []
        if construction != "unknown":
            evidence_rows.append(
                {
                    "source_url": f"https://example.test/blind/{position}",
                    "observation_date": "2026-07-15" if construction == "uc" else "2026-04-01",
                    "literal_pointer": "Synthetic fixture quote.",
                    "capture_sha256": sha256(f"capture-{position}".encode()),
                }
            )
        adjudication = None
        if point is None:
            place = {
                "status": "unable_to_locate",
                "longitude": None,
                "latitude": None,
                "method": None,
                "source_url": None,
                "notes": "Synthetic fixture: no primary source locates the campus.",
            }
            rule, distance = "unable_to_locate", None
        else:
            place = {
                "status": "located",
                "longitude": point[0],
                "latitude": point[1],
                "method": "Synthetic fixture point.",
                "source_url": f"https://example.test/location/{position}",
            }
            # The comparator recomputes with the builder's published method.
            compared = draft.blind_review_location_comparison(point, geometry)
            band = compared["band"]
            if location in EXPECTED_BANDS and band != EXPECTED_BANDS[location]:
                raise AssertionError(f"fixture offset assumption failed at {position}: {band}")
            distance = round(compared["distance_m"], 1)
            if band == "adjudication_band":
                same = location == "band_same"
                rule = "adjudicated_same_campus" if same else "adjudicated_different_campus"
                adjudication = {
                    "adjudicated_by": ADJUDICATOR,
                    "adjudicated_at": "2026-10-10",
                    "reason": "Synthetic adjudication: both sides name the same campus."
                    if same
                    else "Synthetic adjudication: the reviewer point is a different campus.",
                }
            else:
                rule = band
        construction_agrees = determination == "under_construction_in_window"
        review = {
            "position": position,
            "project_stable_key": key,
            "reviewer_session_id": f"session-{position:02d}",
            "session_sequence": 10 * position,
            "session_status": "completed",
            "reviewed_at": "2026-10-10",
            "counted": True,
            "construction_determination": determination,
            "construction_evidence": evidence_rows,
            "successor_check": {
                "status": SUCCESSORS[construction],
                "notes": "Synthetic fixture successor check.",
            },
            "location": place,
            "identity_notes": "Synthetic fixture: no aliases.",
            "blindness_attestation": {
                "atlas_materials_accessed": False,
                "statement": "Synthetic fixture: no Atlas material was used.",
            },
        }
        row = {
            "position": position,
            "project_stable_key": key,
            "construction_agrees": construction_agrees,
            "location_distance_m": distance,
            "location_rule": rule,
            "adjudication": adjudication,
            "agreement": construction_agrees
            and rule in {"inside", "within_1000m", "adjudicated_same_campus"},
        }
        return review, row

    def make_results(self, preregistration: dict) -> dict:
        # Reviews compare against the pre-registered release, not the checkpoint.
        projects, sites = release_rows(self.root / POPULATION)
        reviews, comparison = [], []
        for entry in preregistration["sample"]:
            position, key = entry["position"], entry["project_stable_key"]
            construction, location = self.outcomes.get(position, ("uc", "inside"))
            site = sites[projects[key]["physical_site_stable_key"]]
            review, row = self.review(position, key, site, construction, location)
            reviews.append(review)
            comparison.append(row)
        agreements = sum(row["agreement"] for row in comparison)
        return {
            "schema_version": draft.BLIND_REVIEW_RESULTS_SCHEMA,
            "recorded_at": "2026-10-10",
            "preregistration": {
                "path": PREREGISTRATION,
                "sha256": sha256((self.root / PREREGISTRATION).read_bytes()),
            },
            "population": deepcopy(preregistration["population"]),
            "reviews": reviews,
            "comparison": comparison,
            "totals": {
                "sample_size": 20,
                "agreements": agreements,
                "gate_passed": agreements >= 19,
            },
            "disclosures": [
                "Synthetic fixture: the reviewers are simulated AI agents, not human reviewers."
            ],
        }

    def refresh(self, *, preregistration=None, results=None, contract=None, registry=None) -> None:
        """Rewrite the fixture with correct pins, then apply one tamper."""
        for suffix in self.suffixes:
            (self.root / source_path(suffix)).write_bytes(
                draft.core._json_bytes(self.documents[suffix])
            )
        document = self.make_preregistration()
        if preregistration is not None:
            preregistration(document)
        raw = draft.core._json_bytes(document)
        (self.root / PREREGISTRATION).write_bytes(raw)
        self.preregistration = document
        self.registry.clear()
        self.registry[document["population"]["manifest_sha256"]] = {
            "path": PREREGISTRATION, "bytes": len(raw), "sha256": sha256(raw),
        }
        if registry is not None:
            registry(self.registry)
        record = self.make_results(document)
        if results is not None:
            results(record)
        raw_results = draft.core._json_bytes(record)
        (self.root / RESULTS).write_bytes(raw_results)
        self.record = record
        value = make_contract(self.root, self.suffixes, self.documents)
        value.update(
            schema_version=draft.SCHEMA_VERSION_V3,
            batch_id="synthetic-v3-test",
            geometry_identity_reviewed_at="2026-10-10",
            baseline_corrections=[],
            blind_review={
                "preregistration": {
                    "path": PREREGISTRATION, "bytes": len(raw), "sha256": sha256(raw),
                },
                "results": {
                    "path": RESULTS, "bytes": len(raw_results), "sha256": sha256(raw_results),
                },
            },
        )
        if contract is not None:
            contract(value)
        raw_contract = draft.core._json_bytes(value)
        (self.root / CONTRACT).write_bytes(raw_contract)
        self.contract = value
        self.pins = pins_for(value, raw_contract)

    def validate(self, pins: draft.ReviewPins | None = None) -> draft.ValidatedBatch:
        return draft.validate_batch(self.root / CONTRACT, pins or self.pins, root=self.root)

    def build(self) -> dict:
        return draft.build_draft(self.root / CONTRACT, self.pins, self.output, root=self.root)

    def gate(self) -> dict:
        files, _ = draft._payloads(self.validate())
        report = json.loads(files["selection-report.json"])
        return report["final_release_gates"]["blind_review"]

    def assert_rejected(self, message: str, pins: draft.ReviewPins | None = None) -> None:
        with self.assertRaisesRegex(draft.DraftValidationError, message):
            self.validate(pins)

    def rejected(self, cases) -> None:
        """Each case is (keyword, mutator, message); keyword names the tampered file."""
        for keyword, mutate, message in cases:
            self.refresh(**{keyword: mutate})
            with self.subTest(message=message):
                self.assert_rejected(message)

    def sampled_site(self, position: int) -> tuple[str, dict, dict]:
        projects, sites = release_rows(self.root / POPULATION)
        key = self.preregistration["sample"][position - 1]["project_stable_key"]
        site = sites[projects[key]["physical_site_stable_key"]]
        return key, site, json.loads(site["geometry_json"])

    def first_position(self, kind: str) -> int:
        for entry in self.preregistration["sample"]:
            if self.sampled_site(entry["position"])[2]["type"] == kind:
                return entry["position"]
        raise AssertionError(f"no sampled {kind}")

    @staticmethod
    def session(record: dict, position: int, **fields) -> dict:
        """A copy of the default session at ``position`` with ``fields`` changed."""
        session = deepcopy(record["reviews"][position - 1])
        session.update(fields)
        return session

    # Acceptance -----------------------------------------------------------

    def test_fixture_sample_covers_the_geometry_kinds(self) -> None:
        projects, sites = release_rows(self.root / POPULATION)
        sample = [entry["project_stable_key"] for entry in self.preregistration["sample"]]
        kinds = [projects[key]["geometry_type"] for key in sample]
        self.assertIn(SYNTHETIC_B, sample)
        self.assertEqual(sample.index(SYNTHETIC_B) + 1, 19)
        self.assertEqual(kinds.count("MultiPolygon"), 2)
        self.assertGreaterEqual(kinds.count("Polygon"), 5)
        self.assertGreaterEqual(kinds.count("Point"), 5)
        # The default reviewer point is the site's display anchor. Comparison uses
        # the site geometry, and two frozen v0.17 anchors in this sample lie a few
        # metres outside their own polygons, so they compare as within_1000m.
        outside = []
        for key, row in zip(sample, self.record["comparison"], strict=True):
            site = sites[projects[key]["physical_site_stable_key"]]
            geometry = json.loads(site["geometry_json"])
            anchor = [float(site["longitude"]), float(site["latitude"])]
            covered = geometry["coordinates"] == anchor if geometry["type"] == "Point" else (
                draft._covers(draft._geometry_polygons(geometry), anchor)
            )
            self.assertEqual(row["location_rule"], "inside" if covered else "within_1000m")
            if not covered:
                outside.append(site["physical_site_stable_key"])
                self.assertLess(row["location_distance_m"], 10.0)
        self.assertEqual(
            sorted(outside),
            ["curated:borealis-blonduos-data-center-campus", "curated:racks-central-johor-ai-campus"],
        )

    def test_valid_v3_record_passes_the_gate_and_rebuilds_byte_for_byte(self) -> None:
        self.outcomes = {2: ("uc", "near"), 3: ("uc", "band_same"), 7: ("uc", "near")}
        self.refresh()
        population = {path.name: path.read_bytes() for path in (self.root / POPULATION).iterdir()}
        manifest = self.build()
        self.assertEqual(
            manifest,
            draft.validate_draft(self.output, self.root / CONTRACT, self.pins, root=self.root),
        )
        self.assertEqual(manifest["format"], draft.DRAFT_MANIFEST_FORMAT_V3)
        self.assertEqual(manifest["release_status"], "draft")
        self.assertFalse(manifest["publishable_as_final"])
        self.assertEqual(manifest["counts"]["projects"], 105)
        self.assertEqual(manifest["counts"]["host_estate_context_projects"], 0)
        # Without corrections every row, feature and CSV byte is the population's.
        for name in ("projects.csv", "sites.csv", "evidence.csv"):
            self.assertEqual((self.output / name).read_bytes(), population[name])
        self.assertEqual(
            json.loads((self.output / "sites.geojson").read_bytes())["features"],
            json.loads(population["sites.geojson"])["features"],
        )
        report = json.loads((self.output / "selection-report.json").read_text())
        self.assertEqual(report["format"], "datacenter-atlas-v018-draft-selection-v3")
        self.assertEqual(report["baseline_corrections"], [])
        self.assertEqual(report["locator_exceptions"]["host_estate_context_projects"], 0)
        gates = report["final_release_gates"]
        gate = gates["blind_review"]
        self.assertEqual((gate["sample_size"], gate["agreements"], gate["passed"]), (20, 20, True))
        self.assertEqual((gate["required_sample_size"], gate["required_agreements"]), (20, 19))
        self.assertTrue(gate["population_matches"])
        self.assertIsNone(gate["population_mismatch"])
        self.assertTrue(gate["reviewed_population_gate_passed"])
        self.assertEqual(gate["population_scope"], draft.BLIND_REVIEW_POPULATION_SCOPE)
        self.assertEqual(gate["reviewed_population"], self.preregistration["population"])
        self.assertEqual(
            gate["reviewed_claim_fields"],
            {
                "projects": list(draft.BLIND_REVIEW_PROJECT_CLAIM_FIELDS),
                "sites": list(draft.BLIND_REVIEW_SITE_CLAIM_FIELDS),
            },
        )
        self.assertEqual(gate["eligible_project_count"], 105)
        self.assertEqual(
            gate["eligible_project_keys_sha256"],
            self.preregistration["population"]["eligible_project_keys_sha256"],
        )
        self.assertEqual(
            gate["preregistration"],
            {
                **self.contract["blind_review"]["preregistration"],
                "registered_at": "2026-10-09",
                "seed_material": self.preregistration["sampling"]["seed_material"],
                "seed_sha256": self.preregistration["sampling"]["seed_sha256"],
            },
        )
        self.assertEqual(
            gate["results_record"],
            {**self.contract["blind_review"]["results"], "recorded_at": "2026-10-10"},
        )
        self.assertEqual(gate["reviewers"], self.preregistration["protocol"]["reviewers"])
        self.assertEqual(gate["disclosures"], self.record["disclosures"])
        self.assertEqual(gate["counted_session_rule"], draft.BLIND_REVIEW_COUNTED_SESSION_RULE)
        self.assertEqual(gate["uncounted_review_sessions"], [])
        self.assertEqual(gate["disagreement_positions"], [])
        recorded_rules = [row["location_rule"] for row in self.record["comparison"]]
        self.assertEqual(
            gate["location_rule_counts"],
            {rule: recorded_rules.count(rule) for rule in draft.LOCATION_RULES},
        )
        self.assertEqual(
            [recorded_rules[1], recorded_rules[2], recorded_rules[6]],
            ["within_1000m", "adjudicated_same_campus", "within_1000m"],
        )
        self.assertEqual(gate["location_agreements"], 20)
        outcomes = gate["sample_outcomes"]
        self.assertEqual([item["position"] for item in outcomes], list(range(1, 21)))
        for item, row in zip(outcomes, self.record["comparison"], strict=True):
            # Reported distances are the pinned recorded values, never recomputed floats.
            self.assertEqual(item["recorded_location_distance_m"], row["location_distance_m"])
            self.assertEqual(item["location_rule"], row["location_rule"])
            self.assertEqual(item["adjudication"], row["adjudication"])
            self.assertEqual(item["session_sequence"], 10 * item["position"])
        self.assertEqual(outcomes[2]["adjudication"]["adjudicated_by"], ADJUDICATOR)
        # Every other gate is unchanged by the blind review.
        self.assertFalse(gates["imagery_outcomes_complete"]["passed"])
        self.assertFalse(gates["publication_authorized"]["passed"])
        self.assertFalse(gates["clean_clone_rebuild"]["passed"])
        self.assertFalse(report["publishable_as_final"])
        provenance = json.loads((self.output / "review-provenance.json").read_text())
        self.assertEqual(provenance["independent_blind_review_sha256"], self.pins.blind_review_sha256)
        self.assertEqual(provenance["blind_review"], self.contract["blind_review"])
        self.assertEqual(provenance["baseline_corrections"], [])
        schema = json.loads((self.output / "schema.json").read_text())
        contract = schema["v018_draft_contract"]
        self.assertEqual(contract["schema_version"], draft.SCHEMA_VERSION_V3)
        self.assertEqual(contract["blind_review_results_schema"], draft.BLIND_REVIEW_RESULTS_SCHEMA)
        self.assertEqual(contract["blind_review_location_rules"], list(draft.LOCATION_RULES))
        self.assertEqual(
            contract["blind_review_counted_session_rule"], draft.BLIND_REVIEW_COUNTED_SESSION_RULE
        )
        self.assertEqual(contract["blind_review_claim_fields"], gate["reviewed_claim_fields"])
        fields = {field["name"]: field for field in schema["tables"]["projects.csv"]["fields"]}
        self.assertEqual(
            fields["geometry_use_scope"]["allowed_values_scope"],
            "frozen baseline schema plus values in reviewed draft rows",
        )
        readme = (self.output / "README.md").read_text()
        self.assertIn("All inherited rows and features are preserved. Locators", readme)
        self.assertNotIn("Baseline corrections:", readme)
        self.assertIn(
            "Blind review: 20/20 agreements in the pre-registered fixed sample of all 105 "
            "eligible projects; the blind-review gate (at least 19 of 20) is passed.",
            readme,
        )
        self.assertNotIn("recorded but not counted", readme)
        self.assertIn("AI research agents, not human reviewers", readme)

    def test_gate_threshold_is_nineteen_of_twenty(self) -> None:
        self.outcomes = {5: ("unknown", "inside")}
        self.refresh()
        gate = self.gate()
        self.assertEqual((gate["agreements"], gate["passed"]), (19, True))
        self.assertEqual(gate["disagreement_positions"], [5])
        self.assertEqual(gate["construction_agreements"], 19)
        self.outcomes = {5: ("unknown", "inside"), 6: ("uc", "band_different")}
        self.refresh()
        gate = self.gate()
        self.assertEqual((gate["sample_size"], gate["agreements"], gate["passed"]), (20, 18, False))
        self.assertFalse(gate["reviewed_population_gate_passed"])
        self.assertTrue(gate["population_matches"])
        self.assertEqual(gate["disagreement_positions"], [5, 6])
        self.assertEqual(gate["location_rule_counts"]["adjudicated_different_campus"], 1)
        self.assertFalse(self.record["totals"]["gate_passed"])
        self.outcomes = {5: ("not", "far"), 9: ("uc", "unlocated")}
        self.refresh()
        gate = self.gate()
        self.assertEqual((gate["agreements"], gate["passed"]), (18, False))
        self.assertEqual(gate["location_rule_counts"]["beyond_3000m"], 1)
        self.assertEqual(gate["location_rule_counts"]["unable_to_locate"], 1)

    # Population -------------------------------------------------------------

    def test_population_mismatch_reports_the_inherited_result_and_never_passes(self) -> None:
        self.suffixes = ["a", "b", "c"]
        self.refresh()
        manifest = self.build()
        self.assertEqual(manifest["counts"]["projects"], 106)
        report = json.loads((self.output / "selection-report.json").read_text())
        gate = report["final_release_gates"]["blind_review"]
        self.assertEqual((gate["sample_size"], gate["agreements"]), (20, 20))
        self.assertTrue(gate["reviewed_population_gate_passed"])
        self.assertFalse(gate["population_matches"])
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["eligible_project_count"], 106)
        mismatch = gate["population_mismatch"]
        self.assertEqual(mismatch["current_projects_not_in_reviewed_population"], [SYNTHETIC_C])
        self.assertEqual(mismatch["reviewed_projects_not_in_current_population"], [])
        self.assertEqual(mismatch["projects_with_changed_reviewed_claims"], [])
        self.assertEqual(mismatch["sampled_positions_not_covered"], [])
        self.assertEqual(mismatch["reviewed_eligible_project_count"], 105)
        self.assertEqual(mismatch["current_eligible_project_count"], 106)
        self.assertEqual(mismatch["reviewed_release_path"], POPULATION)
        self.assertEqual(
            mismatch["current_eligible_project_keys_sha256"], gate["eligible_project_keys_sha256"]
        )
        self.assertIn("different eligible population", gate["sample_scope"])
        readme = (self.output / "README.md").read_text()
        self.assertIn(
            "the pinned pre-registered result (20/20 agreements) was drawn from a different "
            "eligible population (105 projects, whose keys or blind-reviewed claims differ), "
            "not this checkpoint's 106 projects, so the blind-review gate is not passed.",
            readme,
        )

    def test_same_keys_with_changed_claims_are_a_different_population(self) -> None:
        # A later contract keeps every key but moves sampled campus b about 5.5 km
        # north and renames its project. The review is still recomputed against
        # the pre-registered geometry, so a disagreement cannot become an
        # agreement, and the gate never passes for the edited checkpoint.
        moved = deepcopy(DOCUMENTS["b"])
        for vertex in moved["results"][0]["geometry"]["coordinates"][0]:
            vertex[1] = round(vertex[1] + 0.05, 6)
        moved["results"][0]["display_anchor"]["coordinates"] = [32.705, 0.555]
        self.documents["b"] = moved
        self.refresh()
        gate = self.gate()
        self.assertEqual((gate["agreements"], gate["reviewed_population_gate_passed"]), (20, True))
        self.assertFalse(gate["population_matches"])
        self.assertFalse(gate["passed"])
        mismatch = gate["population_mismatch"]
        self.assertEqual(mismatch["projects_with_changed_reviewed_claims"], [SYNTHETIC_B])
        self.assertEqual(mismatch["sampled_positions_not_covered"], [19])
        self.assertEqual(mismatch["current_projects_not_in_reviewed_population"], [])
        self.assertEqual(mismatch["reviewed_projects_not_in_current_population"], [])

        def inside_the_moved_polygon(record: dict) -> None:
            record["reviews"][18]["location"].update(longitude=32.705, latitude=0.555)

        # Scored against the edited row this would be inside; it is 4,976 m from
        # the reviewed geometry, so the recorded inside rule is rejected.
        self.refresh(results=inside_the_moved_polygon)
        self.assert_rejected("position 19: recorded distance differs from the recomputed 4975.8 m")
        renamed = deepcopy(DOCUMENTS["b"])
        renamed["project"]["name"] = "Synthetic project b, renamed after review"
        self.documents["b"] = renamed
        self.refresh()
        mismatch = self.gate()["population_mismatch"]
        self.assertEqual(mismatch["projects_with_changed_reviewed_claims"], [SYNTHETIC_B])
        # A field the blind review did not test (here the geometry method) keeps
        # the population: imagery outcomes and semantics are other gates' claims.
        restated = deepcopy(DOCUMENTS["b"])
        restated["results"][0]["semantics"]["geometry_method"] = "synthetic_fixture_locator_v2"
        self.documents["b"] = restated
        self.refresh()
        gate = self.gate()
        self.assertTrue(gate["population_matches"])
        self.assertTrue(gate["passed"])

    def test_sampled_project_absent_from_the_checkpoint_is_reported_and_never_passes(self) -> None:
        for outcomes in ({}, {19: ("uc", "unlocated")}):
            self.suffixes = ["a"]
            self.outcomes = outcomes
            self.refresh()
            gate = self.gate()
            with self.subTest(outcomes=outcomes):
                self.assertFalse(gate["population_matches"])
                self.assertFalse(gate["passed"])
                mismatch = gate["population_mismatch"]
                self.assertEqual(mismatch["reviewed_projects_not_in_current_population"], [SYNTHETIC_B])
                self.assertEqual(mismatch["sampled_positions_not_covered"], [19])

    # Pre-registration -------------------------------------------------------

    def test_only_the_registered_preregistration_is_accepted(self) -> None:
        self.refresh(registry=lambda registry: registry.clear())
        self.assert_rejected("not the one registered in builder code for its population")
        self.refresh(
            registry=lambda registry: next(iter(registry.values())).update(sha256="0" * 64)
        )
        self.assert_rejected("not the one registered in builder code")
        # A second, internally consistent registration of the same population with
        # a freely chosen commit draws a different sample and is refused.
        self.refresh()
        first = deepcopy(self.registry)
        first_sample = [entry["project_stable_key"] for entry in self.preregistration["sample"]]
        self.commit = "e" * 40
        self.refresh(registry=lambda registry: (registry.clear(), registry.update(first)))
        second_sample = [entry["project_stable_key"] for entry in self.preregistration["sample"]]
        self.assertNotEqual(first_sample, second_sample)
        self.assert_rejected("not the one registered in builder code")
        # The real registry names exactly the published pre-registration.
        raw = (ROOT / REAL_PREREGISTRATION).read_bytes()
        published = json.loads(raw)["population"]["manifest_sha256"]
        self.assertEqual(
            {key: dict(value) for key, value in self.real_registry.items()},
            {published: {"path": REAL_PREREGISTRATION, "bytes": len(raw), "sha256": sha256(raw)}},
        )

    def test_tampered_file_and_review_pins_fail_closed(self) -> None:
        self.rejected(
            [
                ("contract", lambda c: c["blind_review"]["results"].update(sha256="0" * 64),
                 "input SHA-256 differs"),
                ("contract", lambda c: c["blind_review"]["preregistration"].update(bytes=1),
                 "input byte count differs"),
                ("contract", lambda c: c["blind_review"]["results"].update(path=PREREGISTRATION),
                 "blind review results must be under sources/"),
                ("contract", lambda c: c["blind_review"]["preregistration"].update(path=RESULTS),
                 "blind review preregistration must be under definitions/"),
                ("contract", lambda c: c["blind_review"].update(extra={}),
                 "blind review keys differ"),
                ("results", lambda r: r["preregistration"].update(sha256="0" * 64),
                 "name a different pre-registration"),
            ]
        )
        self.refresh()
        path = self.root / RESULTS
        path.write_bytes(path.read_bytes() + b" ")
        self.assert_rejected("input SHA-256 differs")
        self.refresh()
        self.assert_rejected(
            "independent blind review pin differs",
            replace(self.pins, blind_review_sha256="0" * 64),
        )
        self.assert_rejected(
            "independent blind review pin differs", replace(self.pins, blind_review_sha256=None)
        )
        stale = self.pins
        self.refresh(contract=lambda c: c["blind_review"]["results"].update(bytes=1))
        self.assert_rejected(
            "independent blind review pin differs",
            replace(self.pins, blind_review_sha256=stale.blind_review_sha256),
        )

    def test_sample_that_does_not_match_the_seed_is_rejected(self) -> None:
        def swap_last(document: dict) -> None:
            rank, key = self.ranked[20]
            document["sample"][19].update(project_stable_key=key, rank_sha256=rank)

        def reorder(document: dict) -> None:
            first, second = document["sample"][0], document["sample"][1]
            for field in ("project_stable_key", "rank_sha256", "blind_inputs"):
                first[field], second[field] = second[field], first[field]

        def resample(document: dict) -> None:
            # A consistent but different seed cannot keep the published sample.
            commit = "f" * 40
            keys_sha256 = document["population"]["eligible_project_keys_sha256"]
            material = f"datacenter-atlas-blind-review-v1|{keys_sha256}|{commit}"
            document["population"]["published_in_commit"] = commit
            document["sampling"].update(seed_material=material, seed_sha256=sha256(material.encode()))

        self.rejected(
            [
                ("preregistration", swap_last, "does not match its seed at position 20"),
                ("preregistration", reorder, "does not match its seed at position 1"),
                ("preregistration", resample, "does not match its seed"),
                ("preregistration", lambda d: d["sample"][0].update(rank_sha256="0" * 64),
                 "does not match its seed at position 1"),
                ("preregistration", lambda d: d["sampling"].update(seed_material="other-seed"),
                 "seed material is not bound"),
                ("preregistration", lambda d: d["sampling"].update(seed_sha256=sha256(b"x")),
                 "seed SHA-256 differs from its seed material"),
                ("preregistration", lambda d: d["sample"].pop(), "must list 20 positions"),
                ("preregistration", lambda d: d["sampling"].update(sample_size=19),
                 "sample size must be 20"),
                ("preregistration", lambda d: d["sampling"].update(formula_fixed_before_draw=False),
                 "not fixed before the draw"),
                ("preregistration", lambda d: d["sample"][3]["blind_inputs"].update(country="Atlantis"),
                 "blind inputs differ from the population release at position 4"),
                ("preregistration", lambda d: d["sample"][0].update(position=2),
                 "positions must run 1..20"),
                ("preregistration", lambda d: d["protocol"].update(
                    physical_observation_window=["2026-05-21", "2026-08-20"]),
                 "observation window differs"),
                ("preregistration", lambda d: d["protocol"].update(lifecycle_reference_date="2026-09-01"),
                 "lifecycle cutoff cannot move"),
            ]
        )

    def test_wrong_population_is_rejected(self) -> None:
        self.rejected(
            [
                ("preregistration", lambda d: d["population"].update(eligible_project_keys_sha256="0" * 64),
                 "population differs from its named release"),
                ("preregistration", lambda d: d["population"].update(eligible_project_count=104),
                 "population differs from its named release"),
                ("preregistration", lambda d: d["population"].update(manifest_sha256="0" * 64),
                 "input SHA-256 differs"),
                ("preregistration", lambda d: d["population"].update(release_path=draft.BASELINE_RELATIVE_DIR),
                 "not the frozen baseline"),
                ("preregistration", lambda d: d["population"].update(population_scope="baseline projects only"),
                 "full expanded eligible population"),
                ("preregistration", lambda d: d["population"].update(published_in_commit="1393e32"),
                 "full lower-case git SHA-1"),
                ("results", lambda r: r["population"].update(eligible_project_count=104),
                 "results population differs from the pre-registration"),
            ]
        )

    # Sessions ---------------------------------------------------------------

    def test_counted_session_is_the_earliest_blind_session(self) -> None:
        def add(*sessions):
            def mutate(record: dict) -> None:
                for build in sessions:
                    record["reviews"].append(build(record))

            return mutate

        def earlier(position: int, **fields):
            # A session started before the default counted one.
            defaults = {
                "reviewer_session_id": f"session-{position:02d}-earlier",
                "session_sequence": 10 * position - 1,
            }
            return lambda record: self.session(record, position, **{**defaults, **fields})

        def later(position: int, **fields):
            defaults = {
                "reviewer_session_id": f"session-{position:02d}-later",
                "session_sequence": 10 * position + 1,
            }
            return lambda record: self.session(record, position, **{**defaults, **fields})

        uncounted = {"counted": False, "counted_session_id": "session-05"}
        unverified = {
            "construction_determination": "unable_to_verify",
            "construction_evidence": [],
            "successor_check": {"status": "not_checked", "notes": "Synthetic fixture."},
        }
        breached = {
            "blindness_attestation": {
                "atlas_materials_accessed": True,
                "statement": "Synthetic fixture: the session opened the Atlas site.",
            }
        }

        def aborted(position: int):
            def build(record: dict) -> dict:
                return {
                    "position": position,
                    "project_stable_key": record["reviews"][position - 1]["project_stable_key"],
                    "reviewer_session_id": f"session-{position:02d}-interrupted",
                    "session_sequence": 10 * position - 2,
                    "session_status": "aborted",
                    "reviewed_at": "2026-10-09",
                    "counted": False,
                    "uncounted_reason": "aborted",
                    "counted_session_id": f"session-{position:02d}",
                    "abort_notes": "Synthetic fixture: interrupted before any output.",
                }

            return build

        # Cherry-picking: an earlier complete, blind session that could not verify
        # cannot be set aside for a later agreeing one, whatever reason is claimed.
        self.rejected(
            [
                ("results", add(earlier(5, **uncounted, uncounted_reason="later_duplicate", **unverified)),
                 "position 5: the counted session must be the earliest blind completed session, "
                 "session-05-earlier"),
                ("results", add(earlier(5, **uncounted, uncounted_reason="blindness_breach", **unverified)),
                 "position 5: the counted session must be the earliest blind completed session"),
                ("results", add(later(5, **uncounted, uncounted_reason="blindness_breach")),
                 "uncounted session session-05-later at position 5 is later_duplicate, not "
                 "blindness_breach"),
                ("results", add(later(5, **uncounted, uncounted_reason="aborted")),
                 "is later_duplicate, not aborted"),
                ("results", add(earlier(5, **uncounted, uncounted_reason="aborted", **breached)),
                 "is blindness_breach, not aborted"),
                ("results", add(later(5, counted=False, counted_session_id="session-04",
                                      uncounted_reason="later_duplicate")),
                 "uncounted session at position 5 must name its counted session"),
                ("results", add(later(5, counted=False, uncounted_reason="later_duplicate")),
                 "exactly the uncounted sessions carry uncounted_reason and counted_session_id"),
                ("results", add(later(5, uncounted_reason="later_duplicate", counted_session_id="session-05")),
                 "exactly the uncounted sessions carry"),
                ("results", add(later(5, uncounted_reason="superseded", **uncounted)),
                 "invalid blind review at position 5 uncounted reason"),
                ("results", add(later(5, session_sequence=50, **uncounted, uncounted_reason="later_duplicate")),
                 "session sequences repeat"),
                ("results", add(later(5, reviewer_session_id="session-05", **uncounted,
                                      uncounted_reason="later_duplicate")),
                 "session IDs repeat"),
                ("results", add(later(5)), "position 5 has more than one counted review"),
                ("results", add(lambda r: {**aborted(5)(r), "counted": True}),
                 "an aborted session is never counted"),
                ("results", add(lambda r: {**aborted(5)(r), "identity_notes": "Partial output."}),
                 "aborted blind review session keys differ"),
                ("results", add(lambda r: {**aborted(5)(r), "abort_notes": " "}),
                 "abort notes must be nonempty text"),
                ("results", lambda r: r["reviews"][4].update(session_sequence=0),
                 "session_sequence must be a positive integer"),
                ("results", lambda r: r["reviews"][4].update(session_status="partial"),
                 "invalid blind review session status"),
                ("results", lambda r: r["reviews"][4].update(
                    counted=False, uncounted_reason="later_duplicate", counted_session_id="session-04"),
                 "missing: 5"),
            ]
        )
        # Sessions set aside for a machine-checkable reason are reported in full:
        # an interrupted attempt, an unblinded attempt and a later blind duplicate
        # whose disagreeing determination is shown, not hidden.
        self.refresh(
            results=add(
                aborted(5),
                earlier(5, **uncounted, uncounted_reason="blindness_breach", **breached, **unverified),
                later(5, **uncounted, uncounted_reason="later_duplicate", **unverified),
            )
        )
        gate = self.gate()
        self.assertEqual((gate["agreements"], gate["passed"]), (20, True))
        self.assertEqual(
            [
                (item["reviewer_session_id"], item["uncounted_reason"], item["construction_determination"],
                 item["atlas_materials_accessed"])
                for item in gate["uncounted_review_sessions"]
            ],
            [
                ("session-05-interrupted", "aborted", None, None),
                ("session-05-earlier", "blindness_breach", "unable_to_verify", True),
                ("session-05-later", "later_duplicate", "unable_to_verify", False),
            ],
        )
        self.assertEqual(
            {item["counted_session_id"] for item in gate["uncounted_review_sessions"]}, {"session-05"}
        )
        self.assertEqual(gate["sample_outcomes"][4]["reviewer_session_id"], "session-05")
        files, _ = draft._payloads(self.validate())
        self.assertIn(
            "3 further review sessions were recorded but not counted under the counted-session "
            "rule; see selection-report.json.",
            files["README.md"].decode(),
        )
        # With every session at a position set aside, none is counted.
        self.refresh(
            results=lambda record: record["reviews"].__setitem__(4, aborted(5)(record))
        )
        self.assert_rejected("missing: 5")

    def test_atlas_surfaces_unblind_a_session(self) -> None:
        atlas_urls = [
            "https://kiankyars.github.io/datacenter-atlas/sites/aws-walqa/",
            "https://github.com/kiankyars/datacenter-atlas/blob/main/verified_construction_core/sites.csv",
            "https://raw.githubusercontent.com/KianKyars/Datacenter-Atlas/main/README.md",
            "https://codeload.github.com/kiankyars/datacenter-atlas/zip/refs/heads/main",
            "https://api.github.com/repos/kiankyars/datacenter-atlas/contents/sources",
            "https://web.archive.org/web/2026/https%3A%2F%2Fkiankyars.github.io%2Fdatacenter-atlas%2F",
            "https://github.com/someone-else/datacenter-atlas.git",
            "https://someone-else.github.io/datacenter_atlas/",
            "https://cdn.jsdelivr.net/gh/kiankyars/datacenter-atlas@main/sites.geojson",
        ]
        for url in atlas_urls:
            with self.subTest(url=url):
                self.assertTrue(draft._atlas_surface(url))
        for url in (
            "https://example.test/datacenter-atlas-report.pdf",
            "https://github.com/someone/datacenter-atlas-tools",
            "https://kiankyars.github.io/other-project/",
        ):
            with self.subTest(url=url):
                self.assertFalse(draft._atlas_surface(url))

        def cite(url: str, field: str):
            def mutate(record: dict) -> None:
                review = record["reviews"][0]
                target = review["construction_evidence"][0] if field == "evidence" else review["location"]
                target["source_url"] = url

            return mutate

        self.rejected(
            [
                ("results", cite(atlas_urls[0], "evidence"),
                 "position 1: a counted session cites an Atlas surface: " + re.escape(atlas_urls[0])),
                ("results", cite(atlas_urls[1], "location"), "a counted session cites an Atlas surface"),
                ("results", cite(atlas_urls[5], "evidence"), "a counted session cites an Atlas surface"),
            ]
        )

        # A session that cited the Atlas is set aside as a breach and reported with
        # the URLs, even when it attested no access.
        def breach_then_blind(record: dict) -> None:
            breach = self.session(
                record, 1, reviewer_session_id="session-01-atlas", session_sequence=9,
                counted=False, uncounted_reason="blindness_breach", counted_session_id="session-01",
            )
            breach["location"]["source_url"] = atlas_urls[1]
            record["reviews"].append(breach)

        self.refresh(results=breach_then_blind)
        [reported] = self.gate()["uncounted_review_sessions"]
        self.assertEqual(
            (reported["uncounted_reason"], reported["atlas_materials_accessed"], reported["atlas_surface_urls"]),
            ("blindness_breach", False, [atlas_urls[1]]),
        )

    def test_reviewer_output_is_kept_verbatim_and_must_agree(self) -> None:
        def output(**changes):
            def mutate(record: dict) -> None:
                review = record["reviews"][0]
                verbatim = {
                    "position": 1,
                    "construction_determination": review["construction_determination"],
                    "location": {
                        "status": "located",
                        "longitude": review["location"]["longitude"],
                        "latitude": review["location"]["latitude"],
                        "what_the_point_represents": "Synthetic fixture.",
                    },
                    "sources_searched": ["https://example.test/searched"],
                    "successor_check": "Synthetic fixture: none found.",
                }
                for key, value in changes.items():
                    if isinstance(value, dict):
                        verbatim[key] = {**verbatim[key], **value}
                    else:
                        verbatim[key] = value
                review["reviewer_output"] = verbatim

            return mutate

        self.refresh(results=output())
        self.assertTrue(self.gate()["passed"])
        self.refresh(results=output(construction_determination="Under construction (stage: piling)"))
        self.assertTrue(self.gate()["passed"])
        self.rejected(
            [
                ("results", output(position=2), "reviewer output names a different position"),
                ("results", output(construction_determination="unable_to_verify"),
                 "reviewer output determination differs"),
                ("results", output(location={"latitude": 0.0}), "reviewer output point differs"),
                ("results", lambda r: r["reviews"][0].update(reviewer_output={}),
                 "reviewer output must be a nonempty object"),
            ]
        )

    # Determinations, locations and adjudication ----------------------------------

    def test_construction_verdict_must_match_the_determination(self) -> None:
        self.outcomes = {5: ("unknown", "inside"), 6: ("not", "inside")}
        self.rejected(
            [
                ("results", lambda r: r["comparison"][4].update(construction_agrees=True, agreement=True),
                 "position 5: construction agreement differs from the determination"),
                ("results", lambda r: r["comparison"][5].update(construction_agrees=True, agreement=True),
                 "position 6: construction agreement differs from the determination"),
                ("results", lambda r: r["comparison"][0].update(construction_agrees=False, agreement=False),
                 "position 1: construction agreement differs from the determination"),
                ("results", lambda r: r["comparison"][4].update(agreement=True),
                 "position 5: agreement differs from the recomputation"),
                ("results", lambda r: r["reviews"][0]["construction_evidence"][0].update(
                    observation_date="2026-05-21"),
                 "needs an observation inside the window"),
                ("results", lambda r: r["reviews"][0]["successor_check"].update(status="not_checked"),
                 "needs no completion, opening or cancellation"),
                ("results", lambda r: r["reviews"][5].update(construction_evidence=[]),
                 "not_under_construction_in_window needs evidence"),
                ("results", lambda r: r["reviews"][0].update(construction_determination="under_construction"),
                 "invalid blind review at position 1 construction determination"),
                ("results", lambda r: r["reviews"][0]["construction_evidence"][0].update(capture_sha256="x"),
                 "evidence capture is not SHA-256"),
            ]
        )

    def test_evidence_retrieval_dates(self) -> None:
        def retrieved(value: str):
            return lambda r: r["reviews"][0]["construction_evidence"][0].update(retrieved_at=value)

        for value in ("2026-10-10", "2026-07-15", "2026-10-10T08:30:00Z", "2026-10-09T23:30:00-07:00"):
            self.refresh(results=retrieved(value))
            with self.subTest(retrieved_at=value):
                self.assertTrue(self.gate()["passed"])
        self.rejected(
            [
                ("results", retrieved("2027-12-31"), "retrieval must fall between its observation and the review"),
                ("results", retrieved("2026-07-14"), "retrieval must fall between its observation and the review"),
                ("results", retrieved("sometime last week"), "must be YYYY-MM-DD or an ISO datetime with a timezone"),
                ("results", retrieved("2026-10-10T08:30:00"), "must be YYYY-MM-DD or an ISO datetime with a timezone"),
                ("results", retrieved("2026-02-30"), "invalid blind review at position 1 evidence retrieval"),
            ]
        )

    def test_location_verdict_must_match_the_recomputation(self) -> None:
        self.outcomes = {4: ("uc", "far"), 8: ("uc", "near"), 12: ("uc", "unlocated")}

        def moved(record: dict) -> None:
            record["reviews"][7]["location"]["latitude"] += 0.05

        def shifted(metres: float):
            def mutate(record: dict) -> None:
                record["comparison"][7]["location_distance_m"] += metres

            return mutate

        self.rejected(
            [
                ("results", lambda r: r["comparison"][3].update(location_rule="within_1000m", agreement=True),
                 "position 4: location rule differs from the recomputed beyond_3000m"),
                ("results", lambda r: r["comparison"][7].update(location_rule="inside"),
                 "position 8: location rule differs from the recomputed within_1000m"),
                ("results", shifted(50.0), "position 8: recorded distance differs"),
                ("results", moved, "position 8: recorded distance differs"),
                ("results", lambda r: r["comparison"][7].update(location_distance_m=None),
                 "location distance must be finite metres"),
                ("results", lambda r: r["comparison"][11].update(location_rule="within_1000m", location_distance_m=10.0),
                 "unlocated review compares as unable_to_locate"),
                ("results", lambda r: r["comparison"][0].update(
                    location_rule="unable_to_locate", location_distance_m=None, agreement=False),
                 "position 1: the review located a point"),
                ("results", lambda r: r["reviews"][11]["location"].update(longitude=1.0, latitude=1.0),
                 "unable_to_locate carries no coordinates"),
                ("results", lambda r: r["reviews"][0]["location"].update(latitude=91.0),
                 "point is not finite WGS84"),
                ("results", lambda r: r["reviews"][0]["location"].update(source_url="ftp://example.test/x"),
                 "invalid blind review at position 1 location source URL"),
            ]
        )
        # A recorded distance inside max(5 m, 1 %) of the recomputation is accepted.
        self.refresh(results=shifted(4.0))
        self.assertEqual(self.gate()["agreements"], 18)

    def test_recorded_distance_must_lie_in_its_rule_band(self) -> None:
        # Within the max(5 m, 1 %) tolerance a published distance could otherwise
        # sit on the far side of a threshold from its own rule.
        position = self.first_position("Polygon")
        _, _, geometry = self.sampled_site(position)
        inside = next(
            row["position"] for row in self.record["comparison"] if row["location_rule"] == "inside"
        )

        def located(metres: float, recorded: float, rule: str, adjudicated: bool = False):
            point = point_at_distance(geometry, metres)

            def mutate(record: dict) -> None:
                record["reviews"][position - 1]["location"].update(longitude=point[0], latitude=point[1])
                record["comparison"][position - 1].update(
                    location_distance_m=recorded,
                    location_rule=rule,
                    adjudication={
                        "adjudicated_by": ADJUDICATOR, "adjudicated_at": "2026-10-10",
                        "reason": "Synthetic adjudication: the same campus.",
                    }
                    if adjudicated
                    else None,
                    agreement=rule in draft.AGREEING_LOCATION_RULES,
                )
                record["totals"].update(
                    agreements=sum(row["agreement"] for row in record["comparison"]),
                    gate_passed=sum(row["agreement"] for row in record["comparison"]) >= 19,
                )

            return mutate

        self.rejected(
            [
                ("results", located(995.0, 1004.0, "within_1000m"),
                 f"position {position}: recorded distance 1004.0 m lies outside the within_1000m band"),
                ("results", located(1004.0, 996.0, "adjudicated_same_campus", True),
                 "lies outside the adjudicated_same_campus band"),
                ("results", located(2985.0, 3014.6, "adjudicated_same_campus", True),
                 "recorded distance 3014.6 m lies outside the adjudicated_same_campus band"),
                ("results", located(3010.0, 2995.0, "beyond_3000m"), "lies outside the beyond_3000m band"),
                ("results", lambda r: r["comparison"][inside - 1].update(location_distance_m=4.0),
                 f"position {inside}: recorded distance 4.0 m lies outside the inside band"),
            ]
        )
        for metres, rule, adjudicated in (
            (995.0, "within_1000m", False),
            (2985.0, "adjudicated_same_campus", True),
            (3010.0, "beyond_3000m", False),
        ):
            self.refresh(results=located(metres, metres, rule, adjudicated))
            with self.subTest(rule=rule):
                self.assertEqual(self.gate()["sample_outcomes"][position - 1]["location_rule"], rule)

    def test_adjudication_needs_an_adjudicator_a_date_and_a_reason(self) -> None:
        self.outcomes = {4: ("uc", "near"), 5: ("uc", "far"), 6: ("uc", "band_same")}
        adjudication = {
            "adjudicated_by": ADJUDICATOR, "adjudicated_at": "2026-10-10", "reason": "Claimed.",
        }

        def adjudicate(**changes):
            return lambda r: r["comparison"][5]["adjudication"].update(changes)

        self.rejected(
            [
                ("results", lambda r: r["comparison"][3].update(
                    location_rule="adjudicated_same_campus", adjudication=dict(adjudication)),
                 "position 4: adjudication is accepted only in the 1,000-3,000 m band"),
                ("results", lambda r: r["comparison"][4].update(
                    location_rule="adjudicated_same_campus", adjudication=dict(adjudication), agreement=True),
                 "position 5: adjudication is accepted only in the 1,000-3,000 m band"),
                ("results", lambda r: r["comparison"][3].update(adjudication=dict(adjudication)),
                 "position 4: only an adjudicated rule has an adjudication"),
                ("results", lambda r: r["comparison"][5].update(adjudication=None),
                 "position 6: 1,000-3,000 m needs a written adjudication"),
                ("results", lambda r: r["comparison"][5].update(location_rule="within_1000m", adjudication=None),
                 "position 6: 1,000-3,000 m needs a written adjudication"),
                ("results", adjudicate(reason="  "), "position 6 adjudication reason must be nonempty text"),
                ("results", adjudicate(adjudicated_by="session-06"),
                 "position 6: the adjudicator must not be a reviewer session"),
                ("results", adjudicate(adjudicated_by=" "), "position 6 adjudicator must be nonempty text"),
                ("results", adjudicate(adjudicated_at="2026-10-09"),
                 "position 6: adjudication must follow every counted review and precede the recording"),
                ("results", adjudicate(adjudicated_at="2026-10-11"),
                 "adjudication must follow every counted review"),
                ("results", adjudicate(adjudicated_at="10 October"), "adjudication date must be YYYY-MM-DD"),
                ("results", adjudicate(note="extra"), "position 6 adjudication keys differ"),
            ]
        )
        self.outcomes = {6: ("uc", "band_different")}
        self.refresh()
        gate = self.gate()
        self.assertEqual((gate["agreements"], gate["disagreement_positions"]), (19, [6]))
        self.assertEqual(
            gate["sample_outcomes"][5]["adjudication"],
            {
                "adjudicated_at": "2026-10-10",
                "adjudicated_by": ADJUDICATOR,
                "reason": "Synthetic adjudication: the reviewer point is a different campus.",
            },
        )

    def test_totals_must_match_the_recomputation(self) -> None:
        self.rejected(
            [
                ("results", lambda r: r["totals"].update(agreements=19), "totals differ"),
                ("results", lambda r: r["totals"].update(gate_passed=False), "totals differ"),
                ("results", lambda r: r["totals"].update(sample_size=21), "totals differ"),
                ("results", lambda r: r["totals"].update(agreements=20.0), "totals differ"),
            ]
        )
        self.outcomes = {5: ("unknown", "inside"), 6: ("not", "inside")}
        self.refresh(results=lambda r: r["totals"].update(gate_passed=True))
        self.assert_rejected("totals differ")

    def test_blind_review_is_rejected_on_v1_and_v2_contracts(self) -> None:
        def as_v1(contract: dict) -> None:
            contract["schema_version"] = draft.SCHEMA_VERSION
            del contract["baseline_corrections"]

        def as_v2(contract: dict) -> None:
            contract["schema_version"] = draft.SCHEMA_VERSION_V2

        def plain(change):
            def mutate(contract: dict) -> None:
                change(contract)
                del contract["blind_review"]

            return mutate

        self.rejected(
            [
                ("contract", as_v1, "batch contract keys differ"),
                ("contract", as_v2, "batch contract keys differ"),
                ("contract", lambda c: c.pop("blind_review"), "batch contract keys differ"),
                ("contract", lambda c: c.update(baseline_corrections={}),
                 "v3 baseline corrections must be a list"),
            ]
        )
        self.refresh(contract=plain(as_v1))
        self.assertIsNone(self.validate().blind_review)
        self.assertIsNone(self.validate(replace(self.pins, blind_review_sha256="")).blind_review)
        self.assert_rejected(
            "a blind review pin requires a v3 contract",
            replace(self.pins, blind_review_sha256="0" * 64),
        )
        self.refresh(contract=plain(as_v2))
        self.assert_rejected(
            "a blind review pin requires a v3 contract",
            replace(self.pins, blind_review_sha256="0" * 64),
        )
        self.assert_rejected("at least one baseline correction")

    def test_review_dates_structure_and_blindness_fail_closed(self) -> None:
        self.rejected(
            [
                ("results", lambda r: r["reviews"][0].update(reviewed_at="2026-10-08"),
                 "dated outside pre-registration..recording"),
                ("results", lambda r: r.update(recorded_at="2026-10-11"),
                 "recorded after pre-registration and by the contract review date"),
                ("results", lambda r: r["reviews"][0]["construction_evidence"][0].update(
                    observation_date="2026-10-11"),
                 "observation follows its review"),
                ("results", lambda r: r["reviews"][0]["blindness_attestation"].update(
                    atlas_materials_accessed=True),
                 "position 1: a counted session must not have accessed Atlas materials"),
                ("results", lambda r: r["reviews"][0].update(reviewer_note="extra"),
                 "blind review keys differ"),
                ("results", lambda r: r["comparison"][0].update(reviewer_note="extra"),
                 "blind review comparison keys differ"),
                ("results", lambda r: r.update(disclosures=[]), "disclosures must be a list"),
                ("results", lambda r: r.update(schema_version="other"), "results schema differs"),
                ("results", lambda r: r["reviews"][0].update(counted="yes"),
                 "counted must be true or false"),
                ("results", lambda r: r["reviews"][0]["successor_check"].update(status=["listed"]),
                 "invalid blind review at position 1 successor status"),
            ]
        )

    # Geodesy -----------------------------------------------------------------

    def test_geodesic_distances_match_published_references(self) -> None:
        # Vincenty (1975): Flinders Peak to Buninyong is 54,972.271 m.
        flinders = [144 + 25 / 60 + 29.52440 / 3600, -(37 + 57 / 60 + 3.72030 / 3600)]
        buninyong = [143 + 55 / 60 + 35.38390 / 3600, -(37 + 39 / 60 + 10.15610 / 3600)]
        compared = draft.blind_review_location_comparison(
            buninyong, {"type": "Point", "coordinates": flinders}
        )
        self.assertAlmostEqual(compared["distance_m"], 54972.271, delta=0.001)
        self.assertEqual(compared["band"], "beyond_3000m")
        # One degree of longitude on the equator is a * pi / 180.
        self.assertAlmostEqual(
            draft._wgs84_distance_m([0, 0], [1, 0]), 6378137 * math.pi / 180, delta=1e-6
        )
        # The WGS84 quarter meridian is 10,001,965.729 m.
        self.assertAlmostEqual(draft._wgs84_distance_m([0, 0], [0, 90]), 10001965.729, delta=0.001)
        # A nearly antipodal pair stays far beyond every threshold.
        self.assertGreater(draft._wgs84_distance_m([0, 0], [179.9, 0.1]), 19_000_000)
        self.assertEqual(draft._wgs84_distance_m([32.6, 0.35], [32.6, 0.35]), 0.0)

    def test_location_bands_polygons_holes_and_thresholds(self) -> None:
        exterior = [[10, 0], [10.01, 0], [10.01, 0.01], [10, 0.01], [10, 0]]
        hole = [[10.004, 0.004], [10.006, 0.004], [10.006, 0.006], [10.004, 0.006], [10.004, 0.004]]
        square = {"type": "Polygon", "coordinates": [exterior, hole]}

        def compare(point, geometry=square):
            return draft.blind_review_location_comparison(point, geometry)

        self.assertEqual(compare([10.002, 0.002]), {"distance_m": 0.0, "band": "inside"})
        self.assertEqual(compare([10.01, 0.005])["band"], "inside")  # boundary inclusive
        self.assertEqual(compare([10.004, 0.005])["band"], "inside")  # hole boundary
        in_hole = compare([10.005, 0.005])
        self.assertEqual(in_hole["band"], "within_1000m")
        self.assertAlmostEqual(
            in_hole["distance_m"], draft._wgs84_distance_m([10.005, 0.005], [10.005, 0.006]), delta=1e-6
        )
        north = compare([10.005, 0.03])
        self.assertEqual(north["band"], "adjudication_band")
        self.assertAlmostEqual(
            north["distance_m"], draft._wgs84_distance_m([10.005, 0.03], [10.005, 0.01]), delta=1e-6
        )
        multi = {
            "type": "MultiPolygon",
            "coordinates": [[exterior], [[[11, 0], [11.01, 0], [11.01, 0.01], [11, 0.01], [11, 0]]]],
        }
        near_second = compare([11.005, 0.015], multi)
        self.assertEqual(near_second["band"], "within_1000m")
        self.assertAlmostEqual(
            near_second["distance_m"], draft._wgs84_distance_m([11.005, 0.015], [11.005, 0.01]), delta=1e-6
        )
        self.assertEqual(compare([32.6, 0.35], {"type": "Point", "coordinates": [32.6, 0.35]})["band"], "inside")
        self.assertEqual(draft._location_band(False, 1000.0), "within_1000m")
        self.assertEqual(draft._location_band(False, 1000.0001), "adjudication_band")
        self.assertEqual(draft._location_band(False, 3000.0), "adjudication_band")
        self.assertEqual(draft._location_band(False, 3000.0001), "beyond_3000m")
        for bad in ([200, 0], [0, 91], [float("nan"), 0], "10,0"):
            with self.subTest(point=bad), self.assertRaises(draft.DraftValidationError):
                compare(bad)
        # Dense sampling of every edge of an irregular polygon agrees with the search.
        irregular = {
            "type": "Polygon",
            "coordinates": [[[24.68, 60.23], [24.70, 60.231], [24.695, 60.245], [24.684, 60.24], [24.68, 60.23]]],
        }
        ring = irregular["coordinates"][0]
        for point in ([24.71, 60.25], [24.66, 60.236], [24.69, 60.22]):
            brute = min(
                draft._wgs84_distance_m(
                    point, [a[0] + step / 500 * (b[0] - a[0]), a[1] + step / 500 * (b[1] - a[1])]
                )
                for a, b in zip(ring, ring[1:])
                for step in range(501)
            )
            found = compare(point, irregular)["distance_m"]
            with self.subTest(point=point):
                self.assertLessEqual(found, brute + 1e-9)
                self.assertGreater(found, brute - 0.01)

    def test_v3_correction_may_inherit_through_a_v3_draft(self) -> None:
        baseline = self.root / draft.BASELINE_RELATIVE_DIR
        release = "verified_construction_core/2026-08-20-v0.18-draft-synthetic-v3-inherited"
        directory = self.root / release
        directory.mkdir()
        files = {}
        for name in ("projects.csv", "sites.csv", "evidence.csv", "sites.geojson"):
            data = (baseline / name).read_bytes()
            (directory / name).write_bytes(data)
            files[name] = {"bytes": len(data), "sha256": sha256(data)}
        manifest = draft.core._json_bytes(
            {
                "format": draft.DRAFT_MANIFEST_FORMAT_V3,
                "release_status": "draft",
                "base_preview_manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
                "base_preview_path": draft.BASELINE_RELATIVE_DIR,
                "files": files,
            }
        )
        (directory / "manifest.json").write_bytes(manifest)
        frozen = {
            key: {
                "file_line_number": 2,
                "raw_line_sha256": sha256((baseline / f"{table_name}.csv").read_bytes().split(b"\n")[1]),
            }
            for key, table_name, _ in draft.FROZEN_ROW_TABLES
        }
        feature = json.loads((baseline / "sites.geojson").read_bytes())["features"][0]
        frozen["sites_geojson"] = {
            "feature_index": 0, "feature_canonical_sha256": draft.canonical_sha256(feature),
        }
        spec = {
            "release_path": release,
            "manifest_sha256": sha256(manifest),
            "rows_byte_identical_to_v017": True,
        }
        with self.assertRaisesRegex(draft.DraftValidationError, "not a v0.18 draft"):
            draft._inherited_unchanged_through(spec, self.root, frozen)
        lines = draft._inherited_unchanged_through(
            spec, self.root, frozen, draft.INHERITED_THROUGH_FORMATS_V3
        )
        self.assertEqual(len(lines["projects"]), 103)


class RealPreregistrationTests(unittest.TestCase):
    def test_real_preregistration_recomputes_its_published_sample(self) -> None:
        raw = (ROOT / REAL_PREREGISTRATION).read_bytes()
        document = json.loads(raw)
        checked = draft.validate_blind_review_preregistration(
            {"path": REAL_PREREGISTRATION, "bytes": len(raw), "sha256": sha256(raw)}, root=ROOT
        )
        population = document["population"]
        self.assertEqual(population["release_path"], thirty_sixth.DRAFT_RELATIVE_PATH)
        release = ROOT / thirty_sixth.DRAFT_RELATIVE_PATH
        self.assertEqual(sha256((release / "manifest.json").read_bytes()), population["manifest_sha256"])
        projects, sites = release_rows(release)
        keys = sorted(projects)
        self.assertEqual(len(keys), 203)
        self.assertEqual(population["eligible_project_count"], 203)
        self.assertEqual(checked["keys"], keys)
        self.assertEqual(draft.canonical_sha256(keys), population["eligible_project_keys_sha256"])
        # Recompute the seed and the ranking independently of the builder.
        material = document["sampling"]["seed_material"]
        self.assertEqual(
            material,
            "datacenter-atlas-blind-review-v1|"
            f"{population['eligible_project_keys_sha256']}|{population['published_in_commit']}",
        )
        seed = sha256(material.encode())
        self.assertEqual(seed, document["sampling"]["seed_sha256"])
        ranked = sorted((sha256(f"{seed}|{key}".encode()), key) for key in keys)[:20]
        self.assertEqual(
            [(entry["rank_sha256"], entry["project_stable_key"]) for entry in document["sample"]],
            ranked,
        )
        self.assertEqual([entry["position"] for entry in document["sample"]], list(range(1, 21)))
        self.assertEqual(checked["sample"], {index: key for index, (_, key) in enumerate(ranked, 1)})
        self.assertEqual(checked["seed_sha256"], seed)
        for entry in document["sample"]:
            project = projects[entry["project_stable_key"]]
            self.assertEqual(
                entry["blind_inputs"],
                {
                    "project_name": project["name"],
                    "campus_name": sites[project["physical_site_stable_key"]]["name"],
                    "country": project["country"],
                },
            )
        # The builder registers exactly this pre-registration for this population.
        self.assertEqual(
            dict(draft.BLIND_REVIEW_PREREGISTRATIONS[population["manifest_sha256"]]),
            {"path": REAL_PREREGISTRATION, "bytes": len(raw), "sha256": sha256(raw)},
        )
        # The committed thirty-sixth gate names exactly this eligible population,
        # so a v3 checkpoint of these 203 projects would evaluate the gate.
        report = json.loads((release / "selection-report.json").read_text())
        gate = report["final_release_gates"]["blind_review"]
        self.assertEqual(gate["eligible_project_stable_keys"], keys)
        self.assertEqual(gate["eligible_project_keys_sha256"], population["eligible_project_keys_sha256"])
        self.assertEqual((gate["sample_size"], gate["agreements"], gate["passed"]), (0, 0, False))
        self.assertEqual(population["population_scope"], gate["population_scope"])


def repository_paths(value) -> set[str]:
    """Every repository path string inside a JSON value."""
    if isinstance(value, dict):
        return set().union(*(repository_paths(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(repository_paths(item) for item in value))
    if isinstance(value, str) and value.split("/", 1)[0] in {
        "sources", "definitions", "verified_construction_core",
    }:
        return {value}
    return set()


class ThirtySixthAsV3Tests(unittest.TestCase):
    """The first real v3 path: the thirty-sixth contract, with its CGK baseline
    correction, pinning the published pre-registration and a SYNTHETIC results
    record whose reviewer points are the sampled sites' own display anchors."""

    CONTRACT = "definitions/synthetic-v3-thirty-sixth-batch.json"
    RESULTS = "sources/synthetic-v3-thirty-sixth-blind-review-results.json"

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name) / "root"
        contract = json.loads((ROOT / thirty_sixth.CONTRACT_RELATIVE_PATH).read_bytes())
        # Copy only what the contract and its correction records name.
        named = {
            REAL_PREREGISTRATION, draft.BASELINE_RELATIVE_DIR, thirty_sixth.DRAFT_RELATIVE_PATH,
            *repository_paths(contract),
        }
        paths = {spec["source_id"]: spec["path"] for spec in contract["sources"]}
        for correction in contract["baseline_corrections"]:
            document = json.loads((ROOT / paths[correction["geometry"]["source_id"]]).read_bytes())
            named |= repository_paths(document)
        for name in sorted(named):
            source, target = ROOT / name, root / name
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        cls.root = root
        cls.template = contract
        cls.preregistration_raw = (root / REAL_PREREGISTRATION).read_bytes()

    def write(self, disagree=()) -> draft.ReviewPins:
        preregistration = json.loads(self.preregistration_raw)
        projects, sites = release_rows(self.root / preregistration["population"]["release_path"])
        reviews, comparison = [], []
        for entry in preregistration["sample"]:
            position, key = entry["position"], entry["project_stable_key"]
            site = sites[projects[key]["physical_site_stable_key"]]
            point = [float(site["longitude"]), float(site["latitude"])]
            compared = draft.blind_review_location_comparison(point, json.loads(site["geometry_json"]))
            self.assertIn(compared["band"], {"inside", "within_1000m"})
            agrees = position not in disagree
            reviews.append(
                {
                    "position": position,
                    "project_stable_key": key,
                    "reviewer_session_id": f"synthetic-session-{position:02d}",
                    "session_sequence": position,
                    "session_status": "completed",
                    "reviewed_at": "2026-10-10",
                    "counted": True,
                    "construction_determination": "under_construction_in_window"
                    if agrees
                    else "unable_to_verify",
                    "construction_evidence": [
                        {
                            "source_url": "https://example.test/synthetic-evidence",
                            "observation_date": "2026-07-01",
                            "literal_pointer": "Synthetic fixture; no real observation.",
                            "capture_sha256": sha256(b"synthetic"),
                        }
                    ]
                    if agrees
                    else [],
                    "successor_check": {
                        "status": "none_found_on_or_before_cutoff" if agrees else "not_checked",
                        "notes": "Synthetic fixture.",
                    },
                    "location": {
                        "status": "located", "longitude": point[0], "latitude": point[1],
                        "method": "Synthetic fixture: the sampled site's own display anchor.",
                        "source_url": "https://example.test/synthetic-location",
                    },
                    "identity_notes": "Synthetic fixture.",
                    "blindness_attestation": {
                        "atlas_materials_accessed": False, "statement": "Synthetic fixture.",
                    },
                }
            )
            comparison.append(
                {
                    "position": position,
                    "project_stable_key": key,
                    "construction_agrees": agrees,
                    "location_distance_m": round(compared["distance_m"], 1),
                    "location_rule": compared["band"],
                    "adjudication": None,
                    "agreement": agrees,
                }
            )
        agreements = 20 - len(disagree)
        record = {
            "schema_version": draft.BLIND_REVIEW_RESULTS_SCHEMA,
            "recorded_at": "2026-10-10",
            "preregistration": {"path": REAL_PREREGISTRATION, "sha256": sha256(self.preregistration_raw)},
            "population": preregistration["population"],
            "reviews": reviews,
            "comparison": comparison,
            "totals": {"sample_size": 20, "agreements": agreements, "gate_passed": agreements >= 19},
            "disclosures": ["SYNTHETIC unit-test record: no blind review was performed."],
        }
        results_raw = draft.core._json_bytes(record)
        (self.root / self.RESULTS).write_bytes(results_raw)
        contract = deepcopy(self.template)
        contract.update(
            schema_version=draft.SCHEMA_VERSION_V3,
            batch_id="synthetic-v3-thirty-sixth",
            geometry_identity_reviewed_at="2026-10-10",
            blind_review={
                "preregistration": {
                    "path": REAL_PREREGISTRATION,
                    "bytes": len(self.preregistration_raw),
                    "sha256": sha256(self.preregistration_raw),
                },
                "results": {"path": self.RESULTS, "bytes": len(results_raw), "sha256": sha256(results_raw)},
            },
        )
        raw = draft.core._json_bytes(contract)
        (self.root / self.CONTRACT).write_bytes(raw)
        return replace(
            thirty_sixth.REVIEW_PINS,
            contract_sha256=sha256(raw),
            blind_review_sha256=draft.canonical_sha256(contract["blind_review"]),
        )

    def test_thirty_sixth_with_its_cgk_correction_rebuilds_as_a_v3_checkpoint(self) -> None:
        pins = self.write()
        output = Path(self.directory.name) / "v3-thirty-sixth"
        manifest = draft.build_draft(self.root / self.CONTRACT, pins, output, root=self.root)
        self.assertEqual(
            manifest, draft.validate_draft(output, self.root / self.CONTRACT, pins, root=self.root)
        )
        committed = ROOT / thirty_sixth.DRAFT_RELATIVE_PATH
        self.assertEqual(manifest["format"], draft.DRAFT_MANIFEST_FORMAT_V3)
        self.assertEqual(manifest["counts"], json.loads((committed / "manifest.json").read_bytes())["counts"])
        for name in ("projects.csv", "sites.csv", "evidence.csv", "sites.geojson", "ATTRIBUTION.txt"):
            with self.subTest(name=name):
                self.assertEqual((output / name).read_bytes(), (committed / name).read_bytes())
        report = json.loads((output / "selection-report.json").read_text())
        reference = json.loads((committed / "selection-report.json").read_text())
        self.assertEqual(report["format"], "datacenter-atlas-v018-draft-selection-v3")
        self.assertEqual(
            [item["correction_id"] for item in report["baseline_corrections"]],
            ["cgk-host-estate-locator-rescope-v1"],
        )
        self.assertEqual(report["baseline_corrections"], reference["baseline_corrections"])
        self.assertEqual(report["locator_exceptions"], reference["locator_exceptions"])
        gate = report["final_release_gates"]["blind_review"]
        self.assertTrue(gate["population_matches"])
        self.assertIsNone(gate["population_mismatch"])
        self.assertEqual((gate["sample_size"], gate["agreements"], gate["passed"]), (20, 20, True))
        self.assertEqual(gate["eligible_project_count"], 203)
        self.assertEqual(gate["eligible_project_stable_keys"], reference["final_release_gates"]["blind_review"]["eligible_project_stable_keys"])
        self.assertEqual(gate["preregistration"]["sha256"], sha256(self.preregistration_raw))
        for name, other in report["final_release_gates"].items():
            if name != "blind_review":
                self.assertEqual(other, reference["final_release_gates"][name])
        for disagree, expected in (((7,), (19, True)), ((7, 12), (18, False))):
            pins = self.write(disagree)
            files, _ = draft._payloads(draft.validate_batch(self.root / self.CONTRACT, pins, root=self.root))
            gate = json.loads(files["selection-report.json"])["final_release_gates"]["blind_review"]
            with self.subTest(disagree=disagree):
                self.assertEqual((gate["agreements"], gate["passed"]), expected)
                self.assertEqual(gate["disagreement_positions"], list(disagree))


if __name__ == "__main__":
    unittest.main()
