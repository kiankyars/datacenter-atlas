from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import csv
import gzip
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from datacenter_atlas.datacenter_atlas import construction_map_v11 as map_v11
    from datacenter_atlas.datacenter_atlas import construction_master_v11 as master_v11
    from datacenter_atlas.datacenter_atlas import coverage_audit_v3 as coverage_v3
except ModuleNotFoundError:
    from datacenter_atlas import construction_map_v11 as map_v11
    from datacenter_atlas import construction_master_v11 as master_v11
    from datacenter_atlas import coverage_audit_v3 as coverage_v3


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v27.json"
)
MASTER = ROOT / "construction_master/2026-07-21-public-open-v27"
BASE_MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-20-public-open-v26.json"
)
BASE_MASTER = ROOT / "construction_master/2026-07-20-public-open-v26"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-21-public-open-v27.json"
CONSTRUCTION_MAP = ROOT / "construction_maps/2026-07-21-public-open-v27"
BASE_MAP_DEFINITION = (
    ROOT / "sources/construction-map-2026-07-20-public-open-v26.json"
)
BASE_MAP = ROOT / "construction_maps/2026-07-20-public-open-v26"
COVERAGE_DEFINITION = (
    ROOT / "sources/coverage-audit-2026-07-21-public-open-v27.json"
)
COVERAGE = ROOT / "audits/2026-07-21-public-open-coverage-v27"
BASE_COVERAGE_DEFINITION = (
    ROOT / "sources/coverage-audit-2026-07-20-public-open-v26.json"
)
BASE_COVERAGE = ROOT / "audits/2026-07-20-public-open-coverage-v26"
V62 = ROOT / "releases/2026-07-20-open-seed-v62"
V67_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v67.json"
V67 = ROOT / "releases/2026-07-21-open-seed-v67"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v28.json"
FEDERATION = ROOT / "federated_indexes/2026-07-21-public-open-v28"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v6.json"
)
IDENTITY = ROOT / "exact_identity_decisions/2026-07-21-public-open-v6"

MASTER_GENERATED_AT = "2026-07-21T08:05:00Z"
MAP_GENERATED_AT = "2026-07-21T08:05:01Z"
COVERAGE_GENERATED_AT = "2026-07-21T08:10:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v62"
NEW_RELEASE_ID = "epoch-official-open-seed-v67"

FILE_PINS = {
    MASTER_DEFINITION: (
        5_659,
        "c0f2a5c89e44838da876d7629dc39f49bdaa497d882a2826fff92e6e7080198b",
    ),
    ROOT / "datacenter_atlas/construction_master_v10.py": (
        2_774,
        "d77c8bd461ea0365708b56a0f55596f9d581ed8a1f520181e85cba78775926bb",
    ),
    ROOT / "datacenter_atlas/construction_master_v11.py": (
        2_921,
        "1ac853a00cd0279c56d14b767cadbe8a6e4e6df256d3ec6b73b4bcf3ff5b88af",
    ),
    ROOT / "construction_master_v11.py": (
        241,
        "437d0d3da0c839250f37064dc08213d51660e44881d369cc98c7d39e3af78fc5",
    ),
    ROOT / "scripts/build_construction_master_v11.py": (
        1_872,
        "e9e06ff8f3c36299e56eca0b5b9cb70910a226e93745a7a7e9845e06717fd465",
    ),
    MAP_DEFINITION: (
        2_442,
        "a7d62e22778ce4c70e5fbe015e67b5cf2702f19862dc63d93896d669bf4638f4",
    ),
    ROOT / "datacenter_atlas/construction_map_v10.py": (
        2_764,
        "b91ee693bac8c3d627ed5ec126eca66efe2c6e421481c888c47f12e074bb7311",
    ),
    ROOT / "datacenter_atlas/construction_map_v11.py": (
        2_860,
        "20ba327d39af80ba7eb14f5b2d52197285e7372a0821ecb3a19817a49c336041",
    ),
    ROOT / "construction_map_v11.py": (
        235,
        "ce1367606c33e5dd4ae2397f841f63d5c5fca1fa5380bf45c7639f30a2f60deb",
    ),
    ROOT / "scripts/build_construction_map_v11.py": (
        2_020,
        "5f0481d6f7d0a57d8369be63897cb27161b9cae08b15dd0497971ed5d12ea033",
    ),
    COVERAGE_DEFINITION: (
        5_920,
        "0224660dd28426c51eb5a76d1264e46b7da629f42d9de2648296b0b0f7b6e9ec",
    ),
    ROOT / "datacenter_atlas/coverage_audit_v3.py": (
        1_516,
        "953742175b8dbb15cc42ff577e2eff1f2d86d82782692a369c7c3a318bc24205",
    ),
    ROOT / "coverage_audit_v3.py": (
        137,
        "789a66ce0a7f0b1106c470305ff8503f17d425fd0c6e72c13d25d71ecd2cd414",
    ),
    ROOT / "scripts/build_coverage_audit_v3.py": (
        1_456,
        "72abbc8885621e17f710854ed050e95ef9810cfa7599ba2f2d1865e8b620e2ba",
    ),
    V67_DEFINITION: (
        83_386,
        "c19fbd69beda335266809e37e9eb252ebd7561a0389cae44a607384bd6790fc5",
    ),
    V67 / "manifest.json": (
        12_274,
        "38ba82bfc042a28e0401f79bedd7114decacf1901fe5fd1670ec476d3848a2eb",
    ),
    FEDERATION_DEFINITION: (
        1_788,
        "6dbc1095c7fd8b6d36e217263aac23b0c612e84b7d781fa5cc32fbaa2c4e57d9",
    ),
    FEDERATION / "manifest.json": (
        986,
        "d465a2de75b94168113b712740a1761e93887c1bc998a5164ba54489202e5f6e",
    ),
    IDENTITY_DEFINITION: (
        1_735,
        "2b9b26f452ebfc3d36f4bb36d9cc7198a29b8be8806657750f440a928671d759",
    ),
    IDENTITY / "manifest.json": (
        11_438,
        "0af1e65f5b772b87e7dfe5b5c195513e79f31d4b5648fdcae5fd343f86f82ee9",
    ),
}

