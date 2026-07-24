from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
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

import datacenter_atlas.coverage_audit as coverage_module
import datacenter_atlas.federated_release as federation_module
from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    PIPELINE_STATUSES,
    CoverageAuditError,
    build_coverage_audit,
    validate_coverage_audit,
    write_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v24.json"
RELEASE = ROOT / "audits/2026-07-20-public-open-coverage-v24"
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-20-public-open-v23.json"
BASE_RELEASE = ROOT / "audits/2026-07-20-public-open-coverage-v23"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-20-public-open-v25.json"
FEDERATION_RELEASE = ROOT / "federated_indexes/2026-07-20-public-open-v25"
OPEN_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v56.json"
OPEN_RELEASE = ROOT / "releases/2026-07-20-open-seed-v56"

GENERATED_AT = "2026-07-20T22:55:00Z"
FEDERATION_GENERATED_AT = "2026-07-20T22:54:00Z"
OPEN_RECORDED_AT = "2026-07-20T22:34:00Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v55"
NEW_RELEASE_ID = "epoch-official-open-seed-v56"

DEFINITION_SHA256 = "4f236d3bb9b39a546c592f2de2f9e5f771b5c913ea3703d5742c4b99772ed937"
TREE_SHA256 = "3828ae78a4b9c29927a4f770fbcc4d36fa10cbada8d9cdde578d447d98e03d37"
BASE_DEFINITION_SHA256 = (
    "3c35a36e02aefbcb169dee6a0dd8b7fe5480983767f0766fd3e7f0c942699436"
)
BASE_TREE_SHA256 = "6df5bd35b44e8efc5d230246ae36c5f3093876cedf64198f362f2613aeeddb8f"
FEDERATION_DEFINITION_SHA256 = (
    "2b60e26e211e584d60f6743beef1a3ed7f06714297cd36896cd2f60a0067e829"
)
FEDERATION_TREE_SHA256 = (
    "962a7d0733b363935f6640bc36d0930573e1c04ba91679dc7cdbef8cada83e57"
)
OPEN_DEFINITION_SHA256 = (
    "b41bf23073c51aed7756f1fa5ae7d081c5d349914b9794531fe0c1010396962c"
)
OPEN_TREE_SHA256 = "c75b3b4b2fb066dce2e8549bdfa6fdbf06412c9885b5a9aeaea7eb36fcfe61d2"

CHECKPOINTS = {
    DEFINITION: (3_871, DEFINITION_SHA256),
    BASE_DEFINITION: (3_871, BASE_DEFINITION_SHA256),
    BASE_RELEASE / "manifest.json": (
        2_240,
        "7d282d3d725a3882475bf69f581a6b70f1505ccc135ecc7027b01cd7269e3e23",
    ),
    FEDERATION_DEFINITION: (1_788, FEDERATION_DEFINITION_SHA256),
    FEDERATION_RELEASE / "federated-index.json": (
        24_828,
        "2b261707bfe1c1e1b78f61217e6e42a46bb75e2e7fb40139c8dcd2ca53cc59db",
    ),
    FEDERATION_RELEASE / "manifest.json": (
        986,
        "36a4e7615a014cac0fb98de9c2f66ad28fdd5d8367864e4d60c3594c4466385f",
    ),
    FEDERATION_RELEASE / "manifest.sha256": (
        80,
        "59a75fc6216e83b703ec16aaaad731fa07939d5a1c05fff488d2d3aab61a94da",
    ),
    OPEN_DEFINITION: (67_918, OPEN_DEFINITION_SHA256),
    OPEN_RELEASE / "manifest.json": (
        9_274,
        "f8bc9b4bef238288f72160e7a21533321b452d7b571d707b1de492a2f62f1cdd",
    ),
    ROOT / "datacenter_atlas/coverage_audit.py": (
        82_129,
        "5b383a4b06f3a767dbb45c52c49e10da5c85f383d1739bc6af9abebff6617ad3",
    ),
    ROOT / "scripts/build_coverage_audit.py": (
        1_259,
        "e8d6558588cd37a50a162937dccb7f5dee9088f35aac2c053714bc7c211ca79d",
    ),
}

