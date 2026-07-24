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
BASE_DEFINITION = "open-seed-2026-07-19-v20.json"
BASE_DEFINITION_SHA256 = (
    "099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd"
)

BITDEER_SOURCE = (
    "curated-official-2026-07-19-bitdeer-fox-creek-alberta.json"
)
PUREDC_SOURCE = (
    "curated-official-2026-07-19-pure-dc-brent-cross-lon01-b2.json"
)
NXERA_SOURCE = (
    "curated-official-2026-07-19-tm-nxera-iskandar-puteri-first-building.json"
)
FIRSTCOLO_SOURCE = "curated-official-2026-07-19-firstcolo-fra7-rosbach.json"

SOURCES: dict[str, dict[str, Any]] = {
    BITDEER_SOURCE: {
        "sha256": "6cbe4fb717074b711d244cc02b5b559a770f0a7911af362f5cfe789394186734",
        "retrieved_at": "2026-07-19T20:35:17Z",
        "published_at": "2026-06-02",
        "publisher": "Bitdeer Technologies Group",
        "source_family": "bitdeer_globenewswire_distributions",
        "evidence_key": (
            "bitdeer-fox-creek-groundbreaking-2026-06-02-"
            "captured-2026-07-19"
        ),
        "country": "Canada",
        "address": (
            "Near Fox Creek, Municipal District of Greenview No. 16, "
            "Alberta, Canada"
        ),
        "campus_key": "curated:bitdeer-fox-creek-alberta-campus",
        "campus_name": "Bitdeer Fox Creek Alberta Campus",
        "project_key": (
            "curated:bitdeer-fox-creek-alberta-campus:"
            "integrated-facility-current-build"
        ),
        "project_name": (
            "Bitdeer Fox Creek Integrated Energy and Computing Facility "
            "Current Build"
        ),
        "as_of_date": "2026-06-02",
        "lifecycle": "under_construction",
        "lifecycle_method": "authoritative_construction_start",
        "workload": "crypto_mining",
        "capacity": ("generation_nameplate_mw", "planned", 101.0),
    },
    PUREDC_SOURCE: {
        "sha256": "792dc6b6db721fd7efd4bf00493b6546264acfe8a563b6b4ad222be282834c1d",
        "retrieved_at": "2026-07-19T20:35:16Z",
        "published_at": "2026-05-28",
        "publisher": "Pure DC",
        "source_family": "pure_dc_news",
        "evidence_key": (
            "pure-dc-brent-cross-lon01-b2-build-update-2026-05-28-"
            "captured-2026-07-19"
        ),
        "country": "United Kingdom",
        "address": "Brent Cross, North London, United Kingdom",
        "campus_key": "curated:pure-dc-brent-cross-lon01-campus",
        "campus_name": "Pure DC Brent Cross LON01 Campus",
        "project_key": (
            "curated:pure-dc-brent-cross-lon01-campus:b2-composite-build"
        ),
        "project_name": "Pure DC Brent Cross LON01 B2 Composite Build",
        "as_of_date": "2026-05-28",
        "lifecycle": "under_construction",
        "lifecycle_method": "authoritative_physical_status_update",
        "workload": None,
        "capacity": None,
    },
    NXERA_SOURCE: {
        "sha256": "e6b14f5c9216671dfcd0ae182d0fc2c4b43fe2e39f5db177e806d66331cb84f0",
        "retrieved_at": "2026-07-19T20:35:18Z",
        "published_at": "2026-04-16",
        "publisher": "Telekom Malaysia",
        "source_family": "telekom_malaysia_news",
        "evidence_key": (
            "tm-nxera-iskandar-puteri-topping-out-2026-04-16-"
            "captured-2026-07-19"
        ),
        "country": "Malaysia",
        "address": "Iskandar Puteri, Johor, Malaysia",
        "campus_key": "curated:tm-nxera-iskandar-puteri-johor-campus",
        "campus_name": "TM Nxera Iskandar Puteri Johor Campus",
        "project_key": (
            "curated:tm-nxera-iskandar-puteri-johor-campus:first-building"
        ),
        "project_name": "TM Nxera Iskandar Puteri First Building",
        "as_of_date": "2026-04-16",
        "lifecycle": "shell",
        "lifecycle_method": "authoritative_physical_status_update",
        "workload": None,
        "capacity": ("grid_connection_mw", "contracted", 280.0),
    },
    FIRSTCOLO_SOURCE: {
        "sha256": "8df80cdc203f714795495b13ffd2bbf35d846da9ed4350f3ad657bb6af64d707",
        "retrieved_at": "2026-07-19T20:35:17Z",
        "published_at": "2026-06-15",
        "publisher": "firstcolo",
        "source_family": "firstcolo_news",
        "evidence_key": (
            "firstcolo-fra7-rosbach-groundbreaking-2026-06-15-"
            "captured-2026-07-19"
        ),
        "country": "Germany",
        "address": "Rosbach vor der Höhe, Hesse, Germany",
        "campus_key": "curated:firstcolo-fra7-rosbach-campus",
        "campus_name": "firstcolo FRA7 Rosbach Campus",
        "project_key": (
            "curated:firstcolo-fra7-rosbach-campus:fra7-current-build"
        ),
        "project_name": "firstcolo FRA7 Current Build",
        "as_of_date": "2026-06-15",
        "lifecycle": "under_construction",
        "lifecycle_method": "authoritative_construction_start",
        "workload": None,
        "capacity": None,
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    BITDEER_SOURCE: {
        "body_bytes": 76833,
        "content_hash": (
            "6c3cdc34dc3acb8521e7a983f0c585f0c6471fb3564b5f116d368539ce6e6899"
        ),
        "headers_bytes": 2353,
        "headers_hash": (
            "54e85cca9fd9179bd378b6dfbba3b11956d32d4c9b57e7b8ddfb9948f8d9c492"
        ),
        "writeout_bytes": 288,
        "writeout_hash": (
            "0660d2f765f6fecd86daa8cc7818a1bda3227275ffff0e77f9e6afce23b7c2df"
        ),
        "content_type": "text/html; charset=utf-8",
        "content_length": 16383,
        "download_bytes": 16383,
        "date": "2026-07-19T20:35:17Z",
        "last_modified": "2026-07-19T20:35:17Z",
        "url": (
            "https://www.globenewswire.com/news-release/2026/06/02/3305088/"
            "0/en/bitdeer-breaks-ground-on-new-energy-and-digital-"
            "infrastructure-facility-in-alberta-canada.html"
        ),
    },
    PUREDC_SOURCE: {
        "body_bytes": 86077,
        "content_hash": (
            "79d293abb6590f7321e8bee14f1adc732a171e774d2589bb94be1843df21acf0"
        ),
        "headers_bytes": 849,
        "headers_hash": (
            "88111e46e4f68f69f4d6cd9d674a3d150d5f8e6f82eda3fbcac3b6f990538870"
        ),
        "writeout_bytes": 238,
        "writeout_hash": (
            "fe96bc19734e02128077cf08448899e2ece61608114eabc240aec7ed71491186"
        ),
        "content_type": "text/html; charset=UTF-8",
        "content_length": None,
        "download_bytes": 21394,
        "date": "2026-07-19T20:35:16Z",
        "last_modified": None,
        "url": (
            "https://puredc.com/2026/05/28/pure-dc-appoints-glencar-for-"
            "next-phase-of-its-90mw-brent-cross-campus-build-out"
        ),
    },
    NXERA_SOURCE: {
        "body_bytes": 67371,
        "content_hash": (
            "06e2eb9a4c4476501a8f8182e6baa9d1eaedcdc11f8c2eaf04a5e8f3465aebd0"
        ),
        "headers_bytes": 1089,
        "headers_hash": (
            "6c8d3adcd6eed97a530c1642e02d2e1440a24fdedbf47c63385d179a5790ccfb"
        ),
        "writeout_bytes": 175,
        "writeout_hash": (
            "75c84bab8fa75c225bc1b7efab4d42f1edf78b9a178f7a628a6b8302e3929780"
        ),
        "content_type": "text/html; charset=UTF-8",
        "content_length": None,
        "download_bytes": 15996,
        "date": "2026-07-19T20:35:18Z",
        "last_modified": None,
        "url": "https://tm.com.my/news/nxera_topping_out_ceremony",
    },
    FIRSTCOLO_SOURCE: {
        "body_bytes": 695319,
        "content_hash": (
            "c129305ab7980df1d4e46272c57a0f9c2dd05dbf0e25bd021d9ae420fc537c34"
        ),
        "headers_bytes": 455,
        "headers_hash": (
            "83939fba4eceac94e205872988254578fd8059130c99227f055e2d870b2b21f4"
        ),
        "writeout_bytes": 245,
        "writeout_hash": (
            "1898df9bb95014d77e3cc955bdd3e4f7dc7c157c1352d80026f34ea24e32863a"
        ),
        "content_type": "text/html; charset=UTF-8",
        "content_length": None,
        "download_bytes": 85976,
        "date": "2026-07-19T20:35:17Z",
        "last_modified": "2026-07-19T20:10:11Z",
        "url": (
            "https://firstcolo.net/en/250-million-euros-for-ai-"
            "infrastructure-firstcolo-breaks-ground-on-fra7-data-center-"
            "in-hesse/"
        ),
    },
}


class BitdeerPureDcNxeraFirstcoloTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
        capture = CAPTURES[name]
        if document["schema_version"] != "1.0":
            raise AssertionError("schema version must remain canonical")
        if len(document["evidence"]) != 1:
            raise AssertionError("exactly one captured disclosure must remain")

        evidence = document["evidence"][0]
        if (
            evidence["key"] != expected["evidence_key"]
            or evidence["kind"] != "company_disclosure"
            or evidence["publisher"] != expected["publisher"]
            or evidence["source_family"] != expected["source_family"]
            or evidence["published_at"] != expected["published_at"]
            or evidence["retrieved_at"] != expected["retrieved_at"]
            or evidence["content_hash"] != capture["content_hash"]
            or evidence["source_url"] != capture["url"]
        ):
            raise AssertionError("evidence identity and dates must remain exact")

        metadata = evidence["metadata"]
        if metadata["content_hash_verification"] != "fetched_bytes_sha256":
            raise AssertionError("capture must remain byte verified")
        if str(capture["body_bytes"]) not in metadata["content_hash_scope"]:
            raise AssertionError("body byte count must remain exact")
        if str(capture["headers_bytes"]) not in metadata["capture_headers_scope"]:
            raise AssertionError("header byte count must remain exact")
        if metadata["capture_headers_sha256"] != capture["headers_hash"]:
            raise AssertionError("header hash must remain exact")
        if str(capture["writeout_bytes"]) not in metadata["capture_curl_writeout_scope"]:
            raise AssertionError("writeout byte count must remain exact")
        if metadata["capture_curl_writeout_sha256"] != capture["writeout_hash"]:
            raise AssertionError("writeout hash must remain exact")
        if (
            "not redistributed" not in metadata["capture_artifact_guardrail"]
            or "no cookie or token value" not in metadata["capture_artifact_guardrail"]
        ):
            raise AssertionError("temporary raw-capture guardrail must remain")
        if (
            metadata["http_status"] != 200
            or metadata["content_type"] != capture["content_type"]
            or metadata["content_encoding_as_received"] != "gzip"
            or metadata["http_transfer_encoding_as_received"] is not None
            or metadata["http_content_length_bytes_as_received"]
            != capture["content_length"]
            or metadata["curl_size_download_bytes_as_received"]
            != capture["download_bytes"]
            or metadata["response_http_date"] != capture["date"]
            or metadata["http_last_modified_at"] != capture["last_modified"]
            or metadata["response_header_blocks"] != 1
            or metadata["redirect_count"] != 0
        ):
            raise AssertionError("HTTP capture facts must remain exact")
        if any(
            metadata[key] != capture["url"]
            for key in ("requested_url", "effective_url", "canonical_url")
        ):
            raise AssertionError("requested effective and canonical URLs must remain exact")
        if (
            "no request-start artifact was supplied" not in metadata["retrieval_method"]
            or "exact response HTTP Date" not in metadata["retrieved_at_semantics"]
            or "not redistributed" not in metadata["rights_scope"]
            or "No publisher photograph" not in metadata["imagery_guardrail"]
        ):
            raise AssertionError("provenance and non-imagery guardrails must remain")

        for entity_name in ("campus", "project"):
            entity = document[entity_name]
            if (
                entity["country"] != expected["country"]
                or entity["address"] != expected["address"]
                or entity["roles"] != {}
                or entity["coordinates"] is not None
                or entity["geometry"] is not None
                or entity["evidence_key"] != expected["evidence_key"]
                or entity["as_of_date"] != expected["as_of_date"]
                or entity["method"] != "authoritative_locality"
            ):
                raise AssertionError("entities must remain broad authoritative localities")
        if (
            document["campus"]["stable_key"] != expected["campus_key"]
            or document["campus"]["name"] != expected["campus_name"]
            or document["project"]["stable_key"] != expected["project_key"]
            or document["project"]["name"] != expected["project_name"]
        ):
            raise AssertionError("canonical entity identities must remain exact")

        lifecycle = document["lifecycle"]
        if len(lifecycle) != 1:
            raise AssertionError("exactly one project lifecycle must remain")
        if lifecycle[0] != {
            "entity": "project",
            "value": expected["lifecycle"],
            "evidence_key": expected["evidence_key"],
            "as_of_date": expected["as_of_date"],
            "method": expected["lifecycle_method"],
            "confidence": 0.99,
        }:
            raise AssertionError("source-scoped lifecycle must remain exact")
        if document["operating_models"] != []:
            raise AssertionError("operating models must remain empty")

        if expected["workload"] is None:
            if document["workloads"] != []:
                raise AssertionError("design capability must not become a workload")
        else:
            if document["workloads"] != [
                {
                    "entity": "project",
                    "value": expected["workload"],
                    "evidence_key": expected["evidence_key"],
                    "as_of_date": expected["as_of_date"],
                    "method": "company_disclosure",
                    "confidence": 0.99,
                }
            ]:
                raise AssertionError("only source-explicit crypto mining must remain")

        capacity = expected["capacity"]
        if capacity is None:
            if document["capacities"] != []:
                raise AssertionError("untyped power and inequalities create no capacity row")
        else:
            if len(document["capacities"]) != 1:
                raise AssertionError("exactly one source-typed capacity must remain")
            row = document["capacities"][0]
            metric, stage, value = capacity
            if (
                row["entity"] != "campus"
                or row["metric"] != metric
                or row["stage"] != stage
                or row["unit"] != "MW"
                or (row["low"], row["base"], row["high"])
                != (value, value, value)
                or row["method"] != "reported"
                or row["confidence"] != 0.99
                or row["evidence_key"] != expected["evidence_key"]
                or row["as_of_date"] != expected["as_of_date"]
                or row["target_date"] is not None
            ):
                raise AssertionError("source-typed campus capacity must remain exact")

        if name == BITDEER_SOURCE:
            if (
                metadata["reported_onsite_natural_gas_generation_nameplate_mw"] != 101
                or metadata["reported_computing_capacity_mw_approximate"] != 100
                or metadata["reported_aeso_interconnection_mw_approved"] != 99
                or "creates no normalized capacity row"
                not in metadata["computing_capacity_guardrail"]
                or "creates no grid_connection_mw row"
                not in metadata["interconnection_guardrail"]
                or metadata["energization_forecast_as_reported"] != "Q2 2027"
                or "crypto_mining" not in metadata["workload_scope"]
                or "creates no AI" not in metadata["future_workload_guardrail"]
            ):
                raise AssertionError("Bitdeer capacity and workload scope must remain exact")
        elif name == PUREDC_SOURCE:
            if (
                metadata["reported_total_campus_capacity_mw"] != 90
                or metadata["reported_existing_b1_capacity_mw"] != 20
                or metadata["reported_b2_extension_area_sqm"] != 23186
                or "No B2 capacity is normalized or calculated"
                not in metadata["b2_capacity_guardrail"]
                or metadata["b2_completion_forecast_as_reported"] != "Q2 2029"
                or "different stages" not in metadata["stage_guardrail"]
            ):
                raise AssertionError("Pure DC composite B2 scope must remain exact")
        elif name == NXERA_SOURCE:
            if (
                metadata["reported_tenaga_electricity_supply_agreement_mw"] != 280
                or metadata["reported_campus_scalability_mw_maximum"] != 200
                or metadata["pue_target_as_reported"]
                != "less than or equal to 1.30 at full load"
                or "not converted into a point estimate" not in metadata["pue_guardrail"]
                or metadata["first_phase_commercial_operations_forecast_as_reported"]
                != "second half of 2026"
                or "not proof of current commissioning or operation"
                not in metadata["commercial_language_guardrail"]
            ):
                raise AssertionError("TM Nxera shell and grid scope must remain exact")
        elif name == FIRSTCOLO_SOURCE:
            if (
                metadata["reported_planned_total_capacity_mw_approximate"] != 24
                or metadata["reported_maximum_rack_power_density_kw"] != 200
                or metadata["reported_investment_eur_approximate"] != 250_000_000
                or metadata["pue_target_as_reported"] != "below 1.2"
                or metadata["waste_heat_commitment_years_minimum_as_reported"] != 20
                or "creates no generation asset" not in metadata["sustainability_guardrail"]
            ):
                raise AssertionError("firstcolo untyped design scope must remain exact")

    def _base_paths(self) -> list[Path]:
        definition_path = ROOT / "sources" / BASE_DEFINITION
        self.assertEqual(
            hashlib.sha256(definition_path.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            paths.append(path)
        self.assertEqual(len(paths), 113)
        self.assertEqual(len(paths), len(set(paths)))
        return paths

    def _import(self, connection: Any, path: Path) -> Any:
        document = json.loads(path.read_text(encoding="utf-8"))
        retrieved = {row["retrieved_at"] for row in document["evidence"]}
        self.assertEqual(len(retrieved), 1)
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            path,
            retrieved_at=next(iter(retrieved)),
        )

    def _semantic_state(self, connection: Any) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        queries = (
            "SELECT kind, stable_key, created_at FROM entities",
            "SELECT kind, title, source_url, publisher, source_family, license, "
            "attribution, published_at, retrieved_at, excerpt, content_hash, "
            "metadata_json FROM evidence",
            "SELECT projects_entity.stable_key, target_entity.stable_key "
            "FROM projects JOIN entities AS projects_entity "
            "ON projects_entity.id = projects.entity_id "
            "JOIN entities AS target_entity "
            "ON target_entity.id = projects.target_entity_id",
            "SELECT entities.stable_key, name, latitude, longitude, geometry_json, "
            "tags_json, evidence.content_hash, as_of_date, valid_to_date, "
            "recorded_at, superseded_at, method, confidence "
            "FROM entity_snapshots JOIN entities "
            "ON entities.id = entity_snapshots.entity_id JOIN evidence "
            "ON evidence.id = entity_snapshots.evidence_id",
            "SELECT entities.stable_key, status, evidence.content_hash, as_of_date, "
            "valid_to_date, recorded_at, superseded_at, method, confidence, notes "
            "FROM lifecycle_observations JOIN entities "
            "ON entities.id = lifecycle_observations.entity_id JOIN evidence "
            "ON evidence.id = lifecycle_observations.evidence_id",
            "SELECT entities.stable_key, operating_model, evidence.content_hash, "
            "as_of_date, valid_to_date, recorded_at, superseded_at, method, "
            "confidence, notes FROM operating_model_observations JOIN entities "
            "ON entities.id = operating_model_observations.entity_id JOIN evidence "
            "ON evidence.id = operating_model_observations.evidence_id",
            "SELECT entities.stable_key, workload, evidence.content_hash, as_of_date, "
            "valid_to_date, recorded_at, superseded_at, method, confidence, notes "
            "FROM workload_observations JOIN entities "
            "ON entities.id = workload_observations.entity_id JOIN evidence "
            "ON evidence.id = workload_observations.evidence_id",
            "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
            "method, confidence, evidence.content_hash, as_of_date, target_date, "
            "valid_to_date, recorded_at, superseded_at, notes "
            "FROM capacity_estimates JOIN entities "
            "ON entities.id = capacity_estimates.entity_id JOIN evidence "
            "ON evidence.id = capacity_estimates.evidence_id",
        )
        return tuple(
            tuple(
                sorted(
                    (tuple(row) for row in connection.execute(query)),
                    key=lambda row: json.dumps(row, ensure_ascii=False),
                )
            )
            for query in queries
        )

    def _counts(self, connection: Any) -> dict[str, int]:
        return {
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

    def _scenario(
        self,
        *,
        base_first: bool,
        new_order: tuple[str, ...],
    ) -> tuple[tuple[tuple[tuple[Any, ...], ...], ...], dict[str, int]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                base_paths = self._base_paths()
                new_paths = [ROOT / "sources" / name for name in new_order]
                with patch.object(
                    socket, "socket", side_effect=AssertionError("network used")
                ), patch.object(
                    socket,
                    "create_connection",
                    side_effect=AssertionError("network used"),
                ):
                    if base_first:
                        for path in base_paths:
                            self._import(connection, path)
                    for path in new_paths:
                        self._import(connection, path)
                    before_repeat = self._semantic_state(connection)
                    for path in new_paths:
                        result = self._import(connection, path)
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._semantic_state(connection), before_repeat)
                    if not base_first:
                        for path in base_paths:
                            self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection), self._counts(connection)
            finally:
                connection.close()

    def _base_state(self) -> tuple[
        tuple[tuple[tuple[Any, ...], ...], ...], dict[str, int]
    ]:
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
                    for path in self._base_paths():
                        self._import(connection, path)
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection), self._counts(connection)
            finally:
                connection.close()

    def test_exact_sources_capture_lineage_and_narrow_semantics(self) -> None:
        base_text = (ROOT / "sources" / BASE_DEFINITION).read_text(encoding="utf-8")
        for name, expected in SOURCES.items():
            source_path = ROOT / "sources" / name
            self.assertEqual(
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
                expected["sha256"],
            )
            self.assertNotIn(name, base_text)
            self.assertNotIn(expected["campus_key"], base_text)
            self.assertNotIn(expected["project_key"], base_text)
            self._assert_document(name, self._load(name))

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    with patch.object(
                        socket, "socket", side_effect=AssertionError("network used")
                    ), patch.object(
                        socket,
                        "create_connection",
                        side_effect=AssertionError("network used"),
                    ):
                        result = self._import(connection, source_path)
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

    def test_v20_forward_reverse_idempotence_and_exact_deltas(self) -> None:
        base_state, base_counts = self._base_state()
        names = tuple(SOURCES)
        forward_state, forward_counts = self._scenario(
            base_first=True,
            new_order=names,
        )
        reverse_state, reverse_counts = self._scenario(
            base_first=False,
            new_order=tuple(reversed(names)),
        )
        self.assertEqual(forward_state, reverse_state)
        self.assertEqual(forward_counts, reverse_counts)

        expected_deltas = {
            "entities": 8,
            "campuses": 4,
            "projects": 4,
            "evidence": 4,
            "entity_snapshots": 8,
            "lifecycle_observations": 4,
            "operating_model_observations": 0,
            "workload_observations": 1,
            "capacity_estimates": 2,
        }
        self.assertEqual(
            {
                table: forward_counts[table] - base_counts[table]
                for table in expected_deltas
            },
            expected_deltas,
        )

        base_entities = {row[1] for row in base_state[0]}
        combined_entities = {row[1] for row in forward_state[0]}
        new_entity_keys = {
            key
            for expected in SOURCES.values()
            for key in (expected["campus_key"], expected["project_key"])
        }
        self.assertTrue(base_entities.isdisjoint(new_entity_keys))
        self.assertEqual(combined_entities - base_entities, new_entity_keys)

        base_evidence_hashes = {row[10] for row in base_state[1]}
        combined_evidence_hashes = {row[10] for row in forward_state[1]}
        new_evidence_hashes = {
            capture["content_hash"] for capture in CAPTURES.values()
        }
        self.assertTrue(base_evidence_hashes.isdisjoint(new_evidence_hashes))
        self.assertEqual(
            combined_evidence_hashes - base_evidence_hashes,
            new_evidence_hashes,
        )

        new_snapshots = [
            row for row in forward_state[3] if row[0] in new_entity_keys
        ]
        self.assertEqual(len(new_snapshots), 8)
        for snapshot in new_snapshots:
            self.assertIsNone(snapshot[2])
            self.assertIsNone(snapshot[3])
            self.assertIsNone(snapshot[4])
            tags = json.loads(snapshot[5])
            self.assertFalse(any(key.startswith("role:") for key in tags))

        new_lifecycle = [
            row for row in forward_state[4] if row[0] in new_entity_keys
        ]
        self.assertEqual(len(new_lifecycle), 4)
        self.assertEqual(
            {(row[0], row[1], row[3], row[7]) for row in new_lifecycle},
            {
                (
                    expected["project_key"],
                    expected["lifecycle"],
                    expected["as_of_date"],
                    expected["lifecycle_method"],
                )
                for expected in SOURCES.values()
            },
        )

        new_workloads = [
            row for row in forward_state[6] if row[0] in new_entity_keys
        ]
        self.assertEqual(
            [(row[0], row[1], row[3], row[7]) for row in new_workloads],
            [
                (
                    SOURCES[BITDEER_SOURCE]["project_key"],
                    "crypto_mining",
                    "2026-06-02",
                    "company_disclosure",
                )
            ],
        )

        new_capacities = [
            row for row in forward_state[7] if row[0] in new_entity_keys
        ]
        self.assertEqual(
            {
                (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[10])
                for row in new_capacities
            },
            {
                (
                    SOURCES[BITDEER_SOURCE]["campus_key"],
                    "generation_nameplate_mw",
                    "planned",
                    "MW",
                    101.0,
                    101.0,
                    101.0,
                    "2026-06-02",
                ),
                (
                    SOURCES[NXERA_SOURCE]["campus_key"],
                    "grid_connection_mw",
                    "contracted",
                    "MW",
                    280.0,
                    280.0,
                    280.0,
                    "2026-04-16",
                ),
            },
        )

    def test_semantic_mutations_fail_guardrails(self) -> None:
        documents = {name: self._load(name) for name in SOURCES}
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(documents[BITDEER_SOURCE])
        mutated["capacities"][0].update(
            {"entity": "project", "metric": "critical_it_mw", "low": 100,
             "base": 100, "high": 100}
        )
        mutations.append((BITDEER_SOURCE, mutated))

        mutated = copy.deepcopy(documents[BITDEER_SOURCE])
        extra = copy.deepcopy(mutated["workloads"][0])
        extra["value"] = "ai_specialized_unspecified"
        mutated["workloads"].append(extra)
        mutations.append((BITDEER_SOURCE, mutated))

        mutated = copy.deepcopy(documents[PUREDC_SOURCE])
        mutated["capacities"] = [
            {
                "forbidden": "70 MW inferred by subtracting B1 from campus total"
            }
        ]
        mutations.append((PUREDC_SOURCE, mutated))

        mutated = copy.deepcopy(documents[PUREDC_SOURCE])
        mutated["lifecycle"][0]["value"] = "shell"
        mutations.append((PUREDC_SOURCE, mutated))

        mutated = copy.deepcopy(documents[NXERA_SOURCE])
        mutated["lifecycle"][0]["value"] = "operational"
        mutations.append((NXERA_SOURCE, mutated))

        mutated = copy.deepcopy(documents[NXERA_SOURCE])
        mutated["workloads"] = [{"forbidden": "AI-ready is capability only"}]
        mutations.append((NXERA_SOURCE, mutated))

        mutated = copy.deepcopy(documents[NXERA_SOURCE])
        mutated["capacities"].append(
            {"forbidden": "PUE inequality cannot become a point estimate"}
        )
        mutations.append((NXERA_SOURCE, mutated))

        mutated = copy.deepcopy(documents[FIRSTCOLO_SOURCE])
        mutated["capacities"] = [
            {"forbidden": "24 MW total capacity metric is untyped"}
        ]
        mutations.append((FIRSTCOLO_SOURCE, mutated))

        mutated = copy.deepcopy(documents[FIRSTCOLO_SOURCE])
        mutated["workloads"] = [{"forbidden": "AI and HPC are design capability"}]
        mutations.append((FIRSTCOLO_SOURCE, mutated))

        mutated = copy.deepcopy(documents[FIRSTCOLO_SOURCE])
        mutated["operating_models"] = [{"forbidden": "no operating model"}]
        mutations.append((FIRSTCOLO_SOURCE, mutated))

        mutated = copy.deepcopy(documents[BITDEER_SOURCE])
        mutated["campus"]["roles"] = {"owner": ["Bitdeer"]}
        mutations.append((BITDEER_SOURCE, mutated))

        mutated = copy.deepcopy(documents[PUREDC_SOURCE])
        mutated["project"]["coordinates"] = {
            "latitude": 51.57,
            "longitude": -0.22,
        }
        mutations.append((PUREDC_SOURCE, mutated))

        mutated = copy.deepcopy(documents[NXERA_SOURCE])
        mutated["project"]["geometry"] = {
            "type": "Point",
            "coordinates": [103.62, 1.43],
        }
        mutations.append((NXERA_SOURCE, mutated))

        mutated = copy.deepcopy(documents[FIRSTCOLO_SOURCE])
        mutated["evidence"][0]["kind"] = "satellite_imagery"
        mutations.append((FIRSTCOLO_SOURCE, mutated))

        for name, document in mutations:
            with self.subTest(source=name):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
