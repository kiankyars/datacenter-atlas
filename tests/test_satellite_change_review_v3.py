from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
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

from datacenter_atlas.satellite_change_review_v3 import (
    BUNDLE_FILES,
    CATALOG_MANIFEST,
    CATALOG_TREE,
    DEFINITION_SHA256,
    INCIDENT_MANIFEST,
    INCIDENT_TREE,
    PENTAPOINT_QUEUE_ID,
    QUEUE_FILE,
    QUEUE_IDS,
    QUEUE_MANIFEST,
    QUEUE_TREE,
    REJECT_DECISION,
    RETAIN_DECISION,
    REVIEW_ID,
    SCOPE,
    SOURCE_MANIFEST,
    SOURCE_TREE,
    TECHNICAL_BLOCKER_QUEUE_IDS,
    SatelliteChangeReviewV3Error,
    build_satellite_change_review_v3,
    make_review_definition,
    validate_satellite_change_review_v3,
    write_review_definition,
    write_satellite_change_review_v3,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v56-active-review-v1.json"
)
BUNDLE = ROOT / "satellite_change_reviews" / REVIEW_ID
SCRIPT = ROOT / "scripts/build_satellite_change_review_v3.py"
PREDECESSOR_DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v55-active-review-v1.json"
)
PREDECESSOR_BUNDLE = (
    ROOT / "satellite_change_reviews" / "2026-07-20-open-seed-v55-active-review-v1"
)

EXPECTED_FILES = {
    "ATTRIBUTION.txt": (
        260,
        "317fa301fe7925a829a4633fbeb71cf1b60e7b5b1224ee9334416fd48bce5030",
    ),
    "README.md": (
        1_321,
        "bcf0cdfea80b6291625b3e6547dc9a7bc34c46a6f0657a9985bb903feb302dec",
    ),
    "analyst-reviews.jsonl": (
        34_142,
        "2854ab46c3aee84c4f243b21549c1c70197f72b68eeff55a9a3b5072e2c2a860",
    ),
    "manifest.json": (
        17_652,
        "269fe8133138d82680b0fa9498f24ee3a886a3e32c58ab4013276d719868dba9",
    ),
    "manifest.sha256": (
        80,
        "7c84126fcbb2fe42c1e8d2c6ad0314b3df51692c4775a08bd6cfbd2963edd988",
    ),
    "summary.json": (
        13_379,
        "e0414cdac8c0a3ad9d8e7d44462df6a3da6517448ad5d231a351555758cc1097",
    ),
}
REVIEW_TREE_SHA256 = "b38079438e238da999a6afa52bb835ac70b57c0c8706082281e58a68d87e5fe4"
EXPECTED_DEFINITION_SHA256 = (
    "c35728fab6b3fa909586d89cb605d978653d9353196a5e7cc56796985e0e4e6c"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _module():
    return importlib.import_module(build_satellite_change_review_v3.__module__)


def _pin(path: Path) -> tuple[int, str, int]:
    return path.stat().st_size, _sha256(path), stat.S_IMODE(path.stat().st_mode)


def _thaw(root: Path) -> None:
    if not root.exists() or root.is_symlink():
        return
    root.chmod(0o755)
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o755)
        elif path.is_file() and not path.is_symlink():
            path.chmod(0o644)


def _contains_key(value: object, forbidden: str) -> bool:
    if isinstance(value, dict):
        return forbidden in value or any(
            _contains_key(child, forbidden) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, forbidden) for child in value)
    return False


@contextmanager
def _offline_guard():
    error = AssertionError("satellite review attempted network access")
    with (
        patch.object(socket, "socket", side_effect=error),
        patch.object(socket, "create_connection", side_effect=error),
        patch.object(socket, "getaddrinfo", side_effect=error),
        patch.object(socket, "gethostbyname", side_effect=error),
    ):
        yield


