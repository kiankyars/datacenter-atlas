from __future__ import annotations

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

try:
    from datacenter_atlas.datacenter_atlas.curated_v11 import (
        CuratedOfficialSourceAdapterV11,
    )
    from datacenter_atlas.datacenter_atlas.database import initialize
    from datacenter_atlas.datacenter_atlas.service import validate_database
except ModuleNotFoundError:
    from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
    from datacenter_atlas.database import initialize
    from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "authoritative-coordinate-successors-v58-2026-07-20-v1"
)
RECORDED_AT = "2026-07-21T01:14:00Z"

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "verne": {
        "v1": "curated-official-2026-07-20-verne-mantsala-current-development.json",
        "v1_size": 8_739,
        "v1_sha256": "7e993fbb78c72340127b6646ff90fa232595b3eb7d8c3c72c88153550d3e5203",
        "v2": "curated-official-2026-07-20-verne-mantsala-current-development-v2.json",
        "v2_size": 22_497,
        "v2_sha256": "349e9d131a5f708359f062d929c9a762680682b3c23ffe35302e3b4fe653b64a",
        "entity": "campus",
        "changed_fields": {
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
        "coordinates": (60.63527854345244, 25.286117693746803),
        "geometry_type": "Polygon",
        "ring_count": 1,
        "method": "authoritative_site_plan",
        "appended": (
            "mantsala-verne-kapuli-property-bridge-captured-2026-07-20",
            "mantsala-property-505-407-7-137-data-center-decision-captured-2026-07-20",
            "mantsala-property-505-407-7-137-gis-captured-2026-07-20",
        ),
    },
    "penzance": {
        "v1": "curated-official-2026-07-20-penzance-chantilly-premier-current-build.json",
        "v1_size": 10_102,
        "v1_sha256": "b78c30cb8ed322dcdae3ce555c9c8f2e90c5de771184901643b64d2653e7aceb",
        "v2": "curated-official-2026-07-20-penzance-chantilly-premier-current-build-v2.json",
        "v2_size": 28_402,
        "v2_sha256": "4647a868f77c225b797502be216a12a1b977fd1657d8c996f9bc5e56bdb9cf85",
        "entity": "campus",
        "changed_fields": {
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
        "coordinates": (38.90287453965922, -77.46593013343211),
        "geometry_type": "Polygon",
        "ring_count": 1,
        "method": "authoritative_site_plan",
        "appended": (
            "fairfax-pin-0332-01-0006-parcel-report-captured-2026-07-20",
            "fairfax-pin-0332-01-0006-cadastral-geometry-captured-2026-07-20",
        ),
    },
    "t5": {
        "v1": "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build.json",
        "v1_size": 15_090,
        "v1_sha256": "4952c3aa872d8ec99f3b9526270b9cd129fdaf454759904eaea01d854d785dd2",
        "v2": "curated-official-2026-07-20-t5-chicago-iii-northlake-current-build-v2.json",
        "v2_size": 25_582,
        "v2_sha256": "35734efff320ff37e70a2af66f1dd9ddb019178504de3d91f637b9e65778e565",
        "entity": "project",
        "changed_fields": {
            "address",
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
        "coordinates": (41.934299423514098, -87.91569501443621),
        "geometry_type": "Point",
        "ring_count": None,
        "method": "authoritative_address_geocode",
        "address": (
            "11650 West Grand Avenue, Northlake, Illinois 60164, United States"
        ),
        "appended": (
            "illinois-epa-t5-chicago-iii-address-captured-2026-07-20",
            "cook-county-11650-west-grand-address-point-captured-2026-07-20",
        ),
    },
    "cra": {
        "v1": "curated-official-2026-07-20-cra-prague-gateway-first-building.json",
        "v1_size": 9_080,
        "v1_sha256": "ce19862d4e24e5c0c3006e842c9baaf89ea12137eceb2b579e40bcf716c1f64a",
        "v2": "curated-official-2026-07-20-cra-prague-gateway-first-building-v2.json",
        "v2_size": 34_655,
        "v2_sha256": "1b9d43d074e15effa188aca522acabb430e4b78954b99f23e6b53edce415cc2a",
        "entity": "campus",
        "changed_fields": {
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
        "coordinates": (49.948186441032426, 14.36784629256487),
        "geometry_type": "Polygon",
        "ring_count": 16,
        "method": "authoritative_site_plan",
        "appended": (
            "praha16-cra-zbraslav-data-center-parcels-captured-2026-07-20",
            "cuzk-jiloviste-cadastral-code-captured-2026-07-20",
            "cuzk-cra-zbraslav-site-parcels-captured-2026-07-20",
        ),
    },
    "maincubes": {
        "v1": "curated-official-2026-07-20-maincubes-fra03-phase-2.json",
        "v1_size": 15_026,
        "v1_sha256": "ad5013be9eab2b0aad9d43883b3d7d39f297d9d8e7cbb256c4d12fb84179ebee",
        "v2": "curated-official-2026-07-20-maincubes-fra03-phase-2-v2.json",
        "v2_size": 26_883,
        "v2_sha256": "cd6f10953cb892134e61384513821cc12ba5e66ce9a2ae1deb539e6d1a59ba38",
        "entity": "campus",
        "changed_fields": {
            "address",
            "coordinates",
            "geometry",
            "evidence_key",
            "as_of_date",
            "method",
        },
        "coordinates": (50.16092256214182, 8.53631666671276),
        "geometry_type": "Point",
        "ring_count": None,
        "method": "authoritative_address_geocode",
        "address": (
            "Am Kronberger Hang 6, 65824 Schwalbach am Taunus, Germany"
        ),
        "appended": (
            "maincubes-fra03-factsheet-address-captured-2026-07-20",
            "hessen-fra03-official-house-coordinate-captured-2026-07-20",
        ),
    },
}

BLOCKER_SPECS = {
    "Princeton Digital Group MU2": {
        "v1": "curated-official-2026-07-20-pdg-mu2-navi-mumbai-current-development.json",
        "size": 14_642,
        "sha256": "07c7a75bb64188a415ac143d8077939979e68fac6b27cae3ef93de70a9502922",
        "request_id": "pdg_blocker",
    },
    "Jefferson Lab Data Center (JLDC)": {
        "v1": "curated-official-2026-07-20-jefferson-lab-jldc-newport-news.json",
        "size": 9_145,
        "sha256": "ea26383ca36ae92f83141d4877d4bd3c46adb24fbb51c1545e574678267c493d",
        "request_id": "jlab_blocker",
    },
}

CAPTURE_PINS = {
    "verne_article": (
        170_337,
        "09ec3c3de9d883467052751084e26a72da3424e519d1bbfa141c3c98fe3dc063",
        476,
        "346c78f259b3de8e84b4a184286adc439e61ca2499dab4d293092c07f1f7b12c",
        15_923,
        "fdf60e0344fd177fb674d051ec5be1b097ccd952687553eb6d88e4f0eabd7e07",
    ),
    "verne_decision": (
        24_402,
        "3220cdd577a742dc4634bf759208d6cce727775fdbc7543a54fc751da0dfa0e0",
        376,
        "656eebbea78ad36e518973994260c34e80c46b4f478dfde91ff5013114d8e57c",
        19_869,
        "61740fa2b6f0d94cc6c0caa0c143f17ef200bb32ecf8e8e488f65d5545a87776",
    ),
    "verne_gis": (
        796,
        "e9998583917b7bc03bc5e9593968d72f4ceca6b39aa18f10cc5bc5d503ecf291",
        157,
        "0ab618cd1c31f7eb578355291ba34d73e3480168d3eae5a0d157e78b5a4485f0",
        16_668,
        "0250ab59a957e171904790437a3328f4dce34b141cb9301f87b8887922ca0392",
    ),
    "penzance_report": (
        26_396,
        "ff74319441798da756e4800a250090a7a1e879dd99b6288b4b23161a2fb24262",
        1_457,
        "8ad4de1ee73d898e390af417a7adf84b130f49c0201ebda2396ba46984153b05",
        15_119,
        "1b3457e0bc891e2dc532aadb945e8ffeaef993aae4ae406a36abaeb90b8bcb38",
    ),
    "penzance_gis": (
        4_659,
        "1ba2864c8a1d91a02e18c574c1b243441eb3c807ab03546270d68b513c3c2d31",
        1_519,
        "f4beff0e5330e66884f1c25c2b3065c615090ccb43d9d11874ad82c825da043c",
        15_423,
        "1d8b6cabfe142e453e7b7881a024de3c3adb304edaa91f0ceb9beb02052e1779",
    ),
    "t5_epa": (
        416_902,
        "3ab6ef8643ebd5b0b4c33b4889a70b88e8f469c3be119757df37b364bbc22184",
        936,
        "863df28c6864d395d58f76019910eada0861ae59862ae20620bbc208500dc868",
        21_114,
        "7ef984712058f43ff53dab9cf5945a659732c1764d3024180217e73861230174",
    ),
    "t5_gis": (
        72,
        "b7328cec6dd4d8a470d2d71623d77830ee4e4992ed2a0a9345a405c2202f7c67",
        489,
        "49698b453dcb2aae2b43b857b2548eb0849e7c59707853159782fd8d4d7be401",
        13_490,
        "2a2b4d4cdbe707cac5332659b3ba14dcdba40e52075e6d097afbb6a9e13b0674",
    ),
    "t5_gis_exact": (
        1_760,
        "4a7560bc0378f2692100230492fec777fc3e7283fb55909c38a66f1e167cb9a5",
        491,
        "3563b20213c1ee5b799eee0e0454f918b5f52d6e20e4783ca3c702f1dca5ec24",
        13_735,
        "eff1cc0baa6ba53c79b5cf5e6a5166361fef047be4a7b23c27baa8413ae72ffa",
    ),
    "t5_modeling_memo": (
        357_180,
        "dc00236020951c2b9be2996a504190ffb581aa078da974aeb41883d3ef2e9aa1",
        936,
        "9c2bf4f97ccec4386667412e5b2726f6d5efd08bb7ec893652627cefb9a1bbf1",
        21_180,
        "b533152a6ad52f97a878045c0bcc9d1501a8373cbdef268079eb3d38cb121cfe",
    ),
    "cra_permit": (
        206_720,
        "d4fe60f75a119f580d64948d657ecda820515c16cbb5e4fb1b572bc80e15547c",
        259,
        "db27ac18b1fcdb38ede4dd92b0c23eefedf88a811f126e06de79ab70defca685",
        17_335,
        "9096861b86d548f71d38197d74ea118cc268bcfc284fb9899d27388b5fe0c661",
    ),
    "cra_cadastral_unit": (
        383,
        "705afbabc7d6ee4e7f0d20ff0711360e4c46c28a8fbe1b8cec14eda25635190d",
        421,
        "370915c27e87fb9dfc9c996cba7f7bbc5d01b1dbd1620f59a354ce5c0f7f3c72",
        13_177,
        "e889f78e58acb80f696f5e53cb58d0498b61bf38a2e043bf2c256f1a474af3b8",
    ),
    "cra_gis": (
        5_633,
        "b703c6ab6fc7a40b7f46263267bb9323c131233d4271990d29dbd28e74eafe94",
        471,
        "e185fb8e6f1d85819f238e84985b56fc3d9bd7e54864bf6b1f9ae3465adedcf4",
        14_168,
        "1f19a9887971ce5d62040338d6d58e69948b5a7af169f4b8212300bc474806de",
    ),
    "maincubes_factsheet": (
        408_127,
        "0567d2e545d1ff323e6f998f1e374c005d8c3d68faaba9b5f595ff5855e67e85",
        305,
        "9c0003b0b3c67c110b61d179a6fffbad0b07cf30f1c772b8c8e365fd0d736326",
        16_369,
        "f06f09c4997db267475910bd5729a28557645bceca8ff10908ed002bb32f0700",
    ),
    "maincubes_gis": (
        2_175,
        "7199bff9948ce17159b27b026f554ec2de8407172dd53849482cbb43e6dcf915",
        385,
        "d1bba5c1304b0e78ee64e1664d47ce61cab1270743c1e452f3186e9845636d73",
        24_258,
        "bbbc7d8d77571688a5b2ce84d1453956c1f8cc7ca920d937f224e395a8822d45",
    ),
    "pdg_blocker": (
        104_420,
        "fe5934afc79ba59018d61c6e91ae9adfaa48e836d8f79b62ddcd4ebe75673e21",
        327,
        "b67b8852e9f6a5372cd37af970179df11c5d453183fe010dc29c4811ce70479b",
        12_714,
        "7eca60d4849a8eeb160c3fb563a58c39ea484c102d4dfde4f1f439c9b044f477",
    ),
    "jlab_blocker": (
        4_774_866,
        "92db0ed3281a29c2584daab0c1ff67f59a43cdc4d45f1044e56449d303a6cb58",
        742,
        "446dc23d53454e7303459e01a0dc34d564263546caa6f47130eff19d391146aa",
        12_644,
        "5e8da77b0724cbb14e8d237a2c80463696307d67b311f9b996ae72516c640ee9",
    ),
}

TABLES = (
    "evidence",
    "entities",
    "entity_snapshots",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "administrative_assignments",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
)


class AuthoritativeCoordinateSuccessorsV58Tests(unittest.TestCase):
    def _source(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _assert_canonical_file(
        self, path: Path, *, size: int, sha256: str
    ) -> dict[str, Any]:
        self.assertTrue(path.is_file())
        self.assertFalse(path.is_symlink())
        self.assertTrue(stat.S_ISREG(path.stat().st_mode))
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        raw = path.read_bytes()
        self.assertEqual(len(raw), size)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), sha256)
        document = json.loads(raw)
        self.assertEqual(
            raw.decode("utf-8"),
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
        )
        return document

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("authoritative-coordinate import attempted network access")
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
                    (tuple(row) for row in connection.execute(f"SELECT * FROM {table}")),
                    key=repr,
                )
            )
            for table in TABLES
        }

    def _build(
        self, names: tuple[str, ...], *, repeat: bool
    ) -> dict[str, tuple[tuple[Any, ...], ...]]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for name in names:
                        result = CuratedOfficialSourceAdapterV11().import_file(
                            connection,
                            self._source(name),
                            recorded_at=RECORDED_AT,
                        )
                        self.assertEqual(result.entities_created, 2)
                        self.assertEqual(result.warnings, ())
                    state = self._state(connection)
                    if repeat:
                        for name in names:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection,
                                self._source(name),
                                recorded_at=RECORDED_AT,
                            )
                            self.assertEqual(result.entities_created, 0)
                            self.assertEqual(result.evidence_created, 0)
                            self.assertEqual(result.warnings, ())
                        self.assertEqual(self._state(connection), state)
                self.assertEqual(validate_database(connection), [])
                return state
            finally:
                connection.close()

    def _point_in_ring(
        self, longitude: float, latitude: float, ring: list[list[float]]
    ) -> bool:
        inside = False
        previous = ring[-1]
        for current in ring:
            x1, y1 = previous
            x2, y2 = current
            crosses = (y1 > latitude) != (y2 > latitude)
            if crosses:
                crossing_x = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
                if longitude < crossing_x:
                    inside = not inside
            previous = current
        return inside

    def test_hash_pins_canonical_json_exact_delta_and_unseeded_v58(self) -> None:
        for label, spec in SOURCE_SPECS.items():
            with self.subTest(site=label):
                v1 = self._assert_canonical_file(
                    self._source(spec["v1"]),
                    size=spec["v1_size"],
                    sha256=spec["v1_sha256"],
                )
                v2 = self._assert_canonical_file(
                    self._source(spec["v2"]),
                    size=spec["v2_size"],
                    sha256=spec["v2_sha256"],
                )
                self.assertEqual(v1["schema_version"], "1.0")
                self.assertEqual(v2["schema_version"], "1.1")
                self.assertEqual(
                    v2["evidence"][: len(v1["evidence"])], v1["evidence"]
                )
                self.assertEqual(
                    tuple(
                        item["key"] for item in v2["evidence"][len(v1["evidence"]) :]
                    ),
                    spec["appended"],
                )
                for section in (
                    "lifecycle",
                    "operating_models",
                    "workloads",
                    "capacities",
                ):
                    self.assertEqual(v2[section], v1[section], section)

                changed_entity = spec["entity"]
                other_entity = "project" if changed_entity == "campus" else "campus"
                self.assertEqual(v2[other_entity], v1[other_entity])
                actual_changed = {
                    key
                    for key in v1[changed_entity]
                    if v1[changed_entity][key] != v2[changed_entity][key]
                }
                self.assertEqual(actual_changed, spec["changed_fields"])
                latitude, longitude = spec["coordinates"]
                self.assertEqual(
                    v2[changed_entity]["coordinates"],
                    {"latitude": latitude, "longitude": longitude},
                )
                self.assertEqual(
                    v2[changed_entity]["geometry"]["type"], spec["geometry_type"]
                )
                self.assertEqual(v2[changed_entity]["method"], spec["method"])
                self.assertEqual(v2[changed_entity]["as_of_date"], "2026-07-20")
                self.assertEqual(
                    v2[changed_entity]["evidence_key"], spec["appended"][-1]
                )
                if "address" in spec:
                    self.assertEqual(v2[changed_entity]["address"], spec["address"])
                if spec["geometry_type"] == "Point":
                    self.assertEqual(
                        v2[changed_entity]["geometry"]["coordinates"],
                        [longitude, latitude],
                    )
                else:
                    rings = v2[changed_entity]["geometry"]["coordinates"]
                    self.assertEqual(len(rings), spec["ring_count"])
                    self.assertTrue(self._point_in_ring(longitude, latitude, rings[0]))
                    self.assertFalse(
                        any(
                            self._point_in_ring(longitude, latitude, ring)
                            for ring in rings[1:]
                        )
                    )

                restored = copy.deepcopy(v2)
                restored["schema_version"] = "1.0"
                restored["evidence"] = copy.deepcopy(v1["evidence"])
                restored[changed_entity] = copy.deepcopy(v1[changed_entity])
                self.assertEqual(restored, v1)

        for spec in BLOCKER_SPECS.values():
            self._assert_canonical_file(
                self._source(spec["v1"]),
                size=spec["size"],
                sha256=spec["sha256"],
            )

        definition_path = ROOT / "sources/open-seed-2026-07-20-v58.json"
        self.assertEqual(definition_path.stat().st_size, 70_057)
        self.assertEqual(
            hashlib.sha256(definition_path.read_bytes()).hexdigest(),
            "76b9200c892c62a579007f7024a3802019c8b06ad34e0dbbd42e5529fb391a74",
        )
        module_path = ROOT / "datacenter_atlas/open_seed_v58.py"
        self.assertEqual(module_path.stat().st_size, 20_129)
        self.assertEqual(
            hashlib.sha256(module_path.read_bytes()).hexdigest(),
            "63446c7c4474df86589c0a0a03261ef055959ef87a3e91b87bf4992318c24eea",
        )
        selected = {
            item["path"]: item["sha256"]
            for item in self._load(definition_path)["curated_inputs"]
        }
        for spec in (*SOURCE_SPECS.values(), *BLOCKER_SPECS.values()):
            self.assertEqual(selected[f"sources/{spec['v1']}"], spec["v1_sha256"] if "v1_sha256" in spec else spec["sha256"])
            if "v2" in spec:
                self.assertNotIn(f"sources/{spec['v2']}", selected)

    def test_inventory_disposition_capture_pins_and_blockers(self) -> None:
        inventory = self._assert_canonical_file(
            ARTIFACT / "retrieval-inventory.json",
            size=23_781,
            sha256="54fa164e521d7e9fa45b68616515f6c78e813d67c050eae9be5b4b1d6e2abd5c",
        )
        disposition = self._assert_canonical_file(
            ARTIFACT / "disposition.json",
            size=10_735,
            sha256="dce8488ca77b29dad6f3cbae55c75f0e8ebbc46cc53d9ee51eab05b36f53858b",
        )
        self.assertTrue(inventory["analysis_temporary_response_bodies_deleted"])
        self.assertFalse(inventory["response_bodies_redistributed"])
        self.assertEqual(inventory["completed_response_requests"], 16)
        self.assertEqual(inventory["accepted_coordinate_evidence_requests"], 12)
        self.assertEqual(inventory["blocker_evidence_requests"], 2)
        self.assertEqual(inventory["excluded_or_superseded_requests"], 2)
        rows = {
            item["request_id"]: item
            for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(rows), set(CAPTURE_PINS))
        self.assertEqual(len(rows), len(inventory["controlled_http_requests"]))
        for request_id, pins in CAPTURE_PINS.items():
            with self.subTest(request=request_id):
                row = rows[request_id]
                body_size, body_hash, header_size, header_hash, write_size, write_hash = pins
                self.assertEqual(
                    (row["body"]["bytes"], row["body"]["sha256"]),
                    (body_size, body_hash),
                )
                self.assertEqual(
                    (row["headers"]["bytes"], row["headers"]["sha256"]),
                    (header_size, header_hash),
                )
                self.assertEqual(
                    (
                        row["curl_writeout"]["bytes"],
                        row["curl_writeout"]["sha256"],
                    ),
                    (write_size, write_hash),
                )
                self.assertFalse(row["body"]["retained"])
                self.assertFalse(row["headers"]["retained"])
                self.assertFalse(row["curl_writeout"]["retained"])
                self.assertFalse(row["request_credentials_supplied"])
                self.assertFalse(row["request_cookie_input_supplied"])
                self.assertFalse(row["response_cookies_persisted_or_reused"])

        self.assertEqual(
            rows["t5_gis"]["application_error"],
            {"code": 400, "message": "Failed to execute query.", "details": []},
        )
        self.assertEqual(rows["t5_gis"]["disposition"], "invalid_query_excluded")
        self.assertEqual(
            rows["t5_epa"]["disposition"], "superseded_text_source_excluded"
        )

        evidence: dict[str, dict[str, Any]] = {}
        for spec in SOURCE_SPECS.values():
            v1 = self._load(self._source(spec["v1"]))
            v2 = self._load(self._source(spec["v2"]))
            for item in v2["evidence"][len(v1["evidence"]) :]:
                self.assertNotIn(item["key"], evidence)
                evidence[item["key"]] = item
        accepted = {
            item["evidence_key"]: item
            for item in rows.values()
            if item["review_role"] == "coordinate_evidence"
        }
        self.assertEqual(set(evidence), set(accepted))
        for key, row in accepted.items():
            item = evidence[key]
            metadata = item["metadata"]
            self.assertEqual(item["content_hash"], row["body"]["sha256"])
            self.assertEqual(item["retrieved_at"], row["retrieved_at"])
            self.assertEqual(
                metadata["capture_headers_sha256"], row["headers"]["sha256"]
            )
            self.assertEqual(
                metadata["capture_curl_writeout_sha256"],
                row["curl_writeout"]["sha256"],
            )
            self.assertEqual(metadata["capture_completed_at"], row["retrieved_at"])
            self.assertEqual(
                metadata["content_hash_verification"], "fetched_bytes_sha256"
            )

        self.assertEqual(disposition["integration_status"], "standalone_unseeded")
        self.assertEqual(
            disposition["summary"],
            {
                "reviewed_sites": 7,
                "coordinate_successors": 5,
                "evidence_backed_blockers": 2,
            },
        )
        sites = {item["site"]: item for item in disposition["sites"]}
        self.assertEqual(len(sites), 7)
        for spec in SOURCE_SPECS.values():
            item = next(
                row
                for row in sites.values()
                if row["predecessor"]["path"] == f"sources/{spec['v1']}"
            )
            self.assertEqual(item["disposition"], "coordinate_successor")
            self.assertEqual(item["successor"]["path"], f"sources/{spec['v2']}")
            self.assertEqual(item["successor"]["bytes"], spec["v2_size"])
            self.assertEqual(item["successor"]["sha256"], spec["v2_sha256"])
            self.assertEqual(tuple(item["appended_evidence_keys"]), spec["appended"])

        for site, spec in BLOCKER_SPECS.items():
            item = sites[site]
            self.assertEqual(item["disposition"], "blocked_no_authoritative_coordinate")
            self.assertIsNone(item["successor"])
            self.assertEqual(item["blocker_evidence"]["request_id"], spec["request_id"])
            predecessor = self._load(self._source(spec["v1"]))
            for entity in (predecessor["campus"], predecessor["project"]):
                self.assertIsNone(entity["coordinates"])
                self.assertIsNone(entity["geometry"])
                self.assertEqual(entity["method"], "authoritative_locality")
            blocked_v2 = self._source(spec["v1"].removesuffix(".json") + "-v2.json")
            self.assertFalse(blocked_v2.exists())

        self.assertIn("CSS marker", sites["Princeton Digital Group MU2"]["forbidden_inference"])
        self.assertIn("different facility", sites["Princeton Digital Group MU2"]["forbidden_inference"])
        self.assertIn("raster-only", sites["Jefferson Lab Data Center (JLDC)"]["blocker_reason"])
        self.assertIn("geolocating", sites["Jefferson Lab Data Center (JLDC)"]["forbidden_inference"])

        forbidden_keys = {
            "authorization",
            "certs",
            "conn_id",
            "local_ip",
            "local_port",
            "proxy_ssl_verify_result",
            "remote_ip",
            "remote_port",
            "set-cookie",
            "ssl_verify_result",
        }

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for nested in value.values():
                    visit(nested)
            elif isinstance(value, list):
                for nested in value:
                    visit(nested)

        visit(inventory)

    def test_coordinate_scope_and_geometry_derivations_are_explicit(self) -> None:
        documents = {
            label: self._load(self._source(spec["v2"]))
            for label, spec in SOURCE_SPECS.items()
        }
        verne = {item["key"]: item for item in documents["verne"]["evidence"]}
        verne_meta = verne[
            "mantsala-property-505-407-7-137-gis-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(verne_meta["returned_property_id"], "505-407-7-137")
        self.assertEqual(verne_meta["returned_feature_count"], 1)
        self.assertIn("campus parcel boundary", verne_meta["geometry_scope"])
        self.assertIn("project snapshot remains", verne_meta["subset_guardrail"])

        penzance = {
            item["key"]: item for item in documents["penzance"]["evidence"]
        }
        penzance_meta = penzance[
            "fairfax-pin-0332-01-0006-cadastral-geometry-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(penzance_meta["returned_parcel_key"], 336317)
        self.assertEqual(penzance_meta["returned_position_count"], 102)
        self.assertIn("parent parcel", penzance_meta["geometry_scope"])
        self.assertIn("project snapshot remains", penzance_meta["subset_guardrail"])

        t5 = {item["key"]: item for item in documents["t5"]["evidence"]}
        t5_meta = t5[
            "cook-county-11650-west-grand-address-point-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(t5_meta["returned_feature_count"], 1)
        self.assertEqual(t5_meta["returned_object_id"], 416552)
        self.assertEqual(
            t5_meta["returned_geometry_decimal_text"],
            {"x": "-87.91569501443621", "y": "41.934299423514098"},
        )
        self.assertIn("not a parcel boundary", t5_meta["coordinate_scope"])

        cra = {item["key"]: item for item in documents["cra"]["evidence"]}
        cra_meta = cra[
            "cuzk-cra-zbraslav-site-parcels-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(cra_meta["returned_feature_count"], 2)
        self.assertEqual(
            [
                (
                    item["id"],
                    item["parcel_number"],
                    item["raw_geometry_sha256"],
                )
                for item in cra_meta["returned_features"]
            ],
            [
                (
                    1318883210,
                    "505/2",
                    "7400f9f4adb7230366388564e7c05ff67a17a3fe78ae0323589951c39f3c8873",
                ),
                (
                    1317935210,
                    "379",
                    "da48e64d91143c005423de9b2a9d212fed3c01d38c2ecef80f65d71e689f140e",
                ),
            ],
        )
        self.assertEqual(cra_meta["derived_geometry_type"], "Polygon")
        self.assertEqual(cra_meta["derived_geometry_ring_count"], 16)
        self.assertEqual(
            cra_meta["derived_geometry_sha256"],
            "ff55350fd07afd91c5e8005f18beb3741152a5e2192f33421004109c39895397",
        )
        self.assertIn("topological union", cra_meta["geometry_scope"].lower())
        self.assertIn("no interpolation", cra_meta["geometry_derivation"].lower())

        maincubes = {
            item["key"]: item for item in documents["maincubes"]["evidence"]
        }
        maincubes_meta = maincubes[
            "hessen-fra03-official-house-coordinate-captured-2026-07-20"
        ]["metadata"]
        self.assertEqual(maincubes_meta["returned_feature_count"], 1)
        self.assertEqual(
            maincubes_meta["returned_house_coordinate_id"], "DEHE06200000jqqY"
        )
        self.assertEqual(maincubes_meta["returned_quality_code"], "A")
        self.assertEqual(
            maincubes_meta["returned_native_point"],
            {"easting": 466880.289239, "northing": 5556625.962855},
        )
        self.assertIn("always_xy=True", maincubes_meta["transformation"])
        self.assertIn("not a parcel boundary", maincubes_meta["geometry_scope"])

        for label, document in documents.items():
            spec = SOURCE_SPECS[label]
            for key in spec["appended"]:
                metadata = next(
                    item["metadata"]
                    for item in document["evidence"]
                    if item["key"] == key
                )
                self.assertIn("request_metadata_guardrail", metadata)
                self.assertIn(
                    "No credentials", metadata["request_metadata_guardrail"]
                )

    def test_offline_import_is_valid_idempotent_and_order_invariant(self) -> None:
        names = tuple(spec["v2"] for spec in SOURCE_SPECS.values())
        forward = self._build(names, repeat=True)
        reverse = self._build(tuple(reversed(names)), repeat=False)
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward["campuses"]), 5)
        self.assertEqual(len(forward["projects"]), 5)

    def test_imports_from_workspace_and_package_roots(self) -> None:
        names = tuple(spec["v2"] for spec in SOURCE_SPECS.values())
        script = f"""
from pathlib import Path
from tempfile import TemporaryDirectory
from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database
root = Path({str(ROOT)!r})
names = {names!r}
with TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    for name in names:
        CuratedOfficialSourceAdapterV11().import_file(
            connection,
            root / "sources" / name,
            recorded_at={RECORDED_AT!r},
        )
    assert validate_database(connection) == []
    connection.close()
print("ok")
"""
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        for cwd in (WORKSPACE, ROOT):
            with self.subTest(cwd=cwd):
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
