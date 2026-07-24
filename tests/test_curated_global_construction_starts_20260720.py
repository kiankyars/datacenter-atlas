from __future__ import annotations

from collections import Counter
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-verne-mantsala-current-development.json": {
        "bytes": 8_739,
        "sha256": "7e993fbb78c72340127b6646ff90fa232595b3eb7d8c3c72c88153550d3e5203",
        "retrieved_at": "2026-07-21T00:05:01Z",
        "campus_key": "curated:verne-mantsala-data-center-campus",
        "project_key": "curated:verne-mantsala-data-center-campus:current-development",
        "country": "Finland",
        "address": "Kapuli, Mäntsälä, Finland",
        "as_of_date": "2026-06-17",
        "confidence": 0.99,
        "evidence_count": 1,
        "capacity": None,
        "status_evidence": "verne-mantsala-construction-start-2026-06-17-captured-2026-07-20",
    },
    "curated-official-2026-07-20-jefferson-lab-jldc-newport-news.json": {
        "bytes": 9_145,
        "sha256": "ea26383ca36ae92f83141d4877d4bd3c46adb24fbb51c1545e574678267c493d",
        "retrieved_at": "2026-07-21T00:05:02Z",
        "campus_key": "curated:jefferson-lab-newport-news-campus",
        "project_key": "curated:jefferson-lab-newport-news-campus:jldc-building",
        "country": "United States",
        "address": "Jefferson Lab campus, Newport News, Virginia, United States",
        "as_of_date": "2026-06-12",
        "confidence": 0.99,
        "evidence_count": 1,
        "capacity": None,
        "status_evidence": "jefferson-lab-jldc-ceremonial-construction-start-2026-06-12-captured-2026-07-20",
    },
    "curated-official-2026-07-20-pdg-mu2-navi-mumbai-current-development.json": {
        "bytes": 14_642,
        "sha256": "07c7a75bb64188a415ac143d8077939979e68fac6b27cae3ef93de70a9502922",
        "retrieved_at": "2026-07-21T00:05:04Z",
        "campus_key": "curated:pdg-mu2-navi-mumbai-data-center-campus",
        "project_key": "curated:pdg-mu2-navi-mumbai-data-center-campus:current-development",
        "country": "India",
        "address": "Navi Mumbai, India",
        "as_of_date": "2026-04-09",
        "confidence": 0.99,
        "evidence_count": 2,
        "capacity": {
            "entity": "campus",
            "metric": "critical_it_mw",
            "base": 120,
            "as_of_date": "2026-07-20",
            "evidence_key": "pdg-mu2-india-facility-page-captured-2026-07-20",
        },
        "status_evidence": "pdg-mu2-mumbai-construction-start-2026-04-09-captured-2026-07-20",
    },
    "curated-official-2026-07-20-cra-prague-gateway-first-building.json": {
        "bytes": 9_080,
        "sha256": "ce19862d4e24e5c0c3006e842c9baaf89ea12137eceb2b579e40bcf716c1f64a",
        "retrieved_at": "2026-07-21T00:05:06Z",
        "campus_key": "curated:cra-prague-gateway-data-center-campus",
        "project_key": "curated:cra-prague-gateway-data-center-campus:first-building",
        "country": "Czechia",
        "address": "Zbraslav–Jíloviště, Prague, Czechia",
        "as_of_date": "2025-07-31",
        "confidence": 0.99,
        "evidence_count": 1,
        "capacity": None,
        "status_evidence": "cra-prague-gateway-first-building-start-2025-07-31-captured-2026-07-20",
    },
    "curated-official-2026-07-20-penzance-chantilly-premier-current-build.json": {
        "bytes": 10_102,
        "sha256": "b78c30cb8ed322dcdae3ce555c9c8f2e90c5de771184901643b64d2653e7aceb",
        "retrieved_at": "2026-07-21T00:09:08Z",
        "campus_key": "curated:penzance-chantilly-premier-data-center",
        "project_key": "curated:penzance-chantilly-premier-data-center:current-facility-build",
        "country": "United States",
        "address": "4151 Autopark Circle, Chantilly, Virginia, United States",
        "as_of_date": "2025-11-21",
        "confidence": 0.99,
        "evidence_count": 1,
        "capacity": None,
        "status_evidence": "fairfax-county-eda-chantilly-premier-groundbreaking-2025-11-21-captured-2026-07-20",
    },
    "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json": {
        "bytes": 15_090,
        "sha256": "4952c3aa872d8ec99f3b9526270b9cd129fdaf454759904eaea01d854d785dd2",
        "retrieved_at": "2026-07-21T00:09:34Z",
        "campus_key": "curated:t5-chicago-iii-northlake-data-center",
        "project_key": "curated:t5-chicago-iii-northlake-data-center:current-facility-build",
        "country": "United States",
        "address": "Northlake, Illinois, United States",
        "as_of_date": "2024-09-25",
        "confidence": 0.99,
        "evidence_count": 2,
        "capacity": {
            "entity": "project",
            "metric": "critical_it_mw",
            "base": 36,
            "as_of_date": "2024-09-07",
            "evidence_key": "clune-t5-chicago-iii-northlake-specification-2024-09-07-captured-2026-07-20",
        },
        "status_evidence": "t5-chicago-iii-groundbreaking-2024-09-25-captured-2026-07-20",
    },
    "curated-official-2026-07-20-maincubes-fra03-phase-2.json": {
        "bytes": 15_026,
        "sha256": "ad5013be9eab2b0aad9d43883b3d7d39f297d9d8e7cbb256c4d12fb84179ebee",
        "retrieved_at": "2026-07-21T00:05:11Z",
        "campus_key": "curated:maincubes-fra03-schwalbach-data-center",
        "project_key": "curated:maincubes-fra03-schwalbach-data-center:phase-2",
        "country": "Germany",
        "address": "Schwalbach am Taunus, Germany",
        "as_of_date": "2025-09-30",
        "confidence": 0.98,
        "evidence_count": 2,
        "capacity": None,
        "status_evidence": "maincubes-fra03-phase-2-timeline-captured-2026-07-20",
    },
}

