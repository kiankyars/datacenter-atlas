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
V18_DEFINITION = "open-seed-2026-07-19-v18.json"
V19_DEFINITION = "open-seed-2026-07-19-v19.json"

TGRU1_SOURCE = (
    "curated-official-2026-07-19-tecto-tgru1-santana-de-parnaiba.json"
)
TPOA1_SOURCE = "curated-official-2026-07-19-tecto-tpoa1-porto-alegre.json"
RJO2_SOURCE = "curated-official-2026-07-19-elea-rjo2-rio-ai-city.json"
SP03_SOURCE = "curated-official-2026-07-19-takoda-sp03-sumare.json"
RJ02_SOURCE = "curated-official-2026-07-19-takoda-rj02-rio-de-janeiro.json"
SP7_SOURCE = "curated-official-2026-07-19-equinix-sp7-sao-paulo-phase-1.json"
SP4_SOURCE = "curated-official-2026-07-19-equinix-sp4-sao-paulo-phase-5.json"
RJ3_SOURCE = (
    "curated-official-2026-07-19-equinix-rj3-rio-de-janeiro-phase-2.json"
)

SOURCES: dict[str, dict[str, Any]] = {
    TGRU1_SOURCE: {
        "sha256": "875e5b1777973e7dd2ded1b2dbeae5aa63700385a8b529d81ac89c75f5fd7f51",
        "retrieved_at": "2026-07-19T19:59:01Z",
        "country": "Brazil",
        "address": "Santana de Parnaíba, São Paulo, Brazil",
        "campus_key": "curated:tecto-tgru1-santana-de-parnaiba-data-center",
        "campus_name": "Tecto TGRU1 Santana de Parnaíba Data Center",
        "project_key": (
            "curated:tecto-tgru1-santana-de-parnaiba-data-center:"
            "current-facility-build"
        ),
        "project_name": "Tecto TGRU1 Current Facility Build",
        "entity_date": "2026-07-19",
        "lifecycle_date": "2026-07-19",
        "evidence_count": 2,
    },
    TPOA1_SOURCE: {
        "sha256": "a84fc185750ce3e7a8739088eae88cd249fde18da28d428920a97fdd04f8f8cc",
        "retrieved_at": "2026-07-19T19:55:52Z",
        "country": "Brazil",
        "address": "Sarandi, Porto Alegre, Rio Grande do Sul, Brazil",
        "campus_key": "curated:tecto-tpoa1-porto-alegre-data-center",
        "campus_name": "Tecto TPOA1 Porto Alegre Data Center",
        "project_key": (
            "curated:tecto-tpoa1-porto-alegre-data-center:current-facility-build"
        ),
        "project_name": "Tecto TPOA1 Current Facility Build",
        "entity_date": "2026-06-12",
        "lifecycle_date": "2026-07-19",
        "evidence_count": 2,
    },
    RJO2_SOURCE: {
        "sha256": "ce29b165b7599bda10b5410a1314f210adfed7c9198c24ad239f3bb52ddf7f01",
        "retrieved_at": "2026-07-19T19:56:17Z",
        "country": "Brazil",
        "address": "Olympic Park region, Rio de Janeiro, Brazil",
        "campus_key": "curated:elea-rjo2-rio-ai-city-data-center",
        "campus_name": "Elea RJO2 Rio AI City Data Center",
        "project_key": (
            "curated:elea-rjo2-rio-ai-city-data-center:current-facility-build"
        ),
        "project_name": "Elea RJO2 Current Facility Build",
        "entity_date": "2025-05-08",
        "lifecycle_date": "2025-05-08",
        "evidence_count": 2,
    },
    SP03_SOURCE: {
        "sha256": "7c2b3935816e0c11206f71384ed2bdafa50dec66d3729fc1d3ae96e1b7b72cdd",
        "retrieved_at": "2026-07-19T19:57:12Z",
        "country": "Brazil",
        "address": (
            "Est. M Luiz Fernandes Breda, Lote Gleb. AR7 Bandeirantes, "
            "Parque Residencial Florença, Sumaré/SP, CEP 13171-412, Brazil"
        ),
        "campus_key": "curated:takoda-sp03-sumare-data-center",
        "campus_name": "Takoda SP03 Sumaré Data Center",
        "project_key": (
            "curated:takoda-sp03-sumare-data-center:current-facility-build"
        ),
        "project_name": "Takoda SP03 Current Facility Build",
        "entity_date": "2025-11-28",
        "lifecycle_date": "2025-11-28",
        "evidence_count": 2,
    },
    RJ02_SOURCE: {
        "sha256": "60bfbbe638897f28e79f8f72920eacec0f4d8e3faa1885108aef6bac18f646b6",
        "retrieved_at": "2026-07-19T19:57:12Z",
        "country": "Brazil",
        "address": (
            "Estrada dos Bandeirantes, nº 10916, Lot 01, Pal 45343, "
            "Camorim, Rio de Janeiro/RJ, CEP 22783-111, Brazil"
        ),
        "campus_key": "curated:takoda-rj02-rio-de-janeiro-data-center",
        "campus_name": "Takoda RJ02 Rio de Janeiro Data Center",
        "project_key": (
            "curated:takoda-rj02-rio-de-janeiro-data-center:current-facility-build"
        ),
        "project_name": "Takoda RJ02 Current Facility Build",
        "entity_date": "2025-11-28",
        "lifecycle_date": "2025-11-28",
        "evidence_count": 2,
    },
    SP7_SOURCE: {
        "sha256": "2e53c941c1c17505f6ade429c97798021de5af39f6a3ffdceab6f93a26c369d7",
        "retrieved_at": "2026-07-19T19:55:41Z",
        "country": "Brazil",
        "address": "São Paulo, Brazil",
        "campus_key": "curated:equinix-sp7-sao-paulo-data-center",
        "campus_name": "Equinix SP7 São Paulo Data Center",
        "project_key": "curated:equinix-sp7-sao-paulo-data-center:phase-1",
        "project_name": "Equinix SP7 Phase 1",
        "entity_date": "2025-12-31",
        "lifecycle_date": "2025-12-31",
        "evidence_count": 1,
    },
    SP4_SOURCE: {
        "sha256": "10f64d09105b5d2b05befaee0393376fe902c67ac721ab7eeed7986ce227c6e4",
        "retrieved_at": "2026-07-19T19:55:41Z",
        "country": "Brazil",
        "address": "São Paulo, Brazil",
        "campus_key": "curated:equinix-sp4-sao-paulo-data-center",
        "campus_name": "Equinix SP4 São Paulo Data Center",
        "project_key": "curated:equinix-sp4-sao-paulo-data-center:phase-5",
        "project_name": "Equinix SP4 Phase 5",
        "entity_date": "2025-12-31",
        "lifecycle_date": "2025-12-31",
        "evidence_count": 1,
    },
    RJ3_SOURCE: {
        "sha256": "43988c572ddae30921854c6ff7bc9e14ba8d06e8cf3592df0ec881ace49275af",
        "retrieved_at": "2026-07-19T19:55:41Z",
        "country": "Brazil",
        "address": "Rio de Janeiro, Brazil",
        "campus_key": "curated:equinix-rj3-rio-de-janeiro-data-center",
        "campus_name": "Equinix RJ3 Rio de Janeiro Data Center",
        "project_key": "curated:equinix-rj3-rio-de-janeiro-data-center:phase-2",
        "project_name": "Equinix RJ3 Phase 2",
        "entity_date": "2025-12-31",
        "lifecycle_date": "2025-12-31",
        "evidence_count": 1,
    },
}

