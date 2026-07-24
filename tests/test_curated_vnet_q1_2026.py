from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T07:24:19Z"
AS_OF_DATE = "2026-03-31"
PRIMARY_URL = (
    "https://ir.vnet.com/static-files/"
    "2b16e7ee-2d06-4379-9035-266b7a27d52d"
)
EVIDENCE_KEY = (
    "vnet-1q26-ir-presentation-wholesale-construction-pdf-"
    "captured-2026-07-20"
)
PDF_BYTES = 2_121_222
PDF_SHA256 = "02ffcae20b92eefb1d8f70fbd6eb15f1b0213eb356713cac23b676c0b10cea0a"

YRD_CAMPUS = "curated:vnet-yangtze-river-delta-regional-wholesale-anchor"
BEIJING_CAMPUS = "curated:vnet-greater-beijing-area-regional-wholesale-anchor"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-vnet-e-js03b.json": {
        "sha256": "acfae78267f91e6820b9f4d22a35fa3a828e4c9d53ae17b8ed58042a4f72330b",
        "code": "E-JS03B",
        "project_name": "VNET E-JS03B Construction Component",
        "campus_key": YRD_CAMPUS,
        "campus_name": "VNET Yangtze River Delta Regional Wholesale Anchor",
        "region": "Yangtze River Delta",
        "mw": 44,
    },
    "curated-official-2026-07-20-vnet-n-hb02.json": {
        "sha256": "6e0a83110457229986e6ab703954c221b5d6904b4a480c22dc9b65a1e05d79a6",
        "code": "N-HB02",
        "project_name": "VNET N-HB02 Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 59,
    },
    "curated-official-2026-07-20-vnet-n-hb03.json": {
        "sha256": "1bfdc6e845755e11871c882c4b80292f53f2407c6cdd25c30f69c504dfce5a01",
        "code": "N-HB03",
        "project_name": "VNET N-HB03 Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 4,
    },
    "curated-official-2026-07-20-vnet-n-hb04.json": {
        "sha256": "c89b4c2b0f93307e85f4fa5cb187c4157552c7d15eaea11587a59da4883fcfe9",
        "code": "N-HB04",
        "project_name": "VNET N-HB04 Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 21,
    },
    "curated-official-2026-07-20-vnet-n-or01.json": {
        "sha256": "b5963e09b58ec96fcd6065959ee9ee7b0c900ac15baa40dad99f813f543f7a4f",
        "code": "N-OR01",
        "project_name": "VNET N-OR01 Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 9,
    },
    "curated-official-2026-07-20-vnet-n-or02a.json": {
        "sha256": "0f7f78b11809e2d926df5820e6999b7dd843278fc6454a0249fb7dae7efda697",
        "code": "N-OR02A",
        "project_name": "VNET N-OR02A Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 101,
    },
    "curated-official-2026-07-20-vnet-n-or02b.json": {
        "sha256": "50278632f21512a44c8d9549915f7a7239c6e21e9f5a49d04858802a07609645",
        "code": "N-OR02B",
        "project_name": "VNET N-OR02B Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 65,
    },
    "curated-official-2026-07-20-vnet-n-or03.json": {
        "sha256": "4a6413620c698fda95ff58b90238b20b4ae474073bfe437b92f80bd5d21f31bb",
        "code": "N-OR03",
        "project_name": "VNET N-OR03 Construction Component",
        "campus_key": BEIJING_CAMPUS,
        "campus_name": "VNET Greater Beijing Area Regional Wholesale Anchor",
        "region": "Greater Beijing Area",
        "mw": 213,
    },
}
SOURCES = tuple(SOURCE_SPECS)

