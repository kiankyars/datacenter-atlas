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

from datacenter_atlas import open_seed_v53 as v53
from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v53.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v53"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v52.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v52"
BUILDER = ROOT / "scripts/build_open_seed_v53.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "de3f8ccb3db48808b13114b7e2508f7043a6af848465d56e3dabec4242373a30"
MANIFEST_SHA256 = "cd11546443ef2302bac358dea5bf3f57fc0c4f0b84f181e007294da9831a0baa"
BASE_DEFINITION_SHA256 = (
    "95dcf883c9a9b8d37ad50e30f01668303d0ea55bc7199d7dcf827d2daea7a75f"
)
BASE_MANIFEST_SHA256 = (
    "c4e7edee4fbd37959f5c9eb080c416aa9ec3e2489e231795bd85f52a60be27cb"
)
RECORDED_AT = "2026-07-20T19:33:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T17:35:25Z"
MAX_COORDINATE_PROVENANCE_AT = "2026-07-20T18:20:10Z"
TREE_SHA256 = "e1efff272b1469b0431f881d5bafefcea7fe625e1679f31329714c6adb88f9d9"
BASE_TREE_SHA256 = "ae5df8cf0d9d6367db58ced1e1d66a66fe7b1b4e3caef05706248d8a286efed5"
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

SUPERSEDED_INPUTS = {
    "sources/curated-official-2026-07-19-data4-ath1-first-data-center.json": (
        "028990145023dd581beff459437414324bcf76b0da893a2c46c0a13aa065df7c"
    ),
    "sources/curated-official-2026-07-19-digital-realty-fra20-frankfurt.json": (
        "096378e468cfd10d4ed41e25b5fe1b32fff3d2c19b8bc71df6ab51cdadb38e59"
    ),
    "sources/curated-official-2026-07-19-digital-realty-rom1-rome.json": (
        "f809518a71f8d0f4333daabab2e94534af03ea1a1b6b19cd35a91bdecd52e84e"
    ),
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout.json": (
        "587318195fb538e94bbbea1aea27abe12f47e7526b055acd8d22143815d13515"
    ),
}

REPLACEMENT_INPUTS = {
    "sources/curated-official-2026-07-19-data4-ath1-first-data-center-v2.json": (
        "f5945a8c0b0c290bea1251d3514986c9d6fefc96ccc6f784ed23c703646f046a"
    ),
    "sources/curated-official-2026-07-19-digital-realty-fra20-frankfurt-v2.json": (
        "d50982f91d6bb3e9f69a555ceb61d7885ac4c463fd806c9daf5dbedc2edb8197"
    ),
    "sources/curated-official-2026-07-19-digital-realty-rom1-rome-v2.json": (
        "f11d6fad3f51d5e5df8c2f667a9c4d600de7df94df5f5442a4201d44655c5120"
    ),
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v5.json": (
        "45b8ba2a95b743fbff19df93ce4cb9b846d92aa347360bfd0606dd32d1fc90d8"
    ),
}

REPLACEMENT_BY_SUPERSEDED = {
    old_path: new_path for old_path, (new_path, _) in v53.REPLACEMENTS.items()
}

REJECTED_PROVISIONAL_INPUTS = {
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v2.json",
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v3.json",
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v4.json",
    "sources/curated-official-2026-07-20-edged-atl01-3-atlanta-topout-v2.json",
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout-v2.json",
}

EXPECTED_COORDINATES = {
    "curated:data4-ath1-paiania-campus": (37.9429028, 23.8735719),
    "curated:data4-ath1-paiania-campus:first-data-center": (
        37.9429028,
        23.8735719,
    ),
    "curated:digital-realty-fra20-frankfurt": (50.125936, 8.752816),
    "curated:digital-realty-fra20-frankfurt:current-facility-build": (
        50.125936,
        8.752816,
    ),
    "curated:digital-realty-rom1-rome": (41.776044, 12.48923),
    "curated:digital-realty-rom1-rome:current-facility-build": (
        41.776044,
        12.48923,
    ),
    "curated:vantage-zrh1-winterthur-campus": (47.5020821, 8.7713397),
}

