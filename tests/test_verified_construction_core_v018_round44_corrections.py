"""Round44 baseline-correction rules B1-B6 over the real RDH2 and RCJM1 records.

Adapted from the round44 correction design. The two correction records must be
committed under sources/ at the paths below. Each test builds a v2 contract in a
temporary root from the committed thirty-sixth contract plus the corrections,
with pins computed here (as the synthetic baseline-correction tests do), so it
does not depend on a committed thirty-seventh checkpoint. The SBOGZB01 host-zone
rescope is superseded by its baseline withdrawal, so rule B1 (a reused null
publication value equals a frozen empty one), which only that record needed, is
tested directly on the capture comparison.
"""

from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import importlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from datacenter_atlas import expansion_200_thirty_sixth_reviewed as previous
from datacenter_atlas import verified_construction_core_v018 as core


ROOT = Path(__file__).resolve().parents[1]
RECORDS = {
    "rdh2-host-estate-locator-rescope-v1": (
        "sources/verified-construction-core-v0.18-rdh2-host-estate-locator-correction-v1.json",
        "rdh2-commissioning-status-identity",
    ),
    "rcjm1-host-estate-locator-rescope-v1": (
        "sources/verified-construction-core-v0.18-rcjm1-host-estate-locator-correction-v1.json",
        "rcjm1-phase-a-status-identity",
    ),
}
RDH2, RCJM1 = RECORDS
THIRTY_SIXTH = "verified_construction_core/2026-08-20-v0.18-draft-thirty-sixth-reviewed"
COPIED_RELEASES = (
    core.BASELINE_RELATIVE_DIR,
    "verified_construction_core/2026-08-20-v0.18-draft-thirty-fifth-reviewed",
    THIRTY_SIXTH,
)
SUPERSEDED = {
    RDH2: ["5b8fa185-405c-56fd-86c4-a0a295820be1"],
    RCJM1: ["d4d4c451-8160-5936-8b49-30b9cebad256", "0f041ac1-c722-588c-bb02-442fcb4c53b3"],
}
SHARED_CRS = "491b3b57-f2fb-53b4-ad33-07902a6d2e19"
STT_SITE = "curated:stt-jakarta-data-centre-campus"
CGK_SITE = "curated:digital-edge-cgk-campus-bekasi"


