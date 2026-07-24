from __future__ import annotations

from contextlib import ExitStack
import copy
import csv
import hashlib
from itertools import islice, zip_longest
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

from datacenter_atlas import construction_master_v10 as master_v10
from datacenter_atlas.construction_master_v10 import (
    ConstructionMasterV10Error,
    validate_construction_master_v10,
    validate_definition,
    write_construction_master_v10,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v26.json"
MASTER = ROOT / "construction_master/2026-07-20-public-open-v26"
BASE_DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v25.json"
BASE_MASTER = ROOT / "construction_master/2026-07-20-public-open-v25"
V59_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
V59_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
V62_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-20-public-open-v5.json"
)
IDENTITY = ROOT / "exact_identity_decisions/2026-07-20-public-open-v5"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v27.json"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v27"

GENERATED_AT = "2026-07-21T05:05:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v59"
NEW_RELEASE_ID = "epoch-official-open-seed-v62"

FILE_PINS = {
    BASE_DEFINITION: (
        5_658,
        "4f87fb1e2e8966b1bbdf5d6e4adc13e383fa83c5452899f504bc671bdef3bcd8",
    ),
    BASE_MASTER / "manifest.json": (
        9_720,
        "d717f3ca4eb7f876ce175d42d7c09a338a182e727aeec151f9df555fccd261fd",
    ),
    ROOT / "datacenter_atlas/construction_master_v9.py": (
        2_550,
        "63ce982579d7d052729a5844954442da868f3126565910e2f5fc5b9f37f9b22d",
    ),
    ROOT / "construction_master_v9.py": (
        239,
        "79e9e20559660c86c9fbc7ba357803ed4be526cf44ac4d1d2d11a7696a4e34dc",
    ),
    ROOT / "scripts/build_construction_master_v9.py": (
        1_864,
        "80a01c5e2a1502809142f43565767013798788d64554b93d16a7a2982cf59596",
    ),
    ROOT / "datacenter_atlas/construction_master_v10.py": (
        2_774,
        "d77c8bd461ea0365708b56a0f55596f9d581ed8a1f520181e85cba78775926bb",
    ),
    ROOT / "construction_master_v10.py": (
        241,
        "e2d035c932275ba399ed042fc7fd762d1b4acbf0826d5f16beaed1f47973da66",
    ),
    ROOT / "scripts/build_construction_master_v10.py": (
        1_872,
        "2d40479d677044dc8144504af2b67611a890ad7bc914bdcf143b6ec1208f767b",
    ),
    DEFINITION: (
        5_658,
        "ede029f2fa2ecb6371b311de6497e0eda2dc38d23752a8ec1efc2760b27dda45",
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
    IDENTITY / "manifest.sha256": (
        80,
        "c1460885a92386abdc39831e8982df77aab0b3e83765a3f9b27cbc552a61dbc6",
    ),
    FEDERATION_DEFINITION: (
        1_788,
        "4f0bbb0fcef771966f9d18cdcc28691b4adeb1b9b60d6f2af95fd4c6e592499e",
    ),
    FEDERATION / "federated-index.json": (
        27_784,
        "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8",
    ),
    FEDERATION / "manifest.json": (
        986,
        "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87",
    ),
    FEDERATION / "manifest.sha256": (
        80,
        "93af947986aa0fc77fb871521dacf09c9bf8111f17212d19caa9942a03694207",
    ),
}

OUTPUTS = {
    "ATTRIBUTION.txt": (
        5_814,
        "164f59baf3498b4f392eea6c92869b0464b9b27e559b0b2aa7018c6bcf129abe",
    ),
    "README.md": (
        1_349,
        "e6ad9cfb2578edf45ac68e8daeeca0710a81b22ad9e644fda99eea95a1b7e5f2",
    ),
    "construction-master.csv": (
        189_801_583,
        "6f659b32099ae8d6badc034b55d598314a7a745698191e55e0cb90a0846fe8c5",
    ),
    "construction-master.jsonl": (
        325_626_276,
        "c6b5516ddbd865065894f2008b4d0f2bba4090bd422a42ba1cd16347e0d7ee50",
    ),
    "coverage.json": (
        8_548,
        "e3c1cb020a0261dee6f405dc5f865e33a53ae28b11faf9c00802b8ccf16bc838",
    ),
    "manifest.json": (
        9_720,
        "f5895210b32b0307dc1cc12791541024bdb9dc39532ff2ebff0f669d9442bb82",
    ),
    "manifest.sha256": (
        80,
        "6930c34364111f5d93624c09c46d08766dac08f132f1f52f362879eecb2ad47a",
    ),
}

TREE_SHA256 = "2c575c8e129c335694d29bac4000773980134a4ac6d253554438106742727079"
BASE_TREE_SHA256 = "8a32d73f27f659da1dbb2ace21def77806f4bd4ac88baeca7675144c9039a9e6"
V62_TREE_SHA256 = "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"
IDENTITY_TREE_SHA256 = (
    "5fabf0ac8f28bc59c9969fb6a50240797ec0a440c2a534388aea9f0a2f9c64e6"
)
FEDERATION_TREE_SHA256 = (
    "1eba8fced5248c8f06f2e77b49ffb86519e723feb2c7a2d3f5eb7cd3e36d5671"
)

EXPECTED = {
    "added_replacement_rows": 174,
    "added_source_record_ids_sha256": (
        "c78815d6f260c714f348db6619aefc15bce7978a4be6bc1e0e99bf005cb81f80"
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
        "cad41d8daee686fb25067533da80401d02df116949c3bc012533a616c262dbc9"
    ),
    "replacement_rows": 373,
    "replacement_rows_with_any_role": 129,
    "replacement_rows_with_customers": 2,
    "replacement_rows_with_operator": 51,
    "replacement_rows_with_owner": 47,
    "replacement_rows_with_source_role_tags": 90,
    "replacement_rows_with_tenants": 6,
    "replacement_rows_with_users": 36,
    "replacement_rows_without_roles_sha256": (
        "9f194a34b9d20b2f7912f20e331430ad3c646dbd8bcd8455155e17c93ca22fba"
    ),
    "replacement_source_record_ids_sha256": (
        "fe4f971b6dd4a6e9cdc53fdaea619c51687b1093a06c08b1b74ed5994ff18831"
    ),
    "rows_with_contract_marker": 373,
    "satellite_recovery_control_plane_bytes": 15_313,
    "satellite_recovery_rows": 0,
    "tier_a_arithmetic_projection_sha256": (
        "748a541ff430743a755b5988cb45e785287a7aed4b976d4adfcdc7558f135655"
    ),
    "tier_a_rows": 493,
    "tier_b_rows": 6_298,
    "tier_c_rows": 102_494,
    "total_rows": 109_285,
    "unchanged_replacement_rows": 199,
}

POST_V62_INPUTS = {
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json",
    "sources/curated-official-2026-07-20-databank-iad6-culpeper.json",
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-e.json",
    "sources/curated-official-2026-07-20-ecodatacenter-falun-data-center-f.json",
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json",
    "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json",
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


def csv_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return {row["entity_id"]: row for row in csv.DictReader(source)}


class FrozenConstructionMasterV26Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("v26 construction master attempted network access")
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
        self.assertEqual(set(OUTPUTS), master_v10.BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(MASTER.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in MASTER.iterdir()}, set(OUTPUTS))
        for name, expected in OUTPUTS.items():
            path = MASTER / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(checkpoint(path), expected)
        self.assertEqual(tree_digest(MASTER), TREE_SHA256)
        self.assertEqual(tree_digest(BASE_MASTER), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(V62_RELEASE), V62_TREE_SHA256)
        self.assertEqual(tree_digest(IDENTITY), IDENTITY_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION), FEDERATION_TREE_SHA256)

    def test_definition_is_exact_v25_successor_with_only_v62_replacement(self) -> None:
        old = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        new = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = copy.deepcopy(old)
        expected["master_id"] = "2026-07-20-public-open-v26"
        expected["generated_at"] = GENERATED_AT
        expected["expected"] = EXPECTED
        expected["inputs"]["replacement_release"] = {
            "artifact_id": NEW_RELEASE_ID,
            "data": {
                "bytes": 482_154,
                "path": "releases/2026-07-20-open-seed-v62/construction_pipeline.csv",
                "sha256": "c69af039c18c30ad858b952662cc2e838a373d98d74a21fe68536e9440e27891",
            },
            "definition": {
                "bytes": 76_824,
                "path": "sources/open-seed-2026-07-20-v62.json",
                "sha256": FILE_PINS[V62_DEFINITION][1],
            },
            "evidence": {
                "bytes": 173_937,
                "path": "releases/2026-07-20-open-seed-v62/evidence.csv",
                "sha256": "4b3ba9c014d64a0ef9ff1d02463db6683a029cd096b2ecb1cb6942ca1814aa57",
            },
            "manifest": {
                "bytes": 10_934,
                "path": "releases/2026-07-20-open-seed-v62/manifest.json",
                "sha256": FILE_PINS[V62_RELEASE / "manifest.json"][1],
            },
            "publication_contract_version": 4,
            "release_id": NEW_RELEASE_ID,
        }
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(new))
        self.assertEqual(new, expected)
        self.assertEqual(old["inputs"]["base_master"], new["inputs"]["base_master"])
        self.assertEqual(
            old["inputs"]["satellite_recovery_acceptance"],
            new["inputs"]["satellite_recovery_acceptance"],
        )
        self.assertEqual(old["scope"], new["scope"])

        carrier = (ROOT / "datacenter_atlas/construction_master_v10.py").read_text()
        self.assertIn('with_name("construction_master_v9.py")', carrier)
        serialized = DEFINITION.read_text() + carrier
        for marker in (
            "exact_identity_decisions/",
            "federated_indexes/",
            "coverage-audit-",
            "current-coverage-",
            "construction-map-",
        ):
            self.assertNotIn(marker, serialized)

    def test_v62_release_delta_identity_v5_lineage_and_post_v62_exclusion(
        self,
    ) -> None:
        old_rows = csv_rows(V59_RELEASE / "construction_pipeline.csv")
        new_rows = csv_rows(V62_RELEASE / "construction_pipeline.csv")
        self.assertEqual((len(old_rows), len(new_rows)), (362, 373))
        self.assertEqual(len(set(new_rows) - set(old_rows)), 12)
        self.assertEqual(len(set(old_rows) - set(new_rows)), 1)
        for entity_id in set(old_rows) & set(new_rows):
            self.assertEqual(old_rows[entity_id], new_rows[entity_id])

        identity_definition = json.loads(
            IDENTITY_DEFINITION.read_text(encoding="utf-8")
        )
        identity_manifest = json.loads(
            (IDENTITY / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            identity_definition["federation"],
            {
                "expected_index_sha256": FILE_PINS[FEDERATION / "federated-index.json"][
                    1
                ],
                "expected_manifest_sha256": FILE_PINS[FEDERATION / "manifest.json"][1],
                "index_path": "../federated_indexes/2026-07-20-public-open-v27",
            },
        )
        identity_child = next(
            child
            for child in identity_definition["children"]
            if child["release_id"] == NEW_RELEASE_ID
        )
        self.assertEqual(
            identity_child,
            {
                "expected_manifest_sha256": FILE_PINS[V62_RELEASE / "manifest.json"][1],
                "expected_review_only": False,
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v62",
            },
        )
        self.assertEqual(
            identity_manifest["federation_input"]["directory_name"],
            "2026-07-20-public-open-v27",
        )
        processed = {
            row["release_id"]: row["disposition"]
            for row in identity_manifest["input_children"]
        }
        self.assertEqual(processed[NEW_RELEASE_ID], "processed")

        federation_index = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        descriptor = next(
            row
            for row in federation_index["releases"]
            if row["release_id"] == NEW_RELEASE_ID
        )
        self.assertEqual(
            descriptor["manifest"]["sha256"],
            FILE_PINS[V62_RELEASE / "manifest.json"][1],
        )
        self.assertEqual(descriptor["manifest"]["lifecycle_freshness_records"], 415)
        self.assertFalse(descriptor["manifest"]["current_status_inferred"])

        v62_definition = json.loads(V62_DEFINITION.read_text(encoding="utf-8"))
        v62_inputs = {row["path"] for row in v62_definition["curated_inputs"]}
        self.assertTrue(POST_V62_INPUTS.isdisjoint(v62_inputs))

    def test_rows_counts_fields_ordering_and_nonclaims_are_preserved(self) -> None:
        definition, _raw, _root, _resolved, context = validate_definition(DEFINITION)
        self.assertEqual(definition["expected"], EXPECTED)
        self.assertEqual(context["recovery"]["rows_created"], 0)
        self.assertFalse(context["recovery"]["payload_traversed"])

        old_coverage = json.loads(
            (BASE_MASTER / "coverage.json").read_text(encoding="utf-8")
        )
        coverage = json.loads((MASTER / "coverage.json").read_text(encoding="utf-8"))
        self.assertEqual(coverage["scope"], old_coverage["scope"])
        self.assertEqual(
            coverage["satellite_recovery_acceptance"],
            old_coverage["satellite_recovery_acceptance"],
        )
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 174,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": NEW_RELEASE_ID,
                "replacement_rows": 373,
                "unchanged_source_record_ids": 199,
            },
        )
        self.assertEqual(
            coverage["role_counts"],
            {
                "rows_with_any_role": 129,
                "rows_with_contract_marker": 373,
                "rows_with_source_role_tags": 90,
                "with_core_role": {
                    "customers": 2,
                    "operator": 51,
                    "owner": 47,
                    "tenants": 6,
                    "users": 36,
                },
            },
        )
        counts = coverage["row_counts"]
        old_counts = old_coverage["row_counts"]
        self.assertEqual(counts["total"], 109_285)
        self.assertEqual(counts["by_tier"], {"A": 493, "B": 6_298, "C": 102_494})
        self.assertEqual(
            {
                key: counts["by_tier"][key] - old_counts["by_tier"][key]
                for key in counts["by_tier"]
            },
            {"A": 11, "B": 0, "C": 0},
        )
        status_delta = {
            key: counts["by_normalized_status"].get(key, 0)
            - old_counts["by_normalized_status"].get(key, 0)
            for key in set(counts["by_normalized_status"])
            | set(old_counts["by_normalized_status"])
        }
        self.assertEqual(
            {key: value for key, value in status_delta.items() if value},
            {"commissioning": 1, "shell": 2, "under_construction": 8},
        )
        self.assertNotIn(OLD_RELEASE_ID, counts["by_source_artifact"])
        self.assertEqual(counts["by_source_artifact"][NEW_RELEASE_ID], 373)
        self.assertIsNone(counts["unique_physical_site_count"])
        self.assertTrue(
            coverage["scope"]["historical_status_is_not_current_status_claim"]
        )
        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertFalse(coverage["scope"]["benchmark_parity_claimed"])
        self.assertFalse(
            coverage["scope"]["structural_or_cv_rows_in_construction_arithmetic"]
        )

        with (
            (BASE_MASTER / "construction-master.csv").open("rb") as old_csv,
            (MASTER / "construction-master.csv").open("rb") as new_csv,
        ):
            self.assertEqual(old_csv.readline(), new_csv.readline())
        with (MASTER / "construction-master.jsonl").open("rb") as source:
            replacement = [json.loads(raw) for raw in islice(source, 373)]
        self.assertEqual(
            [row["source"]["record_id"] for row in replacement],
            list(csv_rows(V62_RELEASE / "construction_pipeline.csv")),
        )
        with (
            (BASE_MASTER / "construction-master.jsonl").open("rb") as old,
            (MASTER / "construction-master.jsonl").open("rb") as new,
        ):
            for _ in range(362):
                next(old)
            for _ in range(373):
                next(new)
            for old_line, new_line in zip_longest(old, new):
                self.assertEqual(old_line, new_line)

        release_manifest = json.loads(
            (V62_RELEASE / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(release_manifest["current_status_inferred"])
        self.assertEqual(
            release_manifest["lifecycle_status_semantics"], "last_observed"
        )
        self.assertEqual(release_manifest["lifecycle_freshness_records"], 415)

    def test_double_offline_replay_tamper_modes_and_exact_bytes(self) -> None:
        with (
            tempfile.TemporaryDirectory(
                prefix="construction-v26-replay-", dir="/private/tmp"
            ) as temporary,
            ExitStack() as stack,
        ):
            self._offline(stack)
            root = Path(temporary)
            for name in ("first", "second"):
                rebuilt = root / name
                write_construction_master_v10(DEFINITION, rebuilt, freeze=True)
                self.assertEqual(tree_digest(rebuilt), TREE_SHA256)
                for filename, expected in OUTPUTS.items():
                    self.assertEqual(checkpoint(rebuilt / filename), expected)

            first = root / "first"
            first.chmod(0o755)
            (first / "coverage.json").chmod(0o644)
            with self.assertRaisesRegex(ConstructionMasterV10Error, "frozen 0555/0444"):
                validate_construction_master_v10(
                    first, definition_path=DEFINITION, reproduce=False
                )
            (first / "coverage.json").chmod(0o444)
            first.chmod(0o555)
            validate_construction_master_v10(
                MASTER, definition_path=DEFINITION, reproduce=False
            )

        for filename, expected in OUTPUTS.items():
            self.assertEqual(checkpoint(MASTER / filename), expected)

    def test_collision_symlink_fault_cleanup_and_semantic_tamper_fail_closed(
        self,
    ) -> None:
        with self.assertRaisesRegex(ConstructionMasterV10Error, "existing output"):
            write_construction_master_v10(DEFINITION, MASTER)
        with tempfile.TemporaryDirectory(
            prefix="construction-v26-fail-closed-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            collision = root / "collision"
            collision.mkdir()
            sentinel = collision / "sentinel"
            sentinel.write_text("keep\n", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMasterV10Error, "existing output"):
                write_construction_master_v10(DEFINITION, collision)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

            symlink = root / "symlink"
            symlink.symlink_to(MASTER, target_is_directory=True)
            with self.assertRaisesRegex(ConstructionMasterV10Error, "existing output"):
                write_construction_master_v10(DEFINITION, symlink)
            self.assertTrue(symlink.is_symlink())

            late = root / "late"

            def late_build(_definition: Path, _stage: Path) -> dict:
                late.mkdir()
                return {}

            with (
                patch.object(master_v10, "_build_into", side_effect=late_build),
                patch.object(master_v10, "_validate_static", return_value={}),
            ):
                with self.assertRaisesRegex(
                    ConstructionMasterV10Error, "late output collision"
                ):
                    write_construction_master_v10(DEFINITION, late, freeze=True)
            self.assertTrue(late.is_dir())
            self.assertFalse((root / ".late.lock").exists())
            self.assertFalse(
                any(".late.stage-" in path.name for path in root.iterdir())
            )

            fault = root / "fault"
            with patch.object(
                master_v10, "_build_into", side_effect=RuntimeError("boom")
            ):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    write_construction_master_v10(DEFINITION, fault)
            self.assertFalse(fault.exists())
            self.assertFalse((root / ".fault.lock").exists())
            self.assertFalse(
                any(".fault.stage-" in path.name for path in root.iterdir())
            )

            document = json.loads(DEFINITION.read_text(encoding="utf-8"))
            cases = []
            changed = copy.deepcopy(document)
            changed["scope"]["unique_physical_site_count"] = 373
            cases.append((changed, "identity or scope changed"))
            changed = copy.deepcopy(document)
            changed["scope"]["historical_status_is_not_current_status_claim"] = False
            cases.append((changed, "identity or scope changed"))
            for index, (changed, message) in enumerate(cases):
                path = root / f"tamper-{index}.json"
                path.write_bytes(canonical_json(changed))
                with self.assertRaisesRegex(ConstructionMasterV10Error, message):
                    validate_definition(path)

            changed_checkpoint = copy.deepcopy(
                document["inputs"]["replacement_release"]["manifest"]
            )
            changed_checkpoint["sha256"] = "0" * 64
            with self.assertRaisesRegex(
                ConstructionMasterV10Error, "pinned input changed"
            ):
                master_v10._checkpoint_spec(
                    ROOT,
                    changed_checkpoint,
                    "inputs.replacement_release.manifest",
                )

    def test_cli_and_both_import_layouts(self) -> None:
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        cli = subprocess.run(
            [
                sys.executable,
                "scripts/build_construction_master_v10.py",
                "--definition",
                str(DEFINITION),
                "--output",
                str(MASTER),
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
        self.assertEqual(json.loads(cli.stdout)["rows"], 109_285)

        for cwd, package in (
            (ROOT, "datacenter_atlas.construction_master_v10"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.construction_master_v10"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_construction_master_v10; "
                f"result=validate_construction_master_v10(Path({str(MASTER)!r}), "
                f"definition_path=Path({str(DEFINITION)!r}), reproduce=False); "
                "assert result['row_counts']['total']==109285; "
                "assert result['row_counts']['by_tier']=={'A':493,'B':6298,'C':102494}; "
                "assert result['row_counts']['unique_physical_site_count'] is None"
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