PIPELINE_COORDINATE_KEYS = {
    "curated:data4-ath1-paiania-campus:first-data-center",
    "curated:digital-realty-fra20-frankfurt:current-facility-build",
    "curated:digital-realty-rom1-rome:current-facility-build",
}

SIGNAL_COORDINATE_IDS = {
    "574037df-3663-58ff-ad75-72635006e6e6",
    "24a2ee72-4b00-5bf8-860a-089f2f970edd",
    "f663d571-a87f-5869-8477-d3f3de680d49",
}

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
        2_298_085,
        "e209aae9dc3f8762818d1ffbb18953c1367b6a81232f7da292cfa50f84e12e88",
    ),
    "capacity_estimates.csv": (
        225_231,
        "49fe125c54528484ca095b580a1f8fa6eeeabd862d4c9db72d062905b44ffd03",
    ),
    "construction_pipeline.csv": (
        445_744,
        "db9f8fd4497a274545640dd0801bdbe71582bb4eb042e8efb4f1502a17bcfc32",
    ),
    "construction_source_signals.csv": (
        268_029,
        "08d0fa323206a1a1901bd6d6e070295a5f717c4ed15487c789b0a09ef94f0cc5",
    ),
    "entities.csv": (
        721_023,
        "9ef4164209cf89c45fde71dc824cfa02a3616e4b8d99fdd967b121d416768fa6",
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
        "94cd1d02ea2bfc65863bc67bb42694dd77b45e9d216082c566180c1ef0c5e95d",
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
    ROOT / "datacenter_atlas/open_seed_v52.py": (
        22_999,
        "01a706fb8c8137b703a901082d0a90046ee3db08f867a83d9a6c423c2aaeed46",
    ),
    ROOT / "open_seed_v52.py": (
        138,
        "59e24fb4b7b0c9186bd28e83d1e8c572dedd45583ef27a45821fdd44149212c0",
    ),
    ROOT / "scripts/build_open_seed_v52.py": (
        422,
        "ec5a1cbbad092203b1420193ee41cadedef9c6189e176b9e7fc7949b1a7765e4",
    ),
    ROOT / "datacenter_atlas/open_seed_v53.py": (
        29_549,
        "acd18508e027c35fda76664236272121929913f539dda95d989296394a230485",
    ),
    ROOT / "open_seed_v53.py": (
        138,
        "a03fa06f165baca54fdde7dd480ddf62f1d8ea2dcbed4bb6ca6bece36febd0dd",
    ),
    BUILDER: (
        361,
        "6d62455c9728def61dff4957dcfd9f36d9a2bd6660524e3e4d7afd3148c274da",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# Common rows, added count/hash, removed count/hash.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        640,
        7,
        "100dfdc136b2ce21e1d5122ac0d6c0ab3aa4425e4c4911d6c20465a9d7cacaa6",
        7,
        "41396f6a327e008be0918680c7a341ec8b895cda9a5add219d7af07ce6e4573b",
    ),
    "construction_pipeline.csv": (
        333,
        3,
        "f1d64ac5750cb9a70d6e74d5541e75af2308881adb752583c2bd39b8c6c9ef08",
        3,
        "2d587f8db372ea6fcd9363cfe5b88784844f2019efd96d5e9d0205317d19ff36",
    ),
    "construction_source_signals.csv": (
        241,
        3,
        "37950b67b0aa02ffae9964fd1acad4c114e51c96aa468c1897440b63d3e65a69",
        3,
        "53d88ab2abda7a8e78de70b6d2dda8692d73ce1fa2df4518d64d6abe0d0559f8",
    ),
    "evidence.csv": (369, 0, EMPTY_DELTA_SHA256, 0, EMPTY_DELTA_SHA256),
    "capacity_estimates.csv": (
        476,
        0,
        EMPTY_DELTA_SHA256,
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


def rows_by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    records = rows(path)
    result = {row[key]: row for row in records}
    if len(result) != len(records):
        raise AssertionError(f"duplicate {key}: {path}")
    return result


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


class OpenSeedV53Tests(unittest.TestCase):
    def _validate_offline(self) -> tuple[dict[str, object], int]:
        network_requests = 0
        original_open = Path.open
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text
        seed_pattern = re.compile(r"open-seed-2026-07-20-v(\d+)")
        forbidden_inputs = {
            str((ROOT / relative).resolve())
            for relative in {*SUPERSEDED_INPUTS, *REJECTED_PROVISIONAL_INPUTS}
        }

        def reject(path: Path) -> None:
            resolved = str(path.resolve())
            match = seed_pattern.search(resolved)
            if match is not None and int(match.group(1)) not in {52, 53}:
                raise AssertionError(f"v53 attempted forbidden seed access: {path}")
            if resolved in forbidden_inputs:
                raise AssertionError(f"v53 attempted rejected input access: {path}")

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
            raise AssertionError("v53 validation attempted network access")

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

    def test_temporal_contract_covers_later_coordinate_capture(self) -> None:
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        retrieved = [current["epoch_capture"]["retrieved_at"]]
        coordinate_capture_times: list[str] = []
        for row in current["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text(encoding="utf-8"))
            retrieved.extend(item["retrieved_at"] for item in document["evidence"])
            for item in document["evidence"]:
                timestamp = item.get("metadata", {}).get(
                    "coordinate_capture_retrieved_at"
                )
                if timestamp is not None:
                    coordinate_capture_times.append(timestamp)
        cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        self.assertEqual(max(retrieved), MAX_SELECTED_RETRIEVED_AT)
        self.assertEqual(max(coordinate_capture_times), MAX_COORDINATE_PROVENANCE_AT)
        self.assertLess(
            datetime.fromisoformat(MAX_COORDINATE_PROVENANCE_AT.replace("Z", "+00:00")),
            cutoff,
        )
        self.assertLessEqual(cutoff, datetime.now(timezone.utc))

        for artifact in (DEFINITION, RELEASE):
            birth_time = getattr(artifact.stat(), "st_birthtime", None)
            if birth_time is not None:
                self.assertLessEqual(cutoff.timestamp(), birth_time, artifact)

        with self.assertRaisesRegex(SystemExit, "at or before the build-start clock"):
            v53.validate_temporal_contract(
                retrieved,
                coordinate_capture_times,
                build_started_at=cutoff - timedelta(microseconds=1),
            )
        v53.validate_temporal_contract(
            retrieved, coordinate_capture_times, build_started_at=cutoff
        )
        v53.validate_temporal_contract(
            retrieved,
            coordinate_capture_times,
            build_started_at=cutoff + timedelta(days=365_000),
        )

    def test_exact_pins_double_offline_rebuild_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 65_089)
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
        self.assertEqual(len(first["source_families"]), 190)

    def test_definition_is_exact_four_row_replacement_of_v52(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_rows = base["curated_inputs"]
        current_rows = current["curated_inputs"]
        base_pins = {row["path"]: row["sha256"] for row in base_rows}
        pins = {row["path"]: row["sha256"] for row in current_rows}
        self.assertEqual(len(base_rows), 306)
        self.assertEqual(len(base_pins), 306)
        self.assertEqual(len(current_rows), 306)
        self.assertEqual(len(pins), 306)
        self.assertEqual(
            {path: base_pins[path] for path in SUPERSEDED_INPUTS}, SUPERSEDED_INPUTS
        )
        self.assertEqual(set(base_pins) - set(pins), set(SUPERSEDED_INPUTS))
        self.assertEqual(set(pins) - set(base_pins), set(REPLACEMENT_INPUTS))
        self.assertEqual(
            {path: pins[path] for path in REPLACEMENT_INPUTS}, REPLACEMENT_INPUTS
        )
        inherited_base = [
            row for row in base_rows if row["path"] not in SUPERSEDED_INPUTS
        ]
        inherited_current = [
            row for row in current_rows if row["path"] not in REPLACEMENT_INPUTS
        ]
        self.assertEqual(len(inherited_current), 302)
        self.assertEqual(inherited_current, inherited_base)
        self.assertEqual(
            [row["path"] for row in current_rows],
            sorted(row["path"] for row in current_rows),
        )
        self.assertEqual(
            [
                index
                for index, row in enumerate(current_rows)
                if row["path"] in REPLACEMENT_INPUTS
            ],
            [37, 45, 46, 296],
        )
        for old_path, new_path in REPLACEMENT_BY_SUPERSEDED.items():
            self.assertNotIn(old_path, pins)
            self.assertIn(new_path, pins)
        self.assertTrue(REJECTED_PROVISIONAL_INPUTS.isdisjoint(pins))
        self.assertEqual(
            set(v53.REJECTED_PROVISIONAL_INPUTS), REJECTED_PROVISIONAL_INPUTS
        )
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v53")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(v53.BASE_DEFINITION, BASE_DEFINITION)
        self.assertEqual(v53.BASE_RELEASE, BASE_RELEASE)

        payloads = [
            DEFINITION.read_bytes(),
            *(path.read_bytes() for path in RELEASE.iterdir()),
        ]
        for marker in (
            b"open-seed-2026-07-20-v50",
            b"2026-07-20-open-seed-v50",
            *(value.encode() for value in REJECTED_PROVISIONAL_INPUTS),
        ):
            self.assertFalse(any(marker in payload for payload in payloads), marker)

        implementation = sys.modules[v53.selected_inputs.__module__]
        for version in (45, 46, 48, 49, 50, 51):
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
                self.assertRaisesRegex(SystemExit, "select exactly accepted v52"),
            ):
                v53.selected_inputs(base)

    def test_exact_csv_deltas_and_coordinate_only_restoration(self) -> None:
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

        base_entities = rows_by_key(BASE_RELEASE / "entities.csv", "stable_key")
        entities = rows_by_key(RELEASE / "entities.csv", "stable_key")
        self.assertEqual(set(base_entities), set(entities))
        changed = {key for key in entities if entities[key] != base_entities[key]}
        self.assertEqual(changed, set(EXPECTED_COORDINATES))
        for key, (latitude, longitude) in EXPECTED_COORDINATES.items():
            row = entities[key]
            self.assertEqual(
                (float(row["latitude"]), float(row["longitude"])), (latitude, longitude)
            )
            self.assertEqual(
                json.loads(row["geometry_json"]),
                {"coordinates": [longitude, latitude], "type": "Point"},
            )
            restored = dict(row)
            for field in ("latitude", "longitude", "geometry_json"):
                restored[field] = base_entities[key][field]
            self.assertEqual(restored, base_entities[key], key)
        self.assertEqual(
            sum(
                bool(row["latitude"] and row["longitude"]) for row in entities.values()
            ),
            150,
        )
        self.assertEqual(
            sum(
                row["entity_kind"] == "campus"
                and bool(row["latitude"] and row["longitude"])
                for row in entities.values()
            ),
            110,
        )
        zrh12 = entities["curated:vantage-zrh1-winterthur-campus:zrh12"]
        self.assertEqual((zrh12["latitude"], zrh12["longitude"]), ("", ""))
        self.assertEqual(zrh12["geometry_json"], "null")

        base_pipeline = rows_by_key(
            BASE_RELEASE / "construction_pipeline.csv", "stable_key"
        )
        pipeline = rows_by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        pipeline_changed = {
            key for key in pipeline if pipeline[key] != base_pipeline[key]
        }
        self.assertEqual(pipeline_changed, PIPELINE_COORDINATE_KEYS)
        for key in pipeline_changed:
            restored = dict(pipeline[key])
            for field in ("latitude", "longitude", "geometry_json"):
                restored[field] = base_pipeline[key][field]
            self.assertEqual(restored, base_pipeline[key], key)

        signal_key = "source_observation_evidence_id"
        base_signals = rows_by_key(
            BASE_RELEASE / "construction_source_signals.csv", signal_key
        )
        signals = rows_by_key(RELEASE / "construction_source_signals.csv", signal_key)
        signal_changed = {key for key in signals if signals[key] != base_signals[key]}
        self.assertEqual(signal_changed, SIGNAL_COORDINATE_IDS)
        for key in signal_changed:
            restored = dict(signals[key])
            for field in ("representative_latitude", "representative_longitude"):
                restored[field] = base_signals[key][field]
            self.assertEqual(restored, base_signals[key], key)

        for filename in (
            "ATTRIBUTION.txt",
            "README.md",
            "capacity_estimates.csv",
            "evidence.csv",
            "resolution_candidates.csv",
            "resolution_candidates.json",
            "source_inputs.json",
        ):
            self.assertEqual(
                (RELEASE / filename).read_bytes(),
                (BASE_RELEASE / filename).read_bytes(),
                filename,
            )

    def test_geojson_summary_counts_and_scope_are_coordinate_only(self) -> None:
        def features(path: Path) -> dict[str, dict[str, object]]:
            document = json.loads(path.read_text(encoding="utf-8"))
            return {
                feature["properties"]["stable_key"]: feature
                for feature in document["features"]
            }

        base_features = features(BASE_RELEASE / "atlas.geojson")
        current_features = features(RELEASE / "atlas.geojson")
        self.assertEqual(set(base_features), set(current_features))
        changed = {
            key
            for key in current_features
            if current_features[key] != base_features[key]
        }
        self.assertEqual(changed, set(EXPECTED_COORDINATES))
        for key, (latitude, longitude) in EXPECTED_COORDINATES.items():
            before = base_features[key]
            after = current_features[key]
            self.assertIsNone(before["geometry"])
            self.assertEqual(
                after["geometry"],
                {"coordinates": [longitude, latitude], "type": "Point"},
            )
            restored = dict(after["properties"])
            restored["latitude"] = before["properties"]["latitude"]
            restored["longitude"] = before["properties"]["longitude"]
            self.assertEqual(restored, before["properties"])

        base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        summary_changes = {key for key in summary if summary[key] != base_summary[key]}
        self.assertEqual(
            summary_changes,
            {"campuses_with_coordinates", "entities_with_coordinates", "recorded_at"},
        )
        self.assertEqual(summary["campuses_with_coordinates"], 110)
        self.assertEqual(summary["entities_with_coordinates"], 150)
        self.assertEqual(summary["recorded_at"], RECORDED_AT)
        self.assertEqual(summary["entities_total"], 647)
        self.assertEqual(summary["evidence_total"], 435)
        self.assertEqual(summary["capacity_estimates_current"], 476)
        self.assertEqual(summary["construction_pipeline_records"], 336)
        self.assertEqual(summary["construction_source_signals"], 244)

        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(len(manifest["source_families"]), 190)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 349, "project": 298})
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)
        self.assertIn("not a count of unique physical sites", readme)
        self.assertTrue(
            {"unique_sites", "global_completeness", "semianalysis_parity"}.isdisjoint(
                manifest
            )
        )

        definition = json.loads(DEFINITION.read_text())
        families = {"epoch_ai_data_centers"}
        for row in definition["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text())
            families.update(item["source_family"] for item in document["evidence"])
        self.assertEqual(len(families), 221)
        self.assertNotIn("source_families", summary)

    def test_coordinate_successors_preserve_source_semantics_and_provenance(
        self,
    ) -> None:
        expected_capture = {
            "sources/curated-official-2026-07-19-data4-ath1-first-data-center-v2.json": (
                "2026-07-20T18:20:10Z",
                "ed826d9fbc599020c0b8006ccbe815d3db73a27372905d042d760677161d47a3",
                "publisher_html_map_marker",
            ),
            "sources/curated-official-2026-07-19-digital-realty-fra20-frankfurt-v2.json": (
                "2026-07-20T18:20:10Z",
                "5bf2e60b5f30d22ca177bf077012344126efc54af83b4a358cef032c40ea39b9",
                "publisher_html_structured_facility_fields",
            ),
            "sources/curated-official-2026-07-19-digital-realty-rom1-rome-v2.json": (
                "2026-07-20T18:20:09Z",
                "5e0d6ca4a486b8d8b9e4664480c681717c9f52d8750020b42d096dfd38258271",
                "publisher_html_structured_facility_fields",
            ),
        }
        for old_path, new_path in REPLACEMENT_BY_SUPERSEDED.items():
            old = json.loads((ROOT / old_path).read_text())
            new = json.loads((ROOT / new_path).read_text())
            self.assertEqual(
                [
                    (
                        item["key"],
                        item["content_hash"],
                        item["retrieved_at"],
                        item["source_family"],
                    )
                    for item in new["evidence"]
                ],
                [
                    (
                        item["key"],
                        item["content_hash"],
                        item["retrieved_at"],
                        item["source_family"],
                    )
                    for item in old["evidence"]
                ],
                new_path,
            )
            self.assertEqual(new["lifecycle"], old["lifecycle"], new_path)
            self.assertEqual(new["operating_models"], old["operating_models"], new_path)
            self.assertEqual(new["workloads"], old["workloads"], new_path)
            self.assertEqual(new["capacities"], old["capacities"], new_path)
            for entity_name in ("campus", "project"):
                restored = dict(new[entity_name])
                restored["coordinates"] = old[entity_name]["coordinates"]
                restored["method"] = old[entity_name]["method"]
                self.assertEqual(restored, old[entity_name], (new_path, entity_name))

        for relative, (timestamp, body_hash, source_type) in expected_capture.items():
            document = json.loads((ROOT / relative).read_text())
            records = [
                item
                for item in document["evidence"]
                if "coordinate_capture_retrieved_at" in item.get("metadata", {})
            ]
            self.assertEqual(len(records), 1, relative)
            metadata = records[0]["metadata"]
            self.assertEqual(metadata["coordinate_capture_retrieved_at"], timestamp)
            self.assertEqual(metadata["coordinate_capture_body_sha256"], body_hash)
            self.assertEqual(metadata["coordinate_source_type"], source_type)

        vantage = json.loads(
            (
                ROOT
                / "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout-v5.json"
            ).read_text()
        )
        vantage_location = next(
            item
            for item in vantage["evidence"]
            if item["key"]
            == "vantage-zrh1-winterthur-campus-current-captured-2026-07-20"
        )
        locator = vantage_location["metadata"]["coordinate_source_locator"]
        self.assertIn(
            "211623c8cbbc8872dc91fc3fbfd062aa20222558ef237ed3bf94f408bc08fa62",
            locator,
        )
        self.assertIn("2026-07-20T06:42:12Z", locator)
        self.assertNotIn(
            "coordinate_capture_retrieved_at", vantage_location["metadata"]
        )
        self.assertIsNone(vantage["project"]["coordinates"])
        self.assertEqual(vantage["project"]["method"], "authoritative_locality")

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
        self.assertFalse(v53.PUBLICATION_LOCK.exists())

        descriptor = os.open(
            v53.PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
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
            v53.PUBLICATION_LOCK.unlink(missing_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v53-collision-"
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
                v53.promote_noreplace(stage, destination)
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
                "from datacenter_atlas.open_seed_v53 import BASE_DEFINITION, RELEASE; "
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
