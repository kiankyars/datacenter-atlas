from __future__ import annotations

from contextlib import ExitStack
import hashlib
import importlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_catalog_reselection_v2 import (
    RESELECTION_SCOPE,
    SOURCE_MANIFEST_FILENAME,
    SatelliteCatalogReselectionV2Error,
    build_catalog_reselection_v2,
    capture_grid_header_evidence_v2,
    plan_catalog_reselection_v2,
    release_catalog_tasks_v2,
    validate_catalog_reselection_v2,
)


reselection = importlib.import_module(plan_catalog_reselection_v2.__module__)


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v43"
SOURCE = ROOT / "satellite_review_runs/2026-07-20-open-seed-v43-active-001"
DOCKLANDS = "satq-cef871428da247c3ecfadec6"
NEXTDC = "satq-d0a872a7aee9f9f54a8631ef"
FULLY_SUPPORTED = "satq-02a713b5d0ec25375cffb0c3"
PENDING = "satq-8324f676e6e2095fc5ec5973"
CANDIDATES = (DOCKLANDS, NEXTDC)
REVERSED_REPEATED = (NEXTDC, DOCKLANDS, NEXTDC)
CAPTURED_AT = "2026-07-20T08:00:00Z"
GENERATED_AT = "2026-07-20T08:01:00Z"

EXPECTED_SELECTED = {
    DOCKLANDS: {
        "baseline": "S2B_30UYC_20240626_0_L2A",
        "current": "S2C_30UYC_20260624_0_L2A",
    },
    NEXTDC: {
        "baseline": "S2B_56JNR_20240712_0_L2A",
        "current": "S2B_56JNR_20260702_0_L2A",
    },
}

V1_PINS = {
    "datacenter_atlas/satellite_catalog_reselection.py": (
        58_039,
        "bdde7818d6fa90b129076e7ce3029c326fed114e8980dabb9d92dfbdfe8a50aa",
    ),
    "scripts/build_satellite_catalog_reselection.py": (
        3_540,
        "a07e489d732c6a16fcc6a82b4c8f1a2cedeb82d741553320e9ac1339ad5a75d2",
    ),
    "tests/test_satellite_catalog_reselection.py": (
        8_135,
        "3a187cd830b5dce3abc97f92cd5a5e78b178e0b4743549aa2fa1ddb7ce6c1d9c",
    ),
}


class _Dataset:
    def __init__(self, grid: dict[str, object]) -> None:
        self.width = grid["width"]
        self.height = grid["height"]
        self.count = 1
        self.dtypes = ("uint16",)
        self.crs = grid["crs"]
        self.transform = tuple(grid["transform"])
        self.nodata = 0
        self.driver = "GTiff"
        self.read_calls = 0

    def __enter__(self) -> _Dataset:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, *_: object, **__: object) -> object:
        self.read_calls += 1
        raise AssertionError("header capture attempted a raster pixel read")


