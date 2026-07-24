from __future__ import annotations

import ast
import copy
from contextlib import ExitStack
import hashlib
import importlib
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Callable
import unittest
from unittest.mock import patch

from datacenter_atlas.satellite_catalog_reselection_v2 import (
    build_catalog_reselection_v2,
    capture_grid_header_evidence_v2,
)
from datacenter_atlas.satellite_reselected_change_batch_v2 import (
    CHANGE_SCOPE,
    RESELECTED_CHANGE_BATCH_PIPELINE,
    ChangeBatchConfig,
    SatelliteReselectedChangeBatchV2Error,
    execute_satellite_reselected_change_batch_v2,
    validate_reselected_change_inputs_v2,
    validate_satellite_reselected_change_batch_v2,
)


runner_v2 = importlib.import_module(
    execute_satellite_reselected_change_batch_v2.__module__
)
reselection_v2 = importlib.import_module(build_catalog_reselection_v2.__module__)

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
QUEUE = ROOT / "satellite_review_queues/2026-07-20-open-seed-v43"
SOURCE = ROOT / "satellite_review_runs/2026-07-20-open-seed-v43-active-001"
RELEASE = (
    ROOT
    / "satellite_catalog_reselection_runs"
    / "2026-07-20-open-seed-v43-active-v2-001"
)
DOCKLANDS = "satq-cef871428da247c3ecfadec6"
NEXTDC = "satq-d0a872a7aee9f9f54a8631ef"
CANDIDATES = (DOCKLANDS, NEXTDC)
REVERSED_REPEATED = (NEXTDC, DOCKLANDS, NEXTDC)
RUN_AT = "2026-07-20T09:00:00Z"

V1_PINS = {
    "datacenter_atlas/satellite_reselected_change_batch.py": (
        31_740,
        "2f988b73d9003d50062fde57ded0ee7fbea6aafc562b01a6b66bb98cc3d4828e",
    ),
    "scripts/run_satellite_reselected_change_batch.py": (
        3_800,
        "6f475395f32e0e6da23988897ec8fac367226416d5516cb7a496ec0c65715975",
    ),
    "tests/test_satellite_reselected_change_batch.py": (
        4_402,
        "bc6c51d64eacf51088cf6f8dbe28d82a59d877e341bd5dae7af9ca0caba0baf4",
    ),
    "docs/satellite_change_batch.md": (
        17_240,
        "cba2944506db9b21078e184a0708fd3509874c1ffb6f82ce8d381a920968c07c",
    ),
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


class _FailingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, 1, "", "intentional offline fixture failure"
        )


