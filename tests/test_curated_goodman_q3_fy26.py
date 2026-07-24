from __future__ import annotations

from collections import Counter
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
RETRIEVED_AT = "2026-07-20T09:05:11Z"
ACTIVITY_AS_OF = "2026-05-26"
FIGURES_AS_OF = "2026-03-31"
EVIDENCE_KEY = "goodman-q3-fy26-operational-update-pdf-captured-2026-07-20"
PDF_BYTES = 9_358_661
PDF_SHA256 = "713196902d9c92df2502874d5cfa44f86a2ac4de35022a76f33983dba8053227"
V45_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v45.json"
V45_RELEASE = ROOT / "releases/2026-07-20-open-seed-v45"
V45_DEFINITION_SHA256 = (
    "c57e58d514fc69742b4dae5f8f1ea5244cc1f14aa1df6093d56abc8b779b6d13"
)

GEDCDP = "Goodman European Data Centre Development Partnership I"
GJDP = "Goodman Japan Development Partnership"
GHKDCP = "Goodman Hong Kong Data Centre Partnership"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-goodman-ams01-amsterdam.json": {
        "bytes": 20_945,
        "sha256": "86b5bab9cd778409410e5cd769cc7d7878f1d96d5ac4a8fe12471ae7ca43abd4",
        "code": "AMS01",
        "campus_key": "curated:goodman-ams01-amsterdam-data-centre-campus",
        "project_key": "curated:goodman-ams01-amsterdam-data-centre-campus:phase-1-current-development",
        "status": "mep_electrical",
        "owner": GEDCDP,
        "address": "Amsterdam, Netherlands",
    },
    "curated-official-2026-07-20-goodman-fra02-frankfurt.json": {
        "bytes": 21_003,
        "sha256": "f30db3b92de147265dfe281c307482f2679e57eecb7d436de8412179521408de",
        "code": "FRA02",
        "campus_key": "curated:goodman-fra02-frankfurt-data-centre-campus",
        "project_key": "curated:goodman-fra02-frankfurt-data-centre-campus:phase-1-current-development",
        "status": "under_construction",
        "owner": GEDCDP,
        "address": "Frankfurt South Availability Zone, Frankfurt, Germany",
    },
    "curated-official-2026-07-20-goodman-hkg09-kwai-chung.json": {
        "bytes": 20_898,
        "sha256": "e61f745ba1b4af4d095b84de81d31c4960a20137786589a949002640c864627c",
        "code": "HKG09",
        "campus_key": "curated:goodman-hkg09-kwai-chung-data-centre",
        "project_key": "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment",
        "status": "site_preparation",
        "owner": GHKDCP,
        "address": "Kwai Chung, Hong Kong",
    },
    "curated-official-2026-07-20-goodman-hkg10-tsuen-wan.json": {
        "bytes": 20_895,
        "sha256": "a6d006f832c90cc98b457dc4213e4c44d1ae01b80315ab14a492bbc69b568c92",
        "code": "HKG10",
        "campus_key": "curated:goodman-hkg10-tsuen-wan-data-centre",
        "project_key": "curated:goodman-hkg10-tsuen-wan-data-centre:current-redevelopment",
        "status": "under_construction",
        "owner": GHKDCP,
        "address": "Tsuen Wan, Hong Kong",
    },
    "curated-official-2026-07-20-goodman-lax01-los-angeles.json": {
        "bytes": 20_934,
        "sha256": "5e79a2176b02b4be58d7531ef6a957e410ef28448e8dd7c8e9fc0f0d0839e9b7",
        "code": "LAX01",
        "campus_key": "curated:goodman-lax01-los-angeles-program-anchor",
        "project_key": "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development",
        "status": "mep_electrical",
        "owner": "Goodman DataBank JV",
        "address": "Los Angeles metro, United States",
    },
    "curated-official-2026-07-20-goodman-par01-paris.json": {
        "bytes": 20_971,
        "sha256": "28179d0b0640362a2fa2405c8fb1564c408e3966fecac776267e091da1ea801a",
        "code": "PAR01",
        "campus_key": "curated:goodman-par01-paris-data-centre-campus",
        "project_key": "curated:goodman-par01-paris-data-centre-campus:phase-1-current-development",
        "status": "under_construction",
        "owner": GEDCDP,
        "address": "North Paris Availability Zone, Paris, France",
    },
    "curated-official-2026-07-20-goodman-par02-paris.json": {
        "bytes": 20_971,
        "sha256": "2ea8e966b737170e2e74ae829c89e61c9eacdc89fc980ceef344454834791e81",
        "code": "PAR02",
        "campus_key": "curated:goodman-par02-paris-data-centre-campus",
        "project_key": "curated:goodman-par02-paris-data-centre-campus:phase-1-current-development",
        "status": "mep_electrical",
        "owner": GEDCDP,
        "address": "Paris Central Availability Zone, Paris, France",
    },
    "curated-official-2026-07-20-goodman-syd01-macquarie-park.json": {
        "bytes": 20_968,
        "sha256": "c09b538259662c918480f223912e622861cac5a25d0a6b946aa64d980e0e8561",
        "code": "SYD01",
        "campus_key": "curated:goodman-syd01-macquarie-park-data-centre",
        "project_key": "curated:goodman-syd01-macquarie-park-data-centre:current-single-building-development",
        "status": "mep_electrical",
        "owner": "Goodman Group",
        "address": "Macquarie Park Availability Zone, Sydney, Australia",
    },
    "curated-official-2026-07-20-goodman-ty005-tokyo.json": {
        "bytes": 20_884,
        "sha256": "7f73b491775f176a2ab1dbacad6842e1aca60b8797771d373bc6d48987f1b47d",
        "code": "TY005",
        "campus_key": "curated:goodman-ty005-tokyo-data-centre-campus",
        "project_key": "curated:goodman-ty005-tokyo-data-centre-campus:phase-1-current-development",
        "status": "mep_electrical",
        "owner": GJDP,
        "address": "Tokyo, Japan",
    },
    "curated-official-2026-07-20-goodman-ty006-tokyo.json": {
        "bytes": 22_311,
        "sha256": "76b5a70e873caa7993c18d2f546cfa993ea0ab1f110f22b5b4d7dde0c98715f0",
        "code": "TY006",
        "campus_key": "curated:goodman-ty006-tokyo-data-centre-site",
        "project_key": "curated:goodman-ty006-tokyo-data-centre-site:current-power-infrastructure-development",
        "status": "under_construction",
        "owner": None,
        "address": "Tokyo, Japan",
    },
}
SOURCES = tuple(SOURCE_SPECS)