class SatelliteCatalogReselectionV2Tests(unittest.TestCase):
    def _plan(self):
        return plan_catalog_reselection_v2(QUEUE, SOURCE, REVERSED_REPEATED)

    def _header_grids(self, plan) -> dict[str, dict[str, object]]:
        items = {
            item["id"]: item
            for job in plan.jobs
            for item in job.selected_items.values()
        }
        return {
            href: reselection._stac_grid(items[identity["item_id"]], identity["asset"])
            for href, identity in reselection._expected_header_assets(plan).items()
        }

    def _capture(self, path: Path):
        plan = self._plan()
        grids = self._header_grids(plan)
        opened: list[str] = []
        datasets: list[_Dataset] = []

        def open_metadata(href: str) -> _Dataset:
            self.assertIn(href, grids)
            opened.append(href)
            dataset = _Dataset(grids[href])
            datasets.append(dataset)
            return dataset

        with patch("rasterio.open", side_effect=open_metadata):
            document = capture_grid_header_evidence_v2(
                QUEUE,
                SOURCE,
                REVERSED_REPEATED,
                path,
                captured_at=CAPTURED_AT,
            )
        self.assertEqual(opened, sorted(grids))
        self.assertTrue(datasets)
        self.assertEqual({dataset.read_calls for dataset in datasets}, {0})
        return document

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("offline build or validation attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        stack.enter_context(patch("rasterio.open", side_effect=error))
        return stack

    def _thaw(self, root: Path) -> None:
        if not root.exists() or root.is_symlink():
            return
        root.chmod(0o755)
        for path in root.rglob("*"):
            if path.is_dir() and not path.is_symlink():
                path.chmod(0o755)
            elif path.is_file() and not path.is_symlink():
                path.chmod(0o644)

    def _tree_hashes(self, root: Path) -> dict[str, tuple[int, str]]:
        return {
            path.relative_to(root).as_posix(): (
                path.stat().st_size,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_v1_carrier_remains_exactly_byte_pinned(self) -> None:
        for relative, expected in V1_PINS.items():
            with self.subTest(path=relative):
                path = ROOT / relative
                raw = path.read_bytes()
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), expected)

    def test_repeated_explicit_ids_are_deduplicated_and_canonicalized(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.candidate_queue_ids, CANDIDATES)
        self.assertEqual(
            tuple(job.queue["queue_id"] for job in plan.jobs), CANDIDATES
        )
        self.assertEqual(plan.unresolved["jobs"], [])

        for job in plan.jobs:
            queue_id = job.queue["queue_id"]
            manifest = job.derived_manifest
            self.assertTrue(manifest["original_selection_failed_full_support"])
            self.assertEqual(
                manifest["original_selection_failed_epochs"],
                ["baseline", "current"],
            )
            self.assertEqual(manifest["selected_ids"], EXPECTED_SELECTED[queue_id])
            self.assertNotEqual(
                manifest["selected_ids"], manifest["original_selected_ids"]
            )
            self.assertGreater(manifest["comparable_pair_count"], 0)
            for epoch in ("baseline", "current"):
                coverage = manifest["selected_features"][epoch][
                    "stac_grid_coverage"
                ]
                self.assertTrue(
                    coverage["all_required_asset_windows_within_grid"]
                )
                self.assertEqual(len(coverage["assets"]), 6)
                self.assertTrue(
                    all(asset["within_grid"] for asset in coverage["assets"])
                )

        def task(queue_id: str) -> dict[str, object]:
            return {
                "output_directory": f"jobs/{queue_id}/catalog",
                "selected_ids": {"baseline": "before", "current": "after"},
                "artifacts": {
                    "baseline-response.json": {"bytes": 1, "sha256": "a" * 64},
                    "current-response.json": {"bytes": 1, "sha256": "b" * 64},
                    "manifest.json": {"bytes": 1, "sha256": "c" * 64},
                },
            }

        serialized_order = {
            "configuration": {"supported_queue_ids": [NEXTDC, DOCKLANDS]},
            "jobs": {DOCKLANDS: task(DOCKLANDS), NEXTDC: task(NEXTDC)},
        }
        self.assertEqual(
            list(release_catalog_tasks_v2(serialized_order)),
            [NEXTDC, DOCKLANDS],
        )

    def test_only_completed_genuinely_failed_candidates_are_accepted(self) -> None:
        with self.assertRaisesRegex(
            SatelliteCatalogReselectionV2Error,
            "already fully covered",
        ):
            plan_catalog_reselection_v2(QUEUE, SOURCE, [FULLY_SUPPORTED])
        with self.assertRaisesRegex(
            SatelliteCatalogReselectionV2Error,
            "not completed",
        ):
            plan_catalog_reselection_v2(QUEUE, SOURCE, [PENDING])
        with self.assertRaisesRegex(
            SatelliteCatalogReselectionV2Error,
            "at least one",
        ):
            plan_catalog_reselection_v2(QUEUE, SOURCE, [])
        with self.assertRaisesRegex(
            SatelliteCatalogReselectionV2Error,
            "lacks explicit candidate",
        ):
            plan_catalog_reselection_v2(QUEUE, SOURCE, ["satq-not-in-queue"])

    def test_no_comparable_pair_emits_explicit_unresolved_record(self) -> None:
        with patch.object(
            reselection,
            "_select_comparable_pair",
            return_value=(None, None, None, 0),
        ):
            plan = plan_catalog_reselection_v2(QUEUE, SOURCE, [DOCKLANDS])
        self.assertEqual(plan.jobs, ())
        self.assertEqual(len(plan.unresolved["jobs"]), 1)
        unresolved = plan.unresolved["jobs"][0]
        self.assertEqual(unresolved["queue_id"], DOCKLANDS)
        self.assertEqual(
            unresolved["outcome"],
            "unresolved_multitile_or_supplemental_scene_required",
        )
        self.assertEqual(unresolved["comparable_pair_count"], 0)
        self.assertTrue(unresolved["original_selection_failed_full_support"])
        self.assertFalse(unresolved["unavailable_no_scene_claim"])
        self.assertFalse(unresolved["reselection_emitted"])
        self.assertIn("not a no-scene claim", plan.unresolved["meaning"])
        self.assertEqual(
            set(unresolved["source_artifacts"]),
            {"baseline_response", "current_response", "source_manifest"},
        )

    def test_capture_opens_selected_metadata_only_and_binds_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "grid-headers.json"
            document = self._capture(output)
            self.assertEqual(document["candidate_queue_ids"], list(CANDIDATES))
            self.assertEqual(document["scope"]["pixel_reads"], 0)
            self.assertTrue(document["scope"]["opens_selected_assets_only"])
            self.assertIsNone(document["scope"]["http_request_count"])
            self.assertEqual(document["asset_open_operations"], 24)
            self.assertEqual(len(document["assets"]), 24)
            self.assertEqual(
                document["selection_plan_sha256"],
                reselection._canonical_hash(document["candidate_bindings"]),
            )
            self.assertEqual(
                set(document["candidate_bindings"]["supported"]),
                set(CANDIDATES),
            )
            self.assertEqual(document["candidate_bindings"]["unresolved"], {})
            raw = output.read_bytes()
            self.assertEqual(raw, reselection._canonical_bytes(document))

    def test_offline_build_is_atomic_frozen_closed_and_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "grid-headers.json"
            self._capture(header)
            outputs = [root / "release-a", root / "release-b"]
            try:
                manifests = []
                for output in outputs:
                    with self._offline():
                        manifests.append(
                            build_catalog_reselection_v2(
                                QUEUE,
                                SOURCE,
                                REVERSED_REPEATED,
                                header,
                                output,
                                generated_at=GENERATED_AT,
                            )
                        )
                    self.assertFalse(
                        output.with_name(f".{output.name}.staging-v2").exists()
                    )
                    self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o555)
                    for path in output.rglob("*"):
                        expected_mode = 0o555 if path.is_dir() else 0o444
                        self.assertEqual(
                            stat.S_IMODE(path.stat().st_mode), expected_mode
                        )
                self.assertEqual(manifests[0], manifests[1])
                self.assertEqual(
                    self._tree_hashes(outputs[0]), self._tree_hashes(outputs[1])
                )
                manifest = manifests[0]
                self.assertEqual(manifest["scope"], RESELECTION_SCOPE)
                self.assertEqual(
                    manifest["configuration"]["candidate_queue_ids"],
                    list(CANDIDATES),
                )
                self.assertEqual(
                    manifest["configuration"]["supported_queue_ids"],
                    list(CANDIDATES),
                )
                self.assertEqual(
                    manifest["configuration"]["unresolved_queue_ids"], []
                )
                self.assertEqual(
                    manifest["summary"],
                    {
                        "candidate_jobs_assessed": 2,
                        "jobs_reselected": 2,
                        "unique_aois_reselected": 2,
                        "jobs_unresolved_multitile_needed": 0,
                        "raw_provider_response_files_copied": 4,
                        "source_catalog_manifest_files_copied": 2,
                        "change_jobs_executed": 0,
                        "atlas_rows_emitted": 0,
                    },
                )
                self.assertEqual(
                    list(release_catalog_tasks_v2(manifest)), list(CANDIDATES)
                )
                for queue_id in CANDIDATES:
                    top = manifest["jobs"][queue_id]
                    release_job = outputs[0] / top["output_directory"]
                    source_job = SOURCE / top["output_directory"]
                    self.assertEqual(
                        (release_job / "baseline-response.json").read_bytes(),
                        (source_job / "baseline-response.json").read_bytes(),
                    )
                    self.assertEqual(
                        (release_job / "current-response.json").read_bytes(),
                        (source_job / "current-response.json").read_bytes(),
                    )
                    self.assertEqual(
                        (release_job / SOURCE_MANIFEST_FILENAME).read_bytes(),
                        (source_job / "manifest.json").read_bytes(),
                    )
                    derived = json.loads(
                        (release_job / "manifest.json").read_text(encoding="utf-8")
                    )
                    self.assertEqual(derived["selected_ids"], EXPECTED_SELECTED[queue_id])
                    for epoch in ("baseline", "current"):
                        self.assertTrue(
                            derived["selected_features"][epoch][
                                "observed_header_coverage"
                            ]["all_required_asset_windows_within_grid"]
                        )
            finally:
                for output in outputs:
                    self._thaw(output)

    def test_build_and_validator_fail_closed_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "grid-headers.json"
            document = self._capture(header)
            document["candidate_queue_ids"] = list(reversed(CANDIDATES))
            header.write_bytes(reselection._canonical_bytes(document))
            output = root / "release"
            with self.assertRaisesRegex(
                SatelliteCatalogReselectionV2Error,
                "candidate or input lineage changed",
            ):
                with self._offline():
                    build_catalog_reselection_v2(
                        QUEUE,
                        SOURCE,
                        CANDIDATES,
                        header,
                        output,
                        generated_at=GENERATED_AT,
                    )
            self.assertFalse(output.exists())
            self.assertFalse(
                output.with_name(f".{output.name}.staging-v2").exists()
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "grid-headers.json"
            self._capture(header)
            output = root / "release"
            try:
                with self._offline():
                    build_catalog_reselection_v2(
                        QUEUE,
                        SOURCE,
                        CANDIDATES,
                        header,
                        output,
                        generated_at=GENERATED_AT,
                    )
                self._thaw(output)
                extra = output / "unexpected.txt"
                extra.write_text("closed world", encoding="utf-8")
                reselection._freeze_tree(output)
                with self.assertRaisesRegex(
                    SatelliteCatalogReselectionV2Error,
                    "unexpected file",
                ):
                    with self._offline():
                        validate_catalog_reselection_v2(
                            QUEUE, SOURCE, REVERSED_REPEATED, output
                        )
            finally:
                self._thaw(output)

    def test_cli_exposes_repeatable_queue_id_for_every_step(self) -> None:
        script = ROOT / "scripts/build_satellite_catalog_reselection_v2.py"
        text = script.read_text(encoding="utf-8")
        self.assertIn('action="append"', text)
        self.assertEqual(text.count("_inputs("), 4)
        self.assertIn("capture_grid_header_evidence_v2", text)
        self.assertIn("build_catalog_reselection_v2", text)
        self.assertIn("validate_catalog_reselection_v2", text)


if __name__ == "__main__":
    unittest.main()
