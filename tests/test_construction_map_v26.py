from __future__ import annotations

from contextlib import ExitStack
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_map_v10 as map_v10
from datacenter_atlas.construction_map_v10 import (
    ConstructionMapV10Error,
    validate_construction_map_v10,
    validate_map_definition_v10,
    write_construction_map_v10,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v26.json"
MAP = ROOT / "construction_maps/2026-07-20-public-open-v26"
BASE_DEFINITION = ROOT / "sources/construction-map-2026-07-20-public-open-v25.json"
BASE_MAP = ROOT / "construction_maps/2026-07-20-public-open-v25"
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-20-public-open-v26.json"
)
MASTER = ROOT / "construction_master/2026-07-20-public-open-v26"
BASE_MASTER = ROOT / "construction_master/2026-07-20-public-open-v25"
V62_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v5.json"
)
IDENTITY = ROOT / "exact_identity_decisions/2026-07-20-public-open-v5"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v27"

GENERATED_AT = "2026-07-21T05:05:01Z"
IAD5_ID = "47239c82-4e96-5033-b329-14a6e7311750"
REMOVED_STC_ID = "582fa8ba-66b8-56d1-95af-de41a4628dc0"

FILE_PINS = {
    BASE_DEFINITION: (
        2_441,
        "00b7dc30961cbe09cbdb826c9181dddf4d4e8235ca50eaf1d8b97701eb4b5a88",
    ),
    BASE_MAP / "manifest.json": (
        2_192,
        "20e46d30fcde26b4e8fa1ede55e24235b4a9a7d808e85411d3174d374c50d001",
    ),
    ROOT / "datacenter_atlas/construction_map_v9.py": (
        2_611,
        "cdb2cf235fc053b00d093874d1ca024dffdb4ba09fe5c89ad3c97168c483249b",
    ),
    ROOT / "construction_map_v9.py": (
        233,
        "df62d6f9e0eb46e8647fd630050fd0a5002627ebb3b67de1f438f4c7c3db66ab",
    ),
    ROOT / "scripts/build_construction_map_v9.py": (
        2_012,
        "93676524510a966bdc64d418273d4e462d1018cac3042aa03eadb834f9974b45",
    ),
    ROOT / "datacenter_atlas/construction_map_v10.py": (
        2_764,
        "b91ee693bac8c3d627ed5ec126eca66efe2c6e421481c888c47f12e074bb7311",
    ),
    ROOT / "construction_map_v10.py": (
        235,
        "7f47122e303748af373812b5c71b9c65246dbcc6e1c4a9df2cd0c40ad263e82a",
    ),
    ROOT / "scripts/build_construction_map_v10.py": (
        2_020,
        "c6e5bd2c5eb3467a91bdf7eec49e107ddf0258fdfeb23966e95a9137cb0c5c09",
    ),
    DEFINITION: (
        2_441,
        "3829254804d1377f7df74a92cd860db80d22e7b206ce4fd63214cbd1dd901d13",
    ),
    MASTER_DEFINITION: (
        5_658,
        "ede029f2fa2ecb6371b311de6497e0eda2dc38d23752a8ec1efc2760b27dda45",
    ),
    MASTER / "manifest.json": (
        9_720,
        "f5895210b32b0307dc1cc12791541024bdb9dc39532ff2ebff0f669d9442bb82",
    ),
    V62_DEFINITION: (
        76_824,
        "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66",
    ),
    V62_RELEASE / "manifest.json": (
        10_934,
        "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6",
    ),
    IDENTITY_DEFINITION: (
        1_735,
        "c5a33ae467c2187157d5799a17d81f08c49d623926303641ebb21cd15f7192d7",
    ),
    IDENTITY / "manifest.json": (
        11_438,
        "9bb5c1ef49fe1bf3904c2dca080ef5ab51de014935f1792a2bc99c0888bb68b5",
    ),
    FEDERATION / "federated-index.json": (
        27_784,
        "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8",
    ),
    FEDERATION / "manifest.json": (
        986,
        "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87",
    ),
}

