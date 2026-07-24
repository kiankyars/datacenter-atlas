from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
import hashlib
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

import datacenter_atlas.coverage_audit_v2 as coverage_v2
import datacenter_atlas.coverage_audit_v3 as coverage_v3


COVERAGE_IMPL = sys.modules[coverage_v3.build_coverage_audit.__module__]
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v26.json"
AUDIT = ROOT / "audits/2026-07-20-public-open-coverage-v26"
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v25.json"
BASE_AUDIT = ROOT / "audits/2026-07-20-public-open-coverage-v25"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v27.json"
FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v27"
BASE_FEDERATION_DEFINITION = (
    ROOT / "sources/federation-2026-07-20-public-open-v26.json"
)
BASE_FEDERATION = ROOT / "federated_indexes/2026-07-20-public-open-v26"
V62_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v62.json"
V62_RELEASE = ROOT / "releases/2026-07-20-open-seed-v62"
V63_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v63.json"
V63_RELEASE = ROOT / "releases/2026-07-20-open-seed-v63"
V59_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v59.json"
V59_RELEASE = ROOT / "releases/2026-07-20-open-seed-v59"
GLOBAL_RELEASE = ROOT / "releases/2026-07-18-global-open-v3"
REVIEW_RELEASE = ROOT / "releases/2026-07-18-osm-fuzzy-review-v2"
SUPPORT_DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews/2026-07-20-open-seed-v57-active-review-v1.json"
)
SUPPORT = (
    ROOT
    / "satellite_change_reviews/2026-07-20-open-seed-v57-active-review-v1"
)

OLD_RELEASE_ID = "epoch-official-open-seed-v59"
NEW_RELEASE_ID = "epoch-official-open-seed-v62"
GENERATED_AT = "2026-07-21T05:35:00Z"

PINS = {
    DEFINITION: "7275d187e5d490be4a21a941f1d06189729f5357381957f51651d64c9ee0fddd",
    BASE_DEFINITION: (
        "8a238ec8d056dd1162bcdd1e798dd20774271224cc9c6c76cacf0a8a8ada7894"
    ),
    BASE_AUDIT / "manifest.json": (
        "f4b4656b04f558a9d89af6348ede4080c55755729c5efded9fb077d0b9330012"
    ),
    FEDERATION_DEFINITION: (
        "4f0bbb0fcef771966f9d18cdcc28691b4adeb1b9b60d6f2af95fd4c6e592499e"
    ),
    FEDERATION / "federated-index.json": (
        "53302961eb0d6ea2d122c53fdcf585264e79fab0bb47d849fb50033322b8e2c8"
    ),
    FEDERATION / "manifest.json": (
        "7c33486c445992f7174410c4c9cd2c9312b6f180b3a5a8b8e40df0100bb8bf87"
    ),
    FEDERATION / "manifest.sha256": (
        "93af947986aa0fc77fb871521dacf09c9bf8111f17212d19caa9942a03694207"
    ),
    BASE_FEDERATION_DEFINITION: (
        "34a26ee6f747d3dae9a96257b6dd5e7051aacf446ce392f2c6f5087146a66b32"
    ),
    BASE_FEDERATION / "manifest.json": (
        "7c46daa54ea1de6da325f495f4a54fda2e1c16bae3a0ca7fdb6901ba7d391361"
    ),
    V62_DEFINITION: (
        "e992f321a463c4a4316ed617dcc1efef505f01792fb91f6e13aded94e10b6f66"
    ),
    V62_RELEASE / "manifest.json": (
        "60c7172a20a7ff43a3644902d5c186b015e06228737ea8b39c7a5082d3d94ea6"
    ),
    V59_DEFINITION: (
        "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
    ),
    V59_RELEASE / "manifest.json": (
        "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
    ),
    GLOBAL_RELEASE / "manifest.json": (
        "fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562"
    ),
    REVIEW_RELEASE / "manifest.json": (
        "60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c"
    ),
    SUPPORT_DEFINITION: (
        "eb009c496f805d8c68e9510904f45f5a7c82af3fe3f0428a4c96d97dd38aa482"
    ),
}

