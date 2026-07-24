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

from datacenter_atlas import open_seed_v54 as v54
from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v54.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v54"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v53.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v53"
BUILDER = ROOT / "scripts/build_open_seed_v54.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "1510c2abcf24c90be1de69c11878ad7075a495ddeff53859a7525a4e6c6778a5"
MANIFEST_SHA256 = "ae3d6229d7a78e41d7df1e9d6424a45da3ee9ce41d109d8dee426f557e03db11"
BASE_DEFINITION_SHA256 = (
    "de3f8ccb3db48808b13114b7e2508f7043a6af848465d56e3dabec4242373a30"
)
BASE_MANIFEST_SHA256 = (
    "cd11546443ef2302bac358dea5bf3f57fc0c4f0b84f181e007294da9831a0baa"
)
RECORDED_AT = "2026-07-20T19:56:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T19:42:23Z"
TREE_SHA256 = "6a48e0caf8b2a0d6542005b25cf196d1e96a29b1cb44a37af8a9dde0c18c75d5"
BASE_TREE_SHA256 = "e1efff272b1469b0431f881d5bafefcea7fe625e1679f31329714c6adb88f9d9"
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-fleet-reno-storey-county-program.json": (
        "7ada494873559da3782bc31773af1f312b3362df3706a7f8cf90ac97011c7e70"
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw9.json": (
        "2e49ef1fb5659929878ef7418911d9af13e4f45487a013a3e9f7120ea081fab1"
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10-v2.json": (
        "a5da37d9cab7b326e7f08db9ae0561cc20c63dc2e363f87834c146167e7ac14d"
    ),
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11-v2.json": (
        "a01a6f59e2f52de29b867c35e16f124c15a09704c82c980a344efebb4f4512b0"
    ),
    "sources/curated-official-2026-07-20-ascenty-spo06-greater-sao-paulo.json": (
        "6217582ee8cdf3c0e3d1ad175ab33debd90a4fa3ce88288b0e2ce96c9535a491"
    ),
    "sources/curated-official-2026-07-20-ascenty-vinhedo-3.json": (
        "1dfc6f7de38b62692f88c0a8153f7ab3b50117b67fc292c7df97d0ca2f2df8a9"
    ),
    "sources/curated-official-2026-07-20-sb-energy-ports-technology-campus.json": (
        "7a8a6c639b0b26a7c14949ff8787473714eb774d57bf39612adc219584c24260"
    ),
    "sources/curated-official-2026-07-20-raxio-tz1-tanzania.json": (
        "14ef48f59ff1ea9365362a017e68446a362c9cdb748ddffce2ce4be6dc16abd1"
    ),
}

REJECTED_V1_INPUTS = {
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10.json",
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11.json",
}

ADDITION_POSITIONS = {
    "sources/curated-official-2026-07-20-ascenty-spo06-greater-sao-paulo.json": 165,
    "sources/curated-official-2026-07-20-ascenty-vinhedo-3.json": 167,
    "sources/curated-official-2026-07-20-databank-red-oak-dfw10-v2.json": 186,
    "sources/curated-official-2026-07-20-databank-red-oak-dfw11-v2.json": 187,
    "sources/curated-official-2026-07-20-databank-red-oak-dfw9.json": 188,
    "sources/curated-official-2026-07-20-fleet-reno-storey-county-program.json": 237,
    "sources/curated-official-2026-07-20-raxio-tz1-tanzania.json": 290,
    "sources/curated-official-2026-07-20-sb-energy-ports-technology-campus.json": 292,
}

ADDED_ENTITY_KEYS = {
    "curated:ascenty-greater-sao-paulo-campus",
    "curated:ascenty-greater-sao-paulo-campus:spo06",
    "curated:ascenty-vinhedo-campus",
    "curated:ascenty-vinhedo-campus:vinhedo-3",
    "curated:databank-red-oak-campus",
    "curated:databank-red-oak-campus:dfw10",
    "curated:databank-red-oak-campus:dfw11",
    "curated:databank-red-oak-campus:dfw9",
    "curated:fleet-reno-storey-county-program",
    "curated:raxio-tanzania-tz1-campus",
    "curated:raxio-tanzania-tz1-campus:tz1-facility",
    "curated:sb-energy-ports-technology-campus",
}