RAW_COMPONENTS = [
    {
        "normalized_component_code": "E-JS03B",
        "source_idc_code": "E-JS Campus 03B",
        "region": "Yangtze River Delta",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 44,
        "capacity_pre_committed_mw": 44,
        "pre_commitment_rate_percent": 100.0,
        "ready_for_service_as_reported": "2H26",
    },
    {
        "normalized_component_code": "N-HB02",
        "source_idc_code": "N-HB Campus 02",
        "region": "Greater Beijing Area",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 59,
        "capacity_pre_committed_mw": 0,
        "pre_commitment_rate_percent": 0.0,
        "ready_for_service_as_reported": "2H26",
    },
    {
        "normalized_component_code": "N-HB03",
        "source_idc_code": "N-HB Campus 03",
        "region": "Greater Beijing Area",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 4,
        "capacity_pre_committed_mw": 4,
        "pre_commitment_rate_percent": 91.4,
        "ready_for_service_as_reported": "1H26",
    },
    {
        "normalized_component_code": "N-HB04",
        "source_idc_code": "N-HB04",
        "region": "Greater Beijing Area",
        "tenure": "Leased",
        "status": "Under Construction",
        "capacity_under_construction_mw": 21,
        "capacity_pre_committed_mw": 7,
        "pre_commitment_rate_percent": 33.0,
        "ready_for_service_as_reported": "2H26/1H27",
    },
    {
        "normalized_component_code": "N-OR01",
        "source_idc_code": "N-OR Campus 01",
        "region": "Greater Beijing Area",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 9,
        "capacity_pre_committed_mw": 9,
        "pre_commitment_rate_percent": 100.0,
        "ready_for_service_as_reported": "1H26",
    },
    {
        "normalized_component_code": "N-OR02A",
        "source_idc_code": "N-OR Campus 02A",
        "region": "Greater Beijing Area",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 101,
        "capacity_pre_committed_mw": 101,
        "pre_commitment_rate_percent": 100.0,
        "ready_for_service_as_reported": "2H26",
    },
    {
        "normalized_component_code": "N-OR02B",
        "source_idc_code": "N-OR Campus 02B",
        "region": "Greater Beijing Area",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 65,
        "capacity_pre_committed_mw": 65,
        "pre_commitment_rate_percent": 100.0,
        "ready_for_service_as_reported": "2H26",
    },
    {
        "normalized_component_code": "N-OR03",
        "source_idc_code": "N-OR Campus 03",
        "region": "Greater Beijing Area",
        "tenure": "Owned",
        "status": "Under Construction",
        "capacity_under_construction_mw": 213,
        "capacity_pre_committed_mw": 213,
        "pre_commitment_rate_percent": 100.0,
        "ready_for_service_as_reported": "2H26/1H27",
    },
]


