from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from datacenter_atlas.peeringdb_assessment import (
    PeeringDBAssessmentError,
    audit_scrutica_peeringdb_rights,
    validate_assessment_bundle,
    validate_assessment_document,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PINNED_ASSESSMENT = (
    PROJECT_ROOT / "source_assessments" / "peeringdb-2026-07-18-v1"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture_release(path: Path, *, permission: bool = False) -> None:
    path.mkdir()
    database = path / "atlas.sqlite"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE evidence (
            id TEXT PRIMARY KEY,
            source_family TEXT NOT NULL,
            license TEXT NOT NULL,
            attribution TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        );
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            created_from_evidence_id TEXT NOT NULL
        );
        CREATE TABLE entity_snapshots (entity_id TEXT, evidence_id TEXT);
        CREATE TABLE capacity_estimates (entity_id TEXT, evidence_id TEXT);
        CREATE TABLE lifecycle_observations (entity_id TEXT, evidence_id TEXT);
        CREATE TABLE operating_model_observations (entity_id TEXT, evidence_id TEXT);
        CREATE TABLE workload_observations (entity_id TEXT, evidence_id TEXT);
        CREATE TABLE facilities (entity_id TEXT);
        """
    )
    metadata = {
        "data_source": "peeringdb",
        "upstream_source_url": "https://www.peeringdb.com/fac/1",
    }
    if permission:
        metadata["peeringdb_permission"] = {
            "approval_status": "approved",
            "bulk_redistribution": True,
            "document_sha256": "a" * 64,
            "granted_by": "PeeringDB",
            "permission_reference": "fixture approval",
        }
    connection.executemany(
        "INSERT INTO evidence VALUES (?, ?, ?, ?, ?)",
        (
            (
                "ev-pdb",
                "scrutica",
                "CC-BY-SA-4.0",
                "Scrutica data, licensed under CC BY-SA 4.0",
                json.dumps(metadata, sort_keys=True),
            ),
            (
                "ev-osm",
                "scrutica",
                "CC-BY-SA-4.0",
                "Scrutica data, licensed under CC BY-SA 4.0",
                json.dumps({"data_source": "openstreetmap"}, sort_keys=True),
            ),
        ),
    )
    connection.executemany(
        "INSERT INTO entities VALUES (?, ?)",
        (("entity-pdb", "ev-pdb"), ("entity-osm", "ev-osm")),
    )
    for table in (
        "entity_snapshots",
        "lifecycle_observations",
        "operating_model_observations",
    ):
        connection.executemany(
            f"INSERT INTO {table} VALUES (?, ?)",  # noqa: S608
            (("entity-pdb", "ev-pdb"), ("entity-osm", "ev-osm")),
        )
    connection.executemany(
        "INSERT INTO facilities VALUES (?)", (("entity-pdb",), ("entity-osm",))
    )
    connection.commit()
    connection.close()

    attribution = path / "ATTRIBUTION.txt"
    attribution.write_text(
        "Scrutica data, licensed under CC BY-SA 4.0\n", encoding="utf-8"
    )
    files = {
        item.name: {"bytes": item.stat().st_size, "sha256": _sha256(item)}
        for item in (database, attribution)
    }
    (path / "manifest.json").write_text(
        json.dumps({"files": files}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


class PeeringDBAssessmentTests(unittest.TestCase):
    def test_pinned_metadata_only_assessment_validates(self) -> None:
        document = validate_assessment_bundle(PINNED_ASSESSMENT)
        self.assertEqual(
            document["atlas_decision"]["status"],
            "blocked_pending_written_permission",
        )
        self.assertFalse(document["atlas_decision"]["publication_eligible"])
        self.assertEqual(
            document["scrutica_upstream_rights_conflict"][
                "peeringdb_evidence_rows"
            ],
            1548,
        )

    def test_assessment_rejects_rights_relaxation(self) -> None:
        document = json.loads(
            (PINNED_ASSESSMENT / "assessment.json").read_text(encoding="utf-8")
        )
        relaxed = deepcopy(document)
        relaxed["rights_assessment"]["direct_release_permitted"] = True
        with self.assertRaisesRegex(PeeringDBAssessmentError, "fail closed"):
            validate_assessment_document(relaxed)

    def test_bundle_rejects_retained_raw_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "assessment"
            shutil.copytree(PINNED_ASSESSMENT, copied)
            (copied / "facility-response.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(PeeringDBAssessmentError, "file set"):
                validate_assessment_bundle(copied)

    def test_scrutica_audit_finds_upstream_license_conflict_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            _write_fixture_release(release)
            before = _sha256(release / "atlas.sqlite")
            result = audit_scrutica_peeringdb_rights(release)
            after = _sha256(release / "atlas.sqlite")
        self.assertEqual(before, after)
        self.assertEqual(result["peeringdb_evidence_rows"], 1)
        self.assertEqual(result["peeringdb_entity_rows"], 1)
        self.assertEqual(result["cc_by_sa_labeled_peeringdb_evidence_rows"], 1)
        self.assertEqual(result["permission_evidence_recorded_rows"], 0)
        self.assertEqual(result["dependent_rows"]["entity_snapshots"], 1)
        self.assertEqual(result["dependent_rows"]["capacity_estimates"], 0)
        self.assertTrue(result["conflict_detected"])
        self.assertFalse(result["relabel_alone_is_sufficient"])

    def test_recorded_permission_removes_detected_conflict_but_not_policy_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            release = Path(temporary) / "release"
            _write_fixture_release(release, permission=True)
            result = audit_scrutica_peeringdb_rights(release)
        self.assertEqual(result["permission_evidence_recorded_rows"], 1)
        self.assertFalse(result["conflict_detected"])
        self.assertFalse(result["publication_eligible"])


if __name__ == "__main__":
    unittest.main()
