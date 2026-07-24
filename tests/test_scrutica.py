from __future__ import annotations

from email.message import Message
import io
import json
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.models import Evidence, EvidenceKind
from datacenter_atlas.repository import add_evidence
from datacenter_atlas.release import build_release_documents
from datacenter_atlas.global_snapshot import validate_release_files
from datacenter_atlas.scrutica import (
    SCRUTICA_DATA_CENTER_SCOPE_POLICY,
    SCRUTICA_DIRECTORY_DIRECTION,
    SCRUTICA_DIRECTORY_SORT,
    SCRUTICA_DIRECTORY_URL,
    SCRUTICA_LICENSE,
    DirectorySpec,
    ScruticaAdapter,
    ScruticaFetcher,
    parse_directory_page,
    parse_mcp_facility_response,
    scrutica_data_center_scope,
    upstream_source_family,
)
from datacenter_atlas.scrutica_snapshot import (
    ScruticaSnapshotError,
    build_scrutica_snapshot,
    scrutica_release_readme,
)
from datacenter_atlas.service import validate_database


RETRIEVED_AT = "2026-07-18T20:00:00Z"
SPEC = DirectorySpec(tracked=4, browsable=3, aggregate_only=1, pages=2, page_size=2)


def _directory_html(page: int, ids: list[str]) -> bytes:
    links = "".join(f'<a href="/facilities/{facility_id}">{facility_id}</a>' for facility_id in ids)
    return (
        "<!doctype html><html><body>"
        "<span>1–2</span><span>of</span><span>3</span>"
        "<span>(4 tracked; 1 licensed-source rows in aggregates only)</span>"
        f"<span>Page {page} of 2</span>{links}"
        "<script>throw new Error('must not execute')</script>"
        "</body></html>"
    ).encode()


def _facility_document(facility_id: str, **overrides: object) -> dict[str, object]:
    facility: dict[str, object] = {
        "id": facility_id,
        "name": facility_id.replace("fac-", "").title(),
        "country": "United States",
        "region": "North America",
        "state": "Virginia",
        "county": "Loudoun County",
        "city": "Ashburn",
        "lat": 39.0,
        "lng": -77.5,
        "facility_type": "ai_training",
        "status": "operational",
        "announced_date": "2024-01-01",
        "construction_start_date": "2024-04-01",
        "expected_operational_date": "2025-01-01",
        "actual_operational_date": "2025-02-01",
        "power_capacity_mw": 100.0,
        "it_load_mw": 75.0,
        "pue": 1.2,
        "energy_profile": {"renewable_pct": 40, "grid_region": "PJM"},
        "water_usage_mgd": 0.6,
        "water_source": "municipal",
        "owner_name": "Example Owner",
        "operator_name": "Example Operator",
        "data_source": "epoch-gpu-clusters",
        "source_url": "https://example.com/upstream",
        "is_estimated": False,
        "estimation_method": None,
        "authority_tier": "secondary",
        "data_vintage": "2026-07-15",
        "credibility": 0.8,
    }
    facility.update(overrides)
    return {
        "facility": facility,
        "data_quality_flags": [],
        "url": f"{SCRUTICA_DIRECTORY_URL}/{facility_id}",
        "note": "Full provenance available in facility.data_source and source_url.",
    }


def _sse(facility_id: str, document: dict[str, object] | None = None, *, request_id: str | None = None) -> bytes:
    document = document or _facility_document(facility_id)
    envelope = {
        "jsonrpc": "2.0",
        "id": request_id or f"scrutica-facility:{facility_id}",
        "result": {"content": [{"type": "text", "text": json.dumps(document)}]},
    }
    return ("event: message\ndata: " + json.dumps(envelope) + "\n\n").encode()


