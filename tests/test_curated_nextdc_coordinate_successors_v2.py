from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.curated_v11 import (
    LEGACY_CURATED_SHA256,
    CuratedOfficialSourceAdapterV11,
)
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PDF_KEY = "nextdc-1h26-results-presentation-captured-2026-07-19"
CONTACT_KEY = "nextdc-current-contact-locations-captured-2026-07-20"
V11_RECORDED_AT = "2026-07-20T23:15:31Z"

SPECS: dict[str, dict[str, Any]] = {
    "B2": {
        "token": "b2-brisbane",
        "v1_sha256": "ec0da982be0d87f142618100a518f947fd58bc014d5f7b621629fbe7cda5f97d",
        "v1_size": 14269,
        "v2_sha256": "0e5c6c9dc979bc0604a8b49541d6c4f9af548d69b6f7864b99b23893e7d8ea3e",
        "v2_size": 48417,
        "old_address": "Brisbane, Australia",
        "address": "454 St Pauls Terrace, Fortitude Valley QLD 4006",
        "coordinates": (-27.4539022, 153.0332005),
        "page_id": "brisbane",
    },
    "M2": {
        "token": "m2-melbourne",
        "v1_sha256": "1674ac8b23e48cf947e01ede96f0baa3fc94d891bc84ab35b4c61d10134e317b",
        "v1_size": 14278,
        "v2_sha256": "fb7ba690ad00ea6734a1299167131ac744c4db11f78dd3d27cbc87490d618134",
        "v2_size": 48397,
        "old_address": "Melbourne, Australia",
        "address": "75 Sharps Road, Tullamarine VIC 3043",
        "coordinates": (-37.7080294, 144.8756939),
        "page_id": "melbourne",
    },
    "P1": {
        "token": "p1-perth",
        "v1_sha256": "cf22bd4df7074daf34dc13f0ba2855e7ed8d5ec701b603f45aca3531ba0afefd",
        "v1_size": 14254,
        "v2_sha256": "ab8f3acc96ec0e94dc3c7ebcaac321f087c9e7c960ab572436b9eb008de002dc",
        "v2_size": 48398,
        "old_address": "Perth, Australia",
        "address": "4 Millrose Drive, Malaga WA 6090",
        "coordinates": (-31.8644016, 115.895935),
        "page_id": "perth",
    },
    "P2": {
        "token": "p2-perth",
        "v1_sha256": "60c0825766b68dccfcfa8b361389394bd2b5d0321ed0591fc20da84512798a46",
        "v1_size": 14254,
        "v2_sha256": "4802ae0d901e31536c56521910c061ca503b01602078d494b684d92e24b06bb7",
        "v2_size": 48404,
        "old_address": "Perth, Australia",
        "address": "11 Newcastle Street, Perth WA 6000",
        "coordinates": (-31.9496948, 115.8685493),
        "page_id": "perth",
    },
    "KL1": {
        "token": "kl1-kuala-lumpur",
        "v1_sha256": "b428c2d24c796e5dc68ae64221c90fc0a85680061a092f97786512941b2c8da3",
        "v1_size": 14293,
        "v2_sha256": "748522f0e5cfbc0c24de6929d986fa886f763d03897fdf97346635daf2797bc4",
        "v2_size": 48466,
        "old_address": "Kuala Lumpur, Malaysia",
        "address": "1, Jln 51a/229, Seksyen 51a, Petaling Jaya, 46100 Selangor",
        "coordinates": (3.0965132, 101.6241451),
        "page_id": "malaysia",
    },
}

