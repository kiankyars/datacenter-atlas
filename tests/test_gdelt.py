from __future__ import annotations

import gzip
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

from datacenter_atlas.gdelt import (
    CANDIDATES_FILENAME,
    GDELTSnapshotFetcher,
    GDELTValidationError,
    REVIEW_CONSTRAINTS,
    SnapshotFile,
    SnapshotSpec,
    build_candidate_bundle,
    validate_candidate_bundle,
    validate_source_bundle,
    write_candidate_bundle,
)


SNAPSHOT_ID = "20260718000000"
RUN_AT = "2026-07-18T01:00:00Z"


def _gzip(raw: bytes) -> bytes:
    return gzip.compress(raw, mtime=0)


def _md5(raw: bytes) -> str:
    return hashlib.md5(raw, usedforsecurity=False).hexdigest()


def _fixture() -> tuple[SnapshotSpec, dict[str, bytes]]:
    toc_raw = b"".join(
        (
            json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
        for record in (
            {
                "ID": 1,
                "date": "2026-07-18T00:00:00.000Z",
                "img": "",
                "lang": "en",
                "title": "New data center project enters planning",
                "url": "https://news.example.co.uk/articles/one",
            },
            {
                "ID": 2,
                "date": "2026-07-18T00:00:00.000Z",
                "img": "https://example.es/two.jpg",
                "lang": "es",
                "title": "Tecnología regional",
                "url": "https://example.es/noticias/dos",
            },
            {
                "ID": 3,
                "date": "2026-07-18T00:00:00.000Z",
                "img": "",
                "lang": "en",
                "title": "Data center services update",
                "url": "https://example.com/three",
            },
        )
    )
    ngram_raw = (
        "1\tnew data center project\t2\n"
        "1\tplanning for next year\t1\n"
        "2\tnuevo centro de datos\t3\n"
        "2\tatrae inversión regional hoy\t1\n"
        "3\tdata center services update\t1\n"
        "3\tcloud operations continue normally\t1\n"
    ).encode("utf-8")
    ngrams = _gzip(ngram_raw)
    toc = _gzip(toc_raw)
    files = {
        f"{SNAPSHOT_ID}.ngrams.txt.gz": ngrams,
        f"{SNAPSHOT_ID}.toc.json.gz": toc,
    }
    spec = SnapshotSpec(
        SNAPSHOT_ID,
        SnapshotFile(
            f"{SNAPSHOT_ID}.ngrams.txt.gz",
            "1001",
            len(ngrams),
            _md5(ngrams),
        ),
        SnapshotFile(
            f"{SNAPSHOT_ID}.toc.json.gz",
            "1002",
            len(toc),
            _md5(toc),
        ),
    )
    return spec, files


class _Response(io.BytesIO):
    def __init__(
        self,
        raw: bytes,
        url: str,
        *,
        status: int,
        generation: str,
        md5: str,
        content_range: str | None = None,
    ) -> None:
        super().__init__(raw)
        self.url = url
        self.status = status
        self.headers = {
            "x-goog-generation": generation,
            "ETag": f'"{md5}"',
        }
        if content_range is not None:
            self.headers["Content-Range"] = content_range

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def geturl(self) -> str:
        return self.url


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class _Opener:
    def __init__(
        self,
        spec: SnapshotSpec,
        files: dict[str, bytes],
        *,
        truncate_first: bool = False,
        wrong_etag: bool = False,
    ) -> None:
        self.spec = spec
        self.files = files
        self.truncate_first = truncate_first
        self.wrong_etag = wrong_etag
        self.calls: list[dict[str, object]] = []

    def __call__(self, request: object, *, timeout: float) -> _Response:
        parsed = urllib.parse.urlsplit(request.full_url)
        filename = Path(parsed.path).name
        raw = self.files[filename]
        item = next(item for item in self.spec.files if item.filename == filename)
        range_header = request.get_header("Range")
        self.calls.append(
            {
                "url": request.full_url,
                "range": range_header,
                "user_agent": request.get_header("User-agent"),
            }
        )
        if self.truncate_first and len(self.calls) == 1 and range_header is None:
            raw = raw[: len(raw) // 2]
        offset = int(range_header.removeprefix("bytes=").removesuffix("-")) if range_header else 0
        if range_header:
            raw = raw[offset:]
            status = 206
            content_range = f"bytes {offset}-{item.bytes - 1}/{item.bytes}"
        else:
            status = 200
            content_range = None
        md5 = "0" * 32 if self.wrong_etag else item.md5
        return _Response(
            raw,
            request.full_url,
            status=status,
            generation=item.generation,
            md5=md5,
            content_range=content_range,
        )


def _complete_source(path: Path) -> tuple[SnapshotSpec, _Opener]:
    spec, files = _fixture()
    opener = _Opener(spec, files)
    clock = _Clock()
    manifest = GDELTSnapshotFetcher(
        spec=spec,
        opener=opener,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        timestamp=lambda: RUN_AT,
    ).fetch(path, max_requests=2)
    if manifest["state"] != "completed":
        raise AssertionError("fixture source did not complete")
    return spec, opener


def _write_candidate_manifest(path: Path, document: dict[str, object]) -> None:
    raw = (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    (path / "manifest.json").write_bytes(raw)
    (path / "manifest.sha256").write_text(
        f"{hashlib.sha256(raw).hexdigest()}  manifest.json\n"
    )


class GDELTFetchTests(unittest.TestCase):
    def test_fetch_is_hash_pinned_low_rate_and_resumes_a_partial(self) -> None:
        spec, files = _fixture()
        opener = _Opener(spec, files, truncate_first=True)
        clock = _Clock()
        fetcher = GDELTSnapshotFetcher(
            spec=spec,
            opener=opener,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            timestamp=lambda: RUN_AT,
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            partial = fetcher.fetch(output, max_requests=1)
            self.assertEqual(partial["state"], "incomplete")
            self.assertEqual(partial["last_run"]["requests_made"], 1)
            self.assertEqual(
                partial["files"][spec.ngrams.filename]["state"], "pending"
            )
            self.assertTrue((output / f".{spec.ngrams.filename}.partial").is_file())

            completed = fetcher.fetch(output, max_requests=2)
            self.assertEqual(completed["state"], "completed")
            self.assertEqual(completed["summary"]["files_completed"], 2)
            self.assertEqual(opener.calls[1]["range"], f"bytes={len(files[spec.ngrams.filename]) // 2}-")
            self.assertTrue(
                all(call["user_agent"] for call in opener.calls),
                "every raw request needs a transparent User-Agent",
            )
            self.assertTrue(clock.sleeps)
            self.assertTrue(all(seconds >= 1.1 - 1e-9 for seconds in clock.sleeps))
            validate_source_bundle(output, spec)

            calls_before = len(opener.calls)
            no_op = fetcher.fetch(output, max_requests=2)
            self.assertEqual(no_op, completed)
            self.assertEqual(len(opener.calls), calls_before)

    def test_generation_or_integrity_drift_fails_closed(self) -> None:
        spec, files = _fixture()
        opener = _Opener(spec, files, wrong_etag=True)
        with tempfile.TemporaryDirectory() as temporary:
            manifest = GDELTSnapshotFetcher(
                spec=spec,
                opener=opener,
                sleep=lambda _: None,
                monotonic=lambda: 0.0,
                timestamp=lambda: RUN_AT,
            ).fetch(temporary, max_requests=1)
            self.assertEqual(
                manifest["files"][spec.ngrams.filename]["state"], "failed"
            )
            self.assertIn("ETag", manifest["files"][spec.ngrams.filename]["failures"][0]["error"])

    def test_nontransient_http_error_fails_instead_of_retrying(self) -> None:
        spec, _ = _fixture()

        def not_found(request: object, *, timeout: float) -> object:
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                "not found",
                {},
                None,
            )

        with tempfile.TemporaryDirectory() as temporary:
            manifest = GDELTSnapshotFetcher(
                spec=spec,
                opener=not_found,
                sleep=lambda _: None,
                monotonic=lambda: 0.0,
                timestamp=lambda: RUN_AT,
            ).fetch(temporary, max_requests=1)
        task = manifest["files"][spec.ngrams.filename]
        self.assertEqual(task["state"], "failed")
        self.assertEqual(task["attempts"], 1)
        self.assertIn("HTTP Error 404", task["failures"][0]["error"])


class GDELTExtractionTests(unittest.TestCase):
    def test_multilingual_matches_are_deterministic_and_review_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "candidates"
            spec, _ = _complete_source(source)
            first = build_candidate_bundle(source, generated_at=RUN_AT, spec=spec)
            second = build_candidate_bundle(source, generated_at=RUN_AT, spec=spec)
            self.assertEqual(first[:3], second[:3])
            records = [json.loads(line) for line in first[0].splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                [record["article"]["language"] for record in records], ["en", "es"]
            )
            self.assertEqual(
                records[0]["location_hints"],
                [
                    {
                        "kind": "publisher_domain_cctld",
                        "value": "UK",
                        "scope": "publisher_domain_only_not_article_or_facility_location",
                    }
                ],
            )
            for record in records:
                self.assertEqual(record["review_constraints"], REVIEW_CONSTRAINTS)
                self.assertTrue(record["lexical_match"]["subject_terms"])
                self.assertTrue(record["lexical_match"]["development_terms"])
                rendered = json.dumps(record).casefold()
                self.assertNotIn('"status":', rendered)
                self.assertNotIn('"power":', rendered)
                self.assertNotIn('"capacity":', rendered)

            manifest = write_candidate_bundle(
                source, output, generated_at=RUN_AT, spec=spec
            )
            self.assertEqual(manifest["counts"]["candidate_articles"], 2)
            self.assertEqual(validate_candidate_bundle(output), manifest)
            self.assertEqual(
                len((output / CANDIDATES_FILENAME).read_text().splitlines()), 2
            )
            with self.assertRaisesRegex(GDELTValidationError, "refusing existing"):
                write_candidate_bundle(source, output, generated_at=RUN_AT, spec=spec)

            changed = json.loads((output / "manifest.json").read_text())
            changed["counts"]["distinct_candidate_urls"] = 1
            _write_candidate_manifest(output, changed)
            with self.assertRaisesRegex(GDELTValidationError, "count"):
                validate_candidate_bundle(output)

    def test_source_tampering_stops_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            spec, _ = _complete_source(source)
            artifact = source / spec.ngrams.filename
            artifact.write_bytes(artifact.read_bytes() + b"\n")
            with self.assertRaisesRegex(GDELTValidationError, "hash"):
                build_candidate_bundle(source, generated_at=RUN_AT, spec=spec)

    def test_unknown_ngram_document_fails_instead_of_being_dropped(self) -> None:
        spec, files = _fixture()
        bad_raw = gzip.decompress(files[spec.ngrams.filename]) + b"4\tnew data center project\t1\n"
        bad_gzip = _gzip(bad_raw)
        files[spec.ngrams.filename] = bad_gzip
        spec = SnapshotSpec(
            spec.snapshot_id,
            SnapshotFile(spec.ngrams.filename, "1001", len(bad_gzip), _md5(bad_gzip)),
            spec.toc,
        )
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            opener = _Opener(spec, files)
            GDELTSnapshotFetcher(
                spec=spec,
                opener=opener,
                sleep=lambda _: None,
                monotonic=lambda: 0.0,
                timestamp=lambda: RUN_AT,
            ).fetch(source, max_requests=2)
            with self.assertRaisesRegex(GDELTValidationError, "unknown document"):
                build_candidate_bundle(source, generated_at=RUN_AT, spec=spec)

    def test_truncated_gzip_is_reported_as_a_validation_error(self) -> None:
        spec, files = _fixture()
        truncated = files[spec.ngrams.filename][:-4]
        files[spec.ngrams.filename] = truncated
        spec = SnapshotSpec(
            spec.snapshot_id,
            SnapshotFile(
                spec.ngrams.filename,
                spec.ngrams.generation,
                len(truncated),
                _md5(truncated),
            ),
            spec.toc,
        )
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            GDELTSnapshotFetcher(
                spec=spec,
                opener=_Opener(spec, files),
                sleep=lambda _: None,
                monotonic=lambda: 0.0,
                timestamp=lambda: RUN_AT,
            ).fetch(source, max_requests=2)
            with self.assertRaisesRegex(GDELTValidationError, "valid gzip"):
                build_candidate_bundle(source, generated_at=RUN_AT, spec=spec)


if __name__ == "__main__":
    unittest.main()