TAKODA_SOURCES = (SP03_SOURCE, RJ02_SOURCE)
EQUINIX_SOURCES = (SP7_SOURCE, SP4_SOURCE, RJ3_SOURCE)

CAPTURES: dict[str, dict[str, Any]] = {
    "ecdc86b877d38daaed5c5e12d35c74574c75dc386869ef80444f18568b9e885e": {
        "body_bytes": 115962,
        "headers_bytes": 277,
        "headers_sha256": "a5a3e8da6f9895b7a19d2979c7c065e6f429cbb97deeb979bbddb97d150a119d",
        "response_date": "2026-07-19T19:55:52Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": None,
        "content_length": None,
        "url": "https://tecto.com/data-centers/em-construcao/tgru1/",
    },
    "a22354ec2f886372ea5554eb5e41f762337b53968f5195872dee835d40df0bd8": {
        "body_bytes": 114659,
        "headers_bytes": 279,
        "headers_sha256": "351b16628c5228d86d36e84be99b9b7a099971cd96da900e3862c58d07717adb",
        "response_date": "2026-07-19T19:59:01Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": None,
        "content_length": None,
        "url": (
            "https://tecto.com/radar-tecto/tecto-data-centers-anuncia-plano-"
            "de-investimento-de-us-2-bilhoes-e-amplia-atuacao-comercial-ao-"
            "oferecer-solucoes-para-o-mercado-enterprise/"
        ),
    },
    "c79ccd8ac6abb8d2b74867c74745b60db25c718c6941f25701a7079bbc0469cd": {
        "body_bytes": 115529,
        "headers_bytes": 279,
        "headers_sha256": "aaa5fd7633e10a0534bcfcedf01d437ddda961abd0f5532e9200bf24b2ec3b17",
        "response_date": "2026-07-19T19:55:52Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": None,
        "content_length": None,
        "url": "https://tecto.com/data-centers/em-construcao/tpoa1/",
    },
    "c07cb1e22859d98c4a12802af63ca9396c36fa73755a1a2344a530f9dad5dc98": {
        "body_bytes": 114352,
        "headers_bytes": 277,
        "headers_sha256": "a5505a5b4f553d7a452c173eb66ee6e2281a454e7bb58a2f97437a30f3128303",
        "response_date": "2026-07-19T19:55:52Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": None,
        "content_length": None,
        "url": (
            "https://tecto.com/radar-tecto/tecto-anuncia-investimento-de-r-"
            "700-milhoes-em-novo-data-center-em-porto-alegre-conectado-ao-"
            "cabo-submarino-da-v-tal/"
        ),
    },
    "d94b3c0e74e521f76af7c1487a6c90f5f9c502c0fb0efdcdee366a96a447810a": {
        "body_bytes": 82198,
        "headers_bytes": 1735,
        "headers_sha256": "25538f245d96d3e8b1bf4cacaf759c990852008a195d5c983149e3f93bd5b9c4",
        "response_date": "2026-07-19T19:52:21Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://eleadatacenters.com/en/2025/05/08/"
            "elea-announces-rio-ai-city/"
        ),
    },
    "8d8da13643a75a87ea56192ca0ab10a2eca117ffc78be2c0fb3a3095b1153191": {
        "body_bytes": 79000,
        "headers_bytes": 1683,
        "headers_sha256": "2a7924c0fe710e2e49d001925a3c33a72d4b0a60d463b66fc58f115491f9bee9",
        "response_date": "2026-07-19T19:56:17Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": "https://eleadatacenters.com/en/rio-ai-city/",
    },
    "bcd576a3e543160839532193f938640efdb1732cd949809bd400ffed85782c8f": {
        "body_bytes": 1280603,
        "headers_bytes": 338,
        "headers_sha256": "33472d9084811eb7085b321e704fa909eaf4b8db5608cbfbfd17d2fd1d786b05",
        "response_date": "2026-07-19T19:52:22Z",
        "last_modified": "2025-12-05T14:50:08Z",
        "content_type": "application/pdf",
        "content_encoding": None,
        "content_length": 1280603,
        "url": (
            "https://takodadatacenters.com/wp-content/uploads/2025/12/"
            "Deb.-Takoda-Escritura-de-Emissao-v.assinada.pdf"
        ),
    },
    "3235f111098b2cbf84c2ee12be9622aff3f7ec5e4791fece595a264c7fb9e697": {
        "body_bytes": 114688,
        "headers_bytes": 483,
        "headers_sha256": "cc2ed8349eab9cc4a480794c34039e8a63967b4f6a8c67fb00a4d2a2f80df68a",
        "response_date": "2026-07-19T19:57:12Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": 28942,
        "url": "https://takodadatacenters.com/new-data-centers/",
    },
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54": {
        "body_bytes": 4071886,
        "headers_bytes": 2615,
        "headers_sha256": "226fb23df1efbdadb6d55352d6c908a3c9c478c1aed00062225dc4539a43f397",
        "response_date": "2026-07-19T19:55:41Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "url": (
            "https://investor.equinix.com/sec-filings/all-sec-filings/"
            "content/0001101239-26-000032/eqix-20251231.htm"
        ),
    },
}


class LatamOfficialNextTrancheTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        capture = CAPTURES[evidence["content_hash"]]
        metadata = evidence["metadata"]
        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(capture["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], capture["headers_sha256"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], capture["content_type"])
        self.assertEqual(
            metadata["content_encoding_as_received"], capture["content_encoding"]
        )
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            capture["content_length"],
        )
        self.assertEqual(metadata["response_http_date"], capture["response_date"])
        self.assertEqual(metadata["http_last_modified_at"], capture["last_modified"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(evidence["source_url"], capture["url"])
        for key in ("requested_url", "effective_url", "canonical_url"):
            self.assertEqual(metadata[key], capture["url"])
        self.assertNotIn("request_started_at", metadata)
        self.assertNotIn("request_start_utc", metadata)
        self.assertIn("no request-start artifact was supplied", metadata["retrieval_method"])
        self.assertIn("not redistributed", metadata["rights_scope"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), expected["evidence_count"])
        self.assertEqual(
            {row["retrieved_at"] for row in document["evidence"]},
            {expected["retrieved_at"]},
        )
        for evidence in document["evidence"]:
            self._assert_capture(evidence)

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["as_of_date"], expected["entity_date"])
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["campus"]["name"], expected["campus_name"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["project"]["name"], expected["project_name"])

        self.assertEqual(len(document["lifecycle"]), 1)
        lifecycle = document["lifecycle"][0]
        self.assertEqual(lifecycle["entity"], "project")
        self.assertEqual(lifecycle["value"], "under_construction")
        self.assertEqual(lifecycle["as_of_date"], expected["lifecycle_date"])
        self.assertEqual(
            lifecycle["method"], "authoritative_physical_status_update"
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])

        metadata_text = json.dumps(
            [row["metadata"] for row in document["evidence"]],
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertIn("classification_guardrail", metadata_text)
        self.assertIn("role_guardrail", metadata_text)
        self.assertIn("capacity", metadata_text.lower())
        self.assertIn("no capacity row", metadata_text.lower())

    def _database_state(
        self, order: tuple[str, ...] | list[str]
    ) -> tuple[list[tuple[Any, ...]], ...]:
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
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                self.assertEqual(validate_database(connection), [])
                return (
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT kind, stable_key FROM entities "
                            "ORDER BY kind, stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT title, content_hash, metadata_json FROM evidence "
                            "ORDER BY content_hash"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, name, latitude, longitude, "
                            "geometry_json, tags_json FROM entity_snapshots "
                            "JOIN entities ON entities.id = entity_snapshots.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                )
            finally:
                connection.close()

    def test_exact_source_hashes_capture_lineage_and_release_exclusion(self) -> None:
        release_texts = [
            (ROOT / "sources" / name).read_text(encoding="utf-8")
            for name in (V18_DEFINITION, V19_DEFINITION)
        ]
        for name, expected in SOURCES.items():
            source_path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                expected["sha256"],
            )
            document = self._load(name)
            self._assert_document(name, document)
            for release_text in release_texts:
                self.assertNotIn(name, release_text)
                self.assertNotIn(expected["campus_key"], release_text)
                self.assertNotIn(expected["project_key"], release_text)

        self.assertEqual(
            self._load(SP03_SOURCE)["evidence"],
            self._load(RJ02_SOURCE)["evidence"],
        )
        equinix_evidence = [
            self._load(name)["evidence"] for name in EQUINIX_SOURCES
        ]
        self.assertEqual(equinix_evidence[0], equinix_evidence[1])
        self.assertEqual(equinix_evidence[0], equinix_evidence[2])

    def test_source_specific_numbers_conflicts_and_guardrails(self) -> None:
        tgru1 = self._load(TGRU1_SOURCE)
        current, support = tgru1["evidence"]
        self.assertIsNone(current["published_at"])
        self.assertEqual(current["metadata"]["status_wording_as_reported"], "Em construção")
        self.assertEqual(current["metadata"]["planned_capacity_as_reported_mw"], 200)
        self.assertEqual(
            current["metadata"]["copied_total_capacity_block_as_reported_mw"],
            220,
        )
        self.assertIn("does not reconcile", current["metadata"]["capacity_conflict_guardrail"])
        self.assertEqual(support["metadata"]["internal_dateline_as_reported"], "7 April 2026")

        tpoa1 = self._load(TPOA1_SOURCE)
        current, release = tpoa1["evidence"]
        self.assertEqual(
            current["metadata"]["copied_total_capacity_block_as_reported_mw"],
            220,
        )
        self.assertEqual(release["metadata"]["total_power_as_reported_mw"], 20)
        self.assertEqual(release["metadata"]["first_phase_capacity_as_reported_mw"], 3)
        self.assertEqual(
            release["metadata"]["invalid_placeholder_dateline_as_displayed"],
            "São Paulo, XX de março de 2026",
        )
        self.assertIn("never interpreted", release["metadata"]["publication_date_guardrail"])
        self.assertIn("untyped evidence metadata", release["metadata"]["capacity_metric_guardrail"])

        elea = self._load(RJO2_SOURCE)
        release, current = elea["evidence"]
        self.assertEqual(release["published_at"], "2025-05-08")
        self.assertEqual(release["metadata"]["rjo2_capacity_as_reported_mw"], 80)
        self.assertEqual(
            release["metadata"]["rio_ai_city_first_phase_energy_capacity_as_reported_gw"],
            1.5,
        )
        self.assertEqual(
            release["metadata"]["future_rjo3_rjo4_combined_capacity_as_reported_mw"],
            120,
        )
        self.assertIn("not RJO2", release["metadata"]["capacity_scope_guardrail"])
        self.assertIn("construction of RJO2", current["metadata"]["development_wording_as_reported"])
        self.assertIn("does not create a second", current["metadata"]["corroboration_scope"])

        takoda = self._load(SP03_SOURCE)
        deed, platform = takoda["evidence"]
        self.assertEqual(deed["metadata"]["document_date_as_reported"], "28 November 2025")
        self.assertEqual(deed["metadata"]["document_page_count"], 55)
        self.assertEqual(deed["metadata"]["sp03_activity_as_reported"], "Data Center em construção")
        self.assertEqual(deed["metadata"]["rj02_activity_as_reported"], "Data Center em construção")
        self.assertIn("CEP 13171-412", deed["metadata"]["sp03_address_as_reported"])
        self.assertIn("CEP 22783-111", deed["metadata"]["rj02_address_as_reported"])
        self.assertEqual(platform["metadata"]["dual_campus_platform_capacity_as_reported_mw"], 160)
        self.assertEqual(platform["metadata"]["sumare_campus_capacity_as_reported_mw"], 96)
        self.assertEqual(platform["metadata"]["barra_campus_capacity_as_reported_mw"], 64)
        self.assertEqual(platform["metadata"]["shared_phase_one_capacity_as_reported_mw"], 18)
        self.assertIn("not allocated", platform["metadata"]["capacity_scope_guardrail"])

        equinix = self._load(SP7_SOURCE)["evidence"][0]["metadata"]
        self.assertEqual(equinix["construction_table_as_of_date"], "2025-12-31")
        self.assertEqual(
            equinix["target_projects_as_reported"],
            [
                {"property": "SP7 phase 1", "location": "São Paulo", "target_open_quarter": "Q4 2026", "sellable_cabinets": 600, "approximate_total_capex_usd_millions": 35},
                {"property": "SP4 phase 5", "location": "São Paulo", "target_open_quarter": "Q2 2027", "sellable_cabinets": 700, "approximate_total_capex_usd_millions": 74},
                {"property": "RJ3 phase 2", "location": "Rio de Janeiro", "target_open_quarter": "Q4 2026", "sellable_cabinets": 550, "approximate_total_capex_usd_millions": 46},
            ],
        )
        self.assertIn("forward-looking", equinix["target_date_guardrail"])
        self.assertIn("not MW", equinix["cabinet_guardrail"])
        self.assertIn("approximate", equinix["capex_guardrail"])

    def test_individual_sources_import_offline_with_narrow_semantics(self) -> None:
        for name, expected in SOURCES.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with patch.object(
                        socket, "socket", side_effect=AssertionError("network used")
                    ), patch.object(
                        socket,
                        "create_connection",
                        side_effect=AssertionError("network used"),
                    ):
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=expected["retrieved_at"],
                        )
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, expected["evidence_count"])
                    self.assertEqual(validate_database(connection), [])
                    self.assertEqual(
                        [
                            tuple(row)
                            for row in connection.execute(
                                "SELECT kind, stable_key FROM entities "
                                "ORDER BY kind, stable_key"
                            )
                        ],
                        [
                            ("campus", expected["campus_key"]),
                            ("project", expected["project_key"]),
                        ],
                    )
                    self.assertEqual(
                        [
                            tuple(row)
                            for row in connection.execute(
                                "SELECT status, as_of_date, method "
                                "FROM lifecycle_observations"
                            )
                        ],
                        [
                            (
                                "under_construction",
                                expected["lifecycle_date"],
                                "authoritative_physical_status_update",
                            )
                        ],
                    )
                    for table in (
                        "capacity_estimates",
                        "workload_observations",
                        "operating_model_observations",
                    ):
                        self.assertEqual(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0],
                            0,
                        )
                    snapshots = connection.execute(
                        "SELECT latitude, longitude, geometry_json, tags_json "
                        "FROM entity_snapshots"
                    ).fetchall()
                    self.assertEqual(len(snapshots), 2)
                    for snapshot in snapshots:
                        self.assertIsNone(snapshot["latitude"])
                        self.assertIsNone(snapshot["longitude"])
                        self.assertIsNone(snapshot["geometry_json"])
                        tags = json.loads(snapshot["tags_json"])
                        self.assertEqual(tags["address"], expected["address"])
                        self.assertFalse(any(key.startswith("role:") for key in tags))
                finally:
                    connection.close()

    def test_shared_evidence_import_order_is_invariant(self) -> None:
        takoda_states = [
            self._database_state(order)
            for order in itertools.permutations(TAKODA_SOURCES)
        ]
        for state in takoda_states[1:]:
            self.assertEqual(state, takoda_states[0])
        self.assertEqual(len(takoda_states[0][0]), 4)
        self.assertEqual(len(takoda_states[0][1]), 2)

        equinix_states = [
            self._database_state(order)
            for order in itertools.permutations(EQUINIX_SOURCES)
        ]
        for state in equinix_states[1:]:
            self.assertEqual(state, equinix_states[0])
        self.assertEqual(len(equinix_states[0][0]), 6)
        self.assertEqual(len(equinix_states[0][1]), 1)

    def test_combined_import_has_exact_entities_evidence_and_no_classifications(self) -> None:
        state = self._database_state(list(SOURCES))
        entities, evidence, lifecycle, snapshots = state
        self.assertEqual(len(entities), 16)
        self.assertEqual(
            {kind: sum(row[0] == kind for row in entities) for kind in ("campus", "project")},
            {"campus": 8, "project": 8},
        )
        self.assertEqual(len(evidence), 9)
        self.assertEqual(len(lifecycle), 8)
        self.assertEqual(len(snapshots), 16)
        self.assertEqual(
            {row[0] for row in lifecycle},
            {expected["project_key"] for expected in SOURCES.values()},
        )
        self.assertEqual({row[1] for row in lifecycle}, {"under_construction"})
        for row in snapshots:
            self.assertIsNone(row[2])
            self.assertIsNone(row[3])
            self.assertIsNone(row[4])
            tags = json.loads(row[5])
            self.assertFalse(any(key.startswith("role:") for key in tags))

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
                    for name in SOURCES:
                        CuratedOfficialSourceAdapter().import_file(
                            connection,
                            ROOT / "sources" / name,
                            retrieved_at=SOURCES[name]["retrieved_at"],
                        )
                for table in (
                    "capacity_estimates",
                    "workload_observations",
                    "operating_model_observations",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                    )
            finally:
                connection.close()

    def test_semantic_negative_mutations_fail_tranche_guardrails(self) -> None:
        document = self._load(TGRU1_SOURCE)
        mutations: list[dict[str, Any]] = []

        mutated = copy.deepcopy(document)
        mutated["campus"]["roles"] = {"owner": ["Tecto Data Centers"]}
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["coordinates"] = {
            "latitude": -23.5,
            "longitude": -46.8,
        }
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["project"]["geometry"] = {
            "type": "Point",
            "coordinates": [-46.8, -23.5],
        }
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["lifecycle"][0]["value"] = "commissioning"
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["operating_models"] = [
            {
                "entity": "project",
                "value": "hyperscale_self_build",
                "evidence_key": document["lifecycle"][0]["evidence_key"],
                "as_of_date": "2026-07-19",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["workloads"] = [
            {
                "entity": "project",
                "value": "ai_specialized_unspecified",
                "evidence_key": document["lifecycle"][0]["evidence_key"],
                "as_of_date": "2026-07-19",
                "method": "company_disclosure",
                "confidence": 0.99,
            }
        ]
        mutations.append(mutated)

        mutated = copy.deepcopy(document)
        mutated["capacities"] = [
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 200,
                "base": 200,
                "high": 200,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": document["lifecycle"][0]["evidence_key"],
                "as_of_date": "2026-07-19",
                "target_date": None,
                "notes": "Invalid normalization of an untyped and conflicting claim.",
            }
        ]
        mutations.append(mutated)

        for mutated in mutations:
            with self.assertRaises(AssertionError):
                self._assert_document(TGRU1_SOURCE, mutated)


if __name__ == "__main__":
    unittest.main()