CAPTURE_SPECS: dict[str, dict[str, Any]] = {
    "verne-mantsala-construction-start-2026-06-17-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-verne-mantsala-current-development.json",
        "url": "https://www.verne.co/news/news-verne-begins-construction-of-the-first-70-mw-on-its-data-center-campus-in-m%C3%A4nts%C3%A4l%C3%A4",
        "published_at": "2026-06-17",
        "body": (113_308, "2ec376832ffe1fb1c1313375cebc197834b657cec18beec6df37dc2152795ebc"),
        "headers": (3_175, "a3df911483381d0ee262ba8c99ece819d8ca79d68692a280fa722505214680f7"),
        "writeout": (13_130, "9e98c3ebb7266d95e47def4eb92d8446ebc0436c0b8513aa63cfc68a30381b1c"),
        "capture_completed_at": "2026-07-21T00:05:01Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": None,
        "download": 19_116,
        "header_count": 28,
        "http_date": "2026-07-21T00:05:01Z",
        "last_modified": "2026-07-20T10:12:03Z",
    },
    "jefferson-lab-jldc-ceremonial-construction-start-2026-06-12-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-jefferson-lab-jldc-newport-news.json",
        "url": "https://www.jlab.org/news/releases/jefferson-lab-breaks-ground-new-building-power-next-generation-scientific-discovery",
        "published_at": "2026-06-12",
        "body": (98_427, "1c9034ba0e4bd2c0d210dc7a3dfe74f9a98c25913b57284661165f9c6bb01f48"),
        "headers": (1_001, "3296c8bbe7ce615aae34cf4282089727a1dce4838285670c14b97b38b3c27b43"),
        "writeout": (12_959, "6379e3e9f0bb496a550ffc04b92308b4418a38320df905588ebfa55414fe757f"),
        "capture_completed_at": "2026-07-21T00:05:02Z",
        "http_version": "HTTP/1.1",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": "chunked",
        "content_length": None,
        "download": 17_563,
        "header_count": 19,
        "http_date": "2026-07-21T00:05:02Z",
        "last_modified": None,
    },
    "pdg-mu2-mumbai-construction-start-2026-04-09-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-pdg-mu2-navi-mumbai-current-development.json",
        "url": "https://www.linkedin.com/posts/princetondg_princetondg-datacenter-india-activity-7447960033515995136-k0c7",
        "published_at": "2026-04-09T10:54:08.375Z",
        "body": (376_356, "4e76483ccd3c08e8b73e53c2a27f0b499f63e1dd310ca288f8f5ad26b478beba"),
        "headers": (5_348, "5846157ecf5ca5a497435624cb10304971a71b5761c8ced54fb3d5754f90af3d"),
        "writeout": (17_693, "d72f7bc9b9259865227a6efd81399a8cc039dd8f4007b29a6a27b25832c80836"),
        "capture_completed_at": "2026-07-21T00:05:03Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": 36_563,
        "download": 36_563,
        "header_count": 27,
        "http_date": "2026-07-21T00:05:03Z",
        "last_modified": None,
    },
    "pdg-mu2-india-facility-page-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-pdg-mu2-navi-mumbai-current-development.json",
        "url": "https://princetondg.com/locations/india/",
        "published_at": None,
        "body": (104_420, "fe5934afc79ba59018d61c6e91ae9adfaa48e836d8f79b62ddcd4ebe75673e21"),
        "headers": (327, "9a2dd3820f6f42d4793003df1281e0238e2b65d46054f6e3d89a587ef90b88ff"),
        "writeout": (12_713, "f3f1e60a61bd63ff64af83b5b1354df61882aa6b3332bfa50a61d5654158f952"),
        "capture_completed_at": "2026-07-21T00:05:04Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": None,
        "download": 19_098,
        "header_count": 10,
        "http_date": "2026-07-21T00:05:04Z",
        "last_modified": "2026-07-20T07:01:26Z",
    },
    "cra-prague-gateway-first-building-start-2025-07-31-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-cra-prague-gateway-first-building.json",
        "url": "https://www.cra.cz/files/clanky_upld/250731_nove-datove-centrum-od-cra-prague-gateway-dc-ma-stavebni-povoleni.pdf",
        "published_at": "2025-07-31",
        "body": (273_734, "dc8a6947a7e6e4d2e0a12260be5726b1e7954747a50b44c12b91835c316cc593"),
        "headers": (960, "94c283ad2a55b7e65b5a7eebbd07faa795b792d4a5a2a8ea2d9ae4c4837864aa"),
        "writeout": (16_733, "495c1f84cc4a6473577c3453bdbd8b2960c14caa5f9c6262a8225a551c868762"),
        "capture_completed_at": "2026-07-21T00:05:06Z",
        "http_version": "HTTP/1.1",
        "content_type": "application/pdf",
        "encoding": None,
        "transfer": None,
        "content_length": 273_734,
        "download": 273_734,
        "header_count": 15,
        "http_date": "2026-07-21T00:05:05Z",
        "last_modified": "2025-07-31T17:35:46Z",
    },
    "fairfax-county-eda-chantilly-premier-groundbreaking-2025-11-21-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-penzance-chantilly-premier-current-build.json",
        "url": "https://fairfaxcountyeda.org/fairfax-county-penzance-officials-break-ground-next-generation-digital-infrastructure-project-to-power-the-worlds-deep-tech-future/",
        "published_at": "2025-11-22",
        "body": (150_151, "55e3dfeae22c7f360950bfd53445ad35868a7982829fd6c915e4f32f3e5a711d"),
        "headers": (1_316, "c99cd5bb19ed299e13de1fbc9776bd4ab11523599301ed2d4072f85eff6cc352"),
        "writeout": (13_183, "e46fccd3cc3c657bfebaa647518af413f28dd8b4a7a386cd6b96bd030aa0b6fe"),
        "capture_completed_at": "2026-07-21T00:09:08Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": None,
        "download": 39_191,
        "header_count": 25,
        "http_date": "2026-07-21T00:09:08Z",
        "last_modified": "2026-07-21T00:09:08Z",
    },
    "t5-chicago-iii-groundbreaking-2024-09-25-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json",
        "url": "https://www.linkedin.com/posts/t5-data-centers_t5chiiii-groundbreaking-datacenters-activity-7244756042381709312-oN2J",
        "published_at": "2024-09-25T17:14:01.532Z",
        "body": (159_835, "b79cd319e22c2c0422d063b890fcc745a3b1d95875a5823c33403c204e964090"),
        "headers": (5_348, "cc75ea55f2545d87e6c630a0f0a20229dfb9aa3de929049cc5e2f22fded78c66"),
        "writeout": (17_736, "5ec8f32b5470eb9b9bf86ad64ca2f436aa37a205e053c9c5312bdfec2a6fac7b"),
        "capture_completed_at": "2026-07-21T00:09:34Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": 19_849,
        "download": 19_849,
        "header_count": 27,
        "http_date": "2026-07-21T00:09:34Z",
        "last_modified": None,
    },
    "clune-t5-chicago-iii-northlake-specification-2024-09-07-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json",
        "url": "https://www.clunegc.com/chicago-sun-times-chicago-areas-data-center-push-continues-as-developer-t5-breaks-ground-on-northlake-facility/",
        "published_at": "2024-09-07",
        "body": (185_527, "0f7505bf7606df271b5c6aa3861d1152c9fd767e245bb291a2be545dd54363ef"),
        "headers": (1_015, "9c57d995d2ca05b389c81e470e11843293212f7c8efd14b5e1b6a0b095bc5d58"),
        "writeout": (8_705, "80ae85df2470e5c293d00661c61d3a74554af72eb1c652047f6d0ed5b70f230e"),
        "capture_completed_at": "2026-07-21T00:05:09Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": None,
        "download": 37_521,
        "header_count": 20,
        "http_date": "2026-07-21T00:05:09Z",
        "last_modified": "2026-07-21T00:05:09Z",
    },
    "maincubes-fra03-phase-2-timeline-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-maincubes-fra03-phase-2.json",
        "url": "https://www.maincubes.com/en/data-centers/carrier-neutral-data-center-fra03/",
        "published_at": None,
        "body": (641_360, "a8b4e29abb55585d15ff83babb4b6aa9e6d1ea4068fe5b5ead20fdcac69686db"),
        "headers": (530, "d83e0aa5f14fe6c3d49096bd16d870bc19d7d811d6e3a6d913a58499e61f952f"),
        "writeout": (16_332, "963d84a3a5dcfbeb6dceeb8ecebe59f0c20acad05b217073ff0d6c41c8fd8ce0"),
        "capture_completed_at": "2026-07-21T00:05:10Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": None,
        "download": 91_256,
        "header_count": 14,
        "http_date": "2026-07-21T00:05:10Z",
        "last_modified": "2026-07-06T12:18:42Z",
    },
    "maincubes-fra03-topout-2025-06-12-captured-2026-07-20": {
        "source": "curated-official-2026-07-20-maincubes-fra03-phase-2.json",
        "url": "https://www.maincubes.com/presse/maincubes-feiert-richtfest-fuer-zweites-rechenzentrum-in-schwalbach/",
        "published_at": "2025-06-12",
        "body": (501_915, "ddfd58615b4bd5598c39e0faa7556727463978ed45c8565f85244a9afe87e714"),
        "headers": (530, "d4d1a8ae9c135cf99c12fe411dfcf44cbb65f69188ec7c8bb18a07f8666e5ac8"),
        "writeout": (16_432, "2a302b18818e1d3e18908a1255de133ade877a33585a5b3f434d027a3915d13c"),
        "capture_completed_at": "2026-07-21T00:05:11Z",
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=UTF-8",
        "encoding": "gzip",
        "transfer": None,
        "content_length": None,
        "download": 68_855,
        "header_count": 14,
        "http_date": "2026-07-21T00:05:11Z",
        "last_modified": "2026-07-06T16:12:47Z",
    },
}


