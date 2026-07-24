from __future__ import annotations

import copy
import hashlib
import itertools
import json
import socket
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).parents[1]
V17_DEFINITION = "open-seed-2026-07-19-v17.json"
V18_DEFINITION = "open-seed-2026-07-19-v18.json"
PDG_SOURCE = "curated-official-2026-07-19-pdg-jc4-greater-jakarta.json"
SG1_SOURCE = "curated-official-2026-07-19-dayone-sg1-singapore.json"
TOKYO_SOURCE = "curated-official-2026-07-19-dayone-gaw-tokyo-phase-one.json"
CHONBURI_SOURCE = "curated-official-2026-07-19-dayone-chonburi-ctp1.json"

CHONBURI_2025_EVIDENCE = (
    "dayone-chonburi-ctp1-under-construction-2025-11-10-captured-2026-07-19"
)
CHONBURI_2026_EVIDENCE = (
    "dayone-chonburi-ctp1-progress-update-2026-04-25-captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    PDG_SOURCE: {
        "sha256": "de4e6ea4997d572d76701564602d185870e21e9e70902929d6d57132d0ca03d0",
        "retrieved_at": "2026-07-19T19:48:28Z",
        "country": "Indonesia",
        "address": (
            "Greenland International Industrial Center, Bekasi Regency, "
            "Greater Jakarta, Indonesia"
        ),
        "campus_key": "curated:pdg-jc4-greater-jakarta-campus",
        "project_key": (
            "curated:pdg-jc4-greater-jakarta-campus:current-campus-build"
        ),
        "project_name": "PDG JC4 Greater Jakarta Current Campus Build",
        "lifecycle_date": "2026-04-30",
        "lifecycle_method": "authoritative_construction_start",
        "capacity": None,
        "evidence_keys": (
            "pdg-jc4-greater-jakarta-construction-2026-04-30-captured-2026-07-19",
        ),
    },
    SG1_SOURCE: {
        "sha256": "0ff2f288415ffab9aca036fb8c28cc8598cde1c14a12e0c33c8672caf16bfdd6",
        "retrieved_at": "2026-07-19T19:48:28Z",
        "country": "Singapore",
        "address": "Singapore",
        "campus_key": "curated:dayone-sg1-singapore-data-center",
        "project_key": (
            "curated:dayone-sg1-singapore-data-center:current-facility-build"
        ),
        "project_name": "DayOne SG1 Singapore Current Facility Build",
        "lifecycle_date": "2025-07-25",
        "lifecycle_method": "authoritative_construction_start",
        "capacity": None,
        "evidence_keys": (
            "dayone-sg1-singapore-groundbreaking-2025-07-25-captured-2026-07-19",
        ),
    },
    TOKYO_SOURCE: {
        "sha256": "d2b4b73e1de5c61524af90d805e11c5a6a183949fbf90415d6fec96030d20529",
        "retrieved_at": "2026-07-19T19:48:30Z",
        "country": "Japan",
        "address": "Fuchu Intelligent Park, Fuchu City, Tokyo, Japan",
        "campus_key": "curated:dayone-gaw-fuchu-tokyo-data-center-campus",
        "project_key": (
            "curated:dayone-gaw-fuchu-tokyo-data-center-campus:phase-one-building"
        ),
        "project_name": "DayOne Gaw Fuchu Tokyo Phase One Building",
        "lifecycle_date": "2025-08-01",
        "lifecycle_method": "authoritative_construction_start",
        "capacity": 18.0,
        "evidence_keys": (
            "dayone-gaw-tokyo-phase-one-groundbreaking-2025-08-01-captured-2026-07-19",
        ),
    },
    CHONBURI_SOURCE: {
        "sha256": "42cf9d67828563e92cc0b80ae30cfdf0d3a9849f19612b3ff7eaee4ee54889d4",
        "retrieved_at": "2026-07-19T19:48:32Z",
        "country": "Thailand",
        "address": "Amata City, Chonburi, Thailand",
        "campus_key": "curated:dayone-chonburi-tech-park-campus",
        "project_key": (
            "curated:dayone-chonburi-tech-park-campus:ctp1-current-development"
        ),
        "project_name": "DayOne Chonburi CTP1 Current Development",
        "lifecycle_date": "2026-04-25",
        "lifecycle_method": "authoritative_physical_status_update",
        "capacity": None,
        "evidence_keys": (CHONBURI_2025_EVIDENCE, CHONBURI_2026_EVIDENCE),
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "7e26ac51d2c22892ee65a5e8a5c5f170dea21ff50649800154c64006e17b6596": {
        "body_bytes": 75881,
        "headers_bytes": 327,
        "headers_sha256": (
            "49b77986346c83765daec697ca0142af005f9691f0e698295ccebdd840e35c88"
        ),
        "response_date": "2026-07-19T19:48:28Z",
        "last_modified": "2026-06-29T09:14:07Z",
        "content_type": "text/html; charset=UTF-8",
        "url": (
            "https://princetondg.com/newsroom/pdg-acquires-240-mw-of-powered-"
            "land-in-jakarta-advancing-its-rapid-expansion-across-asia/"
        ),
    },
    "d6677c822b4b8d9689cba36db7dd44ab23f85048eb8ea43ea04afbd2b423aa41": {
        "body_bytes": 108986,
        "headers_bytes": 1150,
        "headers_sha256": (
            "0e0de337159b6275b4ff56e16c2a569b8d763830dea9b4b72be2022e84b5ac3c"
        ),
        "response_date": "2026-07-19T19:48:28Z",
        "last_modified": None,
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://dayonedc.com/markets/"
            "singapores-dayone-breaks-ground-on-first-data-center-in-singapore"
        ),
    },
    "c6080cd681de2fce2771cb466a2f945ed7da85213d0213f4aa778ae85a5dce1b": {
        "body_bytes": 71854,
        "headers_bytes": 1238,
        "headers_sha256": (
            "02a7207e05ef770a174e25bd6edf0434b8feaa89490baf792a664019838a8de5"
        ),
        "response_date": "2026-07-19T19:48:30Z",
        "last_modified": None,
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://dayonedc.com/markets/dayone-and-gaw-capital-break-ground-"
            "on-phase-one-of-hyperscale-tokyo-data-center-campus"
        ),
    },
    "cd42f02c8e363a14dd68300fb3b596f31620e3c031556f28b2105b64726f6d32": {
        "body_bytes": 86913,
        "headers_bytes": 1394,
        "headers_sha256": (
            "a6f8092864078c2c9f3d304e96f91ea87163f471d426dd47e12066d3820ad4ab"
        ),
        "response_date": "2026-07-19T19:48:31Z",
        "last_modified": None,
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://dayonedc.com/headliners/dayone-strengthens-thailands-"
            "digital-hub-with-amata-as-chonburi-campus-expands-toward-the-"
            "countrys-first-1gw-power-platform"
        ),
    },
    "2a55761f18d8bee2419528a3caf4281b3b4e49689033d13e1ee70acd8910aa5c": {
        "body_bytes": 107864,
        "headers_bytes": 1402,
        "headers_sha256": (
            "0df0ebc387669275ca9cb28c8d9293ed0b7465fefd3c6da8317b874ac8f7590b"
        ),
        "response_date": "2026-07-19T19:48:32Z",
        "last_modified": None,
        "content_type": "text/html; charset=utf-8",
        "url": (
            "https://dayonedc.com/markets/dayone-launches-inaugural-tech-ai-"
            "career-expo-in-thailand-showcasing-commitment-to-digital-"
            "infrastructure-and-talent-development"
        ),
    },
}


class PdgDayOneNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_guardrails(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")
        if tuple(row["key"] for row in document["evidence"]) != expected[
            "evidence_keys"
        ]:
            raise AssertionError("exact evidence set and semantic order must remain")
        if any(row["kind"] != "company_disclosure" for row in document["evidence"]):
            raise AssertionError("evidence must remain company disclosure only")

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["country"] != expected["country"]:
                raise AssertionError("country must remain source explicit")
            if entity["address"] != expected["address"]:
                raise AssertionError("address must remain authoritative locality only")
            if entity["roles"] != {}:
                raise AssertionError("roles must remain empty")
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise AssertionError("authoritative localities must remain ungeocoded")
            if entity["method"] != "authoritative_locality":
                raise AssertionError("snapshot method must remain authoritative locality")
        if document["campus"]["stable_key"] != expected["campus_key"]:
            raise AssertionError("canonical campus identity must remain")
        if (
            document["project"]["stable_key"] != expected["project_key"]
            or document["project"]["name"] != expected["project_name"]
        ):
            raise AssertionError("canonical current-project identity must remain")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1 or lifecycle[0]["entity"] != "project":
            raise AssertionError("one project lifecycle observation must remain")
        if (
            lifecycle[0]["value"] != "under_construction"
            or lifecycle[0]["as_of_date"] != expected["lifecycle_date"]
            or lifecycle[0]["method"] != expected["lifecycle_method"]
        ):
            raise AssertionError("generic construction lifecycle must remain exact")
        if name == CHONBURI_SOURCE and lifecycle[0]["evidence_key"] != CHONBURI_2026_EVIDENCE:
            raise AssertionError("latest Chonburi physical update must control lifecycle")

        if document["operating_models"]:
            raise AssertionError("operating models must remain empty")
        if document["workloads"]:
            raise AssertionError("capability and market language must not become workloads")

        capacity = expected["capacity"]
        if capacity is None:
            if document["capacities"]:
                raise AssertionError("untyped or inexact power claims create no capacity rows")
        else:
            if len(document["capacities"]) != 1:
                raise AssertionError("only one Phase One critical-IT capacity must remain")
            row = document["capacities"][0]
            if (
                row["entity"] != "project"
                or row["metric"] != "critical_it_mw"
                or row["stage"] != "planned"
                or row["unit"] != "MW"
                or (row["low"], row["base"], row["high"])
                != (capacity, capacity, capacity)
                or row["method"] != "reported"
                or row["as_of_date"] != "2025-08-01"
                or row["target_date"] is not None
            ):
                raise AssertionError("Phase One critical-IT capacity must remain exact")

        for evidence in document["evidence"]:
            metadata = evidence["metadata"]
            if "normalized workload" not in metadata["classification_guardrail"]:
                raise AssertionError("classification exclusions must remain explicit")
            if "installed hardware model" not in metadata["classification_guardrail"]:
                raise AssertionError("hardware-model exclusion must remain explicit")
            if "No satellite imagery" not in metadata["imagery_guardrail"]:
                raise AssertionError("imagery non-use must remain explicit")
            if "not redistributed" not in metadata["rights_scope"]:
                raise AssertionError("rights scope must remain explicit")
            if "not normalized" not in metadata["role_guardrail"]:
                raise AssertionError("role exclusion must remain explicit")

        if name == PDG_SOURCE:
            metadata = document["evidence"][0]["metadata"]
            if metadata["construction_wording_as_reported"] != (
                "Construction has already commenced."
            ):
                raise AssertionError("PDG explicit construction wording must remain")
            if (
                metadata["planned_capacity_as_reported_mw"] != 240
                or metadata["building_count_as_reported"] != 4
                or metadata["per_building_capacity_as_reported_mw"] != 60
                or "untyped evidence metadata" not in metadata["capacity_metric_guardrail"]
            ):
                raise AssertionError("PDG power claims must remain untyped metadata")
        elif name == SG1_SOURCE:
            metadata = document["evidence"][0]["metadata"]
            if (
                metadata["facility_capacity_as_reported_mw"] != 20
                or "untyped evidence metadata" not in metadata["capacity_metric_guardrail"]
                or metadata["ready_for_service_forecast_as_reported"] != "2026"
                or "future forecast" not in metadata["forecast_guardrail"]
            ):
                raise AssertionError("SG1 capacity and RFS must remain excluded metadata")
            energy = metadata["energy_wording_as_reported"]
            if energy["power_purchase_agreement_term_years"] != 10:
                raise AssertionError("SG1 energy wording must remain source scoped")
            for token in ("PPA", "renewable-energy certificates", "SOFC"):
                if token not in metadata["energy_guardrail"]:
                    raise AssertionError("SG1 energy exclusions must remain explicit")
        elif name == TOKYO_SOURCE:
            metadata = document["evidence"][0]["metadata"]
            if (
                metadata["phase_one_it_capacity_as_reported_mw"] != 18
                or "planned project critical_it_mw" not in metadata[
                    "phase_one_capacity_scope"
                ]
                or metadata["campus_total_it_capacity_as_reported_mw"] != 80
                or "double count" not in metadata["campus_capacity_guardrail"]
                or metadata["core_and_shell_forecast_as_reported"] != "mid-2027"
            ):
                raise AssertionError("Tokyo Phase One scope and forecast must remain exact")
        elif name == CHONBURI_SOURCE:
            old_metadata = document["evidence"][0]["metadata"]
            current_metadata = document["evidence"][1]["metadata"]
            if (
                old_metadata["ctp1_status_wording_as_reported"]
                != "CTP1 already under construction"
                or current_metadata["development_progress_wording_as_reported"]
                != "The development is progressing toward a multi-phase rollout"
                or "April 25, 2026" not in current_metadata["status_scope"]
            ):
                raise AssertionError("Chonburi two-source status semantics must remain")
            if (
                old_metadata["ctp1_site_power_capacity_as_reported_mw"] != 300
                or old_metadata["unified_power_platform_as_reported_gw"] != 1
                or "untyped evidence metadata" not in old_metadata[
                    "power_metric_guardrail"
                ]
                or "more than 100 MW" not in current_metadata[
                    "expected_it_capacity_inequality_as_reported"
                ]
                or "inequality" not in current_metadata["capacity_guardrail"]
            ):
                raise AssertionError("Chonburi power claims must remain excluded metadata")
            if (
                "future development" not in old_metadata["ctp2_guardrail"]
                or "creates no entity" not in old_metadata["ctp2_guardrail"]
            ):
                raise AssertionError("future CTP2 must remain excluded")

    def _database_state(
        self,
        order: tuple[str, ...] | list[str],
        *,
        overrides: dict[str, Path] | None = None,
    ) -> tuple[list[tuple[Any, ...]], ...]:
        overrides = overrides or {}
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name in order:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            overrides.get(name, ROOT / "sources" / name),
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                self.assertEqual(validate_database(connection), [])
                return (
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, stable_key, created_at FROM entities "
                            "ORDER BY kind, stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, source_url, published_at, retrieved_at, "
                            "content_hash, metadata_json FROM evidence "
                            "ORDER BY content_hash"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, name, latitude, longitude, "
                            "geometry_json, tags_json, as_of_date, recorded_at, method "
                            "FROM entity_snapshots JOIN entities "
                            "ON entities.id = entity_snapshots.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, "
                            "recorded_at, method FROM lifecycle_observations "
                            "JOIN entities ON entities.id = "
                            "lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, metric, stage, low, base, "
                            "high, unit, as_of_date, recorded_at, target_date, notes "
                            "FROM capacity_estimates JOIN entities "
                            "ON entities.id = capacity_estimates.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                )
            finally:
                connection.close()

    def test_exact_sources_import_offline_with_narrow_semantics(self) -> None:
        for baseline_name in (V17_DEFINITION, V18_DEFINITION):
            baseline = (ROOT / "sources" / baseline_name).read_text(encoding="utf-8")
            for name, expected in SOURCES.items():
                self.assertNotIn(name, baseline)
                self.assertNotIn(expected["campus_key"], baseline)
                self.assertNotIn(expected["project_key"], baseline)

        documents = {name: self._load(name) for name in SOURCES}
        seen_captures: set[str] = set()
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    for name, expected in SOURCES.items():
                        source_path = ROOT / "sources" / name
                        self.assertEqual(
                            hashlib.sha256(source_path.read_bytes()).hexdigest(),
                            expected["sha256"],
                        )
                        document = documents[name]
                        self._assert_guardrails(name, document)
                        self.assertEqual(
                            {row["retrieved_at"] for row in document["evidence"]},
                            {expected["retrieved_at"]},
                        )
                        for evidence in document["evidence"]:
                            capture = CAPTURES[evidence["content_hash"]]
                            metadata = evidence["metadata"]
                            self.assertEqual(
                                metadata["content_hash_verification"],
                                "fetched_bytes_sha256",
                            )
                            self.assertIn(
                                str(capture["body_bytes"]),
                                metadata["content_hash_scope"],
                            )
                            self.assertIn(
                                str(capture["headers_bytes"]),
                                metadata["capture_headers_scope"],
                            )
                            self.assertEqual(
                                metadata["capture_headers_sha256"],
                                capture["headers_sha256"],
                            )
                            self.assertEqual(metadata["http_status"], 200)
                            self.assertEqual(
                                metadata["response_http_date"],
                                capture["response_date"],
                            )
                            self.assertEqual(
                                metadata["http_last_modified_at"],
                                capture["last_modified"],
                            )
                            self.assertEqual(
                                metadata["content_type"], capture["content_type"]
                            )
                            self.assertEqual(
                                metadata["content_encoding_as_received"], "gzip"
                            )
                            self.assertIsNone(
                                metadata["http_content_length_bytes_as_received"]
                            )
                            self.assertEqual(metadata["response_header_blocks"], 1)
                            self.assertEqual(evidence["source_url"], capture["url"])
                            for key in ("requested_url", "effective_url", "canonical_url"):
                                self.assertEqual(metadata[key], capture["url"])
                            self.assertNotIn("request_started_at", metadata)
                            self.assertNotIn("request_start_utc", metadata)
                            self.assertIn(
                                "no request-start artifact was supplied",
                                metadata["retrieval_method"],
                            )
                            seen_captures.add(evidence["content_hash"])

                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            source_path,
                            retrieved_at=expected["retrieved_at"],
                        )

                self.assertEqual(seen_captures, set(CAPTURES))
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, COUNT(*) FROM entities "
                            "GROUP BY kind ORDER BY kind"
                        )
                    ],
                    [("campus", 4), ("project", 4)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT status, COUNT(*) FROM lifecycle_observations "
                            "GROUP BY status ORDER BY status"
                        )
                    ],
                    [("under_construction", 4)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    sorted(
                        (
                            expected["project_key"],
                            "under_construction",
                            expected["lifecycle_date"],
                            expected["lifecycle_method"],
                        )
                        for expected in SOURCES.values()
                    ),
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, metric, stage, low, base, "
                            "high, unit, as_of_date, target_date "
                            "FROM capacity_estimates JOIN entities "
                            "ON entities.id = capacity_estimates.entity_id"
                        )
                    ],
                    [
                        (
                            SOURCES[TOKYO_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            18.0,
                            18.0,
                            18.0,
                            "MW",
                            "2025-08-01",
                            None,
                        )
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots"
                    ).fetchone()[0],
                    8,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                for row in connection.execute("SELECT tags_json FROM entity_snapshots"):
                    tags = json.loads(row["tags_json"])
                    self.assertFalse(any(key.startswith("role:") for key in tags))
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence "
                        "WHERE kind = 'satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_all_source_orders_and_chonburi_evidence_orders_are_invariant(self) -> None:
        names = tuple(SOURCES)
        expected_state = self._database_state(names)
        for order in itertools.permutations(names):
            with self.subTest(source_order=order):
                self.assertEqual(self._database_state(order), expected_state)

        chonburi = self._load(CHONBURI_SOURCE)
        reversed_document = copy.deepcopy(chonburi)
        reversed_document["evidence"].reverse()
        with tempfile.TemporaryDirectory() as temporary:
            reversed_path = Path(temporary) / "reversed-chonburi-evidence.json"
            reversed_path.write_text(
                json.dumps(reversed_document, indent=2) + "\n", encoding="utf-8"
            )
            canonical = self._database_state((CHONBURI_SOURCE,))
            reversed_state = self._database_state(
                (CHONBURI_SOURCE,), overrides={CHONBURI_SOURCE: reversed_path}
            )
        self.assertEqual(reversed_state, canonical)

    def test_semantic_mutations_fail_guardrails(self) -> None:
        documents = {name: self._load(name) for name in SOURCES}
        mutations: list[tuple[str, dict[str, Any], str]] = []

        for name, value in ((PDG_SOURCE, 240), (SG1_SOURCE, 20), (CHONBURI_SOURCE, 100)):
            mutated = copy.deepcopy(documents[name])
            mutated["capacities"] = [
                {
                    "entity": "project",
                    "metric": "critical_it_mw",
                    "stage": "planned",
                    "unit": "MW",
                    "low": value,
                    "base": value,
                    "high": value,
                    "method": "reported",
                    "confidence": 0.5,
                    "evidence_key": mutated["evidence"][-1]["key"],
                    "as_of_date": SOURCES[name]["lifecycle_date"],
                    "target_date": None,
                }
            ]
            mutations.append(
                (
                    name,
                    mutated,
                    "untyped or inexact power claims create no capacity rows",
                )
            )

        mutated = copy.deepcopy(documents[TOKYO_SOURCE])
        campus_capacity = copy.deepcopy(mutated["capacities"][0])
        campus_capacity.update({"entity": "campus", "low": 80, "base": 80, "high": 80})
        mutated["capacities"].append(campus_capacity)
        mutations.append(
            (TOKYO_SOURCE, mutated, "only one Phase One critical-IT capacity must remain")
        )

        mutated = copy.deepcopy(documents[TOKYO_SOURCE])
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(
            (TOKYO_SOURCE, mutated, "Phase One critical-IT capacity must remain exact")
        )

        mutated = copy.deepcopy(documents[CHONBURI_SOURCE])
        mutated["lifecycle"][0].update(
            {
                "evidence_key": CHONBURI_2025_EVIDENCE,
                "as_of_date": "2025-11-10",
                "method": "authoritative_construction_start",
            }
        )
        mutations.append(
            (CHONBURI_SOURCE, mutated, "generic construction lifecycle must remain exact")
        )

        mutated = copy.deepcopy(documents[CHONBURI_SOURCE])
        mutated["project"]["stable_key"] = (
            "curated:dayone-chonburi-tech-park-campus:ctp2-future-development"
        )
        mutations.append(
            (CHONBURI_SOURCE, mutated, "canonical current-project identity must remain")
        )

        mutated = copy.deepcopy(documents[CHONBURI_SOURCE])
        mutated["evidence"] = [mutated["evidence"][1]]
        mutations.append(
            (CHONBURI_SOURCE, mutated, "exact evidence set and semantic order must remain")
        )

        mutated = copy.deepcopy(documents[SG1_SOURCE])
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2025-07-25",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append(
            (
                SG1_SOURCE,
                mutated,
                "capability and market language must not become workloads",
            )
        )

        mutated = copy.deepcopy(documents[SG1_SOURCE])
        mutated["operating_models"] = [
            {
                "entity": "project",
                "value": "hyperscale",
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2025-07-25",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append((SG1_SOURCE, mutated, "operating models must remain empty"))

        mutated = copy.deepcopy(documents[TOKYO_SOURCE])
        mutated["project"]["roles"] = {"contractor": ["HASEKO Corporation"]}
        mutations.append((TOKYO_SOURCE, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(documents[PDG_SOURCE])
        mutated["campus"]["coordinates"] = {
            "latitude": -6.3,
            "longitude": 107.1,
        }
        mutations.append(
            (PDG_SOURCE, mutated, "authoritative localities must remain ungeocoded")
        )

        mutated = copy.deepcopy(documents[PDG_SOURCE])
        mutated["evidence"][0]["kind"] = "satellite_imagery"
        mutations.append(
            (PDG_SOURCE, mutated, "evidence must remain company disclosure only")
        )

        for name, document, message in mutations:
            with self.subTest(source=name, rejection=message):
                with self.assertRaisesRegex(AssertionError, message):
                    self._assert_guardrails(name, document)


if __name__ == "__main__":
    unittest.main()
