"""Schema-v3 baseline withdrawals over the committed thirty-sixth checkpoint.

The fixture rebuilds the committed thirty-sixth contract, with its CGK baseline
correction, as a v3 checkpoint in a temporary root. It pins the published
pre-registration and a SYNTHETIC results record whose reviewer points are the
sampled sites' own display anchors, and adds pinned baseline withdrawals whose
records and review basis are generated here from the frozen v0.17 rows and the
committed curated v0.17 inputs. No real review or withdrawal decision is claimed;
only tracked inputs are read from the repository.
"""

from __future__ import annotations

from copy import deepcopy
import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_sixth_reviewed as thirty_sixth
from datacenter_atlas import verified_construction_core_v018 as draft


ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION = (
    "definitions/verified-construction-core-v0.18-blind-review-preregistration-v1.json"
)
RESULTS = "sources/synthetic-withdrawal-blind-review-results.json"
BASIS = "sources/synthetic-withdrawal-review-basis.json"
CONTRACT = "definitions/synthetic-v3-withdrawal-batch.json"
THIRTY_FIFTH = "verified_construction_core/2026-08-20-v0.18-draft-thirty-fifth-reviewed"
THIRTY_SIXTH = thirty_sixth.DRAFT_RELATIVE_PATH
SBOG = "curated:scala-zona-franca-bogota-campus:sbogzb01"
SBOG_SITE = "curated:scala-zona-franca-bogota-campus"
WALQA = "curated:aws-walqa-huesca-data-center:current-build"
HEBRON = "curated:microsoft-hebron-oh-datacenter:initial-site-preparation"
STT_PROJECT = "curated:stt-jakarta-data-centre-campus:stt-jakarta-3"
STT_SITE = "curated:stt-jakarta-data-centre-campus"
CGK = "curated:digital-edge-cgk-campus-bekasi:cgk1"
RDH2 = "curated:telecom-egypt-rdh2-smart-village-campus:regional-data-hub-2"
CGK_RECORD = "sources/verified-construction-core-v0.18-cgk-host-estate-locator-correction-v1.json"
# The frozen v0.17 curated input binding each fixture's withdrawn observation:
# (path, lifecycle index, evidence index). Other projects reuse SBOGZB01's.
OBSERVATIONS = {
    SBOG: ("sources/curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json", 0, 0),
    WALQA: ("sources/curated-official-2026-07-19-aws-walqa-spain.json", 0, 0),
    CGK: ("sources/curated-official-2026-07-20-digital-edge-cgk1-bekasi.json", 0, 0),
}
SBOG_EVIDENCE = ["1fc139c6-ea1d-5f7c-ac84-745cf2602806", "4723a143-571a-5f76-97c2-12aea18b3a8b"]
# The frozen v0.17 status rows of three other Scala projects come from the same
# 2026-07-21 portfolio capture (URL and content hash) as SBOGZB01's status row.
SCALA_SHARED = [
    ("62b2a499-44a6-59c1-b956-78abbbc1b8d5", "curated:scala-praia-do-futuro-campus:sforpf01"),
    ("97007edb-ddfc-5984-884a-8222ded41e29", "curated:scala-lampa-campus:sscllp01"),
    ("d4f91e87-3ea2-5833-b19d-fd5a3ca7b591", "curated:scala-huechuraba-campus:ssclhb01"),
]
SBOG_SHARED_ROWS = [
    {"evidence_id": evidence_id, "project_stable_keys": [key], "withdrawn_evidence_id": SBOG_EVIDENCE[1]}
    for evidence_id, key in SCALA_SHARED
]
SHARED_GATE = "withdrawal_shared_capture_review"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def table(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))