class GlobalConstructionStartsCuratedTests(unittest.TestCase):
    def _source_path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._source_path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("global construction-start curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _write_document(self, destination: Path, document: dict[str, Any]) -> None:
        destination.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _database_state(
        self, order: tuple[str, ...] | list[str], *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        for name in order:
                            spec = SOURCE_SPECS[name]
                            result = CuratedOfficialSourceAdapter().import_file(
                                connection,
                                self._source_path(name),
                                retrieved_at=spec["retrieved_at"],
                            )
                            self.assertEqual(result.warnings, ())
                            self.assertEqual(
                                result.entities_created, 2 if iteration == 0 else 0
                            )
                            self.assertEqual(
                                result.evidence_created,
                                spec["evidence_count"] if iteration == 0 else 0,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities "
                    "ORDER BY kind, stable_key",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "content_hash, retrieved_at, source_url FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, name, tags_json, latitude, longitude, "
                    "geometry_json, as_of_date, recorded_at, method, confidence "
                    "FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method, confidence FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY entities.stable_key",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, high, "
                    "as_of_date, target_date, recorded_at, method, confidence, notes "
                    "FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id "
                    "ORDER BY entities.stable_key, metric, stage",
                    "SELECT entity_id, operating_model FROM operating_model_observations",
                    "SELECT entity_id, workload FROM workload_observations",
                    "SELECT entities.stable_key, targets.stable_key FROM projects "
                    "JOIN entities ON entities.id = projects.entity_id "
                    "JOIN entities AS targets ON targets.id = projects.target_entity_id "
                    "ORDER BY entities.stable_key",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _assert_semantic_contract(
        self, name: str, document: dict[str, Any]
    ) -> None:
        spec = SOURCE_SPECS[name]
        self.assertEqual(document["schema_version"], "1.0")
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
        self.assertEqual(len(document["evidence"]), spec["evidence_count"])
        self.assertEqual(document["campus"]["stable_key"], spec["campus_key"])
        self.assertEqual(document["project"]["stable_key"], spec["project_key"])
        for entity in (document["campus"], document["project"]):
            self.assertEqual(entity["country"], spec["country"])
            self.assertEqual(entity["address"], spec["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["as_of_date"], spec["as_of_date"])
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], spec["confidence"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": spec["status_evidence"],
                    "as_of_date": spec["as_of_date"],
                    "method": "authoritative_construction_start",
                    "confidence": spec["confidence"],
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        capacity = spec["capacity"]
        if capacity is None:
            self.assertEqual(document["capacities"], [])
        else:
            self.assertEqual(len(document["capacities"]), 1)
            row = document["capacities"][0]
            self.assertEqual(row["entity"], capacity["entity"])
            self.assertEqual(row["metric"], capacity["metric"])
            self.assertEqual(row["stage"], "planned")
            self.assertEqual(row["unit"], "MW")
            self.assertEqual((row["low"], row["base"], row["high"]), (capacity["base"],) * 3)
            self.assertEqual(row["as_of_date"], capacity["as_of_date"])
            self.assertEqual(row["evidence_key"], capacity["evidence_key"])
            self.assertIsNone(row["target_date"])

    def test_sources_are_canonical_regular_mode_and_byte_pinned(self) -> None:
        for name, spec in SOURCE_SPECS.items():
            with self.subTest(source=name):
                source = self._source_path(name)
                self.assertTrue(source.is_file())
                self.assertFalse(source.is_symlink())
                self.assertTrue(stat.S_ISREG(source.stat().st_mode))
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
                self.assertEqual(source.stat().st_size, spec["bytes"])
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).hexdigest(), spec["sha256"]
                )
                text = source.read_text(encoding="utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
                )
                self._assert_semantic_contract(name, document)

    def test_all_capture_bundles_are_exact_closed_and_credential_free(self) -> None:
        evidence: dict[str, dict[str, Any]] = {}
        for name in SOURCE_SPECS:
            for item in self._load(name)["evidence"]:
                self.assertNotIn(item["key"], evidence)
                evidence[item["key"]] = item
        self.assertEqual(set(evidence), set(CAPTURE_SPECS))
        forbidden_telemetry = {
            "authorization",
            "certs",
            "conn_id",
            "cookie",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }
        for key, expected in CAPTURE_SPECS.items():
            with self.subTest(evidence=key):
                item = evidence[key]
                metadata = item["metadata"]
                source_spec = SOURCE_SPECS[expected["source"]]
                self.assertEqual(item["source_url"], expected["url"])
                self.assertEqual(item["published_at"], expected["published_at"])
                self.assertEqual(item["retrieved_at"], source_spec["retrieved_at"])
                self.assertEqual(item["content_hash"], expected["body"][1])
                self.assertIn(
                    f'{expected["body"][0]}-byte', metadata["content_hash_scope"]
                )
                self.assertEqual(
                    metadata["content_hash_verification"], "fetched_bytes_sha256"
                )
                self.assertIn(
                    f'{expected["headers"][0]}-byte',
                    metadata["capture_headers_scope"],
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], expected["headers"][1]
                )
                self.assertIn(
                    f'{expected["writeout"][0]}-byte',
                    metadata["capture_curl_writeout_scope"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    expected["writeout"][1],
                )
                self.assertEqual(
                    metadata["capture_completed_at"], expected["capture_completed_at"]
                )
                self.assertEqual(metadata["http_status"], 200)
                self.assertEqual(metadata["curl_exit_code"], 0)
                self.assertEqual(
                    metadata["http_version_as_received"], expected["http_version"]
                )
                self.assertEqual(metadata["content_type"], expected["content_type"])
                self.assertEqual(
                    metadata["content_encoding_as_received"], expected["encoding"]
                )
                self.assertEqual(
                    metadata["http_transfer_encoding_as_received"],
                    expected["transfer"],
                )
                self.assertEqual(
                    metadata["http_content_length_bytes_as_received"],
                    expected["content_length"],
                )
                self.assertEqual(
                    metadata["curl_size_download_bytes_as_received"],
                    expected["download"],
                )
                self.assertEqual(
                    metadata["curl_size_header_bytes"], expected["headers"][0]
                )
                self.assertEqual(
                    metadata["curl_num_headers"], expected["header_count"]
                )
                self.assertEqual(metadata["response_http_date"], expected["http_date"])
                self.assertEqual(
                    metadata["http_last_modified_at"], expected["last_modified"]
                )
                self.assertEqual(metadata["requested_url"], expected["url"])
                self.assertEqual(metadata["effective_url"], expected["url"])
                self.assertEqual(metadata["response_header_blocks"], 1)
                self.assertEqual(metadata["redirect_count"], 0)
                self.assertTrue(
                    forbidden_telemetry.isdisjoint(
                        {field.casefold() for field in metadata}
                    )
                )
                self.assertIn("credential-free", metadata["retrieval_method"])
                self.assertIn("not redistributed", metadata["capture_artifact_guardrail"])

    def test_semantic_capacity_and_historical_guardrails_are_exact(self) -> None:
        documents = {name: self._load(name) for name in SOURCE_SPECS}
        all_capacity_rows = [
            row for document in documents.values() for row in document["capacities"]
        ]
        self.assertEqual(
            sorted(
                (
                    row["entity"],
                    row["metric"],
                    row["base"],
                    row["as_of_date"],
                )
                for row in all_capacity_rows
            ),
            [
                ("campus", "critical_it_mw", 120, "2026-07-20"),
                ("project", "critical_it_mw", 36, "2024-09-07"),
            ],
        )
        self.assertTrue(
            all(row["metric"] == "critical_it_mw" for row in all_capacity_rows)
        )
        serialized = json.dumps(documents, ensure_ascii=False)
        for metric in (
            "annual_energy_mwh",
            "grid_connection_mw",
            "gross_facility_mw",
            "generation_nameplate_mw",
            '"metric": "pue"',
        ):
            self.assertNotIn(metric, serialized)
        for name, document in documents.items():
            evidence = {item["key"]: item for item in document["evidence"]}
            status_metadata = evidence[SOURCE_SPECS[name]["status_evidence"]]["metadata"]
            self.assertIn("historical", status_metadata["historical_status_guardrail"])
            self.assertIn("does not prove", status_metadata["historical_status_guardrail"])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            for entity in (document["campus"], document["project"]):
                self.assertEqual(entity["roles"], {})
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])

        verne = documents[
            "curated-official-2026-07-20-verne-mantsala-current-development.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(verne["reported_initial_capacity_mw_untyped"], 70)
        self.assertIn("no capacity row", verne["capacity_exclusion"])

        cra = documents[
            "curated-official-2026-07-20-cra-prague-gateway-first-building.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(cra["reported_secured_power_mw_untyped"], 26)
        self.assertIn("no capacity row", cra["capacity_exclusion"])

        penzance = documents[
            "curated-official-2026-07-20-penzance-chantilly-premier-current-build.json"
        ]["evidence"][0]["metadata"]
        self.assertEqual(penzance["reported_capacity_mw_untyped"], 45)
        self.assertIn("no capacity row", penzance["capacity_exclusion"])
        self.assertEqual(penzance["reported_lease_counterparty"], "Amazon Web Services (AWS)")
        self.assertIn("no normalized", penzance["role_and_tenant_guardrail"])

        pdg = documents[
            "curated-official-2026-07-20-pdg-mu2-navi-mumbai-current-development.json"
        ]
        pdg_evidence = {item["key"]: item for item in pdg["evidence"]}
        self.assertEqual(
            pdg_evidence["pdg-mu2-india-facility-page-captured-2026-07-20"][
                "metadata"
            ]["reported_critical_it_capacity_mw"],
            120,
        )
        self.assertIn(
            "explicitly types 120 MW as critical IT",
            pdg_evidence["pdg-mu2-india-facility-page-captured-2026-07-20"][
                "metadata"
            ]["capacity_scope"],
        )

        t5 = documents[
            "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json"
        ]
        t5_evidence = {item["key"]: item for item in t5["evidence"]}
        self.assertEqual(
            t5_evidence[
                "clune-t5-chicago-iii-northlake-specification-2024-09-07-captured-2026-07-20"
            ]["metadata"]["reported_it_capacity_mw"],
            36,
        )

    def test_jldc_and_fra03_stage_precision_cannot_leak(self) -> None:
        jldc_name = "curated-official-2026-07-20-jefferson-lab-jldc-newport-news.json"
        jldc = self._load(jldc_name)
        metadata = jldc["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["reported_status_wording"],
            "marked the ceremonial start of construction for the Jefferson Lab Data Center",
        )
        self.assertIn("only one generic", metadata["construction_scope"])
        self.assertEqual(jldc["lifecycle"][0]["value"], "under_construction")

        fra_name = "curated-official-2026-07-20-maincubes-fra03-phase-2.json"
        fra = self._load(fra_name)
        evidence = {item["key"]: item for item in fra["evidence"]}
        phase = evidence["maincubes-fra03-phase-2-timeline-captured-2026-07-20"][
            "metadata"
        ]
        topout = evidence[
            "maincubes-fra03-topout-2025-06-12-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(phase["reported_phase_two_start_period"], "Q3/2025")
        self.assertEqual(phase["quarter_end_as_of_date"], "2025-09-30")
        self.assertIn("not the exact start date", phase["quarter_end_as_of_basis"])
        self.assertEqual(phase["reported_full_fra03_it_capacity_mw"], 16)
        self.assertIn("creates no", phase["capacity_exclusion"])
        self.assertIn("cannot support a Phase 2 shell", topout["phase_disambiguation_guardrail"])
        self.assertEqual(fra["lifecycle"][0]["value"], "under_construction")
        self.assertEqual(fra["capacities"], [])

    def test_import_is_offline_exact_idempotent_and_order_independent(self) -> None:
        names = tuple(SOURCE_SPECS)
        once = self._database_state(names)
        self.assertEqual(self._database_state(names, repetitions=2), once)
        self.assertEqual(self._database_state(tuple(reversed(names))), once)
        (
            entities,
            evidence,
            snapshots,
            lifecycle,
            capacities,
            operating_models,
            workloads,
            projects,
        ) = once
        self.assertEqual(len(entities), 14)
        self.assertEqual(len(evidence), 10)
        self.assertEqual(len(snapshots), 14)
        self.assertEqual(len(lifecycle), 7)
        self.assertEqual(len(capacities), 2)
        self.assertEqual(operating_models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(len(projects), 7)
        self.assertEqual({row[1] for row in lifecycle}, {"under_construction"})
        self.assertEqual({row[1] for row in capacities}, {"critical_it_mw"})
        self.assertEqual({row[5] for row in capacities}, {36.0, 120.0})

    def test_stable_evidence_and_exact_identity_markers_do_not_collide(self) -> None:
        new_names = set(SOURCE_SPECS)
        claimed_stable = {
            spec[key]
            for spec in SOURCE_SPECS.values()
            for key in ("campus_key", "project_key")
        }
        claimed_evidence = set(CAPTURE_SPECS)
        identity_markers = {
            "verne mäntsälä data center campus",
            "jefferson lab data center (jldc)",
            "princeton digital group mu2 navi mumbai data center campus",
            "cra prague gateway data center campus",
            "penzance chantilly premier data center",
            "t5 chicago iii northlake data center",
            "maincubes fra03 phase 2",
        }
        intentional_coordinate_successors = {
            "curated-official-2026-07-20-verne-mantsala-current-development-v2.json": {
                "predecessor": "curated-official-2026-07-20-verne-mantsala-current-development.json",
                "identity": {"verne mäntsälä data center campus"},
            },
            "curated-official-2026-07-20-penzance-chantilly-premier-current-build-v2.json": {
                "predecessor": "curated-official-2026-07-20-penzance-chantilly-premier-current-build.json",
                "identity": {"penzance chantilly premier data center"},
            },
            "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build-v2.json": {
                "predecessor": "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json",
                "identity": {"t5 chicago iii northlake data center"},
            },
            "curated-official-2026-07-20-cra-prague-gateway-first-building-v2.json": {
                "predecessor": "curated-official-2026-07-20-cra-prague-gateway-first-building.json",
                "identity": {"cra prague gateway data center campus"},
            },
            "curated-official-2026-07-20-maincubes-fra03-phase-2-v2.json": {
                "predecessor": "curated-official-2026-07-20-maincubes-fra03-phase-2.json",
                "identity": {"maincubes fra03 phase 2"},
            },
        }
        collisions: dict[str, Any] = {}
        identity_hits: dict[str, list[str]] = {}
        intentional_overlaps: dict[str, dict[str, list[str]]] = {}
        for source in sorted((ROOT / "sources").glob("*.json")):
            if source.name in new_names:
                continue
            text = source.read_text(encoding="utf-8")
            lowered = text.casefold()
            hits = sorted(marker for marker in identity_markers if marker.casefold() in lowered)
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                continue
            stable_keys = {
                entity["stable_key"]
                for entity in (document.get("campus"), document.get("project"))
                if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str)
            }
            evidence_keys = {
                item["key"]
                for item in document.get("evidence", [])
                if isinstance(item, dict) and isinstance(item.get("key"), str)
            }
            stable_overlap = sorted(claimed_stable & stable_keys)
            evidence_overlap = sorted(claimed_evidence & evidence_keys)
            successor = intentional_coordinate_successors.get(source.name)
            if successor is not None:
                predecessor = SOURCE_SPECS[successor["predecessor"]]
                expected = {
                    "stable": sorted(
                        {
                            predecessor["campus_key"],
                            predecessor["project_key"],
                        }
                    ),
                    "evidence": sorted(
                        key
                        for key, capture in CAPTURE_SPECS.items()
                        if capture["source"] == successor["predecessor"]
                    ),
                    "identity": sorted(successor["identity"]),
                }
                actual = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                    "identity": hits,
                }
                self.assertEqual(actual, expected)
                intentional_overlaps[source.name] = actual
                continue
            if hits:
                identity_hits[source.name] = hits
            if stable_overlap or evidence_overlap:
                collisions[source.name] = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                }
        self.assertEqual(
            set(intentional_overlaps), set(intentional_coordinate_successors)
        )
        self.assertEqual(collisions, {})
        self.assertEqual(identity_hits, {})

    def test_records_are_unseeded_through_v57_and_v58_selects_exact_sources(self) -> None:
        forbidden_markers = set(SOURCE_SPECS)
        forbidden_markers.update(
            spec[key]
            for spec in SOURCE_SPECS.values()
            for key in ("campus_key", "project_key")
        )
        seeded_hits: dict[str, list[str]] = {}
        for definition in sorted((ROOT / "sources").glob("open-seed-*.json")):
            version = definition.stem.rpartition("-v")[2]
            if not version.isdigit() or int(version) > 57:
                continue
            text = definition.read_text(encoding="utf-8")
            hits = sorted(marker for marker in forbidden_markers if marker in text)
            if hits:
                seeded_hits[definition.name] = hits
        self.assertEqual(seeded_hits, {})

        v58 = json.loads(
            (ROOT / "sources/open-seed-2026-07-20-v58.json").read_text(
                encoding="utf-8"
            )
        )
        selected_names = [Path(row["path"]).name for row in v58["curated_inputs"]]
        self.assertEqual(
            Counter(name for name in selected_names if name in SOURCE_SPECS),
            Counter(SOURCE_SPECS.keys()),
        )

    def test_tamper_and_semantic_leakage_are_detected(self) -> None:
        name = "curated-official-2026-07-20-jefferson-lab-jldc-newport-news.json"
        original = self._load(name)
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            invalid_hash = copy.deepcopy(original)
            invalid_hash["evidence"][0]["content_hash"] = "not-a-sha256"
            invalid_path = temporary_path / name
            self._write_document(invalid_path, invalid_hash)
            connection, _ = initialize(temporary_path / "invalid.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "content_hash must be a lowercase SHA-256"
                ):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        invalid_path,
                        retrieved_at=SOURCE_SPECS[name]["retrieved_at"],
                    )
            finally:
                connection.close()

            weak_method = copy.deepcopy(original)
            weak_method["lifecycle"][0]["method"] = "authoritative_status_update"
            weak_path = temporary_path / f"weak-{name}"
            self._write_document(weak_path, weak_method)
            connection, _ = initialize(temporary_path / "weak.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "construction status requires"
                ):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        weak_path,
                        retrieved_at=SOURCE_SPECS[name]["retrieved_at"],
                    )
            finally:
                connection.close()

            duplicate_path = temporary_path / f"duplicate-{name}"
            duplicate_path.write_text(
                self._source_path(name)
                .read_text(encoding="utf-8")
                .replace(
                    '  "schema_version": "1.0",',
                    '  "schema_version": "1.0",\n  "schema_version": "1.0",',
                    1,
                ),
                encoding="utf-8",
            )
            connection, _ = initialize(temporary_path / "duplicate.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "duplicate JSON field"
                ):
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        duplicate_path,
                        retrieved_at=SOURCE_SPECS[name]["retrieved_at"],
                    )
            finally:
                connection.close()

        promoted = copy.deepcopy(original)
        promoted["lifecycle"][0]["value"] = "foundations"
        with self.assertRaises(AssertionError):
            self._assert_semantic_contract(name, promoted)

        fra_name = "curated-official-2026-07-20-maincubes-fra03-phase-2.json"
        leaked_capacity = copy.deepcopy(self._load(fra_name))
        leaked_capacity["capacities"].append(
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 16,
                "base": 16,
                "high": 16,
                "method": "reported",
                "confidence": 0.98,
                "evidence_key": "maincubes-fra03-phase-2-timeline-captured-2026-07-20",
                "as_of_date": "2025-09-30",
                "target_date": None,
                "notes": "invalid full-site to phase allocation",
            }
        )
        with self.assertRaises(AssertionError):
            self._assert_semantic_contract(fra_name, leaked_capacity)

    def test_sources_import_offline_in_both_workspace_layouts(self) -> None:
        sources = [
            (str(self._source_path(name)), spec["retrieved_at"])
            for name, spec in SOURCE_SPECS.items()
        ]
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated import CuratedOfficialSourceAdapter
from {package}.database import initialize
from {package}.service import validate_database

sources = {sources!r}
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for iteration in range(2):
                for source, retrieved_at in sources:
                    result = CuratedOfficialSourceAdapter().import_file(
                        connection, Path(source), retrieved_at=retrieved_at
                    )
                    assert result.warnings == ()
                    assert result.entities_created == (2 if iteration == 0 else 0)
        assert validate_database(connection) == []
        counts = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
        }}
        metrics = [row[0] for row in connection.execute("SELECT metric FROM capacity_estimates ORDER BY base")]
        statuses = [row[0] for row in connection.execute("SELECT status FROM lifecycle_observations ORDER BY id")]
        print(json.dumps({{"counts": counts, "metrics": metrics, "statuses": statuses}}, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=45,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(
                    output["counts"],
                    {
                        "capacity": 2,
                        "entities": 14,
                        "evidence": 10,
                        "lifecycle": 7,
                        "operating_models": 0,
                        "snapshots": 14,
                        "workloads": 0,
                    },
                )
                self.assertEqual(output["metrics"], ["critical_it_mw"] * 2)
                self.assertEqual(output["statuses"], ["under_construction"] * 7)


if __name__ == "__main__":
    unittest.main()