OUTPUT_PINS = {
    MASTER: {
        "ATTRIBUTION.txt": (
            5_814,
            "98ffd48f9e14cb0e128ba165d5677ce7079899c29a9b3f38b5c6e44bb418e67f",
        ),
        "README.md": (
            1_349,
            "ab447e269942beca6f2841d1a0b82cd1ef87a88447f49e6e30408a2d406d258d",
        ),
        "construction-master.csv": (
            189_870_775,
            "499b1b2b6c02764ecf1e8322dde38ea50bad65e5779580398963310a862bf3e0",
        ),
        "construction-master.jsonl": (
            325_731_613,
            "23b926f0a8ed0a425a49b2fdd0e4c595b83489a1d6e3bb2761be11bcab28c3c2",
        ),
        "coverage.json": (
            8_550,
            "8df2ba8c2211b0b55a363088b22ca14c5a6b508d6788dcae7e804a1ca6050635",
        ),
        "manifest.json": (
            9_720,
            "6a5f48a0c86220c66d13fc1bd0ec7a9716e624d3d952599e3b6660e07717f5e7",
        ),
        "manifest.sha256": (
            80,
            "865ee7ad251622d0ffa40ab340b6f849d0dd67ba26696d25841cc392f5577116",
        ),
    },
    CONSTRUCTION_MAP: {
        "ATTRIBUTION.txt": (
            365,
            "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
        ),
        "README.md": (
            518,
            "8dcbbf466a57edd3401736982fab1e601cf3a51e60141e4253389ed3cc40be31",
        ),
        "construction-map-index.json.gz": (
            6_680_053,
            "692c04029f979c0df648d095f123dbc360adfcf671e165af5529eb3edd3f51b2",
        ),
        "construction-map.html": (
            8_924_348,
            "bb3edac26b64f3ad89f2379725223285d2bd78178855fd2261b91a4d2a835330",
        ),
        "coverage.json": (
            7_465,
            "02edcf096c49e8e164b03f6270b38603c4464d3070198d11e69165c4002e8438",
        ),
        "manifest.json": (
            2_192,
            "7115033102529e7dcca992960948463ead7f7d74a717510fdddbcfa2e89c6c38",
        ),
        "manifest.sha256": (
            80,
            "d4c05dd9d9fc02e0d124436c8d191e511c3cc0bd054995e7561f08814789de6d",
        ),
    },
    COVERAGE: {
        "REPORT.md": (
            4_763,
            "2ce5a713a24f30ff5762ca222e71ea0aa0a33a23794264cdaa3e11f9adbfadb9",
        ),
        "coverage-audit.json": (
            2_666_154,
            "a1d7dd0c3349360904158132466e8722b6900a41584b16daee7d3ce16236e666",
        ),
        "coverage.csv": (
            363_536,
            "3d827ae52d130a842c062ba0d792f58b231c3c9635cdd835b416269be5a0ffca",
        ),
        "gap-registry.json": (
            2_059_776,
            "cef023e9f739e1f5e364b3a169eb2a48f10a10d90607c2b055c39859ef970075",
        ),
        "manifest.json": (
            3_379,
            "fc3c4af31d6f37f103d08ca4f1e9f78fa87a82e692c9abd19ddd9002176be64f",
        ),
        "manifest.sha256": (
            80,
            "7a79c96916362ff1eb12e07cab18765178404fce6a4297291ac64856580dadc0",
        ),
    },
}

