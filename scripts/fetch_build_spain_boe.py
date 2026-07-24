#!/usr/bin/env python3
"""Build the frozen Spain BOE assessment from a bounded reviewed capture."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.spain_boe import (
    INVENTORY_FORMAT,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    OPEN_DATA_FAQ_URL,
    RELEASE_ID,
    SEARCH_FORM_URL,
    SEARCH_HELP_URL,
    SEARCH_TERMS,
    LEGAL_NOTICE_URL,
    SpainBOEError,
    build_sanitized_snapshot,
    canonical_json,
    search_url,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UNION = Path("/tmp/boe-2016-union.json")
DEFAULT_QUERY_PREFIX = Path("/tmp/boe-2016")
DEFAULT_SUPPORT = Path("/tmp/boe-spain-support-20260718")
DEFAULT_A_LOG = Path("/tmp/boe-spain-a-detail-log.json")
DEFAULT_B_LOG = Path("/tmp/boe-spain-b-detail-log.json")
DEFAULT_PDF_LOG = Path("/tmp/boe-spain-pdf-log.json")
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"

SLUGS = {
    "centro de datos": "centro-de-datos",
    "centros de datos": "centros-de-datos",
    "centro de procesamiento de datos": "centro-de-procesamiento-de-datos",
    "centro de proceso de datos": "centro-de-proceso-de-datos",
    "data center": "data-center",
    "datacenter": "datacenter",
}
SUPPORT_URLS = {
    "legal-notice.html": LEGAL_NOTICE_URL,
    "open-data-faq.html": OPEN_DATA_FAQ_URL,
    "search-form.html": SEARCH_FORM_URL,
    "search-help.html": SEARCH_HELP_URL,
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--union", type=Path, default=DEFAULT_UNION)
    result.add_argument("--query-prefix", type=Path, default=DEFAULT_QUERY_PREFIX)
    result.add_argument("--support-dir", type=Path, default=DEFAULT_SUPPORT)
    result.add_argument("--a-detail-log", type=Path, default=DEFAULT_A_LOG)
    result.add_argument("--b-detail-log", type=Path, default=DEFAULT_B_LOG)
    result.add_argument("--pdf-log", type=Path, default=DEFAULT_PDF_LOG)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--validate-only", action="store_true")
    return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SpainBOEError(f"invalid capture input: {path}") from error


def _response_record(
    *,
    kind: str,
    url: str,
    body_bytes: int,
    digest: str,
    response_date: str | None,
    body_retained: bool,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "body_retained": body_retained,
        "bytes": body_bytes,
        "http_status": 200,
        "kind": kind,
        "response_date": response_date,
        "sha256": digest,
        "url": url,
        **extra,
    }


def _build_inventory(arguments: argparse.Namespace) -> tuple[dict[str, Any], dict[str, bytes]]:
    responses: list[dict[str, Any]] = []
    for term in SEARCH_TERMS:
        slug = SLUGS[term]
        metadata = _load_json(Path(f"{arguments.query_prefix}-{slug}.metadata.json"))
        expected_url = search_url(term)
        if metadata.get("query_url") != expected_url:
            raise SpainBOEError(f"query URL differs for {term}")
        responses.append(
            _response_record(
                kind="search_result",
                url=expected_url,
                body_bytes=int(metadata["bytes"]),
                digest=str(metadata["sha256"]),
                response_date=metadata.get("date"),
                body_retained=False,
                reported_count=int(metadata["reported_count"]),
                term=term,
            )
        )

    support: dict[str, bytes] = {}
    for name, url in SUPPORT_URLS.items():
        path = arguments.support_dir / name
        body = path.read_bytes()
        support[name] = body
        responses.append(
            _response_record(
                kind="support_policy",
                url=url,
                body_bytes=len(body),
                digest=sha256_bytes(body),
                response_date=None,
                body_retained=True,
                release_path=f"support/{name}",
            )
        )

    for log_path in (arguments.a_detail_log, arguments.b_detail_log):
        records = _load_json(log_path)
        if not isinstance(records, list):
            raise SpainBOEError(f"detail log must be a list: {log_path}")
        for raw in records:
            responses.append(
                _response_record(
                    kind="detail_xml",
                    url=str(raw["url"]),
                    body_bytes=int(raw["bytes"]),
                    digest=str(raw["sha256"]),
                    response_date=raw.get("date"),
                    body_retained=False,
                    boe_id=str(raw["boe_id"]),
                )
            )

    pdf_records = _load_json(arguments.pdf_log)
    if not isinstance(pdf_records, list):
        raise SpainBOEError("PDF detail log must be a list")
    for raw in pdf_records:
        responses.append(
            _response_record(
                kind="detail_pdf",
                url=str(raw["url"]),
                body_bytes=int(raw["bytes"]),
                digest=str(raw["sha256"]),
                response_date=raw.get("date"),
                body_retained=False,
                boe_id=str(raw["boe_id"]),
                extracted_text_bytes=int(raw["extracted_text_bytes"]),
                exact_phrase_hits=int(raw["phrase_hits"]),
            )
        )

    capture_dates = [str(row["response_date"]) for row in responses if row.get("response_date")]
    inventory = {
        "capture_completed_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "capture_response_dates": {"first": min(capture_dates), "last": max(capture_dates)},
        "exploratory_all_time_pilot": {
            "controlled_release_capture": False,
            "description": "Earlier unbounded count-only pilot; not part of the classified closed set",
            "term_counts": {"centro de datos": 104, "centros de datos": 217, "centro de procesamiento de datos": 78, "centro de proceso de datos": 1417, "data center": 84, "datacenter": 36},
            "union_count": 1903,
        },
        "format": INVENTORY_FORMAT,
        "maximum_network_requests": MAX_NETWORK_REQUESTS,
        "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
        "network_requests": len(responses),
        "raw_detail_pdf_xml_or_search_bodies_retained": False,
        "release_id": RELEASE_ID,
        "responses": responses,
    }
    return inventory, support


def _write_definition(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise SpainBOEError("definition output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(source_definition()))


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.validate_only:
        validate_release_bundle(arguments.output)
        print(f"validated {arguments.output}")
        return 0
    union = _load_json(arguments.union)
    if not isinstance(union, dict):
        raise SpainBOEError("union capture must be an object")
    snapshot = build_sanitized_snapshot(union)
    inventory, support = _build_inventory(arguments)
    _write_definition(arguments.definition)
    write_release_bundle(snapshot, inventory, support, arguments.output)
    validate_release_bundle(arguments.output)
    print(f"built and validated {arguments.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpainBOEError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