OUTPUTS = {
    "ATTRIBUTION.txt": (
        365,
        "c875bc3936878d6220dfd413fe0b3920aa33d4d2a51ccb72f5871fc1916de15d",
    ),
    "README.md": (
        518,
        "d4f9d7bd11dbd0c88e6b6a0a400635b9c583ec2cc2497ece49bb77d86f1ee052",
    ),
    "construction-map-index.json.gz": (
        6_678_342,
        "6c28ca8e208712022bc3e2eb308a6574741fff8aef5b06c310754c0c83a981da",
    ),
    "construction-map.html": (
        8_922_064,
        "f7a6f45cee80c28cf628d493acf1b3cfe9fe63f23e5287f0df5e25366cdf2886",
    ),
    "coverage.json": (
        7_462,
        "238abbbc23fffb5f132a472223a7a207e2bc375a402d62c926a2ee1fecf5d4fa",
    ),
    "manifest.json": (
        2_192,
        "1f365a43ecc97d5ed19c9003bc517f962a69ee7d9c94e27943b2bd5052478de3",
    ),
    "manifest.sha256": (
        80,
        "b48f582ecb469ffb701efbbe13bf9331fdbb01fb445fd47c0ab2821bec6dc221",
    ),
}

EXPECTED_PROJECTION = {
    "added_replacement_rows_unmapped": 167,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "1c9a28d7773f23fc5145465acfc303b92fb9a7b6cf288bacc986168c81ea6553"
    ),
    "default_visible_rows": 6_493,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 213, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 94,
    "mapped_rows": 108_987,
    "mapped_rows_with_any_role": 69,
    "master_rows": 109_285,
    "unmapped_rows": 298,
    "unmapped_source_record_ids_sha256": (
        "acb532944530a2146dddc7b6292c8ddb6678eb2a46f70b79e6a7bec93d703b04"
    ),
}

TREE_SHA256 = "7f9a6e61f6d082286448d29c0d68fda37206c7a90a814f813909c049149350b2"
BASE_TREE_SHA256 = "e63f618ef36a5a6f57663f41bf887e97f93f54cb2713e15b07a63517674e4e00"
MASTER_TREE_SHA256 = "2c575c8e129c335694d29bac4000773980134a4ac6d253554438106742727079"
V62_TREE_SHA256 = "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"
IDENTITY_TREE_SHA256 = (
    "5fabf0ac8f28bc59c9969fb6a50240797ec0a440c2a534388aea9f0a2f9c64e6"
)
FEDERATION_TREE_SHA256 = (
    "1eba8fced5248c8f06f2e77b49ffb86519e723feb2c7a2d3f5eb7cd3e36d5671"
)