class GoodmanQ3FY26CuratedTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("Goodman curated import attempted network access")
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
                    "SELECT entities.kind, entities.stable_key, tags_json, latitude, "
                    "longitude, geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.kind, entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, base, as_of_date, "
                    "target_date, notes FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric",
                    "SELECT entities.stable_key, operating_model "
                    "FROM operating_model_observations JOIN entities "
                    "ON entities.id = operating_model_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, workload "
                    "FROM workload_observations JOIN entities "
                    "ON entities.id = workload_observations.entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def test_exact_files_are_canonical_pinned_and_share_one_pdf_evidence(self) -> None:
        self.assertEqual(len(SOURCES), 10)
        self.assertFalse(any(name.endswith("-v2.json") for name in SOURCES))
        shared_evidence: bytes | None = None
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                path = self._path(name)
                raw = path.read_bytes()
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                self.assertEqual(len(raw), spec["bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), spec["sha256"])
                text = raw.decode("utf-8")
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
                    document["evidence"][0], indent=2, ensure_ascii=False
                ).encode()
                if shared_evidence is None:
                    shared_evidence = encoded
                self.assertEqual(encoded, shared_evidence)

    def test_exact_capture_table_dates_and_guardrails(self) -> None:
        evidence = self._load(SOURCES[0])["evidence"][0]
        metadata = evidence["metadata"]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["publisher"], "Goodman Group")
        self.assertEqual(evidence["published_at"], ACTIVITY_AS_OF)
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], PDF_SHA256)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertEqual(metadata["http_content_length_bytes_as_received"], PDF_BYTES)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], PDF_BYTES)
        self.assertIn(f"{PDF_BYTES}-byte", metadata["content_hash_scope"])
        self.assertEqual(metadata["document_page_count"], 13)
        self.assertEqual(metadata["reporting_date_as_reported"], "31 March 2026")
        self.assertIn("activities current", metadata["activity_date_basis"])
        self.assertEqual(
            metadata["page_6_column_headings_as_reported"],
            [
                "FY26 PROJECTED DC WIP PROJECTS (MW)",
                ">FY26 SECURED PIPELINE ON CAMPUS (MW)",
                "TOTAL (MW)",
            ],
        )
        rows = metadata["page_6_dc_wip_pipeline_table_as_reported"]
        self.assertEqual([row["facility_code"] for row in rows], [
            "PAR01", "PAR02", "FRA02", "AMS01", "LAX01", "TY005",
            "HKG09", "HKG10", "MAD01", "SYD01",
        ])
        self.assertEqual(
            metadata["page_6_dc_wip_pipeline_table_totals_as_reported_mw"],
            {
                "fy26_projected_dc_wip_projects_mw": 497,
                "greater_than_fy26_secured_pipeline_on_campus_mw": 1332,
                "total_mw": 1829,
            },
        )
        for row in rows:
            self.assertNotIn("work_in_progress_mw", row)
            self.assertNotIn("future_development_mw", row)
        lax = next(row for row in rows if row["facility_code"] == "LAX01")
        self.assertEqual(lax["reported_program_site_count"], 3)
        self.assertEqual(lax["first_site_resolution"], "unresolved")
        self.assertIn("locality-scoped non-site", metadata["lax01_program_anchor_guardrail"])
        self.assertIn("raw reported program_site_count of 3", metadata["unique_site_guardrail"])
        self.assertIn("untyped evidence metadata", metadata["main_table_power_typing_guardrail"])
        self.assertIn("no exact target_date", metadata["forecast_guardrail"])
        self.assertIn("no site-level current electrical load", metadata["energy_guardrail"])

    def test_exact_entities_statuses_parent_only_owners_and_typed_capacity(self) -> None:
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                document = self._load(name)
                campus = document["campus"]
                project = document["project"]
                self.assertEqual(campus["stable_key"], spec["campus_key"])
                self.assertEqual(project["stable_key"], spec["project_key"])
                for entity in (campus, project):
                    self.assertEqual(entity["address"], spec["address"])
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["as_of_date"], ACTIVITY_AS_OF)
                    self.assertEqual(entity["method"], "authoritative_locality")
                expected_roles = (
                    {} if spec["owner"] is None else {"owner": [spec["owner"]]}
                )
                self.assertEqual(campus["roles"], expected_roles)
                self.assertEqual(project["roles"], {})
                self.assertEqual(
                    document["lifecycle"],
                    [
                        {
                            "entity": "project",
                            "value": spec["status"],
                            "evidence_key": EVIDENCE_KEY,
                            "as_of_date": ACTIVITY_AS_OF,
                            "method": "authoritative_physical_status_update",
                            "confidence": 0.99,
                        }
                    ],
                )
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                if spec["code"] == "TY006":
                    capacities = document["capacities"]
                    self.assertEqual(
                        {(row["metric"], row["base"]) for row in capacities},
                        {("gross_facility_mw", 50), ("critical_it_mw", 33)},
                    )
                    for row in capacities:
                        self.assertEqual(row["entity"], "project")
                        self.assertEqual(row["stage"], "planned")
                        self.assertEqual(row["as_of_date"], FIGURES_AS_OF)
                        self.assertIsNone(row["target_date"])
                        self.assertIn("not additive", row["notes"])
                else:
                    self.assertEqual(document["capacities"], [])

        self.assertEqual(
            Counter(spec["status"] for spec in SOURCE_SPECS.values()),
            {"mep_electrical": 5, "under_construction": 4, "site_preparation": 1},
        )
        all_keys = {
            key
            for spec in SOURCE_SPECS.values()
            for key in (spec["campus_key"], spec["project_key"])
        }
        self.assertFalse(any("mad01" in key.casefold() for key in all_keys))

    def test_each_source_imports_offline_in_isolation(self) -> None:
        for name, spec in SOURCE_SPECS.items():
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
                    expected = {
                        "evidence": 1,
                        "entities": 2,
                        "campuses": 1,
                        "projects": 1,
                        "entity_snapshots": 2,
                        "lifecycle_observations": 1,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 2 if spec["code"] == "TY006" else 0,
                    }
                    for table, count in expected.items():
                        observed = connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        self.assertEqual(observed, count, table)
                finally:
                    connection.close()

    def test_combined_import_is_order_independent_idempotent_and_exact(self) -> None:
        forward = self._state(SOURCES)
        self.assertEqual(forward, self._state(tuple(reversed(SOURCES))))
        self.assertEqual(forward, self._state(SOURCES, repetitions=2))
        entities, evidence, lifecycle, snapshots, capacities, models, workloads = forward
        self.assertEqual(len(entities), 20)
        self.assertEqual(Counter(kind for kind, _ in entities), {"campus": 10, "project": 10})
        self.assertEqual(evidence, ((EVIDENCE_KEY, PDF_SHA256),))
        self.assertEqual(len(lifecycle), 10)
        self.assertEqual(Counter(row[1] for row in lifecycle), {
            "mep_electrical": 5,
            "under_construction": 4,
            "site_preparation": 1,
        })
        self.assertEqual({row[2] for row in lifecycle}, {ACTIVITY_AS_OF})
        self.assertEqual(len(snapshots), 20)
        by_campus = {spec["campus_key"]: spec for spec in SOURCE_SPECS.values()}
        for kind, stable_key, tags_json, latitude, longitude, geometry_json in snapshots:
            tags = json.loads(tags_json)
            self.assertIsNone(latitude)
            self.assertIsNone(longitude)
            self.assertIsNone(geometry_json)
            if kind == "campus" and by_campus[stable_key]["owner"] is not None:
                self.assertEqual(tags["role:owner"], by_campus[stable_key]["owner"])
            else:
                self.assertFalse(any(key.startswith("role:") for key in tags))
        self.assertEqual(
            {(row[1], row[2], row[3], row[4], row[5]) for row in capacities},
            {
                ("critical_it_mw", "planned", 33.0, FIGURES_AS_OF, None),
                ("gross_facility_mw", "planned", 50.0, FIGURES_AS_OF, None),
            },
        )
        self.assertTrue(all("not additive" in row[6] for row in capacities))
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())

    def test_tranche_is_absent_from_frozen_open_seed_v45(self) -> None:
        self.assertEqual(
            hashlib.sha256(V45_DEFINITION.read_bytes()).hexdigest(),
            V45_DEFINITION_SHA256,
        )
        definition = json.loads(V45_DEFINITION.read_text(encoding="utf-8"))
        pinned = {row["path"] for row in definition["curated_inputs"]}
        intended_paths = {f"sources/{name}" for name in SOURCES}
        self.assertTrue(intended_paths.isdisjoint(pinned))

        payloads = [
            V45_DEFINITION.read_bytes(),
            *(path.read_bytes() for path in V45_RELEASE.iterdir() if path.is_file()),
        ]
        markers = {
            EVIDENCE_KEY,
            *(f"sources/{name}" for name in SOURCES),
            *(spec["sha256"] for spec in SOURCE_SPECS.values()),
            *(spec["campus_key"] for spec in SOURCE_SPECS.values()),
            *(spec["project_key"] for spec in SOURCE_SPECS.values()),
        }
        for marker in markers:
            self.assertFalse(
                any(marker.encode("utf-8") in payload for payload in payloads),
                marker,
            )


if __name__ == "__main__":
    unittest.main()
