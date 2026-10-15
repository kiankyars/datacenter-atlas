"""Narrative prose stays pinned to the exact current project and evidence."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import uuid

from datacenter_atlas.project_narratives import (
    ProjectNarrativeError, _canonical_sha256, load_project_narratives,
)


class ProjectNarrativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = {"project_id": "p", "project_stable_key": "curated:one",
                        "last_observed_physical_status": "operational", "status_as_of": "2026-10-01",
                        "project_details": [], "geometry_evidence_id": "geometry"}
        self.atlas = SimpleNamespace(projects=[self.project], evidence_by_id={}, evidence_by_project={"p": []})
        self.version = SimpleNamespace(path=self.root / "datasets/current", manifest={}, manifest_sha256="current")
        self.provenance = {}

    def load(self, versions=None, provenances=None):
        return load_project_narratives(self.root, versions or [self.version], self.version,
                                      self.atlas, lambda version, name:
                                      (provenances or {}).get(version.path, self.provenance))

    def add_source(self, key, *, curated=False, text="Useful fact.", url=None, digest=None,
                   roles=None, projects=None, kind="company_disclosure"):
        source = {"key": key, "id": key, "source_url": url or f"https://example.com/{key}",
                  "content_hash": digest or hashlib.sha256(key.encode()).hexdigest(),
                  "summary": text, "excerpt": text, "kind": kind}
        identifier = str(uuid.uuid5(
            uuid.UUID("aa3d9079-c7f8-4a77-84d9-75ae2097549f") if curated else uuid.NAMESPACE_URL,
            (f"evidence|curated-official|{key}|{source['content_hash']}" if curated
             else f"{source['source_url']}#{source['content_hash']}")))
        evidence = {**source, "evidence_id": identifier, "project_ids": ["p"] if projects is None else projects,
                    "roles": ["context:identity"] if roles is None else roles}
        self.atlas.evidence_by_id[identifier] = evidence
        if "p" in evidence["project_ids"]:
            self.atlas.evidence_by_project["p"].append(evidence)
        return source, identifier

    def write_pin(self, path, document):
        raw = (json.dumps(document, ensure_ascii=False) + "\n").encode()
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return {"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def modern(self, source, identifier, *, context=None, status_date="2026-10-01"):
        self.project["status_evidence_id"] = identifier
        self.version.manifest["files"] = {"review-provenance.json": {}}
        self.provenance = {"source_projections": {source["id"]: source}, "update": {"additions": [{
            "project_stable_key": "curated:one", "status": {
                "value": "operational", "as_of": status_date, "source_id": source["id"],
                "summary": "Operating campus; the exact opening day is unknown."},
            "context_source_ids": context or [],
        }]}}

    def test_minimal_fixture_without_provenance_or_stable_key(self):
        self.project.pop("project_stable_key")
        self.assertEqual(self.load(), {})

    def test_modern_status_context_and_caveats_without_mutation(self):
        source, identifier = self.add_source("status", roles=["physical_status"])
        self.modern(source, identifier, context=["context", "map"])
        context, cid = self.add_source("context", text="Building A opened in May 2006; no exact day is established.")
        geo, gid = self.add_source("map", roles=["geometry"], kind="openstreetmap")
        self.provenance["source_projections"].update(context=context, map=geo)
        self.project["geometry_evidence_id"] = gid
        before = copy.deepcopy(self.atlas)
        result = self.load()["p"]
        self.assertEqual(result["status"]["evidence_id"], identifier)
        self.assertIn("exact opening day is unknown", result["status"]["text"])
        self.assertEqual(result["context"], [{"text": context["summary"], "evidence_id": cid}])
        self.assertEqual(vars(self.atlas), vars(before))

    def test_stale_status_and_unassociated_source_never_become_leads(self):
        source, identifier = self.add_source("status", roles=["physical_status"])
        self.modern(source, identifier, status_date="2026-09-01")
        self.assertEqual(self.load(), {})
        self.provenance["update"]["additions"][0]["status"]["as_of"] = "2026-10-01"
        self.atlas.evidence_by_id[identifier]["project_ids"] = ["another-project"]
        self.assertEqual(self.load(), {})

    def test_structured_record_can_receive_new_current_status_but_not_duplicate_context(self):
        source, identifier = self.add_source("status", roles=["physical_status"])
        self.modern(source, identifier, context=["context"])
        context, _ = self.add_source("context")
        self.provenance["source_projections"]["context"] = context
        self.project["project_details"] = [{"summary": "Original imported record."}]
        result = self.load()["p"]
        self.assertIsNotNone(result["status"])
        self.assertEqual(result["context"], [])

    def test_shared_document_context_is_project_scoped_and_preserves_other_prose(self):
        other_project = {**self.project, "project_id": "q", "project_stable_key": "curated:two"}
        self.atlas.projects.append(other_project)
        self.atlas.evidence_by_project["q"] = []
        shared, sid = self.add_source("register", projects=["p", "q"],
                                      text="Campus Two is listed at 27 East Street on page 16.")
        other, oid = self.add_source("equipment", text="Two feeds and redundant UPS; no IT-load figure is reported.")
        scoped = ("Campus One is listed at 6 West Street on page 14. "
                  "The certificate is valid from November 2024 through November 2027; "
                  "these dates are not construction, opening or current-operation observations.")
        self.version.manifest["files"] = {"review-provenance.json": {}}
        self.provenance = {"source_projections": {"register": shared, "equipment": other}, "update": {
            "additions": [
                {"project_stable_key": "curated:one", "context_source_ids": ["register", "equipment"]},
                {"project_stable_key": "curated:two", "context_source_ids": ["register"]},
            ],
            "context_updates": [{"project_stable_key": "curated:one",
                                 "source_ids": ["register"], "summary": scoped}],
        }}
        before = copy.deepcopy((vars(self.atlas), self.provenance))
        result = self.load()
        self.assertEqual(result["p"]["context"], [
            {"text": scoped, "evidence_id": sid},
            {"text": other["summary"], "evidence_id": oid},
        ])
        self.assertEqual(result["q"]["context"], [{"text": shared["summary"], "evidence_id": sid}])
        self.assertEqual((vars(self.atlas), self.provenance), before)

    def test_newest_scoped_context_wins_across_lineage_without_generic_duplicates(self):
        shared, sid = self.add_source("register", text="Generic document excerpt for another campus.")
        base = SimpleNamespace(path=self.root / "datasets/base", manifest={
            "files": {"review-provenance.json": {}}}, manifest_sha256="base")
        self.version.manifest.update(base_dataset="datasets/base", base_manifest_sha256="base",
                                     files={"review-provenance.json": {}})
        newer = "Reviewed correction: this campus occupies two floors; whole-building area is excluded."
        older = "Earlier review identified this campus in the building."
        provenances = {
            self.version.path: {"source_projections": {"register": shared}, "update": {
                "context_updates": [{"project_stable_key": "curated:one", "source_ids": ["register"],
                                     "summary": newer}]}},
            base.path: {"source_projections": {"register": shared}, "update": {
                "additions": [{"project_stable_key": "curated:one", "context_source_ids": ["register"]}],
                "context_updates": [{"project_stable_key": "curated:one", "source_ids": ["register"],
                                     "summary": older}]}},
        }
        before = copy.deepcopy(provenances)
        result = self.load([self.version, base], provenances)["p"]
        self.assertEqual(result["context"], [{"text": newer, "evidence_id": sid}])
        self.assertEqual(provenances, before)

    def test_current_status_source_can_supply_context_without_reviving_stale_or_map_evidence(self):
        source, identifier = self.add_source("interview", roles=["physical_status"])
        self.modern(source, identifier)
        stale, _ = self.add_source("old-interview", roles=["physical_status"])
        geo, gid = self.add_source("map", roles=["geometry"], kind="openstreetmap")
        self.project["geometry_evidence_id"] = gid
        self.provenance["source_projections"].update({"old-interview": stale, "map": geo})
        context = ("The operator describes groundwater-assisted cooling and says the facilities are not "
                   "designed for high-density GPU workloads. Publication is October 1; interview day is unknown.")
        self.provenance["update"]["context_updates"] = [
            {"project_stable_key": "curated:one", "source_ids": ["interview"], "summary": context},
            {"project_stable_key": "curated:one", "source_ids": ["old-interview"], "summary": "Old claim."},
            {"project_stable_key": "curated:one", "source_ids": ["map"], "summary": "Geometry metadata."},
        ]
        result = self.load()["p"]
        self.assertEqual(result["status"]["text"], "Operating campus; the exact opening day is unknown.")
        self.assertEqual(result["status"]["evidence_id"], identifier)
        self.assertEqual(result["context"], [{"text": context, "evidence_id": identifier}])

    def test_multisource_update_keeps_each_complete_source_summary(self):
        first, fid = self.add_source("first", text="Building A supports 200 racks as of 2024; occupancy is unknown.")
        second, sid = self.add_source("second", text="Building B supports 300 racks as of 2024; this is not IT power.")
        self.version.manifest["files"] = {"review-provenance.json": {}}
        self.provenance = {"source_projections": {"first": first, "second": second}, "update": {
            "context_updates": [{"project_stable_key": "curated:one", "source_ids": ["first", "second"],
                                 "summary": "Review note covering both sources."}]}}
        self.assertEqual(self.load()["p"]["context"], [
            {"text": first["summary"], "evidence_id": fid},
            {"text": second["summary"], "evidence_id": sid},
        ])

    def test_curated_exact_id_prevents_shared_page_excerpt_cross_wiring(self):
        one, oid = self.add_source("one", curated=True, text="Only campus One is operational.",
                                   url="https://example.com/campuses", digest="a" * 64,
                                   roles=["physical_status"])
        two, _ = self.add_source("two", curated=True, text="Campus Two is under construction.",
                                 url=one["source_url"], digest=one["content_hash"], projects=["q"])
        self.project["status_evidence_id"] = oid
        pin = self.write_pin("sources/campuses.json", {"evidence": [one, two]})
        self.version.manifest["portable_source_inputs"] = [pin]
        result = self.load()["p"]
        self.assertEqual(result["status"]["text"], one["excerpt"])
        self.assertEqual(result["context"], [])

    def test_exact_pointer_and_canonical_hash(self):
        source, identifier = self.add_source("unicode", curated=True, text="Keihanna ラボ; campus scope only.")
        self.project["status_evidence_id"] = identifier
        pin = self.write_pin("sources/pointer.json", {"evidence": [source]})
        pin.update(evidence_pointer="/evidence/0", evidence_sha256=_canonical_sha256(source))
        self.version.manifest["files"] = {"review-provenance.json": {}}
        self.provenance = {"source_inputs": [pin]}
        self.assertEqual(self.load()["p"]["status"]["text"], source["excerpt"])
        pin["evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(ProjectNarrativeError, "evidence checksum"):
            self.load()

    def test_tampered_source_and_escaping_path_fail_closed(self):
        source, identifier = self.add_source("one", curated=True)
        self.project["status_evidence_id"] = identifier
        pin = self.write_pin("sources/one.json", {"evidence": [source]})
        self.version.manifest["portable_source_inputs"] = [pin]
        (self.root / pin["path"]).write_text("{}")
        with self.assertRaisesRegex(ProjectNarrativeError, "checksum"):
            self.load()
        pin["path"] = "sources/../../outside.json"
        with self.assertRaisesRegex(ProjectNarrativeError, "unsafe"):
            self.load()

    def test_reviewed_artifacts_must_be_shipped_and_hash_verified(self):
        source, identifier = self.add_source("legacy", curated=True, roles=["physical_status"])
        self.project["status_evidence_id"] = identifier
        pin = self.write_pin("source_artifacts/local-only.json", {"evidence": [source]})
        self.version.manifest["portable_source_inputs"] = [pin]
        contract = self.write_pin("definitions/review.json", {"acceptances": [{
            "source_input_path": pin["path"], "source_input_sha256": pin["sha256"]}]})
        self.version.manifest.update(definition_paths={"reviewed_sites": contract["path"]},
                                     review_definition_sha256=contract["sha256"])
        self.assertEqual(self.load()["p"]["status"]["text"], source["excerpt"])
        (self.root / pin["path"]).unlink()
        with self.assertRaisesRegex(ProjectNarrativeError, "missing narrative input"):
            self.load()

    def test_legacy_review_chain_pins_portable_sources(self):
        source, identifier = self.add_source("legacy", curated=True, roles=["physical_status"])
        self.project["status_evidence_id"] = identifier
        pin = self.write_pin("sources/legacy.json", {"evidence": [source]})
        old = self.write_pin("definitions/old.json", {"acceptances": [{
            "source_input_path": pin["path"], "source_input_sha256": pin["sha256"]}]})
        new = self.write_pin("definitions/new.json", {"base_contract": old, "acceptances": []})
        self.version.manifest.update(definition_paths={"reviewed_sites": new["path"]},
                                     review_definition_sha256=new["sha256"])
        self.assertEqual(self.load()["p"]["status"]["text"], source["excerpt"])
        (self.root / old["path"]).write_text("{}")
        with self.assertRaisesRegex(ProjectNarrativeError, "checksum"):
            self.load()

    def test_lineage_hash_is_required(self):
        base = SimpleNamespace(path=self.root / "datasets/base", manifest={}, manifest_sha256="base")
        self.version.manifest.update(base_dataset="datasets/base", base_manifest_sha256="incorrect")
        with self.assertRaisesRegex(ProjectNarrativeError, "base manifest"):
            self.load([self.version, base])
        self.version.manifest["base_manifest_sha256"] = "base"
        self.assertEqual(self.load([self.version, base]), {})


if __name__ == "__main__":
    unittest.main()