class _Response(io.BytesIO):
    def __init__(self, raw: bytes, url: str) -> None:
        super().__init__(raw)
        self.url = url

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
    def __init__(self, documents: dict[str, dict[str, object]], *, rate_limit_once: str | None = None) -> None:
        self.documents = documents
        self.rate_limit_once = rate_limit_once
        self.rate_limited = False
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def __call__(self, request: object, *, timeout: float) -> _Response:
        url = request.full_url
        method = request.get_method()
        headers = {key.casefold(): value for key, value in request.header_items()}
        self.calls.append((method, url, headers))
        if method == "GET":
            parsed = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qs(
                parsed.query, keep_blank_values=True, strict_parsing=True
            )
            expected_query = {
                "sort": [SCRUTICA_DIRECTORY_SORT],
                "dir": [SCRUTICA_DIRECTORY_DIRECTION],
            }
            if {key: value for key, value in query.items() if key != "page"} != expected_query:
                raise AssertionError(f"unexpected Scrutica directory ordering: {query}")
            if len(query.get("page", [])) != 1:
                raise AssertionError(f"unexpected Scrutica page query: {query}")
            page = int(query["page"][0])
            if page not in {1, 2}:
                raise AssertionError(f"unexpected Scrutica page: {page}")
            ids = ["fac-one", "fac-two"] if page == 1 else ["fac-three"]
            return _Response(_directory_html(page, ids), url)
        payload = json.loads(request.data)
        facility_id = payload["params"]["arguments"]["facility_id"]
        if facility_id == self.rate_limit_once and not self.rate_limited:
            self.rate_limited = True
            headers_message = Message()
            headers_message["Retry-After"] = "3"
            raise urllib.error.HTTPError(
                url, 429, "Too Many Requests", headers_message, io.BytesIO(b"")
            )
        return _Response(_sse(facility_id, self.documents[facility_id]), url)


class _BrokenFacilityOpener(_Opener):
    def __call__(self, request: object, *, timeout: float) -> _Response:
        if request.get_method() == "POST":
            url = request.full_url
            headers = {
                key.casefold(): value for key, value in request.header_items()
            }
            self.calls.append(("POST", url, headers))
            return _Response(b"event: message\ndata: {}\n\n", url)
        return super().__call__(request, timeout=timeout)


def _documents() -> dict[str, dict[str, object]]:
    return {
        "fac-one": _facility_document("fac-one"),
        "fac-two": _facility_document(
            "fac-two",
            facility_type="colocation",
            status="Operational",
            is_estimated=True,
            data_source="IM3 / OpenStreetMap",
            power_capacity_mw=60,
            it_load_mw=None,
            pue=None,
        ),
        "fac-three": _facility_document(
            "fac-three",
            facility_type="hyperscale_dc",
            status="expanding",
            data_source="PDB-facilities",
            power_capacity_mw=None,
            it_load_mw=None,
            pue=None,
        ),
    }


def _fetch_bundle(
    path: Path,
    *,
    max_requests: int | None = None,
    documents: dict[str, dict[str, object]] | None = None,
) -> tuple[dict[str, object], _Opener, _Clock]:
    opener = _Opener(documents if documents is not None else _documents())
    clock = _Clock()
    fetcher = ScruticaFetcher(
        spec=SPEC,
        opener=opener,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        timestamp=lambda: "2026-07-18T19:00:00Z",
    )
    manifest = fetcher.fetch(path, max_requests=max_requests)
    return manifest, opener, clock


