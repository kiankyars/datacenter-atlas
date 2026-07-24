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
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import open_seed_v50 as v50
from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v50.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v50"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v49.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v49"
BUILDER = ROOT / "scripts/build_open_seed_v50.py"
VALIDATOR = ROOT / "scripts/validate_open_seed_release.py"

DEFINITION_SHA256 = "6d15ead5b9efe37710d3ed5748cb46655ccfc16b681027ac6e343e26b546194a"
MANIFEST_SHA256 = "b5b03eab81e25e7f967d4af48d8221e60ced9dfc38909d4373a7f7ca88e088b0"
BASE_DEFINITION_SHA256 = (
    "b7081b2bf511951434ee96a80bd1466e330516e415b46dde76ed171683b6c88c"
)
BASE_MANIFEST_SHA256 = (
    "8cd4859e8222fe9ddfcad4fcece7420a9e25a2ff10dd67ab1d8a237d9ee33489"
)
RECORDED_AT = "2026-07-20T18:00:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T16:57:56Z"
TREE_SHA256 = "b587ab6602c592b5035fc2d6b7e8a8ec1af4614a2a22811e8d73fc62e0a239e0"
BASE_TREE_SHA256 = (
    "77309cad997d57635c7a88de10746ff194d456d19b360574cf46223cb2841395"
)
EMPTY_DELTA_SHA256 = "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-leighton-anonymous-johor-groundbreaking.json": (
        "51b3bbd33dbe5f7d921f0e0428495277c433c48e629966eba5c092276306ebef"
    ),
    "sources/curated-official-2026-07-20-leighton-johor-bahru-57-6mw-contract.json": (
        "29ec37c89471f591a1f4f9d12d06da9021b257a0b1317e295f33d9a16d38553a"
    ),
    "sources/curated-official-2026-07-20-radiusdc-nashville-i.json": (
        "e402d328e2e9c7217d5692cbf7cf6394ae4875eda9ee6a7cceac1b5f568be7d8"
    ),
    "sources/curated-official-2026-07-20-uniserve-369-terminal-vancouver.json": (
        "fcbaef2079eb7058222a44390590ae80abe31faae184e7faf30c8306469381de"
    ),
}

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3_257,
        "aa7de00cd3f8a3066253ae8d901cabfe8d5cefe3d7affde6dc7542d0d1d03c5b",
    ),
    "README.md": (
        2_625,
        "d5ee213720f5a6873ac480c14991e75f204230fd994fa70be4cee11bed840d5a",
    ),
    "atlas.geojson": (
        2_264_090,
        "ecf03b720916018a7783f1c877e79e5a9d06b845a4e45c9061edc9bac91de527",
    ),
    "capacity_estimates.csv": (
        222_084,
        "013a24068a7c2fe5f56118e5e13df3557de4aa8caa0f2c298f4a7a8fa3f67e2c",
    ),
    "construction_pipeline.csv": (
        439_727,
        "e23e753b92448295c93685d80d58124ed50b3bc1ddb2c063a23a7cc839b0dba4",
    ),
    "construction_source_signals.csv": (
        263_261,
        "6eb4084155c67093e029ea76d20672b801cc12e52010498b71dd58c716123fb8",
    ),
    "entities.csv": (
        710_772,
        "b3578b5460f5637bb9a6d7fc36ed1c2a8dc4beb03b3dbc05b47eed8bde289fe1",
    ),
    "evidence.csv": (
        138_307,
        "19c42495c0139a85f595e7ee66bdf8e65d4f718faf0f85f648c9b6bd6f2e2486",
    ),
    "manifest.json": (8_468, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4_011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5_874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        204_815,
        "960ffb6abf5ea45aef8573c359c0bc6e4564b26fec3adff55959079e8bcf19bc",
    ),
    "summary.json": (
        2_807,
        "d429f8a067019108f08b89c96af3bd083299697b808d5f401f8b98e396d15e93",
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
    ROOT / "datacenter_atlas/open_seed_v50.py": (
        17_355,
        "63dc5d12acf733c4d6729542f869f18c452db1c5739462c57bf6b141f2e62bb2",
    ),
    ROOT / "open_seed_v50.py": (
        138,
        "c7cf9c7564e4466346e7ad18be87a67516fa37d955e4103744b08abc9ded6fda",
    ),
    BUILDER: (
        422,
        "31f64b542967765bad24c9846a75b1fd00578149e831fa78c41a6ebf40df6182",
    ),
    VALIDATOR: (
        1_534,
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
    ),
}