TREE_PINS = {
    MASTER: "15f5a8c5630faa28c45c7aaa4cb4cd212b472441db4c9e3a9daf80fb23bc25a9",
    CONSTRUCTION_MAP: (
        "55a9811b96d5d644f325c4b82082c8c96c60c21011302fd43ed0e07b76fb665d"
    ),
    COVERAGE: "a2f945f421e22776633c0dc5960301d429ef629882e7361204cd35912ab764e1",
    FEDERATION: "88113b5342b48be3dbe663bdc4da2fe57a5de75c983220f42e2ccc822b3f501a",
    IDENTITY: "44057ef4e03b3ce4412fb4d89b7e673cf9da8a289eb13ecbca6e11dcb9a4505d",
}

EXPECTED_MASTER = {
    "added_replacement_rows": 202,
    "added_source_record_ids_sha256": (
        "cb50c4a8eb0b94503ea7832bf7843fff88c55e9c438f744d78e2e86c837e94df"
    ),
    "base_replaced_rows": 199,
    "base_replaced_source_record_ids_sha256": (
        "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950"
    ),
    "base_rows": 109_111,
    "inherited_rows": 108_912,
    "inherited_rows_without_roles_sha256": (
        "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f"
    ),
    "replacement_role_projection_sha256": (
        "21cc79fd2dd1039f6d80cf05f553f0d90887db62543f0dff4567c41ecd3bc7ec"
    ),
    "replacement_rows": 401,
    "replacement_rows_with_any_role": 142,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 58,
    "replacement_rows_with_owner": 48,
    "replacement_rows_with_source_role_tags": 103,
    "replacement_rows_with_tenants": 7,
    "replacement_rows_with_users": 36,
    "replacement_rows_without_roles_sha256": (
        "3a28bef872e0f960d07539161e1364ac0619c744fd8dba8608d4e4f2ec13a1ff"
    ),
    "replacement_source_record_ids_sha256": (
        "a73974c823e653f1635be48fa27027ad3260d043bd2f9f2308b3da9f0468cab5"
    ),
    "rows_with_contract_marker": 401,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_arithmetic_projection_sha256": (
        "8eb646d1b2b86939932287ea4c0f7c730e35e825cef89392054a1cf17d0e40ee"
    ),
    "tier_a_rows": 521,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_313,
    "unchanged_replacement_rows": 199,
}

EXPECTED_MAP = {
    "added_replacement_rows_unmapped": 189,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "e6aeb2083faca56c59fcdc66f2c9846aa0b3de013e0ce11eea58da89e20c5aa1"
    ),
    "default_visible_rows": 6_499,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 219, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 100,
    "mapped_rows": 108_993,
    "mapped_rows_with_any_role": 75,
    "master_rows": 109_313,
    "unmapped_rows": 320,
    "unmapped_source_record_ids_sha256": (
        "1f0cfed2294f9b5e6281fe12d9699f1ccff1888d764bf204a153b0a2ddeda17e"
    ),
}

EXPECTED_COVERAGE_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 816,
    "methodology_support_artifacts": 1,
    "methodology_support_jobs": 74,
    "methodology_support_views": 71,
    "non_review_source_scoped_entity_records": 10_078,
    "open_gaps": 3_959,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_208,
    "unique_physical_sites": None,
}

DISCOVERY_PATHS = {
    "source_artifacts/global-underrepresented-official-discovery-2026-07-21-v1",
    "source_artifacts/second-underrepresented-official-discovery-2026-07-21-v1",
    "sources/curated-official-2026-07-21-azerbaijan-undisclosed-new-data-center.json",
    "sources/curated-official-2026-07-21-firebird-ai-center-hrazdan-current-build.json",
    "sources/curated-official-2026-07-21-green-mountain-fra-mainz-current-build.json",
    "sources/curated-official-2026-07-21-harch-dakhla-groundbreaking.json",
    "sources/curated-official-2026-07-21-scala-sbogzb01-bogota-current-build.json",
    "sources/curated-official-2026-07-21-scala-sforpf01-fortaleza-current-build.json",
    "sources/curated-official-2026-07-21-scala-sgrutb07-tambore-current-build.json",
    "sources/curated-official-2026-07-21-scala-sgrutb09-tambore-current-build.json",
    "sources/curated-official-2026-07-21-scala-sgrutb10-tambore-current-build.json",
    "sources/curated-official-2026-07-21-scala-sgrutb11-tambore-current-build.json",
    "sources/curated-official-2026-07-21-scala-smextp02-tepotzotlan-current-build.json",
    "sources/curated-official-2026-07-21-scala-ssclhb01-huechuraba-current-build.json",
    "sources/curated-official-2026-07-21-scala-sscllp01-lampa-current-build.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"tree contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{path.stat().st_size}\0"
                    f"{sha256(path)}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported tree entry: {relative}")
    return digest.hexdigest()


