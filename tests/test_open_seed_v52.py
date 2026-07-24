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

from datacenter_atlas import open_seed_v52 as v52
from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v52.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v52"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v51.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v51"
BUILDER = ROOT / "scripts/build_open_seed_v52.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "95dcf883c9a9b8d37ad50e30f01668303d0ea55bc7199d7dcf827d2daea7a75f"
MANIFEST_SHA256 = "c4e7edee4fbd37959f5c9eb080c416aa9ec3e2489e231795bd85f52a60be27cb"
BASE_DEFINITION_SHA256 = (
    "eca98402dfcb5e7c2c9b9a16093dcf852d20afa932d047966e3409c07d1d3837"
)
BASE_MANIFEST_SHA256 = (
    "c0534405a668df93a783e7d7bdd4cb4f18898879892f559a0dfee914ea081235"
)
RECORDED_AT = "2026-07-20T18:11:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T17:35:25Z"
TREE_SHA256 = "ae5df8cf0d9d6367db58ced1e1d66a66fe7b1b4e3caef05706248d8a286efed5"
BASE_TREE_SHA256 = "7ad5386590b7a8d76f4732a8020bea4c55df0ba6847fa96987a3f12f2e014a8f"
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-greensquaredc-syd1-stage2.json": (
        "7e5628efb8beae2a3e43c015800dfe37d4ea74f2a58e4b227e0b23c2e83adfa4"
    ),
    "sources/curated-official-2026-07-20-iron-mountain-mum3-navi-mumbai.json": (
        "6913bff64fb893a8377ad384936a8873f1d886b1654590ac62d8b7f7130e3080"
    ),
    "sources/curated-official-2026-07-20-bell-ai-fabric-saskatchewan.json": (
        "212173178a5b04e1299ef62bd8de0aabac6cdcdb84132fb53d06ba6bb2994a39"
    ),
    "sources/curated-official-2026-07-20-trg-hou2-spring-texas.json": (
        "1689c544d726d8eb9c1e21602c8b3e8a20209c7e5650b84e589ad604a4bff60d"
    ),
    "sources/curated-official-2026-07-20-related-digital-cheyenne-phase1.json": (
        "5889a849ed963fd59b944d2c2da0bfa0d8920eaf76489a0c6f8f68f7c25119c2"
    ),
}