PAGE_CAPTURES = {
    "brisbane": {
        "url": "https://www.nextdc.com/data-centres/brisbane-data-centres-colocation",
        "retrieved_at": "2026-07-20T23:13:48Z",
        "size": 358131,
        "body": "ec5e503ee4bfdb7c77272df9b16a22dacfe64dc7c6db7de461f9372bb571bc8e",
        "headers_size": 3178,
        "headers": "7ea117e0e5c73ed82c42dcd98c3d0306c640e29f1f7e864d4e504c5ed1d86195",
        "writeout_size": 240,
        "writeout": "63577a2c4a93977e23471642a70e93692889bb74fb9c3fb4323b468d526f9300",
    },
    "melbourne": {
        "url": "https://www.nextdc.com/data-centres/melbourne-data-centres-colocation",
        "retrieved_at": "2026-07-20T23:13:48Z",
        "size": 377673,
        "body": "8951a209a4cf97c8e5044edd439c93f61c43d723a9bce35b43efbf57bb4fcb6e",
        "headers_size": 3170,
        "headers": "378a4d456ff62d5987d0cb2e740f928e0fa856b3415c77fcd49712dd6ff3a019",
        "writeout_size": 241,
        "writeout": "f81899f812f16ad396d6ffdca6ac1067c03808adfda79f15047f673051c2cce3",
    },
    "perth": {
        "url": "https://www.nextdc.com/data-centres/perth-data-centres-colocation",
        "retrieved_at": "2026-07-20T23:13:50Z",
        "size": 348268,
        "body": "7e85f2e89281b3e2029ac0691329a5349a8d4e13044ded8507a917c103be32bc",
        "headers_size": 3180,
        "headers": "ff98309c9062814d679e063f5816c19e1deb869a85246f89a750d12dce24db4d",
        "writeout_size": 237,
        "writeout": "9b235adc05ca3959af7ef4edc75cb6db0e2a510c1b4736d942a925e00814310f",
    },
    "malaysia": {
        "url": "https://www.nextdc.com/data-centres/malaysia-data-centres-colocation",
        "retrieved_at": "2026-07-20T23:13:50Z",
        "size": 353507,
        "body": "ed9c833acc4c7f3fbd5e3341ebe7b50309fe6a51e0541dc15e9755f8b31c2ba7",
        "headers_size": 3196,
        "headers": "bad7ad1ec468fab74d4202e6629b6897121df7e58045c4c63e56ae5ea3ffb344",
        "writeout_size": 240,
        "writeout": "de909892a906a85c0778e9bc12f1a3e8e98f9b54d5cdcdf20910ca65d61fb6f4",
    },
}

CONTACT_CAPTURE = {
    "url": "https://www.nextdc.com/contact",
    "retrieved_at": "2026-07-20T23:13:48Z",
    "size": 264101,
    "body": "73792fd9af539fcc5316f184d7f6ccb6ee00770069705995e04f1d2efa669cb0",
    "headers_size": 4045,
    "headers": "4baba3d19bccd5215a5bce8de1572d1a3237a24cb8459e27120b7a69b52b6a3f",
    "writeout_size": 202,
    "writeout": "2cad4b7edaba9b10ffd7845e6e52397e453b62fdd08009677b1bbe510b587840",
}

DOCUMENT_CAPTURES = {
    "partner_onboarding_guide": {
        "url": "https://nextdc.com/hubfs/240718_Partner_Onboarding_Guide.pdf",
        "retrieved_at": "2026-07-20T23:15:29Z",
        "size": 5587896,
        "body": "1ffa85b6152242da9f604a3f675b8ede7ee3219095426fc47d5f089b3f932aa7",
        "headers_size": 1656,
        "headers": "b5ceaf07d9fbbd5990af0203addd66ade6ca8f61dd86de8760de4ce4a4b58a40",
        "writeout_size": 224,
        "writeout": "876a7d7619be4373c5da69e28d212467cb4b3633f160622e4f750ed36b7284b7",
    },
    "iso_9001_qms40018": {
        "url": "https://www.nextdc.com/hubfs/Downloadable%20PDFs/ISO%209001.pdf",
        "retrieved_at": "2026-07-20T23:15:30Z",
        "size": 503061,
        "body": "8c485e6aa05ec0225c72faf5dbcc384efec73ca5fd2bbca8f0ad52d026ec0065",
        "headers_size": 1686,
        "headers": "d6d5a9aa47078c61446a3b342535ce04f5bdc6e192c43efbe31a0d51ac031ef5",
        "writeout_size": 226,
        "writeout": "13c2368fce4d1bbecce6c379badd78985a28d0a36dd5579b5fdc85c2a719fde3",
    },
    "fy25_esg_report": {
        "url": "https://www.nextdc.com/hubfs/ASX%20Announcements/FY25%20Environmental%2C%20Social%20and%20Governance%20Report.pdf",
        "retrieved_at": "2026-07-20T23:15:31Z",
        "size": 8893796,
        "body": "294ccc0b14d61ad0483f96b5a440c2bdcce48dfe2420053c6a3c7a0b64bc04da",
        "headers_size": 1703,
        "headers": "36894f260e9882cdcc9af80e11b056c36f520a6a3669e040ba265dec10e03d6d",
        "writeout_size": 277,
        "writeout": "1347345983b69537d6914299b77d977f65973abfa9575e47f299bb08a1e3228d",
    },
}

