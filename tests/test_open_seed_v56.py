from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from dataclasses import asdict
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

from datacenter_atlas import open_seed_v56 as v56
from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.epoch import EpochAIAdapter
from datacenter_atlas.open_seed_release import validate_open_seed_release
from datacenter_atlas.publication_release import write_release
from datacenter_atlas.service import summarize, validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v55.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v55"
BUILDER = ROOT / "scripts/build_open_seed_v56.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c"
MANIFEST_SHA256 = "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd"
TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"
BASE_DEFINITION_SHA256 = (
    "06ec0c788bb2dc83dce159a054af644df04337c60367b72abb64e810ac1571ba"
)
BASE_MANIFEST_SHA256 = (
    "26e0da8a7e7b6c051a3dbb0bd74d6155ef7ad94a66904ea319468f2e0b48445b"
)
BASE_TREE_SHA256 = "44610a81fab0375255da9824975746ce301591a2b94e099f43f551eb7eb157b4"
RECORDED_AT = "2026-07-20T22:34:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T22:26:51Z"
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-paix-dkr1-dakar.json": (
        "4abc83e219a463e3a4aa0029063b6708a668a90b80411dbb5795649d08e69ad4"
    ),
    "sources/curated-official-2026-07-20-pentapoint-emd-bkk01-sathorn.json": (
        "98ecc046fac96abbef96a02ab76bbc661c7d7525dbf892dad4e49d6502250cb2"
    ),
}

EXCLUDED_INPUTS = {
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10.json",
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11.json",
    "sources/curated-official-2026-07-20-google-bermuda-hundred-chesterfield.json",
}

ADDITION_POSITIONS = {
    "sources/curated-official-2026-07-20-paix-dkr1-dakar.json": 287,
    "sources/curated-official-2026-07-20-pentapoint-emd-bkk01-sathorn.json": 290,
}

ADDED_ENTITY_KEYS = {
    "curated:paix-dkr1-dakar-data-center-campus",
    "curated:paix-dkr1-dakar-data-center-campus:current-development",
    "curated:pentapoint-emd-bkk01-sathorn-campus",
    "curated:pentapoint-emd-bkk01-sathorn-campus:current-development",
}

