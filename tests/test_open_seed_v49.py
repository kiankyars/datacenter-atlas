from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v49.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v49"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v47.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v47"
BUILDER = ROOT / "scripts/build_open_seed_v49.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c"
MANIFEST_SHA256 = "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489"
BASE_DEFINITION_SHA256 = (
    "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"
)
BASE_MANIFEST_SHA256 = (
    "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1"
)
RECORDED_AT = "2026-07-20T16:45:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T10:42:21Z"
TREE_SHA256 = "77309cad997d57635c7a88de10746ff194d456d19b360574cf46223cb2841395"
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

REMOVED_INPUTS = {
    "sources/curated-official-2026-07-20-digipower-columbiana-shell.json": (
        "7728f26d064c0ec3a47ac34aa60fdb635770a7b49e2fa90c4a0de91ca91e2ace"
    )
}

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-coresite-de3-denver.json": (
        "8bfb0b31e468647753a142e9fc0ba3306e06e8272b02e6fbe848809a3bd69868"
    ),
    "sources/curated-official-2026-07-20-digipower-columbiana-shell-v2.json": (
        "a137bd6356ead2052ad160aa50c7ab27d7871f4b2552dba276ffa86949f46ccd"
    ),
    "sources/curated-official-2026-07-20-edged-atl01-3-atlanta-topout.json": (
        "0213438b6b2844bbad14674ed8381e3a019c3d240ef55db3625c1543a4f98c06"
    ),
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout.json": (
        "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c"
    ),
    "sources/curated-official-2026-07-20-flexential-parker-colorado-shell.json": (
        "caab2c8be10a81a8b26f2cc5acbfe3b4229dc9b8fbcbaef61028efb688fbb34a"
    ),
    "sources/curated-official-2026-07-20-goodman-ams01-amsterdam-v2.json": (
        "802d18c2dab6091add67c798064c60dbed843a0c639abc3b843adaf68d77f1a0"
    ),
    "sources/curated-official-2026-07-20-goodman-fra02-frankfurt-v2.json": (
        "2016970c6feda0ed1df7299c346713a29c86eed4088994f74fce515ddb809830"
    ),
    "sources/curated-official-2026-07-20-goodman-hkg09-kwai-chung-v2.json": (
        "e4e0f0c9db3ce6295696427e425a41cc458441cc06d9413e8b6cab50a40367d1"
    ),
    "sources/curated-official-2026-07-20-goodman-hkg10-tsuen-wan-v2.json": (
        "ce187a48475f227603a73922320a14cf03b7f6c88374830e969f5cba6d1138b9"
    ),
    "sources/curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json": (
        "296b17b45a9a6f56037b137ca68f37e549607317c2550b3e606a59e640528249"
    ),
    "sources/curated-official-2026-07-20-goodman-par01-paris-v2.json": (
        "f7d558d0e0234379ae3013bd794bd878a0c70ae9ccfcefd1718ee23406c6711c"
    ),
    "sources/curated-official-2026-07-20-goodman-par02-paris-v2.json": (
        "f7e770519d244a8b57d7710c7ae1674ec2390bcd44f8d1b73d8c642adf5319c6"
    ),
    "sources/curated-official-2026-07-20-goodman-syd01-macquarie-park-v2.json": (
        "4667aea59067cd587bba475d9c42f26ac08e4edbdac058412b5a8df8a738d660"
    ),
    "sources/curated-official-2026-07-20-goodman-ty005-tokyo-v2.json": (
        "045cf3bb76bc9171ce017784562bcebab5eb5fc306c9ab017981631ce2e84764"
    ),
    "sources/curated-official-2026-07-20-goodman-ty006-tokyo-v2.json": (
        "991f66bc60af577f47d2ad0a87ce861524ab805090d0215b1ff3bf5407dffdb4"
    ),
}

GOODMAN_V1_PATHS = {
    path.removesuffix("-v2.json") + ".json"
    for path in ADDED_INPUTS
    if "/curated-official-2026-07-20-goodman-" in path
}
VNET_V1_PATHS = {
    f"sources/curated-official-2026-07-20-vnet-{slug}.json"
    for slug in (
        "e-js03b",
        "n-hb02",
        "n-hb03",
        "n-hb04",
        "n-or01",
        "n-or02a",
        "n-or02b",
        "n-or03",
    )
}
VNET_V2_PATHS = {
    path.removesuffix(".json") + "-v2.json" for path in VNET_V1_PATHS
}

FORBIDDEN_PATH_FRAGMENTS = tuple(
    set(REMOVED_INPUTS)
    | GOODMAN_V1_PATHS
    | VNET_V1_PATHS
    | {
        "sources/curated-official-2026-07-20-hyperco-dayone-koria.json",
        "sources/curated-official-2026-07-20-teraco-jb7-isando.json",
        "sources/open-seed-2026-07-20-v48.json",
        "releases/2026-07-20-open-seed-v48",
    }
)

