from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import open_seed_v55 as v55
from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v55.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v54.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v54"
BUILDER = ROOT / "scripts/build_open_seed_v55.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "06ec0c788bb2dc83dce159a054af644df04337c60367b72abb64e810ac1571ba"
MANIFEST_SHA256 = "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b"
TREE_SHA256 = "44610a81fab0375255da9824975746ce301591a2b94e099f43f551eb7eb157b4"
BASE_DEFINITION_SHA256 = (
    "1510c2abcf24c90be1de69c11878ad7075a495ddeff53859a7525a4e6c6778a5"
)
BASE_MANIFEST_SHA256 = (
    "ae3d6229d7a78e41d7df1e9d6424a45da3ee9ce41d109d8dee426f557e03db11"
)
BASE_TREE_SHA256 = "6a48e0caf8b2a0d6542005b25cf196d1e96a29b1cb44a37af8a9dde0c18c75d5"
RECORDED_AT = "2026-07-20T20:05:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T20:01:06Z"
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json": (
        "c31ecbe7fb4b8e47de2683c0b321d5dd3e59dda1fbf596218ceab0ef7e191f94"
    ),
    "sources/curated-official-2026-07-20-google-kronstorf-austria.json": (
        "763f11edfea3ce7ff7ec76093716d732a92a906562a3b7f3d17c3b08fa3a4e21"
    ),
}

REJECTED_V1_INPUTS = {
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10.json",
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11.json",
}

ADDITION_POSITIONS = {
    "sources/curated-official-2026-07-20-digital-edge-bgrimm-chonburi-eec.json": 190,
    "sources/curated-official-2026-07-20-google-kronstorf-austria.json": 251,
}

ADDED_ENTITY_KEYS = {
    "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus",
    "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus:current-development",
    "curated:google-kronstorf-austria-data-center-campus",
    "curated:google-kronstorf-austria-data-center-campus:current-development",
}

PUBLISHED_EVIDENCE = {
    "449843d800a5ba175833634054b308369afdae02ea19ead284893f2152e6e7a9": (
        "digital_edge_newsroom"
    ),
    "fa9fb59cdd774842321c98f471f4b6eb70df6ab47dd4d1adb23c63bf062bed08": (
        "google_cloud_press_corner"
    ),
}

EXPECTED_EVIDENCE_IDS = {
    "digital_edge_newsroom": "893ba9e6-ad9d-5647-aea1-407290c48bbf",
    "google_cloud_press_corner": "d34eed88-226a-5311-b8af-c6f04f01ee30",
}

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3_412,
        "1d2ab51a61334bb4603834fe179e070ca03c63408d79bcba2d133f9f56b0f290",
    ),
    "README.md": (
        2_625,
        "8180393d82a111fcba10e94fe5de254b9d5d46e0e397b9c66996de9374fbf58b",
    ),
    "atlas.geojson": (
        2_348_285,
        "4c9b9e3be5af3ad617890b15dedbe805231d58a1bc41bb24f8cc0356d0c6d9c1",
    ),
    "capacity_estimates.csv": (
        227_936,
        "365e09f2ed90a7b2ba60cd5a75942027310ac61eb6b6fc3622ee2609e2095e2c",
    ),
    "construction_pipeline.csv": (
        455_437,
        "a2843ed87812c299ec9654763604115f77fc1e5c33519bf5e41b3f04e44f73c7",
    ),
    "construction_source_signals.csv": (
        276_303,
        "0b7b7cd8cd34b61784e39568b022b7858622fa84afcf51362e5e83f7dda11d1b",
    ),
    "entities.csv": (
        734_105,
        "ad2f7148fbb30a7835d9472b139c3099a97187862c36b80fefbfad73cc2939ee",
    ),
    "evidence.csv": (
        147_576,
        "a8fd8bd16cf423a2f0582a564378cd2b1fd14ee0d2d7d8aea3a2537aa69bb548",
    ),
    "manifest.json": (9_210, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5_874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        222_194,
        "37132d8ee451c6ebadefad43edb733a54c2a63aedf95a043043374d90b56de74",
    ),
    "summary.json": (
        2_864,
        "0ae9e53c6d4b7e13b16be61615fe32a4c243ed2b31c27d5a090b570c38011ea4",
    ),
}