UNPUBLISHED_EVIDENCE = {
    "databank-red-oak-first-three-financing-2026-04-21-captured-2026-07-20": (
        "4a8b8583d59f0a1927e27bbd0ff1fee4cbc629c3370a8c77bd3679b92021563b",
        "databank_press_releases",
    ),
    "doe-ports-partnership-announcement-2026-03-20-captured-2026-07-20": (
        "cdbde8bb003681344ff79d3d0141e1fdb957183b0b23672797911bdc9e523be2",
        "energy_department_newsroom",
    ),
    "fleet-storey-county-financing-2026-02-24-captured-2026-07-20": (
        "7265aa702f693e8f1e00b157604dc233938614fd74e32c519997b301678b4322",
        "fleet_data_centers_newsroom",
    ),
    "raxio-capital-expansion-2026-07-13-captured-2026-07-20": (
        "a101d2c4fcc5851a9e700ac973907b2cfde6daa7a5aa4f30b0c86328e378e2fd",
        "raxio_newsroom",
    ),
    "sb-energy-ports-current-captured-2026-07-20": (
        "e900032ad28add961c911768fd50aa884aa9c6b6902b2d558195dcee0503696e",
        "sb_energy_digital_infrastructure_pages",
    ),
}

PUBLISHED_EVIDENCE = {
    "05b820f12ce0835ae6fb7fd77fe184ca05463b3273b4b8cee73355a49bdb8a27": (
        "databank_facility_pages"
    ),
    "174f7e1993b1a5f3ced70614fb08afe514179d542f799c16d0bf33f7edb50ea1": (
        "energy_department_nepa_records"
    ),
    "1c08dd9b746d0cf45af229e79e3d195fee2340e00c4757116d92d42b2d065d71": (
        "databank_campus_pages"
    ),
    "1f6fc48795414821901bc2cd63eb9243bfbb9dd999a19127557a220ad0103f77": (
        "databank_facility_pages"
    ),
    "3ca3253561d8cb17e857aee910aae6438bfe7c4d6a8f5d12f8a187ee1a4731b2": (
        "databank_facility_pages"
    ),
    "3d2943fbf13815cc39a73cff0067e6107616dff5c0225030509df8dc05766dd7": (
        "raxio_location_pages"
    ),
    "50b1f1abd24ae0eb4ec7f453043cea09255f448477312edaf932feb404618e77": (
        "ascenty_newsroom"
    ),
    "966870f4e9dc712246aaa91720f200ebb422da97c408f2ddedb8b9b1daa0e132": (
        "ascenty_newsroom"
    ),
    "9e5b3e4ed1ccb8e3f34c3333fe879f15d5feb89da8223346cf0aca168ce3c859": (
        "energy_department_environmental_management_news"
    ),
    "d2cb3eb5e3da4dae448ca5f7c4c3746b14a17e8a8de239ce3a3ff9f7ac2174ac": (
        "raxio_linkedin_company_posts"
    ),
    "d77a71239c1c7d7a850a81fc930ba1e249d78565e31f20b92f931591b47765fa": (
        "databank_official_blogs"
    ),
    "e0c1ae990238bf18716f4dae496251c8fcde754ae4fe1c32128f0c219167ddb2": (
        "fleet_data_centers_linkedin_posts"
    ),
}

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3_399,
        "193063c5d95ddf8c9e6bf0e0ae9b1bcd9b14ae8bdf997672a386d96143d7f0de",
    ),
    "README.md": (
        2_625,
        "cf60838472e6ac27a12beffd2a81d2f50607212c51b0dd9e612391b295696667",
    ),
    "atlas.geojson": (
        2_336_347,
        "3177f90cde510dad2e374ea47e94524768938b99e76e7323b5b7caa5166ab947",
    ),
    "capacity_estimates.csv": (
        227_936,
        "365e09f2ed90a7b2ba60cd5a75942027310ac61eb6b6fc3622ee2609e2095e2c",
    ),
    "construction_pipeline.csv": (
        453_849,
        "a9ad9dcb3f835be62b38fe0b871438f5969244b9a0798c49924b6f681534a569",
    ),
    "construction_source_signals.csv": (
        274_173,
        "8a9b0612f8e97b3ce24faed658c3944f0d2bcd554bd113e0386ea002203807bc",
    ),
    "entities.csv": (
        731_247,
        "283d568ff36dc6d94ccf00181f48641412ee1dc3c988caa32e2f301f44e6856f",
    ),
    "evidence.csv": (
        146_729,
        "d6156b4bc4a4a1e190cc3a2d7aa26d67fbcf2e7cb917ee76d9eef91a8ece5f2c",
    ),
    "manifest.json": (9_148, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5_874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        220_717,
        "6e0930d694a6767fdea19e7e3f6f84235dcb418d26f558364839b817e8d32ae6",
    ),
    "summary.json": (
        2_846,
        "301e6cac6417aa104799412540b59f810605da336f717d376f87865a9a14fe6d",
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
    ROOT / "datacenter_atlas/open_seed_v53.py": (
        29_549,
        "acd18508e027c35fda76664236272121929913f539dda95d989296394a230485",
    ),
    ROOT / "open_seed_v53.py": (
        138,
        "a03fa06f165baca54fdde7dd480ddf62f1d8ea2dcbed4bb6ca6bece36febd0dd",
    ),
    ROOT / "scripts/build_open_seed_v53.py": (
        361,
        "6d62455c9728def61dff4957dcfd9f36d9a2bd6660524e3e4d7afd3148c274da",
    ),
    ROOT / "datacenter_atlas/open_seed_v54.py": (
        29_058,
        "224e358d88cddd9a761364f09776a0230fa6137952b2126e0b60ba9a5e708cfc",
    ),
    ROOT / "open_seed_v54.py": (
        138,
        "d321a574c82711ff18897e36389e186443c8db734a5e64773418a28abaecee98",
    ),
    BUILDER: (
        361,
        "b83d6f216d6919e466ffe8400dc8344e15cf182f5e191c794881d6a3357c9202",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# Common rows, added count/hash, removed count/hash.
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        647,
        12,
        "1d8a83d82bda93a8b511948e6fa684bda77119c4ef0b928166b6bbee07fe03f7",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "evidence.csv": (
        369,
        12,
        "12f6f770cc497116adcc660f90ef1da78be85293d2f1aecc67aad55d39f26b04",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "capacity_estimates.csv": (
        476,
        6,
        "64e85a77c95b013fbad02b932e0ae8d2a99ba229a380748a2b1dd6266dabcae1",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_pipeline.csv": (
        336,
        8,
        "d56034a321b2fa1036c1955b5deef4892884abd5151d1773879710eeab367594",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_source_signals.csv": (
        244,
        6,
        "8f619eecc2a142f2269bf90e8645c2d1a42ce8aca719ce6703743ab80b4ad82a",
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


class OpenSeedV54Tests(unittest.TestCase):
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
            if match is not None and int(match.group(1)) not in {53, 54}:
                raise AssertionError(f"v54 attempted forbidden seed access: {path}")
            if resolved in forbidden_inputs:
                raise AssertionError(f"v54 attempted rejected v1 input access: {path}")

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
            raise AssertionError("v54 validation attempted network access")

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
            v54.validate_temporal_contract(
                retrieved,
                build_started_at=cutoff - timedelta(microseconds=1),
            )
        v54.validate_temporal_contract(retrieved, build_started_at=cutoff)
        v54.validate_temporal_contract(
            retrieved,
            build_started_at=cutoff + timedelta(days=365_000),
        )

    def test_exact_pins_double_offline_rebuild_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 67_040)
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
            "entities": 659,
            "entities_by_kind": {"campus": 355, "project": 304},
            "evidence_records": 381,
            "capacity_estimates": 482,
            "construction_pipeline_records": 344,
            "construction_source_signals": 250,
            "resolution_candidates": 4,
        }
        for key, value in expected.items():
            self.assertEqual(first[key], value, key)
        self.assertEqual(len(first["source_families"]), 199)

    def test_definition_is_exact_eight_input_addition_to_v53_only(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_rows = base["curated_inputs"]
        current_rows = current["curated_inputs"]
        base_pins = {row["path"]: row["sha256"] for row in base_rows}
        pins = {row["path"]: row["sha256"] for row in current_rows}
        self.assertEqual(len(base_rows), 306)
        self.assertEqual(len(base_pins), 306)
        self.assertEqual(len(current_rows), 314)
        self.assertEqual(len(pins), 314)
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
        actual_positions = {
            row["path"]: index
            for index, row in enumerate(current_rows)
            if row["path"] in ADDED_INPUTS
        }
        self.assertEqual(actual_positions, ADDITION_POSITIONS)
        self.assertTrue(REJECTED_V1_INPUTS.isdisjoint(pins))
        self.assertEqual(set(v54.REJECTED_PROVISIONAL_INPUTS), REJECTED_V1_INPUTS)
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v54")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(v54.BASE_DEFINITION, BASE_DEFINITION)
        self.assertEqual(v54.BASE_RELEASE, BASE_RELEASE)

        payloads = [
            DEFINITION.read_bytes(),
            *(path.read_bytes() for path in RELEASE.iterdir()),
        ]
        for marker in (
            b"open-seed-2026-07-20-v50",
            b"2026-07-20-open-seed-v50",
            *(value.encode() for value in REJECTED_V1_INPUTS),
        ):
            self.assertFalse(any(marker in payload for payload in payloads), marker)

        implementation = sys.modules[v54.selected_inputs.__module__]
        for version in (45, 46, 48, 49, 50, 51, 52):
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
                self.assertRaisesRegex(SystemExit, "select exactly accepted v53"),
            ):
                v54.selected_inputs(base)

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
        all_entities = rows(RELEASE / "entities.csv")
        added = {
            row["stable_key"]: row
            for row in all_entities
            if tuple(row.items()) not in base_entities
        }
        self.assertEqual(set(added), ADDED_ENTITY_KEYS)
        expected_roles = {
            "curated:fleet-reno-storey-county-program": {
                "role:contractor": "Clark Construction Group"
            },
            "curated:raxio-tanzania-tz1-campus": {
                "role:developer": "Raxio Group",
                "role:operator": "Raxio Group",
            },
            "curated:raxio-tanzania-tz1-campus:tz1-facility": {
                "role:developer": "Raxio Group",
                "role:operator": "Raxio Group",
            },
        }
        for key, row in added.items():
            tags = json.loads(row["tags_json"])
            roles = {
                name: value for name, value in tags.items() if name.startswith("role:")
            }
            self.assertEqual(roles, expected_roles.get(key, {}), key)
            self.assertEqual(row["latitude"], "", key)
            self.assertEqual(row["longitude"], "", key)
            self.assertEqual(row["geometry_json"], "null", key)
            self.assertEqual(row["workloads_json"], "[]", key)
        self.assertEqual(
            added["curated:raxio-tanzania-tz1-campus:tz1-facility"]["operating_model"],
            "colocation",
        )
        for key, row in added.items():
            if key != "curated:raxio-tanzania-tz1-campus:tz1-facility":
                self.assertEqual(row["operating_model"], "", key)

        base_pipeline = row_counter(BASE_RELEASE / "construction_pipeline.csv")
        pipeline = {
            row["stable_key"]: row
            for row in rows(RELEASE / "construction_pipeline.csv")
            if tuple(row.items()) not in base_pipeline
        }
        expected_status_dates = {
            "curated:fleet-reno-storey-county-program": "2026-05-21",
            "curated:databank-red-oak-campus:dfw9": "2025-11-10",
            "curated:databank-red-oak-campus:dfw10": "2025-11-10",
            "curated:databank-red-oak-campus:dfw11": "2025-11-10",
            "curated:ascenty-greater-sao-paulo-campus:spo06": "2026-05-08",
            "curated:ascenty-vinhedo-campus:vinhedo-3": "2026-05-28",
            "curated:sb-energy-ports-technology-campus": "2026-03-20",
            "curated:raxio-tanzania-tz1-campus:tz1-facility": "2024-12-23",
        }
        self.assertEqual(set(pipeline), set(expected_status_dates))
        for key, as_of in expected_status_dates.items():
            self.assertEqual(pipeline[key]["status"], "under_construction", key)
            self.assertEqual(pipeline[key]["status_as_of"], as_of, key)

        base_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        entity_by_id = {row["entity_id"]: row for row in all_entities}
        capacity = [
            row
            for row in rows(RELEASE / "capacity_estimates.csv")
            if tuple(row.items()) not in base_capacity
        ]
        observed = {
            (
                entity_by_id[row["entity_id"]]["stable_key"],
                row["metric"],
                row["stage"],
                row["base"],
            )
            for row in capacity
        }
        self.assertEqual(
            observed,
            {
                (
                    "curated:fleet-reno-storey-county-program",
                    "critical_it_mw",
                    "planned",
                    "400.0",
                ),
                (
                    "curated:databank-red-oak-campus:dfw9",
                    "critical_it_mw",
                    "planned",
                    "60.0",
                ),
                (
                    "curated:databank-red-oak-campus:dfw10",
                    "critical_it_mw",
                    "planned",
                    "60.0",
                ),
                (
                    "curated:databank-red-oak-campus:dfw11",
                    "critical_it_mw",
                    "planned",
                    "60.0",
                ),
                (
                    "curated:raxio-tanzania-tz1-campus:tz1-facility",
                    "critical_it_mw",
                    "planned",
                    "6.0",
                ),
                (
                    "curated:raxio-tanzania-tz1-campus:tz1-facility",
                    "pue",
                    "design",
                    "1.3",
                ),
            },
        )

    def test_shared_campus_and_evidence_collisions_are_deterministic(self) -> None:
        entities = rows(RELEASE / "entities.csv")
        databank = [
            row
            for row in entities
            if row["stable_key"].startswith("curated:databank-red-oak-campus")
        ]
        self.assertEqual(
            {row["stable_key"] for row in databank},
            {
                "curated:databank-red-oak-campus",
                "curated:databank-red-oak-campus:dfw9",
                "curated:databank-red-oak-campus:dfw10",
                "curated:databank-red-oak-campus:dfw11",
            },
        )
        self.assertEqual(sum(row["entity_kind"] == "campus" for row in databank), 1)
        construction_evidence_id = "2d81c3fa-b8f8-51f3-94ca-de614682fa69"
        pipeline = rows_by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        for suffix in ("dfw9", "dfw10", "dfw11"):
            self.assertEqual(
                pipeline[f"curated:databank-red-oak-campus:{suffix}"][
                    "status_evidence_id"
                ],
                construction_evidence_id,
            )
        evidence_rows = rows(RELEASE / "evidence.csv")
        self.assertEqual(
            sum(
                row["evidence_id"] == construction_evidence_id for row in evidence_rows
            ),
            1,
        )
        signals = rows_by_key(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )
        shared_signal = signals[construction_evidence_id]
        self.assertEqual(shared_signal["affected_entity_count"], "3")
        affected = json.loads(shared_signal["affected_entities_json"])
        self.assertEqual(
            {row["stable_key"] for row in affected},
            {
                "curated:databank-red-oak-campus:dfw9",
                "curated:databank-red-oak-campus:dfw10",
                "curated:databank-red-oak-campus:dfw11",
            },
        )

        source_evidence_keys: list[str] = []
        for relative in ADDED_INPUTS:
            document = json.loads((ROOT / relative).read_text())
            source_evidence_keys.extend(item["key"] for item in document["evidence"])
        counts = Counter(source_evidence_keys)
        self.assertEqual(len(source_evidence_keys), 24)
        self.assertEqual(len(counts), 17)
        self.assertEqual(
            counts[
                "ascenty-ai-contracts-vinhedo3-spo06-2026-05-28-captured-2026-07-20"
            ],
            2,
        )
        for key in (
            "databank-red-oak-construction-2025-11-10-captured-2026-07-20",
            "databank-red-oak-first-three-financing-2026-04-21-captured-2026-07-20",
            "databank-red-oak-campus-current-captured-2026-07-20",
        ):
            self.assertEqual(counts[key], 3, key)
        ascenty_evidence_id = "2b138f72-e7f8-560c-8f63-0cbe196b245e"
        self.assertEqual(
            sum(row["evidence_id"] == ascenty_evidence_id for row in evidence_rows),
            1,
        )
        entity_rows = rows_by_key(RELEASE / "entities.csv", "stable_key")
        for key in (
            "curated:ascenty-vinhedo-campus",
            "curated:ascenty-vinhedo-campus:vinhedo-3",
        ):
            self.assertEqual(
                entity_rows[key]["snapshot_evidence_id"], ascenty_evidence_id
            )

    def test_database_and_published_evidence_boundaries_are_exact(self) -> None:
        base_summary = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        base_manifest = json.loads((BASE_RELEASE / "manifest.json").read_text())
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        self.assertEqual(base_summary["evidence_total"], 435)
        self.assertEqual(summary["evidence_total"], 452)
        self.assertEqual(base_manifest["evidence_records"], 369)
        self.assertEqual(manifest["evidence_records"], 381)

        input_evidence: dict[str, dict[str, object]] = {}
        incoming_families: set[str] = set()
        for relative in ADDED_INPUTS:
            document = json.loads((ROOT / relative).read_text())
            for item in document["evidence"]:
                input_evidence[item["key"]] = item
                incoming_families.add(item["source_family"])
        self.assertEqual(len(input_evidence), 17)
        self.assertEqual(len(incoming_families), 14)

        base_published = row_counter(BASE_RELEASE / "evidence.csv")
        added_published = [
            row
            for row in rows(RELEASE / "evidence.csv")
            if tuple(row.items()) not in base_published
        ]
        published_by_hash = {
            row["content_hash"]: row["source_family"] for row in added_published
        }
        self.assertEqual(published_by_hash, PUBLISHED_EVIDENCE)
        for key, (content_hash, family) in UNPUBLISHED_EVIDENCE.items():
            self.assertEqual(input_evidence[key]["content_hash"], content_hash)
            self.assertEqual(input_evidence[key]["source_family"], family)
            self.assertNotIn(content_hash, published_by_hash)

        definition = json.loads(DEFINITION.read_text())
        database_families = {"epoch_ai_data_centers"}
        for row in definition["curated_inputs"]:
            document = json.loads((ROOT / row["path"]).read_text())
            database_families.update(
                item["source_family"] for item in document["evidence"]
            )
        self.assertEqual(len(database_families), 235)
        self.assertEqual(len(base_manifest["source_families"]), 190)
        self.assertEqual(len(manifest["source_families"]), 199)
        self.assertEqual(
            set(manifest["source_families"]) - set(base_manifest["source_families"]),
            set(PUBLISHED_EVIDENCE.values()),
        )
        self.assertNotIn("source_families", summary)

    def test_summary_scope_and_resolution_contracts_are_exact(self) -> None:
        base = json.loads((BASE_RELEASE / "summary.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        expected_deltas = {
            "entities_total": 12,
            "campuses_total": 6,
            "projects_total": 6,
            "evidence_total": 17,
            "lifecycle_observations_current": 8,
            "capacity_estimates_current": 6,
            "construction_pipeline_records": 8,
            "construction_source_signals": 6,
            "entities_with_coordinates": 0,
            "campuses_with_coordinates": 0,
        }
        for key, delta in expected_deltas.items():
            self.assertEqual(summary[key] - base[key], delta, key)
        self.assertEqual(
            summary["entities_by_status"]["under_construction"]
            - base["entities_by_status"]["under_construction"],
            8,
        )
        self.assertEqual(
            summary["capacity_estimates_by_stage"]["planned"]
            - base["capacity_estimates_by_stage"]["planned"],
            5,
        )
        self.assertEqual(
            summary["capacity_estimates_by_stage"]["design"]
            - base["capacity_estimates_by_stage"]["design"],
            1,
        )
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
        self.assertFalse(v54.PUBLICATION_LOCK.exists())

        descriptor = os.open(
            v54.PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
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
            v54.PUBLICATION_LOCK.unlink(missing_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v54-collision-"
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
                v54.promote_noreplace(stage, destination)
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
                "from datacenter_atlas.open_seed_v54 import BASE_DEFINITION, RELEASE; "
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
            self.assertEqual(payload["entities"], 659)
            self.assertEqual(payload["evidence_records"], 381)
            self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
