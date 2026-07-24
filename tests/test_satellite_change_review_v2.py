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

from datacenter_atlas.satellite_change_review_v2 import (
    BUNDLE_FILES,
    CATALOG_MANIFEST,
    CATALOG_TREE,
    DEFINITION_SHA256,
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
    SatelliteChangeReviewV2Error,
    build_satellite_change_review_v2,
    make_review_definition,
    validate_satellite_change_review_v2,
    write_review_definition,
    write_satellite_change_review_v2,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v55-active-review-v1.json"
)
BUNDLE = ROOT / "satellite_change_reviews" / REVIEW_ID
SOURCE = ROOT / SOURCE_TREE["path"]
CATALOG = ROOT / CATALOG_TREE["path"]
QUEUE = ROOT / QUEUE_TREE["path"]
CATALOG_LOCK = CATALOG.parent / f"{CATALOG.name}.lock"
SCRIPT = ROOT / "scripts/build_satellite_change_review_v2.py"

EXPECTED_FILES = {
    "ATTRIBUTION.txt": (
        260,
        "317fa301fe7925a829a4633fbeb71cf1b60e7b5b1224ee9334416fd48bce5030",
    ),
    "README.md": (
        972,
        "6e39b4eaa2e581c7ef487098b5eb50ebcfc8958d0b7309450908fbe4f9169801",
    ),
    "analyst-reviews.jsonl": (
        26_481,
        "cb7161f78482696faf09b622455cc6236f32597dac4cbe3ea13b69338cbd7769",
    ),
    "manifest.json": (
        18_667,
        "19e025f4435c413ce9d9af1176bd54996ab474fab216277a7b5a5165980a170a",
    ),
    "manifest.sha256": (
        80,
        "dd4b1935f84aded7d8797d84166516ec3e7623656b842c428bdc94735be7e6ec",
    ),
    "summary.json": (
        8_533,
        "631e16ca6ca6ee5b57dd0d1fd20b0cef492093a7394d05022d48e87a64edea7a",
    ),
}
REVIEW_TREE_SHA256 = "baf1172ab85658ea80f34fdafc68868e2f8fc112ab5fc06e219015b6361c4a59"

