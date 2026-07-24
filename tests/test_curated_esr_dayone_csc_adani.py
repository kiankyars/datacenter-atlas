from __future__ import annotations

import copy
import csv
import hashlib
import json
import socket
import stat
import tempfile
import unittest
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-19-v32.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-19-open-seed-v32"
BASE_DEFINITION_SHA256 = (
    "97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150"
)
BASE_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)

MINOH_SOURCE = "curated-official-2026-07-19-esr-colt-minoh-osaka-phase-1.json"
LAHTI_SOURCE = "curated-official-2026-07-19-dayone-kiverio-lahti.json"
LUMI_SOURCE = "curated-official-2026-07-19-csc-lumi-ai-kajaani.json"
ADANI_SOURCE = "curated-official-2026-07-19-adani-info-valley-bhubaneswar.json"
SOURCE_ORDER = (MINOH_SOURCE, LAHTI_SOURCE, LUMI_SOURCE, ADANI_SOURCE)

MINOH_EVIDENCE = (
    "esr-colt-dcs-minoh-osaka-joint-venture-release-2025-10-16-"
    "captured-2026-07-19"
)
LAHTI_EVIDENCE = (
    "srv-dayone-kiverio-lahti-construction-launch-2026-04-07-"
    "captured-2026-07-19"
)
LUMI_EVIDENCE = (
    "csc-lumi-ai-data-center-construction-full-swing-2026-03-17-"
    "captured-2026-07-19"
)
ADANI_EVIDENCE = (
    "adani-connect-info-valley-bhubaneswar-groundbreaking-may-2026-"
    "captured-2026-07-19"
)

SOURCES: dict[str, dict[str, Any]] = {
    MINOH_SOURCE: {
        "sha256": "effde4481c0a5859cfbfdde3fdce575772c0c9d2d32f3a9c5fd8610b71f3d8f7",
        "evidence_key": MINOH_EVIDENCE,
        "publisher": "ESR",
        "source_family": "esr_newsroom",
        "published_at": "2025-10-16",
        "retrieved_at": "2026-07-19T23:53:31Z",
        "country": "Japan",
        "address": "Minoh City, Osaka, Japan",
        "campus_key": "curated:esr-colt-dcs-minoh-osaka-data-centre-site",
        "campus_name": "ESR–Colt DCS Minoh Data Centre Site",
        "project_key": (
            "curated:esr-colt-dcs-minoh-osaka-data-centre-site:phase-1"
        ),
        "project_name": "ESR–Colt DCS Minoh Phase 1",
        "as_of_date": "2025-10-16",
        "status": "site_preparation",
        "lifecycle_method": "authoritative_physical_status_update",
        "confidence": 0.99,
        "campus_roles": {
            "owner": ["ESR–Colt DCS joint venture"],
            "developer": ["ESR–Colt DCS joint venture"],
        },
        "project_roles": {
            "developer": ["ESR–Colt DCS joint venture"],
            "operator": ["Colt Data Centre Services"],
        },
    },
    LAHTI_SOURCE: {
        "sha256": "5367f4c31b48423a418861e3a8e06611c56213578d92ee6d632a5ada191206a4",
        "evidence_key": LAHTI_EVIDENCE,
        "publisher": "SRV Group Plc",
        "source_family": "srv_cision_press_releases",
        "published_at": "2026-04-07T09:00:00Z",
        "retrieved_at": "2026-07-19T23:53:30Z",
        "country": "Finland",
        "address": "Ilmarisentie 3, Kiveriö, Lahti, Finland",
        "campus_key": "curated:dayone-kiverio-lahti-unnamed-data-center-campus",
        "campus_name": "DayOne Kiveriö Unnamed Data Center Campus",
        "project_key": (
            "curated:dayone-kiverio-lahti-unnamed-data-center-campus:"
            "unnamed-construction-project"
        ),
        "project_name": "DayOne Kiveriö Unnamed Data Center Construction Project",
        "as_of_date": "2026-04-07",
        "status": "under_construction",
        "lifecycle_method": "authoritative_construction_start",
        "confidence": 0.99,
        "campus_roles": {},
        "project_roles": {},
    },
    LUMI_SOURCE: {
        "sha256": "36ec0668806dff0891a2ad8647938b48daa6c32ec95137fcd0e3899dbc596c12",
        "evidence_key": LUMI_EVIDENCE,
        "publisher": "CSC – IT Center for Science Ltd.",
        "source_family": "csc_news_and_blog",
        "published_at": "2026-03-17T13:39:40+00:00",
        "retrieved_at": "2026-07-19T23:53:30Z",
        "country": "Finland",
        "address": "Renforsin Ranta, Kajaani, Finland",
        "campus_key": "curated:csc-lumi-ai-data-center-renforsin-ranta-kajaani",
        "campus_name": "CSC LUMI-AI Data Center",
        "project_key": (
            "curated:csc-lumi-ai-data-center-renforsin-ranta-kajaani:"
            "current-build"
        ),
        "project_name": "CSC LUMI-AI Data Center Current Build",
        "as_of_date": "2026-03-17",
        "status": "under_construction",
        "lifecycle_method": "authoritative_physical_status_update",
        "confidence": 0.99,
        "campus_roles": {},
        "project_roles": {"contractor": ["SRV"]},
    },
    ADANI_SOURCE: {
        "sha256": "3d64e7a63c433bf9f43c4c6efe1425766543ad05b77459d30b4aab988db156f9",
        "evidence_key": ADANI_EVIDENCE,
        "publisher": "Adani Group",
        "source_family": "adani_connect_magazine",
        "published_at": None,
        "retrieved_at": "2026-07-19T23:53:30Z",
        "country": "India",
        "address": "Info Valley, Bhubaneswar, Odisha, India",
        "campus_key": "curated:adani-info-valley-bhubaneswar-data-centre-campus",
        "campus_name": "Adani Info Valley Data Centre Campus",
        "project_key": (
            "curated:adani-info-valley-bhubaneswar-data-centre-campus:"
            "groundbreaking-project"
        ),
        "project_name": "Adani Info Valley Data Centre Groundbreaking Project",
        "as_of_date": "2026-05-01",
        "status": "under_construction",
        "lifecycle_method": "authoritative_construction_start",
        "confidence": 0.95,
        "campus_roles": {},
        "project_roles": {},
    },
}

