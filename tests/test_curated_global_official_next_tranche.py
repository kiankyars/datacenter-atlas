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
EQUINIX_SOURCE = (
    "curated-official-2026-07-19-equinix-db7x-blanchardstown.json"
)
RETELIT_SOURCE = "curated-official-2026-07-19-retelit-milan-corsico.json"
XNEELO_SOURCE = (
    "curated-official-2026-07-19-xneelo-samrand-second-facility.json"
)
SMF02_SOURCE = "curated-official-2026-07-19-prime-smf02-sacramento.json"
PHX01_SOURCE = (
    "curated-official-2026-07-19-prime-phx01-avondale-buildings-1-3.json"
)
CAPROCK_SOURCE = (
    "curated-official-2026-07-19-aligned-project-caprock-hale-county.json"
)
FIN02_SOURCE = (
    "curated-official-2026-07-19-atnorth-fin02-espoo-expansion.json"
)

SOURCES: dict[str, dict[str, Any]] = {
    EQUINIX_SOURCE: {
        "sha256": "f61109cc0142901d53e2581a8a86e9f6698e44858f7eb9058c8cea5d696bdf49",
        "retrieved_at": "2026-07-19T18:57:40Z",
        "country": "Ireland",
        "address": "Blanchardstown, Dublin, Ireland",
        "campus_key": "curated:equinix-db7x-blanchardstown-dublin",
        "project_key": (
            "curated:equinix-db7x-blanchardstown-dublin:"
            "current-facility-build"
        ),
        "lifecycle_date": "2026-03-20",
        "lifecycle_method": "authoritative_construction_start",
        "capacity_mw": None,
    },
    RETELIT_SOURCE: {
        "sha256": "9ef4402a9dee22d6b7b1c006961c36e0c9e45bbacc3bf51adeb2ec69a93ce96c",
        "retrieved_at": "2026-07-19T18:57:41Z",
        "country": "Italy",
        "address": "Corsico, Milan, Italy",
        "campus_key": "curated:retelit-milan-corsico-data-centre",
        "project_key": (
            "curated:retelit-milan-corsico-data-centre:"
            "current-two-building-development"
        ),
        "lifecycle_date": "2026-05-05",
        "lifecycle_method": "authoritative_construction_start",
        "capacity_mw": None,
    },
    XNEELO_SOURCE: {
        "sha256": "96726ac469d19c6484a0cda436f2e331bec992cfb29948fae9b0247269509d86",
        "retrieved_at": "2026-07-19T18:57:42Z",
        "country": "South Africa",
        "address": "Samrand, Gauteng, South Africa",
        "campus_key": "curated:xneelo-samrand-data-centre-campus",
        "project_key": (
            "curated:xneelo-samrand-data-centre-campus:second-facility-build"
        ),
        "lifecycle_date": "2026-02-03",
        "lifecycle_method": "authoritative_construction_start",
        "capacity_mw": None,
    },
    SMF02_SOURCE: {
        "sha256": "f8e0ee48af75b3aed382eaee3a85e50df7ea5ddcaeb909289c2837cb0fe40549",
        "retrieved_at": "2026-07-19T19:03:23Z",
        "country": "United States",
        "address": "Sacramento, California, United States",
        "campus_key": "curated:prime-sacramento-data-center-campus",
        "project_key": (
            "curated:prime-sacramento-data-center-campus:"
            "smf02-current-facility-build"
        ),
        "lifecycle_date": "2026-05-07",
        "lifecycle_method": "authoritative_construction_start",
        "capacity_mw": 18.0,
    },
    PHX01_SOURCE: {
        "sha256": "29d808e0ceec2714bc87427e623ea4151c4bb7769eba404054e1ee419e23d0a6",
        "retrieved_at": "2026-07-19T19:03:48Z",
        "country": "United States",
        "address": "Avondale, Arizona, United States",
        "campus_key": "curated:prime-phx01-avondale-campus",
        "project_key": (
            "curated:prime-phx01-avondale-campus:"
            "buildings-1-3-current-phase"
        ),
        "lifecycle_date": "2026-05-21",
        "lifecycle_method": "authoritative_construction_start",
        "capacity_mw": 144.0,
    },
    CAPROCK_SOURCE: {
        "sha256": "d3b3e5747bd10b5a654f6000f0ccf52fc7cd5e6ccdac5c2a4f96654147168cb7",
        "retrieved_at": "2026-07-19T19:03:25Z",
        "country": "United States",
        "address": "Hale County near Abernathy, Texas, United States",
        "campus_key": "curated:aligned-project-caprock-hale-county-campus",
        "project_key": (
            "curated:aligned-project-caprock-hale-county-campus:"
            "current-campus-development"
        ),
        "lifecycle_date": "2026-04-09",
        "lifecycle_method": "authoritative_construction_start",
        "capacity_mw": None,
    },
    FIN02_SOURCE: {
        "sha256": "3f2429e4d29d7550440f93e927e42425ea98ab21eb56e6fa9891eb762195d144",
        "retrieved_at": "2026-07-19T19:03:25Z",
        "country": "Finland",
        "address": "Espoo, Finland",
        "campus_key": "curated:atnorth-fin02-espoo-data-center",
        "project_key": (
            "curated:atnorth-fin02-espoo-data-center:current-expansion-building"
        ),
        "lifecycle_date": "2026-05-04",
        "lifecycle_method": "authoritative_physical_status_update",
        "capacity_mw": None,
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    "6e7b62fb02ea4cc816bb44023222e9b40146f29f85daa7c196adb1a3816990b9": {
        "body_bytes": 91672,
        "headers_bytes": 921,
        "headers_sha256": "0945e64752da1213775dcc2db936c02699b3ca39583c8f90bc483e4e75c343f6",
        "response_date": "2026-07-19T18:57:40Z",
        "last_modified": "2026-07-19T18:57:40Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://newsroom.equinix.com/"
            "2026-03-20-Equinix-begins-construction-on-new-data-center-in-Dublin"
        ),
    },
    "0460d58997d924162adda82af69430b2e3aaf9eb79562d4fb816c8a97a81b679": {
        "body_bytes": 85501,
        "headers_bytes": 381,
        "headers_sha256": "e6e87835cdb9baac20a9768052ae16ea54a0be74aaa8a4b37e77160efd11091f",
        "response_date": "2026-07-19T18:57:41Z",
        "last_modified": None,
        "content_type": "text/html; charset=utf-8",
        "content_encoding": None,
        "content_length": 85501,
        "url": (
            "https://www.retelit.it/en/press/press-releases/2026/"
            "retelit-breaks-ground-on-a-new-ai-ready-sustainable-data-centre-"
            "in-milan-corsico"
        ),
    },
    "7e4aebae64df0e2c7f1b32e75b121189ea3d911e7c7290f4644a72e881eaf852": {
        "body_bytes": 283783,
        "headers_bytes": 1252,
        "headers_sha256": "e9cadfe8b57ec7bb364e41611389879d890db9cee43581f80ca7882bc6168a6f",
        "response_date": "2026-07-19T18:57:42Z",
        "last_modified": "2026-07-18T22:23:57Z",
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://xneelo.co.za/insights/"
            "xneelo-breaks-ground-on-second-samrand-data-centre/"
        ),
    },
    "e637053b8524b1cdfd7ca1888de259c86bbe427d945b2b5108df391e0271a5e6": {
        "body_bytes": 231604,
        "headers_bytes": 1102,
        "headers_sha256": "b0c2f29c7418ea7f1eb5e40dd0bdbc70221d8c9f62ce4f50bb19a193c9d6d119",
        "response_date": "2026-07-19T19:03:23Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://primedatacenters.com/news/"
            "prime-data-centers-breaks-ground-on-second-sacramento-data-center-"
            "expanding-regional-campus-footprint/"
        ),
    },
    "0ee7f3b2cd41d5dc7b2552e412317accdca297190340f574c06dc8f5d50a297a": {
        "body_bytes": 229873,
        "headers_bytes": 1101,
        "headers_sha256": "195a9b69fb1375dffe3d088cc460e645e61d338e173438252b957961205d2550",
        "response_date": "2026-07-19T19:03:48Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://primedatacenters.com/news/"
            "prime-data-centers-breaks-ground-on-three-buildings-at-its-240mw-"
            "phoenix-campus-advancing-3billion-dollar-investment-in-avondale/"
        ),
    },
    "64cfe216b26fca653b031fd3c80feb76072a86e8d63900a1b61ab31d08b58cfb": {
        "body_bytes": 227430,
        "headers_bytes": 716,
        "headers_sha256": "33177fb811409922c979fdffdcc91471936f59d5009300774a9b6d1581bbc7e8",
        "response_date": "2026-07-19T19:03:25Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://aligneddc.com/press-release/"
            "aligned-breaks-ground-on-project-caprock/"
        ),
    },
    "a2a8a0f55ac0e719dc1452ef6bd797790756e91afe933a5f2273d548efad2dbb": {
        "body_bytes": 23104,
        "headers_bytes": 752,
        "headers_sha256": "6d3b2528001ac6b4968270c442bf1c57b88601bfbcbbe4c85379cb80e62e073d",
        "response_date": "2026-07-19T19:03:25Z",
        "last_modified": "2026-07-19T19:03:25Z",
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://news.cision.com/skanska/r/"
            "skanska-builds-data-center-expansion-in-espoo--finland-for-eur-"
            "100m--about-sek-1-1-billion,c4343680"
        ),
    },
}


class GlobalOfficialNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_guardrails(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")
        if len(document["evidence"]) != 1:
            raise AssertionError("one exact source capture must remain")
        if document["evidence"][0]["kind"] != "company_disclosure":
            raise AssertionError("evidence must remain company disclosure only")

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
        if document["campus"]["stable_key"] != expected["campus_key"]:
            raise AssertionError("one canonical campus identity must remain")
        if document["project"]["stable_key"] != expected["project_key"]:
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

        if document["workloads"]:
            raise AssertionError("AI-ready language must not become a workload")
        operating_models = document["operating_models"]
        if name == EQUINIX_SOURCE:
            if len(operating_models) != 1:
                raise AssertionError("one DB7x retail operating model must remain")
            model = operating_models[0]
            if (
                model["entity"] != "project"
                or model["value"] != "retail_colocation"
                or model["as_of_date"] != "2026-03-20"
                or model["method"] != "company_disclosure"
            ):
                raise AssertionError("DB7x retail scope must remain exact")
        elif operating_models:
            raise AssertionError("unscoped operating models must remain empty")

        capacities = document["capacities"]
        capacity_mw = expected["capacity_mw"]
        if capacity_mw is None:
            if capacities:
                raise AssertionError("untyped power claims must create no capacity rows")
        else:
            if len(capacities) != 1:
                raise AssertionError("one planned critical-IT capacity row must remain")
            capacity = capacities[0]
            if (
                capacity["entity"] != "project"
                or capacity["metric"] != "critical_it_mw"
                or capacity["stage"] != "planned"
                or capacity["unit"] != "MW"
                or capacity["method"] != "reported"
                or capacity["target_date"] is not None
                or (capacity["low"], capacity["base"], capacity["high"])
                != (capacity_mw,) * 3
            ):
                raise AssertionError("planned project critical-IT capacity must remain exact")

        metadata = document["evidence"][0]["metadata"]
        if name == EQUINIX_SOURCE:
            if (
                "DB7x-specific" not in metadata["retail_ibx_scope"]
                or "No capacity or energy row" not in metadata["grid_guardrail"]
            ):
                raise AssertionError("DB7x retail and grid guardrails must remain explicit")
        elif name == RETELIT_SOURCE:
            if (
                metadata["capacity_as_reported_mw"] != 13.6
                or "untyped metadata" not in metadata["capacity_metric_guardrail"]
                or metadata["building_count_as_reported"] != 2
            ):
                raise AssertionError("Retelit 13.6 MW must remain untyped metadata")
        elif name == XNEELO_SOURCE:
            if (
                "not assigned to the second facility"
                not in metadata["efficiency_guardrail"]
                or metadata["completion_forecast_as_reported"] != "October 2026"
            ):
                raise AssertionError("xneelo second-facility scope must remain narrow")
        elif name == SMF02_SOURCE:
            if (
                metadata["critical_it_capacity_as_reported_mw"] != 18
                or "not current load" not in metadata["capacity_scope"]
            ):
                raise AssertionError("SMF02 18 MW critical IT scope must remain exact")
        elif name == PHX01_SOURCE:
            if (
                metadata["current_phase_building_count_as_reported"] != 3
                or metadata["per_building_critical_it_capacity_as_reported_mw"]
                != 48
                or metadata["current_phase_critical_it_capacity_as_reported_mw"]
                != 144
                or metadata["future_campus_critical_it_capacity_as_reported_mw"]
                != 240
                or metadata["substation_capacity_as_reported_mw"] != 250
                or "No per-building capacity rows"
                not in metadata["current_phase_capacity_guardrail"]
                or "creates no additional capacity row"
                not in metadata["future_campus_guardrail"]
                or "not imported as a grid-connection"
                not in metadata["substation_guardrail"]
            ):
                raise AssertionError("PHX01 current-phase capacity must avoid double counting")
        elif name == CAPROCK_SOURCE:
            if (
                metadata["capacity_as_reported_mw"] != 540
                or "untyped metadata" not in metadata["capacity_metric_guardrail"]
                or metadata["facility_count_as_reported"] != 6
            ):
                raise AssertionError("Caprock 540 MW must remain untyped metadata")
        elif name == FIN02_SOURCE:
            if (
                metadata[
                    "post_expansion_whole_facility_gross_capacity_as_reported_mw"
                ]
                != 45
                or "does not isolate incremental expansion capacity"
                not in metadata["capacity_scope_guardrail"]
                or "preventing double counting"
                not in metadata["capacity_scope_guardrail"]
            ):
                raise AssertionError("FIN02 whole-facility 45 MW must remain untyped")

    def test_exact_sources_import_offline_with_narrow_semantics(self) -> None:
        v15_definition = (ROOT / "sources" / V15_DEFINITION).read_text(
            encoding="utf-8"
        )
        for name, expected in SOURCES.items():
            self.assertNotIn(name, v15_definition)
            self.assertNotIn(expected["campus_key"], v15_definition)
            self.assertNotIn(expected["project_key"], v15_definition)

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
                    [("campus", 7), ("project", 7)],
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
                            """
                            SELECT entities.stable_key, capacity_estimates.metric,
                                   capacity_estimates.stage, capacity_estimates.low,
                                   capacity_estimates.base, capacity_estimates.high,
                                   capacity_estimates.unit,
                                   capacity_estimates.target_date
                            FROM capacity_estimates
                            JOIN entities
                              ON entities.id = capacity_estimates.entity_id
                            ORDER BY entities.stable_key
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[PHX01_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            144.0,
                            144.0,
                            144.0,
                            "MW",
                            None,
                        ),
                        (
                            SOURCES[SMF02_SOURCE]["project_key"],
                            "critical_it_mw",
                            "planned",
                            18.0,
                            18.0,
                            18.0,
                            "MW",
                            None,
                        ),
                    ],
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            """
                            SELECT entities.stable_key,
                                   operating_model_observations.operating_model,
                                   operating_model_observations.as_of_date,
                                   operating_model_observations.method
                            FROM operating_model_observations
                            JOIN entities
                              ON entities.id = operating_model_observations.entity_id
                            """
                        )
                    ],
                    [
                        (
                            SOURCES[EQUINIX_SOURCE]["project_key"],
                            "retail_colocation",
                            "2026-03-20",
                            "company_disclosure",
                        )
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    7,
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
                    14,
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
                        "SELECT COUNT(*) FROM lifecycle_observations "
                        "WHERE status != 'under_construction'"
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

        mutated = copy.deepcopy(documents[EQUINIX_SOURCE])
        mutated["operating_models"] = []
        mutations.append(
            (EQUINIX_SOURCE, mutated, "one DB7x retail operating model must remain")
        )

        mutated = copy.deepcopy(documents[RETELIT_SOURCE])
        forbidden_capacity = copy.deepcopy(documents[SMF02_SOURCE]["capacities"][0])
        forbidden_capacity.update(
            {
                "low": 13.6,
                "base": 13.6,
                "high": 13.6,
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-05-05",
            }
        )
        mutated["capacities"] = [forbidden_capacity]
        mutations.append(
            (RETELIT_SOURCE, mutated, "untyped power claims must create no capacity rows")
        )

        mutated = copy.deepcopy(documents[CAPROCK_SOURCE])
        forbidden_capacity = copy.deepcopy(documents[SMF02_SOURCE]["capacities"][0])
        forbidden_capacity.update(
            {
                "low": 540,
                "base": 540,
                "high": 540,
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-04-09",
            }
        )
        mutated["capacities"] = [forbidden_capacity]
        mutations.append(
            (CAPROCK_SOURCE, mutated, "untyped power claims must create no capacity rows")
        )

        mutated = copy.deepcopy(documents[FIN02_SOURCE])
        forbidden_capacity = copy.deepcopy(documents[SMF02_SOURCE]["capacities"][0])
        forbidden_capacity.update(
            {
                "metric": "gross_facility_mw",
                "low": 45,
                "base": 45,
                "high": 45,
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-05-04",
            }
        )
        mutated["capacities"] = [forbidden_capacity]
        mutations.append(
            (FIN02_SOURCE, mutated, "untyped power claims must create no capacity rows")
        )

        mutated = copy.deepcopy(documents[PHX01_SOURCE])
        per_building = copy.deepcopy(mutated["capacities"][0])
        per_building.update({"low": 48, "base": 48, "high": 48})
        mutated["capacities"].append(per_building)
        mutations.append(
            (PHX01_SOURCE, mutated, "one planned critical-IT capacity row must remain")
        )

        mutated = copy.deepcopy(documents[SMF02_SOURCE])
        mutated["capacities"][0]["stage"] = "operational"
        mutations.append(
            (SMF02_SOURCE, mutated, "planned project critical-IT capacity must remain exact")
        )

        mutated = copy.deepcopy(documents[PHX01_SOURCE])
        mutated["capacities"][0]["base"] = 240
        mutations.append(
            (PHX01_SOURCE, mutated, "planned project critical-IT capacity must remain exact")
        )

        mutated = copy.deepcopy(documents[PHX01_SOURCE])
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_training",
                "evidence_key": mutated["evidence"][0]["key"],
                "as_of_date": "2026-05-21",
                "method": "company_disclosure",
                "confidence": 0.5,
            }
        ]
        mutations.append(
            (PHX01_SOURCE, mutated, "AI-ready language must not become a workload")
        )

        mutated = copy.deepcopy(documents[XNEELO_SOURCE])
        mutated["project"]["roles"] = {"operator": ["xneelo"]}
        mutations.append((XNEELO_SOURCE, mutated, "roles must remain empty"))

        mutated = copy.deepcopy(documents[FIN02_SOURCE])
        mutated["campus"]["coordinates"] = {
            "latitude": 60.2,
            "longitude": 24.7,
        }
        mutations.append((FIN02_SOURCE, mutated, "localities must remain ungeocoded"))

        mutated = copy.deepcopy(documents[CAPROCK_SOURCE])
        mutated["lifecycle"][0]["value"] = "foundations"
        mutations.append(
            (CAPROCK_SOURCE, mutated, "lifecycle must remain generic under_construction")
        )

        mutated = copy.deepcopy(documents[SMF02_SOURCE])
        forbidden_pue = copy.deepcopy(mutated["capacities"][0])
        forbidden_pue.update(
            {
                "metric": "pue",
                "unit": "ratio",
                "low": 1.2,
                "base": 1.2,
                "high": 1.2,
            }
        )
        mutated["capacities"].append(forbidden_pue)
        mutations.append(
            (SMF02_SOURCE, mutated, "one planned critical-IT capacity row must remain")
        )

        mutated = copy.deepcopy(documents[EQUINIX_SOURCE])
        mutated["evidence"][0]["kind"] = "satellite_imagery"
        mutations.append(
            (EQUINIX_SOURCE, mutated, "evidence must remain company disclosure only")
        )

        for name, document, message in mutations:
            with self.subTest(source=name, rejection=message):
                with self.assertRaisesRegex(AssertionError, message):
                    self._assert_guardrails(name, document)


if __name__ == "__main__":
    unittest.main()