PREDECESSOR_V1_PINS = {
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1.json": (
        7_568,
        "7c84666520844b0e308f3d0fddb8223217648efe02c08ef134c19eb31a16a161",
    ),
    ROOT
    / "satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
    / "ATTRIBUTION.txt": (
        260,
        "317fa301fe7925a829a4633fbeb71cf1b60e7b5b1224ee9334416fd48bce5030",
    ),
    ROOT
    / "satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
    / "README.md": (
        863,
        "abf02914ab9d220fc65ea176fb67cd5995597571153098a7cb0ef7f0a0825181",
    ),
    ROOT
    / "satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
    / "analyst-reviews.jsonl": (
        9_730,
        "02bbd253d3458b78e38e77ea427b2727a0a56660c9286ab65dc1f72cd585200d",
    ),
    ROOT
    / "satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
    / "manifest.json": (
        13_297,
        "e06b780e6fc2ee85e969374ec97eb167a536953c5e8e9d9b5bb3feff14ab7623",
    ),
    ROOT
    / "satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
    / "manifest.sha256": (
        80,
        "f5acc23dbea6b631fb3439454e51e97828b87519f66bff5bfe644cb4265e297e",
    ),
    ROOT
    / "satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1"
    / "summary.json": (
        2_953,
        "d650dba66decbc80b4b4b57cc00b44a360f1d1b81cd2aa6f4936f09f74af6c04",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _module():
    return importlib.import_module(build_satellite_change_review_v2.__module__)


def _pin(path: Path) -> tuple[int, str, int]:
    return (
        path.stat().st_size,
        _sha256(path),
        stat.S_IMODE(path.stat().st_mode),
    )


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


class FrozenSatelliteChangeReviewV2Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_with_exact_pins(self) -> None:
        self.assertEqual(
            DEFINITION_SHA256,
            "5dbe5e35da8af84a84e62717355c0d5b3c0cc228a2206f6dedb20b41eab83cc3",
        )
        self.assertEqual(_pin(DEFINITION), (18_540, DEFINITION_SHA256, 0o644))
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        for filename, (size, digest) in EXPECTED_FILES.items():
            path = BUNDLE / filename
            self.assertEqual(_pin(path), (size, digest, 0o444))

        module = _module()
        inventory = module._tree_inventory(BUNDLE, "review bundle")
        self.assertEqual(inventory["files"], 6)
        self.assertEqual(inventory["file_bytes"], 54_993)
        self.assertEqual(inventory["inventory_sha256"], REVIEW_TREE_SHA256)
        with _offline_guard():
            first = build_satellite_change_review_v2(DEFINITION)
            second = build_satellite_change_review_v2(DEFINITION)
            validated_first = validate_satellite_change_review_v2(
                BUNDLE, definition_path=DEFINITION
            )
            validated_second = validate_satellite_change_review_v2(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.files, second.files)
        self.assertEqual(
            first.files, {path.name: path.read_bytes() for path in BUNDLE.iterdir()}
        )
        self.assertEqual(validated_first, validated_second)
        self.assertEqual(validated_first["review_id"], REVIEW_ID)

    def test_decisions_observations_and_report_metrics_are_exact(self) -> None:
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
            ],
        )
        expected_observations = {
            QUEUE_IDS[0]: [
                "The comparison shows new or changed large-roof surfaces concentrated in the central and northern campus area, while substantial southern coverage is masked by invalid pixels.",
                "The output is retained only as a site-aligned visible-change follow-up and cannot establish identity, lifecycle, operating status, or construction progress.",
            ],
            QUEUE_IDS[1]: [
                "The change mask is diffuse across unrelated roofs, fields, roads, and river-adjacent surfaces throughout the city-scale AOI.",
                "The automated proposals are not isolated to the named data-centre site and are rejected for imagery-based site promotion.",
            ],
            QUEUE_IDS[2]: [
                "The change mask is dominated by agricultural and seasonal field changes across the AOI rather than an isolated data-centre footprint.",
                "The automated proposals are not isolated to the named data-centre site and are rejected for imagery-based site promotion.",
            ],
            QUEUE_IDS[3]: [
                "The comparison shows central industrial-site roof and earthwork change near the named location, while some proposals cover ordinary industrial surfaces.",
                "The output is retained only as a site-aligned visible-change follow-up and cannot establish identity, lifecycle, operating status, or construction progress.",
            ],
            QUEUE_IDS[4]: [
                "The comparison shows a large, spatially concentrated clearing and buildout pattern within the central site AOI.",
                "The output is retained only as a site-aligned visible-change follow-up and cannot establish identity, lifecycle, operating status, or construction progress.",
            ],
        }
        expected_metrics = {
            QUEUE_IDS[0]: (22, 394_200.0, 0.5435012086271619, 54.35),
            QUEUE_IDS[1]: (9, 248_200.0, 0.9944647031323048, 99.45),
            QUEUE_IDS[2]: (36, 1_401_600.0, 1.0, 100.0),
            QUEUE_IDS[3]: (7, 108_600.0, 1.0, 100.0),
            QUEUE_IDS[4]: (12, 1_412_500.0, 0.9335876430492152, 93.36),
        }
        for row in records:
            queue_id = row["queue_id"]
            self.assertEqual(row["observations"], expected_observations[queue_id])
            self.assertIn("original_resolution", row["review_method"])
            self.assertNotIn("confidence", row)
            components, area, fraction, percent = expected_metrics[queue_id]
            metrics = row["report_metrics"]
            self.assertEqual(metrics["proposal_component_count"], components)
            self.assertEqual(metrics["proposal_area_m2_after_component_filter"], area)
            self.assertEqual(metrics["valid_pixel_fraction"], fraction)
            self.assertEqual(metrics["valid_pixel_percent_display"], percent)
            self.assertEqual(
                metrics["interpretation"],
                "report_derived_change_mask_metadata_not_construction_area",
            )

    def test_multitile_failures_are_metadata_not_review_decisions(self) -> None:
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
        blockers = summary["technical_blockers"]
        self.assertEqual(
            [row["queue_id"] for row in blockers],
            list(TECHNICAL_BLOCKER_QUEUE_IDS),
        )
        for blocker in blockers:
            self.assertTrue(blocker["metadata_only"])
            self.assertFalse(blocker["review_decision_created"])
            self.assertEqual(blocker["artifacts_hash_bound"], 0)
            self.assertEqual(blocker["source_state"], "failed")
            self.assertEqual(blocker["blocker"], "multi_tile_mosaic_required")
            self.assertEqual(
                blocker["detail"],
                "AOI covering window crosses asset red; a future multi-tile mosaic is required",
            )
        self.assertEqual(
            summary["counts"],
            {
                "decisions": 5,
                "reject_for_site_promotion": 2,
                "retain_for_site_aligned_visible_change_follow_up": 3,
                "source_artifacts_hash_bound": 30,
                "technical_multitile_failures": 2,
            },
        )

    def test_scope_creates_no_atlas_or_sourced_fact_claim(self) -> None:
        claim_keys = {
            "atlas_claim_created",
            "atlas_mutation",
            "capacity_claim_created",
            "construction_area_claim_created",
            "construction_status_claim_created",
            "data_centre_type_claim_created",
            "energy_claim_created",
            "identity_claim_created",
            "imagery_change_is_construction_truth",
            "it_capacity_claim_created",
            "lifecycle_status_claim_created",
            "operating_status_claim_created",
            "operator_claim_created",
            "power_claim_created",
            "pue_claim_created",
            "site_count_claim_created",
            "unique_site_claim_created",
            "workload_claim_created",
        }
        self.assertTrue(all(SCOPE[key] is False for key in claim_keys))
        self.assertFalse(SCOPE["automated_promotion_allowed"])
        self.assertFalse(SCOPE["separately_sourced_facts_negated"])
        self.assertFalse(SCOPE["source_change_artifacts_copied"])
        self.assertFalse(SCOPE["technical_blockers_are_review_decisions"])
        self.assertTrue(SCOPE["decision_applies_only_to_imagery_visible_change_triage"])
        self.assertEqual(
            json.loads((BUNDLE / "summary.json").read_text())["scope"], SCOPE
        )

    def test_manifest_binds_30_artifacts_and_all_upstream_lineage(self) -> None:
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertEqual(manifest["source_change_run"]["manifest"], SOURCE_MANIFEST)
        self.assertEqual(manifest["source_change_run"]["closed_tree"], SOURCE_TREE)
        self.assertEqual(manifest["source_catalog_run"]["manifest"], CATALOG_MANIFEST)
        self.assertEqual(manifest["source_catalog_run"]["closed_tree"], CATALOG_TREE)
        self.assertEqual(manifest["source_queue_bundle"]["manifest"], QUEUE_MANIFEST)
        self.assertEqual(manifest["source_queue_bundle"]["queue"], QUEUE_FILE)
        self.assertEqual(manifest["source_queue_bundle"]["closed_tree"], QUEUE_TREE)
        source_artifacts = manifest["source_artifacts"]
        self.assertEqual(set(source_artifacts), set(QUEUE_IDS))
        self.assertEqual(sum(len(files) for files in source_artifacts.values()), 30)
        for queue_id, files in source_artifacts.items():
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
        self.assertEqual(
            set(manifest["source_lineage"]["sha256"]),
            {"catalog_batches", "processor", "queue_bundle"},
        )
        self.assertFalse(
            any(path.suffix in {".png", ".geojson"} for path in BUNDLE.iterdir())
        )
        for filename in ("manifest.json", "summary.json", "analyst-reviews.jsonl"):
            if filename.endswith(".jsonl"):
                values = [
                    json.loads(line)
                    for line in (BUNDLE / filename).read_text().splitlines()
                ]
            else:
                values = json.loads((BUNDLE / filename).read_text())
            self.assertFalse(_contains_key(values, "confidence"))

    def test_definition_generation_is_order_independent(self) -> None:
        module = _module()
        self.assertEqual(make_review_definition(), DEFINITION.read_bytes())
        self.assertEqual(
            make_review_definition(
                list(reversed(module._DECISIONS)),
                list(reversed(module._TECHNICAL_BLOCKERS)),
            ),
            DEFINITION.read_bytes(),
        )
        duplicate_decisions = [deepcopy(module._DECISIONS[0])] * 5
        with self.assertRaisesRegex(
            SatelliteChangeReviewV2Error, "exactly the five reviewed queue IDs"
        ):
            make_review_definition(duplicate_decisions)
        duplicate_blockers = [deepcopy(module._TECHNICAL_BLOCKERS[0])] * 2
        with self.assertRaisesRegex(
            SatelliteChangeReviewV2Error, "exactly the two technical queue IDs"
        ):
            make_review_definition(technical_blockers=duplicate_blockers)

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
            "confidence": lambda value: value["decisions"][0].__setitem__(
                "confidence", 0.9
            ),
            "metric": lambda value: value["decisions"][1]["report_metrics"].__setitem__(
                "proposal_component_count", 10
            ),
            "observation": lambda value: value["decisions"][0].__setitem__(
                "observations", []
            ),
            "blocker decision": lambda value: value["technical_blockers"][
                0
            ].__setitem__("review_decision_created", True),
            "source hash": lambda value: value["decisions"][0]["input_artifacts"][
                "comparison.png"
            ].__setitem__("sha256", "0" * 64),
        }
        original_reader = module._read_regular
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                changed = deepcopy(original)
                mutate(changed)
                changed_raw = _canonical_json(changed)

                def reader(path: Path, read_label: str) -> bytes:
                    if Path(path).resolve() == DEFINITION.resolve():
                        return changed_raw
                    return original_reader(path, read_label)

                with (
                    patch.object(
                        module,
                        "DEFINITION_SHA256",
                        hashlib.sha256(changed_raw).hexdigest(),
                    ),
                    patch.object(module, "_read_regular", side_effect=reader),
                ):
                    with self.assertRaisesRegex(
                        SatelliteChangeReviewV2Error,
                        "definition semantics changed|confidence is forbidden",
                    ):
                        build_satellite_change_review_v2(DEFINITION)

    def test_source_and_upstream_fault_paths_fail_closed(self) -> None:
        module = _module()
        original_inventory = module._tree_inventory

        def changed_source_tree(path: Path, label: str):
            inventory = original_inventory(path, label)
            if Path(path).resolve() == SOURCE.resolve():
                inventory["files"] += 1
            return inventory

        with patch.object(module, "_tree_inventory", side_effect=changed_source_tree):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV2Error, "source change run closed tree changed"
            ):
                build_satellite_change_review_v2(DEFINITION)

        def changed_catalog_tree(path: Path, label: str):
            inventory = original_inventory(path, label)
            if Path(path).resolve() == CATALOG.resolve():
                inventory["file_bytes"] += 1
            return inventory

        with patch.object(module, "_tree_inventory", side_effect=changed_catalog_tree):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV2Error, "source catalog run closed tree changed"
            ):
                build_satellite_change_review_v2(DEFINITION)

        original_reader = module._read_regular

        def changed_manifest(path: Path, label: str) -> bytes:
            raw = original_reader(path, label)
            if Path(path).resolve() == (ROOT / SOURCE_MANIFEST["path"]).resolve():
                return raw + b"\n"
            return raw

        with patch.object(module, "_read_regular", side_effect=changed_manifest):
            with self.assertRaisesRegex(
                SatelliteChangeReviewV2Error, "source change manifest changed"
            ):
                build_satellite_change_review_v2(DEFINITION)

    def test_writers_are_collision_safe_lock_aware_and_freeze_only(self) -> None:
        module = _module()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_root = Path(temporary)
            output = temporary_root / "review"
            try:
                write_satellite_change_review_v2(DEFINITION, output)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
                self.assertTrue(
                    all(
                        stat.S_IMODE(path.stat().st_mode) == 0o444
                        for path in output.iterdir()
                    )
                )
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV2Error, "existing output"
                ):
                    write_satellite_change_review_v2(DEFINITION, output)
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV2Error, "requires freeze=True"
                ):
                    write_satellite_change_review_v2(
                        DEFINITION, temporary_root / "unfrozen", freeze=False
                    )
                locked = temporary_root / "locked"
                lock_path = locked.parent / f".{locked.name}.lock"
                lock_path.write_text("active\n")
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV2Error, "active output lock"
                ):
                    write_satellite_change_review_v2(DEFINITION, locked)
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
                        write_satellite_change_review_v2(DEFINITION, failed)
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
            temporary_root = Path(temporary)
            relative = Path(temporary_root.name) / "definition.json"
            destination = ROOT / relative
            with patch.object(module, "DEFINITION_PATH", relative.as_posix()):
                self.assertEqual(
                    write_review_definition(ROOT, destination),
                    hashlib.sha256(make_review_definition()).hexdigest(),
                )
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV2Error, "existing output"
                ):
                    write_review_definition(ROOT, destination)

    def test_sources_catalog_lock_and_predecessor_v1_are_unchanged(self) -> None:
        module = _module()
        source_before = module._tree_inventory(SOURCE, "source change run")
        catalog_before = module._tree_inventory(CATALOG, "source catalog run")
        queue_before = module._tree_inventory(QUEUE, "source queue bundle")
        predecessor_before = {path: _pin(path) for path in PREDECESSOR_V1_PINS}
        lock_before = _pin(CATALOG_LOCK)
        with _offline_guard():
            build_satellite_change_review_v2(DEFINITION)
            validate_satellite_change_review_v2(BUNDLE, definition_path=DEFINITION)
        self.assertEqual(
            module._tree_inventory(SOURCE, "source change run"), source_before
        )
        self.assertEqual(
            module._tree_inventory(CATALOG, "source catalog run"), catalog_before
        )
        self.assertEqual(
            module._tree_inventory(QUEUE, "source queue bundle"), queue_before
        )
        self.assertEqual(
            source_before, {k: v for k, v in SOURCE_TREE.items() if k != "path"}
        )
        self.assertEqual(
            catalog_before, {k: v for k, v in CATALOG_TREE.items() if k != "path"}
        )
        self.assertEqual(
            queue_before, {k: v for k, v in QUEUE_TREE.items() if k != "path"}
        )
        self.assertEqual(
            {path: _pin(path) for path in PREDECESSOR_V1_PINS}, predecessor_before
        )
        for path, (size, digest) in PREDECESSOR_V1_PINS.items():
            self.assertEqual(_pin(path)[:2], (size, digest))
        self.assertEqual(_pin(CATALOG_LOCK), lock_before)
        self.assertEqual(lock_before, (0, hashlib.sha256(b"").hexdigest(), 0o600))

    def test_both_workspace_import_layouts_and_cli_validate(self) -> None:
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.satellite_change_review_v2 import "
            "validate_satellite_change_review_v2; "
            f"m=validate_satellite_change_review_v2(Path({str(BUNDLE)!r}), "
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
        self.assertEqual(payload["decisions"], 5)
        self.assertEqual(payload["technical_multitile_failures"], 2)


if __name__ == "__main__":
    unittest.main()