def pipeline_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return {row["entity_id"]: row for row in csv.DictReader(source)}


def map_rows(path: Path) -> dict[str, dict[str, object]]:
    document = json.loads(gzip.decompress(path.read_bytes()))
    return {
        str(values["source_record_id"]): values
        for row in document["rows"]
        if (values := dict(zip(map_v11.FIELDS, row, strict=True)))
    }


class DownstreamV67CheckpointTests(unittest.TestCase):
    maxDiff = 20_000

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("downstream v67 checkpoint attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_frozen_pins_modes_trees_and_carriers_are_exact(self) -> None:
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        for directory, artifacts in OUTPUT_PINS.items():
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o555)
            self.assertEqual({path.name for path in directory.iterdir()}, set(artifacts))
            for name, expected in artifacts.items():
                path = directory / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
                self.assertEqual(checkpoint(path), expected)
        for directory, expected in TREE_PINS.items():
            self.assertEqual(tree_digest(directory), expected, directory)

        self.assertIn(
            FILE_PINS[ROOT / "datacenter_atlas/construction_master_v10.py"][1],
            (ROOT / "datacenter_atlas/construction_master_v11.py").read_text(),
        )
        self.assertIn(
            FILE_PINS[ROOT / "datacenter_atlas/construction_map_v10.py"][1],
            (ROOT / "datacenter_atlas/construction_map_v11.py").read_text(),
        )

    def test_master_is_exact_v26_successor_with_only_v67_replacement(self) -> None:
        base = json.loads(BASE_MASTER_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(MASTER_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["master_id"] = "2026-07-21-public-open-v27"
        expected["generated_at"] = MASTER_GENERATED_AT
        expected["expected"] = EXPECTED_MASTER
        expected["inputs"]["replacement_release"] = current["inputs"][
            "replacement_release"
        ]
        self.assertEqual(MASTER_DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        self.assertEqual(current["scope"], base["scope"])
        self.assertEqual(
            current["inputs"]["base_master"], base["inputs"]["base_master"]
        )
        self.assertEqual(
            current["inputs"]["satellite_recovery_acceptance"],
            base["inputs"]["satellite_recovery_acceptance"],
        )

        replacement = current["inputs"]["replacement_release"]
        expected_inputs = {
            "data": V67 / "construction_pipeline.csv",
            "definition": V67_DEFINITION,
            "evidence": V67 / "evidence.csv",
            "manifest": V67 / "manifest.json",
        }
        for key, path in expected_inputs.items():
            self.assertEqual(
                (replacement[key]["bytes"], replacement[key]["sha256"]),
                checkpoint(path),
            )
        self.assertEqual(replacement["artifact_id"], NEW_RELEASE_ID)
        self.assertEqual(replacement["release_id"], NEW_RELEASE_ID)
        self.assertEqual(replacement["publication_contract_version"], 4)

        definition, _raw, _root, _resolved, context = master_v11.validate_definition(
            MASTER_DEFINITION
        )
        self.assertEqual(definition["expected"], EXPECTED_MASTER)
        self.assertEqual(context["recovery"]["control_plane_bytes"], 15_313)
        self.assertEqual(context["recovery"]["rows_created"], 0)
        self.assertFalse(context["recovery"]["payload_traversed"])
        manifest = master_v11.validate_construction_master_v11(
            MASTER, definition_path=MASTER_DEFINITION, reproduce=False
        )
        self.assertEqual(manifest["row_counts"]["total"], 109_313)
        self.assertEqual(
            manifest["row_counts"]["by_tier"], {"A": 521, "B": 6_298, "C": 102_494}
        )
        self.assertIsNone(manifest["row_counts"]["unique_physical_site_count"])

        old_pipeline = pipeline_rows(V62 / "construction_pipeline.csv")
        new_pipeline = pipeline_rows(V67 / "construction_pipeline.csv")
        self.assertEqual((len(old_pipeline), len(new_pipeline)), (373, 401))
        self.assertEqual(len(set(new_pipeline) - set(old_pipeline)), 28)
        self.assertFalse(set(old_pipeline) - set(new_pipeline))
        changed = {
            record_id
            for record_id in set(old_pipeline) & set(new_pipeline)
            if old_pipeline[record_id] != new_pipeline[record_id]
        }
        self.assertEqual(
            changed,
            {
                "65e8849e-2ebe-5d58-be63-299cbbcf8d23",
                "b8399bc6-5c72-5627-a035-4fea208cd287",
            },
        )
        self.assertTrue(
            all(
                new_pipeline[record_id]["latitude"]
                and new_pipeline[record_id]["longitude"]
                and new_pipeline[record_id]["source_url"]
                for record_id in changed
            )
        )

        with (
            (BASE_MASTER / "construction-master.jsonl").open("rb") as old_source,
            (MASTER / "construction-master.jsonl").open("rb") as new_source,
        ):
            for _ in range(373):
                next(old_source)
            for _ in range(401):
                next(new_source)
            for old_line, new_line in zip_longest(old_source, new_source):
                self.assertEqual(old_line, new_line)

    def test_map_is_exact_v26_successor_and_adds_only_v67_coordinates(self) -> None:
        base = json.loads(BASE_MAP_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(MAP_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["map_id"] = "2026-07-21-public-open-v27-construction-map-v2"
        expected["generated_at"] = MAP_GENERATED_AT
        expected["expected_projection"] = EXPECTED_MAP
        expected["master"] = current["master"]
        self.assertEqual(MAP_DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        self.assertEqual(current["scope"], base["scope"])
        self.assertEqual(current["template"], base["template"])

        validated = map_v11.validate_map_definition_v11(
            MAP_DEFINITION,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
        )
        self.assertEqual(validated["expected_projection"], EXPECTED_MAP)
        manifest = map_v11.validate_construction_map_v11(
            CONSTRUCTION_MAP,
            master_directory=MASTER,
            master_definition_path=MASTER_DEFINITION,
            map_definition_path=MAP_DEFINITION,
            reproduce=False,
        )
        self.assertEqual(manifest["master"]["rows"], 109_313)
        self.assertIsNone(manifest["scope"]["unique_physical_site_count"])
        self.assertFalse(manifest["scope"]["entity_merges_created"])
        self.assertTrue(manifest["scope"]["map_rows_are_observations_not_unique_sites"])

        old_rows = map_rows(BASE_MAP / "construction-map-index.json.gz")
        new_rows = map_rows(CONSTRUCTION_MAP / "construction-map-index.json.gz")
        for record_id, old_row in old_rows.items():
            current_row = dict(new_rows[record_id])
            if old_row["source_artifact_id"] == OLD_RELEASE_ID:
                current_row.update(
                    {
                        "row_id": old_row["row_id"],
                        "source_artifact_id": OLD_RELEASE_ID,
                        "source_release_id": OLD_RELEASE_ID,
                    }
                )
            self.assertEqual(current_row, old_row, record_id)
        added = set(new_rows) - set(old_rows)
        self.assertEqual(
            added,
            {
                "65e8849e-2ebe-5d58-be63-299cbbcf8d23",
                "b8399bc6-5c72-5627-a035-4fea208cd287",
                "8f7e4a93-adc0-5863-a470-00fa072ba88a",
                "357b7fdb-d73e-517e-82a9-fb1babd5c986",
                "0fe3b8df-03a0-57f5-86a0-a21e13116c7e",
                "1fbc2ccf-c972-5ccd-a202-fb9e2d6f7adc",
            },
        )
        pipeline = pipeline_rows(V67 / "construction_pipeline.csv")
        for record_id in added:
            self.assertEqual(
                str(new_rows[record_id]["latitude"]),
                pipeline[record_id]["latitude"],
            )
            self.assertEqual(
                str(new_rows[record_id]["longitude"]),
                pipeline[record_id]["longitude"],
            )
            self.assertEqual(new_rows[record_id]["source_url"], pipeline[record_id]["source_url"])
            self.assertTrue(new_rows[record_id]["source_publisher"])
            self.assertTrue(pipeline[record_id]["source_publisher"])

    def test_coverage_is_exact_v26_successor_with_review_and_nonclaims_intact(
        self,
    ) -> None:
        base_definition = json.loads(
            BASE_COVERAGE_DEFINITION.read_text(encoding="utf-8")
        )
        current_definition = json.loads(
            COVERAGE_DEFINITION.read_text(encoding="utf-8")
        )
        expected = deepcopy(base_definition)
        expected["as_of"] = "2026-07-21"
        expected["audit_id"] = "public-open-coverage-v27"
        expected["generated_at"] = COVERAGE_GENERATED_AT
        child = next(
            row for row in expected["children"] if row["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": FILE_PINS[V67 / "manifest.json"][1],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-21-open-seed-v67",
            }
        )
        expected["federated_index"] = {
            "expected_manifest_sha256": FILE_PINS[FEDERATION / "manifest.json"][1],
            "path": "../federated_indexes/2026-07-21-public-open-v28",
        }
        for references in expected["methodology_evidence_classification"].values():
            for reference in references:
                if reference["release_id"] == OLD_RELEASE_ID:
                    reference["release_id"] = NEW_RELEASE_ID
        self.assertEqual(COVERAGE_DEFINITION.read_bytes(), canonical_json(current_definition))
        self.assertEqual(current_definition, expected)
        self.assertEqual(
            current_definition["methodology_support_artifacts"],
            base_definition["methodology_support_artifacts"],
        )
        self.assertEqual(
            current_definition["public_benchmark"], base_definition["public_benchmark"]
        )

        base_manifest = json.loads(
            (BASE_COVERAGE / "manifest.json").read_text(encoding="utf-8")
        )
        coverage_v3.validate_coverage_audit(
            COVERAGE, definition_path=COVERAGE_DEFINITION
        )
        manifest = json.loads(
            (COVERAGE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["counts"], EXPECTED_COVERAGE_COUNTS)
        self.assertEqual(
            {
                key: manifest["counts"][key] - base_manifest["counts"][key]
                for key in (
                    "coverage_groups",
                    "non_review_source_scoped_entity_records",
                    "open_gaps",
                    "review_only_source_scoped_entity_records",
                    "source_scoped_entity_records",
                )
            },
            {
                "coverage_groups": 62,
                "non_review_source_scoped_entity_records": 53,
                "open_gaps": 223,
                "review_only_source_scoped_entity_records": 0,
                "source_scoped_entity_records": 53,
            },
        )

        base_audit = json.loads(
            (BASE_COVERAGE / "coverage-audit.json").read_text(encoding="utf-8")
        )
        audit = json.loads(
            (COVERAGE / "coverage-audit.json").read_text(encoding="utf-8")
        )
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            old_groups = [
                row
                for row in base_audit["groups"]
                if row["child_release"] == release_id
            ]
            new_groups = [
                row for row in audit["groups"] if row["child_release"] == release_id
            ]
            self.assertEqual(len(new_groups), len(old_groups))
            for old_group, new_group in zip(old_groups, new_groups, strict=True):
                old_without_freshness = dict(old_group)
                new_without_freshness = dict(new_group)
                old_without_freshness.pop("status_freshness_counts")
                new_without_freshness.pop("status_freshness_counts")
                self.assertEqual(new_without_freshness, old_without_freshness)
        self.assertEqual(
            audit["inputs"]["methodology_support_artifacts"],
            base_audit["inputs"]["methodology_support_artifacts"],
        )
        self.assertEqual(
            audit["lifecycle_contract"],
            {
                "current_status_classification": "unknown",
                "current_status_inferred": False,
                "publication_v4_children": [
                    {
                        "current_status_inferred": False,
                        "lifecycle_freshness_records": 443,
                        "lifecycle_status_semantics": "last_observed",
                        "publication_contract_version": 4,
                        "release_id": NEW_RELEASE_ID,
                    }
                ],
                "status_semantics": "last_observed",
            },
        )
        self.assertFalse(audit["scope"]["current_status_inferred"])
        self.assertFalse(audit["scope"]["children_merged"])
        self.assertFalse(audit["scope"]["cross_source_deduplication"])
        self.assertFalse(audit["scope"]["review_candidates_promoted"])
        self.assertTrue(audit["scope"]["review_only_rows_separately_counted"])
        self.assertIsNone(audit["scope"]["unique_physical_sites"])
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        self.assertEqual(
            audit["semianalysis_public_comparison"]["overall_parity"]["status"],
            "pending",
        )
        report = (COVERAGE / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("dated observations, not current-status assertions", report)
        self.assertIn("Unique physical sites: **unknown**", report)
        self.assertIn("SemiAnalysis parity determination: **pending**", report)

    def test_v67_federation_identity_lineage_and_discovery_exclusion(self) -> None:
        federation = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        descriptor = next(
            row for row in federation["releases"] if row["release_id"] == NEW_RELEASE_ID
        )
        self.assertEqual(descriptor["manifest"]["sha256"], FILE_PINS[V67 / "manifest.json"][1])
        self.assertEqual(descriptor["manifest"]["lifecycle_freshness_records"], 443)
        self.assertFalse(descriptor["manifest"]["current_status_inferred"])
        identity_definition = json.loads(IDENTITY_DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(
            identity_definition["federation"],
            {
                "expected_index_sha256": (
                    "d21cfa01157dc7529d71bfd99d4f6d2bbc74285a8c58392ee402dc767faf3210"
                ),
                "expected_manifest_sha256": FILE_PINS[FEDERATION / "manifest.json"][1],
                "index_path": "../federated_indexes/2026-07-21-public-open-v28",
            },
        )
        identity_child = next(
            row
            for row in identity_definition["children"]
            if row["release_id"] == NEW_RELEASE_ID
        )
        self.assertEqual(
            identity_child["expected_manifest_sha256"],
            FILE_PINS[V67 / "manifest.json"][1],
        )

        v67_definition = json.loads(V67_DEFINITION.read_text(encoding="utf-8"))
        curated_inputs = {row["path"] for row in v67_definition["curated_inputs"]}
        self.assertTrue(
            {
                marker
                for marker in DISCOVERY_PATHS
                if marker.startswith("sources/")
            }.isdisjoint(curated_inputs)
        )
        serialized = b"\n".join(
            path.read_bytes()
            for path in (
                MASTER_DEFINITION,
                MAP_DEFINITION,
                COVERAGE_DEFINITION,
                MASTER / "manifest.json",
                CONSTRUCTION_MAP / "manifest.json",
                COVERAGE / "manifest.json",
            )
        )
        for marker in DISCOVERY_PATHS:
            self.assertNotIn(marker.encode(), serialized)

    def test_offline_double_replay_is_byte_exact(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="downstream-v67-replay-", dir="/private/tmp"
            ) as temporary,
            ExitStack() as stack,
        ):
            self._offline(stack)
            root = Path(temporary)
            master_snapshots = []
            for name in ("master-one", "master-two"):
                output = root / name
                master_v11.write_construction_master_v11(
                    MASTER_DEFINITION, output, freeze=True
                )
                master_snapshots.append(
                    {path.name: checkpoint(path) for path in output.iterdir()}
                )
                self.assertEqual(tree_digest(output), TREE_PINS[MASTER])
            self.assertEqual(master_snapshots[0], master_snapshots[1])
            self.assertEqual(master_snapshots[0], OUTPUT_PINS[MASTER])

            map_snapshots = []
            for name in ("map-one", "map-two"):
                output = root / name
                map_v11.write_construction_map_v11(
                    MASTER,
                    output,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                    freeze=True,
                )
                map_snapshots.append(
                    {path.name: checkpoint(path) for path in output.iterdir()}
                )
                self.assertEqual(tree_digest(output), TREE_PINS[CONSTRUCTION_MAP])
            self.assertEqual(map_snapshots[0], map_snapshots[1])
            self.assertEqual(map_snapshots[0], OUTPUT_PINS[CONSTRUCTION_MAP])

            first = coverage_v3.build_coverage_audit(COVERAGE_DEFINITION)
            second = coverage_v3.build_coverage_audit(COVERAGE_DEFINITION)
            self.assertEqual(dict(first.payloads), dict(second.payloads))
            output = root / "coverage"
            written = coverage_v3.write_coverage_audit(COVERAGE_DEFINITION, output)
            self.assertEqual(written["audit_id"], "public-open-coverage-v27")
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()},
                dict(first.payloads),
            )
            self.assertEqual(tree_digest(output), TREE_PINS[COVERAGE])

    def test_collision_tamper_and_symlink_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="downstream-v67-fail-closed-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            collision = root / "collision"
            collision.write_bytes(b"do-not-replace\n")
            with self.assertRaises(master_v11.ConstructionMasterV11Error):
                master_v11.write_construction_master_v11(
                    MASTER_DEFINITION, collision
                )
            self.assertEqual(collision.read_bytes(), b"do-not-replace\n")

            linked_master = root / "linked-master"
            linked_master.symlink_to(MASTER, target_is_directory=True)
            with self.assertRaises(master_v11.ConstructionMasterV11Error):
                master_v11.write_construction_master_v11(
                    MASTER_DEFINITION, linked_master
                )

            linked_map = root / "linked-map"
            linked_map.symlink_to(CONSTRUCTION_MAP, target_is_directory=True)
            with self.assertRaises(map_v11.ConstructionMapV11Error):
                map_v11.write_construction_map_v11(
                    MASTER,
                    linked_map,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=MAP_DEFINITION,
                )

            linked_coverage = root / "linked-coverage"
            linked_coverage.symlink_to(COVERAGE, target_is_directory=True)
            with self.assertRaisesRegex(
                coverage_v3.CoverageAuditError, "may not be a symlink"
            ):
                coverage_v3.write_coverage_audit(
                    COVERAGE_DEFINITION, linked_coverage
                )

            master_document = json.loads(MASTER_DEFINITION.read_text(encoding="utf-8"))
            master_document["scope"]["unique_physical_site_count"] = 401
            bad_master = root / "bad-master.json"
            bad_master.write_bytes(canonical_json(master_document))
            with self.assertRaisesRegex(
                master_v11.ConstructionMasterV11Error,
                "identity or scope changed",
            ):
                master_v11.validate_definition(bad_master)

            map_document = json.loads(MAP_DEFINITION.read_text(encoding="utf-8"))
            map_document["scope"]["entity_merges_created"] = True
            bad_map = ROOT / "sources/.test-bad-map-v27.json"
            try:
                bad_map.write_bytes(canonical_json(map_document))
                with self.assertRaisesRegex(
                    map_v11.ConstructionMapV11Error,
                    "identity or scope changed",
                ):
                    map_v11.validate_map_definition_v11(
                        bad_map,
                        master_directory=MASTER,
                        master_definition_path=MASTER_DEFINITION,
                    )
            finally:
                bad_map.unlink(missing_ok=True)

            coverage_document = json.loads(
                COVERAGE_DEFINITION.read_text(encoding="utf-8")
            )
            coverage_document["federated_index"]["expected_manifest_sha256"] = (
                "0" * 64
            )
            bad_coverage = ROOT / "sources/.test-bad-coverage-v27.json"
            try:
                bad_coverage.write_bytes(canonical_json(coverage_document))
                with self.assertRaisesRegex(
                    coverage_v3.CoverageAuditError,
                    "manifest SHA-256 does not match",
                ):
                    coverage_v3.build_coverage_audit(bad_coverage)
            finally:
                bad_coverage.unlink(missing_ok=True)

            tampered = root / "tampered-coverage"
            shutil.copytree(COVERAGE, tampered)
            tampered.chmod(0o755)
            report = tampered / "REPORT.md"
            report.chmod(0o644)
            report.write_bytes(report.read_bytes() + b"tamper\n")
            report.chmod(0o444)
            tampered.chmod(0o555)
            with self.assertRaisesRegex(
                coverage_v3.CoverageAuditError, "artifact checkpoint mismatch"
            ):
                coverage_v3.validate_coverage_audit(tampered)

    def test_cli_and_parent_nested_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "UV_OFFLINE": "1"}
        commands = (
            [
                sys.executable,
                "scripts/build_construction_master_v11.py",
                "--definition",
                str(MASTER_DEFINITION),
                "--output",
                str(MASTER),
                "--validate-only",
            ],
            [
                sys.executable,
                "scripts/build_construction_map_v11.py",
                "--master-dir",
                str(MASTER),
                "--master-definition",
                str(MASTER_DEFINITION),
                "--map-definition",
                str(MAP_DEFINITION),
                "--output-dir",
                str(CONSTRUCTION_MAP),
                "--validate-only",
            ],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        code = (
            "from pathlib import Path; "
            "from datacenter_atlas import construction_master_v11 as a; "
            "from datacenter_atlas import construction_map_v11 as b; "
            "from datacenter_atlas import coverage_audit_v3 as c; "
            f"m=a.validate_construction_master_v11(Path({str(MASTER)!r}),"
            f"definition_path=Path({str(MASTER_DEFINITION)!r}),reproduce=False); "
            f"p=b.validate_construction_map_v11(Path({str(CONSTRUCTION_MAP)!r}),"
            f"master_directory=Path({str(MASTER)!r}),"
            f"master_definition_path=Path({str(MASTER_DEFINITION)!r}),"
            f"map_definition_path=Path({str(MAP_DEFINITION)!r}),reproduce=False); "
            f"q=c.validate_coverage_audit(Path({str(COVERAGE)!r})); "
            "assert m['row_counts']['total']==109313; "
            "assert p['master']['rows']==109313; "
            "assert q['totals']['source_scoped_entity_records']==16208; "
            "assert q['totals']['unique_physical_sites'] is None"
        )
        for working_directory in (ROOT, WORKSPACE):
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=working_directory,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
