from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sources/curated-official-2026-07-20-databank-iad6-culpeper.json"
IAD5_SOURCE = ROOT / "sources/curated-official-2026-07-20-databank-iad5-culpeper.json"
V62_ENTITIES = ROOT / "releases/2026-07-20-open-seed-v62/entities.csv"
SOURCE_BYTES = 24_662
SOURCE_SHA256 = "d5d1beb4bc0549b7921fa91d41f495a950439a61b9e464c704aa272e7798af31"
RECORDED_AT = "2026-07-21T04:40:00Z"
POST_KEY = (
    "databank-iad5-iad6-culpeper-groundwork-update-2026-02-19-captured-2026-07-20"
)
PAGE_KEY = (
    "databank-iad6-culpeper-facility-page-modified-2026-05-14-captured-2026-07-20"
)
DHCD_KEY = "virginia-dhcd-14601-germanna-highway-address-point-captured-2026-07-20"
CAMPUS_KEY = "curated:databank-culpeper-campus"
IAD5_PROJECT_KEY = f"{CAMPUS_KEY}:iad5-current-build"
PROJECT_KEY = f"{CAMPUS_KEY}:iad6-current-build"


class DataBankIad6CulpeperTests(unittest.TestCase):
    def _block_network(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "DataBank IAD6 curated import attempted network access"
        )
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def _import(self):
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        result = CuratedOfficialSourceAdapterV11().import_file(
            connection,
            SOURCE,
            recorded_at=RECORDED_AT,
        )
        return temporary, connection, result

    def test_source_is_canonical_and_capture_facts_are_byte_pinned(self) -> None:
        data = SOURCE.read_bytes()
        self.assertEqual(len(data), SOURCE_BYTES)
        self.assertEqual(hashlib.sha256(data).hexdigest(), SOURCE_SHA256)
        document = json.loads(data.decode("utf-8"))
        self.assertEqual(
            data.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(document["schema_version"], "1.1")
        self.assertEqual(
            [row["key"] for row in document["evidence"]],
            [POST_KEY, PAGE_KEY, DHCD_KEY],
        )
        expected = (
            (
                "8e31aba45178e81c547545bed4b12e6024c10baf71dd1bbb6cd05d1ab66ea8ee",
                319_992,
                "d49b929e8c9c473e9d8f78e1d77af62b0ae4dc61f86ef88d70e5731906d24622",
                "fb00aba9ede96d61c67d17f519daf59174941de5231ee080e995587c4f803e39",
                "2026-07-21T04:36:19Z",
            ),
            (
                "2b7d359c3d98d0e4ccd5c0929538d4798386580eb966c28cf2562c3df191afe7",
                121_243,
                "12c1f7b5bb155bf69a036b0e0bea756a2a22ed24213514a3612021b164832d8c",
                "5ddd93f815df1791535dd9fcf2a6ad951bf60d07b1d73e9044aebc3a0f11174a",
                "2026-07-21T04:36:20Z",
            ),
            (
                "a9cd3e4d919d4c11a97b4bca717c6e617730efa26d02ffec8b0983114a8b1f41",
                7_225_328,
                "a46c57544a1baa7bca015f3c8d75fdc24a782a6fd72922d29a49d72adf5a85ca",
                "be8e935a65878ead60181341cbabe0df9160bb55c9f1315b3261145454c22f00",
                "2026-07-21T04:27:49Z",
            ),
        )
        for evidence, (
            body_hash,
            body_bytes,
            header_hash,
            facts_hash,
            retrieved,
        ) in zip(document["evidence"], expected, strict=True):
            metadata = evidence["metadata"]
            self.assertEqual(evidence["content_hash"], body_hash)
            self.assertEqual(evidence["retrieved_at"], retrieved)
            self.assertEqual(evidence["license"], "all-rights-reserved")
            self.assertEqual(metadata["http_status"], 200)
            self.assertIn(str(body_bytes), metadata["content_hash_scope"])
            self.assertEqual(metadata["capture_headers_sha256"], header_hash)
            self.assertEqual(metadata["capture_curl_writeout_sha256"], facts_hash)
            self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
            self.assertEqual(metadata["requested_url"], metadata["effective_url"])
            self.assertEqual(metadata["effective_url"], metadata["canonical_url"])

        post = document["evidence"][0]["metadata"]
        self.assertEqual(post["structured_date_published"], "2026-02-19T18:02:17.998Z")
        self.assertIn(
            "Both facilities are being built", post["construction_wording_as_reported"]
        )
        self.assertIn("grading", post["physical_context_as_reported"])
        page = document["evidence"][1]["metadata"]
        self.assertEqual(page["page_modified_at"], "2026-05-14T19:00:22+00:00")
        self.assertEqual(
            page["address_as_reported"], "14601 Germanna Hwy - Culpeper, VA 22701"
        )
        self.assertEqual(page["capacity_wording_as_reported"], "120MW Critical IT Load")

        iad5_document = json.loads(IAD5_SOURCE.read_text(encoding="utf-8"))
        iad5_dhcd = next(
            row for row in iad5_document["evidence"] if row["key"] == DHCD_KEY
        )
        self.assertEqual(document["evidence"][2], iad5_dhcd)

    def test_offline_import_has_exact_source_scoped_rows(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary, connection, result = self._import()
            stack.callback(temporary.cleanup)
            stack.callback(connection.close)
            self.assertEqual(result.entities_created, 2)
            self.assertEqual(result.evidence_created, 3)
            self.assertEqual(result.warnings, ())
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 2,
                    "evidence": 3,
                    "entity_snapshots": 2,
                    "lifecycle_observations": 1,
                    "operating_model_observations": 1,
                    "workload_observations": 0,
                    "capacity_estimates": 1,
                },
            )
            entity_rows = list(
                connection.execute(
                    "SELECT stable_key, kind FROM entities ORDER BY stable_key"
                )
            )
            self.assertEqual(
                [tuple(row) for row in entity_rows],
                [(CAMPUS_KEY, "campus"), (PROJECT_KEY, "project")],
            )
            project_target = connection.execute(
                "SELECT target.stable_key FROM projects "
                "JOIN entities AS project ON project.id = projects.entity_id "
                "JOIN entities AS target ON target.id = projects.target_entity_id "
                "WHERE project.stable_key = ?",
                (PROJECT_KEY,),
            ).fetchone()
            self.assertEqual(project_target["stable_key"], CAMPUS_KEY)
            evidence_rows = list(
                connection.execute(
                    "SELECT title, publisher, published_at, retrieved_at "
                    "FROM evidence ORDER BY retrieved_at, title"
                )
            )
            self.assertEqual(
                [tuple(row) for row in evidence_rows],
                [
                    (
                        "2024 VATI Culpeper County Fiber Expansion application address list",
                        "Virginia Department of Housing and Community Development",
                        None,
                        "2026-07-21T04:27:49Z",
                    ),
                    (
                        "IAD5 & IAD6 Data Center Update",
                        "DataBank",
                        "2026-02-19",
                        "2026-07-21T04:36:19Z",
                    ),
                    (
                        "Culpeper Campus Data Center",
                        "DataBank",
                        "2026-05-14",
                        "2026-07-21T04:36:20Z",
                    ),
                ],
            )

    def test_status_capacity_colocation_and_roles_are_exact(self) -> None:
        temporary, connection, _ = self._import()
        try:
            lifecycle = connection.execute(
                "SELECT entities.stable_key, status, as_of_date, method, confidence "
                "FROM lifecycle_observations JOIN entities "
                "ON entities.id = lifecycle_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(lifecycle),
                (
                    PROJECT_KEY,
                    "under_construction",
                    "2026-02-19",
                    "authoritative_physical_status_update",
                    0.99,
                ),
            )
            capacity = connection.execute(
                "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                "method, as_of_date, target_date FROM capacity_estimates JOIN entities "
                "ON entities.id = capacity_estimates.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(capacity),
                (
                    PROJECT_KEY,
                    "critical_it_mw",
                    "planned",
                    "MW",
                    120.0,
                    120.0,
                    120.0,
                    "reported",
                    "2026-05-14",
                    None,
                ),
            )
            model = connection.execute(
                "SELECT entities.stable_key, operating_model, as_of_date, method "
                "FROM operating_model_observations JOIN entities "
                "ON entities.id = operating_model_observations.entity_id"
            ).fetchone()
            self.assertEqual(
                tuple(model),
                (PROJECT_KEY, "colocation", "2026-05-14", "company_disclosure"),
            )
            snapshots = list(
                connection.execute(
                    "SELECT entities.stable_key, latitude, longitude, geometry_json, "
                    "tags_json, entity_snapshots.method, entity_snapshots.as_of_date "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                [row["stable_key"] for row in snapshots], [CAMPUS_KEY, PROJECT_KEY]
            )
            for row in snapshots:
                self.assertEqual(
                    (row["latitude"], row["longitude"]), (38.45185992, -77.98378765)
                )
                self.assertEqual(
                    json.loads(row["geometry_json"]),
                    {
                        "type": "Point",
                        "coordinates": [-77.98378765, 38.45185992],
                    },
                )
                self.assertEqual(row["method"], "authoritative_address_geocode")
                self.assertEqual(row["as_of_date"], "2026-07-20")
                tags = json.loads(row["tags_json"])
                self.assertEqual(
                    tags["address"],
                    "14601 Germanna Hwy, Culpeper, Virginia 22701, United States",
                )
                self.assertEqual(tags["role:developer"], "DataBank")
                self.assertEqual(tags["role:operator"], "DataBank")
        finally:
            connection.close()
            temporary.cleanup()

    def test_coordinates_and_design_language_cannot_expand_claim_scope(self) -> None:
        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["workloads"], [])
        self.assertEqual(len(document["capacities"]), 1)
        capacity = document["capacities"][0]
        self.assertEqual(
            (
                capacity["entity"],
                capacity["metric"],
                capacity["stage"],
                capacity["base"],
            ),
            ("project", "critical_it_mw", "planned", 120),
        )
        self.assertIsNone(capacity["target_date"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(
                entity["coordinates"],
                {"latitude": 38.45185992, "longitude": -77.98378765},
            )
            self.assertEqual(
                entity["geometry"],
                {
                    "type": "Point",
                    "coordinates": [-77.98378765, 38.45185992],
                },
            )
            self.assertEqual(entity["evidence_key"], DHCD_KEY)
            self.assertEqual(entity["method"], "authoritative_address_geocode")
            self.assertEqual(entity["confidence"], 0.98)

        post = document["evidence"][0]["metadata"]
        page = document["evidence"][1]["metadata"]
        coordinate = document["evidence"][2]["metadata"]
        self.assertIn("generic IAD6 project-level", post["status_scope"])
        self.assertIn("no duplicate capacity", post["capacity_scope"])
        self.assertIn("No phase entity", post["phase_guardrail"])
        self.assertIn("no normalized current workload", post["workload_guardrail"])
        self.assertIn("site-count observation", page["site_count_guardrail"])
        self.assertIn("no phase entity", page["phase_guardrail"])
        self.assertIn("no current workload", page["workload_guardrail"])
        self.assertIn("no construction start", page["forecast_guardrail"])
        self.assertIn("not a parcel", coordinate["coordinate_scope"])
        self.assertIn("location only", coordinate["identity_bridge_scope"])
        self.assertIn("not a physical-site count", coordinate["site_count_guardrail"])
        self.assertIn("no data-center lifecycle", coordinate["broadband_guardrail"])

    def test_identity_is_absent_from_v62_and_time_gate_fails_closed(self) -> None:
        if V62_ENTITIES.exists():
            with V62_ENTITIES.open(newline="", encoding="utf-8") as handle:
                v62_keys = {row["stable_key"] for row in csv.DictReader(handle)}
            self.assertNotIn(PROJECT_KEY, v62_keys)
            self.assertIn(CAMPUS_KEY, v62_keys)
            self.assertIn(IAD5_PROJECT_KEY, v62_keys)

        document = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(document["campus"]["stable_key"], CAMPUS_KEY)
        self.assertEqual(document["project"]["stable_key"], PROJECT_KEY)
        self.assertTrue(PROJECT_KEY.startswith(CAMPUS_KEY + ":"))
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        SOURCE,
                        recorded_at="2026-07-21T04:36:19Z",
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    0,
                )
            finally:
                connection.close()

    def test_iad5_then_iad6_shares_one_campus_and_never_double_counts(self) -> None:
        with ExitStack() as stack:
            self._block_network(stack)
            temporary = tempfile.TemporaryDirectory()
            stack.callback(temporary.cleanup)
            connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
            stack.callback(connection.close)
            adapter = CuratedOfficialSourceAdapterV11()
            iad5_result = adapter.import_file(
                connection,
                IAD5_SOURCE,
                recorded_at=RECORDED_AT,
            )
            iad6_result = adapter.import_file(
                connection,
                SOURCE,
                recorded_at=RECORDED_AT,
            )
            repeated_result = adapter.import_file(
                connection,
                SOURCE,
                recorded_at=RECORDED_AT,
            )
            self.assertEqual(
                (iad5_result.entities_created, iad5_result.evidence_created), (2, 3)
            )
            self.assertEqual(
                (iad6_result.entities_created, iad6_result.evidence_created), (1, 2)
            )
            self.assertEqual(
                (repeated_result.entities_created, repeated_result.evidence_created),
                (0, 0),
            )
            self.assertEqual(validate_database(connection), [])
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "entities",
                    "campuses",
                    "projects",
                    "evidence",
                    "entity_snapshots",
                    "lifecycle_observations",
                    "operating_model_observations",
                    "workload_observations",
                    "capacity_estimates",
                )
            }
            self.assertEqual(
                counts,
                {
                    "entities": 3,
                    "campuses": 1,
                    "projects": 2,
                    "evidence": 5,
                    "entity_snapshots": 3,
                    "lifecycle_observations": 2,
                    "operating_model_observations": 2,
                    "workload_observations": 0,
                    "capacity_estimates": 2,
                },
            )
            project_targets = list(
                connection.execute(
                    "SELECT project.stable_key AS project_key, "
                    "target.stable_key AS target_key FROM projects "
                    "JOIN entities AS project ON project.id = projects.entity_id "
                    "JOIN entities AS target ON target.id = projects.target_entity_id "
                    "ORDER BY project.stable_key"
                )
            )
            self.assertEqual(
                [tuple(row) for row in project_targets],
                [(IAD5_PROJECT_KEY, CAMPUS_KEY), (PROJECT_KEY, CAMPUS_KEY)],
            )
            capacity_rows = list(
                connection.execute(
                    "SELECT entities.stable_key, metric, stage, base "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key"
                )
            )
            self.assertEqual(
                [tuple(row) for row in capacity_rows],
                [
                    (IAD5_PROJECT_KEY, "critical_it_mw", "planned", 72.0),
                    (PROJECT_KEY, "critical_it_mw", "planned", 120.0),
                ],
            )
            self.assertEqual(sum(row["base"] for row in capacity_rows), 192.0)
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "WHERE entities.stable_key = ?",
                    (CAMPUS_KEY,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM evidence WHERE source_url = ?",
                    (
                        "https://www.dhcd.virginia.gov/sites/default/files/DocX/"
                        "vati/2024-vati-applications/vati2024culpeper.pdf",
                    ),
                ).fetchone()[0],
                1,
            )


if __name__ == "__main__":
    unittest.main()
