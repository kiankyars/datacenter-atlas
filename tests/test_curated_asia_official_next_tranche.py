from __future__ import annotations

import copy
import hashlib
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
V15_DEFINITION = "open-seed-2026-07-19-v15.json"
JAKARTA_3_SOURCE = "curated-official-2026-07-19-stt-jakarta-3.json"
JAKARTA_5_SOURCE = "curated-official-2026-07-19-stt-jakarta-5.json"
JAKARTA_6_SOURCE = "curated-official-2026-07-19-stt-jakarta-6.json"
BANGKOK_2_SOURCE = "curated-official-2026-07-19-stt-bangkok-2.json"
JC3_SOURCE = "curated-official-2026-07-19-pdg-jc3-greater-jakarta.json"
SE1_SOURCE = "curated-official-2026-07-19-pdg-se1-incheon.json"
JAKARTA_CAMPUS_KEY = "curated:stt-jakarta-data-centre-campus"
JAKARTA_RELEASE_EVIDENCE_KEY = (
    "stt-jakarta-campus-expansion-2026-06-10-captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    JAKARTA_3_SOURCE: {
        "sha256": "34f5383be85da949e2453dd1a211e546341535dff5281c87a45b130ddb6cb96f",
        "retrieved_at": "2026-07-19T19:09:17Z",
        "country": "Indonesia",
        "address": "Cikarang, Greater Jakarta, Indonesia",
        "campus_key": JAKARTA_CAMPUS_KEY,
        "project_key": "curated:stt-jakarta-data-centre-campus:stt-jakarta-3",
        "project_name": "STT Jakarta 3",
        "lifecycle": (
            "shell",
            "2026-06-10",
            "authoritative_physical_status_update",
        ),
        "capacity": (24.0, "2026-07-16"),
        "evidence_count": 2,
    },
    JAKARTA_5_SOURCE: {
        "sha256": "05c5198220c2f7616c715c566044c67776a135be7e99c3aa4ce543e5e951b258",
        "retrieved_at": "2026-07-19T19:09:17Z",
        "country": "Indonesia",
        "address": "Cikarang, Greater Jakarta, Indonesia",
        "campus_key": JAKARTA_CAMPUS_KEY,
        "project_key": "curated:stt-jakarta-data-centre-campus:stt-jakarta-5",
        "project_name": "STT Jakarta 5",
        "lifecycle": (
            "under_construction",
            "2026-06-10",
            "authoritative_construction_start",
        ),
        "capacity": (40.0, "2026-06-10"),
        "evidence_count": 1,
    },
    JAKARTA_6_SOURCE: {
        "sha256": "77e63e1cca648e4001d49ad44a35e73c0e33423f857f17c5e139eb7de29d3459",
        "retrieved_at": "2026-07-19T19:09:17Z",
        "country": "Indonesia",
        "address": "Cikarang, Greater Jakarta, Indonesia",
        "campus_key": JAKARTA_CAMPUS_KEY,
        "project_key": "curated:stt-jakarta-data-centre-campus:stt-jakarta-6",
        "project_name": "STT Jakarta 6",
        "lifecycle": (
            "under_construction",
            "2026-06-10",
            "authoritative_construction_start",
        ),
        "capacity": (40.0, "2026-06-10"),
        "evidence_count": 1,
    },
    BANGKOK_2_SOURCE: {
        "sha256": "4b2cbca170c62bd8ae2e20034416af4f44fefc5948ceb465fbe542a2dcbe3aa3",
        "retrieved_at": "2026-07-19T19:09:18Z",
        "country": "Thailand",
        "address": "Bangkok, Thailand",
        "campus_key": "curated:stt-bangkok-data-centre-campus",
        "project_key": "curated:stt-bangkok-data-centre-campus:stt-bangkok-2",
        "project_name": "STT Bangkok 2",
        "lifecycle": (
            "under_construction",
            "2025-03-03",
            "authoritative_construction_start",
        ),
        "capacity": (24.0, "2025-03-03"),
        "evidence_count": 1,
    },
    JC3_SOURCE: {
        "sha256": "44bc4fe172ca53320994815f64b6080c2d339f39d7fc04ec9439d8e51c650303",
        "retrieved_at": "2026-07-19T19:09:19Z",
        "country": "Indonesia",
        "address": (
            "Greenland International Industrial Center, Bekasi Regency, "
            "Greater Jakarta, Indonesia"
        ),
        "campus_key": "curated:pdg-jc3-greater-jakarta-campus",
        "project_key": (
            "curated:pdg-jc3-greater-jakarta-campus:current-campus-build"
        ),
        "project_name": "PDG JC3 Greater Jakarta Current Campus Build",
        "lifecycle": (
            "under_construction",
            "2025-11-19",
            "authoritative_construction_start",
        ),
        "capacity": None,
        "evidence_count": 1,
    },
    SE1_SOURCE: {
        "sha256": "3a68c5ff3c904bb30f4a03e24780b37a1598263b6cab0b34ae2c23cbb08ab419",
        "retrieved_at": "2026-07-19T19:09:20Z",
        "country": "South Korea",
        "address": "Incheon, South Korea",
        "campus_key": "curated:pdg-se1-incheon-campus",
        "project_key": "curated:pdg-se1-incheon-campus:se1-development",
        "project_name": "PDG SE1 Incheon Development",
        "lifecycle": (
            "announced",
            "2025-11-17",
            "authoritative_announcement",
        ),
        "capacity": None,
        "evidence_count": 1,
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "f56371010a4c86f72e48fec5078c3b0bb8441cf46d97fb43a1e85f52980fc676": {
        "body_bytes": 84369,
        "headers_bytes": 2980,
        "headers_sha256": (
            "dcbf6023dc77c11431d40b04c2f8581e7e3f4e1b8b83150f5b3f80f9563224bd"
        ),
        "response_date": "2026-07-19T19:09:17Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": None,
        "content_length": 84369,
        "url": (
            "https://www.sttelemediagdc.com/newsroom/"
            "stt-gdc-accelerates-jakarta-campus-expansion-power-indonesia-ai-"
            "and-digital-ambitions"
        ),
    },
    "79219de45833e9cdb149c37a1cfbc644ac805b2e7be7fbdbfcad6de90347a240": {
        "body_bytes": 1062613,
        "headers_bytes": 735,
        "headers_sha256": (
            "09cac1754820055e8a6919d9ddda5a45d56c2cf88fc8b5a33990684b6452de6f"
        ),
        "response_date": "2026-07-16T08:57:17Z",
        "last_modified": "2026-07-15T08:04:19Z",
        "content_type": "application/pdf",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://assets.sttelemediagdc.com/sttgdc/global_en/public/2026-07/"
            "STT_Jakarta_3_Factsheet-vJul2026.pdf"
        ),
    },
    "2f6ca0f848c46d410ae7225753082564611a25f3b9c33055c774ca3f984679bf": {
        "body_bytes": 70122,
        "headers_bytes": 2980,
        "headers_sha256": (
            "8d4af39bb5addc65f4459ba8a32fa856ea7bede282a24658802e7b15ab53a12d"
        ),
        "response_date": "2026-07-19T19:09:18Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": None,
        "content_length": 70122,
        "url": (
            "https://www.sttelemediagdc.com/th-en/newsroom/"
            "stt-gdc-thailand-commences-construction-stt-bangkok-2"
        ),
    },
    "f3deaad94be14f15372424f0adcfbcd56b8a3f93b50e92a50dab13c899beda6e": {
        "body_bytes": 74996,
        "headers_bytes": 327,
        "headers_sha256": (
            "3f7501387c4220c4b6153d32cfa78fa146c72faa839335f02af7b057211cb76e"
        ),
        "response_date": "2026-07-19T19:09:19Z",
        "last_modified": "2026-06-29T09:14:07Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://princetondg.com/newsroom/princeton-digital-group-breaks-"
            "ground-on-milestone-usd-1-billion-120-mw-greater-jakarta-campus/"
        ),
    },
    "31fb872992b9d43d9aefb9323a6365b13715b4eff75455fc2ed01346fb1c54ce": {
        "body_bytes": 74989,
        "headers_bytes": 327,
        "headers_sha256": (
            "69fff17cab292a493ae25a782597b2f75e09aa63720c195f2fd148ed7042009a"
        ),
        "response_date": "2026-07-19T19:09:20Z",
        "last_modified": "2026-06-29T09:14:26Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://princetondg.com/newsroom/"
            "pdg-enters-south-korea-with-usd-700-million-data-center-investment/"
        ),
    },
}


class AsiaOfficialNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_guardrails(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")
        if len(document["evidence"]) != expected["evidence_count"]:
            raise AssertionError("exact source evidence count must remain")
        if any(row["kind"] != "company_disclosure" for row in document["evidence"]):
            raise AssertionError("evidence must remain company disclosure only")

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["roles"] != {}:
                raise AssertionError("roles must remain empty")
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise AssertionError("authoritative localities must remain ungeocoded")
            if entity["method"] != "authoritative_locality":
                raise AssertionError("snapshot method must remain authoritative_locality")
            if entity["country"] != expected["country"]:
                raise AssertionError("country must remain source explicit")
            if entity["address"] != expected["address"]:
                raise AssertionError("address must remain authoritative locality only")
        if document["campus"]["stable_key"] != expected["campus_key"]:
            raise AssertionError("canonical campus identity must remain")
        if (
            document["project"]["stable_key"] != expected["project_key"]
            or document["project"]["name"] != expected["project_name"]
        ):
            raise AssertionError("distinct project identity must remain")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1 or lifecycle[0]["entity"] != "project":
            raise AssertionError("one project lifecycle observation must remain")
        expected_status, expected_date, expected_method = expected["lifecycle"]
        if (
            lifecycle[0]["value"] != expected_status
            or lifecycle[0]["as_of_date"] != expected_date
            or lifecycle[0]["method"] != expected_method
        ):
            raise AssertionError("lifecycle scope, date, and method must remain exact")

        if document["operating_models"]:
            raise AssertionError("operating models must remain empty")
        if document["workloads"]:
            raise AssertionError("design and market language must not become workloads")

        expected_capacity = expected["capacity"]
        capacities = document["capacities"]
        if expected_capacity is None:
            if capacities:
                raise AssertionError("untyped power claims must create no capacity rows")
        else:
            if len(capacities) != 1:
                raise AssertionError("one planned project critical-IT capacity must remain")
            value, capacity_date = expected_capacity
            row = capacities[0]
            if (
                row["entity"] != "project"
                or row["metric"] != "critical_it_mw"
                or row["stage"] != "planned"
                or row["unit"] != "MW"
                or (row["low"], row["base"], row["high"]) != (value,) * 3
                or row["method"] != "reported"
                or row["as_of_date"] != capacity_date
                or row["target_date"] is not None
            ):
                raise AssertionError("planned project critical-IT scope must remain exact")

        evidence = {row["key"]: row for row in document["evidence"]}
        if name in {JAKARTA_3_SOURCE, JAKARTA_5_SOURCE, JAKARTA_6_SOURCE}:
            shared = evidence[JAKARTA_RELEASE_EVIDENCE_KEY]["metadata"]
            if (
                shared["status_wording_as_reported"]["stt_jakarta_3"]
                != "the topping out of STT Jakarta 3"
                or "generic under_construction" not in shared["status_scope"]
                or shared["stt_jakarta_5_planned_it_load_as_reported_mw"] != 40
                or shared["stt_jakarta_6_planned_it_load_as_reported_mw"] != 40
            ):
                raise AssertionError("Jakarta project status and capacity scope must remain")
            if (
                "greater-than aggregate" not in shared["campus_pipeline_guardrail"]
                or "outside this construction tranche"
                not in shared["stt_jakarta_2_guardrail"]
            ):
                raise AssertionError("Jakarta aggregate and J2 exclusions must remain")
        if name == JAKARTA_3_SOURCE:
            factsheet_evidence = evidence[
                "stt-jakarta-3-factsheet-july-2026-captured-2026-07-19"
            ]
            factsheet = factsheet_evidence["metadata"]
            if (
                factsheet_evidence["published_at"] != "2026-07-16"
                or factsheet["resource_listing_date_as_reported"]
                != "Jul 16, 2026"
                or factsheet["planned_it_load_wording_as_reported"]
                != "Up to 24MW of IT Load"
                or factsheet["planned_it_load_maximum_as_reported_mw"] != 24
                or "upper-bound design value" not in factsheet["capacity_scope"]
            ):
                raise AssertionError("Jakarta 3 maximum IT-load scope must remain")
            if (
                factsheet["design_pue_wording_as_reported"]
                != "Design PUE of <1.30"
                or "cannot faithfully encode" not in factsheet["pue_guardrail"]
                or factsheet["ready_for_service_forecast_as_reported"] != "Q1 2027"
            ):
                raise AssertionError("Jakarta 3 PUE inequality and forecast must stay metadata")
        elif name == BANGKOK_2_SOURCE:
            metadata = next(iter(evidence.values()))["metadata"]
            if (
                metadata["development_potential_it_power_as_reported_mw"] != 24
                or "future design capacity" not in metadata["capacity_scope"]
                or metadata["ready_for_service_forecast_as_reported"] != "Q4 2026"
            ):
                raise AssertionError("Bangkok 2 IT-power and forecast scope must remain")
        elif name == JC3_SOURCE:
            metadata = next(iter(evidence.values()))["metadata"]
            if (
                metadata["reported_scale_claim_mw"] != 120
                or "does not explicitly identify" not in metadata["scale_metric_guardrail"]
                or "creates no capacity row" not in metadata["scale_metric_guardrail"]
                or metadata["ready_for_service_forecast_as_reported"] != "Q4 2026"
            ):
                raise AssertionError("JC3 120 MW must remain untyped and forecast-only")
        elif name == SE1_SOURCE:
            metadata = next(iter(evidence.values()))["metadata"]
            if (
                metadata["future_construction_wording_as_reported"]
                != "construction is commencing later this month"
                or "not under_construction" not in metadata["status_scope"]
            ):
                raise AssertionError("SE1 future construction must remain announced")
            if (
                metadata["se1_scale_claim_mw"] != 48
                or metadata["south_korea_buildout_claim_mw"] != 500
                or "create no capacity row" not in metadata["scale_metric_guardrail"]
                or metadata["ready_for_service_forecast_as_reported"] != "early 2028"
            ):
                raise AssertionError("SE1 power claims must remain untyped and forecast-only")

        for row in document["evidence"]:
            metadata = row["metadata"]
            if (
                "normalized workload" not in metadata["classification_guardrail"]
                or "installed hardware model" not in metadata["classification_guardrail"]
            ):
                raise AssertionError("classification exclusions must remain explicit")
            if "No satellite imagery" not in metadata["imagery_guardrail"]:
                raise AssertionError("imagery non-use must remain explicit")

    def test_exact_sources_import_offline_with_narrow_semantics(self) -> None:
        v15_definition = (ROOT / "sources" / V15_DEFINITION).read_text(
            encoding="utf-8"
        )
        for name, expected in SOURCES.items():
            self.assertNotIn(name, v15_definition)
            self.assertNotIn(expected["project_key"], v15_definition)
        self.assertNotIn(JAKARTA_CAMPUS_KEY, v15_definition)

        documents = {name: self._load(name) for name in SOURCES}
        jakarta_documents = [
            documents[JAKARTA_3_SOURCE],
            documents[JAKARTA_5_SOURCE],
            documents[JAKARTA_6_SOURCE],
        ]
        self.assertTrue(
            all(
                document["campus"] == jakarta_documents[0]["campus"]
                for document in jakarta_documents[1:]
            )
        )
        shared_evidence = jakarta_documents[0]["evidence"][0]
        self.assertTrue(
            all(
                document["evidence"][0] == shared_evidence
                for document in jakarta_documents[1:]
            )
        )

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
                    for name, expected in sorted(SOURCES.items()):
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
                                metadata["content_encoding_as_received"],
                                capture["content_encoding"],
                            )
                            self.assertEqual(
                                metadata["http_content_length_bytes_as_received"],
                                capture["content_length"],
                            )
                            self.assertEqual(metadata["response_header_blocks"], 1)
                            self.assertEqual(evidence["source_url"], capture["url"])
                            self.assertEqual(metadata["requested_url"], capture["url"])
                            self.assertEqual(metadata["effective_url"], capture["url"])
                            self.assertEqual(metadata["canonical_url"], capture["url"])
                            self.assertNotIn("request_started_at", metadata)
                            self.assertNotIn("request_start_utc", metadata)
                            self.assertIn(
                                "no request-start artifact was supplied",
                                metadata["retrieval_method"],
                            )
                            self.assertIn(
                                "not redistributed", metadata["rights_scope"]
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
                    [("campus", 4), ("project", 6)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT project_entity.stable_key,
                                   lifecycle_observations.status,
                                   lifecycle_observations.as_of_date,
                                   lifecycle_observations.method
                            FROM lifecycle_observations
                            JOIN entities AS project_entity
                              ON project_entity.id = lifecycle_observations.entity_id
                            ORDER BY project_entity.stable_key
                            """
                        )
                    ],
                    sorted(
                        (
                            expected["project_key"],
                            expected["lifecycle"][0],
                            expected["lifecycle"][1],
                            expected["lifecycle"][2],
                        )
                        for expected in SOURCES.values()
                    ),
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT status, COUNT(*) FROM lifecycle_observations "
                            "GROUP BY status ORDER BY status"
                        )
                    ],
                    [
                        ("announced", 1),
                        ("shell", 1),
                        ("under_construction", 4),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key, capacity_estimates.metric,
                                   capacity_estimates.stage, capacity_estimates.low,
                                   capacity_estimates.base, capacity_estimates.high,
                                   capacity_estimates.unit,
                                   capacity_estimates.as_of_date,
                                   capacity_estimates.target_date
                            FROM capacity_estimates
                            JOIN entities
                              ON entities.id = capacity_estimates.entity_id
                            ORDER BY entities.stable_key
                            """
                        )
                    ],
                    sorted(
                        (
                            expected["project_key"],
                            "critical_it_mw",
                            "planned",
                            expected["capacity"][0],
                            expected["capacity"][0],
                            expected["capacity"][0],
                            "MW",
                            expected["capacity"][1],
                            None,
                        )
                        for expected in SOURCES.values()
                        if expected["capacity"] is not None
                    ),
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    5,
                )
                self.assertEqual(
                    {
                        row[0]
                        for row in connection.execute(
                            "SELECT content_hash FROM evidence"
                        )
                    },
                    set(CAPTURES),
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots"
                    ).fetchone()[0],
                    10,
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
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric != 'critical_it_mw' OR stage != 'planned'"
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

    def test_semantic_mutations_fail_guardrails(self) -> None:
        documents = {name: self._load(name) for name in SOURCES}
        mutations: list[tuple[str, dict[str, Any], str]] = []

        mutated = copy.deepcopy(documents[JAKARTA_3_SOURCE])
        mutated["lifecycle"][0]["value"] = "under_construction"
        mutations.append(
            (
                JAKARTA_3_SOURCE,
                mutated,
                "lifecycle scope, date, and method must remain exact",
            )
        )

        mutated = copy.deepcopy(documents[SE1_SOURCE])
        mutated["lifecycle"][0].update(
            {
                "value": "under_construction",
                "method": "authoritative_construction_start",
            }
        )
        mutations.append(
            (
                SE1_SOURCE,
                mutated,
                "lifecycle scope, date, and method must remain exact",
            )
        )

        mutated = copy.deepcopy(documents[JC3_SOURCE])
        forbidden_capacity = copy.deepcopy(documents[JAKARTA_3_SOURCE]["capacities"][0])
        forbidden_capacity.update(
            {
                "low": 120,
                "base": 120,
                "high": 120,
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2025-11-19",
            }
        )
        mutated["capacities"] = [forbidden_capacity]
        mutations.append(
            (JC3_SOURCE, mutated, "untyped power claims must create no capacity rows")
        )

        mutated = copy.deepcopy(documents[SE1_SOURCE])
        forbidden_capacity = copy.deepcopy(documents[JAKARTA_3_SOURCE]["capacities"][0])
        forbidden_capacity.update(
            {
                "low": 48,
                "base": 48,
                "high": 48,
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2025-11-17",
            }
        )
        mutated["capacities"] = [forbidden_capacity]
        mutations.append(
            (SE1_SOURCE, mutated, "untyped power claims must create no capacity rows")
        )

        mutated = copy.deepcopy(documents[JAKARTA_3_SOURCE])
        forbidden_pue = copy.deepcopy(mutated["capacities"][0])
        forbidden_pue.update(
            {
                "metric": "pue",
                "unit": "ratio",
                "low": 1.3,
                "base": 1.3,
                "high": 1.3,
            }
        )
        mutated["capacities"].append(forbidden_pue)
        mutations.append(
            (
                JAKARTA_3_SOURCE,
                mutated,
                "one planned project critical-IT capacity must remain",
            )
        )

        mutated = copy.deepcopy(documents[BANGKOK_2_SOURCE])
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(
            (
                BANGKOK_2_SOURCE,
                mutated,
                "planned project critical-IT scope must remain exact",
            )
        )

        mutated = copy.deepcopy(documents[JAKARTA_5_SOURCE])
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-06-10",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append(
            (
                JAKARTA_5_SOURCE,
                mutated,
                "design and market language must not become workloads",
            )
        )

        mutated = copy.deepcopy(documents[JAKARTA_6_SOURCE])
        mutated["operating_models"] = [
            {
                "entity": "project",
                "value": "hyperscale",
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-06-10",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append(
            (JAKARTA_6_SOURCE, mutated, "operating models must remain empty")
        )

        mutated = copy.deepcopy(documents[JC3_SOURCE])
        mutated["campus"]["coordinates"] = {
            "latitude": -6.3,
            "longitude": 107.1,
        }
        mutations.append(
            (JC3_SOURCE, mutated, "authoritative localities must remain ungeocoded")
        )

        mutated = copy.deepcopy(documents[SE1_SOURCE])
        mutated["project"]["roles"] = {"operator": ["Princeton Digital Group"]}
        mutations.append((SE1_SOURCE, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(documents[JAKARTA_5_SOURCE])
        mutated["campus"]["stable_key"] = (
            "curated:stt-jakarta-data-centre-campus:duplicate"
        )
        mutations.append(
            (JAKARTA_5_SOURCE, mutated, "canonical campus identity must remain")
        )

        mutated = copy.deepcopy(documents[BANGKOK_2_SOURCE])
        mutated["evidence"][0]["kind"] = "satellite_imagery"
        mutations.append(
            (BANGKOK_2_SOURCE, mutated, "evidence must remain company disclosure only")
        )

        for name, document, message in mutations:
            with self.subTest(source=name, rejection=message):
                with self.assertRaisesRegex(AssertionError, message):
                    self._assert_guardrails(name, document)

    def test_shared_jakarta_campus_is_import_order_invariant(self) -> None:
        orders = (
            (JAKARTA_3_SOURCE, JAKARTA_5_SOURCE, JAKARTA_6_SOURCE),
            (JAKARTA_6_SOURCE, JAKARTA_5_SOURCE, JAKARTA_3_SOURCE),
        )
        outcomes: list[dict[str, Any]] = []
        for order in orders:
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
                                ROOT / "sources" / name,
                                retrieved_at="2026-07-19T19:09:17Z",
                            )
                    outcomes.append(
                        {
                            "entities": [
                                tuple(row)
                                for row in connection.execute(
                                    "SELECT stable_key, kind FROM entities "
                                    "ORDER BY stable_key"
                                )
                            ],
                            "snapshots": [
                                tuple(row)
                                for row in connection.execute(
                                    "SELECT entity_id, name, evidence_id, as_of_date, "
                                    "recorded_at, method FROM entity_snapshots "
                                    "ORDER BY entity_id"
                                )
                            ],
                            "lifecycle": [
                                tuple(row)
                                for row in connection.execute(
                                    "SELECT entity_id, status, evidence_id, as_of_date, "
                                    "recorded_at, method FROM lifecycle_observations "
                                    "ORDER BY entity_id"
                                )
                            ],
                            "capacities": [
                                tuple(row)
                                for row in connection.execute(
                                    "SELECT entity_id, metric, stage, low, base, high, "
                                    "evidence_id, as_of_date, recorded_at "
                                    "FROM capacity_estimates ORDER BY entity_id"
                                )
                            ],
                            "evidence": [
                                tuple(row)
                                for row in connection.execute(
                                    "SELECT content_hash, retrieved_at FROM evidence "
                                    "ORDER BY content_hash"
                                )
                            ],
                        }
                    )
                    self.assertEqual(
                        [
                            tuple(row)
                            for row in connection.execute(
                                "SELECT kind, COUNT(*) FROM entities "
                                "GROUP BY kind ORDER BY kind"
                            )
                        ],
                        [("campus", 1), ("project", 3)],
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM entity_snapshots"
                        ).fetchone()[0],
                        4,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM lifecycle_observations"
                        ).fetchone()[0],
                        3,
                    )
                    self.assertEqual(
                        connection.execute(
                            "SELECT COUNT(*) FROM capacity_estimates"
                        ).fetchone()[0],
                        3,
                    )
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                        2,
                    )
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()
        self.assertEqual(outcomes[0], outcomes[1])


if __name__ == "__main__":
    unittest.main()