class VnetQ12026CuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("VNET curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _state(
        self,
        order: tuple[str, ...],
        *,
        repetitions: int = 1,
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for _ in range(repetitions):
                        for name in order:
                            CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._path(name),
                                retrieved_at=RETRIEVED_AT,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, base "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_exact_files_are_canonical_hash_pinned_and_share_one_evidence(self) -> None:
        self.assertEqual(len(SOURCES), 8)
        shared_evidence: bytes | None = None
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    spec["sha256"],
                )
                text = path.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
                self.assertEqual(
                    set(document),
                    {
                        "schema_version",
                        "evidence",
                        "campus",
                        "project",
                        "lifecycle",
                        "operating_models",
                        "workloads",
                        "capacities",
                    },
                )
                self.assertEqual(document["schema_version"], "1.0")
                self.assertEqual(len(document["evidence"]), 1)
                encoded = json.dumps(
                    document["evidence"][0],
                    indent=2,
                    ensure_ascii=False,
                ).encode()
                if shared_evidence is None:
                    shared_evidence = encoded
                self.assertEqual(encoded, shared_evidence)

    def test_exact_pdf_capture_pages_rows_and_raw_mw_guardrails(self) -> None:
        evidence = self._load(SOURCES[0])["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["source_url"], PRIMARY_URL)
        self.assertEqual(evidence["publisher"], "VNET Group, Inc.")
        self.assertEqual(evidence["published_at"], "2026-05-26")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], PDF_SHA256)
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(f"{PDF_BYTES}-byte", metadata["content_hash_scope"])
        self.assertIn("Fetch.takeResponseBodyAsStream", metadata["content_hash_scope"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertEqual(metadata["content_length_bytes_as_received"], PDF_BYTES)
        self.assertEqual(metadata["pdf_version"], "1.7")
        self.assertEqual(metadata["pdf_page_count"], 31)
        self.assertEqual(metadata["publication_date_pdf_page_index_one_based"], 1)
        self.assertIn("title slide", metadata["publication_date_basis"])
        self.assertIn("does not derive", metadata["publication_date_basis"])
        self.assertEqual(metadata["resource_pipeline_pdf_page_index_one_based"], 10)
        self.assertEqual(metadata["resource_pipeline_printed_slide_label"], 10)
        self.assertEqual(
            metadata["wholesale_construction_pdf_page_index_one_based"],
            25,
        )
        self.assertEqual(metadata["wholesale_construction_printed_slide_label"], 25)
        self.assertEqual(metadata["reporting_period_end"], AS_OF_DATE)
        self.assertEqual(metadata["components_as_reported"], RAW_COMPONENTS)
        self.assertEqual(
            [row["capacity_under_construction_mw"] for row in RAW_COMPONENTS],
            [44, 59, 4, 21, 9, 101, 65, 213],
        )
        self.assertEqual(
            sum(row["capacity_under_construction_mw"] for row in RAW_COMPONENTS),
            516,
        )
        self.assertEqual(
            sum(row["capacity_pre_committed_mw"] for row in RAW_COMPONENTS),
            443,
        )
        self.assertEqual(metadata["reported_total_capacity_under_construction_mw"], 516)
        self.assertEqual(metadata["reported_total_capacity_pre_committed_mw"], 443)
        self.assertEqual(metadata["reported_total_pre_commitment_rate_percent"], 85.8)
        self.assertIn("100.0 percent values remain JSON 100.0", metadata["raw_table_consistency_guardrail"])
        self.assertIn("4 MW pre-committed, and 91.4 percent", metadata["raw_table_consistency_guardrail"])
        self.assertIn("No rate is recomputed", metadata["raw_table_consistency_guardrail"])
        self.assertIn("no normalized capacity rows", metadata["capacity_guardrail"])
        self.assertIn("raw evidence metadata", metadata["aggregate_guardrail"])
        self.assertIn("no exact target date", metadata["rfs_guardrail"])
        self.assertIn("not verified unique physical sites", metadata["site_count_guardrail"])
        self.assertIn("no city, province", metadata["locality_guardrail"])

    def test_exact_eight_projects_two_regional_anchors_and_no_type_leakage(self) -> None:
        project_keys: set[str] = set()
        campus_keys: list[str] = []
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                document = self._load(name)
                campus = document["campus"]
                project = document["project"]
                address = f"{spec['region']}, China"
                self.assertEqual(campus["stable_key"], spec["campus_key"])
                self.assertEqual(campus["name"], spec["campus_name"])
                self.assertEqual(project["name"], spec["project_name"])
                self.assertEqual(
                    project["stable_key"],
                    f"{spec['campus_key']}:{spec['code'].lower()}-under-construction",
                )
                campus_keys.append(campus["stable_key"])
                project_keys.add(project["stable_key"])
                for entity in (campus, project):
                    self.assertEqual(entity["country"], "China")
                    self.assertEqual(entity["address"], address)
                    self.assertEqual(entity["roles"], {})
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
                    self.assertEqual(entity["as_of_date"], AS_OF_DATE)
                    self.assertEqual(entity["method"], "authoritative_locality")
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
                raw = next(
                    row
                    for row in document["evidence"][0]["metadata"][
                        "components_as_reported"
                    ]
                    if row["normalized_component_code"] == spec["code"]
                )
                self.assertEqual(raw["capacity_under_construction_mw"], spec["mw"])

        self.assertEqual(len(project_keys), 8)
        self.assertEqual(set(campus_keys), {YRD_CAMPUS, BEIJING_CAMPUS})
        self.assertEqual(campus_keys.count(YRD_CAMPUS), 1)
        self.assertEqual(campus_keys.count(BEIJING_CAMPUS), 7)
        self.assertTrue(project_keys.isdisjoint(set(campus_keys)))

    def test_each_source_imports_offline_in_isolation(self) -> None:
        for name in SOURCES:
            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with self._offline():
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            self._path(name),
                            retrieved_at=RETRIEVED_AT,
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                    expected_counts = {
                        "evidence": 1,
                        "entities": 2,
                        "campuses": 1,
                        "projects": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 1,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    }
                    for table, expected in expected_counts.items():
                        observed = connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        self.assertEqual(observed, expected, table)
                finally:
                    connection.close()

    def test_combined_import_is_idempotent_order_independent_and_exact(self) -> None:
        forward = self._state(SOURCES)
        reverse = self._state(tuple(reversed(SOURCES)))
        repeated = self._state(SOURCES, repetitions=2)
        self.assertEqual(forward, reverse)
        self.assertEqual(forward, repeated)

        entities, evidence, lifecycle, snapshots, models, workloads, capacities = forward
        self.assertEqual(len(entities), 10)
        self.assertEqual(sum(kind == "campus" for kind, _ in entities), 2)
        self.assertEqual(sum(kind == "project" for kind, _ in entities), 8)
        self.assertEqual(evidence, ((EVIDENCE_KEY, PDF_SHA256),))
        self.assertEqual(len(lifecycle), 8)
        self.assertEqual({row[1] for row in lifecycle}, {"under_construction"})
        self.assertEqual({row[2] for row in lifecycle}, {AS_OF_DATE})
        self.assertEqual(len(snapshots), 10)
        self.assertEqual(len(models), 8)
        self.assertEqual({row[1] for row in models}, {"wholesale_colocation"})
        self.assertEqual(workloads, ())
        self.assertEqual(capacities, ())
        for _, _, tags_json, latitude, longitude, geometry_json in snapshots:
            tags = json.loads(tags_json)
            self.assertEqual(tags["country"], "China")
            self.assertIn(
                tags["address"],
                {"Yangtze River Delta, China", "Greater Beijing Area, China"},
            )
            self.assertFalse(any(key.startswith("role:") for key in tags))
            self.assertIsNone(latitude)
            self.assertIsNone(longitude)
            self.assertIsNone(geometry_json)


if __name__ == "__main__":
    unittest.main()