CODE_PINS = {
    ROOT / "datacenter_atlas/curated.py": (
        37_523,
        "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12",
    ),
    ROOT / "datacenter_atlas/epoch.py": (
        36_031,
        "95f5513322aa77dbbece928954214bc931eb883656525f49f091959457735d31",
    ),
    ROOT / "datacenter_atlas/open_seed_release.py": (
        12_373,
        "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab",
    ),
    ROOT / "datacenter_atlas/publication_release.py": (
        3_180,
        "a4d1aec6f0180003cdaea7bcfb89489aa391b888ca12b1ef5c730a3f28bbe510",
    ),
    ROOT / "datacenter_atlas/release.py": (
        27_591,
        "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056",
    ),
    ROOT / "datacenter_atlas/release_contract_v4.py": (
        3_236,
        "7faa3cca20cd724b75e2a574fccdaff21fd4db5073cb8f76683f4a973d821169",
    ),
    ROOT / "datacenter_atlas/open_seed_v54.py": (
        29_058,
        "224e358d88cddd9a761364f09776a0230fa6137952b2126e0b60ba9a5e708cfc",
    ),
    ROOT / "open_seed_v54.py": (
        138,
        "d321a574c82711ff18897e36389e186443c8db734a5e64773418a28abaecee98",
    ),
    ROOT / "scripts/build_open_seed_v54.py": (
        361,
        "b83d6f216d6919e466ffe8400dc8344e15cf182f5e191c794881d6a3357c9202",
    ),
    ROOT / "datacenter_atlas/open_seed_v55.py": (
        24_543,
        "ad094846f230b1a7c0a7aacbff5bd064f6dba441ecc953db088d93cdd47a1d43",
    ),
    ROOT / "open_seed_v55.py": (
        138,
        "a668e9f392a591f23ccbb5ca94f31b8dbf69a2f48e71dca0a0dbab547ad324cb",
    ),
    BUILDER: (
        361,
        "3a99aa85021cbdc2ee88887621dea4eb1694fa789f9705598b047656f5b0e15b",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# Common rows, added count/hash, removed count/hash.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        659,
        4,
        "958b5e1c0bcef84b22113e7bd6d4e2e7e0c492c1acc4e348b1379f7dfaa77c02",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "evidence.csv": (
        381,
        2,
        "6f5eb14ae1b8ce8e19daefbb42306617f4bd0662abbfac0416ad5e4565ae5f37",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "capacity_estimates.csv": (
        482,
        0,
        EMPTY_DELTA_SHA256,
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_pipeline.csv": (
        344,
        2,
        "06a5c0cebcefd4e20587c5fba558c1f825f3b91e4b04deb139bd181bf77dea33",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_source_signals.csv": (
        250,
        2,
        "7f6b8c13ff7fb4efa6fb677275cb43cf6e172206c7d343176cb23ea468919eab",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "resolution_candidates.csv": (
        4,
        0,
        EMPTY_DELTA_SHA256,
        0,
        EMPTY_DELTA_SHA256,
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def row_counter(path: Path) -> Counter[tuple[tuple[str, str], ...]]:
    return Counter(tuple(row.items()) for row in rows(path))


def normalized_counter_rows(
    counter: Counter[tuple[tuple[str, str], ...]],
) -> list[dict[str, str]]:
    result = [dict(packed) for packed in counter.elements()]
    result.sort(
        key=lambda row: json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return result


def canonical_hash(document: object) -> str:
    raw = (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"release contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported release entry: {relative}")
    return digest.hexdigest()


class OpenSeedV55Tests(unittest.TestCase):
    def _validate_offline(self) -> tuple[dict[str, object], int]:
        network_requests = 0
        original_open = Path.open
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text
        seed_pattern = re.compile(r"open-seed-2026-07-20-v(\d+)")
        forbidden_inputs = {
            str((ROOT / relative).resolve()) for relative in REJECTED_V1_INPUTS
        }

        def reject(path: Path) -> None:
            resolved = str(path.resolve())
            match = seed_pattern.search(resolved)
            if match is not None and int(match.group(1)) not in {54, 55}:
                raise AssertionError(f"v55 attempted forbidden seed access: {path}")
            if resolved in forbidden_inputs:
                raise AssertionError(f"v55 attempted rejected v1 input access: {path}")

        def guarded_open(
            path: Path, mode: str = "r", *args: object, **kwargs: object
        ) -> object:
            reject(path)
            return original_open(path, mode, *args, **kwargs)

        def guarded_read_bytes(path: Path) -> bytes:
            reject(path)
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            reject(path)
            return original_read_text(path, *args, **kwargs)

        def blocked(*args: object, **kwargs: object) -> None:
            nonlocal network_requests
            network_requests += 1
            raise AssertionError("v55 validation attempted network access")

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "open", new=guarded_open))
            stack.enter_context(
                patch.object(Path, "read_bytes", new=guarded_read_bytes)
            )
            stack.enter_context(patch.object(Path, "read_text", new=guarded_read_text))
            for name in (
                "socket",
                "create_connection",
                "getaddrinfo",
                "gethostbyname",
                "gethostbyname_ex",
            ):
                stack.enter_context(patch.object(socket, name, side_effect=blocked))
            manifest = validate_open_seed_release(DEFINITION, RELEASE)
        return manifest, network_requests

    def test_temporal_contract_and_birth_times_are_truthful(self) -> None:
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        retrieved = [current["epoch_capture"]["retrieved_at"]]
        for row in current["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))
            retrieved.extend(item["retrieved_at"] for item in document["evidence"])
        cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertEqual(max(retrieved), MAX_SELECTED_RETRIEVED_AT)
        self.assertLess(
            datetime.fromisoformat(MAX_SELECTED_RETRIEVED_AT.replace("Z", "+00:00")),
            cutoff,
        )
        self.assertLessEqual(cutoff, datetime.now(timezone.utc))
        for artifact in (DEFINITION, RELEASE):
            birth_time = getattr(artifact.stat(), "st_birthtime", None)
            if birth_time is not None:
                self.assertLessEqual(cutoff.timestamp(), birth_time, artifact)
        with self.assertRaisesRegex(SystemExit, "at or before the build-start clock"):
            v55.validate_temporal_contract(
                retrieved,
                build_started_at=cutoff - timedelta(microseconds=1),
            )
        v55.validate_temporal_contract(retrieved, build_started_at=cutoff)
        v55.validate_temporal_contract(
            retrieved,
            build_started_at=cutoff + timedelta(days=365_000),
        )

    def test_exact_pins_double_offline_validation_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 67_472)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256)
        self.assertEqual(tree_digest(BASE_RELEASE), BASE_TREE_SHA256)
        for path, (expected_bytes, expected_hash) in CODE_PINS.items():
            self.assertEqual(path.stat().st_size, expected_bytes, path)
            self.assertEqual(sha256(path), expected_hash, path)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        entries = list(RELEASE.iterdir())
        self.assertEqual({path.name for path in entries}, set(RELEASE_FILE_PINS))
        for path in entries:
            expected_bytes, expected_hash = RELEASE_FILE_PINS[path.name]
            self.assertTrue(path.is_file(), path.name)
            self.assertFalse(path.is_symlink(), path.name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path.name)
            self.assertEqual(path.stat().st_size, expected_bytes, path.name)
            self.assertEqual(sha256(path), expected_hash, path.name)
        self.assertEqual(tree_digest(RELEASE), TREE_SHA256)

        frozen = {path.name: path.read_bytes() for path in entries}
        first, first_network = self._validate_offline()
        second, second_network = self._validate_offline()
        self.assertEqual(first_network, 0)
        self.assertEqual(second_network, 0)
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        expected = {
            "publication_contract_version": 4,
            "recorded_at": RECORDED_AT,
            "entities": 663,
            "entities_by_kind": {"campus": 357, "project": 306},
            "evidence_records": 383,
            "capacity_estimates": 482,
            "construction_pipeline_records": 346,
            "construction_source_signals": 252,
            "resolution_candidates": 4,
        }
        for key, value in expected.items():
            self.assertEqual(first[key], value, key)
        self.assertEqual(len(first["source_families"]), 201)

    def test_definition_is_exact_two_input_addition_to_v54_only(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_rows = base["curated_inputs"]
        current_rows = current["curated_inputs"]
        base_pins = {row["path"]: row["sha256"] for row in base_rows}
        pins = {row["path"]: row["sha256"] for row in current_rows}
        self.assertEqual(len(base_rows), 314)
        self.assertEqual(len(current_rows), 316)
        self.assertEqual(set(pins) - set(base_pins), set(ADDED_INPUTS))
        self.assertEqual({path: pins[path] for path in base_pins}, base_pins)
        self.assertEqual({path: pins[path] for path in ADDED_INPUTS}, ADDED_INPUTS)
        self.assertEqual(
            [row for row in current_rows if row["path"] in base_pins], base_rows
        )
        self.assertEqual(
            [row["path"] for row in current_rows],
            sorted(row["path"] for row in current_rows),
        )
        actual_positions = {
            row["path"]: index
            for index, row in enumerate(current_rows)
            if row["path"] in ADDED_INPUTS
        }
        self.assertEqual(actual_positions, ADDITION_POSITIONS)
        self.assertTrue(REJECTED_V1_INPUTS.isdisjoint(pins))
        self.assertEqual(set(v55.REJECTED_PROVISIONAL_INPUTS), REJECTED_V1_INPUTS)
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v55")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(current["scope"], base["scope"])
        self.assertEqual(current["epoch_capture"], base["epoch_capture"])
        self.assertEqual(current["expected_epoch_result"], base["expected_epoch_result"])
        self.assertEqual(v55.BASE_DEFINITION, BASE_DEFINITION)
        self.assertEqual(v55.BASE_RELEASE, BASE_RELEASE)

        implementation = sys.modules[v55.selected_inputs.__module__]
        with (
            patch.object(
                implementation,
                "BASE_DEFINITION",
                ROOT / "sources/open-seed-2026-07-20-v53.json",
            ),
            patch.object(
                implementation,
                "BASE_RELEASE",
                ROOT / "releases/2026-07-20-open-seed-v53",
            ),
            self.assertRaisesRegex(SystemExit, "select exactly accepted v54"),
        ):
            v55.selected_inputs(base)

    def test_csv_delta_is_strictly_additive_and_exact(self) -> None:
        for filename, expected in CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            common = before & after
            added = after - common
            removed = before - common
            common_count, added_count, added_hash, removed_count, removed_hash = (
                expected
            )
            self.assertEqual(sum(common.values()), common_count, filename)
            self.assertEqual(sum(added.values()), added_count, filename)
            self.assertEqual(
                canonical_hash(normalized_counter_rows(added)), added_hash, filename
            )
            self.assertEqual(sum(removed.values()), removed_count, filename)
            self.assertEqual(
                canonical_hash(normalized_counter_rows(removed)), removed_hash, filename
            )

    def test_added_entities_status_roles_and_capacity_are_exact(self) -> None:
        base_entities = row_counter(BASE_RELEASE / "entities.csv")
        added = {
            row["stable_key"]: row
            for row in rows(RELEASE / "entities.csv")
            if tuple(row.items()) not in base_entities
        }
        self.assertEqual(set(added), ADDED_ENTITY_KEYS)
        expected = {
            "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus": (
                "campus",
                "",
                "",
                "B.Grimm Power; Digital Edge",
            ),
            "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus:current-development": (
                "project",
                "under_construction",
                "colocation",
                "B.Grimm Power; Digital Edge",
            ),
            "curated:google-kronstorf-austria-data-center-campus": (
                "campus",
                "",
                "",
                "Google",
            ),
            "curated:google-kronstorf-austria-data-center-campus:current-development": (
                "project",
                "under_construction",
                "",
                "Google",
            ),
        }
        for key, row in added.items():
            kind, status, operating_model, developers = expected[key]
            self.assertEqual(row["entity_kind"], kind, key)
            self.assertEqual(row["status"], status, key)
            self.assertEqual(row["operating_model"], operating_model, key)
            self.assertEqual(json.loads(row["tags_json"])["role:developer"], developers)
            self.assertEqual(row["latitude"], "", key)
            self.assertEqual(row["longitude"], "", key)
            self.assertEqual(row["geometry_json"], "null", key)
            self.assertEqual(row["capacity_estimates_json"], "[]", key)
            self.assertEqual(row["workloads_json"], "[]", key)

        base_pipeline = row_counter(BASE_RELEASE / "construction_pipeline.csv")
        pipeline = {
            row["stable_key"]: row
            for row in rows(RELEASE / "construction_pipeline.csv")
            if tuple(row.items()) not in base_pipeline
        }
        expected_dates = {
            "curated:digital-edge-bgrimm-chonburi-eec-data-center-campus:current-development": (
                "2025-09-04"
            ),
            "curated:google-kronstorf-austria-data-center-campus:current-development": (
                "2026-04-23"
            ),
        }
        self.assertEqual(set(pipeline), set(expected_dates))
        for key, as_of in expected_dates.items():
            self.assertEqual(pipeline[key]["status"], "under_construction", key)
            self.assertEqual(pipeline[key]["status_as_of"], as_of, key)

        self.assertEqual(
            row_counter(BASE_RELEASE / "capacity_estimates.csv"),
            row_counter(RELEASE / "capacity_estimates.csv"),
        )
        signal_delta = row_counter(
            RELEASE / "construction_source_signals.csv"
        ) - row_counter(BASE_RELEASE / "construction_source_signals.csv")
        signals = [dict(packed) for packed in signal_delta.elements()]
        self.assertEqual(len(signals), 2)
        self.assertEqual({row["affected_entity_count"] for row in signals}, {"1"})
        self.assertEqual(
            {row["representative_stable_key"] for row in signals}, set(expected_dates)
        )

    def test_database_and_published_evidence_boundaries_are_exact(self) -> None:
        base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(base_summary["evidence_total"], 452)
        self.assertEqual(summary["evidence_total"], 454)
        self.assertEqual(base_manifest["evidence_records"], 381)
        self.assertEqual(manifest["evidence_records"], 383)

        base_published = row_counter(BASE_RELEASE / "evidence.csv")
        published = [
            row
            for row in rows(RELEASE / "evidence.csv")
            if tuple(row.items()) not in base_published
        ]
        published_by_hash = {
            row["content_hash"]: row["source_family"] for row in published
        }
        self.assertEqual(published_by_hash, PUBLISHED_EVIDENCE)
        self.assertEqual(
            {row["source_family"]: row["evidence_id"] for row in published},
            EXPECTED_EVIDENCE_IDS,
        )

        definition = json.loads(DEFINITION.read_text())
        database_families = {"epoch_ai_data_centers"}
        for row in definition["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text())
            database_families.update(
                item["source_family"] for item in document["evidence"]
            )
        self.assertEqual(len(database_families), 237)
        self.assertEqual(len(base_manifest["source_families"]), 199)
        self.assertEqual(len(manifest["source_families"]), 201)
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            set(PUBLISHED_EVIDENCE.values()),
        )
        self.assertNotIn("source_families", summary)

    def test_summary_scope_parent_container_and_resolution_contracts(self) -> None:
        base = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        expected_deltas = {
            "entities_total": 4,
            "campuses_total": 2,
            "projects_total": 2,
            "evidence_total": 2,
            "lifecycle_observations_current": 2,
            "capacity_estimates_current": 0,
            "construction_pipeline_records": 2,
            "construction_source_signals": 2,
            "entities_with_coordinates": 0,
            "campuses_with_coordinates": 0,
        }
        for key, delta in expected_deltas.items():
            self.assertEqual(summary[key] - base[key], delta, key)
        self.assertEqual(
            summary["entities_by_status"]["under_construction"]
            - base["entities_by_status"]["under_construction"],
            2,
        )
        self.assertEqual(
            summary["capacity_estimates_by_stage"],
            base["capacity_estimates_by_stage"],
        )

        for relative in ADDED_INPUTS:
            document = json.loads((ROOT / relative).read_text())
            metadata = document["evidence"][0]["metadata"]
            self.assertIn("internal parent container", metadata["entity_model_guardrail"])
            self.assertEqual(document["capacities"], [])
            self.assertEqual(document["workloads"], [])
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)
        self.assertIn("not a count of unique physical sites", readme)
        self.assertTrue(
            {"unique_sites", "global_completeness", "semianalysis_parity"}.isdisjoint(
                manifest
            )
        )
        self.assertEqual(
            row_counter(BASE_RELEASE / "resolution_candidates.csv"),
            row_counter(RELEASE / "resolution_candidates.csv"),
        )

    def test_existing_active_lock_and_late_arrival_collisions_are_safe(self) -> None:
        before_definition = DEFINITION.read_bytes()
        before_tree = tree_digest(RELEASE)
        result = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("definition already exists; refusing to overwrite", result.stderr)
        self.assertFalse(v55.PUBLICATION_LOCK.exists())

        descriptor = os.open(
            v55.PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        try:
            os.write(descriptor, b"test-active-lock\n")
            os.close(descriptor)
            descriptor = -1
            locked = subprocess.run(
                [sys.executable, str(BUILDER)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertNotEqual(locked.returncode, 0)
            self.assertIn("active publication lock exists", locked.stderr)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            v55.PUBLICATION_LOCK.unlink(missing_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v55-collision-"
        ) as temporary:
            root = Path(temporary)
            stage = root / "stage"
            destination = root / "destination"
            stage.mkdir()
            destination.mkdir()
            (stage / "stage.txt").write_text("stage\n", encoding="utf-8")
            (destination / "existing.txt").write_text("existing\n", encoding="utf-8")
            with self.assertRaisesRegex(
                SystemExit, "late output collision; refusing overwrite"
            ):
                v55.promote_noreplace(stage, destination)
            self.assertEqual((stage / "stage.txt").read_text(), "stage\n")
            self.assertEqual((destination / "existing.txt").read_text(), "existing\n")
        self.assertEqual(DEFINITION.read_bytes(), before_definition)
        self.assertEqual(tree_digest(RELEASE), before_tree)

    def test_validator_and_import_work_in_both_layouts(self) -> None:
        command = [
            sys.executable,
            str(VALIDATOR),
            "--definition",
            str(DEFINITION),
            "--release",
            str(RELEASE),
        ]
        import_command = [
            sys.executable,
            "-c",
            (
                "from datacenter_atlas.open_seed_v55 import BASE_DEFINITION, RELEASE; "
                "print(BASE_DEFINITION); print(RELEASE)"
            ),
        ]
        for cwd in (WORKSPACE, ROOT):
            environment = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(cwd),
            }
            imported = subprocess.run(
                import_command,
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertEqual(
                imported.stdout.splitlines(), [str(BASE_DEFINITION), str(RELEASE)]
            )
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "offline_rebuild_validate")
            self.assertEqual(payload["network_requests"], 0)
            self.assertEqual(payload["entities"], 663)
            self.assertEqual(payload["evidence_records"], 383)
            self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