LEGACY_CODE_PINS = {
    ROOT / "datacenter_atlas/coverage_audit.py": (
        82_129,
        "5b383a4b06f3a767dbb45c52c49e10da5c85f383d1739bc6af9abebff6617ad3",
    ),
    ROOT / "scripts/build_coverage_audit.py": (
        1_259,
        "e8d6558588cd37a50a162937dccb7f5dee9088f35aac2c053714bc7c211ca79d",
    ),
    ROOT / "datacenter_atlas/coverage_audit_v2.py": (
        54_772,
        "f4af61258d90054fe6f3c28c2470164c096e2186cf97d4445a09aa4675bb2b52",
    ),
    ROOT / "coverage_audit_v2.py": (
        137,
        "4923b322edd996ec977ab85c8c928b7d39b4eecb2dab080a25e6df03a2f06764",
    ),
    ROOT / "scripts/build_coverage_audit_v2.py": (
        1_456,
        "0d4f910280d1400c27fc1a91eb71b6727cfd678a8b89bd43f676c8e294d9fe30",
    ),
}

V3_CODE_PINS = {
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
}

UPSTREAM_CARRIER_PINS = {
    ROOT / "datacenter_atlas/federated_release_v2.py": (
        26_557,
        "ff16627d62a5bda3d760e9d211de9923c5691d13760c6abe7540d2b1aff216f3",
    ),
    ROOT / "federated_release_v2.py": (
        144,
        "f3b44cd056a181b73536bab186c921c6182a0c32d03054e4a6a34cb292d35906",
    ),
    ROOT / "datacenter_atlas/federated_release_v3.py": (
        26_524,
        "e8504ca3bba1f201085579df20ec0cde4ebd700284e402f5104b656dd7c24528",
    ),
    ROOT / "federated_release_v3.py": (
        136,
        "eb95516c9d05b368f389b4100f08139c0d939639d833d6943a56199f1856d221",
    ),
}

ARTIFACTS = {
    "REPORT.md": (
        4_764,
        "9c9d17eca2bb6820cd61c803c8b7295a1983776c627db79533ed09a2c202d4a1",
    ),
    "coverage-audit.json": (
        2_465_631,
        "38a6d45db49b0fcadbcbe664613a9290e9f4041cea33dcc7b1fa13d387b77980",
    ),
    "coverage.csv": (
        335_848,
        "76e0e76236cec8bdef1bc00584c76660bb661707a15f217ace4081baac29eb84",
    ),
    "gap-registry.json": (
        1_941_659,
        "a2a5187c5cd249169f8d5a12df51f9ba4c1453dc0635e6b15459f0eeb7c2737c",
    ),
    "manifest.json": (
        3_379,
        "181dd9c24f7445cade64e20708d01485d67d78c0124b6f88f2071d9b920de931",
    ),
    "manifest.sha256": (
        80,
        "883efb8d198600566ee4c36a668f6466fb4b12917a50cffcd3353ecea2d08837",
    ),
}

AUDIT_TREE_SHA256 = "ed88ac54e1358233bb7270836d00aff6063ecf4b9fbfbdaf3e109fb968ea0fe8"
BASE_AUDIT_TREE_SHA256 = (
    "cd867e629d5447a023d73fa61ad2353bfd7b3ef8398fed9183bfab97288b1548"
)
FEDERATION_TREE_SHA256 = (
    "1eba8fced5248c8f06f2e77b49ffb86519e723feb2c7a2d3f5eb7cd3e36d5671"
)
BASE_FEDERATION_TREE_SHA256 = (
    "f512cca96449fc844f6e18f72ba9705862b06563af743cb775e9ed3d6ef9ab5e"
)
V62_RELEASE_TREE_SHA256 = (
    "71ec5c0a2f0af7d5557de5479f81fcb29dca0ae6342736681e3bdc12ac4ae8fb"
)
V59_RELEASE_TREE_SHA256 = (
    "53cb173fb0e07b8dba8f9bb974cc533b38ba006590583725baf122cb8ba8d636"
)
SUPPORT_TREE_SHA256 = (
    "0e79d853fd6ee4ba11ead97754850efe9de16c2c9782a47ce6e01105e3358a41"
)