class ScruticaParsingTests(unittest.TestCase):
    def test_data_center_scope_uses_the_exact_official_type_taxonomy(self) -> None:
        for facility_type in (
            "ai_training",
            "colocation",
            "edge",
            "hpc_center",
            "hyperscale_dc",
        ):
            self.assertEqual(scrutica_data_center_scope(facility_type), "in_scope")
        for facility_type in ("logic_fab", "memory_fab", "packaging"):
            self.assertEqual(scrutica_data_center_scope(facility_type), "out_of_scope")
        self.assertEqual(scrutica_data_center_scope("other"), "review_required")
        self.assertEqual(scrutica_data_center_scope("Colocation"), "unknown_type")
        self.assertEqual(scrutica_data_center_scope("future_type"), "unknown_type")
        self.assertEqual(scrutica_data_center_scope(None), "unknown_type")

    def test_directory_parser_proves_counts_page_and_unique_ids(self) -> None:
        page = parse_directory_page(
            _directory_html(1, ["fac-one", "fac-two"]), expected_page=1
        )
        self.assertEqual((page.tracked, page.browsable, page.aggregate_only), (4, 3, 1))
        self.assertEqual(page.facility_ids, ("fac-one", "fac-two"))
        mixed_case = parse_directory_page(
            _directory_html(1, ["gridstatus-ercot-25INR0688", "fac-two"]),
            expected_page=1,
        )
        self.assertEqual(
            mixed_case.facility_ids,
            ("gridstatus-ercot-25INR0688", "fac-two"),
        )
        with self.assertRaisesRegex(ValueError, "repeats a facility"):
            parse_directory_page(
                _directory_html(1, ["fac-one", "fac-one"]), expected_page=1
            )
        with self.assertRaisesRegex(ValueError, "expected 2"):
            parse_directory_page(_directory_html(1, ["fac-one"]), expected_page=2)

    def test_sse_parser_validates_jsonrpc_request_and_facility_ids(self) -> None:
        parsed = parse_mcp_facility_response(
            _sse("fac-one"), request_id="scrutica-facility:fac-one", facility_id="fac-one"
        )
        self.assertEqual(parsed["facility"]["id"], "fac-one")
        with self.assertRaisesRegex(ValueError, "response ID"):
            parse_mcp_facility_response(
                _sse("fac-one", request_id="wrong"),
                request_id="scrutica-facility:fac-one",
                facility_id="fac-one",
            )
        wrong = _facility_document("fac-one")
        wrong["facility"]["id"] = "fac-two"
        with self.assertRaisesRegex(ValueError, "document ID"):
            parse_mcp_facility_response(
                _sse("fac-one", wrong),
                request_id="scrutica-facility:fac-one",
                facility_id="fac-one",
            )

        envelope = json.loads(_sse("fac-one").decode().split("data: ", 1)[1])
        envelope_text = json.dumps(envelope)
        comma = envelope_text.index(",") + 1
        multiline = (
            "event: message\ndata: "
            + envelope_text[:comma]
            + "\ndata: "
            + envelope_text[comma:]
            + "\n\n"
        ).encode()
        self.assertEqual(
            parse_mcp_facility_response(
                multiline,
                request_id="scrutica-facility:fac-one",
                facility_id="fac-one",
            )["facility"]["id"],
            "fac-one",
        )

    def test_dependency_root_mapping_is_conservative(self) -> None:
        self.assertEqual(upstream_source_family("epoch-gpu-clusters"), "epoch_ai")
        self.assertEqual(upstream_source_family("IM3 / OSM"), "openstreetmap")
        self.assertEqual(upstream_source_family("PDB facilities"), "peeringdb")
        self.assertEqual(upstream_source_family("gridstatus-NYISO"), "gridstatus")
        self.assertEqual(upstream_source_family("Press Reporting"), "press_reporting")
        self.assertEqual(upstream_source_family(None), "unknown")


