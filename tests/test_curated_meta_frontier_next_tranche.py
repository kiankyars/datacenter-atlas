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
V14_DEFINITION = "open-seed-2026-07-19-v14.json"
META_SOURCE = "curated-official-2026-07-19-meta-sturgeon-county-alberta.json"
FRONTIER_SOURCE = (
    "curated-official-2026-07-19-vantage-frontier-shackelford.json"
)
SOURCES: dict[str, dict[str, Any]] = {
    META_SOURCE: {
        "sha256": "2b1b612b0ada0c25ed2bbc3cf2cef2fc0063ae6b58feaf467d9917b22c9265f1",
        "retrieved_at": "2026-07-19T18:47:40Z",
        "country": "Canada",
        "address": "Sturgeon County, Alberta, Canada",
        "campus_key": "curated:meta-sturgeon-county-alberta-data-center",
        "campus_name": "Meta Sturgeon County Alberta Data Center",
        "project_key": (
            "curated:meta-sturgeon-county-alberta-data-center:current-campus-build"
        ),
        "project_name": "Meta Sturgeon County Alberta Current Campus Build",
        "lifecycle_date": "2026-07-08",
        "lifecycle_method": "authoritative_construction_start",
        "capacities": [],
        "workload_date": "2026-07-08",
    },
    FRONTIER_SOURCE: {
        "sha256": "169bd1808a8f6a6202a2ec8beda3f9c42515b44491e40ceed3e37e6144a978b2",
        "retrieved_at": "2026-07-19T18:47:43Z",
        "country": "United States",
        "address": "Shackelford County, Texas, United States",
        "campus_key": "curated:vantage-frontier-shackelford-campus",
        "campus_name": "Vantage Frontier Shackelford County Data Center Campus",
        "project_key": (
            "curated:vantage-frontier-shackelford-campus:"
            "current-10-building-campus-development"
        ),
        "project_name": (
            "Vantage Frontier Shackelford Current 10-Building Campus Development"
        ),
        "lifecycle_date": "2026-06-01",
        "lifecycle_method": "authoritative_physical_status_update",
        "capacities": [("campus", "critical_it_mw", 1400.0)],
        "workload_date": "2025-08-19",
    },
}
CAPTURES: dict[str, dict[str, Any]] = {
    "2ee9ab456d8d58d14a4813432de9160dd645651b266f7c1d19616fb6bab49a42": {
        "body_bytes": 512253,
        "headers_bytes": 808,
        "headers_sha256": (
            "7e09972c86ff4a57f0789a79584a56448c55201e0fbda35008787075c6ad2713"
        ),
        "response_date": "2026-07-19T18:47:40Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://about.fb.com/news/2026/07/"
            "breaking-ground-on-metas-first-data-center-in-canada/"
        ),
    },
    "39749b482fcd40c2e5e1ae84f784302b5cbc5e5e76000b822650965a8c67cbad": {
        "body_bytes": 192091,
        "headers_bytes": 2005,
        "headers_sha256": (
            "bc0d7d17eb3d392b9ecad8dc6df52b9cc2641120ebce9334be87e6cf05dafb5c"
        ),
        "response_date": "2026-07-19T18:47:43Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://vantage-dc.com/news/"
            "vantage-data-centers-unveils-plans-for-frontier-a-25b-mega-campus-"
            "in-texas-to-meet-unprecedented-ai-demand/"
        ),
    },
    "d9040d52ac8ec73bce431a2114cf61545c9ea01a7bffd55cbce9ff5bf642f3d6": {
        "body_bytes": 722380,
        "headers_bytes": 744,
        "headers_sha256": (
            "2a33371899cb2f301174e11d569ef07526ca908af53aef237680a219f53b5297"
        ),
        "response_date": "2026-07-19T18:47:40Z",
        "last_modified": "2025-08-19T01:00:12Z",
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 722380,
        "url": (
            "https://vantage-dc.com/wp-content/uploads/2025/08/"
            "VDC_DataSheet_Frontier.pdf"
        ),
    },
    "b61b6a48d4399cd02f84781e27ea94b1ce1d66c2e82d95df1648842aae831371": {
        "body_bytes": 53946,
        "headers_bytes": 1756,
        "headers_sha256": (
            "ce61c5de535c0a9c762f68be5ffabe904316c2176a21201903e30bacf9175e86"
        ),
        "response_date": "2026-07-19T18:33:46Z",
        "last_modified": "2026-07-15T14:30:30Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": 14762,
        "url": "https://www.oracle.com/data-centers/",
    },
    "f266cb83e96c6d5dabbe45bf3c6c9ef712cba1da6854d2755cbf236b82632681": {
        "body_bytes": 30189,
        "headers_bytes": 1753,
        "headers_sha256": (
            "419fd03fffdd8ea315314291292120922715ae43c1d392f43476bfb10e6e7df2"
        ),
        "response_date": "2026-07-19T18:47:40Z",
        "last_modified": "2026-07-12T03:32:23Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": 9549,
        "url": "https://www.oracle.com/data-centers/shackelford-county/",
    },
}


class MetaFrontierNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_guardrails(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")
        if any(row["kind"] != "company_disclosure" for row in document["evidence"]):
            raise AssertionError("evidence must remain first-party disclosure only")

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if entity["roles"] != {}:
                raise AssertionError("roles must remain empty")
            if entity["coordinates"] is not None or entity["geometry"] is not None:
                raise AssertionError("localities must remain ungeocoded")
            if entity["method"] != "authoritative_locality":
                raise AssertionError("snapshot method must remain authoritative_locality")
            if entity["country"] != expected["country"]:
                raise AssertionError("country must remain source explicit")
            if entity["address"] != expected["address"]:
                raise AssertionError("address must remain authoritative locality only")

        if (
            document["campus"]["stable_key"] != expected["campus_key"]
            or document["campus"]["name"] != expected["campus_name"]
        ):
            raise AssertionError("one canonical campus identity must remain")
        if (
            document["project"]["stable_key"] != expected["project_key"]
            or document["project"]["name"] != expected["project_name"]
        ):
            raise AssertionError("one canonical current-build project must remain")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1 or lifecycle[0]["entity"] != "project":
            raise AssertionError("one project lifecycle observation must remain")
        if lifecycle[0]["value"] != "under_construction":
            raise AssertionError("lifecycle must remain generic under_construction")
        if lifecycle[0]["as_of_date"] != expected["lifecycle_date"]:
            raise AssertionError("lifecycle date must remain source scoped")
        if lifecycle[0]["method"] != expected["lifecycle_method"]:
            raise AssertionError("lifecycle method must remain authoritative")

        if document["operating_models"]:
            raise AssertionError("operating models must remain empty")
        workloads = document["workloads"]
        if len(workloads) != 1:
            raise AssertionError("one narrow AI workload must remain")
        workload = workloads[0]
        if (
            workload["entity"] != "campus"
            or workload["value"] != "ai_specialized_unspecified"
            or workload["as_of_date"] != expected["workload_date"]
            or workload["method"] != "company_disclosure"
        ):
            raise AssertionError("AI workload must remain explicit and unspecified")

        capacities = document["capacities"]
        if len(capacities) != len(expected["capacities"]):
            raise AssertionError("typed capacity row count must remain exact")
        actual_capacities: list[tuple[str, str, float]] = []
        for row in capacities:
            if (
                row["stage"] != "planned"
                or row["unit"] != "MW"
                or row["method"] != "reported"
                or row["target_date"] is not None
            ):
                raise AssertionError("capacity must remain planned reported MW")
            if (row["low"], row["base"], row["high"]) != (row["base"],) * 3:
                raise AssertionError("capacity values must remain exact")
            actual_capacities.append(
                (row["entity"], row["metric"], float(row["base"]))
            )
        if actual_capacities != expected["capacities"]:
            raise AssertionError("capacity metric scope and value must remain exact")

        evidence = {row["key"]: row for row in document["evidence"]}
        if name == META_SOURCE:
            meta = evidence[
                "meta-sturgeon-county-groundbreaking-2026-07-08-captured-2026-07-19"
            ]["metadata"]
            if (
                meta["reported_scale_claim_gw"] != 1
                or "does not identify" not in meta["scale_metric_guardrail"]
                or "creates no typed capacity row" not in meta["scale_metric_guardrail"]
            ):
                raise AssertionError("Meta 1 GW claim must remain untyped metadata")
            if (
                "breaking ground" not in meta["construction_wording_as_reported"]
                or "generic under_construction" not in meta["status_scope"]
            ):
                raise AssertionError("Meta status must remain explicit and generic")
            if (
                "site generation asset" not in meta["energy_infrastructure_guardrail"]
                or "matching commitment" not in meta["clean_energy_matching_scope"]
                or "supplies no Sturgeon-specific measurement"
                not in meta["annual_disclosure_guardrail"]
            ):
                raise AssertionError("Meta energy context must remain non-measured")
        else:
            announcement = evidence[
                "vantage-frontier-announcement-2025-08-19-captured-2026-07-19"
            ]["metadata"]
            datasheet = evidence[
                "vantage-frontier-datasheet-captured-2026-07-19"
            ]["metadata"]
            aerials = evidence[
                "oracle-data-centers-shackelford-aerials-captured-2026-07-19"
            ]["metadata"]
            shackelford = evidence[
                "oracle-shackelford-county-page-captured-2026-07-19"
            ]["metadata"]
            if (
                announcement["building_count_as_reported"] != 10
                or announcement["campus_area_as_reported_acres"] != 1200
                or announcement["floor_area_as_reported_square_feet"] != 3700000
                or "match" not in announcement["identity_scope"]
            ):
                raise AssertionError("Frontier identity facts must remain exact")
            if (
                datasheet["critical_it_capacity_as_reported_mw"] != 1400
                or datasheet["capacity_label_as_reported"]
                != "1.4GW of critical IT load"
                or "full-campus critical IT" not in datasheet["capacity_scope"]
            ):
                raise AssertionError("Frontier critical IT metric must remain exact")
            if (
                aerials["shackelford_data_halls_aerial_caption_as_reported"]
                != "Data Halls - 06/01/2026"
                or aerials["abilene_data_halls_aerial_caption_as_reported"]
                != "Data Halls – 06/04/2026"
                or aerials["dona_ana_aerial_captions_as_reported"]
                != ["Campus - 05/27/2026", "Data Hall - 05/21/2026"]
                or aerials["port_washington_aerial_captions_as_reported"]
                != [
                    "Campus - 05/26/2026",
                    "Data Hall - 05/27/2026",
                    "Data Hall - 05/21/2026",
                ]
                or aerials["saline_aerial_captions_as_reported"]
                != [
                    "Campus - 05/15/2026",
                    "Data Hall - 05/15/2026",
                    "Data Hall - 05/26/2026",
                ]
                or "None may set Frontier" not in aerials["cross_site_aerial_guardrail"]
            ):
                raise AssertionError("Frontier aerial date must remain Shackelford scoped")
            if (
                "not independent satellite imagery"
                not in aerials["imagery_provenance_guardrail"]
                or "computer-vision result"
                not in aerials["imagery_provenance_guardrail"]
            ):
                raise AssertionError("Frontier aerial provenance must remain explicit")
            if (
                aerials["power_capacity_as_reported_mw"] != 115
                or "does not identify" not in aerials["power_metric_guardrail"]
                or "creates no capacity row" not in aerials["power_metric_guardrail"]
            ):
                raise AssertionError("Oracle 115 MW must remain untyped metadata")
            if (
                shackelford["building_count_as_reported"] != 10
                or shackelford["campus_area_as_reported_acres"] != 1200
                or shackelford["floor_area_as_reported_square_feet"] != 3700000
                or "does not establish generation nameplate"
                not in shackelford["power_guardrail"]
            ):
                raise AssertionError("Oracle Shackelford facts must remain narrow")

    def test_exact_sources_import_offline_with_narrow_semantics(self) -> None:
        v14_definition = (ROOT / "sources" / V14_DEFINITION).read_text(
            encoding="utf-8"
        )
        for name, expected in SOURCES.items():
            self.assertNotIn(name, v14_definition)
            self.assertNotIn(expected["campus_key"], v14_definition)
            self.assertNotIn(expected["project_key"], v14_definition)

        documents: dict[str, dict[str, Any]] = {}
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
                        document = self._load(name)
                        documents[name] = document
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
                    [("campus", 2), ("project", 2)],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT project_entity.stable_key,
                                   campus_entity.stable_key,
                                   lifecycle_observations.status,
                                   lifecycle_observations.as_of_date,
                                   lifecycle_observations.method
                            FROM lifecycle_observations
                            JOIN entities AS project_entity
                              ON project_entity.id = lifecycle_observations.entity_id
                            JOIN projects ON projects.entity_id = project_entity.id
                            JOIN entities AS campus_entity
                              ON campus_entity.id = projects.target_entity_id
                            ORDER BY project_entity.stable_key
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[META_SOURCE]["project_key"],
                            SOURCES[META_SOURCE]["campus_key"],
                            "under_construction",
                            "2026-07-08",
                            "authoritative_construction_start",
                        ),
                        (
                            SOURCES[FRONTIER_SOURCE]["project_key"],
                            SOURCES[FRONTIER_SOURCE]["campus_key"],
                            "under_construction",
                            "2026-06-01",
                            "authoritative_physical_status_update",
                        ),
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
                                   capacity_estimates.unit, capacity_estimates.target_date
                            FROM capacity_estimates
                            JOIN entities
                              ON entities.id = capacity_estimates.entity_id
                            ORDER BY entities.stable_key
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[FRONTIER_SOURCE]["campus_key"],
                            "critical_it_mw",
                            "planned",
                            1400.0,
                            1400.0,
                            1400.0,
                            "MW",
                            None,
                        )
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   workload_observations.workload,
                                   workload_observations.as_of_date,
                                   workload_observations.method
                            FROM workload_observations
                            JOIN entities
                              ON entities.id = workload_observations.entity_id
                            ORDER BY entities.stable_key
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[META_SOURCE]["campus_key"],
                            "ai_specialized_unspecified",
                            "2026-07-08",
                            "company_disclosure",
                        ),
                        (
                            SOURCES[FRONTIER_SOURCE]["campus_key"],
                            "ai_specialized_unspecified",
                            "2025-08-19",
                            "company_disclosure",
                        ),
                    ],
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
                    4,
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
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric != 'critical_it_mw' OR stage != 'planned'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM capacity_estimates "
                        "WHERE metric IN ('pue', 'annual_energy_mwh', "
                        "'grid_connection_mw', 'gross_facility_mw', "
                        "'generation_nameplate_mw')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_observations "
                        "WHERE status IN ('commissioning', 'operational')"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM evidence WHERE kind = 'satellite_imagery'"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_semantic_mutations_fail_guardrails(self) -> None:
        meta = self._load(META_SOURCE)
        frontier = self._load(FRONTIER_SOURCE)
        mutations: list[tuple[str, dict[str, Any], str]] = []

        meta_capacity = {
            "entity": "campus",
            "metric": "critical_it_mw",
            "stage": "planned",
            "unit": "MW",
            "low": 1000,
            "base": 1000,
            "high": 1000,
            "method": "reported",
            "confidence": 0.5,
            "evidence_key": (
                "meta-sturgeon-county-groundbreaking-2026-07-08-"
                "captured-2026-07-19"
            ),
            "as_of_date": "2026-07-08",
            "target_date": None,
            "notes": "Forbidden conversion of an untyped 1 GW scale claim.",
        }
        mutated = copy.deepcopy(meta)
        mutated["capacities"] = [meta_capacity]
        mutations.append(
            (META_SOURCE, mutated, "typed capacity row count must remain exact")
        )

        mutated = copy.deepcopy(frontier)
        oracle_capacity = copy.deepcopy(mutated["capacities"][0])
        oracle_capacity.update(
            {
                "metric": "grid_connection_mw",
                "low": 115,
                "base": 115,
                "high": 115,
                "evidence_key": (
                    "oracle-data-centers-shackelford-aerials-captured-2026-07-19"
                ),
                "as_of_date": "2026-06-01",
                "notes": "Forbidden typing of Oracle's untyped power claim.",
            }
        )
        mutated["capacities"].append(oracle_capacity)
        mutations.append(
            (FRONTIER_SOURCE, mutated, "typed capacity row count must remain exact")
        )

        mutated = copy.deepcopy(frontier)
        mutated["lifecycle"][0]["as_of_date"] = "2026-06-04"
        mutations.append(
            (FRONTIER_SOURCE, mutated, "lifecycle date must remain source scoped")
        )

        mutated = copy.deepcopy(frontier)
        mutated["capacities"][0]["metric"] = "gross_facility_mw"
        mutations.append(
            (FRONTIER_SOURCE, mutated, "capacity metric scope and value must remain exact")
        )

        mutated = copy.deepcopy(meta)
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append(
            (META_SOURCE, mutated, "lifecycle must remain generic under_construction")
        )

        mutated = copy.deepcopy(frontier)
        mutated["campus"]["roles"] = {"operator": ["Vantage Data Centers"]}
        mutations.append((FRONTIER_SOURCE, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(meta)
        mutated["project"]["coordinates"] = {
            "latitude": 53.8,
            "longitude": -113.6,
        }
        mutations.append((META_SOURCE, mutated, "localities must remain ungeocoded"))

        for metric, unit, value in (
            ("pue", "ratio", 1.2),
            ("annual_energy_mwh", "MWh/year", 12_264_000),
        ):
            mutated = copy.deepcopy(frontier)
            forbidden = copy.deepcopy(mutated["capacities"][0])
            forbidden.update(
                {
                    "metric": metric,
                    "unit": unit,
                    "low": value,
                    "base": value,
                    "high": value,
                    "notes": "Forbidden inferred efficiency or annual energy.",
                }
            )
            mutated["capacities"].append(forbidden)
            mutations.append(
                (
                    FRONTIER_SOURCE,
                    mutated,
                    "typed capacity row count must remain exact",
                )
            )

        mutated = copy.deepcopy(frontier)
        current_load = copy.deepcopy(mutated["capacities"][0])
        current_load.update(
            {
                "stage": "operational",
                "low": 115,
                "base": 115,
                "high": 115,
                "notes": "Forbidden current-load promotion.",
            }
        )
        mutated["capacities"].append(current_load)
        mutations.append(
            (FRONTIER_SOURCE, mutated, "typed capacity row count must remain exact")
        )

        mutated = copy.deepcopy(meta)
        current_generation = copy.deepcopy(meta_capacity)
        current_generation.update(
            {
                "metric": "generation_nameplate_mw",
                "stage": "operational",
                "notes": "Forbidden current-generation promotion.",
            }
        )
        mutated["capacities"] = [current_generation]
        mutations.append(
            (META_SOURCE, mutated, "typed capacity row count must remain exact")
        )

        mutated = copy.deepcopy(frontier)
        mutated["evidence"][2]["kind"] = "satellite_imagery"
        mutations.append(
            (
                FRONTIER_SOURCE,
                mutated,
                "evidence must remain first-party disclosure only",
            )
        )

        for name, document, message in mutations:
            with self.subTest(source=name, rejection=message):
                with self.assertRaisesRegex(AssertionError, message):
                    self._assert_guardrails(name, document)


if __name__ == "__main__":
    unittest.main()