FORBIDDEN_PAYLOAD_MARKERS = tuple(
    value.encode("ascii")
    for value in (
        *FORBIDDEN_PATH_FRAGMENTS,
        "2026-07-20-open-seed-v48",
        "7d94cc5359a326f2ffaf00b28816a8d1751a25079cfd0264115246fdbbe78f89",
        "8e708671fd88ca2b4d9c106bda6a692e06e11f2ab1a6b72e31342277e300eee8",
        "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293",
        "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d",
    )
)

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3_198,
        "daf38528a182d983550358b248cac9eb5cf40952d68f962a475b8067d5d2673a",
    ),
    "README.md": (
        2_625,
        "8cfd629546c3275d1e3e3b902f7c9a3f923e5531a8cb34b82c79bf0fcaddbe4e",
    ),
    "atlas.geojson": (
        2_237_133,
        "4817c82419d1c3d5d332da77a18279fbfe0c467d301035ddcd7a0b7a5681262d",
    ),
    "capacity_estimates.csv": (
        219_958,
        "b43f73c879054d1fa4fd337941b4a56af2c1dd49c27f984d6cab8d6a296df2da",
    ),
    "construction_pipeline.csv": (
        434_385,
        "abe17bc0c2d7bfa425e9d28bbe96b2f6e48f7834477d984cab1a9f579493921c",
    ),
    "construction_source_signals.csv": (
        259_146,
        "9a9189f971c19ae7ec81ef5642f773225d24e8a6a8aef0fffcd793dc8729a612",
    ),
    "entities.csv": (
        702_522,
        "934dcce10932f10617b7ff81a53c1b0a33f1b7807ab1430f86c4bbcfae809601",
    ),
    "evidence.csv": (
        135_561,
        "1e8f32a5fe6b129a11cb0fabe3a24b516e4bbc79f46fc6c2ed073d8ff1965c4d",
    ),
    "manifest.json": (8_364, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5_874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        199_684,
        "ad4b6f30184d0a2a1e65ed988dc77e7527d7547e8de4851511cb4a5e4aa7aad2",
    ),
    "summary.json": (
        2_806,
        "2d74a291a2a4862fb27f444ba6cbe653d7587e8d89251a4cf30eef41e94f2e9c",
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
    BUILDER: (
        18_656,
        "0f01bd518faa5ed4bb6610777a7864128fefc65591ae3c6d7c1165b19469c1a3",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# common count, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        601,
        28,
        "bdf459577137ac647454c38e0db6954d5fe2ab17c25843836e441aef68f19871",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "evidence.csv": (
        337,
        15,
        "4a0fd521f9d27227cfb22236c0a1908c78131c7b5beb460c266ee6a762273246",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "capacity_estimates.csv": (
        454,
        13,
        "2f10a1203d138db4e3616486b797e677d40f93fbacad13e52665d9cf952867e6",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_pipeline.csv": (
        313,
        14,
        "42311dbb4e7ef694f6d6c798de6ab2d35fe393c15f1121fb5d00c7a9caee7d35",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_source_signals.csv": (
        228,
        7,
        "d9ba33d85aff0ffb639232825a275fa79d44fd775c26cc89dbecb7eac46a8f58",
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
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode("utf-8"))
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode("utf-8")
            )
        else:
            raise AssertionError(f"unsupported release entry: {relative}")
    return digest.hexdigest()


class OpenSeedV49Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        blocked = AssertionError("v49 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def forbidden(path: Path) -> bool:
            rendered = path.resolve().as_posix()
            return any(marker in rendered for marker in FORBIDDEN_PATH_FRAGMENTS)

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v49 attempted forbidden input access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if forbidden(path):
                raise AssertionError(f"v49 attempted forbidden input access: {path}")
            return original_read_text(path, *args, **kwargs)

        with ExitStack() as stack:
            stack.enter_context(patch.object(Path, "read_bytes", new=guarded_read_bytes))
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

    def test_exact_pins_double_offline_reproduction_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 62_617)
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256)
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
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 629)
        self.assertEqual(first["entities_by_kind"], {"campus": 340, "project": 289})
        self.assertEqual(first["evidence_records"], 352)
        self.assertEqual(first["capacity_estimates"], 467)
        self.assertEqual(first["construction_pipeline_records"], 327)
        self.assertEqual(first["construction_source_signals"], 235)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exact_v47_delta_and_rejects_bad_lineage(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_pins = {row["path"]: row["sha256"] for row in base["curated_inputs"]}
        pins = {row["path"]: row["sha256"] for row in current["curated_inputs"]}
        self.assertEqual(len(base_pins), 283)
        self.assertEqual(len(pins), 297)
        self.assertEqual(set(base_pins) - set(pins), set(REMOVED_INPUTS))
        self.assertEqual(set(pins) - set(base_pins), set(ADDED_INPUTS))
        self.assertEqual(
            {path: base_pins[path] for path in set(base_pins) & set(pins)},
            {path: pins[path] for path in set(base_pins) & set(pins)},
        )
        self.assertEqual({path: base_pins[path] for path in REMOVED_INPUTS}, REMOVED_INPUTS)
        self.assertEqual({path: pins[path] for path in ADDED_INPUTS}, ADDED_INPUTS)
        self.assertTrue(VNET_V2_PATHS <= set(pins))
        self.assertFalse(set(pins) & (GOODMAN_V1_PATHS | VNET_V1_PATHS))
        self.assertTrue(any("stack-stafford-first-topout" in path for path in pins))
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v49")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)

        retrieved = [current["epoch_capture"]["retrieved_at"]]
        for path in pins:
            document = json.loads((ROOT / path).read_text(encoding="utf-8"))
            retrieved.extend(row["retrieved_at"] for row in document["evidence"])
        self.assertEqual(max(retrieved), MAX_SELECTED_RETRIEVED_AT)
        self.assertLess(
            datetime.fromisoformat(MAX_SELECTED_RETRIEVED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00")),
        )

        payloads = [DEFINITION.read_bytes(), *(path.read_bytes() for path in RELEASE.iterdir())]
        for marker in FORBIDDEN_PAYLOAD_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_csv_delta_is_additive_only_and_exact(self) -> None:
        for filename, expected in CSV_DELTA_CONTRACT.items():
            before = row_counter(BASE_RELEASE / filename)
            after = row_counter(RELEASE / filename)
            common = before & after
            added = after - common
            removed = before - common
            common_count, added_count, added_hash, removed_count, removed_hash = expected
            self.assertEqual(sum(common.values()), common_count, filename)
            self.assertEqual(sum(added.values()), added_count, filename)
            self.assertEqual(
                canonical_hash(normalized_counter_rows(added)), added_hash, filename
            )
            self.assertEqual(sum(removed.values()), removed_count, filename)
            self.assertEqual(
                canonical_hash(normalized_counter_rows(removed)), removed_hash, filename
            )

    def test_capacity_status_type_and_workload_semantics_remain_typed(self) -> None:
        entities = {row["entity_id"]: row for row in rows(RELEASE / "entities.csv")}
        capacities = rows(RELEASE / "capacity_estimates.csv")
        base_capacity_ids = {
            tuple(row.items()) for row in rows(BASE_RELEASE / "capacity_estimates.csv")
        }
        added_capacities = [
            row for row in capacities if tuple(row.items()) not in base_capacity_ids
        ]
        observed = {
            (
                entities[row["entity_id"]]["stable_key"],
                row["metric"],
                row["stage"],
                row["base"],
            )
            for row in added_capacities
        }
        expected = {
            ("curated:coresite-de3-race-street-campus", "critical_it_mw", "planned", "60.0"),
            ("curated:coresite-de3-race-street-campus:de3", "critical_it_mw", "planned", "18.0"),
            ("curated:edged-atlanta-campus", "critical_it_mw", "planned", "169.0"),
            ("curated:edged-atlanta-campus:atl01-03", "critical_it_mw", "planned", "42.0"),
            ("curated:edged-chicago-aurora-campus", "critical_it_mw", "planned", "96.0"),
            ("curated:edged-chicago-aurora-campus:ord01-2", "critical_it_mw", "planned", "72.0"),
            ("curated:flexential-parker-compark-campus:first-data-center", "grid_connection_mw", "planned", "22.5"),
            ("curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment", "critical_it_mw", "planned", "28.0"),
            ("curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment", "grid_connection_mw", "contracted", "50.0"),
            ("curated:goodman-syd01-macquarie-park-data-centre:current-single-building-development", "critical_it_mw", "planned", "61.0"),
            ("curated:goodman-syd01-macquarie-park-data-centre:current-single-building-development", "grid_connection_mw", "contracted", "90.0"),
            ("curated:goodman-ty006-tokyo-data-centre-site:current-power-infrastructure-development", "critical_it_mw", "planned", "33.0"),
            ("curated:goodman-ty006-tokyo-data-centre-site:current-power-infrastructure-development", "gross_facility_mw", "planned", "50.0"),
        }
        self.assertEqual(observed, expected)
        self.assertFalse(any(row["metric"] == "annual_energy_mwh" for row in added_capacities))

        pipeline = {row["stable_key"]: row for row in rows(RELEASE / "construction_pipeline.csv")}
        expected_statuses = {
            "curated:coresite-de3-race-street-campus:de3": "under_construction",
            "curated:edged-atlanta-campus:atl01-03": "shell",
            "curated:edged-chicago-aurora-campus:ord01-2": "shell",
            "curated:flexential-parker-compark-campus:first-data-center": "shell",
            "curated:goodman-ams01-amsterdam-data-centre-campus:phase-1-current-development": "mep_electrical",
            "curated:goodman-fra02-frankfurt-data-centre-campus:phase-1-current-development": "under_construction",
            "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment": "under_construction",
            "curated:goodman-hkg10-tsuen-wan-data-centre:current-redevelopment": "under_construction",
            "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development": "mep_electrical",
            "curated:goodman-par01-paris-data-centre-campus:phase-1-current-development": "under_construction",
            "curated:goodman-par02-paris-data-centre-campus:phase-1-current-development": "mep_electrical",
            "curated:goodman-syd01-macquarie-park-data-centre:current-single-building-development": "under_construction",
            "curated:goodman-ty005-tokyo-data-centre-campus:phase-1-current-development": "mep_electrical",
            "curated:goodman-ty006-tokyo-data-centre-site:current-power-infrastructure-development": "under_construction",
        }
        self.assertEqual(
            {key: pipeline[key]["status"] for key in expected_statuses},
            expected_statuses,
        )
        self.assertEqual(
            pipeline["curated:coresite-de3-race-street-campus:de3"]["operating_model"],
            "colocation",
        )
        self.assertEqual(
            pipeline["curated:flexential-parker-compark-campus:first-data-center"]["operating_model"],
            "colocation",
        )
        for key in (
            "curated:edged-atlanta-campus:atl01-03",
            "curated:edged-chicago-aurora-campus:ord01-2",
        ):
            workloads = {
                row["workload"] for row in json.loads(pipeline[key]["workloads_json"])
            }
            self.assertEqual(workloads, {"ai_training", "ai_inference"})

    def test_manifest_summary_and_source_family_contract(self) -> None:
        manifest = json.loads((RELEASE / "manifest.json").read_text())
        summary = json.loads((RELEASE / "summary.json").read_text())
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["publication_contract_version"], 4)
        self.assertEqual(len(manifest["source_families"]), 178)
        self.assertEqual(
            {key: manifest[key] for key in (
                "entities",
                "entities_by_kind",
                "evidence_records",
                "capacity_estimates",
                "construction_pipeline_records",
                "construction_source_signals",
                "resolution_candidates",
            )},
            {
                "entities": 629,
                "entities_by_kind": {"campus": 340, "project": 289},
                "evidence_records": 352,
                "capacity_estimates": 467,
                "construction_pipeline_records": 327,
                "construction_source_signals": 235,
                "resolution_candidates": 4,
            },
        )
        self.assertEqual(summary["evidence_total"], 415)
        self.assertEqual(summary["entities_total"], 629)
        self.assertEqual(summary["projects_total"], 289)
        self.assertEqual(
            summary["entities_by_status"],
            {
                "announced": 5,
                "civil_works": 2,
                "commissioning": 1,
                "expansion": 27,
                "foundations": 2,
                "mep_electrical": 19,
                "operational": 35,
                "permitted": 3,
                "proposed": 2,
                "shell": 23,
                "site_preparation": 12,
                "under_construction": 231,
            },
        )

    def test_builder_refuses_collision_without_mutation(self) -> None:
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
        self.assertEqual(DEFINITION.read_bytes(), before_definition)
        self.assertEqual(tree_digest(RELEASE), before_tree)
        self.assertFalse((ROOT / ".open-seed-v49.lock").exists())

    def test_cli_both_layouts_and_v47_history(self) -> None:
        before = {
            BASE_DEFINITION: sha256(BASE_DEFINITION),
            BASE_RELEASE / "manifest.json": sha256(BASE_RELEASE / "manifest.json"),
        }
        command = [
            sys.executable,
            str(VALIDATOR),
            "--definition",
            str(DEFINITION),
            "--release",
            str(RELEASE),
        ]
        for cwd in (WORKSPACE, ROOT):
            result = subprocess.run(
                command,
                cwd=cwd,
                env={**os.environ, "PYTHONPATH": str(cwd)},
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "offline_rebuild_validate")
            self.assertEqual(payload["network_requests"], 0)
            self.assertEqual(payload["entities"], 629)
            self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)
        self.assertEqual(before[BASE_DEFINITION], BASE_DEFINITION_SHA256)
        self.assertEqual(before[BASE_RELEASE / "manifest.json"], BASE_MANIFEST_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256
        )
        self.assertEqual(stat.S_IMODE(BASE_RELEASE.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in BASE_RELEASE.iterdir()
            )
        )


if __name__ == "__main__":
    unittest.main()
