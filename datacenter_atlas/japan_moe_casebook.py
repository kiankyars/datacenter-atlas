"""Deterministic Japan MOE data-centre decarbonization casebook lane.

This is a source-bound auxiliary lane.  It converts a frozen, page-scoped
transcription of the May 2026 MOE casebook into program, case, reconciliation,
and metric observations.  It does not identify unique physical sites or infer
construction/operating status, IT load, utility capacity, PUE, or electricity
consumption from subsidy participation, generation, or savings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "japan-moe-data-centre-decarbonization-casebook-2026-05-v1"
RELEASE_FORMAT = "datacenter-atlas-japan-moe-casebook-release-v1"
SOURCE_ARTIFACT_FORMAT = "datacenter-atlas-japan-moe-source-snapshot-v1"
SOURCE_ARTIFACT_MANIFEST_FORMAT = (
    "datacenter-atlas-japan-moe-source-artifact-manifest-v1"
)
RELEASE_MANIFEST_FORMAT = "datacenter-atlas-japan-moe-casebook-manifest-v1"
DEFINITION_FORMAT = "datacenter-atlas-japan-moe-casebook-definition-v1"
SCHEMA_FORMAT = "datacenter-atlas-japan-moe-casebook-schema-v1"
RETRIEVAL_FORMAT = "datacenter-atlas-japan-moe-retrieval-inventory-v1"

TERMS_URL = "https://www.env.go.jp/mail.html"
LANDING_URL = "https://www.env.go.jp/earth/earth/ondanka/data-center.html"
CASEBOOK_URL = "https://www.env.go.jp/content/000400242.pdf"
ALLOWED_SOURCE_URLS = {TERMS_URL, LANDING_URL, CASEBOOK_URL}

MIN_REQUEST_START_INTERVAL_SECONDS = 3.2
MAX_DIRECT_REQUEST_ATTEMPTS = 12
SOURCE_ARTIFACT_MANIFEST_SHA256 = (
    "ed1ee5ce555fd6fb51643c581d6d5b505605b9677ee2ce16eed4b827c5ceffd9"
)
SOURCE_ARTIFACT_TREE_SHA256 = (
    "a16880fdd487c86f5c707955286fce7d4c4963fc8c545ef063fcaff89c7b2629"
)

MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"
SOURCE_ARTIFACT_EXPECTED_FILES = {
    "ATTRIBUTION.txt",
    "README.md",
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    "retrieval-inventory.json",
    "source-snapshot.json",
}
RELEASE_EXPECTED_FILES = {
    "ATTRIBUTION.txt",
    "README.md",
    "assessment.json",
    "definition.json",
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    "metrics.jsonl",
    "observations.jsonl",
    "program-observations.jsonl",
    "reconciliation.json",
    "retrieval-inventory.json",
    "schema.json",
    "source-inventory.json",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_HASH_RE = re.compile(r"^([0-9a-f]{64})  manifest\.json\n$")
_FISCAL_YEAR_MAP = {"R3": 2021, "R4": 2022, "R5": 2023, "R6": 2024, "R7": 2025}
_METRIC_TYPES = {
    "co2_reduction",
    "energy_savings",
    "renewable_generation",
    "renewable_share",
}


class JapanMOECasebookError(ValueError):
    """Raised when the casebook artifact or release violates its contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def canonical_jsonl(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(
                row,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        for row in rows
    )


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _exact_keys(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise JapanMOECasebookError(f"{field} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise JapanMOECasebookError(
            f"{field} keys differ; missing={missing}, extra={extra}"
        )
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise JapanMOECasebookError(f"{field} must be an array")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise JapanMOECasebookError(f"{field} must be a non-empty string")
    return value


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JapanMOECasebookError(f"{field} must be numeric")
    return float(value)


def _official_url(value: Any, field: str) -> str:
    url = _string(value, field)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.env.go.jp"
        or url not in ALLOWED_SOURCE_URLS
    ):
        raise JapanMOECasebookError(
            f"{field} must be one of the three approved official URLs"
        )
    return url


def _parse_utc(value: Any, field: str) -> datetime:
    text = _string(value, field)
    if not text.endswith("Z"):
        raise JapanMOECasebookError(f"{field} must be an RFC 3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise JapanMOECasebookError(
            f"{field} must be an RFC 3339 UTC timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JapanMOECasebookError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JapanMOECasebookError(f"cannot parse {field}: {path}") from error
    if not isinstance(value, dict):
        raise JapanMOECasebookError(f"{field} must contain a JSON object")
    if path.read_bytes() != canonical_json(value):
        raise JapanMOECasebookError(f"{field} must use canonical JSON encoding")
    return value


def _read_jsonl(path: Path, field: str) -> list[dict[str, Any]]:
    try:
        body = path.read_bytes()
        text = body.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise JapanMOECasebookError(f"cannot read {field}: {path}") from error
    rows: list[dict[str, Any]] = []
    if text:
        if not text.endswith("\n"):
            raise JapanMOECasebookError(f"{field} must end with a newline")
        for number, line in enumerate(text.splitlines(), start=1):
            if not line:
                raise JapanMOECasebookError(f"{field} has blank line {number}")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise JapanMOECasebookError(
                    f"{field} line {number} is not JSON"
                ) from error
            if not isinstance(row, dict):
                raise JapanMOECasebookError(
                    f"{field} line {number} must be an object"
                )
            rows.append(row)
    if body != canonical_jsonl(rows):
        raise JapanMOECasebookError(f"{field} must use canonical JSONL encoding")
    return rows


def _assert_exact_regular_files(root: Path, expected: set[str], field: str) -> None:
    if root.is_symlink() or not root.is_dir():
        raise JapanMOECasebookError(f"{field} must be a real directory")
    actual: set[str] = set()
    for entry in root.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise JapanMOECasebookError(
                f"{field} may contain only regular files: {entry.name}"
            )
        actual.add(entry.name)
    if actual != expected:
        raise JapanMOECasebookError(
            f"{field} files differ; missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )


def _manifest_document(
    *,
    identifier_key: str,
    identifier: str,
    manifest_format: str,
    payloads: Mapping[str, bytes],
) -> dict[str, Any]:
    files = [
        {
            "bytes": len(payloads[name]),
            "path": name,
            "sha256": sha256_bytes(payloads[name]),
        }
        for name in sorted(payloads)
    ]
    return {
        identifier_key: identifier,
        "files": files,
        "format": manifest_format,
        "tree_sha256": sha256_bytes(canonical_json(files)),
    }


def _validate_manifest(
    root: Path,
    *,
    expected_files: set[str],
    identifier_key: str,
    identifier: str,
    manifest_format: str,
) -> dict[str, Any]:
    payload_names = expected_files - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    payloads = {name: (root / name).read_bytes() for name in payload_names}
    expected = _manifest_document(
        identifier_key=identifier_key,
        identifier=identifier,
        manifest_format=manifest_format,
        payloads=payloads,
    )
    actual = _read_json(root / MANIFEST_FILENAME, "manifest")
    if actual != expected:
        raise JapanMOECasebookError("manifest does not match bundle payloads")
    manifest_body = canonical_json(actual)
    hash_body = (root / MANIFEST_HASH_FILENAME).read_text(encoding="ascii")
    match = _MANIFEST_HASH_RE.fullmatch(hash_body)
    if match is None or match.group(1) != sha256_bytes(manifest_body):
        raise JapanMOECasebookError("manifest.sha256 does not match manifest.json")
    return actual


def is_frozen_bundle(root: Path, expected_files: set[str]) -> bool:
    if root.is_symlink() or not root.is_dir():
        return False
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    try:
        entries = list(root.iterdir())
    except OSError:
        return False
    if {entry.name for entry in entries} != expected_files:
        return False
    return all(
        not entry.is_symlink()
        and entry.is_file()
        and stat.S_IMODE(entry.stat().st_mode) == 0o444
        for entry in entries
    )


def freeze_bundle(root: Path) -> None:
    for entry in root.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise JapanMOECasebookError("only regular files may be frozen")
        entry.chmod(0o444)
    root.chmod(0o555)


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for entry in root.iterdir():
        if entry.is_file() and not entry.is_symlink():
            entry.chmod(0o644)


_RETRIEVAL_KEYS = {
    "analysis_temporary_response_bodies_deleted",
    "browser_proxy_origin_request_count",
    "browser_proxy_research_excluded_from_direct_request_arithmetic",
    "browser_proxy_research_used",
    "completed_response_requests",
    "controlled_http_requests",
    "direct_request_attempt_cap",
    "direct_request_attempts",
    "failed_network_requests",
    "format",
    "minimum_request_start_interval_seconds",
    "raw_response_bodies_retained",
    "successful_http_200_requests",
    "third_party_requests",
}
_REQUEST_KEYS = {
    "body_retained",
    "bytes",
    "content_type",
    "elapsed_seconds",
    "http_status",
    "location",
    "method",
    "outcome",
    "redirect_followed",
    "request_id",
    "response_body_received",
    "sha256",
    "started_at",
    "url",
}


def validate_retrieval_inventory(value: Any) -> dict[str, Any]:
    inventory = _exact_keys(value, _RETRIEVAL_KEYS, "retrieval_inventory")
    if inventory["format"] != RETRIEVAL_FORMAT:
        raise JapanMOECasebookError("unexpected retrieval inventory format")
    rows = _list(inventory["controlled_http_requests"], "controlled_http_requests")
    if len(rows) != 3 or inventory["direct_request_attempts"] != 3:
        raise JapanMOECasebookError("direct request ledger must contain exactly 3 attempts")
    if inventory["direct_request_attempt_cap"] != MAX_DIRECT_REQUEST_ATTEMPTS:
        raise JapanMOECasebookError("direct request cap must remain 12")
    if inventory["minimum_request_start_interval_seconds"] != 3.2:
        raise JapanMOECasebookError("request start interval must remain 3.2 seconds")
    if inventory["direct_request_attempts"] > inventory["direct_request_attempt_cap"]:
        raise JapanMOECasebookError("direct request cap exceeded")
    if inventory["third_party_requests"] != 0:
        raise JapanMOECasebookError("third-party requests are not permitted")
    if inventory["raw_response_bodies_retained"]:
        raise JapanMOECasebookError("raw response bodies must not be retained")
    if not inventory["analysis_temporary_response_bodies_deleted"]:
        raise JapanMOECasebookError("temporary analysis bodies must be deleted")
    if not inventory["browser_proxy_research_used"]:
        raise JapanMOECasebookError("browser-proxy research disclosure is required")
    if inventory["browser_proxy_origin_request_count"] is not None:
        raise JapanMOECasebookError("unknown browser-proxy origin count must remain null")
    if not inventory["browser_proxy_research_excluded_from_direct_request_arithmetic"]:
        raise JapanMOECasebookError("proxy/direct request accounting must stay separate")
    expected_ids = ["moe_terms", "moe_landing", "moe_casebook"]
    expected_urls = [TERMS_URL, LANDING_URL, CASEBOOK_URL]
    starts: list[datetime] = []
    for index, raw in enumerate(rows):
        row = _exact_keys(raw, _REQUEST_KEYS, f"controlled_http_requests[{index}]")
        if row["request_id"] != expected_ids[index]:
            raise JapanMOECasebookError("request ledger order or ID changed")
        if _official_url(row["url"], f"request[{index}].url") != expected_urls[index]:
            raise JapanMOECasebookError("request URL order changed")
        if (
            row["method"] != "GET"
            or row["outcome"] != "response"
            or row["http_status"] != 200
            or row["redirect_followed"]
            or row["location"] is not None
            or not row["response_body_received"]
            or row["body_retained"]
        ):
            raise JapanMOECasebookError("request row violates bounded audit contract")
        if not isinstance(row["bytes"], int) or row["bytes"] <= 0:
            raise JapanMOECasebookError("request bytes must be positive")
        _number(row["elapsed_seconds"], f"request[{index}].elapsed_seconds")
        if not isinstance(row["sha256"], str) or not _SHA256_RE.fullmatch(row["sha256"]):
            raise JapanMOECasebookError("request sha256 must be lowercase hexadecimal")
        starts.append(_parse_utc(row["started_at"], f"request[{index}].started_at"))
    for before, after in zip(starts, starts[1:]):
        if (after - before).total_seconds() < MIN_REQUEST_START_INTERVAL_SECONDS:
            raise JapanMOECasebookError("request starts were not paced by at least 3.2 seconds")
    if inventory["completed_response_requests"] != 3:
        raise JapanMOECasebookError("completed response count must be 3")
    if inventory["successful_http_200_requests"] != 3:
        raise JapanMOECasebookError("successful response count must be 3")
    if inventory["failed_network_requests"] != 0:
        raise JapanMOECasebookError("failed network request count must be 0")
    return inventory


_SNAPSHOT_KEYS = {
    "casebook_scope",
    "created_on",
    "detail_cases",
    "format",
    "overview_cases",
    "processing_disclosure",
    "program_observations",
    "reconciliation",
    "sources",
}
_CASEBOOK_SCOPE_KEYS = {
    "casebook_complete_for_all_awards",
    "casebook_fiscal_years",
    "casebook_month",
    "detail_case_count",
    "detail_file_page_numbers",
    "overview_case_count",
    "overview_file_page_number",
    "overview_printed_page_number",
    "selection_scope",
    "unique_physical_site_count",
}
_OVERVIEW_KEYS = {
    "category_code",
    "category_label_ja",
    "fiscal_year",
    "operator_ja",
    "overview_id",
    "overview_row_number",
    "prefecture_ja",
    "technologies_ja",
}
_DETAIL_KEYS = {
    "category_code",
    "category_label_ja",
    "detail_id",
    "file_page_number",
    "metrics",
    "municipality_ja",
    "operator_ja",
    "printed_page_number",
    "third_party_source_basis_disclosed",
    "title_ja",
}
_METRIC_KEYS = {
    "actuality",
    "certificates_included",
    "comparison_operator",
    "metric_id",
    "metric_type",
    "normalized_mwh_per_year",
    "reported_unit",
    "reported_value",
    "scope",
    "self_consumed",
    "source_internal_consistency_warning",
    "source_label_ja",
    "subsidy_scope",
    "temporal_scope",
}
_PROGRAM_KEYS = {
    "fiscal_year",
    "gregorian_fiscal_year",
    "item_number",
    "program_id",
    "program_name_ja",
    "supplementary_budget_ja",
}
_RECONCILIATION_RELATION_KEYS = {
    "detail_id",
    "match_basis",
    "normalized_observation_id",
    "overview_id",
    "status",
}
_SOURCES_KEYS = {"casebook", "landing", "terms"}
_CASEBOOK_SOURCE_KEYS = {
    "accessed_on",
    "bytes",
    "file_page_count",
    "publication_month",
    "sha256",
    "url",
}
_LANDING_SOURCE_KEYS = {
    "accessed_on",
    "bytes",
    "page_updated_month",
    "sha256",
    "url",
}
_TERMS_SOURCE_KEYS = {
    "accessed_on",
    "bytes",
    "pdl_1_0_default_applies_unless_otherwise_noted",
    "processing_disclosure_required",
    "sha256",
    "url",
}


def validate_source_snapshot(
    value: Any,
    retrieval_inventory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = _exact_keys(value, _SNAPSHOT_KEYS, "source_snapshot")
    if snapshot["format"] != SOURCE_ARTIFACT_FORMAT:
        raise JapanMOECasebookError("unexpected source snapshot format")
    if snapshot["created_on"] != "2026-07-19":
        raise JapanMOECasebookError("source snapshot date changed")
    if "Processed by DataCenter Atlas" not in snapshot["processing_disclosure"]:
        raise JapanMOECasebookError("processing disclosure is missing")

    scope = _exact_keys(snapshot["casebook_scope"], _CASEBOOK_SCOPE_KEYS, "casebook_scope")
    if scope != {
        "casebook_complete_for_all_awards": False,
        "casebook_fiscal_years": ["R3", "R4", "R5", "R6", "R7"],
        "casebook_month": "2026-05",
        "detail_case_count": 8,
        "detail_file_page_numbers": [4, 5, 6, 7, 8, 9, 10, 11],
        "overview_case_count": 9,
        "overview_file_page_number": 3,
        "overview_printed_page_number": 2,
        "selection_scope": "some adopted projects in R3-R7",
        "unique_physical_site_count": None,
    }:
        raise JapanMOECasebookError("casebook scope changed")

    overview = _list(snapshot["overview_cases"], "overview_cases")
    if len(overview) != 9:
        raise JapanMOECasebookError("overview must contain 9 cases")
    overview_ids: set[str] = set()
    for index, raw in enumerate(overview, start=1):
        row = _exact_keys(raw, _OVERVIEW_KEYS, f"overview_cases[{index-1}]")
        if row["overview_row_number"] != index:
            raise JapanMOECasebookError("overview row numbers must be 1 through 9")
        if row["fiscal_year"] not in _FISCAL_YEAR_MAP:
            raise JapanMOECasebookError("unexpected overview fiscal year")
        if row["category_code"] not in {
            "new_build_support", "retrofit_support", "container_modular_support"
        }:
            raise JapanMOECasebookError("unexpected program work category")
        row_id = _string(row["overview_id"], "overview_id")
        if row_id in overview_ids:
            raise JapanMOECasebookError("duplicate overview ID")
        overview_ids.add(row_id)
        if not row["technologies_ja"] or not all(
            isinstance(term, str) and term for term in row["technologies_ja"]
        ):
            raise JapanMOECasebookError("overview technologies must be non-empty strings")

    details = _list(snapshot["detail_cases"], "detail_cases")
    if len(details) != 8:
        raise JapanMOECasebookError("detailed section must contain 8 cases")
    detail_ids: set[str] = set()
    metric_ids: list[str] = []
    for index, raw in enumerate(details):
        row = _exact_keys(raw, _DETAIL_KEYS, f"detail_cases[{index}]")
        if row["file_page_number"] != index + 4 or row["printed_page_number"] != index + 3:
            raise JapanMOECasebookError("detail page sequence must remain physical 4-11")
        detail_id = _string(row["detail_id"], "detail_id")
        if detail_id in detail_ids:
            raise JapanMOECasebookError("duplicate detail ID")
        detail_ids.add(detail_id)
        if row["third_party_source_basis_disclosed"] is not True:
            raise JapanMOECasebookError("third-party source-basis disclosure is required")
        metrics = _list(row["metrics"], f"detail_cases[{index}].metrics")
        for metric_index, raw_metric in enumerate(metrics):
            metric = _exact_keys(
                raw_metric,
                _METRIC_KEYS,
                f"detail_cases[{index}].metrics[{metric_index}]",
            )
            metric_id = _string(metric["metric_id"], "metric_id")
            metric_ids.append(metric_id)
            if metric["metric_type"] not in _METRIC_TYPES:
                raise JapanMOECasebookError("unsupported metric type")
            _number(metric["reported_value"], "reported_value")
            if metric["comparison_operator"] not in {"equal", "greater_than"}:
                raise JapanMOECasebookError("unsupported comparison operator")
            normalized = metric["normalized_mwh_per_year"]
            if normalized is not None:
                _number(normalized, "normalized_mwh_per_year")
                if metric["metric_type"] not in {
                    "renewable_generation",
                    "energy_savings",
                }:
                    raise JapanMOECasebookError(
                        "only energy quantities may have MWh/year normalization"
                    )
            if (
                metric["metric_type"] == "energy_savings"
                and "not energy consumption" not in metric["scope"]
            ):
                raise JapanMOECasebookError(
                    "energy savings must be separated from consumption"
                )
    expected_metric_ids = [f"metric-{number:03d}" for number in range(1, 25)]
    if metric_ids != expected_metric_ids:
        raise JapanMOECasebookError("metric IDs must be the exact ordered 24-row sequence")

    programs = _list(snapshot["program_observations"], "program_observations")
    if len(programs) != 6:
        raise JapanMOECasebookError("landing snapshot must retain 6 program listings")
    program_ids: set[str] = set()
    for index, raw in enumerate(programs):
        row = _exact_keys(raw, _PROGRAM_KEYS, f"program_observations[{index}]")
        if _FISCAL_YEAR_MAP.get(row["fiscal_year"]) != row["gregorian_fiscal_year"]:
            raise JapanMOECasebookError("program fiscal-year mapping changed")
        program_id = _string(row["program_id"], "program_id")
        if program_id in program_ids:
            raise JapanMOECasebookError("duplicate program ID")
        program_ids.add(program_id)

    relations = _list(snapshot["reconciliation"], "reconciliation")
    if len(relations) != 10:
        raise JapanMOECasebookError("reconciliation union must contain 10 observations")
    seen_overview: set[str] = set()
    seen_detail: set[str] = set()
    observation_ids: list[str] = []
    status_counts: dict[str, int] = {}
    for index, raw in enumerate(relations):
        relation = _exact_keys(
            raw, _RECONCILIATION_RELATION_KEYS, f"reconciliation[{index}]"
        )
        overview_id = relation["overview_id"]
        detail_id = relation["detail_id"]
        if overview_id is not None:
            if overview_id not in overview_ids or overview_id in seen_overview:
                raise JapanMOECasebookError("invalid or duplicate overview relation")
            seen_overview.add(overview_id)
        if detail_id is not None:
            if detail_id not in detail_ids or detail_id in seen_detail:
                raise JapanMOECasebookError("invalid or duplicate detail relation")
            seen_detail.add(detail_id)
        observation_ids.append(relation["normalized_observation_id"])
        status_counts[relation["status"]] = status_counts.get(relation["status"], 0) + 1
    if seen_overview != overview_ids or seen_detail != detail_ids:
        raise JapanMOECasebookError("reconciliation must cover every overview and detail row once")
    if observation_ids != [f"japan-moe-case-{number:03d}" for number in range(1, 11)]:
        raise JapanMOECasebookError("normalized observation IDs changed")
    if status_counts != {
        "detail_only": 1,
        "matched_by_name_location_category": 6,
        "matched_by_ordered_operator_location_context": 1,
        "overview_only": 2,
    }:
        raise JapanMOECasebookError("reconciliation status counts changed")

    sources = _exact_keys(snapshot["sources"], _SOURCES_KEYS, "sources")
    source_contracts = {
        "casebook": (_CASEBOOK_SOURCE_KEYS, CASEBOOK_URL, "moe_casebook"),
        "landing": (_LANDING_SOURCE_KEYS, LANDING_URL, "moe_landing"),
        "terms": (_TERMS_SOURCE_KEYS, TERMS_URL, "moe_terms"),
    }
    retrieval_by_id = {}
    if retrieval_inventory is not None:
        retrieval_by_id = {
            row["request_id"]: row
            for row in retrieval_inventory["controlled_http_requests"]
        }
    for name, (keys, expected_url, request_id) in source_contracts.items():
        source = _exact_keys(sources[name], keys, f"sources.{name}")
        if _official_url(source["url"], f"sources.{name}.url") != expected_url:
            raise JapanMOECasebookError("source URL changed")
        if not isinstance(source["sha256"], str) or not _SHA256_RE.fullmatch(
            source["sha256"]
        ):
            raise JapanMOECasebookError("source SHA-256 is invalid")
        if retrieval_by_id:
            request = retrieval_by_id[request_id]
            if source["sha256"] != request["sha256"] or source["bytes"] != request["bytes"]:
                raise JapanMOECasebookError("snapshot source pin differs from retrieval ledger")
    if sources["casebook"]["file_page_count"] != 12:
        raise JapanMOECasebookError("casebook page count changed")
    if not sources["terms"]["pdl_1_0_default_applies_unless_otherwise_noted"]:
        raise JapanMOECasebookError("PDL1.0 source notice must remain explicit")
    if not sources["terms"]["processing_disclosure_required"]:
        raise JapanMOECasebookError("processing disclosure requirement must remain explicit")
    return snapshot


def validate_source_artifact(
    root: Path,
    *,
    require_frozen: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    _assert_exact_regular_files(root, SOURCE_ARTIFACT_EXPECTED_FILES, "source artifact")
    manifest = _validate_manifest(
        root,
        expected_files=SOURCE_ARTIFACT_EXPECTED_FILES,
        identifier_key="artifact_id",
        identifier=RELEASE_ID,
        manifest_format=SOURCE_ARTIFACT_MANIFEST_FORMAT,
    )
    manifest_sha = sha256_bytes((root / MANIFEST_FILENAME).read_bytes())
    if manifest_sha != SOURCE_ARTIFACT_MANIFEST_SHA256:
        raise JapanMOECasebookError("source artifact manifest pin changed")
    if manifest["tree_sha256"] != SOURCE_ARTIFACT_TREE_SHA256:
        raise JapanMOECasebookError("source artifact tree pin changed")
    if require_frozen and not is_frozen_bundle(root, SOURCE_ARTIFACT_EXPECTED_FILES):
        raise JapanMOECasebookError("source artifact is not frozen read-only")
    retrieval = validate_retrieval_inventory(
        _read_json(root / "retrieval-inventory.json", "retrieval inventory")
    )
    snapshot = validate_source_snapshot(
        _read_json(root / "source-snapshot.json", "source snapshot"), retrieval
    )
    attribution = (root / "ATTRIBUTION.txt").read_text(encoding="utf-8")
    if "processed by datacenter atlas" not in attribution.lower():
        raise JapanMOECasebookError("artifact attribution lacks processing disclosure")
    artifact_names = {entry.name for entry in root.iterdir()}
    if artifact_names & {"casebook.pdf", "terms.html", "landing.html"}:
        raise JapanMOECasebookError("raw source body retained in source artifact")
    return {"manifest": manifest, "retrieval": retrieval, "snapshot": snapshot}


RIGHTS_POLICY: dict[str, Any] = {
    "attribution_required": True,
    "editing_and_processor_disclosure_required": True,
    "individual_law_constraints_may_apply": True,
    "legal_conclusion_claimed": False,
    "moe_logo_reuse_permitted_by_this_lane": False,
    "pdl_1_0_default_applies_unless_otherwise_noted": True,
    "raw_html_or_pdf_redistribution_permitted_by_this_lane": False,
    "source_images_or_diagrams_redistribution_permitted_by_this_lane": False,
    "third_party_body_redistribution_permitted_by_this_lane": False,
    "third_party_rights_clearance_verified": False,
}


DOWNSTREAM_IMPORT_POLICY: dict[str, Any] = {
    "construction_map_import_permitted": False,
    "construction_master_import_permitted": False,
    "current_coverage_ledger_import_permitted": False,
    "reason": (
        "official subsidy case-study participation and reported program effects "
        "do not establish unique physical sites or construction/operating lifecycle"
    ),
}


def source_definition() -> dict[str, Any]:
    return {
        "atlas_role": "source_bound_auxiliary_review_only",
        "build_contract": {
            "build_network_requests": 0,
            "deterministic": True,
            "input": f"source_artifacts/{RELEASE_ID}",
            "source_artifact_manifest_sha256": SOURCE_ARTIFACT_MANIFEST_SHA256,
            "source_artifact_tree_sha256": SOURCE_ARTIFACT_TREE_SHA256,
        },
        "coverage": {
            "complete_for_all_japan_data_centres": False,
            "complete_for_all_program_awards": False,
            "detail_case_count": 8,
            "normalized_case_observation_count": 10,
            "overview_case_count": 9,
            "selected_casebook_scope": "some adopted projects in R3-R7",
            "unique_physical_site_count": None,
        },
        "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
        "format": DEFINITION_FORMAT,
        "jurisdiction": "Japan",
        "metric_contract": {
            "annual_energy_consumption_mwh": None,
            "co2_values_are_reported_reductions_not_emissions_inventory": True,
            "energy_savings_are_energy_consumption": False,
            "generation_is_energy_consumption": False,
            "it_load_mw": None,
            "power_capacity_mw": None,
            "pue": None,
            "retained_metric_types": sorted(_METRIC_TYPES),
        },
        "organization": "Ministry of the Environment, Government of Japan",
        "physical_evidence_contract": {
            "case_observation_is_unique_physical_site": False,
            "construction_status": None,
            "data_centre_type": None,
            "operating_status": None,
            "program_work_category_is_physical_data_centre_type": False,
            "subsidy_participation_is_lifecycle_evidence": False,
        },
        "release_id": RELEASE_ID,
        "rights_policy": RIGHTS_POLICY,
        "source_kind": "official_subsidy_program_casebook_auxiliary",
        "source_urls": {
            "casebook": CASEBOOK_URL,
            "landing": LANDING_URL,
            "terms": TERMS_URL,
        },
        "title": "Japan MOE data-centre decarbonization subsidy casebook",
    }


def _derive_observations(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    overview_by_id = {row["overview_id"]: row for row in snapshot["overview_cases"]}
    detail_by_id = {row["detail_id"]: row for row in snapshot["detail_cases"]}
    rows: list[dict[str, Any]] = []
    for relation in snapshot["reconciliation"]:
        overview = overview_by_id.get(relation["overview_id"])
        detail = detail_by_id.get(relation["detail_id"])
        fiscal_year = overview["fiscal_year"] if overview else None
        category_code = overview["category_code"] if overview else detail["category_code"]
        category_label = overview["category_label_ja"] if overview else detail["category_label_ja"]
        municipality = detail["municipality_ja"] if detail else None
        prefecture = overview["prefecture_ja"] if overview else (
            "福岡県" if municipality == "福岡県京都郡" else None
        )
        rows.append(
            {
                "annual_energy_consumption_mwh": None,
                "atlas_treatment": "review_only_official_subsidy_case_study",
                "casebook_relation": relation["status"],
                "data_centre_type": None,
                "fiscal_year": fiscal_year,
                "format": "datacenter-atlas-japan-moe-case-observation-v1",
                "gregorian_fiscal_year": _FISCAL_YEAR_MAP.get(fiscal_year),
                "it_load_mw": None,
                "metric_count": len(detail["metrics"]) if detail else 0,
                "municipality_ja": municipality,
                "observation_id": relation["normalized_observation_id"],
                "observation_unit": "casebook_program_record",
                "operator_ja": detail["operator_ja"] if detail else overview["operator_ja"],
                "overview_row_number": overview["overview_row_number"] if overview else None,
                "physical_construction_status": None,
                "physical_operating_status": None,
                "physical_site_id": None,
                "power_capacity_mw": None,
                "prefecture_ja": prefecture,
                "program_category_is_physical_data_centre_type": False,
                "program_participation_is_lifecycle_evidence": False,
                "program_work_category_code": category_code,
                "program_work_category_label_ja": category_label,
                "pue": None,
                "reconciliation_basis": relation["match_basis"],
                "source_detail_file_page_number": (
                    detail["file_page_number"] if detail else None
                ),
                "source_detail_printed_page_number": (
                    detail["printed_page_number"] if detail else None
                ),
                "source_landing_url": LANDING_URL,
                "source_pdf_url": CASEBOOK_URL,
                "technologies_ja": overview["technologies_ja"] if overview else [],
                "unique_site_resolution_status": "not_attempted_source_insufficient",
            }
        )
    return rows


def _derive_metrics(
    snapshot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    observation_by_detail = {
        relation["detail_id"]: relation["normalized_observation_id"]
        for relation in snapshot["reconciliation"]
        if relation["detail_id"] is not None
    }
    rows: list[dict[str, Any]] = []
    for detail in snapshot["detail_cases"]:
        for metric in detail["metrics"]:
            row = dict(metric)
            row.update(
                {
                    "detail_id": detail["detail_id"],
                    "format": "datacenter-atlas-japan-moe-metric-observation-v1",
                    "is_energy_consumption_metric": False,
                    "is_it_or_power_capacity_metric": False,
                    "observation_id": observation_by_detail[detail["detail_id"]],
                    "source_file_page_number": detail["file_page_number"],
                    "source_pdf_url": CASEBOOK_URL,
                    "source_printed_page_number": detail["printed_page_number"],
                }
            )
            rows.append(row)
    if {row["observation_id"] for row in rows} - {
        row["observation_id"] for row in observations
    }:
        raise JapanMOECasebookError("metric references unknown observation")
    return rows


def _derive_programs(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **row,
            "case_mapping_status": "fiscal_year_only_not_program_item_specific",
            "construction_lifecycle_implication": None,
            "format": "datacenter-atlas-japan-moe-program-observation-v1",
            "operating_lifecycle_implication": None,
            "source_landing_url": LANDING_URL,
        }
        for row in snapshot["program_observations"]
    ]


def schema_document() -> dict[str, Any]:
    return {
        "additional_fields_allowed": False,
        "expected_counts": {
            "case_observations": 10,
            "detail_cases": 8,
            "metric_observations": 24,
            "overview_cases": 9,
            "program_observations": 6,
            "reconciled_matches": 7,
        },
        "format": SCHEMA_FORMAT,
        "metric_observation_fields": sorted(_RELEASE_METRIC_KEYS),
        "observation_fields": sorted(_OBSERVATION_KEYS),
        "program_observation_fields": sorted(_RELEASE_PROGRAM_KEYS),
        "schema_version": SCHEMA_VERSION,
    }


def _reconciliation_document(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "detail_case_count": 8,
        "detail_only_count": 1,
        "format": "datacenter-atlas-japan-moe-reconciliation-v1",
        "matched_count": 7,
        "normalized_case_observation_count": 10,
        "overview_case_count": 9,
        "overview_only_count": 2,
        "physical_site_count": None,
        "release_id": RELEASE_ID,
        "relations": snapshot["reconciliation"],
        "resolution_note": (
            "The overview lists nine cases and the detailed section contains eight. "
            "Seven reconcile; Frontend and Aos Field are overview-only, while WM is "
            "detail-only. The ten-record union is not a physical-site count."
        ),
    }


def _assessment_document(
    retrieval: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
    programs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metric_counts = {
        kind: sum(row["metric_type"] == kind for row in metrics)
        for kind in sorted(_METRIC_TYPES)
    }
    return {
        "atlas_decision": {
            "construction_master_claim": False,
            "downstream_import_policy": DOWNSTREAM_IMPORT_POLICY,
            "status": "source_bound_auxiliary_review_only",
        },
        "casebook_reconciliation": {
            "detail_case_count": 8,
            "detail_only_count": 1,
            "matched_count": 7,
            "normalized_case_observation_count": len(observations),
            "overview_case_count": 9,
            "overview_only_count": 2,
            "unique_physical_site_count": None,
        },
        "coverage": {
            "complete_for_all_japan_data_centres": False,
            "complete_for_all_program_awards": False,
            "fiscal_years": ["R3", "R4", "R5", "R6", "R7"],
            "selection_scope": "some adopted projects in R3-R7",
        },
        "format": RELEASE_FORMAT,
        "lifecycle_boundary": {
            "construction_status_count": None,
            "operating_status_count": None,
            "program_category_is_physical_data_centre_type": False,
            "subsidy_participation_is_lifecycle_evidence": False,
        },
        "metric_boundary": {
            "annual_energy_consumption_mwh": None,
            "co2_values_are_reported_reductions_not_emissions_inventory": True,
            "energy_savings_are_energy_consumption": False,
            "generation_is_energy_consumption": False,
            "it_load_mw": None,
            "metric_counts": metric_counts,
            "metric_observation_count": len(metrics),
            "power_capacity_mw": None,
            "pue": None,
        },
        "program_observation_count": len(programs),
        "release_id": RELEASE_ID,
        "retrieval_batch": {
            "browser_proxy_origin_request_count": retrieval[
                "browser_proxy_origin_request_count"
            ],
            "browser_proxy_research_excluded_from_direct_request_arithmetic": True,
            "build_network_requests": 0,
            "direct_request_attempt_cap": retrieval["direct_request_attempt_cap"],
            "direct_request_attempts": retrieval["direct_request_attempts"],
            "minimum_request_start_interval_seconds": retrieval[
                "minimum_request_start_interval_seconds"
            ],
            "third_party_requests": retrieval["third_party_requests"],
        },
        "rights_policy": RIGHTS_POLICY,
    }


def _source_inventory_document(
    snapshot: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    sources = snapshot["sources"]
    return {
        "format": "datacenter-atlas-japan-moe-source-inventory-v1",
        "official_sources": [
            {
                "bytes": sources[name]["bytes"],
                "kind": name,
                "raw_body_redistributed": False,
                "sha256": sources[name]["sha256"],
                "url": sources[name]["url"],
            }
            for name in ("terms", "landing", "casebook")
        ],
        "release_id": RELEASE_ID,
        "source_artifact": {
            "manifest_sha256": SOURCE_ARTIFACT_MANIFEST_SHA256,
            "path": f"source_artifacts/{RELEASE_ID}",
            "tree_sha256": manifest["tree_sha256"],
        },
        "source_images_redistributed": False,
        "third_party_bodies_redistributed": False,
    }


def _release_readme() -> bytes:
    return (
        "# Japan MOE data-centre decarbonization casebook\n\n"
        "This frozen auxiliary release contains official subsidy-program and casebook "
        "observations from the May 2026 MOE casebook. The overview has nine rows, "
        "the detailed section has eight pages, seven reconcile, two are overview-only, "
        "and one is detail-only. The resulting ten observations are not ten unique "
        "physical sites.\n\n"
        "Program categories describe supported work, not verified data-centre type or "
        "lifecycle. Reported renewable generation, savings, renewable share, and CO2 "
        "reductions retain page-specific scope and are not electricity-consumption, "
        "IT-load, utility-capacity, or PUE observations.\n\n"
        "Source: Ministry of the Environment, Government of Japan. Processed by "
        "DataCenter Atlas on 2026-07-19; this is not unmodified government content. "
        "No images, logos, raw source bodies, or third-party bodies are redistributed.\n"
    ).encode("utf-8")


def derive_release_files(source_bundle: Mapping[str, Any]) -> dict[str, bytes]:
    snapshot = source_bundle["snapshot"]
    retrieval = source_bundle["retrieval"]
    manifest = source_bundle["manifest"]
    observations = _derive_observations(snapshot)
    metrics = _derive_metrics(snapshot, observations)
    programs = _derive_programs(snapshot)
    attribution = (
        "Source: Ministry of the Environment, Government of Japan (MOE Japan)\n"
        f"Landing page: {LANDING_URL}\n"
        f"Casebook: {CASEBOOK_URL}\n"
        f"Use terms: {TERMS_URL}\n"
        "Accessed: 2026-07-19\n\n"
        "Processed by DataCenter Atlas on 2026-07-19. This release is a structured "
        "transcription and reconciliation, not unmodified government content. No "
        "source images, MOE logo, raw HTML, raw PDF, or third-party source bodies "
        "are redistributed.\n"
    ).encode("utf-8")
    return {
        "ATTRIBUTION.txt": attribution,
        "README.md": _release_readme(),
        "assessment.json": canonical_json(
            _assessment_document(retrieval, observations, metrics, programs)
        ),
        "definition.json": canonical_json(source_definition()),
        "metrics.jsonl": canonical_jsonl(metrics),
        "observations.jsonl": canonical_jsonl(observations),
        "program-observations.jsonl": canonical_jsonl(programs),
        "reconciliation.json": canonical_json(_reconciliation_document(snapshot)),
        "retrieval-inventory.json": canonical_json(retrieval),
        "schema.json": canonical_json(schema_document()),
        "source-inventory.json": canonical_json(
            _source_inventory_document(snapshot, manifest)
        ),
    }


def _complete_payloads(payloads: Mapping[str, bytes]) -> dict[str, bytes]:
    expected_payload_names = RELEASE_EXPECTED_FILES - {
        MANIFEST_FILENAME, MANIFEST_HASH_FILENAME
    }
    if set(payloads) != expected_payload_names:
        raise JapanMOECasebookError("derived release payload set differs")
    manifest = _manifest_document(
        identifier_key="release_id",
        identifier=RELEASE_ID,
        manifest_format=RELEASE_MANIFEST_FORMAT,
        payloads=payloads,
    )
    manifest_body = canonical_json(manifest)
    result = dict(payloads)
    result[MANIFEST_FILENAME] = manifest_body
    result[MANIFEST_HASH_FILENAME] = (
        f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return result


def default_source_artifact_path() -> Path:
    return Path(__file__).resolve().parents[1] / "source_artifacts" / RELEASE_ID


def write_release_bundle(
    source_artifact_path: Path,
    output: Path,
    *,
    require_frozen_source: bool = True,
) -> None:
    source_bundle = validate_source_artifact(
        source_artifact_path, require_frozen=require_frozen_source
    )
    expected = _complete_payloads(derive_release_files(source_bundle))
    output = output.resolve()
    if output.exists() or output.is_symlink():
        if output.is_symlink() or not output.is_dir():
            raise JapanMOECasebookError("existing release target is not a real directory")
        _assert_exact_regular_files(output, RELEASE_EXPECTED_FILES, "existing release")
        actual = {name: (output / name).read_bytes() for name in RELEASE_EXPECTED_FILES}
        if actual != expected:
            raise JapanMOECasebookError("existing release differs from deterministic output")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{RELEASE_ID}-", dir=output.parent))
    try:
        for name, body in expected.items():
            (temporary / name).write_bytes(body)
        freeze_bundle(temporary)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            temporary.chmod(0o755)
            for entry in temporary.iterdir():
                if entry.is_file():
                    entry.chmod(0o644)
            shutil.rmtree(temporary)
        raise


_OBSERVATION_KEYS = {
    "annual_energy_consumption_mwh", "atlas_treatment", "casebook_relation",
    "data_centre_type", "fiscal_year", "format", "gregorian_fiscal_year",
    "it_load_mw", "metric_count", "municipality_ja", "observation_id",
    "observation_unit", "operator_ja", "overview_row_number",
    "physical_construction_status", "physical_operating_status", "physical_site_id",
    "power_capacity_mw", "prefecture_ja",
    "program_category_is_physical_data_centre_type",
    "program_participation_is_lifecycle_evidence", "program_work_category_code",
    "program_work_category_label_ja", "pue", "reconciliation_basis",
    "source_detail_file_page_number", "source_detail_printed_page_number",
    "source_landing_url", "source_pdf_url", "technologies_ja",
    "unique_site_resolution_status",
}
_RELEASE_METRIC_KEYS = _METRIC_KEYS | {
    "detail_id", "format", "is_energy_consumption_metric",
    "is_it_or_power_capacity_metric", "observation_id",
    "source_file_page_number", "source_pdf_url", "source_printed_page_number",
}
_RELEASE_PROGRAM_KEYS = _PROGRAM_KEYS | {
    "case_mapping_status", "construction_lifecycle_implication", "format",
    "operating_lifecycle_implication", "source_landing_url",
}
_RECONCILIATION_DOCUMENT_KEYS = {
    "detail_case_count",
    "detail_only_count",
    "format",
    "matched_count",
    "normalized_case_observation_count",
    "overview_case_count",
    "overview_only_count",
    "physical_site_count",
    "release_id",
    "relations",
    "resolution_note",
}
_SOURCE_INVENTORY_KEYS = {
    "format",
    "official_sources",
    "release_id",
    "source_artifact",
    "source_images_redistributed",
    "third_party_bodies_redistributed",
}
_OFFICIAL_SOURCE_INVENTORY_KEYS = {
    "bytes",
    "kind",
    "raw_body_redistributed",
    "sha256",
    "url",
}
_SOURCE_ARTIFACT_INVENTORY_KEYS = {
    "manifest_sha256",
    "path",
    "tree_sha256",
}


def validate_release_bundle(
    root: Path,
    *,
    definition_path: Path | None = None,
    source_artifact_path: Path | None = None,
    require_frozen: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    _assert_exact_regular_files(root, RELEASE_EXPECTED_FILES, "release")
    manifest = _validate_manifest(
        root,
        expected_files=RELEASE_EXPECTED_FILES,
        identifier_key="release_id",
        identifier=RELEASE_ID,
        manifest_format=RELEASE_MANIFEST_FORMAT,
    )
    if require_frozen and not is_frozen_bundle(root, RELEASE_EXPECTED_FILES):
        raise JapanMOECasebookError("release is not frozen read-only")
    definition = _read_json(root / "definition.json", "definition")
    if definition != source_definition():
        raise JapanMOECasebookError("release definition differs from source contract")
    if definition_path is not None:
        external = _read_json(definition_path, "external definition")
        if external != definition:
            raise JapanMOECasebookError("external source definition differs")
    retrieval = validate_retrieval_inventory(
        _read_json(root / "retrieval-inventory.json", "retrieval inventory")
    )
    observations = _read_jsonl(root / "observations.jsonl", "observations")
    metrics = _read_jsonl(root / "metrics.jsonl", "metrics")
    programs = _read_jsonl(root / "program-observations.jsonl", "program observations")
    if len(observations) != 10 or len(metrics) != 24 or len(programs) != 6:
        raise JapanMOECasebookError("release row counts changed")
    observation_ids: set[str] = set()
    for index, row in enumerate(observations):
        _exact_keys(row, _OBSERVATION_KEYS, f"observations[{index}]")
        if row["observation_id"] in observation_ids:
            raise JapanMOECasebookError("duplicate release observation ID")
        observation_ids.add(row["observation_id"])
        for nullable in (
            "annual_energy_consumption_mwh", "data_centre_type", "it_load_mw",
            "physical_construction_status", "physical_operating_status",
            "physical_site_id", "power_capacity_mw", "pue",
        ):
            if row[nullable] is not None:
                raise JapanMOECasebookError(f"{nullable} must remain null")
        if row["program_participation_is_lifecycle_evidence"]:
            raise JapanMOECasebookError("subsidy participation cannot become lifecycle evidence")
    metric_ids: set[str] = set()
    for index, row in enumerate(metrics):
        _exact_keys(row, _RELEASE_METRIC_KEYS, f"metrics[{index}]")
        if row["metric_id"] in metric_ids:
            raise JapanMOECasebookError("duplicate metric ID")
        metric_ids.add(row["metric_id"])
        if row["observation_id"] not in observation_ids:
            raise JapanMOECasebookError("metric references unknown case observation")
        if row["metric_type"] not in _METRIC_TYPES:
            raise JapanMOECasebookError("release contains unsupported metric")
        if (
            row["is_energy_consumption_metric"]
            or row["is_it_or_power_capacity_metric"]
        ):
            raise JapanMOECasebookError("metric boundary changed")
    for index, row in enumerate(programs):
        _exact_keys(row, _RELEASE_PROGRAM_KEYS, f"programs[{index}]")
        if (
            row["construction_lifecycle_implication"] is not None
            or row["operating_lifecycle_implication"] is not None
        ):
            raise JapanMOECasebookError("program observation implies physical lifecycle")
    schema = _read_json(root / "schema.json", "schema")
    if schema != schema_document():
        raise JapanMOECasebookError("release schema differs")
    reconciliation = _read_json(root / "reconciliation.json", "reconciliation")
    _exact_keys(
        reconciliation,
        _RECONCILIATION_DOCUMENT_KEYS,
        "reconciliation",
    )
    relations = _list(reconciliation["relations"], "reconciliation.relations")
    if len(relations) != 10:
        raise JapanMOECasebookError("reconciliation relation count changed")
    for index, relation in enumerate(relations):
        _exact_keys(
            relation,
            _RECONCILIATION_RELATION_KEYS,
            f"reconciliation.relations[{index}]",
        )
    if {row["normalized_observation_id"] for row in relations} != observation_ids:
        raise JapanMOECasebookError(
            "reconciliation relations differ from case observations"
        )
    if reconciliation["physical_site_count"] is not None:
        raise JapanMOECasebookError("physical site count must remain unknown")
    if (
        reconciliation["overview_case_count"],
        reconciliation["detail_case_count"],
        reconciliation["matched_count"],
        reconciliation["overview_only_count"],
        reconciliation["detail_only_count"],
        reconciliation["normalized_case_observation_count"],
    ) != (9, 8, 7, 2, 1, 10):
        raise JapanMOECasebookError("reconciliation counts changed")
    assessment = _read_json(root / "assessment.json", "assessment")
    if assessment != _assessment_document(
        retrieval,
        observations,
        metrics,
        programs,
    ):
        raise JapanMOECasebookError("assessment differs from release rows")
    if (
        assessment["casebook_reconciliation"]["unique_physical_site_count"]
        is not None
    ):
        raise JapanMOECasebookError("assessment physical site count must remain null")
    source_inventory = _read_json(root / "source-inventory.json", "source inventory")
    _exact_keys(source_inventory, _SOURCE_INVENTORY_KEYS, "source_inventory")
    artifact_inventory = _exact_keys(
        source_inventory["source_artifact"],
        _SOURCE_ARTIFACT_INVENTORY_KEYS,
        "source_inventory.source_artifact",
    )
    if (
        artifact_inventory["manifest_sha256"]
        != SOURCE_ARTIFACT_MANIFEST_SHA256
    ):
        raise JapanMOECasebookError("source artifact pin changed")
    if artifact_inventory != {
        "manifest_sha256": SOURCE_ARTIFACT_MANIFEST_SHA256,
        "path": f"source_artifacts/{RELEASE_ID}",
        "tree_sha256": SOURCE_ARTIFACT_TREE_SHA256,
    }:
        raise JapanMOECasebookError("source artifact inventory changed")
    official_sources = _list(
        source_inventory["official_sources"],
        "source_inventory.official_sources",
    )
    if len(official_sources) != 3:
        raise JapanMOECasebookError("official source inventory count changed")
    requests_by_url = {
        row["url"]: row for row in retrieval["controlled_http_requests"]
    }
    for index, source in enumerate(official_sources):
        _exact_keys(
            source,
            _OFFICIAL_SOURCE_INVENTORY_KEYS,
            f"source_inventory.official_sources[{index}]",
        )
        request = requests_by_url.get(source["url"])
        if request is None:
            raise JapanMOECasebookError("source inventory contains unknown URL")
        if (
            source["bytes"] != request["bytes"]
            or source["sha256"] != request["sha256"]
            or source["raw_body_redistributed"]
        ):
            raise JapanMOECasebookError(
                "source inventory differs from retrieval ledger"
            )
    if (
        source_inventory["source_images_redistributed"]
        or source_inventory["third_party_bodies_redistributed"]
    ):
        raise JapanMOECasebookError("excluded content redistribution flag changed")
    if source_artifact_path is not None:
        source_bundle = validate_source_artifact(source_artifact_path, require_frozen=True)
        expected = _complete_payloads(derive_release_files(source_bundle))
        actual = {name: (root / name).read_bytes() for name in RELEASE_EXPECTED_FILES}
        if actual != expected:
            raise JapanMOECasebookError("release differs from pinned source artifact derivation")
    return {
        "assessment": assessment,
        "definition": definition,
        "manifest": manifest,
        "metrics": metrics,
        "observations": observations,
        "programs": programs,
        "reconciliation": reconciliation,
        "retrieval": retrieval,
        "schema": schema,
        "source_inventory": source_inventory,
    }


__all__ = [
    "ALLOWED_SOURCE_URLS",
    "CASEBOOK_URL",
    "DOWNSTREAM_IMPORT_POLICY",
    "JapanMOECasebookError",
    "LANDING_URL",
    "MAX_DIRECT_REQUEST_ATTEMPTS",
    "MIN_REQUEST_START_INTERVAL_SECONDS",
    "RELEASE_EXPECTED_FILES",
    "RELEASE_ID",
    "RIGHTS_POLICY",
    "SOURCE_ARTIFACT_EXPECTED_FILES",
    "SOURCE_ARTIFACT_MANIFEST_SHA256",
    "SOURCE_ARTIFACT_TREE_SHA256",
    "TERMS_URL",
    "canonical_json",
    "canonical_jsonl",
    "default_source_artifact_path",
    "derive_release_files",
    "freeze_bundle",
    "is_frozen_bundle",
    "schema_document",
    "sha256_bytes",
    "source_definition",
    "thaw_for_test",
    "validate_release_bundle",
    "validate_retrieval_inventory",
    "validate_source_artifact",
    "validate_source_snapshot",
    "write_release_bundle",
]