EXPECTED_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 754,
    "methodology_support_artifacts": 1,
    "methodology_support_jobs": 74,
    "methodology_support_views": 71,
    "non_review_source_scoped_entity_records": 10_025,
    "open_gaps": 3_736,
    "review_only_source_scoped_entity_records": 6_130,
    "source_scoped_entity_records": 16_155,
    "unique_physical_sites": None,
}

EXPECTED_DELTA = {
    "coverage_groups": 30,
    "non_review_source_scoped_entity_records": 31,
    "open_gaps": 120,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 31,
}

EXPECTED_FIELD_DELTA = {
    "capacity_entity_rows": 11,
    "capacity_observations": 11,
    "construction_evidence_observations": 9,
    "coordinate_rows": 2,
    "informative_lifecycle_status_rows": 16,
    "lifecycle_status_rows": 16,
    "non_review_rows": 31,
    "non_review_under_construction_rows": 8,
    "operating_model_rows": 4,
    "pipeline_rows": 8,
    "review_only_rows": 0,
    "source_scoped_rows": 31,
    "status_as_of_rows": 16,
    "status_evidence_rows": 16,
    "under_construction_rows": 8,
    "unresolved_lifecycle_status_rows": 15,
    "workload_rows": 1,
}

POST_V62_INPUTS = {
    "sources/curated-official-2026-07-20-cdc-beard-be1.json",
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

V63_ONLY_INPUTS = {
    "sources/curated-official-2026-07-20-core-scientific-dalton-4.json",
    "sources/curated-official-2026-07-20-databank-iad6-culpeper.json",
    "sources/curated-official-2026-07-20-powerhouse-irving-building-1-topout.json",
    "sources/curated-official-2026-07-20-qts-fayetteville-active-construction-program.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise AssertionError(f"unsupported tree entry: {relative}")
    return digest.hexdigest()


class CoverageAuditV26Tests(unittest.TestCase):
    maxDiff = None

    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError("coverage audit v26 attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        stack.enter_context(patch.object(subprocess, "run", side_effect=failure))
        stack.enter_context(patch.object(subprocess, "Popen", side_effect=failure))

    def _definition_copy(
        self, directory: Path, transform: object | None = None
    ) -> Path:
        document = json.loads(DEFINITION.read_text(encoding="utf-8"))
        document["federated_index"]["path"] = str(FEDERATION)
        release_paths = {
            NEW_RELEASE_ID: V62_RELEASE,
            "global-open-v3": GLOBAL_RELEASE,
            "osm-fuzzy-review-v2": REVIEW_RELEASE,
        }
        for child in document["children"]:
            child["release_path"] = str(release_paths[child["release_id"]])
        support = document["methodology_support_artifacts"][0]
        support["directory"] = str(SUPPORT)
        support["definition"]["path"] = str(SUPPORT_DEFINITION)
        if callable(transform):
            transform(document)
        path = directory / "definition.json"
        path.write_bytes(canonical_json(document))
        return path

    def test_frozen_pins_trees_modes_and_adjacent_v25_v26(self) -> None:
        for path, expected in PINS.items():
            self.assertEqual(sha256(path), expected, path)
        code_pins = {
            **LEGACY_CODE_PINS,
            **V3_CODE_PINS,
            **UPSTREAM_CARRIER_PINS,
        }
        for path, expected in code_pins.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(
            {path.name: checkpoint(path) for path in AUDIT.iterdir()}, ARTIFACTS
        )
        self.assertEqual(tree_digest(AUDIT), AUDIT_TREE_SHA256)
        self.assertEqual(tree_digest(BASE_AUDIT), BASE_AUDIT_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION), FEDERATION_TREE_SHA256)
        self.assertEqual(
            tree_digest(BASE_FEDERATION), BASE_FEDERATION_TREE_SHA256
        )
        self.assertEqual(tree_digest(V62_RELEASE), V62_RELEASE_TREE_SHA256)
        self.assertEqual(tree_digest(V59_RELEASE), V59_RELEASE_TREE_SHA256)
        self.assertEqual(tree_digest(SUPPORT), SUPPORT_TREE_SHA256)
        self.assertEqual(stat.S_IMODE(AUDIT.stat().st_mode), 0o555)
        for path in AUDIT.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        base = coverage_v2.validate_coverage_audit(
            BASE_AUDIT, definition_path=BASE_DEFINITION
        )
        current = coverage_v3.validate_coverage_audit(
            AUDIT, definition_path=DEFINITION
        )
        self.assertEqual(base["audit_id"], "public-open-coverage-v25")
        self.assertEqual(current["audit_id"], "public-open-coverage-v26")
        self.assertEqual(tree_digest(BASE_AUDIT), BASE_AUDIT_TREE_SHA256)

    def test_definition_is_exact_v25_successor_and_field_order_is_stable(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        current = json.loads(DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["audit_id"] = "public-open-coverage-v26"
        expected["generated_at"] = GENERATED_AT
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": PINS[V62_RELEASE / "manifest.json"],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v62",
            }
        )
        expected["federated_index"] = {
            "expected_manifest_sha256": PINS[FEDERATION / "manifest.json"],
            "path": "../federated_indexes/2026-07-20-public-open-v27",
        }
        for references in expected["methodology_evidence_classification"].values():
            for reference in references:
                if reference["release_id"] == OLD_RELEASE_ID:
                    reference["release_id"] = NEW_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), canonical_json(current))
        self.assertEqual(current, expected)
        self.assertEqual(
            current["methodology_support_artifacts"],
            base["methodology_support_artifacts"],
        )
        self.assertEqual(current["public_benchmark"], base["public_benchmark"])
        self.assertEqual(current["as_of"], "2026-07-20")
        self.assertTrue(DEFINITION.name.startswith("coverage-audit-2026-07-20"))
        self.assertEqual(
            (AUDIT / "coverage.csv").read_bytes().splitlines()[0],
            (BASE_AUDIT / "coverage.csv").read_bytes().splitlines()[0],
        )

    def test_v62_to_federation_v27_to_audit_lineage_and_v63_exclusion(self) -> None:
        federation_definition = json.loads(
            FEDERATION_DEFINITION.read_text(encoding="utf-8")
        )
        federation_index = json.loads(
            (FEDERATION / "federated-index.json").read_text(encoding="utf-8")
        )
        audit = json.loads(
            (AUDIT / "coverage-audit.json").read_text(encoding="utf-8")
        )
        defined_children = {
            item["release_id"]: item for item in federation_definition["children"]
        }
        indexed_children = {
            item["release_id"]: item for item in federation_index["releases"]
        }
        audit_children = {
            item["release_id"]: item for item in audit["inputs"]["children"]
        }
        self.assertEqual(
            set(defined_children),
            {NEW_RELEASE_ID, "global-open-v3", "osm-fuzzy-review-v2"},
        )
        self.assertEqual(set(indexed_children), set(defined_children))
        self.assertEqual(set(audit_children), set(defined_children))
        self.assertEqual(
            defined_children[NEW_RELEASE_ID]["expected_manifest_sha256"],
            PINS[V62_RELEASE / "manifest.json"],
        )
        self.assertEqual(
            indexed_children[NEW_RELEASE_ID]["manifest"]["sha256"],
            PINS[V62_RELEASE / "manifest.json"],
        )
        self.assertEqual(
            audit_children[NEW_RELEASE_ID]["manifest"]["sha256"],
            PINS[V62_RELEASE / "manifest.json"],
        )
        self.assertEqual(
            audit["inputs"]["federated_index"]["index"]["sha256"],
            PINS[FEDERATION / "federated-index.json"],
        )
        self.assertEqual(
            audit["inputs"]["federated_index"]["manifest"]["sha256"],
            PINS[FEDERATION / "manifest.json"],
        )
        self.assertEqual(
            indexed_children[NEW_RELEASE_ID]["manifest"],
            {
                "as_of": "2026-07-20",
                "bytes": 10_934,
                "current_status_inferred": False,
                "file": "manifest.json",
                "format": "datacenter-atlas-release-v1",
                "lifecycle_freshness_records": 415,
                "lifecycle_status_semantics": "last_observed",
                "publication_contract_version": 4,
                "recorded_at": "2026-07-21T04:35:00Z",
                "sha256": PINS[V62_RELEASE / "manifest.json"],
            },
        )

        v62 = json.loads(V62_DEFINITION.read_text(encoding="utf-8"))
        v63 = json.loads(V63_DEFINITION.read_text(encoding="utf-8"))
        v62_inputs = {row["path"] for row in v62["curated_inputs"]}
        v63_inputs = {row["path"] for row in v63["curated_inputs"]}
        self.assertTrue(POST_V62_INPUTS.isdisjoint(v62_inputs))
        self.assertEqual(v63_inputs - v62_inputs, V63_ONLY_INPUTS)
        self.assertEqual(
            sha256(V63_RELEASE / "manifest.json"),
            "8ee3539f639641c7f97827ba7a21c13b7e907881ba858970e701675510eab4ba",
        )
        for path in (DEFINITION, *AUDIT.iterdir()):
            raw = path.read_bytes()
            self.assertNotIn(b"open-seed-v63", raw, path)
            self.assertNotIn(V63_RELEASE.name.encode(), raw, path)
            for source in POST_V62_INPUTS:
                self.assertNotIn(Path(source).name.encode(), raw, path)

    def test_exact_delta_inherited_rows_and_no_silent_promotions(self) -> None:
        base = json.loads(
            (BASE_AUDIT / "coverage-audit.json").read_text(encoding="utf-8")
        )
        current = json.loads(
            (AUDIT / "coverage-audit.json").read_text(encoding="utf-8")
        )
        base_manifest = json.loads(
            (BASE_AUDIT / "manifest.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (AUDIT / "manifest.json").read_text(encoding="utf-8")
        )
        for field, expected in EXPECTED_COUNTS.items():
            self.assertEqual(manifest["counts"][field], expected, field)
        count_delta = {
            key: manifest["counts"][key] - base_manifest["counts"][key]
            for key in EXPECTED_DELTA
        }
        self.assertEqual(count_delta, EXPECTED_DELTA)
        field_delta = {
            key: current["totals"]["field_totals"][key]
            - base["totals"]["field_totals"][key]
            for key in EXPECTED_FIELD_DELTA
        }
        self.assertEqual(field_delta, EXPECTED_FIELD_DELTA)
        self.assertEqual(
            current["totals"]["field_totals"][
                "administrative_assignment_status_counts"
            ]["source_label_only"]
            - base["totals"]["field_totals"][
                "administrative_assignment_status_counts"
            ]["source_label_only"],
            31,
        )
        self.assertEqual(
            {
                key: current["totals"]["field_totals"]["status_counts"].get(key, 0)
                - base["totals"]["field_totals"]["status_counts"].get(key, 0)
                for key in set(
                    current["totals"]["field_totals"]["status_counts"]
                )
                | set(base["totals"]["field_totals"]["status_counts"])
            },
            {
                "__MISSING__": 15,
                "announced": 0,
                "civil_works": 0,
                "commissioning": 1,
                "expansion": 0,
                "foundations": 0,
                "lead": 0,
                "mep_electrical": 0,
                "operational": 5,
                "permitted": 0,
                "proposed": 0,
                "shell": 2,
                "site_control": 0,
                "site_preparation": 0,
                "under_construction": 8,
                "unknown": 0,
            },
        )

        for child_release in ("global-open-v3", "osm-fuzzy-review-v2"):
            old_groups = [
                row
                for row in base["groups"]
                if row["child_release"] == child_release
            ]
            new_groups = [
                row
                for row in current["groups"]
                if row["child_release"] == child_release
            ]
            self.assertEqual(new_groups, old_groups)
        self.assertEqual(
            current["inputs"]["methodology_support_artifacts"],
            base["inputs"]["methodology_support_artifacts"],
        )

        scope = current["scope"]
        self.assertEqual(scope["unit"], "source_scoped_release_row")
        self.assertTrue(scope["provisional_open_layer_audit"])
        self.assertFalse(scope["scrutica_included"])
        for field in (
            "children_merged",
            "cross_source_deduplication",
            "review_candidates_promoted",
            "candidate_rows_counted_as_facilities",
            "current_status_inferred",
            "methodology_support_artifacts_are_child_evidence",
            "methodology_support_artifacts_are_countable",
            "methodology_support_artifacts_are_promoted",
            "methodology_support_artifacts_create_facility_rows",
            "methodology_support_artifacts_create_lifecycle_observations",
        ):
            self.assertIs(scope[field], False, field)
        self.assertIsNone(scope["confirmed_duplicate_relationships"])
        self.assertIsNone(scope["unique_physical_sites"])
        self.assertIsNone(current["totals"]["unique_physical_sites"])
        self.assertEqual(
            current["semianalysis_public_comparison"]["overall_parity"]["status"],
            "pending",
        )

    def test_gap_semantics_and_nonadditive_satellite_support_are_inherited(self) -> None:
        base = json.loads(
            (BASE_AUDIT / "gap-registry.json").read_text(encoding="utf-8")
        )
        current = json.loads(
            (AUDIT / "gap-registry.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(current["gaps"]), 3_736)
        self.assertEqual(current["summary"]["open_gaps"], 3_736)
        self.assertEqual(
            current["summary"]["by_severity"],
            {"high": 267, "info": 46, "low": 1_998, "medium": 1_425},
        )
        self.assertTrue(all(row["status"] == "open" for row in current["gaps"]))
        self.assertEqual(
            list(current["gaps"][0]), list(base["gaps"][0])
        )
        for child_release in ("global-open-v3", "osm-fuzzy-review-v2"):
            old_rows = [
                {key: value for key, value in row.items() if key != "gap_id"}
                for row in base["gaps"]
                if row.get("child_release") == child_release
            ]
            new_rows = [
                {key: value for key, value in row.items() if key != "gap_id"}
                for row in current["gaps"]
                if row.get("child_release") == child_release
            ]
            self.assertEqual(new_rows, old_rows)

        audit = json.loads(
            (AUDIT / "coverage-audit.json").read_text(encoding="utf-8")
        )
        support = audit["inputs"]["methodology_support_artifacts"]
        self.assertEqual(len(support), 1)
        self.assertEqual(support[0]["counts"], {"jobs": 74, "views": 71})
        self.assertTrue(support[0]["scope"]["review_only"])
        self.assertTrue(
            all(
                support[0]["scope"][field] is False
                for field in (
                    "atlas_mutation",
                    "child_evidence",
                    "countable",
                    "current_status_claim",
                    "facility_rows",
                    "lifecycle_observations",
                    "promoted",
                )
            )
        )
        self.assertTrue(
            all(value is False for value in support[0]["guardrails"].values())
        )
        methodology = audit["methodology_evidence_classification"]
        for category in ("computer_vision", "satellite_imagery"):
            record = methodology[category]
            self.assertEqual(record["status"], "partial_reviewed_method_evidence")
            self.assertEqual(record["evidence_reference_count"], 0)
            self.assertFalse(record["methodology_support_is_child_evidence"])
            self.assertFalse(record["methodology_support_is_promoted"])
            self.assertFalse(record["methodology_support_is_countable"])
        self.assertEqual(
            methodology["foia"]["status"], "absent_from_audited_children"
        )

    def test_lifecycle_is_dated_observation_not_current_status(self) -> None:
        audit = json.loads(
            (AUDIT / "coverage-audit.json").read_text(encoding="utf-8")
        )
        self.assertEqual(audit["generated_at"], GENERATED_AT)
        self.assertEqual(
            audit["lifecycle_contract"],
            {
                "current_status_classification": "unknown",
                "current_status_inferred": False,
                "publication_v4_children": [
                    {
                        "current_status_inferred": False,
                        "lifecycle_freshness_records": 415,
                        "lifecycle_status_semantics": "last_observed",
                        "publication_contract_version": 4,
                        "release_id": NEW_RELEASE_ID,
                    }
                ],
                "status_semantics": "last_observed",
            },
        )
        report = (AUDIT / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("not a facility census", report)
        self.assertIn("dated observations, not current-status assertions", report)
        self.assertIn("provisional open layers only", report)
        self.assertIn("Unique physical sites: **unknown**", report)
        self.assertIn("SemiAnalysis parity determination: **pending**", report)

    def test_byte_exact_offline_double_replay_and_idempotent_publication(self) -> None:
        frozen = {path.name: path.read_bytes() for path in AUDIT.iterdir()}
        with ExitStack() as stack:
            self._offline(stack)
            first = coverage_v3.build_coverage_audit(DEFINITION)
            second = coverage_v3.build_coverage_audit(DEFINITION)
            existing = coverage_v3.write_coverage_audit(DEFINITION, AUDIT)
        self.assertEqual(dict(first.payloads), dict(second.payloads))
        self.assertEqual(dict(first.payloads), frozen)
        self.assertEqual(existing["audit_id"], "public-open-coverage-v26")
        self.assertEqual(
            {path.name: path.read_bytes() for path in AUDIT.iterdir()}, frozen
        )
        self.assertEqual(tree_digest(AUDIT), AUDIT_TREE_SHA256)

    def test_definition_support_and_closed_output_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="coverage-v26-tamper-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)

            def bad_federation(document: dict[str, object]) -> None:
                document["federated_index"]["expected_manifest_sha256"] = "0" * 64

            def bad_support_tree(document: dict[str, object]) -> None:
                document["methodology_support_artifacts"][0]["closed_tree"][
                    "inventory_sha256"
                ] = "0" * 64

            def v63_child(document: dict[str, object]) -> None:
                child = next(
                    item
                    for item in document["children"]
                    if item["release_id"] == NEW_RELEASE_ID
                )
                child.update(
                    {
                        "expected_manifest_sha256": sha256(
                            V63_RELEASE / "manifest.json"
                        ),
                        "release_id": "epoch-official-open-seed-v63",
                        "release_path": str(V63_RELEASE),
                    }
                )
                for references in document[
                    "methodology_evidence_classification"
                ].values():
                    for reference in references:
                        if reference["release_id"] == NEW_RELEASE_ID:
                            reference["release_id"] = "epoch-official-open-seed-v63"

            cases = (
                (bad_federation, "manifest SHA-256 does not match"),
                (bad_support_tree, "closed tree changed"),
                (v63_child, "child path mapping must exactly match federated release IDs"),
            )
            for position, (transform, message) in enumerate(cases):
                directory = root / str(position)
                directory.mkdir()
                definition = self._definition_copy(directory, transform)
                with self.subTest(message=message):
                    with self.assertRaisesRegex(
                        coverage_v3.CoverageAuditError, message
                    ):
                        coverage_v3.build_coverage_audit(definition)

            tampered = root / "tampered"
            shutil.copytree(AUDIT, tampered)
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

            wrong_mode = root / "wrong-mode"
            shutil.copytree(AUDIT, wrong_mode)
            wrong_mode.chmod(0o755)
            with self.assertRaisesRegex(
                coverage_v3.CoverageAuditError, "root must have mode 0555"
            ):
                coverage_v3.validate_coverage_audit(wrong_mode)

            linked_entry = root / "linked-entry"
            shutil.copytree(AUDIT, linked_entry)
            linked_entry.chmod(0o755)
            linked_report = linked_entry / "REPORT.md"
            linked_report.chmod(0o644)
            linked_report.unlink()
            linked_report.symlink_to(AUDIT / "REPORT.md")
            linked_entry.chmod(0o555)
            with self.assertRaisesRegex(
                coverage_v3.CoverageAuditError,
                "audit entry must be a regular file",
            ):
                coverage_v3.validate_coverage_audit(linked_entry)

    def test_collision_symlink_and_fault_cleanup_fail_closed(self) -> None:
        bundle = coverage_v3.build_coverage_audit(DEFINITION)
        with tempfile.TemporaryDirectory(
            prefix="coverage-v26-writer-", dir="/private/tmp"
        ) as temporary:
            root = Path(temporary)
            with patch.object(
                COVERAGE_IMPL, "build_coverage_audit", return_value=bundle
            ):
                collision = root / "collision"
                collision.write_bytes(b"do-not-replace\n")
                before = collision.read_bytes()
                with self.assertRaises(coverage_v3.CoverageAuditError):
                    coverage_v3.write_coverage_audit(DEFINITION, collision)
                self.assertEqual(collision.read_bytes(), before)

                linked = root / "linked"
                linked.symlink_to(AUDIT, target_is_directory=True)
                with self.assertRaisesRegex(
                    coverage_v3.CoverageAuditError,
                    "audit output may not be a symlink",
                ):
                    coverage_v3.write_coverage_audit(DEFINITION, linked)
                self.assertTrue(linked.is_symlink())

                late = root / "late"
                promote = COVERAGE_IMPL.federation_v3._promote_noreplace

                def late_collision(stage: Path, destination: Path) -> None:
                    destination.mkdir()
                    promote(stage, destination)

                with patch.object(
                    COVERAGE_IMPL.federation_v3,
                    "_promote_noreplace",
                    side_effect=late_collision,
                ):
                    with self.assertRaisesRegex(
                        COVERAGE_IMPL.federation_v3.FederatedReleaseError,
                        "late output collision; refusing overwrite",
                    ):
                        coverage_v3.write_coverage_audit(DEFINITION, late)
                self.assertTrue(late.is_dir())
                self.assertEqual(list(late.iterdir()), [])
                self.assertFalse(
                    any(f".{late.name}.stage-" in path.name for path in root.iterdir())
                )

                fault = root / "fault"
                with patch.object(
                    COVERAGE_IMPL.legacy,
                    "_write_bytes",
                    side_effect=OSError("injected write fault"),
                ):
                    with self.assertRaisesRegex(OSError, "injected write fault"):
                        coverage_v3.write_coverage_audit(DEFINITION, fault)
                self.assertFalse(fault.exists())
                self.assertFalse(
                    any(f".{fault.name}.stage-" in path.name for path in root.iterdir())
                )

    def test_cli_and_both_import_layouts(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        with tempfile.TemporaryDirectory(
            prefix="coverage-v26-cli-", dir="/private/tmp"
        ) as temporary:
            output = Path(temporary) / AUDIT.name
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_coverage_audit_v3.py"),
                    "--definition",
                    str(DEFINITION),
                    "--output-dir",
                    str(output),
                ],
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["audit_id"], "public-open-coverage-v26")
            self.assertEqual(payload["coverage_groups"], 754)
            self.assertEqual(payload["source_scoped_entity_records"], 16_155)
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()},
                {path.name: path.read_bytes() for path in AUDIT.iterdir()},
            )

        for cwd, module in (
            (ROOT, "datacenter_atlas.coverage_audit_v3"),
            (WORKSPACE, "datacenter_atlas.coverage_audit_v3"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.coverage_audit_v3"),
        ):
            import_environment = os.environ.copy()
            import_environment["PYTHONDONTWRITEBYTECODE"] = "1"
            import_environment["PYTHONPATH"] = str(cwd)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        f"import {module} as m; "
                        "assert m.build_coverage_audit; "
                        "assert m.validate_coverage_audit; "
                        "assert m.write_coverage_audit"
                    ),
                ],
                cwd=cwd,
                env=import_environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
