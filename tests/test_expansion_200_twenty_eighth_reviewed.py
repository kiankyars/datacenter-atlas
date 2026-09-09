"""Two reviewed campuses; source scope and all preceding release rows stay fixed."""

from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from datacenter_atlas import expansion_200_twenty_seventh_reviewed as previous
from datacenter_atlas import expansion_200_twenty_eighth_reviewed as batch
from datacenter_atlas import verified_construction_core_v018 as core
from datacenter_atlas import verified_construction_core as legacy_core
from datacenter_atlas.models import EvidenceKind


ROOT = Path(__file__).resolve().parents[1]
curated_v11 = importlib.import_module(f"{legacy_core.__package__}.curated_v11")
AURORA = "curated:cyrusone-aurora-diehl-road-campus"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def table(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def additions():
    return read(batch.contract_path(ROOT))["acceptances"][81:]


def documents(acceptance):
    sources = {
        row["source_id"]: row for row in read(batch.contract_path(ROOT))["sources"]
    }
    return tuple(
        read(ROOT / sources[acceptance[key]["source_id"]]["path"])
        for key in ("status", "geometry")
    )


class TwentyEighthReviewedDraftTests(unittest.TestCase):
    def test_two_distinct_campuses_and_exact_cumulative_counts(self):
        contract = read(batch.contract_path(ROOT))
        self.assertEqual(len(contract["acceptances"]), 83)
        self.assertEqual(len(contract["sources"]), 576)
        self.assertEqual(
            Counter(x["country_iso_a2"] for x in additions()), {"US": 1, "AU": 1}
        )
        self.assertEqual(
            read(batch.draft_path(ROOT) / "manifest.json")["counts"],
            {
                "physical_sites": 183,
                "projects": 186,
                "countries": 43,
                "non_us_sites": 122,
                "evidence": 812,
                "official_boundary_projects": 5,
                "reviewed_site_locator_projects": 181,
            },
        )

    def test_aurora_is_permanent_retrofit_not_new_capacity_or_routine_testing(self):
        (acceptance,) = [
            x for x in additions() if x["parent_campus_stable_key"] == AURORA
        ]
        doc, proposal = documents(acceptance)
        self.assertTrue(
            doc["project"]["stable_key"].endswith(
                ":chi2-sound-mitigation-capital-retrofit"
            )
        )
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-08-20")
        metadata = doc["evidence"][0]["metadata"]
        self.assertIn("already operating", metadata["project_scope"])
        self.assertIn(
            "Routine generator testing and maintenance", metadata["excluded_scope"]
        )
        self.assertIn("post-cutoff", metadata["successor_review"])
        (result,) = proposal["results"]
        self.assertEqual(
            result["geometry"]["coordinates"], [-88.243410186001, 41.798071182484]
        )
        self.assertIn("not the CHI2 rooftop", result["semantics"]["precision_scope"])
        source = next(
            x
            for x in proposal["evidence"]
            if x["key"] == "am31-cyrusone-aurora-census-locator"
        )
        self.assertEqual(source["metadata"]["source_crs"], "EPSG:4269")
        self.assertTrue(source["metadata"]["transformation"]["executed"])
        self.assertIn(
            "not the unknown positional accuracy",
            source["metadata"]["transformation"]["accuracy_caveat"],
        )

    def test_firmus_direct_executive_disclosure_keeps_broadcaster_and_date_limits(self):
        (acceptance,) = [x for x in additions() if x["country_iso_a2"] == "AU"]
        doc, proposal = documents(acceptance)
        status = doc["evidence"][0]
        self.assertEqual(status["kind"], "company_disclosure")
        self.assertEqual(status["publisher"], "Australian Broadcasting Corporation")
        self.assertIn("Curtis's answer", status["metadata"]["authority_scope"])
        self.assertFalse(status["metadata"]["audio_verification"])
        self.assertEqual(doc["lifecycle"][0]["as_of_date"], "2026-07-02")
        self.assertIn("July 1 22:30 UTC", status["metadata"]["status_date_semantics"])
        (result,) = proposal["results"]
        self.assertEqual(result["geometry"]["coordinates"], [147.176554, -41.4408613])
        self.assertEqual(result["semantics"]["geometry_use_scope"], "campus_locator")
        self.assertIn(
            "existing-building reference", result["semantics"]["precision_scope"]
        )
        bridge = proposal["evidence"][0]["metadata"]
        self.assertEqual(bridge["pdf_pages_visually_reviewed"], [9, 22, 23, 24])
        self.assertFalse(bridge["lifecycle_selected"])

    def test_no_unsupported_metrics_roles_or_imagery(self):
        for acceptance in additions():
            doc, proposal = documents(acceptance)
            for key in ("capacities", "workloads", "operating_models"):
                self.assertEqual(doc[key], [])
            for entity in ("campus", "project"):
                self.assertEqual(doc[entity]["roles"], {})
                self.assertIsNone(doc[entity]["coordinates"])
            self.assertIsNone(
                proposal["results"][0]["semantics"]["horizontal_uncertainty_metres"]
            )

    def test_selected_source_closure_valid_kinds_and_fresh_custody(self):
        contract = read(batch.contract_path(ROOT))
        new_specs = contract["sources"][559:]
        self.assertEqual(len(new_specs), 17)
        for spec in new_specs:
            raw = (ROOT / spec["path"]).read_bytes()
            self.assertEqual(len(raw), spec["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
            value = json.loads(raw)
            for token in spec["evidence_pointer"].strip("/").split("/"):
                value = value[int(token)] if isinstance(value, list) else value[token]
            EvidenceKind(value["kind"])
            core._source_evidence(value, spec["source_id"])
            self.assertEqual(core.canonical_sha256(value), spec["evidence_sha256"])
            self.assertEqual(value["metadata"]["http_status"], 200)
            self.assertIn("2026-09-09T23:35:", value["retrieved_at"])
            self.assertIn("custody_refresh", value["metadata"])
            self.assertFalse(value["metadata"]["request_credentials_supplied"])
        for acceptance in additions():
            spec = next(
                x
                for x in new_specs
                if x["source_id"] == acceptance["status"]["source_id"]
            )
            curated_v11._parse_document(ROOT / spec["path"], "2026-09-09T23:59:59Z")

    def test_hold_packets_cannot_count_as_admissions(self):
        selected = json.dumps(additions())
        self.assertNotIn("81f637bc", selected)
        self.assertNotIn("north-augusta", selected)
        audit = read(
            ROOT / "sources/research-expansion-200-root-round31-review-2026-09-09.json"
        )
        self.assertEqual(audit["baseline"]["sites"], 181)
        self.assertEqual(
            audit["independent_checks"]["raw_hashes_and_bytes_verified"], 17
        )
        self.assertEqual(audit["completion"]["remaining_to_200"], 17)
        self.assertFalse(audit["completion"]["objective_complete"])
        facts = read(
            ROOT
            / "sources/reviewed-source-facts-2026-09-09-root-round31-meta-aiken-current-build.json"
        )
        self.assertEqual(facts["admission_decision"]["status"], "held_not_selected")
        self.assertEqual(facts["evidence"][0]["kind"], "news")
        self.assertEqual(facts["lifecycle"][0]["method"], "unselected_reporter_narrative")
        proposal = read(
            ROOT
            / "sources/verified-construction-core-v0.18-root-round31-meta-aiken-geometry-proposal.json"
        )
        self.assertEqual(len(proposal["source_binding_map"]), 10)
        for binding in proposal["source_binding_map"]:
            document = read(ROOT / binding["path"])
            index = int(binding["evidence_pointer"].rsplit("/", 1)[1])
            self.assertEqual(document["evidence"][index]["key"], binding["source_id"])
        north_augusta = read(
            ROOT
            / "sources/research-expansion-200-root-round31-north-augusta-2026-09-09.json"
        )
        self.assertEqual(
            north_augusta["admission_decision"]["status"], "held_not_selected"
        )
        self.assertEqual(north_augusta["parcel_identity"]["PARCEL_ASR"], "013-16-04-003")
        self.assertIsNone(north_augusta["geometry_context"]["selected_coordinates"])

    def test_all_prior_rows_full_features_and_source_pins_preserved(self):
        before, after = previous.draft_path(ROOT), batch.draft_path(ROOT)
        for name, key in (
            ("projects.csv", "project_stable_key"),
            ("sites.csv", "physical_site_stable_key"),
            ("evidence.csv", "evidence_id"),
        ):
            current = {x[key]: x for x in table(after / name)}
            for row in table(before / name):
                self.assertEqual(row, current[row[key]])
            self.assertLessEqual(
                Counter((before / name).read_bytes().splitlines(keepends=True)),
                Counter((after / name).read_bytes().splitlines(keepends=True)),
            )
        for feature in read(before / "sites.geojson")["features"]:
            self.assertIn(feature, read(after / "sites.geojson")["features"])
        old, new = read(previous.contract_path(ROOT)), read(batch.contract_path(ROOT))
        self.assertEqual(old["sources"], new["sources"][:559])
        for source in old["sources"]:
            key = source["source_id"]
            self.assertEqual(
                previous.REVIEW_PINS.source_sha256[key],
                batch.REVIEW_PINS.source_sha256[key],
            )
        for old_acceptance, new_acceptance in zip(
            old["acceptances"], new["acceptances"], strict=False
        ):
            new_acceptance["distinctness_review"]["batch_site_keys_sha256"] = (
                old_acceptance["distinctness_review"]["batch_site_keys_sha256"]
            )
            self.assertEqual(old_acceptance, new_acceptance)

    def test_eleven_artifacts_rebuild_and_final_gaps_remain(self):
        stored = batch.draft_path(ROOT)
        manifest = core.validate_draft(
            stored, batch.contract_path(ROOT), batch.REVIEW_PINS, root=ROOT
        )
        self.assertFalse(manifest["publishable_as_final"])
        self.assertFalse(manifest["objective_completion_claim"])
        gates = read(stored / "selection-report.json")["final_release_gates"]
        self.assertEqual(gates["imagery_outcomes_complete"]["actual"], 10)
        self.assertEqual(gates["blind_review"]["required_sample_size"], 20)
        self.assertEqual(gates["blind_review"]["required_agreements"], 19)
        self.assertFalse(gates["site_count"]["passed"])
        self.assertFalse(gates["blind_review"]["passed"])
        with tempfile.TemporaryDirectory(prefix="atlas-twenty-eighth-rebuild-") as temp:
            output = Path(temp) / "draft"
            core.build_draft(
                batch.contract_path(ROOT), batch.REVIEW_PINS, output, root=ROOT
            )
            self.assertEqual(len(list(stored.iterdir())), 11)
            for path in stored.iterdir():
                self.assertEqual(path.read_bytes(), (output / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