class _SuccessfulRunner:
    def __init__(self, before_return: Callable[[], None] | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.before_return = before_return

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        output_flag = command.index("--output-dir")
        stage = Path(command[output_flag + 1])
        stage.mkdir(parents=True)
        for name in runner_v2.legacy.CHANGE_FILES:
            (stage / name).write_bytes(b"")
        if self.before_return is not None:
            self.before_return()
        return subprocess.CompletedProcess(command, 0, "", "")


class SatelliteReselectedChangeBatchV2Tests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("offline runner attempted network or raster access")
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

    def _fake_change_result(
        self, task: dict[str, object], directory: Path, _: Path
    ) -> dict[str, object]:
        self.assertTrue(directory.is_dir())
        self.assertEqual(
            {path.name for path in directory.iterdir()},
            set(runner_v2.legacy.CHANGE_FILES),
        )
        return {
            "artifacts": {
                name: runner_v2.legacy._file_record(directory / name)
                for name in sorted(runner_v2.legacy.CHANGE_FILES)
            },
            "report": {"mocked_numerical_output": True, "queue_id": task["queue_id"]},
        }

    def test_dynamic_ids_are_canonicalized_and_lineage_is_complete(self) -> None:
        with self._offline():
            validated = validate_reselected_change_inputs_v2(
                QUEUE, SOURCE, REVERSED_REPEATED, RELEASE
            )
        self.assertFalse(validated["change_analysis_executed"])
        self.assertEqual(validated["selection"]["selected_queue_ids"], list(CANDIDATES))
        self.assertEqual(validated["selection"]["include_queue_ids"], list(CANDIDATES))
        self.assertEqual(
            validated["summary"],
            {
                "jobs_validated": 2,
                "candidate_jobs": 2,
                "supported_jobs": 2,
                "unresolved_jobs": 0,
                "jobs_unresolved_multitile_needed": 0,
                "change_jobs_executed": 0,
            },
        )
        context = validated["catalog_reselection_v2"]
        self.assertEqual(context["candidate_queue_ids"], list(CANDIDATES))
        self.assertEqual(context["supported_queue_ids"], list(CANDIDATES))
        self.assertEqual(context["unresolved_queue_ids"], [])
        self.assertTrue(context["supported_jobs_executed_only"])
        self.assertFalse(context["unresolved_candidates_executed"])
        source_tree = context["source_catalog_tree"]
        self.assertEqual(source_tree["directory_mode"], "0555")
        self.assertEqual(source_tree["file_mode"], "0444")
        self.assertEqual(len(source_tree["inventory_sha256"]), 64)
        self.assertGreater(source_tree["directories"], 0)
        self.assertGreater(source_tree["files"], 0)
        self.assertEqual(validated["scope"], CHANGE_SCOPE)
        self.assertFalse(validated["scope"]["imagery_load_inference"])
        self.assertFalse(validated["scope"]["imagery_unique_site_inference"])
        processor = validated["processor"]
        self.assertEqual(processor["runtime"]["python"]["cache_tag"], "cpython-312")
        self.assertEqual(
            processor["runtime"]["packages"]["rasterio"]["version"], "1.5.0"
        )
        self.assertTrue(
            processor["reselection_adapter"]["numerical_processor_reused_unchanged"]
        )
        for relative in runner_v2.RESELECTION_ADAPTER_FILES:
            self.assertIn(relative, processor["files"])
        source = (
            ROOT / "datacenter_atlas/satellite_reselected_change_batch_v2.py"
        ).read_text()
        self.assertNotIn("SUPPORTED_QUEUE_IDS", source)

    def test_bounded_failure_checkpoint_resumes_and_rejects_extra_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            runner = _FailingRunner()
            config = ChangeBatchConfig(
                timeout_seconds=7,
                minimum_interval_seconds=0,
                max_job_attempts=1,
            )
            with self._offline():
                first = execute_satellite_reselected_change_batch_v2(
                    QUEUE,
                    SOURCE,
                    REVERSED_REPEATED,
                    RELEASE,
                    output,
                    config=config,
                    max_jobs=1,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
                self.assertEqual(
                    validate_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        REVERSED_REPEATED,
                        RELEASE,
                        output,
                        config=config,
                    ),
                    first,
                )
                resumed = execute_satellite_reselected_change_batch_v2(
                    QUEUE,
                    SOURCE,
                    REVERSED_REPEATED,
                    RELEASE,
                    output,
                    config=config,
                    max_jobs=2,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
            self.assertEqual(first["summary"]["jobs_failed"], 1)
            self.assertEqual(first["summary"]["jobs_pending"], 1)
            self.assertTrue(first["runs"][-1]["budget_exhausted"])
            self.assertEqual(resumed["summary"]["jobs_failed"], 2)
            self.assertEqual(resumed["summary"]["jobs_exhausted"], 2)
            self.assertEqual(
                [task["attempts"] for task in resumed["jobs"].values()], [1, 1]
            )
            self.assertEqual(len(runner.calls), 2)
            self.assertEqual({call[1]["timeout"] for call in runner.calls}, {7})
            for task in resumed["jobs"].values():
                self.assertIn("catalog_reselection_v2", task)
                self.assertEqual(task["failures"][-1]["kind"], "command_exit")
            (output / "unexpected.txt").write_text("closed tree", encoding="utf-8")
            with self.assertRaises(runner_v2.legacy.SatelliteChangeBatchError):
                with self._offline():
                    validate_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        REVERSED_REPEATED,
                        RELEASE,
                        output,
                        config=config,
                    )

    def test_mock_processor_success_is_atomic_bounded_and_interval_limited(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            runner = _SuccessfulRunner()
            sleeps: list[float] = []
            config = ChangeBatchConfig(
                timeout_seconds=9,
                minimum_interval_seconds=0.25,
                max_job_attempts=1,
            )
            with (
                self._offline(),
                patch.object(
                    runner_v2.legacy,
                    "_change_result",
                    side_effect=self._fake_change_result,
                ),
            ):
                document = execute_satellite_reselected_change_batch_v2(
                    QUEUE,
                    SOURCE,
                    REVERSED_REPEATED,
                    RELEASE,
                    output,
                    config=config,
                    max_jobs=2,
                    command_runner=runner,
                    sleep=sleeps.append,
                    timestamp=lambda: RUN_AT,
                )
                self.assertEqual(
                    validate_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        REVERSED_REPEATED,
                        RELEASE,
                        output,
                        config=config,
                    ),
                    document,
                )
            self.assertEqual(document["pipeline"], RESELECTED_CHANGE_BATCH_PIPELINE)
            self.assertEqual(document["state"], "completed")
            self.assertEqual(document["summary"]["jobs_completed"], 2)
            self.assertEqual(len(runner.calls), 2)
            self.assertEqual({call[1]["timeout"] for call in runner.calls}, {9})
            self.assertEqual(sleeps, [0.25])
            self.assertFalse((output / ".batch-manifest.json.tmp").exists())
            self.assertFalse(
                any(path.name.endswith(".staging") for path in output.rglob("*"))
            )

    def test_post_publication_exception_is_recovered_without_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            runner = _SuccessfulRunner()
            config = ChangeBatchConfig(
                minimum_interval_seconds=0,
                max_job_attempts=1,
            )
            timestamp_calls = 0

            def fail_completion_timestamp() -> str:
                nonlocal timestamp_calls
                timestamp_calls += 1
                if timestamp_calls == 3:
                    return "not-an-rfc3339-timestamp"
                return RUN_AT

            with (
                self._offline(),
                patch.object(
                    runner_v2.legacy,
                    "_change_result",
                    side_effect=self._fake_change_result,
                ),
            ):
                with self.assertRaisesRegex(
                    runner_v2.legacy.SatelliteChangeBatchError,
                    "completion timestamp",
                ):
                    execute_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        REVERSED_REPEATED,
                        RELEASE,
                        output,
                        config=config,
                        max_jobs=1,
                        command_runner=runner,
                        sleep=lambda _: None,
                        timestamp=fail_completion_timestamp,
                    )
                interrupted = runner_v2.legacy._load_checkpoint(
                    output / runner_v2.CHANGE_BATCH_MANIFEST_FILENAME
                )
                first = interrupted["jobs"][DOCKLANDS]
                first_final, first_stage = runner_v2.legacy._task_paths(output, first)
                self.assertEqual(interrupted["runs"][-1]["state"], "running")
                self.assertEqual(first["state"], "running")
                self.assertTrue(first_final.is_dir())
                self.assertFalse(first_stage.exists())

                resumed = execute_satellite_reselected_change_batch_v2(
                    QUEUE,
                    SOURCE,
                    REVERSED_REPEATED,
                    RELEASE,
                    output,
                    config=config,
                    max_jobs=1,
                    command_runner=runner,
                    sleep=lambda _: None,
                    timestamp=lambda: RUN_AT,
                )
                self.assertEqual(
                    validate_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        REVERSED_REPEATED,
                        RELEASE,
                        output,
                        config=config,
                    ),
                    resumed,
                )
            self.assertEqual(resumed["state"], "completed")
            self.assertEqual(resumed["summary"]["jobs_completed"], 2)
            self.assertEqual(len(runner.calls), 2)
            self.assertEqual(resumed["runs"][0]["state"], "interrupted")
            self.assertEqual(resumed["runs"][0]["jobs_recovered_after_publish"], 1)
            self.assertEqual(resumed["runs"][1]["jobs_completed"], 1)
            self.assertEqual(
                [task["attempts"] for task in resumed["jobs"].values()],
                [1, 1],
            )

    def test_mid_command_source_tree_drift_blocks_publication(self) -> None:
        mutations = ("content", "mode", "extra")
        for mutation in mutations:
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                source = root / "source"
                output = root / "change-run"
                shutil.copytree(SOURCE, source)
                target = (
                    source / "jobs" / DOCKLANDS / "catalog" / "baseline-response.json"
                )

                def mutate_source() -> None:
                    if mutation == "content":
                        target.chmod(0o644)
                        target.write_bytes(target.read_bytes() + b" ")
                        target.chmod(0o444)
                    elif mutation == "mode":
                        target.chmod(0o644)
                    else:
                        source.chmod(0o755)
                        extra = source / "unexpected.txt"
                        extra.write_text("unexpected", encoding="utf-8")
                        extra.chmod(0o444)
                        source.chmod(0o555)

                runner = _SuccessfulRunner(before_return=mutate_source)
                config = ChangeBatchConfig(
                    minimum_interval_seconds=0,
                    max_job_attempts=1,
                )
                try:
                    with (
                        self._offline(),
                        patch.object(
                            runner_v2.legacy,
                            "_change_result",
                            side_effect=self._fake_change_result,
                        ),
                    ):
                        with self.assertRaisesRegex(
                            SatelliteReselectedChangeBatchV2Error,
                            "original source catalog",
                        ):
                            execute_satellite_reselected_change_batch_v2(
                                QUEUE,
                                source,
                                REVERSED_REPEATED,
                                RELEASE,
                                output,
                                config=config,
                                max_jobs=1,
                                command_runner=runner,
                                sleep=lambda _: None,
                                timestamp=lambda: RUN_AT,
                            )
                    checkpoint = runner_v2.legacy._load_checkpoint(
                        output / runner_v2.CHANGE_BATCH_MANIFEST_FILENAME
                    )
                    task = checkpoint["jobs"][DOCKLANDS]
                    final, stage = runner_v2.legacy._task_paths(output, task)
                    self.assertEqual(task["state"], "failed")
                    self.assertEqual(task["failures"][-1]["kind"], "output_validation")
                    self.assertFalse(final.exists())
                    self.assertFalse(stage.exists())
                    self.assertEqual(len(runner.calls), 1)
                finally:
                    self._thaw(source)

    def test_mid_command_pinned_runtime_drift_fails_after_a_failed_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "change-run"
            command_runner = _FailingRunner()
            original = runner_v2._processor_lineage(ROOT)
            drifted = copy.deepcopy(original)
            drifted["runtime"]["python"]["version"] = "drifted-runtime"
            calls = 0

            def changing_lineage(_: Path) -> dict[str, object]:
                nonlocal calls
                calls += 1
                return copy.deepcopy(original if calls < 3 else drifted)

            with self.assertRaisesRegex(
                runner_v2.legacy.SatelliteChangeBatchError,
                "pinned runtime changed",
            ):
                with (
                    self._offline(),
                    patch.object(
                        runner_v2,
                        "_processor_lineage",
                        side_effect=changing_lineage,
                    ),
                ):
                    execute_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        REVERSED_REPEATED,
                        RELEASE,
                        output,
                        config=ChangeBatchConfig(minimum_interval_seconds=0),
                        max_jobs=1,
                        command_runner=command_runner,
                        sleep=lambda _: None,
                        timestamp=lambda: RUN_AT,
                    )
            self.assertEqual(len(command_runner.calls), 1)
            self.assertGreaterEqual(calls, 4)

    def test_all_unresolved_release_executes_zero_jobs_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "grid-headers.json"
            release = root / "release"
            output = root / "change-run"

            def forbidden_runner(*_: object, **__: object) -> object:
                raise AssertionError("unresolved candidate reached numerical processor")

            try:
                with (
                    patch.object(
                        reselection_v2,
                        "_select_comparable_pair",
                        return_value=(None, None, None, 0),
                    ),
                    self._offline(),
                ):
                    capture_grid_header_evidence_v2(
                        QUEUE,
                        SOURCE,
                        [DOCKLANDS, DOCKLANDS],
                        header,
                        captured_at=RUN_AT,
                    )
                    build_catalog_reselection_v2(
                        QUEUE,
                        SOURCE,
                        [DOCKLANDS, DOCKLANDS],
                        header,
                        release,
                        generated_at=RUN_AT,
                    )
                    validated = validate_reselected_change_inputs_v2(
                        QUEUE,
                        SOURCE,
                        [DOCKLANDS, DOCKLANDS],
                        release,
                    )
                    document = execute_satellite_reselected_change_batch_v2(
                        QUEUE,
                        SOURCE,
                        [DOCKLANDS, DOCKLANDS],
                        release,
                        output,
                        max_jobs=1,
                        command_runner=forbidden_runner,
                        sleep=lambda _: None,
                        timestamp=lambda: RUN_AT,
                    )
                    self.assertEqual(
                        validate_satellite_reselected_change_batch_v2(
                            QUEUE,
                            SOURCE,
                            [DOCKLANDS, DOCKLANDS],
                            release,
                            output,
                        ),
                        document,
                    )
                self.assertEqual(validated["summary"]["candidate_jobs"], 1)
                self.assertEqual(validated["summary"]["supported_jobs"], 0)
                self.assertEqual(validated["summary"]["unresolved_jobs"], 1)
                self.assertEqual(validated["selection"]["selected_queue_ids"], [])
                self.assertEqual(document["state"], "completed")
                self.assertEqual(document["jobs"], {})
                self.assertEqual(document["summary"]["jobs_selected"], 0)
                self.assertEqual(document["runs"][-1]["job_attempts"], 0)
                self.assertEqual(
                    document["catalog_reselection_v2"]["unresolved_queue_ids"],
                    [DOCKLANDS],
                )
            finally:
                self._thaw(release)

    def test_release_extra_content_tamper_and_mode_drift_fail_closed(self) -> None:
        mutations = ("extra", "content", "mode")
        for mutation in mutations:
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as temporary,
            ):
                copied = Path(temporary) / "release"
                shutil.copytree(RELEASE, copied)
                try:
                    self._thaw(copied)
                    if mutation == "extra":
                        (copied / "unexpected.txt").write_text(
                            "extra", encoding="utf-8"
                        )
                        reselection_v2._freeze_tree(copied)
                    elif mutation == "content":
                        target = copied / "grid-headers.json"
                        target.write_bytes(target.read_bytes() + b"\n")
                        reselection_v2._freeze_tree(copied)
                    else:
                        reselection_v2._freeze_tree(copied)
                        (copied / "grid-headers.json").chmod(0o644)
                    with self.assertRaises(SatelliteReselectedChangeBatchV2Error):
                        with self._offline():
                            validate_reselected_change_inputs_v2(
                                QUEUE, SOURCE, REVERSED_REPEATED, copied
                            )
                finally:
                    self._thaw(copied)

    def test_v1_files_are_pinned_and_both_import_layouts_work(self) -> None:
        for relative, expected in V1_PINS.items():
            with self.subTest(path=relative):
                raw = (ROOT / relative).read_bytes()
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), expected)

        command = [
            sys.executable,
            "-c",
            (
                "from datacenter_atlas.satellite_reselected_change_batch_v2 "
                "import RESELECTED_CHANGE_BATCH_PIPELINE; "
                "print(RESELECTED_CHANGE_BATCH_PIPELINE)"
            ),
        ]
        for cwd in (WORKSPACE, ROOT):
            with self.subTest(cwd=cwd):
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    completed.stdout.strip(), RESELECTED_CHANGE_BATCH_PIPELINE
                )
        cli = (ROOT / "scripts/run_satellite_reselected_change_batch_v2.py").read_text()
        self.assertIn('action="append"', cli)
        self.assertIn("required=True", cli)
        self.assertEqual(cli.count("arguments.queue_ids"), 3)

        source = (
            ROOT / "datacenter_atlas/satellite_reselected_change_batch_v2.py"
        ).read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            literal_keys = [
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            self.assertEqual(
                len(literal_keys),
                len(set(literal_keys)),
                f"duplicate literal dictionary key at line {node.lineno}",
            )


if __name__ == "__main__":
    unittest.main()