PUBLISHED_EVIDENCE = {
    "c2250531ebe0d2fcee50a3dbf9cd3bc28c1c6a881d6790d7ed2fa13a3981f0e0": (
        "dee79abd-fdae-502b-86c5-25b84b637aee",
        "paix_official_prismic",
    ),
    "f7afccfd937496d72fdafa0eba262d779cf8b34558aa673ff5c806a2df6128aa": (
        "b16b9325-8834-5a48-87f5-df620c61ac2c",
        "paix_official_prismic",
    ),
    "a2a3a11a842cf92941eb74cdfda77c66731bf72ced8ac0fa58d64796e0758aa8": (
        "72520162-e1a1-5f47-b3a5-dbc64c48f8f8",
        "pentapoint_official_webflow",
    ),
    "41edd89e9c1c60d03c5374032aafae99769c6fd1173b8185a2148262e61f7b67": (
        "fb0a30bb-8eb8-56bd-ae02-7a31ec9a48df",
        "pentapoint_official_webflow",
    ),
    "bf451d0fd6a3a6e02ae0aecc8f7dba58be06cf79d6eec1ba5f7da649d44137f7": (
        "e31042d3-c1b7-5dba-9c08-d0dc5a587c0c",
        "pentapoint_official_webflow",
    ),
}

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3_505,
        "4b02a240e92ad18d7471ac05612812e21be158f4728415834c632a6ff130cecc",
    ),
    "README.md": (
        2_625,
        "515653a4b56aae883f8917c748cc0d0678ec7961b13368c64db2cfa49a8b26b5",
    ),
    "atlas.geojson": (
        2_362_225,
        "32e1c5247c7de6e4e7f9af9981957023116f64e33c8bd6a4f165ad98be98b0d5",
    ),
    "capacity_estimates.csv": (
        228_985,
        "66393d2cb27a5746c4f0aba2becf1e31b462e3a948c532e9c95c83039fddd5f2",
    ),
    "construction_pipeline.csv": (
        458_341,
        "42f07a6694edd50d3022ae4871dd6eb8ff0d783eb47f08f62c45709fdf62047d",
    ),
    "construction_source_signals.csv": (
        278_260,
        "f1f596a5f62006a4b738d18a4f00cd31a5e84a1053617502c8a9a605aa490694",
    ),
    "entities.csv": (
        738_551,
        "7a63e707b67ad211f4a1a44ff694c7c336063337f9df7eaed0c73b0b990e68d8",
    ),
    "evidence.csv": (
        149_384,
        "a99b5c0060b164f7215efb0220ef33b2d01402d4d43732d15c737f89f88d89f2",
    ),
    "manifest.json": (9_274, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5_874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        225_599,
        "ee5e19bc3dcb4336525b6a657f345144b7702cfd7113d2a9ab7bd5f8dde6f0e2",
    ),
    "summary.json": (
        2_905,
        "21021abe6e91675b85bc3ba2c671829a47bee38c8a2cc06acf7125404d8ec5b1",
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
    ROOT / "datacenter_atlas/open_seed_v55.py": (
        24_543,
        "ad094846f230b1a7c0a7aacbff5bd064f6dba441ecc953db088d93cdd47a1d43",
    ),
    ROOT / "open_seed_v55.py": (
        138,
        "a668e9f392a591f23ccbb5ca94f31b8dbf69a2f48e71dca0a0dbab547ad324cb",
    ),
    ROOT / "scripts/build_open_seed_v55.py": (
        361,
        "3a99aa85021cbdc2ee88887621dea4eb1694fa789f9705598b047656f5b0e15b",
    ),
    ROOT / "datacenter_atlas/open_seed_v56.py": (
        25_343,
        "3349ba9ef81dfdbaba07e0c8b5b5e83642aed93442ca0aaf0dcdcc0b406a4f1c",
    ),
    ROOT / "open_seed_v56.py": (
        138,
        "d14ce997138c5ea982168c1ea6dcf2f5c75131416e76003421cbef363bc33e6b",
    ),
    BUILDER: (
        361,
        "fcdf895d67db55be5ac7065b00cdffce23e082f30e3f17005036067cea4f0f3e",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# Common rows, added count/hash, removed count/hash.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        663,
        4,
        "84d0c084658f6950d3ff5b444246645bac57d10fdb1f4c192de10225e1c1db08",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "evidence.csv": (
        383,
        5,
        "c51d13fabc1d6f855f91c6b23ac54afbe29dfaef26c04472d828194bcdce03f3",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "capacity_estimates.csv": (
        482,
        2,
        "5576e5af8cdae75c65e6ba71e0bfba49291164f58cf6851ee750dc6d3b8572ad",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_pipeline.csv": (
        346,
        2,
        "5758d30a8a0e3e288347f56814cfb3b04b52acb6d2fd4729b08588cd52b6e5fb",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_source_signals.csv": (
        252,
        2,
        "be364d4c3d263152333a16572e1cbfba7181faad5abbfdb82488846e636e6b18",
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


class OpenSeedV56Tests(unittest.TestCase):
    def _validate_offline(self) -> tuple[dict[str, object], int]:
        network_requests = 0
        original_open = Path.open
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text
        seed_pattern = re.compile(r"open-seed-2026-07-20-v(\d+)")
        forbidden_inputs = {str((ROOT / path).resolve()) for path in EXCLUDED_INPUTS}

        def reject(path: Path) -> None:
            resolved = str(path.resolve())
            match = seed_pattern.search(resolved)
            if match is not None and int(match.group(1)) not in {55, 56}:
                raise AssertionError(f"v56 attempted forbidden seed access: {path}")
            if resolved in forbidden_inputs:
                raise AssertionError(f"v56 attempted excluded input access: {path}")

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
            raise AssertionError("v56 validation attempted network access")

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

    def _fresh_projection(self) -> tuple[bytes, dict[str, bytes], str]:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        input_rows, curated_paths = v56.selected_inputs(base)
        with tempfile.TemporaryDirectory(
            prefix="open-seed-v56-reproduction-", dir="/private/tmp"
        ) as temporary:
            temporary_root = Path(temporary)
            connection, _ = initialize(temporary_root / "atlas.sqlite")
            try:
                with ExitStack() as stack:
                    error = AssertionError("v56 reproduction attempted network access")
                    for name in (
                        "socket",
                        "create_connection",
                        "getaddrinfo",
                        "gethostbyname",
                        "gethostbyname_ex",
                    ):
                        stack.enter_context(patch.object(socket, name, side_effect=error))
                    epoch = base["epoch_capture"]
                    epoch_result = EpochAIAdapter().import_file(
                        connection,
                        ROOT / epoch["archive"],
                        map_html=ROOT / epoch["map"],
                        retrieved_at=epoch["retrieved_at"],
                        as_of_date="2026-07-20",
                    )
                    self.assertEqual(
                        json.loads(json.dumps(asdict(epoch_result))),
                        base["expected_epoch_result"],
                    )
                    for path in curated_paths:
                        document = json.loads(path.read_text(encoding="utf-8"))
                        timestamp = {
                            item["retrieved_at"] for item in document["evidence"]
                        }.pop()
                        result = CuratedOfficialSourceAdapter().import_file(
                            connection, path, retrieved_at=timestamp
                        )
                        self.assertEqual(result.warnings, ())
                self.assertEqual(validate_database(connection), [])
                release = temporary_root / "release"
                write_release(
                    connection,
                    release,
                    as_of="2026-07-20",
                    recorded_at=RECORDED_AT,
                    publication_contract_version=4,
                )
                summary = summarize(
                    connection, as_of="2026-07-20", recorded_at=RECORDED_AT
                )
            finally:
                connection.close()

            manifest_raw = (release / "manifest.json").read_bytes()
            manifest = json.loads(manifest_raw)
            expected_release = {
                key: value for key, value in manifest.items() if key != "files"
            }
            expected_release["manifest_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            definition = dict(base)
            definition["build"] = {
                "as_of": "2026-07-20",
                "recorded_at": RECORDED_AT,
            }
            definition["curated_inputs"] = input_rows
            definition["expected_release"] = expected_release
            definition["expected_summary"] = {
                key: summary.get(key) for key in v56.EXPECTED_SUMMARY
            }
            definition["release_id"] = "2026-07-20-open-seed-v56"
            definition_raw = v56.canonical_json(definition)
            release_files = {
                path.name: path.read_bytes() for path in sorted(release.iterdir())
            }
            for path in release.iterdir():
                path.chmod(0o444)
            release.chmod(0o555)
            reproduced_tree = tree_digest(release)
            release.chmod(0o755)
            for path in release.iterdir():
                path.chmod(0o644)
            return definition_raw, release_files, reproduced_tree

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
        for artifact in (DEFINITION, RELEASE, *RELEASE.iterdir()):
            birth_time = getattr(artifact.stat(), "st_birthtime", None)
            if birth_time is not None:
                self.assertLessEqual(cutoff.timestamp(), birth_time, artifact)
        with self.assertRaisesRegex(SystemExit, "at or before the build-start clock"):
            v56.validate_temporal_contract(
                retrieved,
                build_started_at=cutoff - timedelta(microseconds=1),
            )
        v56.validate_temporal_contract(retrieved, build_started_at=cutoff)
        v56.validate_temporal_contract(
            retrieved,
            build_started_at=cutoff + timedelta(days=365_000),
        )

    def test_exact_pins_double_offline_validation_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 67_918)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256)
        self.assertEqual(tree_digest(BASE_RELEASE), BASE_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertFalse(DEFINITION.is_symlink())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual({path.name for path in RELEASE.iterdir()}, set(RELEASE_FILE_PINS))
        for name, (size, digest) in RELEASE_FILE_PINS.items():
            path = RELEASE / name
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path)
            self.assertEqual(path.stat().st_size, size, path)
            self.assertEqual(sha256(path), digest, path)
        for path, (size, digest) in CODE_PINS.items():
            self.assertEqual(path.stat().st_size, size, path)
            self.assertEqual(sha256(path), digest, path)
        first, first_network = self._validate_offline()
        second, second_network = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual((first_network, second_network), (0, 0))
        self.assertEqual(first["entities"], 667)
        self.assertEqual(first["evidence_records"], 388)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)

    def test_definition_is_exact_two_input_addition_to_v55_only(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_rows = base["curated_inputs"]
        current_rows = current["curated_inputs"]
        self.assertEqual(len(base_rows), 316)
        self.assertEqual(len(current_rows), 318)
        self.assertEqual(
            [row for row in current_rows if row["path"] not in ADDED_INPUTS],
            base_rows,
        )
        self.assertEqual(
            {row["path"]: row["sha256"] for row in current_rows if row["path"] in ADDED_INPUTS},
            ADDED_INPUTS,
        )
        self.assertEqual(
            {
                row["path"]: index
                for index, row in enumerate(current_rows)
                if row["path"] in ADDED_INPUTS
            },
            ADDITION_POSITIONS,
        )
        self.assertTrue(EXCLUDED_INPUTS.isdisjoint({row["path"] for row in current_rows}))
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v56")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        for key in (
            "epoch_capture",
            "expected_epoch_result",
            "publication_contract_version",
            "schema_version",
            "scope",
        ):
            self.assertEqual(current[key], base[key], key)
        changed = {key for key in current if current[key] != base.get(key)}
        self.assertEqual(
            changed,
            {
                "build",
                "curated_inputs",
                "expected_release",
                "expected_summary",
                "release_id",
            },
        )

    def test_double_fresh_offline_reproduction_matches_every_frozen_byte(self) -> None:
        first_definition, first_files, first_tree = self._fresh_projection()
        second_definition, second_files, second_tree = self._fresh_projection()
        self.assertEqual(first_definition, second_definition)
        self.assertEqual(first_files, second_files)
        self.assertEqual(first_tree, second_tree)
        self.assertEqual(first_definition, DEFINITION.read_bytes())
        self.assertEqual(first_tree, TREE_SHA256)
        self.assertEqual(set(first_files), set(RELEASE_FILE_PINS))
        for name, raw in first_files.items():
            self.assertEqual(raw, (RELEASE / name).read_bytes(), name)

    def test_csv_delta_is_strictly_additive_and_exact(self) -> None:
        for filename, expected in CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            common = before & after
            added = after - common
            removed = before - common
            actual = (
                sum(common.values()),
                sum(added.values()),
                canonical_hash(normalized_counter_rows(added)),
                sum(removed.values()),
                canonical_hash(normalized_counter_rows(removed)),
            )
            self.assertEqual(actual, expected, filename)

    def test_added_entities_status_models_capacity_roles_and_coordinates(self) -> None:
        base_entities = row_counter(BASE_RELEASE / "entities.csv")
        added = {
            row["stable_key"]: row
            for row in rows(RELEASE / "entities.csv")
            if tuple(row.items()) not in base_entities
        }
        self.assertEqual(set(added), ADDED_ENTITY_KEYS)
        expected = {
            "curated:paix-dkr1-dakar-data-center-campus": (
                "campus",
                "",
                "",
                "14.7213975",
                "-17.4997482",
                "PAIX Data Centres",
                "",
            ),
            "curated:paix-dkr1-dakar-data-center-campus:current-development": (
                "project",
                "site_control",
                "colocation",
                "14.7213975",
                "-17.4997482",
                "PAIX Data Centres",
                "",
            ),
            "curated:pentapoint-emd-bkk01-sathorn-campus": (
                "campus",
                "",
                "",
                "13.7248155",
                "100.5390396",
                "PentaPoint Corporation",
                "AIMS Data Center",
            ),
            "curated:pentapoint-emd-bkk01-sathorn-campus:current-development": (
                "project",
                "under_construction",
                "colocation",
                "13.7248155",
                "100.5390396",
                "PentaPoint Corporation",
                "AIMS Data Center",
            ),
        }
        for key, row in added.items():
            (
                kind,
                status,
                model,
                latitude,
                longitude,
                developer,
                operator,
            ) = expected[key]
            self.assertEqual(row["entity_kind"], kind, key)
            self.assertEqual(row["status"], status, key)
            self.assertEqual(row["operating_model"], model, key)
            self.assertEqual(row["latitude"], latitude, key)
            self.assertEqual(row["longitude"], longitude, key)
            self.assertEqual(json.loads(row["tags_json"])["role:developer"], developer)
            self.assertEqual(row["operator"], operator, key)
            self.assertEqual(row["workloads_json"], "[]", key)
            self.assertEqual(json.loads(row["geometry_json"])["type"], "Point", key)

        capacity_delta = row_counter(
            RELEASE / "capacity_estimates.csv"
        ) - row_counter(BASE_RELEASE / "capacity_estimates.csv")
        capacities = {
            row["name"]: row for row in normalized_counter_rows(capacity_delta)
        }
        self.assertEqual(len(capacities), 2)
        self.assertEqual(
            capacities["PAIX DKR-1 Dakar Data Center Development"]["base"], "1.2"
        )
        self.assertEqual(
            capacities["PentaPoint EMD BKK-01 Development"]["base"], "0.8"
        )
        for row in capacities.values():
            self.assertEqual(row["metric"], "critical_it_mw")
            self.assertEqual(row["stage"], "planned")
            self.assertEqual(row["unit"], "MW")
            self.assertEqual(row["target_date"], "")

        pipeline_delta = row_counter(
            RELEASE / "construction_pipeline.csv"
        ) - row_counter(BASE_RELEASE / "construction_pipeline.csv")
        pipeline = {
            row["stable_key"]: row for row in normalized_counter_rows(pipeline_delta)
        }
        self.assertEqual(
            pipeline[
                "curated:paix-dkr1-dakar-data-center-campus:current-development"
            ]["status"],
            "site_control",
        )
        self.assertEqual(
            pipeline[
                "curated:pentapoint-emd-bkk01-sathorn-campus:current-development"
            ]["status"],
            "under_construction",
        )
        self.assertEqual(
            {
                row["affected_entity_count"]
                for row in normalized_counter_rows(
                    row_counter(RELEASE / "construction_source_signals.csv")
                    - row_counter(BASE_RELEASE / "construction_source_signals.csv")
                )
            },
            {"1"},
        )

    def test_evidence_source_family_and_summary_boundaries_are_exact(self) -> None:
        base_published = row_counter(BASE_RELEASE / "evidence.csv")
        published = [
            row
            for row in rows(RELEASE / "evidence.csv")
            if tuple(row.items()) not in base_published
        ]
        self.assertEqual(
            {
                row["content_hash"]: (row["evidence_id"], row["source_family"])
                for row in published
            },
            PUBLISHED_EVIDENCE,
        )
        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        self.assertEqual(len(base_manifest["source_families"]), 201)
        self.assertEqual(len(manifest["source_families"]), 203)
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            {"paix_official_prismic", "pentapoint_official_webflow"},
        )
        expected_deltas = {
            "entities_total": 4,
            "campuses_total": 2,
            "projects_total": 2,
            "evidence_total": 5,
            "lifecycle_observations_current": 2,
            "capacity_estimates_current": 2,
            "construction_pipeline_records": 2,
            "construction_source_signals": 2,
            "entities_with_coordinates": 4,
            "campuses_with_coordinates": 2,
        }
        for key, delta in expected_deltas.items():
            self.assertEqual(summary[key] - base_summary[key], delta, key)
        self.assertEqual(summary["entities_by_status"]["site_control"], 1)
        self.assertEqual(
            summary["entities_by_status"]["under_construction"]
            - base_summary["entities_by_status"]["under_construction"],
            1,
        )
        self.assertEqual(
            summary["capacity_estimates_by_stage"]["planned"]
            - base_summary["capacity_estimates_by_stage"]["planned"],
            2,
        )
        self.assertNotIn("source_families", summary)

        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)
        self.assertIn("not a count of unique physical sites", readme)
        self.assertTrue(
            {
                "unique_sites",
                "global_completeness",
                "semianalysis_parity",
                "capacity_sum",
            }.isdisjoint(manifest)
        )
        self.assertEqual(
            row_counter(BASE_RELEASE / "resolution_candidates.csv"),
            row_counter(RELEASE / "resolution_candidates.csv"),
        )

    def test_existing_active_lock_and_late_arrival_collisions_are_safe(self) -> None:
        before_definition = DEFINITION.read_bytes()
        before_tree = tree_digest(RELEASE)
        before_base_tree = tree_digest(BASE_RELEASE)
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
        self.assertFalse(v56.PUBLICATION_LOCK.exists())

        descriptor = os.open(
            v56.PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        try:
            os.write(descriptor, b"test-active-lock\n")
            os.close(descriptor)
            descriptor = -1
            self.assertEqual(stat.S_IMODE(v56.PUBLICATION_LOCK.stat().st_mode), 0o600)
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
            v56.PUBLICATION_LOCK.unlink(missing_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v56-collision-", dir="/private/tmp"
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
                v56.promote_noreplace(stage, destination)
            self.assertEqual((stage / "stage.txt").read_text(), "stage\n")
            self.assertEqual((destination / "existing.txt").read_text(), "existing\n")
        self.assertEqual(DEFINITION.read_bytes(), before_definition)
        self.assertEqual(tree_digest(RELEASE), before_tree)
        self.assertEqual(tree_digest(BASE_RELEASE), before_base_tree)

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
                "from datacenter_atlas.open_seed_v56 import BASE_DEFINITION, RELEASE; "
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
            self.assertEqual(payload["entities"], 667)
            self.assertEqual(payload["evidence_records"], 388)
            self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