CAPTURES: dict[str, dict[str, Any]] = {
    MINOH_EVIDENCE: {
        "source": MINOH_SOURCE,
        "body_bytes": 291870,
        "content_hash": "85960a34edbbea3d2c96d2c89c672ec78b445744512d1fc2e939f154acfcca66",
        "headers_bytes": 761,
        "headers_hash": "8f6268fe00078b033d8f63aa6feb1647a5743c5311c9bfef4227bea154d5ff5b",
        "download_bytes": 51931,
        "response_date": "2026-07-19T23:53:31Z",
        "last_modified": "2026-07-17T05:52:32Z",
        "content_type": "text/html",
        "content_encoding": "gzip",
        "content_length": None,
        "requested_url": (
            "https://www.esr.com/news/esr-and-colt-dcs-announce-joint-"
            "venture-on-new-osaka-data-centre-development/"
        ),
        "effective_url": (
            "https://www.esr.com/news/esr-and-colt-dcs-announce-joint-"
            "venture-on-new-osaka-data-centre-development/"
        ),
        "canonical_url": (
            "https://www.esr.com/news/esr-and-colt-dcs-announce-joint-"
            "venture-on-new-osaka-data-centre-development/"
        ),
    },
    LAHTI_EVIDENCE: {
        "source": LAHTI_SOURCE,
        "body_bytes": 27625,
        "content_hash": "6c0507925789191c036609350640bf3af98aac27425a677ed65fe83825606810",
        "headers_bytes": 752,
        "headers_hash": "fe1860f0356e976254c938bbbf0acf1c443045dbe2999a861474152b47348cbe",
        "download_bytes": 7026,
        "response_date": "2026-07-19T23:53:30Z",
        "last_modified": "2026-07-19T23:53:30Z",
        "content_type": "text/html; charset=utf-8",
        "content_encoding": "gzip",
        "content_length": None,
        "requested_url": (
            "https://news.cision.com/srv-yhtiot-oyj/r/dayone-data-center-"
            "construction-to-start-in-lahti---srv-strengthens-its-position-in-"
            "the-growing-mark%2Cc4331404"
        ),
        "effective_url": (
            "https://news.cision.com/srv-yhtiot-oyj/r/dayone-data-center-"
            "construction-to-start-in-lahti---srv-strengthens-its-position-in-"
            "the-growing-mark%2Cc4331404"
        ),
        "canonical_url": (
            "https://news.cision.com/srv-yhtiot-oyj/r/dayone-data-center-"
            "construction-to-start-in-lahti---srv-strengthens-its-position-in-"
            "the-growing-mark,c4331404"
        ),
    },
    LUMI_EVIDENCE: {
        "source": LUMI_SOURCE,
        "body_bytes": 113082,
        "content_hash": "a3a5ec6874edde9f171d48731c8db083ef8913fb059b92d262aca0d51d6b9fbf",
        "headers_bytes": 847,
        "headers_hash": "cbe50521e495198bfc207af91e0187f6ce473b645afe171e2ca4ef974001d7b4",
        "download_bytes": 24514,
        "response_date": "2026-07-19T23:53:30Z",
        "last_modified": None,
        "content_type": "text/html; charset=UTF-8",
        "content_encoding": "gzip",
        "content_length": None,
        "requested_url": (
            "https://csc.fi/en/blog/construction-of-the-lumi-ai-data-center-"
            "in-full-swing/"
        ),
        "effective_url": (
            "https://csc.fi/en/blog/construction-of-the-lumi-ai-data-center-"
            "in-full-swing/"
        ),
        "canonical_url": (
            "https://csc.fi/en/blog/construction-of-the-lumi-ai-data-center-"
            "in-full-swing/"
        ),
    },
    ADANI_EVIDENCE: {
        "source": ADANI_SOURCE,
        "body_bytes": 490838,
        "content_hash": "486723459bb190385b061a517c7a021aa351c5fd770310b1374db4f5b740c8d4",
        "headers_bytes": 513,
        "headers_hash": "dfec489109070c5e6b5e340edd04580e292b4158e75040771bd4f25880e34cae",
        "download_bytes": 490838,
        "response_date": "2026-07-19T23:53:30Z",
        "last_modified": "2026-05-06T13:13:31Z",
        "content_type": "text/html",
        "content_encoding": None,
        "content_length": 490838,
        "requested_url": "https://connect.adani.com/2026/may2026/pers/",
        "effective_url": "https://connect.adani.com/2026/may2026/pers/",
        "canonical_url": "https://connect.adani.com/2026/may2026/pers/",
    },
}

SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "administrative_assignments",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class EsrDayOneCscAdaniTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _assert_capture(self, evidence: dict[str, Any]) -> None:
        capture = CAPTURES[evidence["key"]]
        expected = SOURCES[capture["source"]]
        metadata = evidence["metadata"]

        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(evidence["publisher"], expected["publisher"])
        self.assertEqual(evidence["source_family"], expected["source_family"])
        self.assertEqual(evidence["published_at"], expected["published_at"])
        self.assertEqual(evidence["retrieved_at"], expected["retrieved_at"])
        self.assertEqual(evidence["content_hash"], capture["content_hash"])
        self.assertEqual(evidence["source_url"], capture["canonical_url"])
        self.assertEqual(evidence["license"], "all-rights-reserved")

        self.assertEqual(metadata["content_hash_verification"], "fetched_bytes_sha256")
        self.assertIn(str(capture["body_bytes"]), metadata["content_hash_scope"])
        self.assertIn(str(capture["headers_bytes"]), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], capture["headers_hash"])
        self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], capture["content_type"])
        self.assertEqual(
            metadata["content_encoding_as_received"], capture["content_encoding"]
        )
        self.assertIsNone(metadata["http_transfer_encoding_as_received"])
        self.assertEqual(
            metadata["http_content_length_bytes_as_received"],
            capture["content_length"],
        )
        self.assertEqual(
            metadata["curl_size_download_bytes_as_received"],
            capture["download_bytes"],
        )
        self.assertEqual(metadata["response_http_date"], capture["response_date"])
        self.assertEqual(metadata["http_last_modified_at"], capture["last_modified"])
        self.assertEqual(metadata["requested_url"], capture["requested_url"])
        self.assertEqual(metadata["effective_url"], capture["effective_url"])
        self.assertEqual(metadata["canonical_url"], capture["canonical_url"])
        self.assertEqual(metadata["response_header_blocks"], 1)
        self.assertEqual(metadata["redirect_count"], 0)
        self.assertIn("curl --fail --location --compressed", metadata["retrieval_method"])
        self.assertIn("HTTP Date", metadata["retrieved_at_semantics"])
        self.assertIn("not redistributed", metadata["rights_scope"])

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCES[name]
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
        evidence = document["evidence"][0]
        self.assertEqual(evidence["key"], expected["evidence_key"])
        self._assert_capture(evidence)

        for entity_name, roles in (
            ("campus", expected["campus_roles"]),
            ("project", expected["project_roles"]),
        ):
            entity = document[entity_name]
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], roles)
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], expected["evidence_key"])
            self.assertEqual(entity["as_of_date"], expected["as_of_date"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], expected["confidence"])
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["campus"]["name"], expected["campus_name"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["project"]["name"], expected["project_name"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": expected["status"],
                    "evidence_key": expected["evidence_key"],
                    "as_of_date": expected["as_of_date"],
                    "method": expected["lifecycle_method"],
                    "confidence": expected["confidence"],
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])

        metadata = evidence["metadata"]
        self.assertIn("computer vision", metadata["imagery_guardrail"])
        self.assertIn("unique-site claim", metadata["locality_guardrail"])
        if name == MINOH_SOURCE:
            self.assertEqual(
                document["capacities"],
                [
                    {
                        "entity": "campus",
                        "metric": "gross_facility_mw",
                        "stage": "planned",
                        "unit": "MW",
                        "low": 130,
                        "base": 130,
                        "high": 130,
                        "method": "reported",
                        "confidence": 0.99,
                        "evidence_key": MINOH_EVIDENCE,
                        "as_of_date": "2025-10-16",
                        "target_date": None,
                        "notes": (
                            "Planned 130 MW Facility Load for the full Minoh site; "
                            "treated as gross facility demand, not IT, grid, generation, "
                            "current load, or energy. The Phase 1 row is within and "
                            "non-additive to this site total."
                        ),
                    },
                    {
                        "entity": "project",
                        "metric": "gross_facility_mw",
                        "stage": "planned",
                        "unit": "MW",
                        "low": 65,
                        "base": 65,
                        "high": 65,
                        "method": "reported",
                        "confidence": 0.99,
                        "evidence_key": MINOH_EVIDENCE,
                        "as_of_date": "2025-10-16",
                        "target_date": None,
                        "notes": (
                            "Planned 65 MW Facility Load for Phase 1; treated as gross "
                            "facility demand, not IT, grid, generation, current load, or "
                            "energy. It is contained within and non-additive to the "
                            "130 MW site row."
                        ),
                    },
                ],
            )
            self.assertEqual(metadata["site_facility_load_mw_as_reported"], 130)
            self.assertEqual(metadata["phase_1_facility_load_mw_as_reported"], 65)
            self.assertEqual(
                metadata["facility_load_source_note_as_reported"], "Facility Load"
            )
            self.assertIn("not additive", metadata["capacity_scope"])
            self.assertIn("Neither figure is critical IT load", metadata["capacity_guardrail"])
            self.assertEqual(metadata["project_type_as_reported"], "hyperscale data centre site")
            self.assertIn(
                "do not establish a normalized operating model",
                metadata["classification_guardrail"],
            )
            self.assertIn("scheduled to begin in 2027", metadata["building_construction_forecast_as_reported"])
            self.assertIn("late 2029", metadata["ready_for_service_forecast_as_reported"])
        else:
            self.assertEqual(document["capacities"], [])

        if name == LAHTI_SOURCE:
            self.assertIn("no formal facility", metadata["identity_guardrail"])
            self.assertIn("one unnamed campus", metadata["identity_guardrail"])
            self.assertEqual(metadata["operation_forecast_as_reported"], "during 2027")
            self.assertIn("No standardized", metadata["role_guardrail"])
            self.assertIn("no normalized type", metadata["classification_guardrail"])
            self.assertIn("no power", metadata["energy_guardrail"])
        elif name == LUMI_SOURCE:
            self.assertEqual(
                metadata["identity_aliases_as_reported"],
                ["LUMI-AI data center", "LUMI AI Factory data center"],
            )
            self.assertIn("same new data-center", metadata["alias_scope_guardrail"])
            self.assertEqual(
                metadata["planned_hosts_as_reported"],
                ["EuroHPC LUMI-AI supercomputer", "LUMI-IQ quantum computer"],
            )
            self.assertIn("schema cannot stage", metadata["planned_hosting_guardrail"])
            self.assertEqual(metadata["main_contractor_as_reported"], "SRV")
            self.assertIn("not merged", metadata["collision_guardrail"])
            self.assertIn("Roihu", metadata["collision_guardrail"])
            self.assertIn("unique-site claim", metadata["collision_guardrail"])
        elif name == ADANI_SOURCE:
            self.assertEqual(metadata["status_date_precision"], "month")
            self.assertIn("2026-05-01", metadata["status_as_of_normalization"])
            self.assertIn("not an asserted", metadata["status_as_of_normalization"])
            self.assertEqual(metadata["data_center_investment_inr_crore_as_reported"], 800)
            self.assertEqual(
                metadata[
                    "three_project_combined_investment_inr_crore_minimum_as_reported"
                ],
                33000,
            )
            self.assertIn("three-project aggregate", metadata["investment_guardrail"])
            self.assertIn("AdaniConneX", metadata["role_guardrail"])
            self.assertIn("no normalized type", metadata["classification_guardrail"])
            self.assertIn("No critical IT load", metadata["metric_guardrail"])

    def _base_paths(self) -> tuple[Path, ...]:
        self.assertEqual(
            hashlib.sha256(BASE_DEFINITION.read_bytes()).hexdigest(),
            BASE_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((BASE_RELEASE / "manifest.json").read_bytes()).hexdigest(),
            BASE_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(BASE_DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(BASE_RELEASE.stat().st_mode), 0o555)
        definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        paths: list[Path] = []
        for record in definition["curated_inputs"]:
            path = ROOT / record["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"])
            paths.append(path)
        self.assertEqual(len(paths), 157)
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertTrue({ROOT / "sources" / name for name in SOURCE_ORDER}.isdisjoint(paths))
        return tuple(paths)

    def _retrieved_at(self, path: Path) -> str:
        document = json.loads(path.read_text(encoding="utf-8"))
        timestamps = {row["retrieved_at"] for row in document["evidence"]}
        self.assertEqual(len(timestamps), 1)
        return next(iter(timestamps))

    def _import(self, connection: Any, path: Path) -> Any:
        return CuratedOfficialSourceAdapter().import_file(
            connection,
            path,
            retrieved_at=self._retrieved_at(path),
        )

    def _semantic_state(
        self, connection: Any
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in SEMANTIC_TABLES
        }

    def _offline(self) -> tuple[Any, ...]:
        error = AssertionError("network used")
        return (
            patch.object(socket, "socket", side_effect=error),
            patch.object(socket, "create_connection", side_effect=error),
            patch.object(socket, "getaddrinfo", side_effect=error),
            patch.object(socket, "gethostbyname", side_effect=error),
            patch.object(socket, "gethostbyname_ex", side_effect=error),
        )

    def _build(
        self,
        base_paths: tuple[Path, ...],
        source_order: Iterable[str],
        *,
        base_first: bool,
    ) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], dict[str, tuple[int, int]]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                results: dict[str, tuple[int, int]] = {}
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    if base_first:
                        for path in base_paths:
                            self._import(connection, path)
                    for name in source_order:
                        result = self._import(connection, ROOT / "sources" / name)
                        results[name] = (
                            result.entities_created,
                            result.evidence_created,
                        )
                    if not base_first:
                        for path in base_paths:
                            self._import(connection, path)
                    frozen = self._semantic_state(connection)
                    for name in SOURCE_ORDER:
                        result = self._import(connection, ROOT / "sources" / name)
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._semantic_state(connection), frozen)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()
                self.assertEqual(validate_database(connection), [])
                return frozen, results
            finally:
                connection.close()

    def _baseline_state(
        self, base_paths: tuple[Path, ...]
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    for path in base_paths:
                        self._import(connection, path)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()
                self.assertEqual(validate_database(connection), [])
                return self._semantic_state(connection)
            finally:
                connection.close()

    def test_capture_closure_modes_and_all_source_v32_collision_absence(self) -> None:
        base_paths = self._base_paths()
        base_text = BASE_DEFINITION.read_text(encoding="utf-8")
        with (BASE_RELEASE / "entities.csv").open(encoding="utf-8", newline="") as stream:
            base_entity_keys = {row["stable_key"] for row in csv.DictReader(stream)}
        with (BASE_RELEASE / "evidence.csv").open(encoding="utf-8", newline="") as stream:
            base_content_hashes = {row["content_hash"] for row in csv.DictReader(stream)}

        other_entity_keys: set[str] = set()
        other_evidence_keys: set[str] = set()
        other_content_hashes: set[str] = set()
        new_paths = {ROOT / "sources" / name for name in SOURCE_ORDER}
        for path in sorted((ROOT / "sources").glob("curated-official-*.json")):
            if path in new_paths:
                continue
            document = json.loads(path.read_text(encoding="utf-8"))
            other_entity_keys.add(document["campus"]["stable_key"])
            if document["project"] is not None:
                other_entity_keys.add(document["project"]["stable_key"])
            for evidence in document["evidence"]:
                other_evidence_keys.add(evidence["key"])
                other_content_hashes.add(evidence["content_hash"])

        new_entity_keys: set[str] = set()
        new_evidence_keys: set[str] = set()
        new_content_hashes: set[str] = set()
        for name, expected in SOURCES.items():
            path = ROOT / "sources" / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), expected["sha256"]
            )
            self.assertNotIn(name, base_text)
            self.assertNotIn(expected["campus_key"], base_text)
            self.assertNotIn(expected["project_key"], base_text)
            document = self._load(name)
            self._assert_document(name, document)
            new_entity_keys.update((expected["campus_key"], expected["project_key"]))
            new_evidence_keys.add(expected["evidence_key"])
            new_content_hashes.add(document["evidence"][0]["content_hash"])

            with self.subTest(source=name), tempfile.TemporaryDirectory() as temporary:
                connection, _ = initialize(Path(temporary) / "atlas.sqlite")
                try:
                    patches = self._offline()
                    for network_patch in patches:
                        network_patch.start()
                    try:
                        result = self._import(connection, path)
                    finally:
                        for network_patch in reversed(patches):
                            network_patch.stop()
                    self.assertEqual(result.entities_created, 2)
                    self.assertEqual(result.evidence_created, 1)
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

        self.assertEqual(len(new_entity_keys), 8)
        self.assertEqual(len(new_evidence_keys), 4)
        self.assertEqual(len(new_content_hashes), 4)
        self.assertTrue(new_entity_keys.isdisjoint(base_entity_keys))
        self.assertTrue(new_entity_keys.isdisjoint(other_entity_keys))
        self.assertTrue(new_evidence_keys.isdisjoint(other_evidence_keys))
        self.assertTrue(new_content_hashes.isdisjoint(base_content_hashes))
        self.assertTrue(new_content_hashes.isdisjoint(other_content_hashes))
        self.assertEqual(
            new_content_hashes,
            {capture["content_hash"] for capture in CAPTURES.values()},
        )
        for forbidden in (
            "Minoh",
            "Kiveriö",
            "LUMI-AI",
            "Info Valley",
            "Bhubaneswar",
        ):
            self.assertNotIn(forbidden, base_text)
        self.assertEqual(len(base_paths), 157)

    def test_forward_reverse_base_order_idempotence_and_exact_deltas(self) -> None:
        base_paths = self._base_paths()
        baseline_state = self._baseline_state(base_paths)
        scenarios = [
            self._build(base_paths, SOURCE_ORDER, base_first=True),
            self._build(base_paths, reversed(SOURCE_ORDER), base_first=True),
            self._build(base_paths, SOURCE_ORDER, base_first=False),
            self._build(base_paths, reversed(SOURCE_ORDER), base_first=False),
        ]
        expected_results = {name: (2, 1) for name in SOURCE_ORDER}
        reference_state = scenarios[0][0]
        for state, results in scenarios:
            self.assertEqual(state, reference_state)
            self.assertEqual(results, expected_results)

        baseline_counts = {table: len(rows) for table, rows in baseline_state.items()}
        final_counts = {table: len(rows) for table, rows in reference_state.items()}
        self.assertEqual(
            {
                table: final_counts[table] - baseline_counts[table]
                for table in SEMANTIC_TABLES
            },
            {
                "evidence": 4,
                "entities": 8,
                "campuses": 4,
                "facilities": 0,
                "buildings": 0,
                "projects": 4,
                "administrative_assignments": 0,
                "entity_snapshots": 8,
                "lifecycle_observations": 4,
                "operating_model_observations": 0,
                "workload_observations": 0,
                "capacity_estimates": 2,
            },
        )

    def test_combined_import_has_only_exact_narrow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                patches = self._offline()
                for network_patch in patches:
                    network_patch.start()
                try:
                    for name in SOURCE_ORDER:
                        self._import(connection, ROOT / "sources" / name)
                finally:
                    for network_patch in reversed(patches):
                        network_patch.stop()

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
                            "SELECT entities.stable_key, status, as_of_date, method "
                            "FROM lifecycle_observations JOIN entities "
                            "ON entities.id = lifecycle_observations.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    sorted(
                        (
                            expected["project_key"],
                            expected["status"],
                            expected["as_of_date"],
                            expected["lifecycle_method"],
                        )
                        for expected in SOURCES.values()
                    ),
                )
                self.assertEqual(
                    [
                        tuple(row)
                        for row in connection.execute(
                            "SELECT entities.stable_key, metric, stage, unit, low, "
                            "base, high, target_date, notes "
                            "FROM capacity_estimates JOIN entities "
                            "ON entities.id = capacity_estimates.entity_id "
                            "ORDER BY entities.stable_key"
                        )
                    ],
                    [
                        (
                            SOURCES[MINOH_SOURCE]["campus_key"],
                            "gross_facility_mw",
                            "planned",
                            "MW",
                            130.0,
                            130.0,
                            130.0,
                            None,
                            (
                                "Planned 130 MW Facility Load for the full Minoh site; "
                                "treated as gross facility demand, not IT, grid, "
                                "generation, current load, or energy. The Phase 1 row is "
                                "within and non-additive to this site total."
                            ),
                        ),
                        (
                            SOURCES[MINOH_SOURCE]["project_key"],
                            "gross_facility_mw",
                            "planned",
                            "MW",
                            65.0,
                            65.0,
                            65.0,
                            None,
                            (
                                "Planned 65 MW Facility Load for Phase 1; treated as "
                                "gross facility demand, not IT, grid, generation, current "
                                "load, or energy. It is contained within and non-additive "
                                "to the 130 MW site row."
                            ),
                        ),
                    ],
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
                    4,
                )
                self.assertEqual(
                    {
                        row[0]
                        for row in connection.execute(
                            "SELECT content_hash FROM evidence"
                        )
                    },
                    {capture["content_hash"] for capture in CAPTURES.values()},
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM entity_snapshots "
                        "WHERE latitude IS NOT NULL OR longitude IS NOT NULL "
                        "OR geometry_json IS NOT NULL"
                    ).fetchone()[0],
                    0,
                )
                role_tags = {
                    row["stable_key"]: {
                        key: value
                        for key, value in json.loads(row["tags_json"]).items()
                        if key.startswith("role:")
                    }
                    for row in connection.execute(
                        "SELECT entities.stable_key, entity_snapshots.tags_json "
                        "FROM entity_snapshots JOIN entities "
                        "ON entities.id = entity_snapshots.entity_id"
                    )
                }
                self.assertEqual(
                    role_tags,
                    {
                        SOURCES[MINOH_SOURCE]["campus_key"]: {
                            "role:developer": "ESR–Colt DCS joint venture",
                            "role:owner": "ESR–Colt DCS joint venture",
                        },
                        SOURCES[MINOH_SOURCE]["project_key"]: {
                            "role:developer": "ESR–Colt DCS joint venture",
                            "role:operator": "Colt Data Centre Services",
                        },
                        SOURCES[LAHTI_SOURCE]["campus_key"]: {},
                        SOURCES[LAHTI_SOURCE]["project_key"]: {},
                        SOURCES[LUMI_SOURCE]["campus_key"]: {},
                        SOURCES[LUMI_SOURCE]["project_key"]: {
                            "role:contractor": "SRV"
                        },
                        SOURCES[ADANI_SOURCE]["campus_key"]: {},
                        SOURCES[ADANI_SOURCE]["project_key"]: {},
                    },
                )
                for table in (
                    "operating_model_observations",
                    "workload_observations",
                ):
                    self.assertEqual(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                        0,
                        table,
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

    def test_semantic_leakage_and_mutations_fail_closed(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_ORDER}
        mutations: list[tuple[str, dict[str, Any]]] = []

        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["lifecycle"][0]["value"] = "under_construction"
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["capacities"][0]["metric"] = "critical_it_mw"
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["capacities"][1]["base"] = 195
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["operating_models"] = [{"forbidden": "hyperscale type is not a model"}]
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["workloads"] = [{"forbidden": "AI support is future design context"}]
        mutations.append((MINOH_SOURCE, mutated))
        mutated = copy.deepcopy(documents[MINOH_SOURCE])
        mutated["project"]["roles"]["operator"] = ["ESR"]
        mutations.append((MINOH_SOURCE, mutated))

        mutated = copy.deepcopy(documents[LAHTI_SOURCE])
        mutated["project"]["roles"] = {"operator": ["DayOne"]}
        mutations.append((LAHTI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LAHTI_SOURCE])
        mutated["project"]["roles"] = {"contractor": ["SRV"]}
        mutations.append((LAHTI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LAHTI_SOURCE])
        mutated["capacities"] = [{"forbidden": "large amount of data is not power"}]
        mutations.append((LAHTI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LAHTI_SOURCE])
        mutated["workloads"] = [{"forbidden": "large amount of data is not workload"}]
        mutations.append((LAHTI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LAHTI_SOURCE])
        mutated["project"]["coordinates"] = {"latitude": 60.98, "longitude": 25.66}
        mutations.append((LAHTI_SOURCE, mutated))

        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["workloads"] = [{"forbidden": "future systems are not current workload"}]
        mutations.append((LUMI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["operating_models"] = [{"forbidden": "future research use is not current model"}]
        mutations.append((LUMI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["project"]["roles"]["operator"] = ["CSC"]
        mutations.append((LUMI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["evidence"][0]["metadata"]["identity_aliases_as_reported"] = [
            "LUMI-AI data center"
        ]
        mutations.append((LUMI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["campus"]["stable_key"] = "curated:csc-lumi-data-center-2022"
        mutations.append((LUMI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[LUMI_SOURCE])
        mutated["capacities"] = [{"forbidden": "no metric reported"}]
        mutations.append((LUMI_SOURCE, mutated))

        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["evidence"][0]["published_at"] = "2026-05-06"
        mutations.append((ADANI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["lifecycle"][0]["as_of_date"] = "2026-05-06"
        mutations.append((ADANI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["project"]["roles"] = {"operator": ["AdaniConneX"]}
        mutations.append((ADANI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["workloads"] = [{"forbidden": "future AI enablement is not workload"}]
        mutations.append((ADANI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["capacities"] = [{"forbidden": "investment is not power"}]
        mutations.append((ADANI_SOURCE, mutated))
        mutated = copy.deepcopy(documents[ADANI_SOURCE])
        mutated["campus"]["coordinates"] = {"latitude": 20.2, "longitude": 85.8}
        mutations.append((ADANI_SOURCE, mutated))

        for name in SOURCE_ORDER:
            mutated = copy.deepcopy(documents[name])
            mutated["evidence"][0]["content_hash"] = "0" * 64
            mutations.append((name, mutated))

        for name, document in mutations:
            with self.subTest(source=name, mutation=document):
                with self.assertRaises(AssertionError):
                    self._assert_document(name, document)


if __name__ == "__main__":
    unittest.main()