class FrozenSatelliteChangeReviewV3Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_with_exact_pins(self) -> None:
        self.assertEqual(DEFINITION_SHA256, EXPECTED_DEFINITION_SHA256)
        self.assertEqual(_pin(DEFINITION), (23_421, DEFINITION_SHA256, 0o644))
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        for filename, (size, digest) in EXPECTED_FILES.items():
            self.assertEqual(_pin(BUNDLE / filename), (size, digest, 0o444))

        module = _module()
        inventory = module._tree_inventory(BUNDLE, "review bundle")
        self.assertEqual(inventory["files"], 6)
        self.assertEqual(inventory["file_bytes"], 66_834)
        self.assertEqual(inventory["inventory_sha256"], REVIEW_TREE_SHA256)
        with _offline_guard():
            first = build_satellite_change_review_v3(DEFINITION)
            second = build_satellite_change_review_v3(DEFINITION)
            validated_first = validate_satellite_change_review_v3(
                BUNDLE, definition_path=DEFINITION
            )
            validated_second = validate_satellite_change_review_v3(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.files, second.files)
        self.assertEqual(
            first.files, {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        )
        self.assertEqual(validated_first, validated_second)
        self.assertEqual(validated_first["review_id"], REVIEW_ID)

    def test_five_decisions_are_exactly_carried_and_penta_is_exact(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        predecessor = json.loads(PREDECESSOR_DEFINITION.read_text())
        records = [
            json.loads(line)
            for line in (BUNDLE / "analyst-reviews.jsonl").read_text().splitlines()
        ]
        self.assertEqual([row["queue_id"] for row in records], list(QUEUE_IDS))
        self.assertEqual(
            [row["decision"] for row in records],
            [
                RETAIN_DECISION,
                REJECT_DECISION,
                REJECT_DECISION,
                RETAIN_DECISION,
                RETAIN_DECISION,
                REJECT_DECISION,
            ],
        )
        predecessor_by_id = {row["queue_id"]: row for row in predecessor["decisions"]}
        for row in definition["decisions"][:5]:
            old = predecessor_by_id[row["queue_id"]]
            for key in (
                "decision",
                "entity",
                "observations",
                "queue_id",
                "report_metrics",
                "review_method",
                "reviewed_at",
            ):
                self.assertEqual(row[key], old[key])
            self.assertEqual(
                {
                    name: (spec["bytes"], spec["sha256"])
                    for name, spec in row["input_artifacts"].items()
                },
                {
                    name: (spec["bytes"], spec["sha256"])
                    for name, spec in old["input_artifacts"].items()
                },
            )
            for name, spec in row["input_artifacts"].items():
                self.assertEqual(
                    spec["path"],
                    "satellite_change_runs/"
                    "2026-07-20-open-seed-v56-active-runtime-retry-001/"
                    f"jobs/{row['queue_id']}/change/{name}",
                )

        penta = definition["decisions"][-1]
        self.assertEqual(penta["queue_id"], PENTAPOINT_QUEUE_ID)
        self.assertEqual(penta["decision"], REJECT_DECISION)
        self.assertEqual(
            penta["entity"],
            {
                "id": "a75eaf2b-790f-5266-be60-3f2bafee2eeb",
                "name": "PentaPoint EMD BKK-01 Development",
            },
        )
        self.assertEqual(
            penta["observations"],
            [
                "The original-resolution comparison and overlay cover a broad central-Bangkok AOI with diffuse spectral change across unrelated urban roofs and roads, plus invalid or cloud-masked pixels.",
                "BKK-01 is an interior-floor fit-out in an existing tower, so 10 m optical change cannot be attributed to it; this rejection applies only to imagery promotion and does not negate the official under-construction record.",
            ],
        )
        self.assertEqual(
            penta["report_metrics"],
            {
                "interpretation": (
                    "report_derived_change_mask_metadata_not_construction_area"
                ),
                "label": "large_spectral_change_candidate",
                "proposal_area_m2_after_component_filter": 115_400.0,
                "proposal_component_count": 14,
                "valid_pixel_fraction": 0.9212862188152785,
                "valid_pixel_percent_display": 92.13,
            },
        )
        self.assertEqual(records[-1]["observations"], penta["observations"])
        self.assertEqual(records[-1]["report_metrics"], penta["report_metrics"])
        self.assertEqual(
            [row["review_origin"]["kind"] for row in records],
            ["carried_forward_byte_identical_change_artifacts"] * 5
            + ["new_original_resolution_visual_review"],
        )

    def test_one_blocker_and_no_raster_incident_are_metadata_only(self) -> None:
        records = [
            json.loads(line)
            for line in (BUNDLE / "analyst-reviews.jsonl").read_text().splitlines()
        ]
        self.assertTrue(
            set(TECHNICAL_BLOCKER_QUEUE_IDS).isdisjoint(
                {record["queue_id"] for record in records}
            )
        )
        summary = json.loads((BUNDLE / "summary.json").read_text())
        self.assertEqual(
            summary["counts"],
            {
                "decisions": 6,
                "excluded_no_raster_incident_runs": 1,
                "reject_for_site_promotion": 3,
                "retain_for_site_aligned_visible_change_follow_up": 3,
                "source_artifacts_hash_bound": 36,
                "technical_multitile_failures": 1,
            },
        )
        self.assertEqual(len(summary["technical_blockers"]), 1)
        blocker = summary["technical_blockers"][0]
        self.assertEqual(blocker["queue_id"], TECHNICAL_BLOCKER_QUEUE_IDS[0])
        self.assertEqual(blocker["blocker"], "multi_tile_mosaic_required")
        self.assertTrue(blocker["metadata_only"])
        self.assertFalse(blocker["review_decision_created"])
        self.assertEqual(blocker["artifacts_hash_bound"], 0)
        self.assertEqual(
            blocker["source_failure_sha256"],
            "827f462a45286c9c5c41c6a471892135ed48bb94a202828a679461c19055ea8e",
        )
        incident = summary["excluded_incident_run"]
        self.assertEqual(incident["manifest"], INCIDENT_MANIFEST)
        self.assertEqual(incident["closed_tree"], INCIDENT_TREE)
        self.assertEqual(incident["disposition"], "excluded_technical_lineage_only")
        self.assertFalse(incident["imagery_evidence_used"])
        self.assertFalse(incident["review_decision_created"])
        self.assertEqual(incident["raster_artifacts_hash_bound"], 0)
        incident_root = ROOT / INCIDENT_TREE["path"]
        self.assertFalse(
            any(
                path.suffix.lower() in {".png", ".tif", ".tiff"}
                for path in incident_root.rglob("*")
            )
        )

    def test_scope_and_manifest_create_no_atlas_or_sourced_fact_claim(self) -> None:
        false_claim_keys = {
            "atlas_claim_created",
            "atlas_mutation",
            "automated_promotion_allowed",
            "capacity_claim_created",
            "construction_area_claim_created",
            "construction_status_claim_created",
            "data_centre_type_claim_created",
            "energy_claim_created",
            "excluded_incident_run_used_as_imagery_evidence",
            "identity_claim_created",
            "imagery_change_is_construction_truth",
            "it_capacity_claim_created",
            "lifecycle_status_claim_created",
            "operating_status_claim_created",
            "operator_claim_created",
            "power_claim_created",
            "pue_claim_created",
            "separately_sourced_facts_negated",
            "site_count_claim_created",
            "source_change_artifacts_copied",
            "technical_blockers_are_review_decisions",
            "unique_site_claim_created",
            "workload_claim_created",
        }
        self.assertTrue(all(SCOPE[key] is False for key in false_claim_keys))
        self.assertTrue(SCOPE["decision_applies_only_to_imagery_visible_change_triage"])
        self.assertTrue(SCOPE["manual_review_completed"])
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertEqual(manifest["scope"], SCOPE)
        self.assertEqual(manifest["source_change_run"]["manifest"], SOURCE_MANIFEST)
        self.assertEqual(manifest["source_change_run"]["closed_tree"], SOURCE_TREE)
        self.assertEqual(manifest["source_catalog_run"]["manifest"], CATALOG_MANIFEST)
        self.assertEqual(manifest["source_catalog_run"]["closed_tree"], CATALOG_TREE)
        self.assertEqual(manifest["source_queue_bundle"]["manifest"], QUEUE_MANIFEST)
        self.assertEqual(manifest["source_queue_bundle"]["queue"], QUEUE_FILE)
        self.assertEqual(manifest["source_queue_bundle"]["closed_tree"], QUEUE_TREE)
        artifacts = manifest["source_artifacts"]
        self.assertEqual(set(artifacts), set(QUEUE_IDS))
        self.assertEqual(sum(len(files) for files in artifacts.values()), 36)
        for queue_id, files in artifacts.items():
            self.assertEqual(
                set(files),
                {
                    "after.png",
                    "before.png",
                    "change-overlay.png",
                    "change-proposals.geojson",
                    "comparison.png",
                    "report.json",
                },
            )
            for name, spec in files.items():
                path = ROOT / spec["path"]
                self.assertIn(f"jobs/{queue_id}/change/{name}", spec["path"])
                self.assertEqual(_pin(path)[:2], (spec["bytes"], spec["sha256"]))
        self.assertFalse(
            any(
                path.suffix.lower() in {".png", ".geojson"} for path in BUNDLE.iterdir()
            )
        )
        for filename in ("manifest.json", "summary.json", "analyst-reviews.jsonl"):
            if filename.endswith(".jsonl"):
                value = [
                    json.loads(line)
                    for line in (BUNDLE / filename).read_text().splitlines()
                ]
            else:
                value = json.loads((BUNDLE / filename).read_text())
            self.assertFalse(_contains_key(value, "confidence"))
            self.assertFalse(_contains_key(value, "ledger"))

    def test_all_input_trees_and_pinned_manifests_are_unchanged(self) -> None:
        module = _module()
        for spec, label in (
            (QUEUE_TREE, "source queue bundle"),
            (CATALOG_TREE, "source catalog run"),
            (SOURCE_TREE, "source runtime retry run"),
            (INCIDENT_TREE, "excluded no-raster incident run"),
            (module.PREDECESSOR_TREE, "predecessor review bundle"),
        ):
            self.assertEqual(
                module._tree_inventory(ROOT / spec["path"], label),
                {key: value for key, value in spec.items() if key != "path"},
            )
        for spec in (
            QUEUE_MANIFEST,
            QUEUE_FILE,
            CATALOG_MANIFEST,
            SOURCE_MANIFEST,
            INCIDENT_MANIFEST,
            module.PREDECESSOR_DEFINITION,
            module.PREDECESSOR_MANIFEST,
        ):
            self.assertEqual(
                _pin(ROOT / spec["path"])[:2], (spec["bytes"], spec["sha256"])
            )
        self.assertEqual(
            module._tree_inventory(PREDECESSOR_BUNDLE, "predecessor review bundle")[
                "inventory_sha256"
            ],
            "baf1172ab85658ea80f34fdafc68868e2f8fc112ab5fc06e219015b6361c4a59",
        )

    def test_semantic_mutations_fail_closed(self) -> None:
        module = _module()
        original = json.loads(DEFINITION.read_text())
        mutations = {
            "decision": lambda value: value["decisions"][0].__setitem__(
                "decision", REJECT_DECISION
            ),
            "claim": lambda value: value["scope"].__setitem__(
                "identity_claim_created", True
            ),
            "metric": lambda value: value["decisions"][-1][
                "report_metrics"
            ].__setitem__("proposal_component_count", 15),
            "observation": lambda value: value["decisions"][-1].__setitem__(
                "observations", []
            ),
            "blocker": lambda value: value["technical_blockers"][0].__setitem__(
                "review_decision_created", True
            ),
            "incident": lambda value: value["excluded_incident_run"].__setitem__(
                "imagery_evidence_used", True
            ),
            "artifact": lambda value: value["decisions"][0]["input_artifacts"][
                "comparison.png"
            ].__setitem__("sha256", "0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = deepcopy(original)
                mutate(changed)
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV3Error, "definition semantics changed"
                ):
                    module._validate_definition_semantics(changed, original)
        changed = deepcopy(original)
        changed["decisions"][0]["confidence"] = 0.9
        with self.assertRaisesRegex(SatelliteChangeReviewV3Error, "confidence"):
            module._validate_definition_semantics(changed, changed)

    def test_source_tree_manifest_and_artifact_faults_fail_closed(self) -> None:
        module = _module()
        original_inventory = module._tree_inventory

        def changed_source_tree(path: Path, label: str):
            inventory = original_inventory(path, label)
            if Path(path).resolve() == (ROOT / SOURCE_TREE["path"]).resolve():
                inventory["files"] += 1
            return inventory

        with patch.object(module, "_tree_inventory", side_effect=changed_source_tree):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV3Error,
                "source runtime retry run closed tree changed",
            ):
                build_satellite_change_review_v3(DEFINITION)

        original_reader = module._read_regular

        def changed_manifest(path: Path, label: str) -> bytes:
            raw = original_reader(path, label)
            if Path(path).resolve() == (ROOT / INCIDENT_MANIFEST["path"]).resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_manifest):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV3Error,
                "excluded incident manifest checkpoint changed",
            ):
                build_satellite_change_review_v3(DEFINITION)

        artifact = json.loads(DEFINITION.read_text())["decisions"][-1][
            "input_artifacts"
        ]["comparison.png"]

        def changed_artifact(path: Path, label: str) -> bytes:
            raw = original_reader(path, label)
            if Path(path).resolve() == (ROOT / artifact["path"]).resolve():
                return raw + b"x"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_artifact):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV3Error,
                f"source artifact changed: {PENTAPOINT_QUEUE_ID}",
            ):
                build_satellite_change_review_v3(DEFINITION)

    def test_writers_are_collision_safe_lock_aware_and_freeze_only(self) -> None:
        module = _module()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_root = Path(temporary)
            output = temporary_root / "review"
            try:
                write_satellite_change_review_v3(DEFINITION, output)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
                self.assertTrue(
                    all(
                        stat.S_IMODE(path.stat().st_mode) == 0o444
                        for path in output.iterdir()
                    )
                )
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV3Error, "existing output"
                ):
                    write_satellite_change_review_v3(DEFINITION, output)
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV3Error, "requires freeze=True"
                ):
                    write_satellite_change_review_v3(
                        DEFINITION, temporary_root / "unfrozen", freeze=False
                    )
                locked = temporary_root / "locked"
                lock_path = locked.parent / f".{locked.name}.lock"
                lock_path.write_text("active\n")
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV3Error, "active output lock"
                ):
                    write_satellite_change_review_v3(DEFINITION, locked)
                lock_path.unlink()

                failed = temporary_root / "write-fault"
                original_write = module._write_file
                calls = 0

                def fail_second_write(path: Path, raw: bytes) -> None:
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise OSError("injected write fault")
                    original_write(path, raw)

                with patch.object(module, "_write_file", side_effect=fail_second_write):
                    with self.assertRaisesRegex(OSError, "injected write fault"):
                        write_satellite_change_review_v3(DEFINITION, failed)
                self.assertFalse(failed.exists())
                self.assertFalse((failed.parent / f".{failed.name}.lock").exists())
                self.assertFalse(
                    any(
                        path.name.startswith(f".{failed.name}.")
                        for path in failed.parent.iterdir()
                    )
                )
            finally:
                _thaw(output)

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            relative = Path(Path(temporary).name) / "definition.json"
            destination = ROOT / relative
            with patch.object(module, "DEFINITION_PATH", relative.as_posix()):
                self.assertEqual(
                    write_review_definition(ROOT, destination),
                    hashlib.sha256(make_review_definition(ROOT)).hexdigest(),
                )
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV3Error, "existing output"
                ):
                    write_review_definition(ROOT, destination)

    def test_both_workspace_import_layouts_and_cli_validate(self) -> None:
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.satellite_change_review_v3 import "
            "validate_satellite_change_review_v3; "
            f"m=validate_satellite_change_review_v3(Path({str(BUNDLE)!r}), "
            f"definition_path=Path({str(DEFINITION)!r})); "
            f"assert m['review_id'] == {REVIEW_ID!r}"
        )
        for cwd in (ROOT, WORKSPACE):
            with self.subTest(cwd=cwd):
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--validate-only"],
            cwd=WORKSPACE,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["validated"])
        self.assertEqual(payload["decisions"], 6)
        self.assertEqual(payload["technical_multitile_failures"], 1)


if __name__ == "__main__":
    unittest.main()