class ScruticaFetcherTests(unittest.TestCase):
    def test_fetch_checkpoints_raw_bytes_hashes_rate_limit_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            manifest, opener, clock = _fetch_bundle(bundle, max_requests=1)
            self.assertEqual(manifest["state"], "incomplete")
            self.assertEqual(manifest["summary"]["directory_pages_completed"], 2)
            self.assertEqual(manifest["summary"]["records_completed"], 1)
            self.assertEqual(
                manifest["directory"]["ordering"],
                {"sort": "name", "dir": "asc"},
            )
            self.assertEqual(len(list((bundle / "directory").glob("*.html"))), 2)
            self.assertEqual(len(list((bundle / "records").glob("*.sse"))), 1)
            self.assertEqual(len(list((bundle / "records").glob("*.json"))), 1)
            self.assertFalse(
                any("authorization" in headers for _, _, headers in opener.calls)
            )
            post_headers = next(headers for method, _, headers in opener.calls if method == "POST")
            self.assertEqual(post_headers["mcp-protocol-version"], "2025-11-25")

            fetcher = ScruticaFetcher(
                spec=SPEC,
                opener=opener,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
                timestamp=lambda: "2026-07-18T19:05:00Z",
            )
            completed = fetcher.fetch(bundle, max_requests=2)
            self.assertEqual(completed["state"], "completed")
            self.assertEqual(completed["summary"]["records_completed"], 3)
            get_calls = [call for call in opener.calls if call[0] == "GET"]
            self.assertEqual(len(get_calls), 2, "resume must not refetch directory pages")
            for page, (_, url, _) in enumerate(get_calls, start=1):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                self.assertEqual(
                    query,
                    {"sort": ["name"], "dir": ["asc"], "page": [str(page)]},
                )
            self.assertTrue(clock.sleeps)
            self.assertTrue(all(seconds >= 1.1 - 1e-9 for seconds in clock.sleeps))

    def test_resume_rejects_a_different_directory_ordering_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            manifest, _, _ = _fetch_bundle(bundle, max_requests=0)
            manifest["directory"]["ordering"]["dir"] = "desc"
            (bundle / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            clock = _Clock()
            with self.assertRaisesRegex(ValueError, "ordering contract"):
                ScruticaFetcher(
                    spec=SPEC,
                    opener=_Opener(_documents()),
                    sleep=clock.sleep,
                    monotonic=clock.monotonic,
                    timestamp=lambda: "2026-07-18T19:05:00Z",
                ).fetch(bundle, max_requests=0)

    def test_429_retry_after_is_honored_and_attempts_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            opener = _Opener(_documents(), rate_limit_once="fac-one")
            clock = _Clock()
            manifest = ScruticaFetcher(
                spec=SPEC,
                opener=opener,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
                timestamp=lambda: "2026-07-18T19:00:00Z",
                max_attempts=2,
            ).fetch(temporary, max_requests=2)
            self.assertEqual(manifest["records"]["fac-one"]["state"], "completed")
            self.assertEqual(manifest["records"]["fac-one"]["attempts"], 2)
            self.assertGreaterEqual(max(clock.sleeps), 3.0)
            self.assertEqual(manifest["last_run"]["mcp_requests_made"], 2)

    def test_permanent_failures_trip_the_facility_circuit_breaker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            opener = _BrokenFacilityOpener(_documents())
            clock = _Clock()
            manifest = ScruticaFetcher(
                spec=SPEC,
                opener=opener,
                sleep=clock.sleep,
                monotonic=clock.monotonic,
                timestamp=lambda: "2026-07-18T19:00:00Z",
            ).fetch(temporary, max_requests=10, max_failures=1)
            self.assertEqual(manifest["records"]["fac-one"]["state"], "failed")
            self.assertEqual(manifest["summary"]["records_failed"], 1)
            self.assertEqual(manifest["summary"]["records_pending"], 2)
            self.assertEqual(manifest["last_run"]["mcp_requests_made"], 1)


class ScruticaAdapterTests(unittest.TestCase):
    def test_complete_import_is_source_scoped_conservative_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _fetch_bundle(bundle)
            connection, _ = initialize(":memory:")
            try:
                result = ScruticaAdapter(spec=SPEC).import_file(
                    connection, bundle, retrieved_at=RETRIEVED_AT
                )
                self.assertEqual(result.examined_elements, 3)
                self.assertEqual(result.imported_elements, 3)
                self.assertEqual(result.skipped_elements, 0)
                self.assertEqual(result.entities_created, 3)
                self.assertEqual(result.evidence_created, 3)
                self.assertIn("examined 3 completed records", result.warnings[0])
                self.assertIn("excluded 0", result.warnings[0])
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM facilities").fetchone()[0], 3
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM campuses").fetchone()[0], 0
                )
                evidence = connection.execute(
                    "SELECT * FROM evidence WHERE source_url LIKE '%/fac-one'"
                ).fetchone()
                self.assertEqual(evidence["license"], SCRUTICA_LICENSE)
                self.assertEqual(evidence["source_family"], "scrutica")
                metadata = json.loads(evidence["metadata_json"])
                self.assertFalse(metadata["independent_corroboration"])
                self.assertEqual(metadata["upstream_source_family"], "epoch_ai")
                scope = metadata["datacenter_atlas_scope"]
                self.assertEqual(scope["policy"], SCRUTICA_DATA_CENTER_SCOPE_POLICY)
                self.assertEqual(scope["classification"], "in_scope")
                self.assertEqual(scope["completed_records_examined"], 3)
                self.assertEqual(scope["records_imported"], 3)
                self.assertEqual(scope["records_excluded"], 0)
                self.assertTrue(scope["raw_fetch_bundle_unchanged"])
                self.assertFalse(scope["name_or_description_inference"])
                self.assertEqual(
                    metadata["provenance"]["datacenter_atlas_scope"], scope
                )
                tags = json.loads(
                    connection.execute(
                        "SELECT tags_json FROM entity_snapshots "
                        "JOIN entities ON entities.id = entity_snapshots.entity_id "
                        "WHERE entities.stable_key = 'scrutica:fac-one'"
                    ).fetchone()[0]
                )
                self.assertEqual(tags["datacenter_atlas:scope"], "data_center")
                self.assertEqual(
                    tags["datacenter_atlas:scope_policy"],
                    SCRUTICA_DATA_CENTER_SCOPE_POLICY,
                )
                self.assertEqual(
                    metadata["scrutica_facility"]["energy_profile"]["grid_region"], "PJM"
                )
                self.assertEqual(metadata["scrutica_facility"]["water_usage_mgd"], 0.6)
                capacities = connection.execute(
                    "SELECT metric, stage, method, base FROM capacity_estimates ORDER BY metric"
                ).fetchall()
                self.assertEqual(len(capacities), 4)
                self.assertEqual({row["stage"] for row in capacities}, {"unknown"})
                one_methods = connection.execute(
                    """
                    SELECT capacity_estimates.method
                    FROM capacity_estimates
                    JOIN entities ON entities.id = capacity_estimates.entity_id
                    WHERE entities.stable_key = 'scrutica:fac-one'
                    """
                ).fetchall()
                self.assertEqual({row[0] for row in one_methods}, {"reported"})
                self.assertEqual(
                    connection.execute(
                        "SELECT status FROM lifecycle_observations "
                        "JOIN entities ON entities.id = lifecycle_observations.entity_id "
                        "WHERE entities.stable_key = 'scrutica:fac-two'"
                    ).fetchone()[0],
                    "unknown",
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM workload_observations"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM operating_model_observations "
                        "JOIN entities ON entities.id = operating_model_observations.entity_id "
                        "WHERE entities.stable_key = 'scrutica:fac-three'"
                    ).fetchone()[0],
                    0,
                    "hyperscale_dc must not infer a hyperscaler operating model",
                )
                second = ScruticaAdapter(spec=SPEC).import_file(
                    connection, bundle, retrieved_at=RETRIEVED_AT
                )
                self.assertEqual((second.entities_created, second.evidence_created), (0, 0))
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_partial_import_requires_explicit_flag_and_is_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _fetch_bundle(bundle, max_requests=1)
            connection, _ = initialize(":memory:")
            try:
                with self.assertRaisesRegex(ValueError, "bundle is incomplete"):
                    ScruticaAdapter(spec=SPEC).import_file(
                        connection, bundle, retrieved_at=RETRIEVED_AT
                    )
                result = ScruticaAdapter(spec=SPEC).import_file(
                    connection,
                    bundle,
                    retrieved_at=RETRIEVED_AT,
                    allow_partial=True,
                )
                self.assertEqual(result.imported_elements, 1)
                self.assertEqual(result.examined_elements, 1)
                self.assertEqual(result.skipped_elements, 0)
                self.assertIn("PARTIAL SCRUTICA", result.warnings[0])
                self.assertIn("examined 1 completed records", result.warnings[1])
                self.assertIn("excluded 0", result.warnings[1])
            finally:
                connection.close()

    def test_strict_scope_excludes_non_dc_and_review_records_without_mutating_bundle(
        self,
    ) -> None:
        documents = {
            "fac-one": _facility_document("fac-one", facility_type="logic_fab"),
            "fac-two": _facility_document("fac-two", facility_type="other"),
            "fac-three": _facility_document(
                "fac-three", facility_type="colocation"
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _fetch_bundle(bundle, documents=documents)
            manifest_before = (bundle / "manifest.json").read_bytes()
            record_files_before = sorted(
                path.relative_to(bundle).as_posix()
                for path in (bundle / "records").iterdir()
            )
            connection, _ = initialize(":memory:")
            try:
                result = ScruticaAdapter(spec=SPEC).import_file(
                    connection, bundle, retrieved_at=RETRIEVED_AT
                )
                self.assertEqual(result.examined_elements, 3)
                self.assertEqual(result.imported_elements, 1)
                self.assertEqual(result.skipped_elements, 2)
                self.assertEqual(result.entities_created, 1)
                self.assertEqual(result.evidence_created, 1)
                self.assertIn("logic_fab=1", result.warnings[0])
                self.assertIn("other=1", result.warnings[0])

                stable_keys = {
                    row[0]
                    for row in connection.execute(
                        "SELECT stable_key FROM entities ORDER BY stable_key"
                    )
                }
                self.assertEqual(stable_keys, {"scrutica:fac-three"})
                evidence = connection.execute("SELECT * FROM evidence").fetchone()
                metadata = json.loads(evidence["metadata_json"])
                scope = metadata["datacenter_atlas_scope"]
                self.assertEqual(
                    scope["excluded_by_facility_type"],
                    {"logic_fab": 1, "other": 1},
                )
                self.assertEqual(
                    scope["excluded_by_scope"],
                    {"out_of_scope": 1, "review_required": 1},
                )

                documents_out = build_release_documents(
                    connection,
                    as_of="2026-07-18",
                    recorded_at=RETRIEVED_AT,
                )
                geojson = json.loads(documents_out["atlas.geojson"])
                self.assertEqual(len(geojson["features"]), 1)
                self.assertIn("Three", documents_out["entities.csv"])
                self.assertNotIn("One", documents_out["entities.csv"])
                self.assertNotIn("Two", documents_out["entities.csv"])
                source_inputs = json.loads(documents_out["source_inputs.json"])[
                    "sources"
                ]
                self.assertEqual(len(source_inputs), 1)
                self.assertEqual(
                    source_inputs[0]["provenance"]["datacenter_atlas_scope"],
                    scope,
                )
            finally:
                connection.close()

            self.assertEqual((bundle / "manifest.json").read_bytes(), manifest_before)
            self.assertEqual(
                sorted(
                    path.relative_to(bundle).as_posix()
                    for path in (bundle / "records").iterdir()
                ),
                record_files_before,
            )
            self.assertEqual(len(record_files_before), 6)

    def test_import_refuses_database_containing_another_source_family(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _fetch_bundle(bundle)
            connection, _ = initialize(":memory:")
            try:
                with connection:
                    add_evidence(
                        connection,
                        Evidence(
                            id="other-evidence",
                            kind=EvidenceKind.OTHER,
                            title="Other source",
                            source_url="https://example.com",
                            retrieved_at=RETRIEVED_AT,
                            source_family="openstreetmap",
                        ),
                    )
                with self.assertRaisesRegex(ValueError, "separate CC-BY-SA database"):
                    ScruticaAdapter(spec=SPEC).import_file(
                        connection, bundle, retrieved_at=RETRIEVED_AT
                    )
            finally:
                connection.close()

    def test_import_detects_tampered_raw_directory_page(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _fetch_bundle(bundle)
            page = bundle / "directory" / "page-001.html"
            page.write_bytes(page.read_bytes() + b"\n")
            connection, _ = initialize(":memory:")
            try:
                with self.assertRaisesRegex(ValueError, "page 1 hash"):
                    ScruticaAdapter(spec=SPEC).import_file(
                        connection, bundle, retrieved_at=RETRIEVED_AT
                    )
            finally:
                connection.close()

    def test_combined_release_is_refused_even_if_another_source_is_added_later(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            _fetch_bundle(bundle)
            connection, _ = initialize(":memory:")
            try:
                ScruticaAdapter(spec=SPEC).import_file(
                    connection, bundle, retrieved_at=RETRIEVED_AT
                )
                with connection:
                    add_evidence(
                        connection,
                        Evidence(
                            id="later-other-evidence",
                            kind=EvidenceKind.OTHER,
                            title="Later other source",
                            source_url="https://example.com/later",
                            retrieved_at=RETRIEVED_AT,
                            source_family="openstreetmap",
                        ),
                    )
                with self.assertRaisesRegex(ValueError, "requires a separate release"):
                    build_release_documents(
                        connection,
                        as_of="2026-07-18",
                        recorded_at=RETRIEVED_AT,
                    )
            finally:
                connection.close()


class ScruticaSnapshotTests(unittest.TestCase):
    def test_builder_canonicalizes_equivalent_recorded_at_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            _fetch_bundle(bundle)
            output = root / "release"
            build_scrutica_snapshot(
                source_bundle=bundle,
                output_directory=output,
                as_of="2026-07-18",
                recorded_at="2026-07-18T21:00:00.000+01:00",
                retrieved_at=RETRIEVED_AT,
                directory_spec=SPEC,
                expected_imported_records=3,
                expected_excluded_by_facility_type={},
            )
            manifest = validate_release_files(output)
            self.assertEqual(manifest["recorded_at"], RETRIEVED_AT)

    def test_atomic_release_preserves_source_bundle_and_review_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            _fetch_bundle(bundle)
            source_before = {
                path.relative_to(bundle): path.read_bytes()
                for path in bundle.rglob("*")
                if path.is_file()
            }
            output = root / "release"
            result = build_scrutica_snapshot(
                source_bundle=bundle,
                output_directory=output,
                as_of="2026-07-18",
                recorded_at=RETRIEVED_AT,
                retrieved_at=RETRIEVED_AT,
                directory_spec=SPEC,
                expected_imported_records=3,
                expected_excluded_by_facility_type={},
            )
            manifest = validate_release_files(output)
            self.assertTrue(result["review_only"])
            self.assertTrue(manifest["review_only"])
            self.assertEqual(manifest["entities"], 3)
            self.assertEqual(manifest["source_families"], ["scrutica"])
            self.assertIn("atlas.sqlite", manifest["files"])
            self.assertIn("atlas.html", manifest["files"])
            self.assertIn("source_fetch_manifest.json", manifest["files"])
            self.assertEqual(
                (output / "source_fetch_manifest.json").read_bytes(),
                (bundle / "manifest.json").read_bytes(),
            )
            self.assertEqual(
                source_before,
                {
                    path.relative_to(bundle): path.read_bytes()
                    for path in bundle.rglob("*")
                    if path.is_file()
                },
            )
            self.assertEqual(list(root.glob(".release.stage-*")), [])

    def test_incomplete_or_count_mismatched_source_never_publishes(self) -> None:
        for case in ("incomplete", "count mismatch"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundle = root / "bundle"
                _fetch_bundle(bundle, max_requests=1 if case == "incomplete" else None)
                output = root / "release"
                arguments = {
                    "source_bundle": bundle,
                    "output_directory": output,
                    "as_of": "2026-07-18",
                    "recorded_at": RETRIEVED_AT,
                    "retrieved_at": RETRIEVED_AT,
                    "directory_spec": SPEC,
                    "expected_imported_records": 3,
                    "expected_excluded_by_facility_type": {},
                }
                if case == "count mismatch":
                    arguments["expected_imported_records"] = 2
                    arguments["expected_excluded_by_facility_type"] = {"other": 1}
                with self.assertRaises(ScruticaSnapshotError):
                    build_scrutica_snapshot(**arguments)
                self.assertFalse(output.exists())
                self.assertEqual(list(root.glob(".release.stage-*")), [])

    def test_release_readme_is_explicit_about_candidate_and_capacity_limits(self) -> None:
        readme = scrutica_release_readme(
            as_of="2026-07-18",
            summary={"entities_by_status": {"operational": 2, "unknown": 1}},
            examined_records=3,
            imported_records=2,
            excluded_by_facility_type={"other": 1},
        )
        self.assertIn("source-scoped and review-only", readme)
        self.assertIn("not a count of unique physical sites", readme)
        self.assertIn("no annual energy consumption is derived", readme)


if __name__ == "__main__":
    unittest.main()