def dumps(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def slug(project_key: str) -> str:
    return project_key.split(":")[1]


class FrozenRows:
    """The frozen v0.17 rows a withdrawal names, computed independently of the builder."""

    def __init__(self, root: Path) -> None:
        base = root / draft.BASELINE_RELATIVE_DIR
        self.raw = {name: (base / f"{name}.csv").read_bytes() for name in ("projects", "sites", "evidence")}
        self.rows = {name: table(raw) for name, raw in self.raw.items()}
        self.lines = {name: raw.split(b"\n") for name, raw in self.raw.items()}
        self.features = json.loads((base / "sites.geojson").read_bytes())["features"]

    def project(self, key: str) -> dict:
        return next(row for row in self.rows["projects"] if row["project_stable_key"] == key)

    def spec(self, name: str, field: str, identifier: str) -> dict:
        (index,) = [i for i, row in enumerate(self.rows[name]) if row[field] == identifier]
        return {
            "file_line_number": index + 2,
            field: identifier,
            "row_canonical_sha256": draft.canonical_sha256(self.rows[name][index]),
            "raw_line_sha256": sha256(self.lines[name][index + 1]),
        }

    def evidence_ids(self, key: str) -> list[str]:
        project_id = self.project(key)["project_id"]
        return [
            row["evidence_id"]
            for row in self.rows["evidence"]
            if project_id in json.loads(row["project_ids_json"])
        ]

    def frozen_rows(self, key: str) -> dict:
        site_key = self.project(key)["physical_site_stable_key"]
        (index,) = [
            i for i, feature in enumerate(self.features)
            if feature["properties"]["physical_site_stable_key"] == site_key
        ]
        return {
            "release_path": draft.BASELINE_RELATIVE_DIR,
            "manifest_sha256": draft.BASELINE_MANIFEST_SHA256,
            "projects_csv": self.spec("projects", "project_stable_key", key),
            "sites_csv": self.spec("sites", "physical_site_stable_key", site_key),
            "evidence_csv": [
                self.spec("evidence", "evidence_id", identifier)
                for identifier in self.evidence_ids(key)
            ],
            "sites_geojson": {
                "feature_index": index,
                "feature_canonical_sha256": draft.canonical_sha256(self.features[index]),
            },
        }

    def shared_capture_rows(self, key: str) -> list[dict]:
        """Other frozen evidence rows with a withdrawn row's source URL and content hash."""
        withdrawn = self.evidence_ids(key)
        captures: dict[tuple[str, str], str] = {}
        for row in self.rows["evidence"]:
            if row["evidence_id"] in withdrawn:
                captures.setdefault((row["source_url"], row["content_hash"]), row["evidence_id"])
        keys = {row["project_id"]: row["project_stable_key"] for row in self.rows["projects"]}
        return [
            {
                "evidence_id": row["evidence_id"],
                "project_stable_keys": sorted(keys[p] for p in json.loads(row["project_ids_json"])),
                "withdrawn_evidence_id": captures[(row["source_url"], row["content_hash"])],
            }
            for row in self.rows["evidence"]
            if row["evidence_id"] not in withdrawn
            and (row["source_url"], row["content_hash"]) in captures
        ]

    def raw_lines(self, key: str) -> set[bytes]:
        frozen = self.frozen_rows(key)
        specs = [("projects", frozen["projects_csv"]), ("sites", frozen["sites_csv"])] + [
            ("evidence", spec) for spec in frozen["evidence_csv"]
        ]
        return {self.lines[name][spec["file_line_number"] - 1] for name, spec in specs}


def synthetic_results(root: Path, disagree: tuple[int, ...] = ()) -> bytes:
    """A SYNTHETIC record: each reviewer point is the sampled site's display anchor."""
    raw = (root / PREREGISTRATION).read_bytes()
    preregistration = json.loads(raw)
    release = root / preregistration["population"]["release_path"]
    projects = {row["project_stable_key"]: row for row in table((release / "projects.csv").read_bytes())}
    sites = {row["physical_site_stable_key"]: row for row in table((release / "sites.csv").read_bytes())}
    reviews, comparison = [], []
    for entry in preregistration["sample"]:
        position, key = entry["position"], entry["project_stable_key"]
        site = sites[projects[key]["physical_site_stable_key"]]
        point = [float(site["longitude"]), float(site["latitude"])]
        compared = draft.blind_review_location_comparison(point, json.loads(site["geometry_json"]))
        agrees = position not in disagree
        reviews.append(
            {
                "position": position,
                "project_stable_key": key,
                "reviewer_session_id": f"synthetic-withdrawal-session-{position:02d}",
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
                    "status": "located",
                    "longitude": point[0],
                    "latitude": point[1],
                    "method": "Synthetic fixture: the sampled site's own display anchor.",
                    "source_url": "https://example.test/synthetic-location",
                },
                "identity_notes": "Synthetic fixture.",
                "blindness_attestation": {
                    "atlas_materials_accessed": False,
                    "statement": "Synthetic fixture.",
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
    return draft.core._json_bytes(
        {
            "schema_version": draft.BLIND_REVIEW_RESULTS_SCHEMA,
            "recorded_at": "2026-10-10",
            "preregistration": {"path": PREREGISTRATION, "sha256": sha256(raw)},
            "population": preregistration["population"],
            "reviews": reviews,
            "comparison": comparison,
            "totals": {"sample_size": 20, "agreements": agreements, "gate_passed": agreements >= 19},
            "disclosures": ["SYNTHETIC unit-test record: no blind review was performed."],
        }
    )


class BaselineWithdrawalV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory(prefix="atlas-withdrawal-")
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name) / "root"
        for name in ("sources", "definitions"):
            shutil.copytree(ROOT / name, root / name)
        for release in (draft.BASELINE_RELATIVE_DIR, THIRTY_FIFTH, THIRTY_SIXTH):
            shutil.copytree(ROOT / release, root / release)
        (root / BASIS).write_bytes(dumps({"synthetic": "review basis fixture; no real review"}))
        cls.root = root
        cls.template = json.loads((ROOT / thirty_sixth.CONTRACT_RELATIVE_PATH).read_bytes())
        cls.frozen = FrozenRows(root)
        cls.results_raw = synthetic_results(root)
        cls.counter = 0

    # Fixture construction -------------------------------------------------

    def record_for(self, key: str, *, through: str = THIRTY_SIXTH) -> dict:
        project = self.frozen.project(key)
        curated, lifecycle, evidence = OBSERVATIONS.get(key, OBSERVATIONS[SBOG])
        raw = (self.root / curated).read_bytes()
        document = json.loads(raw)
        basis = (self.root / BASIS).read_bytes()
        frozen = self.frozen.frozen_rows(key)
        site = next(
            row for row in self.frozen.rows["sites"]
            if row["physical_site_stable_key"] == project["physical_site_stable_key"]
        )
        return {
            "schema_version": draft.BASELINE_WITHDRAWAL_RECORD_SCHEMA,
            "withdrawal_id": f"synthetic-{slug(key)}-withdrawal",
            "reviewed_at": "2026-10-10",
            "lifecycle_reference_date": "2026-08-20",
            "accepted_additional_sites": 0,
            "project_stable_key": key,
            "physical_site_stable_key": project["physical_site_stable_key"],
            "decision": "withdraw_from_selection",
            "withdrawal_basis": "status_evidence_does_not_meet_contract",
            "claim_boundary": {
                "asserted_physical_status": None,
                "physical_status_on_lifecycle_reference_date": "unknown",
                "asserts_not_under_construction": False,
                "asserts_paused": False,
                "asserts_cancelled": False,
                "asserts_completed": False,
                "statement": "Synthetic fixture: no physical status is asserted.",
            },
            "frozen_baseline_rows": frozen,
            "inherited_unchanged_through": {
                "release_path": through,
                "manifest_sha256": sha256((self.root / through / "manifest.json").read_bytes()),
                "rows_byte_identical_to_v017": True,
            },
            "withdrawn_observation_binding": {
                "source_id": f"synthetic-{slug(key)}-observation",
                "source_path": curated,
                "source_file_sha256": sha256(raw),
                "source_file_bytes": len(raw),
                "evidence_pointer": f"/evidence/{evidence}",
                "evidence_record_sha256": draft.canonical_sha256(document["evidence"][evidence]),
                "project_pointer": "/project",
                "project_sha256": draft.canonical_sha256(document["project"]),
                "campus_pointer": "/campus",
                "campus_sha256": draft.canonical_sha256(document["campus"]),
                "lifecycle_pointer": f"/lifecycle/{lifecycle}",
                "lifecycle_sha256": draft.canonical_sha256(document["lifecycle"][lifecycle]),
            },
            "review_basis": [{"path": BASIS, "bytes": len(basis), "sha256": sha256(basis)}],
            "count_effect": {
                "physical_sites": -1,
                "projects": -1,
                "evidence": -len(frozen["evidence_csv"]),
                "non_us_sites": -int(site["country_iso_a2"] != "US"),
                "reviewed_site_locator_projects": -int(draft._is_reviewed_locator(project)),
                "host_estate_context_projects": 0,
                "official_boundary_projects": -int(draft.core._is_official_boundary(project)),
            },
            "shared_capture_rows": {
                "rows": self.frozen.shared_capture_rows(key),
                "statement": "Synthetic fixture: these rows were not reviewed.",
            },
            "withdrawal_reason": "Synthetic fixture: no real withdrawal decision.",
        }

    def write(
        self,
        withdrawals: tuple[str, ...] = (SBOG,),
        *,
        record=None,
        entry=None,
        contract=None,
        pins=None,
        results: bytes | None = None,
        through: str = THIRTY_SIXTH,
    ) -> draft.ReviewPins:
        """Write the records and a v3 contract with correct pins, then apply each tamper."""
        type(self).counter += 1
        number = self.counter
        entries, withdrawal_pins = [], {}
        for key in withdrawals:
            document = self.record_for(key, through=through)
            if record is not None:
                record(key, document)
            raw = dumps(document)
            path = f"sources/synthetic-withdrawal-{number}-{slug(key)}.json"
            (self.root / path).write_bytes(raw)
            value = {
                "withdrawal_id": f"synthetic-{slug(key)}-withdrawal",
                "physical_site_stable_key": self.frozen.project(key)["physical_site_stable_key"],
                "project_stable_key": key,
                "frozen_rows": self.frozen.frozen_rows(key),
                "record": {"path": path, "bytes": len(raw), "sha256": sha256(raw)},
                "reason": "Synthetic fixture withdrawal; no real decision is claimed.",
            }
            if entry is not None:
                entry(key, value)
            entries.append(value)
            withdrawal_pins[value["withdrawal_id"]] = draft.canonical_sha256(value)
        results_raw = self.results_raw if results is None else results
        (self.root / RESULTS).write_bytes(results_raw)
        prereg = (self.root / PREREGISTRATION).read_bytes()
        value = deepcopy(self.template)
        value.update(
            schema_version=draft.SCHEMA_VERSION_V3,
            batch_id=f"synthetic-withdrawal-{number}",
            geometry_identity_reviewed_at="2026-10-10",
            blind_review={
                "preregistration": {"path": PREREGISTRATION, "bytes": len(prereg), "sha256": sha256(prereg)},
                "results": {"path": RESULTS, "bytes": len(results_raw), "sha256": sha256(results_raw)},
            },
        )
        if entries:
            value["baseline_withdrawals"] = entries
        if contract is not None:
            contract(value)
        raw = (json.dumps(value, indent=2) + "\n").encode()
        (self.root / CONTRACT).write_bytes(raw)
        self.contract = value
        review_pins = replace(
            thirty_sixth.REVIEW_PINS,
            contract_sha256=sha256(raw),
            blind_review_sha256=draft.canonical_sha256(value["blind_review"])
            if "blind_review" in value
            else None,
            baseline_withdrawal_sha256=withdrawal_pins,
        )
        if pins is not None:
            review_pins = pins(review_pins)
        self.pins = review_pins
        return review_pins

    def validate(self) -> draft.ValidatedBatch:
        return draft.validate_batch(self.root / CONTRACT, self.pins, root=self.root)

    def payloads(self, **fixture) -> dict[str, bytes]:
        self.write(**fixture)
        files, _ = draft._payloads(self.validate())
        return files

    def rejected(self, message: str, **fixture) -> None:
        self.write(**fixture)
        with self.assertRaisesRegex(draft.DraftValidationError, re.escape(message)):
            self.validate()

    def rejections(self, cases) -> None:
        for name, message, fixture in cases:
            with self.subTest(name):
                self.rejected(message, **fixture)

    # Acceptance -----------------------------------------------------------

    def test_withdrawal_removes_exactly_the_frozen_rows_and_rebuilds_byte_for_byte(self) -> None:
        self.write()
        output = Path(self.directory.name) / f"draft-{self.counter}"
        manifest = draft.build_draft(self.root / CONTRACT, self.pins, output, root=self.root)
        self.assertEqual(
            manifest, draft.validate_draft(output, self.root / CONTRACT, self.pins, root=self.root)
        )
        self.assertEqual(manifest["format"], draft.DRAFT_MANIFEST_FORMAT_V3)
        self.assertEqual(
            manifest["counts"],
            {
                "physical_sites": 199, "projects": 202, "evidence": 923, "countries": 45,
                "non_us_sites": 133, "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 196, "host_estate_context_projects": 1,
            },
        )
        committed = ROOT / THIRTY_SIXTH
        removed = self.frozen.raw_lines(SBOG)
        self.assertEqual(len(removed), 4)
        for name in ("projects.csv", "sites.csv", "evidence.csv"):
            with self.subTest(name):
                before = (committed / name).read_bytes().split(b"\n")
                self.assertEqual(
                    (output / name).read_bytes(),
                    b"\n".join(line for line in before if line not in removed),
                )
        geojson = json.loads((committed / "sites.geojson").read_bytes())
        features = [
            feature for feature in geojson["features"]
            if feature["properties"]["physical_site_stable_key"] != SBOG_SITE
        ]
        self.assertEqual(len(features), 199)
        self.assertEqual(json.loads((output / "sites.geojson").read_bytes()), {**geojson, "features": features})
        self.assertEqual((output / "ATTRIBUTION.txt").read_bytes(), (committed / "ATTRIBUTION.txt").read_bytes())
        # No remaining row names the withdrawn project, site or evidence rows.
        project = self.frozen.project(SBOG)
        for name in ("projects.csv", "sites.csv", "evidence.csv"):
            text = (output / name).read_text()
            for identifier in (project["project_id"], project["site_id"], *SBOG_EVIDENCE):
                self.assertNotIn(identifier, text)
        report = json.loads((output / "selection-report.json").read_bytes())
        reference = json.loads((committed / "selection-report.json").read_bytes())
        self.assertEqual(report["format"], "datacenter-atlas-v018-draft-selection-v3")
        self.assertEqual(report["baseline_corrections"], reference["baseline_corrections"])
        self.assertEqual(report["locator_exceptions"], reference["locator_exceptions"])
        self.assertNotIn("Colombia", report["country_counts"])
        self.assertEqual(
            {k: v for k, v in report["country_counts"].items()},
            {k: v for k, v in reference["country_counts"].items() if k != "Colombia"},
        )
        gates = report["final_release_gates"]
        self.assertEqual((gates["site_count"]["actual"], gates["site_count"]["passed"]), (199, False))
        self.assertEqual(gates["additional_site_count"]["actual"], 99)
        self.assertEqual((gates["country_count"]["actual"], gates["country_count"]["passed"]), (45, True))
        self.assertEqual(gates["non_us_site_count"]["actual"], 133)
        self.assertEqual(gates["maximum_single_country_share"]["actual"], 66 / 199)
        self.assertEqual(gates["imagery_outcomes_complete"]["required"], 202)
        block = report["baseline_withdrawals"]
        self.assertEqual(block["withdrawn_projects"], 1)
        self.assertEqual(block["countries_without_selected_site"], ["Colombia"])
        self.assertEqual(
            block["count_effect"],
            {
                "physical_sites": -1, "projects": -1, "evidence": -2, "countries": -1,
                "non_us_sites": -1, "reviewed_site_locator_projects": -1,
                "host_estate_context_projects": 0, "official_boundary_projects": 0,
            },
        )
        (item,) = block["withdrawals"]
        entry = self.contract["baseline_withdrawals"][0]
        self.assertEqual(item["withdrawal_id"], entry["withdrawal_id"])
        self.assertEqual((item["project_stable_key"], item["physical_site_stable_key"]), (SBOG, SBOG_SITE))
        self.assertEqual((item["project_id"], item["site_id"]), (project["project_id"], project["site_id"]))
        self.assertEqual(item["withdrawal_record"], entry["record"])
        self.assertEqual(item["reason"], entry["reason"])
        self.assertEqual(item["frozen_rows"], entry["frozen_rows"])
        self.assertEqual(item["claim_boundary"]["asserted_physical_status"], None)
        self.assertEqual(item["claim_boundary"]["physical_status_on_lifecycle_reference_date"], "unknown")
        self.assertEqual(
            item["removed_rows"],
            {
                "projects": [project["project_id"]],
                "sites": [project["site_id"]],
                "evidence": SBOG_EVIDENCE,
                "sites_geojson_frozen_feature_indices": [88],
            },
        )
        self.assertEqual(
            item["withdrawn_selected_observation"],
            {
                "last_observed_physical_status": "under_construction",
                "status_as_of": "2026-07-21",
                "status_method": "authoritative_physical_status_update",
                "status_evidence_id": SBOG_EVIDENCE[1],
                "observation_binding_source_id": "synthetic-scala-zona-franca-bogota-campus-observation",
                "qualifies_for_selection": False,
            },
        )
        self.assertEqual(item["count_effect"], {k: v for k, v in block["count_effect"].items() if k != "countries"})
        # The three other Scala status rows on the same capture stay selected, unchanged,
        # are acknowledged by the record and keep the shared-capture gate open.
        self.assertEqual(self.frozen.shared_capture_rows(SBOG), SBOG_SHARED_ROWS)
        self.assertEqual(
            item["shared_capture_rows"],
            {"rows": SBOG_SHARED_ROWS, "statement": "Synthetic fixture: these rows were not reviewed."},
        )
        scala_keys = sorted(key for _, key in SCALA_SHARED)
        self.assertEqual(set(gates), set(reference["final_release_gates"]) | {SHARED_GATE})
        shared = gates[SHARED_GATE]
        self.assertEqual(
            {k: v for k, v in shared.items() if k != "reason"},
            {
                "actual": 3, "required": 0, "passed": False, "projects": scala_keys,
                "evidence_rows": [
                    {**row, "withdrawal_id": entry["withdrawal_id"]} for row in SBOG_SHARED_ROWS
                ],
            },
        )
        self.assertIn("neither changes nor re-reviews", shared["reason"])
        self.assertIn("shared_capture_rows", block["scope"])
        self.assertIn("ATTRIBUTION.txt keeps every inherited v0.17 notice", block["scope"])
        output_projects = {row["project_stable_key"]: row for row in table((output / "projects.csv").read_bytes())}
        frozen_projects = {row["project_stable_key"]: row for row in self.frozen.rows["projects"]}
        for key in scala_keys:
            self.assertEqual(output_projects[key], frozen_projects[key])
        provenance = json.loads((output / "review-provenance.json").read_bytes())
        self.assertEqual(provenance["baseline_withdrawals"], self.contract["baseline_withdrawals"])
        self.assertEqual(
            provenance["independent_baseline_withdrawal_review_sha256"],
            dict(self.pins.baseline_withdrawal_sha256),
        )
        schema = json.loads((output / "schema.json").read_bytes())
        contract = schema["v018_draft_contract"]
        self.assertEqual(contract["baseline_withdrawal_record_schema"], draft.BASELINE_WITHDRAWAL_RECORD_SCHEMA)
        self.assertEqual(contract["baseline_withdrawal_ids"], [entry["withdrawal_id"]])
        self.assertEqual(contract["baseline_withdrawal_decisions"], ["withdraw_from_selection"])
        self.assertEqual(contract["baseline_withdrawal_claim_boundary"], dict(draft.BASELINE_WITHDRAWAL_CLAIM_BOUNDARY))
        self.assertEqual(contract["baseline_withdrawal_shared_capture_gate"], SHARED_GATE)
        old_schema = json.loads((committed / "schema.json").read_bytes())
        for name in ("projects.csv", "sites.csv"):
            fields = {field["name"]: field for field in schema["tables"][name]["fields"]}
            for old in old_schema["tables"][name]["fields"]:
                if "allowed_values" in old and old["logical_type"] == "string":
                    # A withdrawal adds no value, in particular no status value.
                    self.assertEqual(fields[old["name"]]["allowed_values"], old["allowed_values"])
                    self.assertTrue(
                        fields[old["name"]]["allowed_values_scope"].endswith(
                            "; pinned baseline withdrawals remove rows but add no value"
                        )
                    )
        readme = (output / "README.md").read_text()
        self.assertIn("199 physical sites, 202 projects, 45 countries. The frozen v0.17 baseline has 100 sites; this reviewed draft adds 100 and withdraws 1.", readme)
        self.assertIn(
            "All inherited rows and features are preserved, except the changes made by pinned "
            "baseline corrections (the enumerated fields of 1 re-scoped project row, 1 site row and "
            "1 feature; 1 superseded evidence row dropped; and 1 shared evidence row gaining only the "
            "corrected project association) and the rows removed by pinned baseline withdrawals "
            "(1 project row, 1 site row, 1 feature and 2 evidence rows). ",
            readme,
        )
        self.assertIn(
            f"Baseline withdrawals: 1 pinned versioned withdrawal ({entry['withdrawal_id']}) removes "
            "1 inherited project and 1 site from the selection, because its selected evidence does "
            "not meet the acceptance contract, and drops the 2 evidence rows that only it referenced. "
            "A withdrawal asserts no physical status: it does not claim that a project is paused, "
            "cancelled, completed or not under construction, and a withdrawn project's physical "
            "status on 2026-08-20 is unknown. No selected site remains in Colombia.",
            readme,
        )
        self.assertIn(
            "No selected site remains in Colombia. 3 selected projects ("
            + ", ".join(scala_keys)
            + ") keep evidence from the same source capture (the same URL and content hash) as a "
            "withdrawn evidence row; a withdrawal neither changes nor re-reviews them, so the "
            "withdrawal_shared_capture_review gate is not passed. ATTRIBUTION.txt keeps every "
            "inherited v0.17 notice, including notices for sources that only withdrawn rows used. "
            "See selection-report.json baseline_withdrawals.\n\n",
            readme,
        )

    def test_withdrawn_sampled_project_is_a_population_mismatch_and_never_passes(self) -> None:
        # Without the withdrawal the synthetic 20/20 record passes the gate.
        files = self.payloads(withdrawals=())
        gate = json.loads(files["selection-report.json"])["final_release_gates"]["blind_review"]
        self.assertEqual((gate["agreements"], gate["population_matches"], gate["passed"]), (20, True, True))
        for disagree in ((), (10, 17)):
            files = self.payloads(results=synthetic_results(self.root, disagree))
            report = json.loads(files["selection-report.json"])
            gate = report["final_release_gates"]["blind_review"]
            with self.subTest(disagree=disagree):
                self.assertEqual(gate["agreements"], 20 - len(disagree))
                self.assertEqual(gate["reviewed_population_gate_passed"], not disagree)
                self.assertFalse(gate["population_matches"])
                self.assertFalse(gate["passed"])
                self.assertEqual(gate["eligible_project_count"], 202)
                mismatch = gate["population_mismatch"]
                self.assertEqual(mismatch["reviewed_projects_not_in_current_population"], [SBOG])
                self.assertEqual(mismatch["current_projects_not_in_reviewed_population"], [])
                self.assertEqual(mismatch["projects_with_changed_reviewed_claims"], [])
                self.assertEqual(mismatch["sampled_positions_not_covered"], [10])
                self.assertEqual(mismatch["reviewed_projects_withdrawn"], [SBOG])
                self.assertEqual(
                    mismatch["sampled_projects_withdrawn"],
                    [{"position": 10, "project_stable_key": SBOG,
                      "withdrawal_id": "synthetic-scala-zona-franca-bogota-campus-withdrawal"}],
                )
                # The withdrawn sampled project is still reported as reviewed, never re-scored.
                self.assertEqual(gate["sample_outcomes"][9]["project_stable_key"], SBOG)
                readme = files["README.md"].decode()
                self.assertIn(
                    f"Blind review: the pinned pre-registered result ({20 - len(disagree)}/20 "
                    "agreements) was drawn from a different eligible population (203 projects, "
                    "whose keys or blind-reviewed claims differ), not this checkpoint's 202 "
                    "projects, so the blind-review gate is not passed. Sampled position 10 was "
                    "removed by a pinned baseline withdrawal and cannot be re-scored against this "
                    "checkpoint.",
                    readme,
                )

    def test_withdrawing_an_unsampled_reviewed_project_still_changes_the_population(self) -> None:
        files = self.payloads(withdrawals=(WALQA,))
        report = json.loads(files["selection-report.json"])
        gate = report["final_release_gates"]["blind_review"]
        self.assertFalse(gate["passed"])
        mismatch = gate["population_mismatch"]
        self.assertEqual(mismatch["reviewed_projects_not_in_current_population"], [WALQA])
        self.assertEqual(mismatch["sampled_positions_not_covered"], [])
        self.assertEqual(mismatch["sampled_projects_withdrawn"], [])
        self.assertEqual(mismatch["reviewed_projects_withdrawn"], [WALQA])
        block = report["baseline_withdrawals"]
        self.assertEqual(block["countries_without_selected_site"], [])
        self.assertEqual(block["count_effect"]["countries"], 0)
        self.assertEqual(report["counts"]["countries"], 46)
        # No other frozen row shares a Walqa capture, so the shared-capture gate passes.
        self.assertEqual(self.frozen.shared_capture_rows(WALQA), [])
        self.assertEqual(block["withdrawals"][0]["shared_capture_rows"]["rows"], [])
        shared = report["final_release_gates"][SHARED_GATE]
        self.assertEqual(
            (shared["actual"], shared["passed"], shared["projects"], shared["evidence_rows"]),
            (0, True, [], []),
        )
        readme = files["README.md"].decode()
        self.assertNotIn("No selected site remains", readme)
        self.assertNotIn("Sampled position", readme)
        self.assertIn(
            "No selected project shares a source capture with a withdrawn evidence row. "
            "ATTRIBUTION.txt keeps every inherited v0.17 notice",
            readme,
        )

    def test_two_withdrawals_are_reported_together(self) -> None:
        files = self.payloads(withdrawals=(SBOG, WALQA))
        report = json.loads(files["selection-report.json"])
        block = report["baseline_withdrawals"]
        walqa_evidence = len(self.frozen.evidence_ids(WALQA))
        self.assertEqual(block["withdrawn_projects"], 2)
        self.assertEqual(block["count_effect"]["physical_sites"], -2)
        self.assertEqual(block["count_effect"]["evidence"], -2 - walqa_evidence)
        self.assertEqual(block["count_effect"]["countries"], -1)
        self.assertEqual([item["project_stable_key"] for item in block["withdrawals"]], [SBOG, WALQA])
        self.assertEqual(report["counts"]["physical_sites"], 198)
        self.assertEqual(report["counts"]["evidence"], 925 - 2 - walqa_evidence)
        shared = report["final_release_gates"][SHARED_GATE]
        self.assertEqual(shared["projects"], sorted(key for _, key in SCALA_SHARED))
        self.assertEqual(
            {row["withdrawal_id"] for row in shared["evidence_rows"]},
            {"synthetic-scala-zona-franca-bogota-campus-withdrawal"},
        )
        readme = files["README.md"].decode()
        self.assertIn("this reviewed draft adds 100 and withdraws 2.", readme)
        self.assertIn(
            "Baseline withdrawals: 2 pinned versioned withdrawals "
            "(synthetic-aws-walqa-huesca-data-center-withdrawal, "
            "synthetic-scala-zona-franca-bogota-campus-withdrawal) remove 2 inherited projects and "
            "2 sites from the selection, because their selected evidence does not meet the "
            f"acceptance contract, and drop the {2 + walqa_evidence} evidence rows that only they "
            "referenced.",
            readme,
        )
        self.rejected(
            "duplicate baseline withdrawal target",
            withdrawals=(SBOG, SBOG),
        )

    def test_v3_without_withdrawals_keeps_its_outputs(self) -> None:
        files = self.payloads(withdrawals=())
        report = json.loads(files["selection-report.json"])
        self.assertNotIn("baseline_withdrawals", report)
        self.assertNotIn(SHARED_GATE, report["final_release_gates"])
        self.assertIsNone(report["final_release_gates"]["blind_review"]["population_mismatch"])
        provenance = json.loads(files["review-provenance.json"])
        self.assertNotIn("baseline_withdrawals", provenance)
        self.assertNotIn("independent_baseline_withdrawal_review_sha256", provenance)
        schema = json.loads(files["schema.json"])
        self.assertFalse([key for key in schema["v018_draft_contract"] if "withdrawal" in key])
        readme = files["README.md"].decode()
        self.assertIn("this reviewed draft adds 100. ", readme)
        self.assertIn(
            "All inherited rows and features are preserved, except the changes made by pinned "
            "baseline corrections: the enumerated fields of 1 re-scoped project row",
            readme,
        )
        self.assertNotIn("withdraw", readme)
        committed = ROOT / THIRTY_SIXTH
        for name in ("projects.csv", "sites.csv", "evidence.csv", "sites.geojson"):
            self.assertEqual(files[name], (committed / name).read_bytes())

    # Fail-closed rejections -------------------------------------------------

    def test_withdrawals_need_v3_a_nonempty_list_and_exact_pins(self) -> None:
        def v2(value: dict) -> None:
            value["schema_version"] = draft.SCHEMA_VERSION_V2
            del value["blind_review"]

        def no_blind_pin(pins: draft.ReviewPins) -> draft.ReviewPins:
            return replace(pins, blind_review_sha256=None)

        self.rejections(
            [
                ("v2 carries the key", "batch contract keys differ",
                 {"contract": v2, "pins": no_blind_pin}),
                ("empty list", "v3 baseline withdrawals must be a nonempty list when present",
                 {"withdrawals": (), "contract": lambda c: c.update(baseline_withdrawals=[]),
                  "pins": lambda p: replace(p, baseline_withdrawal_sha256={})}),
                ("pins without withdrawals", "baseline withdrawal review pins require a v3 contract with baseline_withdrawals",
                 {"withdrawals": (), "pins": lambda p: replace(p, baseline_withdrawal_sha256={"x": "0" * 64})}),
                ("missing pin", "independent baseline withdrawal review pin differs",
                 {"pins": lambda p: replace(p, baseline_withdrawal_sha256={})}),
                ("extra pin", "baseline withdrawal review pin inventory differs",
                 {"pins": lambda p: replace(p, baseline_withdrawal_sha256={**p.baseline_withdrawal_sha256, "other-withdrawal": "0" * 64})}),
                ("stale pin", "independent baseline withdrawal review pin differs",
                 {"contract": lambda c: c["baseline_withdrawals"][0].update(reason="Edited after review.")}),
                ("extra entry key", "baseline withdrawal keys differ",
                 {"entry": lambda key, e: e.update(note="unreviewed")}),
                ("unsafe id", "unsafe withdrawal ID",
                 {"entry": lambda key, e: e.update(withdrawal_id="../escape")}),
                ("blank reason", "baseline withdrawal reason must be nonempty text",
                 {"entry": lambda key, e: e.update(reason=" ")}),
            ]
        )

    def test_frozen_rows_are_checked_by_exact_bytes(self) -> None:
        def tamper(path: tuple, value) -> dict:
            def mutate(key: str, entry: dict) -> None:
                target = entry["frozen_rows"]
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = value

            return {"entry": mutate}

        unrelated = self.frozen.spec("evidence", "evidence_id", self.frozen.evidence_ids(WALQA)[0])

        def missing_row(key: str, entry: dict) -> None:
            entry["frozen_rows"]["evidence_csv"].pop()

        def extra_row(key: str, entry: dict) -> None:
            entry["frozen_rows"]["evidence_csv"].append(unrelated)
            entry["frozen_rows"]["evidence_csv"].sort(key=lambda spec: spec["file_line_number"])

        def reordered(key: str, entry: dict) -> None:
            entry["frozen_rows"]["evidence_csv"].reverse()

        def additional(key: str, entry: dict) -> None:
            entry["frozen_rows"]["additional_evidence_csv"] = []

        self.rejections(
            [
                ("project line", "frozen projects row identity differs", tamper(("projects_csv", "file_line_number"), 92)),
                ("project row hash", "frozen projects row SHA-256 differs", tamper(("projects_csv", "row_canonical_sha256"), "0" * 64)),
                ("project raw line", "frozen projects raw line SHA-256 differs", tamper(("projects_csv", "raw_line_sha256"), "0" * 64)),
                ("site row hash", "frozen sites row SHA-256 differs", tamper(("sites_csv", "row_canonical_sha256"), "0" * 64)),
                ("evidence raw line", "frozen evidence raw line SHA-256 differs", tamper(("evidence_csv", 0, "raw_line_sha256"), "0" * 64)),
                ("feature hash", "frozen GeoJSON feature SHA-256 differs", tamper(("sites_geojson", "feature_canonical_sha256"), "0" * 64)),
                ("feature index", "frozen GeoJSON feature SHA-256 differs", tamper(("sites_geojson", "feature_index"), 87)),
                ("baseline", "baseline withdrawal must name rows of the pinned v0.17 manifest", tamper(("manifest_sha256",), "0" * 64)),
                ("missing evidence row", "withdrawn evidence rows differ from the frozen evidence rows of the project", {"entry": missing_row}),
                ("unrelated evidence row", "withdrawn evidence rows differ from the frozen evidence rows of the project", {"entry": extra_row}),
                ("evidence order", "withdrawn evidence rows must be listed once each, in file order", {"entry": reordered}),
                ("extra frozen key", "baseline withdrawal frozen rows keys differ", {"entry": additional}),
                ("no evidence list", "withdrawn evidence rows must be a nonempty list", tamper(("evidence_csv",), [])),
            ]
        )

    def test_only_single_project_sites_without_shared_evidence_can_be_withdrawn(self) -> None:
        self.rejections(
            [
                ("shared site", "baseline withdrawals support single-project sites only", {"withdrawals": (STT_PROJECT,)}),
                ("shared evidence row", "withdrawn evidence row is shared with another project", {"withdrawals": (HEBRON,)}),
            ]
        )

    def test_the_record_is_pinned_and_machine_checked(self) -> None:
        def record(field: str, value) -> dict:
            return {"record": lambda key, document: document.update({field: value})}

        def entry_record(**fields) -> dict:
            return {"entry": lambda key, e: e["record"].update(fields)}

        def count(field: str, value) -> dict:
            return {"record": lambda key, document: document["count_effect"].update({field: value})}

        def frozen_line(key: str, document: dict) -> None:
            document["frozen_baseline_rows"]["projects_csv"]["file_line_number"] = 91.0

        def shared(**fields) -> dict:
            return {"record": lambda key, document: document["shared_capture_rows"].update(fields)}

        def shared_edit(edit) -> dict:
            return {"record": lambda key, document: edit(document["shared_capture_rows"])}

        walqa_row = {
            "evidence_id": self.frozen.evidence_ids(WALQA)[0],
            "project_stable_keys": [WALQA],
            "withdrawn_evidence_id": SBOG_EVIDENCE[1],
        }
        differ = "baseline withdrawal shared-capture rows differ from the frozen evidence rows"
        self.rejections(
            [
                ("shared rows omitted", differ, shared(rows=[])),
                ("shared rows not a list", differ, shared(rows={})),
                ("shared rows reordered", differ, shared_edit(lambda block: block["rows"].reverse())),
                ("shared row extra", differ, shared_edit(lambda block: block["rows"].append(walqa_row))),
                ("shared row dropped", differ, shared_edit(lambda block: block["rows"].pop())),
                ("shared row retargeted", differ,
                 shared_edit(lambda block: block["rows"][0].update(withdrawn_evidence_id=SBOG_EVIDENCE[0]))),
                ("shared row project", differ,
                 shared_edit(lambda block: block["rows"][0].update(project_stable_keys=[SBOG]))),
                ("shared statement missing", "baseline withdrawal shared-capture rows keys differ",
                 shared_edit(lambda block: block.pop("statement"))),
                ("shared statement blank", "baseline withdrawal shared-capture statement must be nonempty text",
                 shared(statement=" ")),
                ("shared block missing", "baseline withdrawal record keys differ",
                 {"record": lambda key, document: document.pop("shared_capture_rows")}),
            ]
        )
        self.rejections(
            [
                ("record bytes", "input SHA-256 differs", entry_record(sha256="0" * 64)),
                ("record size", "input byte count differs", entry_record(bytes=1)),
                ("record outside sources", "baseline withdrawal record must be under sources/", entry_record(path=PREREGISTRATION)),
                ("schema", "baseline withdrawal record schema differs", record("schema_version", "other-schema")),
                ("other withdrawal", "baseline withdrawal record names a different withdrawal", record("withdrawal_id", "another-withdrawal")),
                ("other project", "baseline withdrawal record names a different withdrawal", record("project_stable_key", WALQA)),
                ("unknown key", "baseline withdrawal record keys differ", record("extra", "unchecked")),
                ("cutoff", "withdrawal lifecycle cutoff cannot move", record("lifecycle_reference_date", "2026-09-01")),
                ("additional sites", "a baseline withdrawal cannot add sites", record("accepted_additional_sites", 1)),
                ("boolean sites", "a baseline withdrawal cannot add sites", record("accepted_additional_sites", False)),
                ("late review", "withdrawal review date falls outside the checkpoint review", record("reviewed_at", "2026-10-11")),
                ("early review", "withdrawal review date falls outside the checkpoint review", record("reviewed_at", "2026-08-19")),
                ("decision", "baseline withdrawal decision differs", record("decision", "mark_cancelled")),
                ("basis", "invalid baseline withdrawal basis", record("withdrawal_basis", "project_cancelled")),
                ("frozen rows", "contract frozen rows differ from the withdrawal record", {"record": frozen_line}),
                ("evidence effect", "baseline withdrawal count effect differs from the frozen rows it removes", count("evidence", -1)),
                ("locator effect", "baseline withdrawal count effect differs from the frozen rows it removes", count("reviewed_site_locator_projects", 0)),
                ("country effect", "withdrawal count effect keys differ", count("countries", -1)),
                ("blank reason", "baseline withdrawal record reason must be nonempty text", record("withdrawal_reason", "")),
            ]
        )

    def test_a_withdrawal_never_asserts_a_physical_status(self) -> None:
        def boundary(**fields) -> dict:
            return {"record": lambda key, document: document["claim_boundary"].update(fields)}

        def drop_statement(key: str, document: dict) -> None:
            del document["claim_boundary"]["statement"]

        message = "a baseline withdrawal asserts no physical status"
        self.rejections(
            [
                ("cancelled", message, boundary(asserted_physical_status="cancelled")),
                ("paused", message, boundary(asserts_paused=True)),
                ("completed", message, boundary(asserts_completed=True)),
                ("not cancelled flag", message, boundary(asserts_cancelled=True)),
                ("not under construction", message, boundary(asserts_not_under_construction=True)),
                ("status on cutoff", message, boundary(physical_status_on_lifecycle_reference_date="paused")),
                ("integer flag", message, boundary(asserts_paused=0)),
                ("no statement", "baseline withdrawal claim boundary keys differ", {"record": drop_statement}),
                ("blank statement", "baseline withdrawal claim boundary statement must be nonempty text", boundary(statement="")),
                ("extra claim", "baseline withdrawal claim boundary keys differ", boundary(asserts_operational=False)),
            ]
        )

    def test_withdrawn_observation_must_be_the_frozen_status(self) -> None:
        def binding(**fields) -> dict:
            return {"record": lambda key, document: document["withdrawn_observation_binding"].update(fields)}

        walqa_path, _, _ = OBSERVATIONS[WALQA]
        walqa_raw = (ROOT / walqa_path).read_bytes()
        walqa = json.loads(walqa_raw)

        def other_project(key: str, document: dict) -> None:
            document["withdrawn_observation_binding"].update(
                source_path=walqa_path,
                source_file_sha256=sha256(walqa_raw),
                source_file_bytes=len(walqa_raw),
                evidence_record_sha256=draft.canonical_sha256(walqa["evidence"][0]),
                project_sha256=draft.canonical_sha256(walqa["project"]),
                campus_sha256=draft.canonical_sha256(walqa["campus"]),
                lifecycle_sha256=draft.canonical_sha256(walqa["lifecycle"][0]),
            )

        def no_lifecycle(key: str, document: dict) -> None:
            for field in ("lifecycle_pointer", "lifecycle_sha256"):
                del document["withdrawn_observation_binding"][field]

        basis = (self.root / BASIS).read_bytes()

        def not_v017(key: str, document: dict) -> None:
            document["withdrawn_observation_binding"] = {
                "source_id": "synthetic-basis",
                "source_path": BASIS,
                "source_file_sha256": sha256(basis),
                "source_file_bytes": len(basis),
                "evidence_pointer": "",
                "evidence_record_sha256": draft.canonical_sha256(json.loads(basis)),
            }

        self.rejections(
            [
                ("hash", "withdrawn observation binding record SHA-256 differs", binding(lifecycle_sha256="0" * 64)),
                ("file", "input SHA-256 differs", binding(source_file_sha256="0" * 64)),
                ("other project", "withdrawn observation binding project/campus differs", {"record": other_project}),
                ("no lifecycle", "withdrawn observation binding is not a pinned v0.17 curated input", {"record": no_lifecycle}),
                ("not a v0.17 input", "withdrawn observation binding is not a pinned v0.17 curated input", {"record": not_v017}),
                ("unknown key", "withdrawn observation binding keys differ", binding(extra="x")),
            ]
        )

    def test_inherited_through_draft_and_review_basis_fail_closed(self) -> None:
        def through(**fields) -> dict:
            return {"record": lambda key, document: document["inherited_unchanged_through"].update(fields)}

        def basis(value) -> dict:
            return {"record": lambda key, document: document.update(review_basis=value)}

        pin = {"path": BASIS, "bytes": len((self.root / BASIS).read_bytes()), "sha256": sha256((self.root / BASIS).read_bytes())}
        changed = "verified_construction_core/2026-08-20-v0.18-draft-synthetic-changed-sbogzb01"
        target = self.root / changed
        if not target.exists():
            shutil.copytree(self.root / THIRTY_SIXTH, target)
            raw = (target / "projects.csv").read_bytes()
            edited = raw.replace(b"Scala SBOGZB01,", b"Scala SBOGZB01 (edited),", 1)
            self.assertNotEqual(raw, edited)
            (target / "projects.csv").write_bytes(edited)
            manifest = json.loads((target / "manifest.json").read_bytes())
            manifest["files"]["projects.csv"] = {"bytes": len(edited), "sha256": sha256(edited)}
            (target / "manifest.json").write_bytes(draft.core._json_bytes(manifest))
        self.rejections(
            [
                ("baseline itself", "not the frozen baseline",
                 through(release_path=draft.BASELINE_RELATIVE_DIR, manifest_sha256=draft.BASELINE_MANIFEST_SHA256)),
                ("manifest pin", "input SHA-256 differs", through(manifest_sha256="0" * 64)),
                ("not preserved", "inherited-through release must preserve the frozen rows", through(rows_byte_identical_to_v017=False)),
                ("changed row", "inherited projects row changed after v0.17", {"through": changed}),
                ("no basis", "baseline withdrawal needs a pinned review basis", basis([])),
                ("tampered basis", "input SHA-256 differs", basis([{**pin, "sha256": "0" * 64}])),
                ("repeated basis", "baseline withdrawal review basis repeats a file or names the record itself", basis([pin, pin])),
                ("basis outside sources", "baseline withdrawal review basis must be under sources/",
                 basis([{"path": PREREGISTRATION, "bytes": 1, "sha256": "0" * 64}])),
            ]
        )

        def self_basis(key: str, document: dict) -> None:
            # The record cannot pin itself: its path is the record path of this fixture.
            document["review_basis"] = [{"path": f"sources/synthetic-withdrawal-{self.counter}-{slug(key)}.json", "bytes": 0, "sha256": "0" * 64}]

        with self.subTest("self basis"):
            self.write(record=self_basis)
            with self.assertRaisesRegex(draft.DraftValidationError, "input"):
                self.validate()

    def test_a_corrected_project_or_intersecting_site_cannot_be_withdrawn(self) -> None:
        # CGK is corrected by the thirty-sixth contract; its rows are unchanged in the 35th.
        self.rejected("a baseline project cannot be both corrected and withdrawn", withdrawals=(CGK,), through=THIRTY_FIFTH)
        # A correction that declares the withdrawn site as an unchanged intersecting site.
        raw = (self.root / CGK_RECORD).read_bytes()
        document = json.loads(raw)
        document["preservation_invariants"]["intersecting_site_rows_unchanged"] = sorted([SBOG_SITE, STT_SITE])
        edited = dumps(document)
        path = "sources/synthetic-cgk-correction-declaring-sbogzb01.json"
        (self.root / path).write_bytes(edited)

        def repoint(contract: dict) -> None:
            for spec in contract["sources"]:
                if spec["path"] == CGK_RECORD:
                    spec.update(path=path, bytes=len(edited), sha256=sha256(edited))

        def repin(pins: draft.ReviewPins) -> draft.ReviewPins:
            specs = {spec["source_id"]: spec for spec in self.contract["sources"]}
            return replace(
                pins,
                source_sha256={**pins.source_sha256, **{
                    source_id: draft.canonical_sha256(spec)
                    for source_id, spec in specs.items() if spec["path"] == path
                }},
            )

        self.rejected("a withdrawn site cannot be a correction's intersecting unchanged site", contract=repoint, pins=repin)

    def test_a_later_checkpoint_may_inherit_through_a_draft_with_a_withdrawal(self) -> None:
        # Features after the withdrawn one shift by one; the frozen feature and rows of
        # a later correction are located by their bytes, so RDH2 (frozen feature 91)
        # is found at index 90 of the withdrawn draft and its duplicate is rejected.
        self.write()
        release = "verified_construction_core/2026-08-20-v0.18-draft-synthetic-withdrawn"
        if not (self.root / release).exists():
            draft.build_draft(self.root / CONTRACT, self.pins, self.root / release, root=self.root)
        frozen = self.frozen.frozen_rows(RDH2)
        self.assertEqual(frozen["sites_geojson"]["feature_index"], 91)
        features = json.loads((self.root / release / "sites.geojson").read_bytes())["features"]
        self.assertEqual(draft.canonical_sha256(features[90]), frozen["sites_geojson"]["feature_canonical_sha256"])
        # A v3 inherited-through release; a v2 contract may not name one.
        spec = {
            "release_path": release,
            "manifest_sha256": sha256((self.root / release / "manifest.json").read_bytes()),
            "rows_byte_identical_to_v017": True,
        }
        lines = draft._inherited_unchanged_through(spec, self.root, frozen, draft.INHERITED_THROUGH_FORMATS_V3)
        self.assertEqual(len(lines["projects"]), 202)
        with self.assertRaisesRegex(draft.DraftValidationError, "inherited-through release is not a v0.18 draft"):
            draft._inherited_unchanged_through(spec, self.root, frozen, draft.INHERITED_THROUGH_FORMATS_V2)
        duplicated = "verified_construction_core/2026-08-20-v0.18-draft-synthetic-duplicated-feature"
        target = self.root / duplicated
        if not target.exists():
            shutil.copytree(self.root / release, target)
            geojson = json.loads((target / "sites.geojson").read_bytes())
            geojson["features"].append(features[90])
            raw = draft.core._json_bytes(geojson)
            (target / "sites.geojson").write_bytes(raw)
            manifest = json.loads((target / "manifest.json").read_bytes())
            manifest["files"]["sites.geojson"] = {"bytes": len(raw), "sha256": sha256(raw)}
            (target / "manifest.json").write_bytes(draft.core._json_bytes(manifest))
        spec = {**spec, "release_path": duplicated, "manifest_sha256": sha256((target / "manifest.json").read_bytes())}
        with self.assertRaisesRegex(draft.DraftValidationError, "inherited GeoJSON feature changed after v0.17"):
            draft._inherited_unchanged_through(spec, self.root, frozen, draft.INHERITED_THROUGH_FORMATS_V3)
        # The withdrawn project's own rows are gone from that draft.
        with self.assertRaisesRegex(draft.DraftValidationError, "inherited projects row changed after v0.17"):
            draft._inherited_unchanged_through(
                {**spec, "release_path": release, "manifest_sha256": sha256((self.root / release / "manifest.json").read_bytes())},
                self.root,
                self.frozen.frozen_rows(SBOG),
                draft.INHERITED_THROUGH_FORMATS_V3,
            )


if __name__ == "__main__":
    unittest.main()
