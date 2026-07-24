from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from unittest import mock

from scripts import catalog_satellite
from scripts import run_satellite_review_queue


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Headers(dict[str, str]):
    def get_all(self, name: str) -> list[str] | None:
        value = self.get(name)
        return None if value is None else [value]


class _MultiHeaders:
    def __init__(self, *values: str) -> None:
        self.values = list(values)

    def get_all(self, name: str) -> list[str] | None:
        return self.values if name == "Content-Length" else None


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        content_length: str | None = None,
        max_chunk_bytes: int | None = None,
    ) -> None:
        self.body = body
        self.headers = _Headers()
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.max_chunk_bytes = max_chunk_bytes
        self.offset = 0
        self.read_sizes: list[int] = []
        self.closed = False

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def close(self) -> None:
        self.closed = True

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if self.max_chunk_bytes is not None:
            size = min(size, self.max_chunk_bytes)
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def _request_plan() -> dict[str, object]:
    return {
        "url": "https://example.test/stac/search",
        "headers": {"Content-Type": "application/json"},
        "payload": {},
    }


def _catalog_arguments(output: Path) -> list[str]:
    return [
        "--bbox",
        "0,0,1,1",
        "--baseline-start",
        "2024-06-01",
        "--baseline-end",
        "2024-06-30",
        "--baseline-target",
        "2024-06-15",
        "--current-start",
        "2026-06-01",
        "--current-end",
        "2026-06-30",
        "--current-target",
        "2026-06-15",
        "--output-dir",
        str(output),
    ]