def table(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class Round44CorrectionRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="atlas-round44-")
        cls.root = Path(cls.temporary.name)
        for name in ("sources", "definitions"):
            shutil.copytree(ROOT / name, cls.root / name)
        for release in COPIED_RELEASES:
            shutil.copytree(ROOT / release, cls.root / release)
        cls.base_contract = json.loads(previous.contract_path(ROOT).read_bytes())
        cls.records = {
            cid: json.loads((ROOT / path).read_bytes()) for cid, (path, _) in RECORDS.items()
        }
        cls.counter = 0

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    # Fixture helpers ----------------------------------------------------

    def contract_for(self, records: dict[str, dict]) -> tuple[Path, core.ReviewPins]:
        """Write the records and a v2 contract (36th + these corrections) with fresh pins."""
        type(self).counter += 1
        contract = deepcopy(self.base_contract)
        source_pins = dict(previous.REVIEW_PINS.source_sha256)
        correction_pins = dict(previous.REVIEW_PINS.baseline_correction_sha256)
        for cid, document in records.items():
            raw = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
            relative = f"sources/round44-test-{self.counter}-{cid}.json"
            (self.root / relative).write_bytes(raw)
            for binding in document["source_bindings"]:
                spec = {
                    "source_id": binding["source_id"],
                    "path": relative,
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "evidence_pointer": binding["evidence_pointer"],
                    "evidence_sha256": core.canonical_sha256(
                        core._pointer(document, binding["evidence_pointer"])
                    ),
                }
                contract["sources"].append(spec)
                source_pins[spec["source_id"]] = core.canonical_sha256(spec)
            record = document["results"][0]
            entry = {
                "correction_id": cid,
                "physical_site_stable_key": record["parent_campus_stable_key"],
                "project_stable_key": record["project_stable_key"],
                "frozen_rows": document["supersedes"]["frozen_baseline_rows"],
                "geometry": {
                    "source_id": document["source_bindings"][0]["source_id"],
                    "record_pointer": "/results/0",
                    "record_sha256": core.canonical_sha256(record),
                },
                "identity_source_id": RECORDS[cid][1],
                "evidence_source_ids": record["geometry_source_ids"],
                "reason": f"round44 test {cid}",
            }
            contract["baseline_corrections"].append(entry)
            correction_pins[cid] = core.canonical_sha256(entry)
        contract["batch_id"] = f"round44-test-{self.counter}"
        contract["geometry_identity_reviewed_at"] = "2026-10-10"
        raw = (json.dumps(contract, indent=2) + "\n").encode()
        path = self.root / f"definitions/round44-test-{self.counter}.json"
        path.write_bytes(raw)
        pins = core.ReviewPins(
            hashlib.sha256(raw).hexdigest(),
            source_pins,
            dict(previous.REVIEW_PINS.acceptance_sha256),
            correction_pins,
        )
        return path, pins

    def validate(self, records: dict[str, dict]) -> core.ValidatedBatch:
        path, pins = self.contract_for(records)
        return core.validate_batch(path, pins, root=self.root)

    def rejected(self, records: dict[str, dict], message: str) -> None:
        with self.assertRaisesRegex(core.DraftValidationError, re.escape(message)):
            self.validate(records)

    def with_record(self, cid: str, mutate) -> dict[str, dict]:
        document = deepcopy(self.records[cid])
        mutate(document)
        return {cid: document}

    # Combined checkpoint ------------------------------------------------

    def test_record_files_are_the_reviewed_bytes(self) -> None:
        expected = {
            RDH2: (52458, "c9ac6c72ad76d539d82b58249e009ef55f1a83db02cd18ac116700d91879c78e"),
            RCJM1: (60882, "57e0f5762b73e8b1222e4657cacb0a4777818a17c54db08283cd16a0b7988350"),
        }
        for cid, (path, _) in RECORDS.items():
            raw = (ROOT / path).read_bytes()
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), expected[cid], cid)
            through = json.loads(raw)["supersedes"]["inherited_unchanged_through"]
            self.assertEqual(through["release_path"], THIRTY_SIXTH)

    def test_two_corrections_change_only_enumerated_bytes(self) -> None:
        batch = self.validate(self.records)
        files, manifest = core._payloads(batch)
        self.assertEqual(manifest["counts"], {
            "physical_sites": 200, "projects": 203, "countries": 46, "non_us_sites": 134,
            "evidence": 928, "official_boundary_projects": 5,
            "reviewed_site_locator_projects": 195, "host_estate_context_projects": 3,
        })
        before = ROOT / THIRTY_SIXTH
        for name, key in (("projects.csv", "project_stable_key"), ("sites.csv", "physical_site_stable_key")):
            current = {row[key]: row for row in csv.DictReader(files[name].decode().splitlines())}
            special = {
                (doc["results"][0]["project_stable_key"] if name == "projects.csv"
                 else doc["results"][0]["parent_campus_stable_key"]): doc["exact_row_deltas"][name]["changed"]
                for doc in self.records.values()
            }
            for row in table(before / name):
                changed = {f: [v, current[row[key]][f]] for f, v in row.items() if current[row[key]][f] != v}
                self.assertEqual(changed, special.get(row[key], {}), row[key])
                for field in ("latitude", "longitude", "geometry_json", "geometry_type"):
                    self.assertEqual(row[field], current[row[key]][field])
        evidence = {row["evidence_id"]: row for row in csv.DictReader(files["evidence.csv"].decode().splitlines())}
        dropped = [i for ids in SUPERSEDED.values() for i in ids]
        self.assertFalse(set(dropped) & set(evidence))
        for row in table(before / "evidence.csv"):
            if row["evidence_id"] in dropped:
                continue
            changed = {f for f, v in row.items() if evidence[row["evidence_id"]][f] != v}
            self.assertEqual(changed, {"project_ids_json"} if row["evidence_id"] == SHARED_CRS else set())
        added = {item["evidence_id"] for doc in self.records.values()
                 for item in doc["exact_row_deltas"]["evidence.csv"]["added"]}
        self.assertEqual(len(added), 6)
        self.assertEqual(set(evidence) - {r["evidence_id"] for r in table(before / "evidence.csv")}, added)
        old = json.loads((before / "sites.geojson").read_bytes())["features"]
        new = json.loads(files["sites.geojson"])["features"]
        self.assertEqual([i for i, (a, b) in enumerate(zip(old, new)) if a != b], [81, 91])
        self.assertTrue(all(a["geometry"] == b["geometry"] for a, b in zip(old, new)))
        report = json.loads(files["selection-report.json"])
        exceptions = {row["physical_site_stable_key"]: row["geometry_intersects_site_keys"]
                      for row in report["locator_exceptions"]["projects"]}
        self.assertEqual(exceptions[CGK_SITE], [STT_SITE])
        self.assertEqual({k: v for k, v in exceptions.items() if k != CGK_SITE},
                         {doc["results"][0]["parent_campus_stable_key"]: [] for doc in self.records.values()})
        readme = files["README.md"].decode()
        # B6: the one shared CRS row is counted once, with its three associations.
        self.assertIn("the enumerated fields of 3 re-scoped project rows, 3 site rows and 3 features; "
                      "4 superseded evidence rows dropped; and 1 shared evidence row gaining only "
                      "3 corrected project associations. ", readme)

    def test_report_names_additional_superseded_rows_only_when_present(self) -> None:
        files, _ = core._payloads(self.validate(self.records))
        report = {item["correction_id"]: item for item in json.loads(files["selection-report.json"])["baseline_corrections"]}
        self.assertEqual(report[RCJM1]["superseded_record"]["additional_evidence_ids"], SUPERSEDED[RCJM1][1:])
        self.assertEqual(report[RCJM1]["evidence_rows"]["removed"], SUPERSEDED[RCJM1])
        for cid in ("cgk-host-estate-locator-rescope-v1", RDH2):
            self.assertNotIn("additional_evidence_ids", report[cid]["superseded_record"])

    def test_each_correction_alone_has_its_own_count_effect(self) -> None:
        for cid, net in ((RDH2, 1), (RCJM1, 2)):
            batch = self.validate({cid: self.records[cid]})
            (item,) = [c for c in batch.baseline_corrections if c["correction_id"] == cid]
            self.assertEqual(item["count_effect"]["evidence"], net)
            self.assertEqual(item["count_effect"]["reviewed_site_locator_projects"], -1)
            self.assertEqual(item["count_effect"]["host_estate_context_projects"], 1)

    # B1 publication value ----------------------------------------------

    def test_b1_only_null_equals_a_frozen_empty_publication_value(self) -> None:
        frozen = {
            "kind": "official_record", "source_url": "https://example.test/frozen",
            "publisher": "Fixture", "source_family": "fixture", "license": "fixture",
            "attribution": "Fixture", "published_at": "", "retrieved_at": "2026-07-20",
            "content_hash": "0" * 64,
        }
        reused = {**frozen, "published_at": None}
        core._reused_capture(reused, frozen, {})
        for reused_value, frozen_value in (("2026-01-01", ""), (None, "2026-01-01"), ("", None)):
            with self.subTest(reused=reused_value, frozen=frozen_value):
                with self.assertRaisesRegex(core.DraftValidationError, "not the reused frozen capture"):
                    core._reused_capture(
                        {**frozen, "published_at": reused_value},
                        {**frozen, "published_at": frozen_value},
                        {},
                    )
        # Only that pair, only for published_at, and only in that direction.
        self.assertTrue(core._same_capture_value("published_at", None, ""))
        self.assertFalse(core._same_capture_value("published_at", "", None))
        self.assertFalse(core._same_capture_value("published_at", None, "2026-01-01"))
        self.assertFalse(core._same_capture_value("retrieved_at", None, ""))
        self.assertFalse(core._same_capture_value("content_hash", None, ""))
        # A reused empty string never reaches the comparison: curated evidence
        # needs null or nonempty publication text.
        evidence = {**reused, "key": "fixture", "title": "Fixture", "published_at": ""}
        with self.assertRaisesRegex(core.DraftValidationError, "publication date must be nonempty text"):
            core._source_evidence(evidence, "fixture", inherited_date_only_retrieval=True)

    # B2 additional superseded rows -------------------------------------

    def test_b2_additional_superseded_rows_fail_closed(self) -> None:
        def no_declaration(doc: dict) -> None:
            del doc["supersedes"]["additional_superseded_evidence"]

        def no_frozen_row(doc: dict) -> None:
            del doc["supersedes"]["frozen_baseline_rows"]["additional_evidence_csv"]

        def replacement_is_primary(doc: dict) -> None:
            doc["supersedes"]["additional_superseded_evidence"][0]["replacement_source_id"] = (
                doc["source_bindings"][0]["source_id"]
            )

        def keeps_second_row(doc: dict) -> None:
            doc["exact_row_deltas"]["evidence.csv"]["removed"].pop()

        def no_capture_invariant(doc: dict) -> None:
            del doc["preservation_invariants"]["additional_superseded_captures_unchanged"]

        def wrong_capture_hash(doc: dict) -> None:
            doc["preservation_invariants"]["additional_superseded_captures_unchanged"][0][
                "raw_evidence_body_sha256_unchanged"] = "0" * 64

        def wrong_version(doc: dict) -> None:
            doc["preservation_invariants"]["additional_superseded_captures_unchanged"][0][
                "osm_way_version_unchanged"] = 4

        def replacement_differs(doc: dict) -> None:
            doc["evidence"][1]["content_hash"] = "0" * 64

        def points_at_primary(doc: dict) -> None:
            doc["supersedes"]["additional_superseded_evidence"][0]["evidence_pointer"] = "/source_documents/2"

        cases = {
            no_declaration: "additional superseded evidence differs from the additional frozen rows",
            no_frozen_row: "not solely this project's geometry evidence",
            replacement_is_primary: "distinct replacement geometry sources",
            keeps_second_row: "evidence delta must remove exactly the superseded row",
            no_capture_invariant: "additional_superseded_captures_unchanged",
            wrong_capture_hash: "additional_superseded_captures_unchanged",
            wrong_version: "additional_superseded_captures_unchanged",
            replacement_differs: "not the reused frozen capture",
            points_at_primary: "additional frozen evidence row is not its superseded record",
        }
        for mutate, message in cases.items():
            with self.subTest(mutate.__name__):
                self.rejected(self.with_record(RCJM1, mutate), message)

    def test_b2_single_capture_records_keep_the_v2_shape(self) -> None:
        def extra(doc: dict) -> None:
            doc["supersedes"]["additional_superseded_evidence"] = []

        self.rejected(self.with_record(RDH2, extra), "nonempty list")

        def extra_frozen(doc: dict) -> None:
            doc["supersedes"]["frozen_baseline_rows"]["additional_evidence_csv"] = []

        self.rejected(self.with_record(RDH2, extra_frozen), "nonempty list")

    # B3 exterior anchor -------------------------------------------------

    def test_b3_exterior_anchor_must_be_declared_and_only_then(self) -> None:
        def undeclared(doc: dict) -> None:
            del doc["preservation_invariants"]["display_anchor_outside_geometry"]

        self.rejected(self.with_record(RCJM1, undeclared), "display_anchor_outside_geometry")

        def declared_false(doc: dict) -> None:
            doc["preservation_invariants"]["display_anchor_outside_geometry"] = False

        self.rejected(self.with_record(RCJM1, declared_false), "display_anchor_outside_geometry")

        def declared_inside(doc: dict) -> None:
            doc["preservation_invariants"]["display_anchor_outside_geometry"] = True

        self.rejected(self.with_record(RDH2, declared_inside), "display_anchor_outside_geometry")
        acceptance_like = deepcopy(self.records[RCJM1]["results"][0])
        acceptance_like["location_basis"] = "community_named_site_feature"
        acceptance_like["semantics"].update(
            geometry_source_entity_kind="campus", geometry_use_scope="campus_locator"
        )
        with self.assertRaisesRegex(core.DraftValidationError, "display anchor is outside"):
            core._geometry(acceptance_like)

    # B4 date-only frozen identity evidence ------------------------------

    def test_b4_date_only_identity_evidence_must_equal_the_frozen_row(self) -> None:
        baseline = core._load_baseline(ROOT)
        binding = self.records[RCJM1]["required_unchanged_identity_bindings"][0]
        self.assertEqual(binding["source_id"], RECORDS[RCJM1][1])
        source_id, resolved = core._resolve_binding(binding, ROOT, baseline)
        self.assertTrue(core._date_only(resolved["records"]["evidence"]["retrieved_at"]))
        key = self.records[RCJM1]["results"][0]["project_stable_key"]
        site = self.records[RCJM1]["results"][0]["parent_campus_stable_key"]
        project = next(row for row in baseline["projects"] if row["project_stable_key"] == key)
        accepted = core._frozen_status_identity(resolved, project, key, site, baseline, source_id)
        self.assertEqual(accepted["evidence_id"], project["status_evidence_id"])
        moved = deepcopy(resolved)
        moved["records"]["evidence"]["retrieved_at"] = "2026-08-24"
        with self.assertRaisesRegex(core.DraftValidationError, "identity binding is not the frozen status evidence"):
            core._frozen_status_identity(moved, project, key, site, baseline, source_id)
        # The real record, whose identity evidence keeps that date-only retrieval, validates.
        self.validate({RCJM1: self.records[RCJM1]})

    # B5 inherited-through rows located by bytes ------------------------

    def test_b5_inherited_through_rows_are_located_by_bytes_not_lines(self) -> None:
        through = self.records[RCJM1]["supersedes"]["inherited_unchanged_through"]
        self.assertEqual(through["release_path"], THIRTY_SIXTH)
        lines = (ROOT / THIRTY_SIXTH / "evidence.csv").read_bytes().split(b"\n")
        self.assertTrue(lines[213].startswith(SUPERSEDED[RCJM1][0].encode()))  # moved from v0.17 line 215
        self.validate({RCJM1: self.records[RCJM1]})
        for label, edit in (
            ("changed", lambda ls: ls[:213] + [ls[213].replace(b"OpenStreetMap way", b"OpenStreetMap  way")] + ls[214:]),
            ("duplicated", lambda ls: ls[:214] + [ls[213]] + ls[214:]),
        ):
            with self.subTest(label):
                release = f"verified_construction_core/2026-08-20-v0.18-draft-round44-{label}"
                target = self.root / release
                shutil.copytree(self.root / THIRTY_SIXTH, target)
                edited = b"\n".join(edit(lines))
                self.assertNotEqual(edited, b"\n".join(lines))
                (target / "evidence.csv").write_bytes(edited)
                manifest = json.loads((target / "manifest.json").read_bytes())
                manifest["files"]["evidence.csv"] = {"bytes": len(edited), "sha256": hashlib.sha256(edited).hexdigest()}
                manifest_raw = core.core._json_bytes(manifest)
                (target / "manifest.json").write_bytes(manifest_raw)

                def rename(doc: dict, release=release, digest=hashlib.sha256(manifest_raw).hexdigest()) -> None:
                    doc["supersedes"]["inherited_unchanged_through"].update(
                        release_path=release, manifest_sha256=digest
                    )

                self.rejected(self.with_record(RCJM1, rename), "inherited evidence row changed after v0.17")


class EarlierCheckpointReproductionTests(unittest.TestCase):
    """Rules B1-B6 and withdrawals must leave every committed checkpoint byte-reproducible."""

    def test_every_registered_checkpoint_still_validates(self) -> None:
        script = (ROOT / "scripts/build_expansion_200_draft.py").read_text(encoding="utf-8")
        modules = re.findall(r'"[a-z-]+": (expansion_200_[a-z_]+),', script)
        self.assertGreaterEqual(len(modules), 37)
        for name in modules:
            module = importlib.import_module(f"datacenter_atlas.{name}")
            with self.subTest(name):
                core.validate_draft(module.draft_path(ROOT), module.contract_path(ROOT), module.REVIEW_PINS, root=ROOT)


if __name__ == "__main__":
    unittest.main()