FORBIDDEN_SEED_MARKERS = tuple(
    marker.encode("ascii")
    for version in (45, 46, 48, 50)
    for marker in (
        f"open-seed-2026-07-20-v{version}",
        f"2026-07-20-open-seed-v{version}",
    )
)

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3_306,
        "21fe4b55998a9578aa4a3c60d16e64d53356bc6ba16bcbc19a61e75a29988974",
    ),
    "README.md": (
        2_625,
        "80f7e958331725e5eba96baec6c5bfca27879e284d533dd6c842360e7b4bf707",
    ),
    "atlas.geojson": (
        2_297_271,
        "f760e10edd60612f88d07371fed7f724e1502cd203fa9a8e525a7d958107b98d",
    ),
    "capacity_estimates.csv": (
        225_231,
        "49fe125c54528484ca095b580a1f8fa6eeeabd862d4c9db72d062905b44ffd03",
    ),
    "construction_pipeline.csv": (
        445_522,
        "466c0425b85b9b9ab11a9fdc88034f6e91b371eaf6bffa11f8017aeb8b87fbd4",
    ),
    "construction_source_signals.csv": (
        267_975,
        "b473ba770b3b436f1372e2098230d9981cbab766a615c596cd7e073821893603",
    ),
    "entities.csv": (
        720_503,
        "9672e2dd13e51717beb3bb26f1b7f4acc02a7180f5eea1e3ae6eaaf835e96cd8",
    ),
    "evidence.csv": (
        142_251,
        "20fc040be6cea43e13db9010967b866ef5df248bde4b8ff101250cee26f00ee3",
    ),
    "manifest.json": (8_835, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5_874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        212_130,
        "6506aa8601ae5b50a492157cc678571ed6b5366459040da34d021749a8ec5676",
    ),
    "summary.json": (
        2_807,
        "178e45786335dc577226b010488b3140ce911bfa382cfcaa7605dada49e7bd3f",
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
    ROOT / "datacenter_atlas/open_seed_v51.py": (
        18_105,
        "c40289be2a7a74e7989caa2de23c4698e4fc9de39c180070ef6db892686f6946",
    ),
    ROOT / "open_seed_v51.py": (
        138,
        "1850950c5867adcea1032d4b580739d8e4e92ad799fb7767f7b6b774fbc632c1",
    ),
    ROOT / "scripts/build_open_seed_v51.py": (
        422,
        "fa71541e48abcac39adbab0fb31faad14d5edcb13f75e6d4bb1848681fe5afa1",
    ),
    ROOT / "datacenter_atlas/open_seed_v52.py": (
        22_999,
        "01a706fb8c8137b703a901082d0a90046ee3db08f867a83d9a6c423c2aaeed46",
    ),
    ROOT / "open_seed_v52.py": (
        138,
        "59e24fb4b7b0c9186bd28e83d1e8c572dedd45583ef27a45821fdd44149212c0",
    ),
    BUILDER: (
        422,
        "ec5a1cbbad092203b1420193ee41cadedef9c6189e176b9e7fc7949b1a7765e4",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# Common rows, added count/hash, removed count/hash.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        637,
        10,
        "9344a0757d5b00ab6fc1f9271016e1d1f07fd1c494198448f2f28e8e8e29be48",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "evidence.csv": (
        359,
        10,
        "6e73c6591d48880ea0ba05ab6fdf126f27d8c27bd120e7ccd983f7a30834fbf7",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "capacity_estimates.csv": (
        470,
        6,
        "a6c6daebd32908e4c418aff21f2a847c6652b409d09bbe4897f38966ffe1e29d",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_pipeline.csv": (
        331,
        5,
        "d14e3a314150315e44bfeca3673259196e13e875a60abcd0414bb9fc85b841fd",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_source_signals.csv": (
        239,
        5,
        "cf78dacd7ffecb7a8760daf59f5e21643451adbb1c71f00e8b1fba09335097f0",
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

PUBLISHED_EVIDENCE = {
    "20ffb381c37bb904cde57ebf6064ce6f99d180c5fccd1a3ad2c0c054e2bafa2b": (
        "greensquaredc_official_website_archived"
    ),
    "ca42835bbaef09a7cf254acc7954a357d159271a017f329243a96fba6edca389": (
        "greensquaredc_official_website"
    ),
    "5864de217fc954c10498ada7c05978ea634077106de20aae26c5bebb02ded605": (
        "trg_datacenters_official_brochures"
    ),
    "1f229bdfebfece69bb0626bb4df418e6e02e2c53ad4d2a9cab59fd68aaae5e87": (
        "bell_bce_newsroom"
    ),
    "25716e7dbac99c92446fe7661287e4671167005531a706cbfd317b3dc85e1549": (
        "bell_bce_newsroom"
    ),
    "4da8478aaa8f5475b4580b8eb92b82fc9e385baf52661453a6f779a37a500b82": (
        "bell_ai_fabric_community_pages"
    ),
    "5820ea8c115906490a0d3b857d700545b38d366777e366b0475657b18dc613b0": (
        "iron_mountain_data_centers_official_linkedin"
    ),
    "0d787499cd5eed7e585d745c4cdeed3bd01ca5dbb168871dd26f461e92fb26be": (
        "iron_mountain_data_centers_official_website"
    ),
    "96662e2e42875d37ee182665b40e0b54ac086365fb2eb2633b5a8e1cf5105783": (
        "related_digital_project_pages"
    ),
    "2678b4f72cdb3000d6b3f6237c2b68c27e246fa1f7ceb0e6a40c2ccc961c6a71": (
        "clayco_official_project_pages"
    ),
}

UNPUBLISHED_EVIDENCE = {
    "greensquaredc-syd1-locations-current-captured-2026-07-20": (
        "04e23f5146172d4bbc3e6a1aaa29e2081f8a20e539b6e26ad5b4c30c4ce2ee35",
        "greensquaredc_official_website",
    ),
    "related-digital-cheyenne-news-index-2026-06-14-captured-2026-07-20": (
        "1938c6f5c3c6e5c6b18ffbeebd543ccacbe6b6e8f78149a5a6c857ae1eb77b6a",
        "related_digital_news_index",
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


class OpenSeedV52Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        blocked = AssertionError("v52 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text
        seed_pattern = re.compile(r"open-seed-2026-07-20-v(\d+)")

        def forbidden(path: Path) -> bool:
            match = seed_pattern.search(path.resolve().as_posix())
            return match is not None and int(match.group(1)) not in {51, 52}

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v52 attempted forbidden seed access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if forbidden(path):
                raise AssertionError(f"v52 attempted forbidden seed access: {path}")
            return original_read_text(path, *args, **kwargs)

        with ExitStack() as stack:
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
            return validate_open_seed_release(DEFINITION, RELEASE)

    def test_recorded_at_and_artifact_birth_times_are_truthful(self) -> None:
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
            v52.validate_temporal_contract(
                retrieved,
                build_started_at=cutoff - timedelta(microseconds=1),
            )
        v52.validate_temporal_contract(retrieved, build_started_at=cutoff)
        v52.validate_temporal_contract(
            retrieved,
            build_started_at=cutoff + timedelta(days=365_000),
        )

    def test_exact_pins_double_offline_rebuild_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 64_767)
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
        first = self._validate_offline()
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        expected = {
            "publication_contract_version": 4,
            "recorded_at": RECORDED_AT,
            "entities": 647,
            "entities_by_kind": {"campus": 349, "project": 298},
            "evidence_records": 369,
            "capacity_estimates": 476,
            "construction_pipeline_records": 336,
            "construction_source_signals": 244,
            "resolution_candidates": 4,
        }
        for key, value in expected.items():
            self.assertEqual(first[key], value, key)

    def test_definition_is_exact_sorted_five_input_addition_to_v51_only(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_rows = base["curated_inputs"]
        current_rows = current["curated_inputs"]
        base_pins = {row["path"]: row["sha256"] for row in base_rows}
        pins = {row["path"]: row["sha256"] for row in current_rows}
        self.assertEqual(len(base_rows), 301)
        self.assertEqual(len(base_pins), 301)
        self.assertEqual(len(current_rows), 306)
        self.assertEqual(len(pins), 306)
        self.assertEqual(set(base_pins) - set(pins), set())
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
        self.assertEqual(
            [
                index
                for index, row in enumerate(current_rows)
                if row["path"] in ADDED_INPUTS
            ],
            [170, 247, 258, 284, 294],
        )
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v52")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(v52.BASE_DEFINITION, BASE_DEFINITION)
        self.assertEqual(v52.BASE_RELEASE, BASE_RELEASE)

        payloads = [
            DEFINITION.read_bytes(),
            *(path.read_bytes() for path in RELEASE.iterdir()),
        ]
        for marker in FORBIDDEN_SEED_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

        implementation = sys.modules[v52.selected_inputs.__module__]
        for version in (45, 46, 48, 49, 50):
            with (
                patch.object(
                    implementation,
                    "BASE_DEFINITION",
                    ROOT / f"sources/open-seed-2026-07-20-v{version}.json",
                ),
                patch.object(
                    implementation,
                    "BASE_RELEASE",
                    ROOT / f"releases/2026-07-20-open-seed-v{version}",
                ),
                self.assertRaisesRegex(SystemExit, "select exactly accepted v51"),
            ):
                v52.selected_inputs(base)

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

    def test_added_identity_status_roles_and_capacity_boundaries(self) -> None:
        all_entities = rows(RELEASE / "entities.csv")
        base_entities = row_counter(BASE_RELEASE / "entities.csv")
        added_entities = {
            row["stable_key"]: row
            for row in all_entities
            if tuple(row.items()) not in base_entities
        }
        expected_roles = {
            "curated:greensquaredc-syd1-norwest-campus": {},
            "curated:greensquaredc-syd1-norwest-campus:stage-2": {},
            "curated:iron-mountain-navi-mumbai-campus": {},
            "curated:iron-mountain-navi-mumbai-campus:mum-3": {},
            "curated:bell-ai-fabric-sherwood-campus": {"role:utility": "SaskPower"},
            "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility": {
                "role:contractor": "Bird Construction Inc.",
                "role:customer": "Cerebras; CoreWeave",
            },
            "curated:trg-spring-cypress-campus": {"role:owner": "TRG Datacenters"},
            "curated:trg-spring-cypress-campus:hou2": {},
            "curated:related-digital-cheyenne-campus": {
                "role:developer": "Related Digital"
            },
            "curated:related-digital-cheyenne-campus:phase-1": {
                "role:contractor": "Clayco",
                "role:tenant": "CoreWeave",
            },
        }
        self.assertEqual(set(added_entities), set(expected_roles))
        for key, expected in expected_roles.items():
            row = added_entities[key]
            tags = json.loads(row["tags_json"])
            roles = {
                name: value for name, value in tags.items() if name.startswith("role:")
            }
            self.assertEqual(roles, expected, key)
            self.assertEqual(row["geometry_json"], "null", key)
            self.assertEqual(row["latitude"], "", key)
            self.assertEqual(row["longitude"], "", key)
            self.assertEqual(row["operating_model"], "", key)
            self.assertEqual(row["workloads_json"], "[]", key)

        pipeline = {
            row["stable_key"]: row
            for row in rows(RELEASE / "construction_pipeline.csv")
            if row["stable_key"] in expected_roles
        }
        expected_pipeline = {
            "curated:greensquaredc-syd1-norwest-campus": "2026-01-14",
            "curated:iron-mountain-navi-mumbai-campus:mum-3": "2026-01-20",
            "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility": (
                "2026-04-21"
            ),
            "curated:trg-spring-cypress-campus:hou2": "2026-07-20",
            "curated:related-digital-cheyenne-campus:phase-1": "2026-07-20",
        }
        self.assertEqual(set(pipeline), set(expected_pipeline))
        for key, as_of in expected_pipeline.items():
            self.assertEqual(pipeline[key]["status"], "under_construction", key)
            self.assertEqual(pipeline[key]["status_as_of"], as_of, key)
            self.assertEqual(pipeline[key]["operating_model"], "", key)
            self.assertEqual(pipeline[key]["workloads_json"], "[]", key)
        self.assertEqual(
            added_entities["curated:greensquaredc-syd1-norwest-campus:stage-2"][
                "status"
            ],
            "",
        )

        base_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        added_capacity = [
            row
            for row in rows(RELEASE / "capacity_estimates.csv")
            if tuple(row.items()) not in base_capacity
        ]
        entity_by_id = {row["entity_id"]: row for row in all_entities}
        observed = {
            (
                entity_by_id[row["entity_id"]]["stable_key"],
                row["metric"],
                row["stage"],
                row["base"],
                row["as_of_date"],
            ): row
            for row in added_capacity
        }
        expected_capacity = {
            (
                "curated:greensquaredc-syd1-norwest-campus:stage-2",
                "critical_it_mw",
                "planned",
                "96.0",
                "2025-11-26",
            ),
            (
                "curated:iron-mountain-navi-mumbai-campus:mum-3",
                "critical_it_mw",
                "planned",
                "85.0",
                "2026-01-20",
            ),
            (
                "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility",
                "gross_facility_mw",
                "planned",
                "300.0",
                "2026-07-20",
            ),
            (
                "curated:trg-spring-cypress-campus",
                "grid_connection_mw",
                "planned",
                "30.0",
                "2026-07-20",
            ),
            (
                "curated:trg-spring-cypress-campus:hou2",
                "grid_connection_mw",
                "planned",
                "24.0",
                "2026-07-20",
            ),
            (
                "curated:related-digital-cheyenne-campus:phase-1",
                "critical_it_mw",
                "planned",
                "88.0",
                "2026-07-20",
            ),
        }
        self.assertEqual(set(observed), expected_capacity)
        self.assertIn(
            "upper-bound",
            observed[
                (
                    "curated:bell-ai-fabric-sherwood-campus:saskatchewan-facility",
                    "gross_facility_mw",
                    "planned",
                    "300.0",
                    "2026-07-20",
                )
            ]["notes"],
        )
        self.assertIn(
            "nested within and non-additive",
            observed[
                (
                    "curated:trg-spring-cypress-campus:hou2",
                    "grid_connection_mw",
                    "planned",
                    "24.0",
                    "2026-07-20",
                )
            ]["notes"],
        )
        self.assertTrue(
            {
                "100.0",
                "110.0",
                "15.0",
                "429.0",
                "90.0",
                "12.0",
                "105.0",
                "420.0",
                "302.0",
            }.isdisjoint(row["base"] for row in added_capacity)
        )
        self.assertFalse(
            any(
                row["metric"] in {"annual_energy_mwh", "generation_nameplate_mw", "pue"}
                for row in added_capacity
            )
        )

    def test_database_and_release_evidence_scopes_remain_distinct(self) -> None:
        base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(base_summary["evidence_total"], 423)
        self.assertEqual(summary["evidence_total"], 435)
        self.assertEqual(base_manifest["evidence_records"], 359)
        self.assertEqual(manifest["evidence_records"], 369)

        input_evidence: dict[str, dict[str, object]] = {}
        input_families: set[str] = set()
        base_input_families: set[str] = set()
        base = json.loads(BASE_DEFINITION.read_text())
        current = json.loads(DEFINITION.read_text())
        for row in base["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text())
            base_input_families.update(
                item["source_family"] for item in document["evidence"]
            )
        for path in ADDED_INPUTS:
            document = json.loads((ROOT / path).read_text())
            non_evidence_payload = dict(document)
            non_evidence_payload.pop("evidence")
            normalized_references = json.dumps(non_evidence_payload, sort_keys=True)
            for item in document["evidence"]:
                self.assertNotIn(item["key"], input_evidence)
                input_evidence[item["key"]] = item
                input_families.add(item["source_family"])
            for key in UNPUBLISHED_EVIDENCE:
                if key in {item["key"] for item in document["evidence"]}:
                    self.assertNotIn(key, normalized_references)
        self.assertEqual(len(input_evidence), 12)
        self.assertEqual(len(input_families), 10)
        self.assertEqual(len(base_input_families | {"epoch_ai_data_centers"}), 211)
        all_input_families = set(base_input_families)
        for row in current["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text())
            all_input_families.update(
                item["source_family"] for item in document["evidence"]
            )
        all_input_families.add("epoch_ai_data_centers")
        self.assertEqual(len(all_input_families), 221)

        published_rows = rows(RELEASE / "evidence.csv")
        base_published = row_counter(BASE_RELEASE / "evidence.csv")
        added_published = [
            row for row in published_rows if tuple(row.items()) not in base_published
        ]
        published_by_hash = {
            row["content_hash"]: row["source_family"] for row in added_published
        }
        self.assertEqual(published_by_hash, PUBLISHED_EVIDENCE)
        for key, (content_hash, family) in UNPUBLISHED_EVIDENCE.items():
            self.assertEqual(input_evidence[key]["content_hash"], content_hash)
            self.assertEqual(input_evidence[key]["source_family"], family)
            self.assertNotIn(content_hash, published_by_hash)

        base_release_families = set(base_manifest["source_families"])
        release_families = set(manifest["source_families"])
        expected_added_release_families = set(PUBLISHED_EVIDENCE.values())
        self.assertEqual(len(base_release_families), 181)
        self.assertEqual(len(release_families), 190)
        self.assertEqual(
            release_families - base_release_families,
            expected_added_release_families,
        )
        self.assertNotIn("related_digital_news_index", release_families)
        self.assertIn("greensquaredc_official_website", release_families)
        self.assertNotIn("source_families", summary)
        self.assertNotIn(191, {len(all_input_families), len(release_families)})

    def test_summary_and_scope_contracts_are_exact(self) -> None:
        base = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        expected_deltas = {
            "entities_total": 10,
            "campuses_total": 5,
            "projects_total": 5,
            "evidence_total": 12,
            "lifecycle_observations_current": 5,
            "capacity_estimates_current": 6,
            "construction_pipeline_records": 5,
            "construction_source_signals": 5,
            "entities_with_coordinates": 0,
            "campuses_with_coordinates": 0,
        }
        for key, delta in expected_deltas.items():
            self.assertEqual(summary[key] - base[key], delta, key)
        self.assertEqual(
            summary["capacity_estimates_by_stage"]["planned"]
            - base["capacity_estimates_by_stage"]["planned"],
            6,
        )
        self.assertEqual(
            summary["entities_by_status"]["under_construction"]
            - base["entities_by_status"]["under_construction"],
            5,
        )
        for status, count in base["entities_by_status"].items():
            if status != "under_construction":
                self.assertEqual(summary["entities_by_status"][status], count, status)
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
        self.assertFalse(v52.PUBLICATION_LOCK.exists())

        descriptor = os.open(
            v52.PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
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
            v52.PUBLICATION_LOCK.unlink(missing_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v52-collision-"
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
                v52.promote_noreplace(stage, destination)
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
                "from datacenter_atlas.open_seed_v52 import BASE_DEFINITION, RELEASE; "
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
            self.assertEqual(payload["entities"], 647)
            self.assertEqual(payload["evidence_records"], 369)
            self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
