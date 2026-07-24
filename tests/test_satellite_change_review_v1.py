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

from datacenter_atlas.satellite_change_review_v1 import (
    BUNDLE_FILES,
    DEFINITION_SHA256,
    QUEUE_IDS,
    REVIEW_ID,
    SCOPE,
    SOURCE_MANIFEST,
    SOURCE_TREE,
    SatelliteChangeReviewV1Error,
    build_satellite_change_review_v1,
    make_review_definition,
    validate_satellite_change_review_v1,
    write_review_definition,
    write_satellite_change_review_v1,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
DEFINITION = (
    ROOT
    / "definitions/satellite_change_reviews"
    / "2026-07-20-open-seed-v43-active-reselected-v2-review-v1.json"
)
BUNDLE = ROOT / "satellite_change_reviews" / REVIEW_ID
SOURCE = ROOT / SOURCE_TREE["path"]
SCRIPT = ROOT / "scripts/build_satellite_change_review_v1.py"

EXPECTED_FILES = {
    "ATTRIBUTION.txt": (
        260,
        "317fa301fe7925a829a4633fbeb71cf1b60e7b5b1224ee9334416fd48bce5030",
    ),
    "README.md": (
        863,
        "abf02914ab9d220fc65ea176fb67cd5995597571153098a7cb0ef7f0a0825181",
    ),
    "analyst-reviews.jsonl": (
        9_730,
        "02bbd253d3458b78e38e77ea427b2727a0a56660c9286ab65dc1f72cd585200d",
    ),
    "manifest.json": (
        13_297,
        "e06b780e6fc2ee85e969374ec97eb167a536953c5e8e9d9b5bb3feff14ab7623",
    ),
    "manifest.sha256": (
        80,
        "f5acc23dbea6b631fb3439454e51e97828b87519f66bff5bfe644cb4265e297e",
    ),
    "summary.json": (
        2_953,
        "d650dba66decbc80b4b4b57cc00b44a360f1d1b81cd2aa6f4936f09f74af6c04",
    ),
}
REVIEW_TREE_SHA256 = (
    "58c6d32e77f9956eeca39cee51261474cd0c812a802aafe570f35d9e33674843"
)
V14_PINS = {
    ROOT / "sources/current-coverage-2026-07-20-v14.json": (
        129_254,
        "907942b43861845703900dfb57e518ed56611bb932b2ec0f16f1ab656b0beab0",
    ),
    ROOT / "current_coverage_ledgers/2026-07-20-v14/current-coverage-ledger.json": (
        89_210,
        "ede89a5b75ca30dae4c96f3ae876e02abf53eff00497a8edc85fc9fcde69b2bd",
    ),
    ROOT / "current_coverage_ledgers/2026-07-20-v14/manifest.json": (
        24_814,
        "5f318e610653a4579fb9d995133fd3ea388de5c7a2a3b66c2e250fced69d150c",
    ),
    ROOT / "current_coverage_ledgers/2026-07-20-v14/manifest.sha256": (
        80,
        "a9ad99f6a82b749ec69ef9f38a1b2f1c010848b0e7db33b878c232b64d4ce536",
    ),
}
PRIOR_REVIEW = (
    ROOT
    / "satellite_review_runs/2026-07-18-global-open-v3-active-001/jobs"
    / "satq-0384b818546e954492a85864/change/analyst-review.json"
)
PRIOR_REVIEW_PIN = (
    862,
    "c22b63ed7fcd6eda1195a7b5b72222a10d68f48636a5c2497172836639e1db52",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _module():
    return importlib.import_module(build_satellite_change_review_v1.__module__)


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


@contextmanager
def _offline_guard():
    error = AssertionError("satellite review attempted network access")
    with patch.object(socket, "socket", side_effect=error), patch.object(
        socket, "create_connection", side_effect=error
    ), patch.object(socket, "getaddrinfo", side_effect=error), patch.object(
        socket, "gethostbyname", side_effect=error
    ):
        yield


class FrozenSatelliteChangeReviewV1Tests(unittest.TestCase):
    def test_frozen_bundle_reproduces_twice_offline_with_exact_pins(self) -> None:
        self.assertEqual(
            DEFINITION_SHA256,
            "7c84666520844b0e308f3d0fddb8223217648efe02c08ef134c19eb31a16a161",
        )
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(DEFINITION.stat().st_size, 7_568)
        self.assertEqual({path.name for path in BUNDLE.iterdir()}, BUNDLE_FILES)
        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        for filename, (size, digest) in EXPECTED_FILES.items():
            path = BUNDLE / filename
            self.assertEqual(path.stat().st_size, size)
            self.assertEqual(_sha256(path), digest)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        module = _module()
        inventory = module._tree_inventory(BUNDLE, "review bundle")
        self.assertEqual(inventory["files"], 6)
        self.assertEqual(inventory["file_bytes"], 27_183)
        self.assertEqual(inventory["inventory_sha256"], REVIEW_TREE_SHA256)
        with _offline_guard():
            first = build_satellite_change_review_v1(DEFINITION)
            second = build_satellite_change_review_v1(DEFINITION)
            validated_first = validate_satellite_change_review_v1(
                BUNDLE, definition_path=DEFINITION
            )
            validated_second = validate_satellite_change_review_v1(
                BUNDLE, definition_path=DEFINITION
            )
        self.assertEqual(first.files, second.files)
        self.assertEqual(first.files, {path.name: path.read_bytes() for path in BUNDLE.iterdir()})
        self.assertEqual(validated_first, validated_second)
        self.assertEqual(validated_first["review_id"], REVIEW_ID)

    def test_decisions_and_report_derived_metrics_are_exact(self) -> None:
        records = [
            json.loads(line)
            for line in (BUNDLE / "analyst-reviews.jsonl").read_text().splitlines()
        ]
        self.assertEqual([row["queue_id"] for row in records], list(QUEUE_IDS))
        by_id = {row["queue_id"]: row for row in records}
        docklands = by_id[QUEUE_IDS[0]]
        nextdc = by_id[QUEUE_IDS[1]]
        self.assertEqual(
            {row["decision"] for row in records}, {"reject_for_site_promotion"}
        )
        self.assertEqual(
            docklands["observations"],
            [
                "The city-scale AOI contains widespread airport, water, rooftop, and surface changes.",
                "The automated proposals are not isolated to the data-centre site and cannot support imagery-based site promotion.",
            ],
        )
        self.assertIn(
            "separate pre-existing parcel-cropped evidence bundle remains outside this review",
            docklands["excluded_context"][0],
        )
        self.assertEqual(
            nextdc["observations"],
            [
                "The mask is dominated by tidal or coastal morphology, cloud or atmospheric effects, and unrelated urban or rooftop changes.",
                "The automated proposals are not isolated to the data-centre site and cannot support imagery-based site promotion.",
            ],
        )
        expected_metrics = {
            QUEUE_IDS[0]: (11, 156_800.0, 0.9752989585473198, 97.53),
            QUEUE_IDS[1]: (29, 518_200.0, 0.9159353753197771, 91.59),
        }
        for queue_id, (components, area, fraction, percent) in expected_metrics.items():
            metrics = by_id[queue_id]["report_metrics"]
            self.assertEqual(metrics["proposal_component_count"], components)
            self.assertEqual(metrics["proposal_area_m2_after_component_filter"], area)
            self.assertEqual(metrics["valid_pixel_fraction"], fraction)
            self.assertEqual(metrics["valid_pixel_percent_display"], percent)
            self.assertEqual(
                metrics["interpretation"],
                "report_derived_change_mask_metadata_not_construction_area",
            )

    def test_scope_rejects_imagery_promotion_without_negating_other_facts(self) -> None:
        claim_keys = {
            "atlas_claim_created",
            "atlas_mutation",
            "construction_area_claim_created",
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
            "unique_site_claim_created",
            "workload_claim_created",
        }
        self.assertTrue(all(SCOPE[key] is False for key in claim_keys))
        self.assertFalse(SCOPE["automated_promotion_allowed"])
        self.assertFalse(SCOPE["separately_sourced_construction_facts_negated"])
        self.assertFalse(SCOPE["source_change_artifacts_copied"])
        self.assertTrue(SCOPE["decision_applies_only_to_imagery_site_promotion"])
        summary = json.loads((BUNDLE / "summary.json").read_text())
        self.assertEqual(summary["scope"], SCOPE)
        self.assertEqual(summary["counts"]["reject_for_site_promotion"], 2)
        self.assertEqual(summary["counts"]["source_artifacts_hash_bound"], 12)

    def test_manifest_binds_every_artifact_and_processor_source_lineage(self) -> None:
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertEqual(manifest["source_change_run"]["manifest"], SOURCE_MANIFEST)
        self.assertEqual(manifest["source_change_run"]["closed_tree"], SOURCE_TREE)
        source_artifacts = manifest["source_artifacts"]
        self.assertEqual(set(source_artifacts), set(QUEUE_IDS))
        self.assertEqual(sum(len(files) for files in source_artifacts.values()), 12)
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
        lineage_hashes = manifest["source_lineage"]["sha256"]
        self.assertEqual(
            lineage_hashes["processor"],
            "beb014db43ac6822b7ee356d1096ad6f2dd097f59221ec37c8e239660c8084d6",
        )
        self.assertEqual(len(lineage_hashes), 4)
        self.assertFalse(
            any(path.suffix in {".png", ".geojson"} for path in BUNDLE.iterdir())
        )

    def test_definition_generation_is_order_independent(self) -> None:
        module = _module()
        self.assertEqual(make_review_definition(), DEFINITION.read_bytes())
        self.assertEqual(
            make_review_definition(list(reversed(module._DECISIONS))),
            DEFINITION.read_bytes(),
        )
        duplicate = [deepcopy(module._DECISIONS[0]), deepcopy(module._DECISIONS[0])]
        with self.assertRaisesRegex(
            SatelliteChangeReviewV1Error, "exactly the two reviewed queue IDs"
        ):
            make_review_definition(duplicate)

    def test_semantic_mutations_fail_closed(self) -> None:
        module = _module()
        original = json.loads(DEFINITION.read_text())
        mutations = {
            "decision": lambda value: value["decisions"][0].__setitem__(
                "decision", "accept_for_site_promotion"
            ),
            "claim": lambda value: value["scope"].__setitem__(
                "identity_claim_created", True
            ),
            "metric": lambda value: value["decisions"][1][
                "report_metrics"
            ].__setitem__("proposal_component_count", 30),
            "observation": lambda value: value["decisions"][0].__setitem__(
                "observations", []
            ),
            "excluded context": lambda value: value["decisions"][0].__setitem__(
                "excluded_context", []
            ),
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

                with patch.object(
                    module, "DEFINITION_SHA256", hashlib.sha256(changed_raw).hexdigest()
                ), patch.object(module, "_read_regular", side_effect=reader):
                    with self.assertRaisesRegex(
                        SatelliteChangeReviewV1Error,
                        "definition semantics changed",
                    ):
                        build_satellite_change_review_v1(DEFINITION)

    def test_writers_are_collision_safe_lock_aware_and_freeze_only(self) -> None:
        module = _module()
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            temporary_root = Path(temporary)
            output = temporary_root / "review"
            try:
                write_satellite_change_review_v1(DEFINITION, output)
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
                self.assertTrue(
                    all(
                        stat.S_IMODE(path.stat().st_mode) == 0o444
                        for path in output.iterdir()
                    )
                )
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV1Error, "existing output"
                ):
                    write_satellite_change_review_v1(DEFINITION, output)
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV1Error, "requires freeze=True"
                ):
                    write_satellite_change_review_v1(
                        DEFINITION, temporary_root / "unfrozen", freeze=False
                    )
                locked = temporary_root / "locked"
                lock_path = locked.parent / f".{locked.name}.lock"
                lock_path.write_text("active\n")
                with self.assertRaisesRegex(
                    SatelliteChangeReviewV1Error, "active output lock"
                ):
                    write_satellite_change_review_v1(DEFINITION, locked)
                lock_path.unlink()
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
                    SatelliteChangeReviewV1Error, "existing output"
                ):
                    write_review_definition(ROOT, destination)

    def test_source_v14_and_prior_review_are_unchanged_by_rebuild(self) -> None:
        module = _module()
        source_before = module._tree_inventory(SOURCE, "source change run")
        pinned_before = {path: _pin(path) for path in (*V14_PINS, PRIOR_REVIEW)}
        with _offline_guard():
            build_satellite_change_review_v1(DEFINITION)
            validate_satellite_change_review_v1(BUNDLE, definition_path=DEFINITION)
        source_after = module._tree_inventory(SOURCE, "source change run")
        pinned_after = {path: _pin(path) for path in (*V14_PINS, PRIOR_REVIEW)}
        self.assertEqual(source_before, source_after)
        self.assertEqual(source_after, {key: value for key, value in SOURCE_TREE.items() if key != "path"})
        self.assertEqual(pinned_before, pinned_after)
        for path, (size, digest) in V14_PINS.items():
            self.assertEqual(_pin(path)[:2], (size, digest))
        self.assertEqual(_pin(PRIOR_REVIEW)[:2], PRIOR_REVIEW_PIN)

    def test_both_workspace_import_layouts_and_cli_validate(self) -> None:
        code = (
            "from pathlib import Path; "
            "from datacenter_atlas.satellite_change_review_v1 import "
            "validate_satellite_change_review_v1; "
            f"m=validate_satellite_change_review_v1(Path({str(BUNDLE)!r}), "
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
        self.assertEqual(payload["decisions"], 2)


if __name__ == "__main__":
    unittest.main()