# common count, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        629,
        8,
        "44b609145b392d2fb4f2a061ae2a8a748b9d3f3a4c3027e64c6c22f3b2447ca2",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "evidence.csv": (
        352,
        7,
        "5c390e29a2a35d5eb44c8991c31eac81304e971bf626b52262b810e42be2d066",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "capacity_estimates.csv": (
        467,
        3,
        "9a762b08ca9d4c50376578f93589629d49bb70b6e4cc8e9de5ad940a1a885c86",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_pipeline.csv": (
        327,
        4,
        "39fe5aab8172fd4a58cb56b7707e5f1b7e5322bd2eeb5a8d064a51d513e461f7",
        0,
        EMPTY_DELTA_SHA256,
    ),
    "construction_source_signals.csv": (
        235,
        4,
        "0dc9f7cc4861986f0c30c223e64856e93231043d029dae62f3b8461293105741",
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


class OpenSeedV50Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        blocked = AssertionError("v50 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text
        rejected = tuple(
            f"open-seed-2026-07-20-v{version}" for version in (45, 46, 47, 48)
        )

        def forbidden(path: Path) -> bool:
            return any(marker in path.resolve().as_posix() for marker in rejected)

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v50 attempted rejected seed access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if forbidden(path):
                raise AssertionError(f"v50 attempted rejected seed access: {path}")
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

    def test_exact_pins_double_offline_rebuild_and_frozen_bundle(self) -> None:
        self.assertEqual(DEFINITION.stat().st_size, 63_473)
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
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 637)
        self.assertEqual(first["entities_by_kind"], {"campus": 344, "project": 293})
        self.assertEqual(first["evidence_records"], 359)
        self.assertEqual(first["capacity_estimates"], 470)
        self.assertEqual(first["construction_pipeline_records"], 331)
        self.assertEqual(first["construction_source_signals"], 239)
        self.assertEqual(first["resolution_candidates"], 4)

    def test_definition_is_exact_four_input_addition_to_v49_only(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        base_pins = {row["path"]: row["sha256"] for row in base["curated_inputs"]}
        pins = {row["path"]: row["sha256"] for row in current["curated_inputs"]}
        self.assertEqual(len(base_pins), 297)
        self.assertEqual(len(pins), 301)
        self.assertEqual(set(base_pins) - set(pins), set())
        self.assertEqual(set(pins) - set(base_pins), set(ADDED_INPUTS))
        self.assertEqual(
            {path: pins[path] for path in base_pins},
            base_pins,
        )
        self.assertEqual({path: pins[path] for path in ADDED_INPUTS}, ADDED_INPUTS)
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v50")
        self.assertEqual(current["build"]["recorded_at"], RECORDED_AT)
        self.assertEqual(v50.BASE_DEFINITION, BASE_DEFINITION)
        self.assertEqual(v50.BASE_RELEASE, BASE_RELEASE)

        retrieved = [current["epoch_capture"]["retrieved_at"]]
        for path in pins:
            document = json.loads((ROOT / path).read_text(encoding="utf-8"))
            retrieved.extend(row["retrieved_at"] for row in document["evidence"])
        self.assertEqual(max(retrieved), MAX_SELECTED_RETRIEVED_AT)
        self.assertLess(
            datetime.fromisoformat(MAX_SELECTED_RETRIEVED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00")),
        )

        implementation = sys.modules[v50.selected_inputs.__module__]
        for version in (42, 45, 46, 47, 48):
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
                self.assertRaisesRegex(SystemExit, "select exactly accepted v49"),
            ):
                v50.selected_inputs(base)

    def test_csv_delta_is_strictly_additive_and_exact(self) -> None:
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

    def test_added_records_preserve_identity_status_role_and_power_boundaries(self) -> None:
        all_entities = rows(RELEASE / "entities.csv")
        base_entities = row_counter(BASE_RELEASE / "entities.csv")
        added_entities = {
            row["stable_key"]: row
            for row in all_entities
            if tuple(row.items()) not in base_entities
        }
        expected_keys = {
            "curated:leighton-anonymous-johor-bahru-57-6mw-campus",
            "curated:leighton-anonymous-johor-bahru-57-6mw-campus:development",
            "curated:leighton-anonymous-johor-july-2026-groundbreaking-campus",
            "curated:leighton-anonymous-johor-july-2026-groundbreaking-campus:development",
            "curated:radiusdc-nashville-i-trinity-hills-campus",
            "curated:radiusdc-nashville-i-trinity-hills-campus:nashville-i",
            "curated:uniserve-369-terminal-avenue-vancouver-data-centre",
            "curated:uniserve-369-terminal-avenue-vancouver-data-centre:two-phase-buildout",
        }
        self.assertEqual(set(added_entities), expected_keys)

        first_leighton = (
            "curated:leighton-anonymous-johor-bahru-57-6mw-campus:development"
        )
        second_leighton = (
            "curated:leighton-anonymous-johor-july-2026-groundbreaking-campus:development"
        )
        radius = "curated:radiusdc-nashville-i-trinity-hills-campus:nashville-i"
        uniserve = (
            "curated:uniserve-369-terminal-avenue-vancouver-data-centre:two-phase-buildout"
        )
        self.assertNotEqual(
            added_entities[first_leighton]["entity_id"],
            added_entities[second_leighton]["entity_id"],
        )
        for key in expected_keys:
            row = added_entities[key]
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["workloads_json"], "[]")
        for key in expected_keys:
            if key.startswith("curated:leighton-"):
                row = added_entities[key]
                self.assertEqual(row["operator"], "")
                self.assertEqual(row["owner"], "")
                tags = json.loads(row["tags_json"])
                self.assertEqual(tags["role:contractor"], "Leighton Asia")
                self.assertEqual(
                    {name for name in tags if name.startswith("role:")},
                    {"role:contractor"},
                )
                self.assertFalse(any("airtrunk" in value.lower() for value in tags.values()))

        project_rows = {
            row["stable_key"]: row for row in rows(RELEASE / "construction_pipeline.csv")
        }
        self.assertEqual(project_rows[first_leighton]["status"], "announced")
        self.assertEqual(project_rows[second_leighton]["status"], "under_construction")
        self.assertEqual(project_rows[radius]["status"], "under_construction")
        self.assertEqual(project_rows[uniserve]["status"], "under_construction")
        self.assertEqual(project_rows[first_leighton]["operating_model"], "colocation")
        self.assertEqual(project_rows[second_leighton]["operating_model"], "")
        self.assertEqual(project_rows[radius]["operating_model"], "colocation")
        self.assertEqual(project_rows[uniserve]["operating_model"], "")

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
            )
            for row in added_capacity
        }
        self.assertEqual(
            observed,
            {
                (first_leighton, "critical_it_mw", "planned", "57.6"),
                (radius, "critical_it_mw", "planned", "12.0"),
                (uniserve, "grid_connection_mw", "planned", "3.0"),
            },
        )
        self.assertFalse(any(row["base"] in {"2.0", "20.0"} for row in added_capacity))
        self.assertFalse(
            any(
                row["metric"]
                in {"annual_energy_mwh", "gross_facility_mw", "generation_mw"}
                for row in added_capacity
            )
        )
        uniserve_capacity = next(
            row
            for row in added_capacity
            if entity_by_id[row["entity_id"]]["stable_key"] == uniserve
        )
        self.assertIn("not labeled contracted", uniserve_capacity["notes"])

    def test_scope_explicitly_disclaims_parity_completeness_and_unique_sites(self) -> None:
        manifest = json.loads((RELEASE / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
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
        self.assertEqual(len(manifest["source_families"]), 181)
        self.assertEqual(summary["entities_total"], 637)
        self.assertEqual(summary["projects_total"], 293)
        self.assertEqual(summary["evidence_total"], 423)
        self.assertEqual(summary["entities_by_status"]["announced"], 6)
        self.assertEqual(summary["entities_by_status"]["under_construction"], 234)

    def test_existing_and_active_lock_collisions_preserve_frozen_outputs(self) -> None:
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
        self.assertFalse(v50.PUBLICATION_LOCK.exists())

        descriptor = os.open(
            v50.PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
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
            v50.PUBLICATION_LOCK.unlink(missing_ok=True)
        self.assertEqual(DEFINITION.read_bytes(), before_definition)
        self.assertEqual(tree_digest(RELEASE), before_tree)

    def test_late_arrival_collision_is_atomic_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory(prefix="open-seed-v50-collision-") as temporary:
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
                v50.promote_noreplace(stage, destination)
            self.assertEqual((stage / "stage.txt").read_text(), "stage\n")
            self.assertEqual((destination / "existing.txt").read_text(), "existing\n")

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
                "from datacenter_atlas.open_seed_v50 import BASE_DEFINITION, RELEASE; "
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
            self.assertEqual(payload["entities"], 637)
            self.assertEqual(payload["manifest_sha256"], MANIFEST_SHA256)


if __name__ == "__main__":
    unittest.main()