UNCHANGED_V1_TOKENS = (
    "d2-darwin",
    "ge1-geelong",
    "m3-melbourne",
    "s3-sydney",
    "s6-sydney",
    "sc1-sunshine-coast",
    "sc2-sunshine-coast",
)

TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "entity_snapshots",
    "administrative_assignments",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class NextdcCoordinateSuccessorsV2Tests(unittest.TestCase):
    def _filename(self, spec: dict[str, Any], version: str) -> str:
        suffix = "-v2" if version == "v2" else ""
        return (
            "curated-official-2026-07-19-nextdc-"
            f"{spec['token']}-1h26-fitout{suffix}.json"
        )

    def _path(self, spec: dict[str, Any], version: str) -> Path:
        return ROOT / "sources" / self._filename(spec, version)

    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _network_guard(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _state(self, connection: Any) -> dict[str, tuple[tuple[Any, ...], ...]]:
        return {
            table: tuple(
                sorted(
                    (
                        tuple(row)
                        for row in connection.execute(f"SELECT * FROM {table}")
                    ),
                    key=repr,
                )
            )
            for table in TABLES
        }

    def _recorded_at(self, path: Path) -> str:
        document = self._load(path)
        if document["schema_version"] == "1.1":
            return V11_RECORDED_AT
        return document["evidence"][0]["retrieved_at"]

    def _build(
        self, names: Iterable[str], *, repeat: bool = False
    ) -> tuple[Any, dict[str, tuple[tuple[Any, ...], ...]]]:
        temporary = tempfile.TemporaryDirectory()
        connection, _ = initialize(Path(temporary.name) / "atlas.sqlite")
        try:
            with self._network_guard():
                for name in names:
                    path = ROOT / "sources" / name
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        path,
                        recorded_at=self._recorded_at(path),
                    )
                state = self._state(connection)
                if repeat:
                    for name in names:
                        path = ROOT / "sources" / name
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            path,
                            recorded_at=self._recorded_at(path),
                        )
                        self.assertEqual(result.entities_created, 0)
                        self.assertEqual(result.evidence_created, 0)
                    self.assertEqual(self._state(connection), state)
            self.assertEqual(validate_database(connection), [])
            connection.close()
            return temporary, state
        except Exception:
            connection.close()
            temporary.cleanup()
            raise

    def _assert_capture(
        self,
        capture: dict[str, Any],
        expected: dict[str, Any],
        *,
        header_blocks: int = 1,
    ) -> None:
        self.assertEqual(capture["requested_url"], expected["url"])
        self.assertEqual(capture["effective_url"], expected["url"])
        self.assertEqual(capture["retrieved_at"], expected["retrieved_at"])
        self.assertEqual(capture["http_status"], 200)
        self.assertEqual(capture["http_version_as_received"], "HTTP/2")
        self.assertEqual(capture["redirect_count"], 0)
        self.assertEqual(capture["response_header_blocks"], header_blocks)
        self.assertEqual(capture["size_download_bytes_as_received"], expected["size"])
        self.assertEqual(capture["body_sha256"], expected["body"])
        self.assertIn(f"exact {expected['size']}-byte", capture["body_scope"])
        self.assertEqual(capture["headers_sha256"], expected["headers"])
        self.assertIn(
            f"exact {expected['headers_size']}-byte", capture["headers_scope"]
        )
        self.assertEqual(capture["curl_writeout_sha256"], expected["writeout"])
        self.assertIn(
            f"exact {expected['writeout_size']}-byte",
            capture["curl_writeout_scope"],
        )
        self.assertIn("credential-free", capture["retrieval_method"])
        self.assertIn("No credentials were supplied", capture["credentials_guardrail"])
        self.assertIn("deleted", capture["artifact_guardrail"])

    def test_exact_hashes_modes_canonical_json_and_unseeded_scope(self) -> None:
        expected_v2_paths = set()
        for code, spec in SPECS.items():
            with self.subTest(facility=code):
                for version in ("v1", "v2"):
                    path = self._path(spec, version)
                    expected_v2_paths.add(path) if version == "v2" else None
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                    self.assertEqual(path.stat().st_size, spec[f"{version}_size"])
                    self.assertEqual(
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                        spec[f"{version}_sha256"],
                    )
                    document = self._load(path)
                    self.assertEqual(
                        path.read_text(encoding="utf-8"),
                        json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                    )

        actual_v2_paths = set(
            (ROOT / "sources").glob("curated-official-*-nextdc-*-v2.json")
        )
        self.assertEqual(actual_v2_paths, expected_v2_paths)
        for seed_path in (ROOT / "sources").glob("open-seed-*.json"):
            seed_document = self._load(seed_path)
            selected = {
                record["path"] for record in seed_document["curated_inputs"]
            }
            selected_v2 = {
                path for path in expected_v2_paths if path.name in seed_path.read_text()
            }
            version_match = re.fullmatch(
                r"open-seed-\d{4}-\d{2}-\d{2}-v(\d+)\.json", seed_path.name
            )
            self.assertIsNotNone(version_match, seed_path.name)
            seed_version = int(version_match.group(1))
            if seed_version >= 57:
                self.assertEqual(selected_v2, expected_v2_paths)
                for spec in SPECS.values():
                    self.assertNotIn(
                        f"sources/{self._filename(spec, 'v1')}", selected
                    )
            else:
                self.assertEqual(selected_v2, set(), seed_path.name)

        self.assertEqual(
            hashlib.sha256(
                (ROOT / "datacenter_atlas/curated.py").read_bytes()
            ).hexdigest(),
            LEGACY_CURATED_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "datacenter_atlas/open_seed_release.py").read_bytes()
            ).hexdigest(),
            "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab",
        )
        self.assertEqual(
            hashlib.sha256(
                (ROOT / "tests/test_curated_nextdc_1h26_tranche.py").read_bytes()
            ).hexdigest(),
            "9a9f8e3f93992ab50a0719ec6cdce09e73a63de5f55914f98401078010740995",
        )

    def test_json_delta_is_only_explicit_location_snapshot_and_evidence(self) -> None:
        contact_records = []
        perth_records = []
        for code, spec in SPECS.items():
            with self.subTest(facility=code):
                v1 = self._load(self._path(spec, "v1"))
                v2 = self._load(self._path(spec, "v2"))
                self.assertEqual(v1["schema_version"], "1.0")
                self.assertEqual(v2["schema_version"], "1.1")
                self.assertEqual(v2["evidence"][0], v1["evidence"][0])
                self.assertEqual(v2["evidence"][0]["key"], PDF_KEY)
                self.assertEqual(len(v2["evidence"]), 6)
                self.assertEqual(v2["evidence"][1]["key"], CONTACT_KEY)
                contact_records.append(v2["evidence"][1])
                if spec["page_id"] == "perth":
                    perth_records.append(v2["evidence"][2])

                restored = copy.deepcopy(v2)
                restored["schema_version"] = "1.0"
                restored["evidence"] = [copy.deepcopy(v2["evidence"][0])]
                for entity_name in ("campus", "project"):
                    before = v1[entity_name]
                    after = v2[entity_name]
                    for key in (
                        "stable_key",
                        "name",
                        "country",
                        "roles",
                        "geometry",
                        "confidence",
                    ):
                        self.assertEqual(after[key], before[key], key)
                    self.assertEqual(after["address"], spec["address"])
                    latitude, longitude = spec["coordinates"]
                    self.assertEqual(
                        after["coordinates"],
                        {"latitude": latitude, "longitude": longitude},
                    )
                    self.assertIsNone(after["geometry"])
                    self.assertEqual(after["evidence_key"], CONTACT_KEY)
                    self.assertEqual(after["as_of_date"], "2026-07-20")
                    self.assertEqual(after["method"], "authoritative_site_plan")
                    restored[entity_name]["address"] = before["address"]
                    restored[entity_name]["coordinates"] = before["coordinates"]
                    restored[entity_name]["evidence_key"] = before["evidence_key"]
                    restored[entity_name]["as_of_date"] = before["as_of_date"]
                    restored[entity_name]["method"] = before["method"]

                for section in (
                    "lifecycle",
                    "operating_models",
                    "workloads",
                    "capacities",
                ):
                    self.assertEqual(v2[section], v1[section], section)
                self.assertEqual(restored, v1)
                self.assertEqual(v2["operating_models"], [])
                self.assertEqual(v2["workloads"], [])
                for row in (*v2["lifecycle"], *v2["capacities"]):
                    self.assertEqual(row["evidence_key"], PDF_KEY)
                    self.assertEqual(row["as_of_date"], "2025-12-31")
                self.assertNotIn(
                    "annual_energy_mwh", {row["metric"] for row in v2["capacities"]}
                )
                self.assertTrue(
                    all(row["kind"] != "satellite_imagery" for row in v2["evidence"])
                )

        self.assertTrue(all(row == contact_records[0] for row in contact_records))
        self.assertEqual(perth_records[0], perth_records[1])
        for evidence_index in (3, 4, 5):
            records = [
                self._load(self._path(spec, "v2"))["evidence"][evidence_index]
                for spec in SPECS.values()
            ]
            self.assertTrue(all(row == records[0] for row in records))

    def test_capture_lineage_coordinates_and_discrepancy_guardrails(self) -> None:
        first = self._load(self._path(SPECS["B2"], "v2"))
        contact = first["evidence"][1]
        self.assertEqual(contact["source_url"], CONTACT_CAPTURE["url"])
        self.assertEqual(contact["content_hash"], CONTACT_CAPTURE["body"])
        self._assert_capture(
            contact["metadata"]["capture"], CONTACT_CAPTURE, header_blocks=2
        )
        batch = contact["metadata"]["coordinate_successor"]
        self.assertNotIn("location_page_captures", batch)
        self.assertNotIn("official_document_captures", batch)
        nested_retrievals: list[str] = []

        def collect_retrievals(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "retrieved_at":
                        nested_retrievals.append(item)
                    collect_retrievals(item)
            elif isinstance(value, list):
                for item in value:
                    collect_retrievals(item)

        collect_retrievals(contact["metadata"])
        self.assertEqual(set(nested_retrievals), {CONTACT_CAPTURE["retrieved_at"]})
        self.assertEqual(batch["schema"], "nextdc-coordinate-successor-batch-v1")
        self.assertEqual(
            batch["replacement_mode"], "full_source_replacement_not_additive"
        )
        self.assertIn("must never coexist", batch["future_seed_guardrail"])
        replacements = {row["facility_code"]: row for row in batch["replacements"]}
        self.assertEqual(set(replacements), set(SPECS))
        for code, spec in SPECS.items():
            replacement = replacements[code]
            self.assertEqual(
                replacement["predecessor_source_sha256"], spec["v1_sha256"]
            )
            self.assertEqual(
                Path(replacement["successor_source_path"]).name,
                self._filename(spec, "v2"),
            )

        self._assert_capture(
            batch["contact_page_capture"], CONTACT_CAPTURE, header_blocks=2
        )
        evidence_by_key = {row["key"]: row for row in first["evidence"]}
        for page_id, expected in PAGE_CAPTURES.items():
            page_key = batch["location_page_evidence_keys"][page_id]
            regional = evidence_by_key.get(page_key)
            if regional is None:
                for spec in SPECS.values():
                    candidate = self._load(self._path(spec, "v2"))
                    candidate_map = {row["key"]: row for row in candidate["evidence"]}
                    regional = candidate_map.get(page_key)
                    if regional is not None:
                        break
            self.assertIsNotNone(regional)
            assert regional is not None
            self.assertEqual(regional["content_hash"], expected["body"])
            self._assert_capture(regional["metadata"]["capture"], expected)

        document_keys = batch["official_document_evidence_keys"]
        documents = {
            document_id: evidence_by_key[evidence_key]
            for document_id, evidence_key in document_keys.items()
        }
        for document_id, expected in DOCUMENT_CAPTURES.items():
            evidence = documents[document_id]
            self.assertEqual(evidence["content_hash"], expected["body"])
            self._assert_capture(evidence["metadata"]["capture"], expected)
        partner = documents["partner_onboarding_guide"]["metadata"]
        self.assertIsNone(partner["printed_publication_date"])
        self.assertEqual(partner["filename_revision_token"], "240718")
        self.assertIn("not promoted", partner["filename_revision_token_guardrail"])
        self.assertEqual(partner["capture"]["pdf_page_count"], 43)
        iso = documents["iso_9001_qms40018"]["metadata"]
        self.assertEqual(iso["printed_issuing_date"], "2026-07-03")
        self.assertEqual(iso["printed_certification_decision_date"], "2026-07-02")
        self.assertEqual(iso["printed_valid_until"], "2028-05-16")
        esg = documents["fy25_esg_report"]["metadata"]
        self.assertIsNone(esg["printed_publication_date"])
        self.assertEqual(
            esg["printed_reporting_period"],
            {"start": "2024-07-01", "end": "2025-06-30"},
        )

        facilities = batch["facilities"]
        for code, spec in SPECS.items():
            with self.subTest(facility=code):
                facility = facilities[code]
                latitude, longitude = spec["coordinates"]
                self.assertEqual(facility["current_display_address"], spec["address"])
                self.assertEqual(facility["entity_scope"], ["campus", "project"])
                self.assertEqual(
                    facility["coordinate_source_type"],
                    "publisher_supplied_map_link_destination",
                )
                self.assertEqual(facility["snapshot_method"], "authoritative_site_plan")
                self.assertEqual(
                    facility["location_page_evidence_key"],
                    batch["location_page_evidence_keys"][spec["page_id"]],
                )
                self.assertEqual(
                    facility["coordinate_values"],
                    {"latitude": latitude, "longitude": longitude},
                )
                locator = facility["coordinate_source_locator"]
                viewport = re.search(r"@(-?[0-9.]+),(-?[0-9.]+)", locator)
                self.assertIsNotNone(viewport)
                assert viewport is not None
                self.assertNotEqual(
                    (float(viewport.group(1)), float(viewport.group(2))),
                    (latitude, longitude),
                )
                if code == "KL1":
                    self.assertIn(f"!1d{longitude}!2d{latitude}", locator)
                    self.assertIn(
                        "terminal !1d longitude and !2d latitude",
                        facility["coordinate_locator_semantics"],
                    )
                else:
                    self.assertIn(f"!3d{latitude}!4d{longitude}", locator)
                    self.assertIn(
                        "terminal !3d latitude and !4d longitude",
                        facility["coordinate_locator_semantics"],
                    )
                self.assertIn("viewport", facility["coordinate_locator_semantics"])
                self.assertIn("not used", facility["coordinate_locator_semantics"])

        for code in ("B2", "KL1"):
            self.assertEqual(
                facilities[code]["address_discrepancy"]["status"],
                "no_cited_discrepancy",
            )
        for code in ("M2", "P1", "P2"):
            discrepancy = facilities[code]["address_discrepancy"]
            self.assertEqual(
                discrepancy["status"],
                "planner_discovered_official_document_discrepancy",
            )
            self.assertIn("parcel continuity", discrepancy["normalization_guardrail"])
            self.assertIn("relocation", discrepancy["normalization_guardrail"])
            self.assertIn(
                "did not supply this discrepancy", discrepancy["v1_scope_guardrail"]
            )
        self.assertEqual(
            facilities["M2"]["address_discrepancy"]["conflicting_official_documents"][
                0
            ]["displayed_address_lines"],
            ["5 Sharps Road", "Tullamarine, VIC 3043"],
        )
        self.assertEqual(
            facilities["P1"]["address_discrepancy"]["conflicting_official_documents"][
                0
            ]["displayed_address_lines"],
            ["101 Malaga Drive", "Malaga, WA 6090"],
        )
        self.assertEqual(
            facilities["P2"]["address_discrepancy"]["conflicting_official_documents"][
                0
            ]["displayed_address_lines"],
            ["12 Newcastle Street", "Perth, WA 6000"],
        )
        self.assertIn("no point creates", batch["site_count_guardrail"])
        self.assertIn("Source geometry remains null", batch["geometry_guardrail"])
        self.assertIn("No geocoder", batch["imagery_guardrail"])

    def test_v11_time_contract_atomicity_and_legacy_equivalence(self) -> None:
        v1_path = self._path(SPECS["B2"], "v1")
        v2_path = self._path(SPECS["B2"], "v2")
        old_retrieved_at = self._load(v1_path)["evidence"][0]["retrieved_at"]

        with (
            tempfile.TemporaryDirectory() as first_dir,
            tempfile.TemporaryDirectory() as second_dir,
        ):
            first, _ = initialize(Path(first_dir) / "atlas.sqlite")
            second, _ = initialize(Path(second_dir) / "atlas.sqlite")
            try:
                with self._network_guard():
                    legacy_result = CuratedOfficialSourceAdapter().import_file(
                        first, v1_path, retrieved_at=old_retrieved_at
                    )
                    v11_result = CuratedOfficialSourceAdapterV11().import_file(
                        second, v1_path, recorded_at=old_retrieved_at
                    )
                self.assertEqual(v11_result, legacy_result)
                self.assertEqual(self._state(second), self._state(first))
            finally:
                first.close()
                second.close()

        for recorded_at in (
            "2026-07-20T23:15:31Z",
            "2026-07-20T16:15:31-07:00",
        ):
            with (
                self.subTest(recorded_at=recorded_at),
                tempfile.TemporaryDirectory() as directory,
            ):
                connection, _ = initialize(Path(directory) / "atlas.sqlite")
                try:
                    with self._network_guard():
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection, v2_path, recorded_at=recorded_at
                        )
                    self.assertEqual(
                        (result.entities_created, result.evidence_created), (2, 6)
                    )
                    self.assertEqual(validate_database(connection), [])
                finally:
                    connection.close()

        for recorded_at, evidence_index in (
            ("2026-07-20T23:14:00Z", 3),
            ("2026-07-20T23:15:30Z", 5),
        ):
            with (
                self.subTest(recorded_at=recorded_at),
                tempfile.TemporaryDirectory() as directory,
            ):
                connection, _ = initialize(Path(directory) / "atlas.sqlite")
                try:
                    with self.assertRaisesRegex(
                        ValueError,
                        rf"evidence\[{evidence_index}\]\.retrieved_at must not be later than the import recorded_at",
                    ):
                        CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            v2_path,
                            recorded_at=recorded_at,
                        )
                    for table in TABLES:
                        self.assertEqual(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0],
                            0,
                            table,
                        )
                finally:
                    connection.close()

        with tempfile.TemporaryDirectory() as directory:
            connection, _ = initialize(Path(directory) / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError,
                    r"evidence\[0\]\.retrieved_at must equal the import retrieved_at",
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        v1_path,
                        recorded_at="2026-07-19T19:25:07Z",
                    )
            finally:
                connection.close()

    def test_individual_and_full_mixed_batch_are_offline_and_collision_safe(
        self,
    ) -> None:
        v2_names = tuple(self._filename(spec, "v2") for spec in SPECS.values())
        for name in v2_names:
            with self.subTest(source=name):
                temporary, state = self._build((name,), repeat=True)
                try:
                    counts = {table: len(rows) for table, rows in state.items()}
                    self.assertEqual(counts["evidence"], 6)
                    self.assertEqual(counts["entities"], 2)
                    self.assertEqual(counts["entity_snapshots"], 2)
                    self.assertEqual(counts["lifecycle_observations"], 1)
                    self.assertEqual(counts["capacity_estimates"], 1)
                finally:
                    temporary.cleanup()

        unchanged_names = tuple(
            f"curated-official-2026-07-19-nextdc-{token}-1h26-fitout.json"
            for token in UNCHANGED_V1_TOKENS
        )
        names = (*unchanged_names, *v2_names)
        forward_temp, forward = self._build(names, repeat=True)
        reverse_temp, reverse = self._build(reversed(names), repeat=True)
        try:
            self.assertEqual(reverse, forward)
            counts = {table: len(rows) for table, rows in forward.items()}
            self.assertEqual(
                counts,
                {
                    "evidence": 9,
                    "entities": 24,
                    "campuses": 12,
                    "facilities": 0,
                    "buildings": 0,
                    "projects": 12,
                    "entity_snapshots": 24,
                    "administrative_assignments": 0,
                    "lifecycle_observations": 12,
                    "operating_model_observations": 0,
                    "workload_observations": 0,
                    "capacity_estimates": 12,
                },
            )
            snapshots = forward["entity_snapshots"]
            self.assertEqual(sum(row[3] is not None for row in snapshots), 10)
            self.assertEqual(
                sum(row[12] == "authoritative_site_plan" for row in snapshots), 10
            )
            self.assertEqual(
                sum(row[12] == "authoritative_locality" for row in snapshots), 14
            )
        finally:
            forward_temp.cleanup()
            reverse_temp.cleanup()

    def test_database_delta_keeps_pdf_claims_exact_and_advances_snapshots(self) -> None:
        v1_names = tuple(self._filename(spec, "v1") for spec in SPECS.values())
        v2_names = tuple(self._filename(spec, "v2") for spec in SPECS.values())
        v1_temp, v1_state = self._build(v1_names)
        v2_temp, v2_state = self._build(v2_names)
        try:
            for table in ("campuses", "projects"):
                self.assertEqual(v2_state[table], v1_state[table], table)

            recorded_at_indexes = {
                "lifecycle_observations": 6,
                "capacity_estimates": 14,
            }
            for table, recorded_index in recorded_at_indexes.items():
                before = [list(row) for row in v1_state[table]]
                after = [list(row) for row in v2_state[table]]
                for row in before:
                    row[recorded_index] = "<recorded_at>"
                for row in after:
                    row[recorded_index] = "<recorded_at>"
                self.assertEqual(after, before, table)

            v1_entities = {row[2]: row for row in v1_state["entities"]}
            v2_entities = {row[2]: row for row in v2_state["entities"]}
            self.assertEqual(set(v2_entities), set(v1_entities))
            for stable_key, before in v1_entities.items():
                after = v2_entities[stable_key]
                self.assertEqual(after[:3], before[:3])
                self.assertNotEqual(after[3], before[3])
                self.assertEqual(after[4], V11_RECORDED_AT)

            def snapshots(
                state: dict[str, tuple[tuple[Any, ...], ...]],
            ) -> dict[str, tuple[Any, ...]]:
                entities = {row[0]: row[2] for row in state["entities"]}
                return {entities[row[1]]: row for row in state["entity_snapshots"]}

            before_snapshots = snapshots(v1_state)
            after_snapshots = snapshots(v2_state)
            self.assertEqual(set(after_snapshots), set(before_snapshots))
            expected_by_key = {}
            for spec in SPECS.values():
                document = self._load(self._path(spec, "v2"))
                for entity_name in ("campus", "project"):
                    expected_by_key[document[entity_name]["stable_key"]] = spec
            for stable_key, before in before_snapshots.items():
                after = after_snapshots[stable_key]
                spec = expected_by_key[stable_key]
                latitude, longitude = spec["coordinates"]
                self.assertIsNone(before[3])
                self.assertIsNone(before[4])
                self.assertIsNone(before[5])
                self.assertEqual(before[12], "authoritative_locality")
                self.assertEqual(after[3:5], (latitude, longitude))
                self.assertEqual(
                    json.loads(after[5]),
                    {"type": "Point", "coordinates": [longitude, latitude]},
                )
                self.assertEqual(json.loads(after[6])["address"], spec["address"])
                self.assertEqual(after[8], "2026-07-20")
                self.assertEqual(after[12], "authoritative_site_plan")
                self.assertEqual(after[2], before[2])
                self.assertEqual(after[13], before[13])
        finally:
            v1_temp.cleanup()
            v2_temp.cleanup()

    def test_v11_imports_offline_in_both_workspace_layouts(self) -> None:
        source_paths = [str(self._path(spec, "v2")) for spec in SPECS.values()]
        for cwd in (ROOT, WORKSPACE):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database

sources = {source_paths!r}
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for source in sources:
                CuratedOfficialSourceAdapterV11().import_file(
                    connection, source, recorded_at={V11_RECORDED_AT!r}
                )
        assert validate_database(connection) == []
        result = {{
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "coordinates": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE latitude IS NOT NULL").fetchone()[0],
            "site_plan": connection.execute("SELECT COUNT(*) FROM entity_snapshots WHERE method = 'authoritative_site_plan'").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
        }}
        print(json.dumps(result, sort_keys=True))
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
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "capacity": 5,
                        "coordinates": 10,
                        "entities": 10,
                        "evidence": 9,
                        "lifecycle": 5,
                        "site_plan": 10,
                        "snapshots": 10,
                    },
                )


if __name__ == "__main__":
    unittest.main()
