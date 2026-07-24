from __future__ import annotations

import copy
import csv
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any, Iterable
import unittest
from unittest.mock import patch

from datacenter_atlas.construction_master import _release_row
from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.release import build_release_documents
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T07:24:19Z"
AS_OF_DATE = "2026-03-31"
EVIDENCE_KEY = (
    "vnet-1q26-ir-presentation-wholesale-construction-pdf-"
    "captured-2026-07-20"
)
PDF_SHA256 = "02ffcae20b92eefb1d8f70fbd6eb15f1b0213eb356713cac23b676c0b10cea0a"
V1_TEST = "test_curated_vnet_q1_2026.py"
V1_TEST_BYTES = 22_562
V1_TEST_SHA256 = "7b34e6d1229b3a3daf66c4ae2fff476b437a1e3a8642492b5cb04331cc1d0966"
V1_REGIONAL_ANCHORS = {
    "curated:vnet-yangtze-river-delta-regional-wholesale-anchor",
    "curated:vnet-greater-beijing-area-regional-wholesale-anchor",
}

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "e-js03b": {
        "code": "E-JS03B",
        "region": "Yangtze River Delta",
        "mw": 44,
        "v1_bytes": 12_134,
        "v1_sha256": "acfae78267f91e6820b9f4d22a35fa3a828e4c9d53ae17b8ed58042a4f72330b",
        "v2_bytes": 12_099,
        "v2_sha256": "fca0e08c8a0348e54596d9b3009d3b61a4602bfb44e143530827d338f69cf933",
    },
    "n-hb02": {
        "code": "N-HB02",
        "region": "Greater Beijing Area",
        "mw": 59,
        "v1_bytes": 12_137,
        "v1_sha256": "6e0a83110457229986e6ab703954c221b5d6904b4a480c22dc9b65a1e05d79a6",
        "v2_bytes": 12_096,
        "v2_sha256": "d564746bc94cc05f93344ea427fce48796de9b6747bcf8b9073e2e1aef0d2522",
    },
    "n-hb03": {
        "code": "N-HB03",
        "region": "Greater Beijing Area",
        "mw": 4,
        "v1_bytes": 12_137,
        "v1_sha256": "1bfdc6e845755e11871c882c4b80292f53f2407c6cdd25c30f69c504dfce5a01",
        "v2_bytes": 12_096,
        "v2_sha256": "06fe2a9d44ce961c06e8ea168d5a444fb3aec5da248cbbc178abe693e0c8e7c7",
    },
    "n-hb04": {
        "code": "N-HB04",
        "region": "Greater Beijing Area",
        "mw": 21,
        "v1_bytes": 12_137,
        "v1_sha256": "c89b4c2b0f93307e85f4fa5cb187c4157552c7d15eaea11587a59da4883fcfe9",
        "v2_bytes": 12_096,
        "v2_sha256": "d109533127851b157df10ad017b552ea50ca82d6571386d7ae70a1efaf210854",
    },
    "n-or01": {
        "code": "N-OR01",
        "region": "Greater Beijing Area",
        "mw": 9,
        "v1_bytes": 12_137,
        "v1_sha256": "b5963e09b58ec96fcd6065959ee9ee7b0c900ac15baa40dad99f813f543f7a4f",
        "v2_bytes": 12_096,
        "v2_sha256": "698b8cf3ec1ed5b578589dc1b9c34d92e30ab19305e0f242825862473447eb8f",
    },
    "n-or02a": {
        "code": "N-OR02A",
        "region": "Greater Beijing Area",
        "mw": 101,
        "v1_bytes": 12_139,
        "v1_sha256": "0f7f78b11809e2d926df5820e6999b7dd843278fc6454a0249fb7dae7efda697",
        "v2_bytes": 12_101,
        "v2_sha256": "6645c9853e1c4efe4c366e00086513f3ef7ca10b22c7cff512abca16053e8a82",
    },
    "n-or02b": {
        "code": "N-OR02B",
        "region": "Greater Beijing Area",
        "mw": 65,
        "v1_bytes": 12_139,
        "v1_sha256": "50278632f21512a44c8d9549915f7a7239c6e21e9f5a49d04858802a07609645",
        "v2_bytes": 12_101,
        "v2_sha256": "d84c2febccae8c6c7c871fcd2bca7a2e14462538fa2d5c26b590ba0c3258589b",
    },
    "n-or03": {
        "code": "N-OR03",
        "region": "Greater Beijing Area",
        "mw": 213,
        "v1_bytes": 12_137,
        "v1_sha256": "4a6413620c698fda95ff58b90238b20b4ae474073bfe437b92f80bd5d21f31bb",
        "v2_bytes": 12_096,
        "v2_sha256": "980da0dea024ae56e6f30f855db78c9ce834c2ffc9dc5a024bfe9f8414ede895",
    },
}


