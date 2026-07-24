from __future__ import annotations

import hashlib
import json
import socket
import stat
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T01:40:05Z"

BARBER_BUILDING = (
    "curated-official-2026-07-20-cipher-barber-lake-topped-out-building.json"
)
BARBER_PHASE_1 = (
    "curated-official-2026-07-20-cipher-barber-lake-phase-1-capacity-component.json"
)
BARBER_PHASE_2 = (
    "curated-official-2026-07-20-cipher-barber-lake-phase-2-capacity-component.json"
)
BLACK_PHASE_1 = (
    "curated-official-2026-07-20-cipher-black-pearl-phase-1-aws-retrofit.json"
)
BLACK_PHASE_2 = (
    "curated-official-2026-07-20-cipher-black-pearl-phase-2-site-preparation.json"
)
MUSKOGEE_BUILDING_2 = (
    "curated-official-2026-07-20-core-scientific-muskogee-building-2.json"
)
SOURCE_ORDER = (
    BARBER_BUILDING,
    BARBER_PHASE_1,
    BARBER_PHASE_2,
    BLACK_PHASE_1,
    BLACK_PHASE_2,
    MUSKOGEE_BUILDING_2,
)

SOURCE_SHA256 = {
    BARBER_BUILDING: (
        "e2180f05010ac18d15bb970d93439abb441453c57225b10c2577e5ef5adc3da1"
    ),
    BARBER_PHASE_1: (
        "03f328e2d249a5c5931ef9a8eea45d62782a008f810cf522fd0e77e3e9accd3a"
    ),
    BARBER_PHASE_2: (
        "8c5fa1cde0c76b13e4da145bcb3344d0fa809de6085b1f4d5dd158a8da2f0f24"
    ),
    BLACK_PHASE_1: (
        "1fb9e5ecd778af16d4f2be305894511f94d3ca3371173cf03e38f2e4446361f9"
    ),
    BLACK_PHASE_2: (
        "b82336e19b9ac6594267b9418c3f14da997a019a43532543a403fa9f5fdcc6f9"
    ),
    MUSKOGEE_BUILDING_2: (
        "c6ab36356b873285e23b83f264421d8cac3eea8b14176a3931211c0ecc3979b8"
    ),
}

Q1_KEY = (
    "cipher-digital-q1-2026-barber-black-pearl-construction-update-"
    "captured-2026-07-20"
)
SEPTEMBER_KEY = (
    "cipher-barber-lake-244mw-168mw-lease-presentation-2025-09-25-"
    "captured-2026-07-20"
)
NOVEMBER_KEY = (
    "cipher-barber-lake-additional-56mw-39mw-release-2025-11-20-"
    "captured-2026-07-20"
)
FORM_10K_KEY = "cipher-digital-2025-form-10-k-sites-capacities-captured-2026-07-20"
CORE_KEY = (
    "core-scientific-muskogee-building-2-expansion-release-2026-05-06-"
    "captured-2026-07-20"
)