class SatelliteRunnerLockTests(unittest.TestCase):
    def test_parser_requires_explicit_lock_and_preserves_execution_defaults(self) -> None:
        arguments = run_satellite_review_queue.parser().parse_args(
            [
                "--queue-dir",
                "queue",
                "--output-dir",
                "run",
                "--lock-file",
                "locks/unknown.lock",
            ]
        )
        self.assertEqual(arguments.lock_file, Path("locks/unknown.lock"))
        self.assertEqual(arguments.max_jobs, 25)
        self.assertEqual(arguments.max_http_attempts, 50)
        self.assertEqual(arguments.max_job_attempts, 3)
        self.assertEqual(arguments.catalog_retries, 0)
        self.assertEqual(arguments.timeout_seconds, 60.0)
        self.assertEqual(
            arguments.max_response_bytes,
            catalog_satellite.DEFAULT_MAX_RESPONSE_BYTES,
        )

        overridden = run_satellite_review_queue.parser().parse_args(
            [
                "--queue-dir",
                "queue",
                "--output-dir",
                "run",
                "--lock-file",
                "locks/unknown.lock",
                "--max-response-bytes",
                "1234",
            ]
        )
        self.assertEqual(overridden.max_response_bytes, 1234)

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_satellite_review_queue.parser().parse_args(
                ["--queue-dir", "queue", "--output-dir", "run"]
            )

    def test_contention_is_nonblocking_and_process_crash_releases_lock(self) -> None:
        child_code = """
from pathlib import Path
import sys
from scripts.run_satellite_review_queue import _single_writer_lock
with _single_writer_lock(Path(sys.argv[1])):
    print("locked", flush=True)
    sys.stdin.buffer.read(1)
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "must-not-exist"
            lock_file = root / "must-not-exist.lock"
            holder = subprocess.Popen(
                [sys.executable, "-c", child_code, str(lock_file)],
                cwd=PROJECT_ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                assert holder.stdout is not None
                ready = holder.stdout.readline().strip()
                if ready != "locked":
                    assert holder.stderr is not None
                    self.fail(holder.stderr.read())

                started = time.monotonic()
                with self.assertRaisesRegex(SystemExit, "holds lock"):
                    run_satellite_review_queue.main(
                        [
                            "--queue-dir",
                            str(root / "missing-queue"),
                            "--output-dir",
                            str(output),
                            "--lock-file",
                            str(lock_file),
                        ]
                    )
                self.assertLess(time.monotonic() - started, 1.0)
                self.assertFalse(output.exists())

                holder.kill()
                holder.wait(timeout=5)
                with run_satellite_review_queue._single_writer_lock(lock_file):
                    pass
                self.assertTrue(lock_file.is_file())
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=5)
                for stream in (holder.stdin, holder.stdout, holder.stderr):
                    if stream is not None:
                        stream.close()

    def test_lock_file_inside_output_fails_before_creating_either_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "run"
            lock_file = output / "runner.lock"
            with self.assertRaisesRegex(SystemExit, "outside"):
                run_satellite_review_queue.main(
                    [
                        "--queue-dir",
                        str(root / "missing-queue"),
                        "--output-dir",
                        str(output),
                        "--lock-file",
                        str(lock_file),
                    ]
                )
            self.assertFalse(output.exists())
            self.assertFalse(lock_file.exists())

    def test_different_lock_file_cannot_create_second_domain_for_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "run"
            queue = root / "missing-queue"
            canonical = root / "run.lock"
            alternate = root / "alternate.lock"
            validated = run_satellite_review_queue._validated_lock_path(
                canonical, output, queue
            )
            with run_satellite_review_queue._single_writer_lock(validated):
                with self.assertRaisesRegex(SystemExit, "canonical output sibling"):
                    run_satellite_review_queue.main(
                        [
                            "--queue-dir",
                            str(queue),
                            "--output-dir",
                            str(output),
                            "--lock-file",
                            str(alternate),
                        ]
                    )
            self.assertFalse(alternate.exists())
            self.assertFalse(output.exists())

    def test_symlink_alias_resolves_to_same_canonical_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            resolved = run_satellite_review_queue._validated_lock_path(
                alias / "run.lock",
                alias / "run",
                root / "queue",
            )
            self.assertEqual(resolved, (real / "run.lock").resolve(strict=False))

    def test_parent_symlink_cannot_alias_lock_path_into_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_parent = root / "real"
            real_parent.mkdir()
            output = real_parent / "run"
            output.mkdir()
            alias = root / "alias"
            alias.symlink_to(real_parent, target_is_directory=True)
            lock_file = alias / "run" / "runner.lock"

            with self.assertRaisesRegex(SystemExit, "outside"):
                run_satellite_review_queue.main(
                    [
                        "--queue-dir",
                        str(root / "missing-queue"),
                        "--output-dir",
                        str(output),
                        "--lock-file",
                        str(lock_file),
                    ]
                )
            self.assertFalse(lock_file.exists())

    def test_lock_file_inside_queue_fails_without_mutating_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / "queue"
            queue.mkdir()
            lock_file = queue / "runner.lock"
            before = list(queue.iterdir())
            with self.assertRaisesRegex(SystemExit, "outside"):
                run_satellite_review_queue.main(
                    [
                        "--queue-dir",
                        str(queue),
                        "--output-dir",
                        str(root / "run"),
                        "--lock-file",
                        str(lock_file),
                    ]
                )
            self.assertEqual(list(queue.iterdir()), before)
            self.assertFalse(lock_file.exists())


class CatalogResponseLimitTests(unittest.TestCase):
    def test_parser_default_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "catalog"
            default = catalog_satellite.parser().parse_args(
                _catalog_arguments(output)
            )
            self.assertEqual(
                default.max_response_bytes,
                catalog_satellite.DEFAULT_MAX_RESPONSE_BYTES,
            )
            overridden = catalog_satellite.parser().parse_args(
                [*_catalog_arguments(output), "--max-response-bytes", "1234"]
            )
            self.assertEqual(overridden.max_response_bytes, 1234)

    def test_nonpositive_limit_fails_before_network_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "catalog"
            with mock.patch.object(
                catalog_satellite.urllib.request, "urlopen"
            ) as urlopen, self.assertRaisesRegex(SystemExit, "must be positive"):
                catalog_satellite.main(
                    [*_catalog_arguments(output), "--max-response-bytes", "0"]
                )
            urlopen.assert_not_called()
            self.assertFalse(output.exists())

    def test_under_cap_declared_body_streams_and_closes(self) -> None:
        response = _Response(b"catalog", content_length="7", max_chunk_bytes=2)
        with mock.patch.object(
            catalog_satellite.urllib.request,
            "urlopen",
            return_value=response,
        ):
            result = catalog_satellite._post(
                _request_plan(),
                timeout=1,
                retries=0,
                user_agent="fixture",
                pacer=catalog_satellite._RequestPacer(0),
                max_response_bytes=7,
            )
        self.assertEqual(result, b"catalog")
        self.assertTrue(response.closed)
        self.assertTrue(response.read_sizes)
        self.assertTrue(all(size > 0 for size in response.read_sizes))

    def test_oversized_declared_body_is_rejected_without_reading(self) -> None:
        response = _Response(b"ignored", content_length="8")
        with mock.patch.object(
            catalog_satellite.urllib.request,
            "urlopen",
            return_value=response,
        ), self.assertRaisesRegex(
            catalog_satellite.CatalogResponseTooLarge, "declared 8 bytes"
        ):
            catalog_satellite._post(
                _request_plan(),
                timeout=1,
                retries=0,
                user_agent="fixture",
                pacer=catalog_satellite._RequestPacer(0),
                max_response_bytes=7,
            )
        self.assertEqual(response.read_sizes, [])
        self.assertTrue(response.closed)

    def test_oversized_chunked_body_is_rejected_while_streaming(self) -> None:
        response = _Response(b"123456", max_chunk_bytes=2)
        with mock.patch.object(
            catalog_satellite.urllib.request,
            "urlopen",
            return_value=response,
        ), self.assertRaisesRegex(
            catalog_satellite.CatalogResponseTooLarge, "while streaming"
        ):
            catalog_satellite._post(
                _request_plan(),
                timeout=1,
                retries=0,
                user_agent="fixture",
                pacer=catalog_satellite._RequestPacer(0),
                max_response_bytes=5,
            )
        self.assertGreater(len(response.read_sizes), 1)
        self.assertTrue(response.closed)

    def test_truncated_declared_body_is_rejected_and_closed(self) -> None:
        response = _Response(b"short", content_length="7", max_chunk_bytes=2)
        with mock.patch.object(
            catalog_satellite.urllib.request,
            "urlopen",
            return_value=response,
        ), self.assertRaisesRegex(
            catalog_satellite.CatalogResponseError,
            "declared 7 bytes but streamed 5 bytes",
        ):
            catalog_satellite._post(
                _request_plan(),
                timeout=1,
                retries=0,
                user_agent="fixture",
                pacer=catalog_satellite._RequestPacer(0),
                max_response_bytes=7,
            )
        self.assertTrue(response.closed)

    def test_content_length_variants_are_strict(self) -> None:
        combined = _Response(b"catalog")
        combined.headers = _MultiHeaders("7, 7")
        self.assertEqual(
            catalog_satellite._read_bounded_response(combined, 7), b"catalog"
        )

        for values in (("7", "8"), ("7, 8",), ("+7",), ("",)):
            with self.subTest(values=values):
                response = _Response(b"catalog")
                response.headers = _MultiHeaders(*values)
                with self.assertRaises(catalog_satellite.CatalogResponseError):
                    catalog_satellite._read_bounded_response(response, 8)

    def test_underreported_length_cannot_bypass_stream_cap(self) -> None:
        response = _Response(b"123456", content_length="1", max_chunk_bytes=2)
        with self.assertRaisesRegex(
            catalog_satellite.CatalogResponseTooLarge, "while streaming"
        ):
            catalog_satellite._read_bounded_response(response, 5)

    def test_read_exception_closes_response(self) -> None:
        response = _Response(b"ignored")
        response.read = mock.Mock(side_effect=RuntimeError("read failed"))
        with mock.patch.object(
            catalog_satellite.urllib.request,
            "urlopen",
            return_value=response,
        ), self.assertRaisesRegex(RuntimeError, "read failed"):
            catalog_satellite._post(
                _request_plan(),
                timeout=1,
                retries=0,
                user_agent="fixture",
                pacer=catalog_satellite._RequestPacer(0),
                max_response_bytes=7,
            )
        self.assertTrue(response.closed)

    def test_http_error_response_is_closed_before_propagation(self) -> None:
        body = _Response(b"server error")
        error = urllib.error.HTTPError(
            "https://example.test/stac/search",
            500,
            "fixture",
            {},
            body,
        )
        with mock.patch.object(
            catalog_satellite.urllib.request,
            "urlopen",
            side_effect=error,
        ), self.assertRaises(urllib.error.HTTPError):
            catalog_satellite._post(
                _request_plan(),
                timeout=1,
                retries=0,
                user_agent="fixture",
                pacer=catalog_satellite._RequestPacer(0),
                max_response_bytes=7,
            )
        self.assertTrue(body.closed)

    def test_second_response_overflow_leaves_no_partial_output(self) -> None:
        baseline = _Response(b"{}", content_length="2")
        current = _Response(b"12345", max_chunk_bytes=2)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "catalog"
            with mock.patch.object(
                catalog_satellite.urllib.request,
                "urlopen",
                side_effect=[baseline, current],
            ), self.assertRaises(catalog_satellite.CatalogResponseTooLarge):
                catalog_satellite.main(
                    [*_catalog_arguments(output), "--max-response-bytes", "4"]
                )
            self.assertFalse(output.exists())
        self.assertTrue(baseline.closed)
        self.assertTrue(current.closed)


if __name__ == "__main__":
    unittest.main()