def _v1_name(slug: str) -> str:
    return f"curated-official-2026-07-20-vnet-{slug}.json"


def _v2_name(slug: str) -> str:
    return f"curated-official-2026-07-20-vnet-{slug}-v2.json"


def _campus_key(slug: str) -> str:
    return f"curated:vnet-{slug}-locality-scoped-campus"


def _project_key(slug: str) -> str:
    return f"{_campus_key(slug)}:{slug}-under-construction"


V1_SOURCES = tuple(_v1_name(slug) for slug in SOURCE_SPECS)
V2_SOURCES = tuple(_v2_name(slug) for slug in SOURCE_SPECS)
V2_CAMPUS_KEYS = {_campus_key(slug) for slug in SOURCE_SPECS}
V2_PROJECT_KEYS = {_project_key(slug) for slug in SOURCE_SPECS}
SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class VnetQ12026CollisionIsolatedV2Tests(unittest.TestCase):
    def _source_path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._source_path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("VNET v2 curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _build(
        self,
        order: Iterable[str],
        *,
        repetitions: int = 1,
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for _ in range(repetitions):
                    for name in order:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._source_path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                self.assertEqual(validate_database(connection), [])
                return self._state(connection)
            finally:
                connection.close()

    def _counts(self, connection: Any) -> dict[str, int]:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in SEMANTIC_TABLES
        }

    def test_v1_is_untouched_v2_is_hash_pinned_and_v44_excludes_v2(self) -> None:
        v1_test = ROOT / "tests" / V1_TEST
        self.assertEqual(v1_test.stat().st_size, V1_TEST_BYTES)
        self.assertEqual(hashlib.sha256(v1_test.read_bytes()).hexdigest(), V1_TEST_SHA256)

        for slug, spec in SOURCE_SPECS.items():
            with self.subTest(component=slug):
                for version in ("v1", "v2"):
                    name = _v1_name(slug) if version == "v1" else _v2_name(slug)
                    path = self._source_path(name)
                    raw = path.read_bytes()
                    self.assertTrue(path.is_file())
                    self.assertFalse(path.is_symlink())
                    self.assertTrue(stat.S_ISREG(path.stat().st_mode))
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                    self.assertEqual(len(raw), spec[f"{version}_bytes"])
                    self.assertEqual(
                        hashlib.sha256(raw).hexdigest(),
                        spec[f"{version}_sha256"],
                    )
                    document = json.loads(raw)
                    self.assertEqual(
                        raw.decode("utf-8"),
                        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                    )

        v44 = (ROOT / "sources" / "open-seed-2026-07-20-v44.json").read_text(
            encoding="utf-8"
        )
        for name in V2_SOURCES:
            self.assertNotIn(name, v44)

    def test_v2_changes_only_the_three_topology_fields_and_reuses_exact_evidence(self) -> None:
        shared_evidence: dict[str, Any] | None = None
        for slug, spec in SOURCE_SPECS.items():
            with self.subTest(component=slug):
                v1 = self._load(_v1_name(slug))
                v2 = self._load(_v2_name(slug))
                expected = copy.deepcopy(v1)
                expected["campus"]["stable_key"] = _campus_key(slug)
                expected["campus"]["name"] = (
                    f"VNET {spec['code']} Locality-Scoped Technical Campus"
                )
                expected["project"]["stable_key"] = _project_key(slug)
                self.assertEqual(v2, expected)
                self.assertEqual(v2["evidence"], v1["evidence"])
                if shared_evidence is None:
                    shared_evidence = v2["evidence"][0]
                self.assertEqual(v2["evidence"][0], shared_evidence)

        assert shared_evidence is not None
        self.assertEqual(shared_evidence["key"], EVIDENCE_KEY)
        self.assertEqual(shared_evidence["content_hash"], PDF_SHA256)
        self.assertEqual(shared_evidence["retrieved_at"], RETRIEVED_AT)
        metadata = shared_evidence["metadata"]
        self.assertEqual(metadata["reporting_period_end"], AS_OF_DATE)
        self.assertEqual(metadata["reported_total_capacity_under_construction_mw"], 516)
        self.assertEqual(metadata["reported_total_capacity_pre_committed_mw"], 443)
        self.assertIn("no normalized capacity rows", metadata["capacity_guardrail"])
        self.assertIn("no exact target date", metadata["rfs_guardrail"])
        self.assertIn("not verified unique physical sites", metadata["site_count_guardrail"])

    def test_exact_eight_component_scopes_have_no_shared_or_regional_parent(self) -> None:
        observed_campuses: set[str] = set()
        observed_projects: set[str] = set()
        for slug, spec in SOURCE_SPECS.items():
            with self.subTest(component=slug):
                document = self._load(_v2_name(slug))
                campus = document["campus"]
                project = document["project"]
                self.assertEqual(campus["stable_key"], _campus_key(slug))
                self.assertEqual(
                    campus["name"],
                    f"VNET {spec['code']} Locality-Scoped Technical Campus",
                )
                self.assertEqual(project["stable_key"], _project_key(slug))
                self.assertEqual(
                    project["name"],
                    f"VNET {spec['code']} Construction Component",
                )
                observed_campuses.add(campus["stable_key"])
                observed_projects.add(project["stable_key"])
                for entity in (campus, project):
                    self.assertEqual(entity["country"], "China")
                    self.assertEqual(entity["address"], f"{spec['region']}, China")
                    self.assertEqual(entity["roles"], {})
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
                    self.assertEqual(entity["as_of_date"], AS_OF_DATE)
                    self.assertEqual(entity["method"], "authoritative_locality")
                    self.assertEqual(entity["confidence"], 0.99)
                self.assertEqual(
                    document["lifecycle"],
                    [
                        {
                            "entity": "project",
                            "value": "under_construction",
                            "evidence_key": EVIDENCE_KEY,
                            "as_of_date": AS_OF_DATE,
                            "method": "authoritative_physical_status_update",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(
                    document["operating_models"],
                    [
                        {
                            "entity": "project",
                            "value": "wholesale_colocation",
                            "evidence_key": EVIDENCE_KEY,
                            "as_of_date": AS_OF_DATE,
                            "method": "company_disclosure",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(document["workloads"], [])
                self.assertEqual(document["capacities"], [])
                component = next(
                    row
                    for row in document["evidence"][0]["metadata"][
                        "components_as_reported"
                    ]
                    if row["normalized_component_code"] == spec["code"]
                )
                self.assertEqual(component["capacity_under_construction_mw"], spec["mw"])

        self.assertEqual(observed_campuses, V2_CAMPUS_KEYS)
        self.assertEqual(observed_projects, V2_PROJECT_KEYS)
        self.assertEqual(len(observed_campuses), 8)
        self.assertEqual(len(observed_projects), 8)
        self.assertTrue(observed_campuses.isdisjoint(observed_projects))
        self.assertTrue(observed_campuses.isdisjoint(V1_REGIONAL_ANCHORS))

    def test_each_v2_source_imports_offline_in_isolation(self) -> None:
        for name in V2_SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._source_path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                    self.assertEqual(
                        self._counts(connection),
                        {
                            "evidence": 1,
                            "entities": 2,
                            "campuses": 1,
                            "facilities": 0,
                            "buildings": 0,
                            "projects": 1,
                            "entity_snapshots": 2,
                            "lifecycle_observations": 1,
                            "operating_model_observations": 1,
                            "workload_observations": 0,
                            "capacity_estimates": 0,
                        },
                    )
                finally:
                    connection.close()

    def test_combined_v2_is_offline_idempotent_order_independent_and_exact(self) -> None:
        forward = self._build(V2_SOURCES)
        reverse = self._build(reversed(V2_SOURCES))
        repeated = self._build(V2_SOURCES, repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)
        self.assertEqual(len(forward["evidence"]), 1)
        self.assertEqual(len(forward["entities"]), 16)
        self.assertEqual(len(forward["campuses"]), 8)
        self.assertEqual(len(forward["projects"]), 8)
        self.assertEqual(len(forward["entity_snapshots"]), 16)
        self.assertEqual(len(forward["lifecycle_observations"]), 8)
        self.assertEqual(len(forward["operating_model_observations"]), 8)
        self.assertEqual(forward["facilities"], ())
        self.assertEqual(forward["buildings"], ())
        self.assertEqual(forward["workload_observations"], ())
        self.assertEqual(forward["capacity_estimates"], ())

    def test_v2_adds_exactly_16_entities_after_v1_without_key_or_parent_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in V1_SOURCES:
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._source_path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                before = self._counts(connection)
                first_results = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._source_path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in V2_SOURCES
                ]
                after = self._counts(connection)
                delta = {table: after[table] - before[table] for table in SEMANTIC_TABLES}
                self.assertEqual(
                    delta,
                    {
                        "evidence": 0,
                        "entities": 16,
                        "campuses": 8,
                        "facilities": 0,
                        "buildings": 0,
                        "projects": 8,
                        "entity_snapshots": 16,
                        "lifecycle_observations": 8,
                        "operating_model_observations": 8,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    },
                )
                self.assertEqual(
                    [(result.entities_created, result.evidence_created) for result in first_results],
                    [(2, 0)] * 8,
                )
                links = {
                    (row["project_key"], row["target_key"], row["target_entity_id"])
                    for row in connection.execute(
                        "SELECT project.stable_key AS project_key, "
                        "target.stable_key AS target_key, "
                        "p.target_entity_id AS target_entity_id "
                        "FROM projects AS p "
                        "JOIN entities AS project ON project.id = p.entity_id "
                        "JOIN entities AS target ON target.id = p.target_entity_id "
                        "WHERE project.stable_key IN "
                        f"({','.join('?' for _ in V2_PROJECT_KEYS)})",
                        tuple(sorted(V2_PROJECT_KEYS)),
                    )
                }
                self.assertEqual(
                    {(project, target) for project, target, _ in links},
                    {(_project_key(slug), _campus_key(slug)) for slug in SOURCE_SPECS},
                )
                self.assertEqual(len({target_id for _, _, target_id in links}), 8)
                self.assertTrue(
                    {target for _, target, _ in links}.isdisjoint(V1_REGIONAL_ANCHORS)
                )

                second_results = [
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._source_path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    for name in reversed(V2_SOURCES)
                ]
                self.assertEqual(
                    [(result.entities_created, result.evidence_created) for result in second_results],
                    [(0, 0)] * 8,
                )
                self.assertEqual(self._counts(connection), after)
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_release_and_master_projection_keep_all_components_unmapped_and_uncounted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, self._offline():
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in V2_SOURCES:
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._source_path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                documents = build_release_documents(
                    connection,
                    as_of=AS_OF_DATE,
                    recorded_at=RETRIEVED_AT,
                    publication_contract_version=3,
                )
            finally:
                connection.close()

        manifest = json.loads(documents["manifest.json"])
        self.assertEqual(manifest["entities"], 16)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 8, "project": 8})
        self.assertEqual(manifest["construction_pipeline_records"], 8)
        self.assertEqual(manifest["construction_source_signals"], 1)
        self.assertEqual(manifest["evidence_records"], 1)
        self.assertEqual(manifest["capacity_estimates"], 0)
        self.assertEqual(manifest["resolution_candidates"], 0)

        geojson = json.loads(documents["atlas.geojson"])
        v2_features = [
            feature
            for feature in geojson["features"]
            if feature["properties"]["stable_key"] in V2_CAMPUS_KEYS | V2_PROJECT_KEYS
        ]
        self.assertEqual(len(v2_features), 16)
        self.assertTrue(all(feature["geometry"] is None for feature in v2_features))
        project_features = [
            feature
            for feature in v2_features
            if feature["properties"]["entity_kind"] == "project"
        ]
        self.assertEqual(len(project_features), 8)
        self.assertEqual(
            len(
                {
                    feature["properties"]["target_entity_id"]
                    for feature in project_features
                }
            ),
            8,
        )

        pipeline = list(csv.DictReader(io.StringIO(documents["construction_pipeline.csv"])))
        evidence = {
            row["evidence_id"]: row
            for row in csv.DictReader(io.StringIO(documents["evidence.csv"]))
        }
        self.assertEqual(len(pipeline), 8)
        self.assertEqual({row["stable_key"] for row in pipeline}, V2_PROJECT_KEYS)
        master_rows = [
            _release_row(
                row,
                artifact={
                    "artifact_id": "vnet-q1-2026-v2-test",
                    "release_id": "vnet-q1-2026-v2-test",
                    "data": {"path": "construction_pipeline.csv"},
                },
                artifact_sha="a" * 64,
                manifest_sha="b" * 64,
                evidence=evidence,
                satellite_by_entity={},
                advisories_by_entity={},
                tier="A",
            )
            for row in pipeline
        ]
        for source_row, master_row in zip(pipeline, master_rows):
            self.assertEqual(source_row["entity_kind"], "project")
            self.assertEqual(source_row["status"], "under_construction")
            self.assertEqual(source_row["operating_model"], "wholesale_colocation")
            self.assertEqual(source_row["latitude"], "")
            self.assertEqual(source_row["longitude"], "")
            self.assertEqual(json.loads(source_row["capacity_estimates_json"]), [])
            self.assertEqual(json.loads(source_row["workloads_json"]), [])
            self.assertFalse(master_row["disposition"]["unique_site_counted"])
            self.assertEqual(master_row["capacity_observations"], [])
            self.assertEqual(master_row["annual_energy_observations"], [])
            self.assertEqual(master_row["pue_observations"], [])
            self.assertEqual(
                master_row["operating_model_observation"]["value"],
                "wholesale_colocation",
            )


if __name__ == "__main__":
    unittest.main()