ARTIFACTS = {
    "REPORT.md": (
        4_152,
        "a54ca3debcc5d25bf7aadcba4d016fd162595a40268ba63635a2ee77a1d48305",
    ),
    "coverage-audit.json": (
        2_194_393,
        "ddf165eb455d3af2c7577efac6b43ff1b7d36018a366a1d2e284cedfc052092a",
    ),
    "coverage.csv": (
        303_804,
        "c91dd8a560887dfae6a3e55757351c28267abef10b43f7aa431f70361d23c3dc",
    ),
    "gap-registry.json": (
        1_792_002,
        "7755df09b40e6d02026ff7700c5aa220b57b3d6a635633705b12a176395d93a3",
    ),
    "manifest.json": (
        2_240,
        "7fa0fd899ba268bef8d3105fc542e29c150728e0640484c9553d83d4eca392a2",
    ),
    "manifest.sha256": (
        80,
        "aa537a45183b48c4ea2b8813f7794089f12d24ed57657f52bf744911ac4bfbbc",
    ),
}

NEW_SOURCE_COUNTRIES = {
    "paix_official_prismic": ("Senegal", "SN", "SEN"),
    "pentapoint_official_webflow": ("Thailand", "TH", "THA"),
}

FORBIDDEN_READ_FRAGMENTS = (
    "sources/open-seed-2026-07-20-v55.json",
    "releases/2026-07-20-open-seed-v55",
    "federated_indexes/2026-07-20-public-open-v24",
    "sources/curated-official-2026-07-20-paix-dkr1-dakar.json",
    "sources/curated-official-2026-07-20-pentapoint-emd-bkk01-sathorn.json",
)


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
            raise AssertionError(f"bundle contains symlink: {relative}")
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
            raise AssertionError(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def normalize(value: object) -> object:
    if isinstance(value, dict):
        return {key: normalize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize(child) for child in value]
    if value == OLD_RELEASE_ID:
        return NEW_RELEASE_ID
    return value


def group_key(group: dict[str, object]) -> tuple[object, ...]:
    normalized = normalize(group)
    assert isinstance(normalized, dict)
    return tuple(
        normalized[field]
        for field in (
            "child_release",
            "scope_type",
            "source_family",
            "country",
            "country_iso_a2",
            "country_iso_a3",
        )
    )


def gap_key(gap: dict[str, object]) -> tuple[object, ...]:
    normalized = normalize(gap)
    assert isinstance(normalized, dict)
    return tuple(
        normalized[field]
        for field in (
            "scope_type",
            "child_release",
            "source_family",
            "country",
            "field",
        )
    )


def normalized_gap(gap: dict[str, object]) -> dict[str, object]:
    normalized = normalize(gap)
    assert isinstance(normalized, dict)
    normalized.pop("gap_id")
    return normalized


class CoverageAuditV24Tests(unittest.TestCase):
    def _offline(self, stack: ExitStack) -> None:
        failure = AssertionError(
            "v24 coverage attempted network or superseded/direct-source access"
        )
        coverage_regular_bytes = coverage_module._regular_bytes
        federation_regular_bytes = federation_module._regular_bytes
        path_open = Path.open

        def check(path: Path) -> None:
            rendered = path.as_posix()
            if any(marker in rendered for marker in FORBIDDEN_READ_FRAGMENTS):
                raise failure

        def coverage_guarded(path: Path, label: str) -> bytes:
            check(path)
            return coverage_regular_bytes(path, label)

        def federation_guarded(path: Path, label: str) -> bytes:
            check(path)
            return federation_regular_bytes(path, label)

        def open_guarded(path: Path, *args: object, **kwargs: object):
            check(path)
            return path_open(path, *args, **kwargs)

        stack.enter_context(
            patch.object(
                coverage_module, "_regular_bytes", side_effect=coverage_guarded
            )
        )
        stack.enter_context(
            patch.object(
                federation_module, "_regular_bytes", side_effect=federation_guarded
            )
        )
        stack.enter_context(patch.object(Path, "open", open_guarded))
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))

    def test_exact_pins_double_offline_reproduction_modes_and_trees(self) -> None:
        for path, expected in CHECKPOINTS.items():
            self.assertEqual(checkpoint(path), expected, path)
        self.assertEqual(tree_digest(BASE_RELEASE), BASE_TREE_SHA256)
        self.assertEqual(tree_digest(FEDERATION_RELEASE), FEDERATION_TREE_SHA256)
        self.assertEqual(tree_digest(OPEN_RELEASE), OPEN_TREE_SHA256)

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        self.assertEqual(tree_digest(RELEASE), TREE_SHA256)
        self.assertEqual({path.name for path in RELEASE.iterdir()}, set(ARTIFACTS))
        frozen = {}
        for path in RELEASE.iterdir():
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual(checkpoint(path), ARTIFACTS[path.name], path.name)
            frozen[path.name] = path.read_bytes()

        with ExitStack() as stack:
            self._offline(stack)
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            validated = validate_coverage_audit(RELEASE, definition_path=DEFINITION)
            idempotent = write_coverage_audit(DEFINITION, RELEASE)
        self.assertEqual(first, second)
        self.assertEqual(first.audit, validated)
        self.assertEqual(first.audit, idempotent)
        self.assertEqual(dict(first.payloads), frozen)
        self.assertEqual(
            {path.name: path.read_bytes() for path in RELEASE.iterdir()}, frozen
        )

        payload = b"".join([DEFINITION.read_bytes(), *frozen.values()])
        for marker in FORBIDDEN_READ_FRAGMENTS:
            self.assertNotIn(marker.encode("ascii"), payload, marker)

    def test_definition_is_only_the_v23_to_v25_v56_lineage_transform(self) -> None:
        base = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        expected = deepcopy(base)
        expected["audit_id"] = "public-open-coverage-v24"
        expected["generated_at"] = GENERATED_AT
        expected["federated_index"] = {
            "expected_manifest_sha256": CHECKPOINTS[
                FEDERATION_RELEASE / "manifest.json"
            ][1],
            "path": "../federated_indexes/2026-07-20-public-open-v25",
        }
        child = next(
            item
            for item in expected["children"]
            if item["release_id"] == OLD_RELEASE_ID
        )
        child.update(
            {
                "expected_manifest_sha256": CHECKPOINTS[OPEN_RELEASE / "manifest.json"][
                    1
                ],
                "release_id": NEW_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v56",
            }
        )
        for references in expected["methodology_evidence_classification"].values():
            for reference in references:
                if reference["release_id"] == OLD_RELEASE_ID:
                    reference["release_id"] = NEW_RELEASE_ID

        raw = DEFINITION.read_bytes()
        current = json.loads(raw)
        self.assertEqual(raw, canonical_json(current))
        self.assertEqual(current, expected)
        self.assertEqual(current["public_benchmark"], base["public_benchmark"])
        self.assertEqual(
            current["methodology_evidence_classification"]["permits"],
            [
                {**reference, "release_id": NEW_RELEASE_ID}
                for reference in base["methodology_evidence_classification"]["permits"]
            ],
        )
        for category in (
            "computer_vision",
            "foia",
            "property_records",
            "satellite_imagery",
        ):
            self.assertEqual(
                current["methodology_evidence_classification"][category], []
            )
        self.assertGreater(
            datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(FEDERATION_GENERATED_AT.replace("Z", "+00:00")),
        )
        self.assertGreater(
            datetime.fromisoformat(FEDERATION_GENERATED_AT.replace("Z", "+00:00")),
            datetime.fromisoformat(OPEN_RECORDED_AT.replace("Z", "+00:00")),
        )

    def test_live_counts_and_site_control_pipeline_boundary_are_exact(self) -> None:
        base = json.loads((BASE_RELEASE / AUDIT_FILENAME).read_text())
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text())
        totals = current["totals"]
        self.assertEqual(
            {
                key: totals[key]
                for key in (
                    "advisory_resolution_candidate_records",
                    "confirmed_duplicate_relationships",
                    "non_review_source_scoped_entity_records",
                    "review_only_source_scoped_entity_records",
                    "source_scoped_entity_records",
                    "unique_physical_sites",
                )
            },
            {
                "advisory_resolution_candidate_records": 100_409,
                "confirmed_duplicate_relationships": None,
                "non_review_source_scoped_entity_records": 9_962,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 16_092,
                "unique_physical_sites": None,
            },
        )
        fields = totals["field_totals"]
        base_fields = base["totals"]["field_totals"]
        expected_fields = {
            "capacity_observations": (1_270, 2),
            "coordinate_rows": (15_469, 4),
            "country_rows": (15_990, 4),
            "informative_lifecycle_status_rows": (521, 2),
            "non_review_rows": (9_962, 4),
            "operating_model_rows": (302, 2),
            "pipeline_rows": (423, 1),
            "source_scoped_rows": (16_092, 4),
            "under_construction_rows": (367, 1),
            "workload_observations": (122, 0),
        }
        for field, (value, delta) in expected_fields.items():
            self.assertEqual(fields[field], value, field)
            self.assertEqual(fields[field] - base_fields[field], delta, field)

        self.assertEqual(
            PIPELINE_STATUSES,
            frozenset({"announced", "expansion", "proposed", "under_construction"}),
        )
        self.assertNotIn("site_control", PIPELINE_STATUSES)
        self.assertEqual(fields["status_counts"].get("site_control"), 1)
        self.assertNotIn("site_control", fields["pipeline_status_counts"])
        self.assertEqual(fields["pipeline_with_status_evidence_rows"], 423)
        self.assertEqual(
            fields["pipeline_status_counts"],
            {
                "announced": 6,
                "expansion": 27,
                "proposed": 23,
                "under_construction": 367,
            },
        )
        self.assertEqual(current["scope"], base["scope"])
        self.assertIsNone(current["scope"]["unique_physical_sites"])

    def test_only_two_source_families_add_four_groups_and_seventeen_gaps(self) -> None:
        base = json.loads((BASE_RELEASE / AUDIT_FILENAME).read_text())
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text())
        base_groups = {group_key(group): normalize(group) for group in base["groups"]}
        current_groups = {
            group_key(group): normalize(group) for group in current["groups"]
        }
        added_group_keys = current_groups.keys() - base_groups.keys()
        self.assertEqual((len(base_groups), len(current_groups)), (675, 679))
        self.assertFalse(base_groups.keys() - current_groups.keys())
        self.assertEqual(
            added_group_keys,
            {
                (
                    NEW_RELEASE_ID,
                    scope_type,
                    source_family,
                    "__ALL__" if scope_type == "release_source" else country,
                    None if scope_type == "release_source" else iso_a2,
                    None if scope_type == "release_source" else iso_a3,
                )
                for source_family, (
                    country,
                    iso_a2,
                    iso_a3,
                ) in NEW_SOURCE_COUNTRIES.items()
                for scope_type in ("release_source", "release_source_country")
            },
        )
        self.assertEqual(
            sum(
                base_groups[key] != current_groups[key]
                for key in base_groups.keys() & current_groups.keys()
            ),
            1,
        )
        self.assertEqual(
            Counter(group["scope_type"] for group in current["groups"]),
            {"release": 3, "release_source": 210, "release_source_country": 466},
        )
        self.assertEqual(
            set(current["entity_source_families"])
            - set(base["entity_source_families"]),
            set(NEW_SOURCE_COUNTRIES),
        )
        for child_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(
                [
                    group
                    for group in current["groups"]
                    if group["child_release"] == child_id
                ],
                [
                    group
                    for group in base["groups"]
                    if group["child_release"] == child_id
                ],
            )

        base_gaps = json.loads((BASE_RELEASE / GAP_REGISTRY_FILENAME).read_text())
        current_gaps = json.loads((RELEASE / GAP_REGISTRY_FILENAME).read_text())
        base_gap_map = {gap_key(gap): normalized_gap(gap) for gap in base_gaps["gaps"]}
        current_gap_map = {
            gap_key(gap): normalized_gap(gap) for gap in current_gaps["gaps"]
        }
        added_gap_keys = current_gap_map.keys() - base_gap_map.keys()
        self.assertEqual((len(base_gap_map), len(current_gap_map)), (3_435, 3_452))
        self.assertEqual(len(added_gap_keys), 17)
        self.assertFalse(base_gap_map.keys() - current_gap_map.keys())
        self.assertFalse(
            {
                key
                for key in base_gap_map.keys() & current_gap_map.keys()
                if base_gap_map[key] != current_gap_map[key]
            }
        )
        self.assertEqual(
            Counter(key[-1] for key in added_gap_keys),
            {
                "annual_energy": 2,
                "capacity": 2,
                "informative_lifecycle_status": 2,
                "lifecycle_status": 2,
                "operating_model": 2,
                "status_as_of": 2,
                "status_evidence": 2,
                "status_stale_366_plus_days": 1,
                "workload": 2,
            },
        )
        self.assertEqual(
            current_gaps["summary"],
            {
                "by_field": {
                    "annual_energy": 458,
                    "capacity": 425,
                    "coordinates": 230,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 425,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 255,
                    "operating_model": 460,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 39,
                    "status_as_of": 255,
                    "status_evidence": 255,
                    "status_stale_366_plus_days": 179,
                    "unique_physical_sites": 1,
                    "workload": 455,
                },
                "by_severity": {
                    "high": 240,
                    "info": 39,
                    "low": 1_861,
                    "medium": 1_312,
                },
                "open_gaps": 3_452,
            },
        )
        self.assertEqual(
            {
                severity: current_gaps["summary"]["by_severity"][severity]
                - base_gaps["summary"]["by_severity"][severity]
                for severity in current_gaps["summary"]["by_severity"]
            },
            {"high": 0, "info": 0, "low": 8, "medium": 9},
        )

    def test_definition_and_output_collisions_fail_closed_without_mutation(
        self,
    ) -> None:
        with tempfile.NamedTemporaryFile(
            dir=DEFINITION.parent,
            prefix=".coverage-v24-mutation-",
            suffix=".json",
        ) as temporary:
            definition = Path(temporary.name)
            mutated = json.loads(DEFINITION.read_text())
            mutated["federated_index"]["expected_manifest_sha256"] = "0" * 64
            definition.write_bytes(canonical_json(mutated))
            with self.assertRaisesRegex(
                CoverageAuditError, "federated index manifest SHA-256 does not match"
            ):
                build_coverage_audit(definition)

        with tempfile.TemporaryDirectory(dir=RELEASE.parent) as temporary:
            temporary_path = Path(temporary)
            different = temporary_path / "different"
            shutil.copytree(BASE_RELEASE, different)
            before = tree_digest(different)
            with self.assertRaises(CoverageAuditError):
                write_coverage_audit(DEFINITION, different)
            self.assertEqual(tree_digest(different), before)
            different.chmod(0o755)

            symlink = temporary_path / "symlink"
            symlink.symlink_to(RELEASE, target_is_directory=True)
            with self.assertRaisesRegex(CoverageAuditError, "regular directory"):
                write_coverage_audit(DEFINITION, symlink)
            self.assertTrue(symlink.is_symlink())

            late = temporary_path / "late"
            sentinel = late / "sentinel.txt"
            original_validate = coverage_module.validate_coverage_audit

            def validate_then_race(*args: object, **kwargs: object) -> object:
                validated = original_validate(*args, **kwargs)
                late.mkdir()
                sentinel.write_text("late arrival\n", encoding="utf-8")
                return validated

            with patch.object(
                coverage_module,
                "validate_coverage_audit",
                side_effect=validate_then_race,
            ):
                with self.assertRaisesRegex(
                    CoverageAuditError, "appeared during publication"
                ):
                    write_coverage_audit(DEFINITION, late)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "late arrival\n")
            self.assertFalse(
                any(path.name.startswith(".late.") for path in temporary_path.iterdir())
            )

    def test_both_import_layouts_validate_the_same_frozen_bundle(self) -> None:
        for cwd, package in (
            (ROOT, "datacenter_atlas.coverage_audit"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas.coverage_audit"),
        ):
            code = (
                "from pathlib import Path; "
                f"from {package} import validate_coverage_audit; "
                f"result=validate_coverage_audit(Path({str(RELEASE)!r}), "
                f"definition_path=Path({str(DEFINITION)!r})); "
                "assert result['audit_id']=='public-open-coverage-v24'; "
                "assert result['totals']['source_scoped_entity_records']==16092; "
                "assert result['totals']['field_totals']['pipeline_rows']==423; "
                "assert result['totals']['unique_physical_sites'] is None"
            )
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