CAPTURE_FACTS = {
    Q1_KEY: {
        "body_bytes": 140109,
        "content_hash": (
            "e8c146f2e616aaf8ff8757989145334534bd34b306c641367d0717b97ded4eed"
        ),
        "headers_bytes": 662,
        "headers_hash": (
            "0ab8bafddb63770915bde630b38ca85c88d91a98ffcf36453129e7e47b87bffb"
        ),
        "download_bytes": 10579,
        "response_date": "2026-07-20T01:40:04Z",
        "last_modified": "2026-05-05T11:25:45Z",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/1819989/"
            "000181998926000025/exh991q1fy26_earningsxprvf.htm"
        ),
    },
    SEPTEMBER_KEY: {
        "body_bytes": 15510,
        "content_hash": (
            "1f77c00a44751e7ef52850a4245d6cb70a1230be313f757b6a2dfd21a8f7a9dc"
        ),
        "headers_bytes": 661,
        "headers_hash": (
            "c1395e069b40e98e437694f56ea8d6ed5609e362b997c181e8f321d34edda225"
        ),
        "download_bytes": 5086,
        "response_date": "2026-07-20T01:40:04Z",
        "last_modified": "2025-09-25T10:31:04Z",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/1819989/"
            "000095010325012168/dp234624_ex9902.htm"
        ),
    },
    NOVEMBER_KEY: {
        "body_bytes": 25006,
        "content_hash": (
            "57a44de751a1530cfd6aa08ae6f2b8f2e5ec5e0e9b8cc02e5d6ce9431f1bd15d"
        ),
        "headers_bytes": 681,
        "headers_hash": (
            "ad1c32ac9711306e76fab70adce996f707c02eee72ff5fd0565657fbcdf6f848"
        ),
        "download_bytes": 5495,
        "response_date": "2026-07-20T01:40:04Z",
        "last_modified": "2025-11-20T12:47:39Z",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/1819989/"
            "000095010325015073/dp237633_ex9901.htm"
        ),
    },
    FORM_10K_KEY: {
        "body_bytes": 2318067,
        "content_hash": (
            "8116bbe1eaa8c2ef7732cb277688e108f7ee0e43fc114435d4e17b6842d8c760"
        ),
        "headers_bytes": 683,
        "headers_hash": (
            "2b40e55664f8d1a6ae1e445eb67189cf6e5e29c85af5cba3ec6b6c7ee19cea58"
        ),
        "download_bytes": 216707,
        "response_date": "2026-07-20T01:40:05Z",
        "last_modified": "2026-02-24T14:07:18Z",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/1819989/"
            "000181998926000009/cifr-20251231.htm"
        ),
    },
    CORE_KEY: {
        "body_bytes": 9137,
        "content_hash": (
            "3dd8f30f1659609d358f30eb81f8c1ed29d4c23f03857232bcd9540d531abf5f"
        ),
        "headers_bytes": 681,
        "headers_hash": (
            "9a4fe44942f99f0d23e11b8ae131605d2579a7c8b4f0f02c31ab127f94af2e04"
        ),
        "download_bytes": 3569,
        "response_date": "2026-07-20T01:40:05Z",
        "last_modified": "2026-05-06T11:53:40Z",
        "url": (
            "https://www.sec.gov/Archives/edgar/data/1839341/"
            "000162828026030918/exhibit991polarispressre.htm"
        ),
    },
}

BARBER_CAMPUS = (
    "curated:cipher-digital-barber-lake-colorado-city-texas-data-center-campus"
)
BLACK_CAMPUS = "curated:cipher-digital-black-pearl-wink-texas-data-center-campus"
MUSKOGEE_CAMPUS = (
    "curated:core-scientific-muskogee-oklahoma-data-center-campus"
)

PROJECT_KEYS = {
    BARBER_BUILDING: BARBER_CAMPUS + ":current-data-center-building",
    BARBER_PHASE_1: BARBER_CAMPUS + ":phase-1-contracted-capacity-component",
    BARBER_PHASE_2: BARBER_CAMPUS + ":phase-2-contracted-capacity-component",
    BLACK_PHASE_1: BLACK_CAMPUS + ":aws-phase-1-retrofit",
    BLACK_PHASE_2: BLACK_CAMPUS + ":aws-phase-2-site-preparation",
    MUSKOGEE_BUILDING_2: MUSKOGEE_CAMPUS + ":building-2-current-construction",
}

SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "projects",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class CipherAndCoreOfficialSourceTests(unittest.TestCase):
    def _path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def _block_network(self, stack: ExitStack) -> None:
        error = AssertionError("network used")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))

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
        self, source_order: Iterable[str]
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            self._block_network(stack)
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                for name in source_order:
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    self.assertEqual(result.warnings, ())

                self.assertEqual(validate_database(connection), [])
                expected_counts = {
                    "evidence": 5,
                    "entities": 9,
                    "campuses": 3,
                    "projects": 6,
                    "entity_snapshots": 9,
                    "lifecycle_observations": 4,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 5,
                }
                for table, expected in expected_counts.items():
                    observed = connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    self.assertEqual(observed, expected, table)

                lifecycle = {
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, l.status, l.as_of_date, l.method
                        FROM lifecycle_observations AS l
                        JOIN entities AS e ON e.id = l.entity_id
                        """
                    )
                }
                self.assertEqual(
                    lifecycle,
                    {
                        (
                            PROJECT_KEYS[BARBER_BUILDING],
                            "shell",
                            "2026-05-05",
                            "authoritative_physical_status_update",
                        ),
                        (
                            PROJECT_KEYS[BLACK_PHASE_1],
                            "under_construction",
                            "2026-05-05",
                            "authoritative_physical_status_update",
                        ),
                        (
                            PROJECT_KEYS[BLACK_PHASE_2],
                            "site_preparation",
                            "2026-05-05",
                            "authoritative_construction_start",
                        ),
                        (
                            PROJECT_KEYS[MUSKOGEE_BUILDING_2],
                            "under_construction",
                            "2026-05-06",
                            "authoritative_construction_start",
                        ),
                    },
                )

                capacities = {
                    (row[0], row[1], row[2], float(row[3]))
                    for row in connection.execute(
                        """
                        SELECT e.stable_key, c.metric, c.stage, c.base
                        FROM capacity_estimates AS c
                        JOIN entities AS e ON e.id = c.entity_id
                        """
                    )
                }
                self.assertEqual(
                    capacities,
                    {
                        (BARBER_CAMPUS, "gross_facility_mw", "planned", 300.0),
                        (
                            PROJECT_KEYS[BARBER_PHASE_1],
                            "gross_facility_mw",
                            "planned",
                            244.0,
                        ),
                        (
                            PROJECT_KEYS[BARBER_PHASE_1],
                            "critical_it_mw",
                            "planned",
                            168.0,
                        ),
                        (
                            PROJECT_KEYS[BARBER_PHASE_2],
                            "gross_facility_mw",
                            "planned",
                            56.0,
                        ),
                        (
                            PROJECT_KEYS[BARBER_PHASE_2],
                            "critical_it_mw",
                            "planned",
                            39.0,
                        ),
                    },
                )
                self.assertEqual(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM entity_snapshots
                        WHERE latitude IS NOT NULL
                           OR longitude IS NOT NULL
                           OR geometry_json IS NOT NULL
                        """
                    ).fetchone()[0],
                    0,
                )

                frozen = self._state(connection)
                for name in SOURCE_ORDER:
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection,
                        self._path(name),
                        retrieved_at=RETRIEVED_AT,
                    )
                    self.assertEqual(result.entities_created, 0)
                    self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(result.warnings, ())
                self.assertEqual(self._state(connection), frozen)
                self.assertEqual(validate_database(connection), [])
                return frozen
            finally:
                connection.close()

    def test_files_are_canonical_byte_pinned_and_capture_bound(self) -> None:
        evidence_records: dict[str, dict[str, Any]] = {}
        appearances: dict[str, set[str]] = {}
        for name in SOURCE_ORDER:
            path = self._path(name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                SOURCE_SHA256[name],
            )
            text = path.read_text(encoding="utf-8")
            document = json.loads(text)
            self.assertEqual(
                text,
                json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            )
            self.assertEqual(document["schema_version"], "1.0")
            self.assertEqual(
                {item["retrieved_at"] for item in document["evidence"]},
                {RETRIEVED_AT},
            )
            self.assertEqual(document["project"]["stable_key"], PROJECT_KEYS[name])
            for entity in (document["campus"], document["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])

            for record in document["evidence"]:
                key = record["key"]
                if key in evidence_records:
                    self.assertEqual(record, evidence_records[key])
                else:
                    evidence_records[key] = record
                appearances.setdefault(key, set()).add(name)

        self.assertEqual(set(evidence_records), set(CAPTURE_FACTS))
        self.assertEqual(
            {key: len(names) for key, names in appearances.items()},
            {
                Q1_KEY: 3,
                SEPTEMBER_KEY: 1,
                NOVEMBER_KEY: 2,
                FORM_10K_KEY: 5,
                CORE_KEY: 1,
            },
        )
        for key, expected in CAPTURE_FACTS.items():
            record = evidence_records[key]
            metadata = record["metadata"]
            self.assertEqual(record["content_hash"], expected["content_hash"])
            self.assertEqual(record["source_url"], expected["url"])
            self.assertEqual(
                metadata["content_hash_scope"],
                (
                    f"SHA-256 of the exact {expected['body_bytes']}-byte "
                    "content-decoded official SEC-hosted HTML response body captured "
                    "with curl --compressed"
                ),
            )
            self.assertEqual(
                metadata["capture_headers_scope"],
                (
                    f"SHA-256 of the exact {expected['headers_bytes']}-byte raw "
                    "HTTP response-header capture"
                ),
            )
            self.assertEqual(
                metadata["capture_headers_sha256"], expected["headers_hash"]
            )
            self.assertEqual(metadata["http_status"], 200)
            self.assertEqual(metadata["content_type"], "text/html")
            self.assertEqual(metadata["content_encoding_as_received"], "gzip")
            self.assertIsNone(metadata["http_transfer_encoding_as_received"])
            self.assertEqual(
                metadata["http_content_length_bytes_as_received"],
                expected["download_bytes"],
            )
            self.assertEqual(
                metadata["curl_size_download_bytes_as_received"],
                expected["download_bytes"],
            )
            self.assertEqual(
                metadata["response_http_date"], expected["response_date"]
            )
            self.assertEqual(
                metadata["http_last_modified_at"], expected["last_modified"]
            )
            self.assertEqual(metadata["requested_url"], expected["url"])
            self.assertEqual(metadata["effective_url"], expected["url"])
            self.assertEqual(metadata["redirect_count"], 0)
            self.assertEqual(metadata["response_header_blocks"], 1)

    def test_barber_capacity_hierarchy_is_explicit_and_nonadditive(self) -> None:
        building = self._load(BARBER_BUILDING)
        phase_1 = self._load(BARBER_PHASE_1)
        phase_2 = self._load(BARBER_PHASE_2)
        documents = (building, phase_1, phase_2)

        for document in documents:
            self.assertEqual(document["campus"]["stable_key"], BARBER_CAMPUS)
            self.assertEqual(document["campus"]["roles"], {})
            self.assertEqual(document["project"]["roles"], {})
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            normalized_roles = json.dumps(
                {
                    "campus": document["campus"]["roles"],
                    "project": document["project"]["roles"],
                }
            ).lower()
            self.assertNotIn("fluidstack", normalized_roles)
            self.assertNotIn("google", normalized_roles)
            self.assertNotIn('"user"', normalized_roles)

        self.assertEqual(
            building["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "shell",
                    "evidence_key": Q1_KEY,
                    "as_of_date": "2026-05-05",
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(phase_1["lifecycle"], [])
        self.assertEqual(phase_2["lifecycle"], [])

        def indexed(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
            return {row["metric"]: row for row in document["capacities"]}

        end_state = indexed(building)
        p1 = indexed(phase_1)
        p2 = indexed(phase_2)
        self.assertEqual(set(end_state), {"gross_facility_mw"})
        self.assertEqual(end_state["gross_facility_mw"]["entity"], "campus")
        self.assertEqual(end_state["gross_facility_mw"]["base"], 300)
        self.assertEqual(
            {metric: row["base"] for metric, row in p1.items()},
            {"gross_facility_mw": 244, "critical_it_mw": 168},
        )
        self.assertEqual(
            {metric: row["base"] for metric, row in p2.items()},
            {"gross_facility_mw": 56, "critical_it_mw": 39},
        )
        self.assertEqual(
            p1["gross_facility_mw"]["base"] + p2["gross_facility_mw"]["base"],
            end_state["gross_facility_mw"]["base"],
        )
        self.assertEqual(
            p1["critical_it_mw"]["base"] + p2["critical_it_mw"]["base"],
            207,
        )
        for document in documents:
            for row in document["capacities"]:
                self.assertEqual(row["stage"], "planned")
                self.assertEqual(row["target_date"], None)
                self.assertEqual([row["low"], row["base"], row["high"]], [row["base"]] * 3)
        self.assertIn(
            "contains",
            end_state["gross_facility_mw"]["notes"],
        )
        self.assertIn("not additive", end_state["gross_facility_mw"]["notes"])
        self.assertIn(
            "must not be summed again",
            phase_2["evidence"][0]["metadata"]["nesting_guardrail"],
        )

    def test_black_pearl_phases_do_not_inherit_mining_operation(self) -> None:
        phase_1 = self._load(BLACK_PHASE_1)
        phase_2 = self._load(BLACK_PHASE_2)
        self.assertNotEqual(
            phase_1["project"]["stable_key"], phase_2["project"]["stable_key"]
        )
        for document in (phase_1, phase_2):
            self.assertEqual(document["campus"]["stable_key"], BLACK_CAMPUS)
            self.assertEqual(document["campus"]["roles"], {})
            self.assertEqual(
                document["project"]["roles"],
                {"tenant": ["Amazon Web Services, Inc."]},
            )
            self.assertNotIn("user", document["project"]["roles"])
            self.assertNotIn("customer", document["project"]["roles"])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["capacities"], [])
            self.assertNotEqual(document["lifecycle"][0]["value"], "operational")
            metadata = {
                record["key"]: record["metadata"] for record in document["evidence"]
            }
            self.assertIn(
                "do not inherit",
                metadata[FORM_10K_KEY]["black_pearl_mining_guardrail"],
            )
            self.assertIn(
                "create no rows",
                metadata[FORM_10K_KEY]["black_pearl_capacity_guardrail"],
            )
            self.assertIn(
                "distinct physical-construction projects",
                metadata[Q1_KEY]["phase_identity_guardrail"],
            )
        self.assertEqual(phase_1["lifecycle"][0]["value"], "under_construction")
        self.assertEqual(
            phase_1["lifecycle"][0]["method"],
            "authoritative_physical_status_update",
        )
        self.assertEqual(phase_2["lifecycle"][0]["value"], "site_preparation")
        self.assertEqual(
            phase_2["lifecycle"][0]["method"],
            "authoritative_construction_start",
        )

    def test_muskogee_building_2_is_unleased_and_82_5_mw_is_untyped(self) -> None:
        document = self._load(MUSKOGEE_BUILDING_2)
        self.assertEqual(document["campus"]["stable_key"], MUSKOGEE_CAMPUS)
        self.assertEqual(document["campus"]["roles"], {})
        self.assertEqual(document["project"]["roles"], {})
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])
        self.assertEqual(document["lifecycle"][0]["value"], "under_construction")
        self.assertEqual(document["lifecycle"][0]["as_of_date"], "2026-05-06")
        metadata = document["evidence"][0]["metadata"]
        self.assertEqual(metadata["untyped_capacity_as_reported_mw"], 82.5)
        self.assertIn("explicitly unleased", metadata["lease_scope"])
        self.assertIn("creates no capacity row", metadata["untyped_capacity_guardrail"])
        for excluded in ("440 MW", "1.5 GW", "1.0 GW", "70 MW"):
            self.assertIn(excluded, metadata["other_capacity_exclusions"])

    def test_offline_import_is_valid_idempotent_and_order_independent(self) -> None:
        forward = self._build(SOURCE_ORDER)
        reverse = self._build(reversed(SOURCE_ORDER))
        self.assertEqual(forward, reverse)


if __name__ == "__main__":
    unittest.main()