POST_V62_INPUTS = {
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json",
    "sources/curated-official-2026-07-20-databank-iad6-culpeper.json",
    "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b1.json",
    "sources/curated-official-2026-07-20-ecodatacenter-borlange-data-center-b2.json",
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json",
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json",
    "sources/curated-official-2026-07-20-esr-bupyeong-kr1.json",
    "sources/curated-official-2026-07-20-esr-kwai-chung-hk1-phase-2.json",
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json",
    "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json",
    "sources/curated-official-2026-07-20-teraco-ct1-rondebosch-expansion.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path: Path) -> tuple[int, str]:
    return path.stat().st_size, sha256(path)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise AssertionError(f"bundle contains symlink: {relative}")
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
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def load_index(directory: Path) -> dict:
    return json.loads(
        gzip.decompress((directory / "construction-map-index.json.gz").read_bytes())
    )


def unresolved_ids(master: Path) -> set[str]:
    result: set[str] = set()
    with (master / "construction-master.jsonl").open("rb") as source:
        for line_number, raw in enumerate(source, start=1):
            row = json.loads(raw)
            if map_v10._project_row(row, line_number) is None:
                result.add(row["source"]["record_id"])
    return result


class FrozenConstructionMapV26Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v26 construction map attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_frozen_modes_and_tree_digests(self) -> None:
        for path, expected in FILE_PINS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(set(OUTPUTS), map_v10.BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(MAP.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in MAP.iterdir()}, set(OUTPUTS))
        for name, expected in OUTPUTS.items():
            path = MAP / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(checkpoint(path), expected)
        self.assertEqual(tree_digest(MAP), TREE_SHA256)
        self.assertEqual(tree_digest(BASE_MAP), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(MASTER), MASTER_TREE_SHA256)
        self.assertEqual(tree_digest(V62_RELEASE), V62_TREE_SHA256)
        self.assertEqual(tree_digest(IDENTITY), IDENTITY_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION), FEDERATION_TREE_SHA256)

    def test_definition_is_exact_v25_successor_with_only_v26_master(self) -> None:
        old = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        new = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = copy.deepcopy(old)
        expected["expected_projection"] = EXPECTED_PROJECTION
        expected["generated_at"] = GENERATED_AT
        expected["map_id"] = "2026-07-20-public-open-v26-construction-map-v2"
        expected["master"] = {
            "definition": {
                "bytes": 5_658,
                "path": "construction-master-2026-07-20-public-open-v26.json",
                "sha256": FILE_PINS[MASTER_DEFINITION][1],
            },
            "directory": "../construction_master/2026-07-20-public-open-v26",
            "jsonl": {
                "bytes": 325_626_276,
                "path": "../construction_master/2026-07-20-public-open-v26/construction-master.jsonl",
                "sha256": "c6b5516ddbd865065894f2008b4d0f2bba4090bd422a42ba1cd16347e0d7ee50",
            },
            "manifest": {
                "bytes": 9_720,
                "path": "../construction_master/2026-07-20-public-open-v26/manifest.json",
                "sha256": FILE_PINS[MASTER / "manifest.json"][1],
            },
            "master_id": "2026-07-20-public-open-v26",
        }
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(new))
        self.assertEqual(new, expected)
        self.assertEqual(old["scope"], new["scope"])
        self.assertEqual(old["template"], new["template"])
        carrier = (ROOT / "datacenter_atlas/construction_map_v10.py").read_text()
        self.assertIn('with_name("construction_map_v9.py")', carrier)

    def test_projection_delta_fields_provenance_and_unresolved_boundary(self) -> None:
        old_coverage = json.loads(
            (BASE_MAP / "coverage.json").read_text(encoding="utf-8")
        )
        coverage = json.loads((MAP / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["projection"], EXPECTED_PROJECTION)
        self.assertEqual(coverage["scope"], old_coverage["scope"])
        self.assertEqual(
            coverage["counts"],
            {
                "mapped_observation_rows": 108_987,
                "mapped_replacement_rows": 94,
                "mapped_rows_with_any_role": 69,
                "master_observation_rows": 109_285,
                "unique_physical_site_count": None,
                "unmapped_observation_rows": 298,
            },
        )
        old_projection = old_coverage["projection"]
        self.assertEqual(
            {
                "mapped": EXPECTED_PROJECTION["mapped_rows"]
                - old_projection["mapped_rows"],
                "unmapped": EXPECTED_PROJECTION["unmapped_rows"]
                - old_projection["unmapped_rows"],
                "total": EXPECTED_PROJECTION["master_rows"]
                - old_projection["master_rows"],
                "default_visible": EXPECTED_PROJECTION["default_visible_rows"]
                - old_projection["default_visible_rows"],
                "mapped_replacement": EXPECTED_PROJECTION["mapped_replacement_rows"]
                - old_projection["mapped_replacement_rows"],
                "mapped_with_role": EXPECTED_PROJECTION["mapped_rows_with_any_role"]
                - old_projection["mapped_rows_with_any_role"],
            },
            {
                "mapped": 1,
                "unmapped": 10,
                "total": 11,
                "default_visible": 1,
                "mapped_replacement": 1,
                "mapped_with_role": 1,
            },
        )
        self.assertEqual(
            {
                tier: EXPECTED_PROJECTION["mapped_by_tier"][tier]
                - old_projection["mapped_by_tier"][tier]
                for tier in ("A", "B", "C")
            },
            {"A": 1, "B": 0, "C": 0},
        )

        old_index = load_index(BASE_MAP)
        index = load_index(MAP)
        self.assertEqual(index["fields"], old_index["fields"])
        self.assertEqual(index["scope"], old_index["scope"])
        field = {name: offset for offset, name in enumerate(index["fields"])}
        old_rows = {
            row[field["source_record_id"]]: row for row in old_index["rows"]
        }
        new_rows = {row[field["source_record_id"]]: row for row in index["rows"]}
        self.assertEqual(set(new_rows) - set(old_rows), {IAD5_ID})
        self.assertFalse(set(old_rows) - set(new_rows))
        for record_id, old_row in old_rows.items():
            new_row = new_rows[record_id]
            if old_row[field["source_artifact_id"]] != "epoch-official-open-seed-v59":
                self.assertEqual(new_row, old_row)
                continue
            ignored = {
                field["row_id"],
                field["source_artifact_id"],
                field["source_release_id"],
            }
            self.assertEqual(
                [value for offset, value in enumerate(new_row) if offset not in ignored],
                [value for offset, value in enumerate(old_row) if offset not in ignored],
            )

        old_unresolved = unresolved_ids(BASE_MASTER)
        new_unresolved = unresolved_ids(MASTER)
        self.assertEqual((len(old_unresolved), len(new_unresolved)), (288, 298))
        self.assertEqual(len(old_unresolved & new_unresolved), 287)
        self.assertEqual(old_unresolved - new_unresolved, {REMOVED_STC_ID})
        self.assertEqual(len(new_unresolved - old_unresolved), 11)
        self.assertNotIn(IAD5_ID, new_unresolved)

    def test_master_v62_identity_v5_lineage_and_post_v62_exclusion(self) -> None:
        map_definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        master_definition = json.loads(
            MASTER_DEFINITION.read_text(encoding="utf-8")
        )
        replacement = master_definition["inputs"]["replacement_release"]
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v62")
        self.assertEqual(
            replacement["manifest"]["sha256"],
            FILE_PINS[V62_RELEASE / "manifest.json"][1],
        )
        self.assertEqual(
            map_definition["master"]["manifest"]["sha256"],
            FILE_PINS[MASTER / "manifest.json"][1],
        )

        identity_definition = json.loads(
            IDENTITY_DEFINITION.read_text(encoding="utf-8")
        )
        identity_manifest = json.loads(
            (IDENTITY / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            identity_definition["federation"]["index_path"],
            "../federated_indexes/2026-07-20-public-open-v27",
        )
        self.assertEqual(
            identity_definition["federation"]["expected_index_sha256"],
            FILE_PINS[FEDERATION / "federated-index.json"][1],
        )
        child = next(
            row
            for row in identity_definition["children"]
            if row["release_id"] == "epoch-official-open-seed-v62"
        )
        self.assertEqual(
            child["expected_manifest_sha256"],
            FILE_PINS[V62_RELEASE / "manifest.json"][1],
        )
        dispositions = {
            row["release_id"]: row["disposition"]
            for row in identity_manifest["input_children"]
        }
        self.assertEqual(dispositions["epoch-official-open-seed-v62"], "processed")

        v62_definition = json.loads(V62_DEFINITION.read_text(encoding="utf-8"))
        v62_inputs = {row["path"] for row in v62_definition["curated_inputs"]}
        self.assertTrue(POST_V62_INPUTS.isdisjoint(v62_inputs))
        self.assertNotIn(
            "open-seed-v63",
            DEFINITION.read_text() + MASTER_DEFINITION.read_text(),
        )

    def test_double_offline_replay_tamper_modes_and_exact_bytes(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="construction-map-v26-replay-", dir="/private/tmp"
            ) as temporary,
            ExitStack() as stack,
        ):
            self._offline(stack)
            root = Path(temporary)
            for name in ("first", "second"):
                rebuilt = root / name
                write_construction_map_v10(
                    MASTER,
                    rebuilt,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    freeze=True,
                )
                self.assertEqual(tree_digest(rebuilt), TREE_SHA256)
                for filename, expected in OUTPUTS.items():
                    self.assertEqual(checkpoint(rebuilt / filename), expected)

            first = root / "first"
            first.chmod(0o755)
            (first / "coverage.json").chmod(0o644)
            with self.assertRaisesRegex(ConstructionMapV10Error, "frozen 0555/0444"):
                validate_construction_map_v10(
                    first,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    reproduce=False,
                )

            second = root / "second"
            second.chmod(0o755)
            index_path = second / "construction-map-index.json.gz"
            index_path.chmod(0o644)
            tampered = bytearray(index_path.read_bytes())
            tampered[-1] ^= 1
            index_path.write_bytes(tampered)
            with self.assertRaisesRegex(ConstructionMapV10Error, "map output changed"):
                validate_construction_map_v10(
                    second,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                    reproduce=False,
                )

        for filename, expected in OUTPUTS.items():
            self.assertEqual(checkpoint(MAP / filename), expected)

    def test_collision_symlink_fault_cleanup_and_definition_tamper_fail_closed(
        self,
    ) -> None:
        with self.assertRaisesRegex(ConstructionMapV10Error, "existing output"):
            write_construction_map_v10(
                MASTER,
                MAP,
                master_definition_path=MASTER_DEFINITION,
                map_definition_path=DEFINITION,
            )
        with tempfile.TemporaryDirectory(
            prefix="construction-map-v26-fail-closed-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            collision = root / "collision"
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_text("keep\n", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMapV10Error, "existing output"):
                write_construction_map_v10(
                    MASTER,
                    collision,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

            symlink = root / "symlink"
            symlink.symlink_to(MAP, target_is_directory=True)
            with self.assertRaisesRegex(ConstructionMapV10Error, "existing output"):
                write_construction_map_v10(
                    MASTER,
                    symlink,
                    master_definition_path=MASTER_DEFINITION,
                    map_definition_path=DEFINITION,
                )
            self.assertTrue(symlink.is_symlink())

            late = root / "late"

            def late_build(*_args: object, **_kwargs: object) -> dict:
                late.mkdir()
                return {}

            with (
                patch.object(map_v10, "_build_into", side_effect=late_build),
                patch.object(map_v10, "_validate_static", return_value={}),
            ):
                with self.assertRaisesRegex(
                    ConstructionMapV10Error, "late output collision"
                ):
                    write_construction_map_v10(
                        MASTER,
                        late,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=DEFINITION,
                        freeze=True,
                    )
            self.assertTrue(late.is_dir())
            self.assertFalse((root / ".late.lock").exists())
            self.assertFalse(any(".late.stage-" in path.name for path in root.iterdir()))

            fault = root / "fault"
            with patch.object(map_v10, "_build_into", side_effect=RuntimeError("boom")):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    write_construction_map_v10(
                        MASTER,
                        fault,
                        master_definition_path=MASTER_DEFINITION,
                        map_definition_path=DEFINITION,
                    )
            self.assertFalse(fault.exists())
            self.assertFalse((root / ".fault.lock").exists())
            self.assertFalse(any(".fault.stage-" in path.name for path in root.iterdir()))

            document = json.loads(DEFINITION.read_text(encoding="utf-8"))
            changed = copy.deepcopy(document)
            changed["scope"]["unique_physical_site_count"] = 108_987
            path = root / "scope-tamper.json"
            path.write_bytes(canonical_json(changed))
            with self.assertRaisesRegex(
                ConstructionMapV10Error, "identity or scope changed"
            ):
                validate_map_definition_v10(
                    path,
                    master_directory=MASTER,
                    master_definition_path=MASTER_DEFINITION,
                )

            changed_checkpoint = copy.deepcopy(document["master"]["manifest"])
            changed_checkpoint["sha256"] = "0" * 64
            with self.assertRaisesRegex(
                ConstructionMapV10Error, "checkpoint changed"
            ):
                map_v10._validate_checkpoint(
                    DEFINITION.parent,
                    changed_checkpoint,
                    MASTER / "manifest.json",
                    "master manifest",
                )

    def test_cli_and_both_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        cli = subprocess.run(
            [
                sys.executable,
                "scripts/build_construction_map_v10.py",
                "--master-dir",
                str(MASTER),
                "--master-definition",
                str(MASTER_DEFINITION),
                "--map-definition",
                str(DEFINITION),
                "--output-dir",
                str(MAP),
                "--validate-only",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout)["master"]["rows"], 109_285)

        for cwd, package in (
            (ROOT, "datacenter_atlas.construction_map_v10"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.construction_map_v10"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_construction_map_v10; "
                f"result=validate_construction_map_v10(Path({str(MAP)!r}), "
                f"master_directory=Path({str(MASTER)!r}), "
                f"master_definition_path=Path({str(MASTER_DEFINITION)!r}), "
                f"map_definition_path=Path({str(DEFINITION)!r}), reproduce=False); "
                "assert result['outputs']['construction-map-index.json.gz']['records']==108987; "
                "assert result['scope']['unique_physical_site_count'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
