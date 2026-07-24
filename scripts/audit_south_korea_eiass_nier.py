#!/usr/bin/env python3
"""Run a fail-closed, metadata-only EIASS/NIER source audit.

This script never calls an EIASS search action or a NIER data endpoint.  It
only retrieves robots policies and official documentation pages from a fixed
allowlist, without following redirects.  Response bodies are temporary audit
inputs and must not be shipped in a release bundle.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import socket
import time
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MIN_REQUEST_START_INTERVAL_SECONDS = 3.0
AUDIT_REQUEST_START_INTERVAL_SECONDS = 3.2
MAX_DIRECT_REQUEST_ATTEMPTS = 40
USER_AGENT = (
    "DataCenterAtlasSourceAssessment/1.0 "
    "(metadata-only; no result queries or exports)"
)

DATA_GO_ROBOTS_URL = "https://www.data.go.kr/robots.txt"
DATA_GO_API_ROBOTS_URL = "https://apis.data.go.kr/robots.txt"
EIASS_ROBOTS_URL = "https://www.eiass.go.kr/robots.txt"
EIASS_CANONICAL_ROBOTS_URL = "https://eiasas.eiass.go.kr/robots.txt"
KOGL_ROBOTS_URL = "https://www.kogl.or.kr/robots.txt"

ROBOTS_REQUESTS = (
    ("data_go_robots", DATA_GO_ROBOTS_URL),
    ("data_go_api_robots", DATA_GO_API_ROBOTS_URL),
    ("eiass_robots", EIASS_ROBOTS_URL),
    ("eiass_canonical_robots", EIASS_CANONICAL_ROBOTS_URL),
    ("kogl_robots", KOGL_ROBOTS_URL),
)

DATA_GO_METADATA_REQUESTS = (
    (
        "data_go_portal_policy",
        "https://www.data.go.kr/ugs/selectPortalPolicyView.do",
    ),
    (
        "data_go_migration_notice",
        "https://www.data.go.kr/bbs/ntc/selectNotice.do?"
        "originId=NOTICE_0000000004067",
    ),
    (
        "data_go_eia_discussion_api_metadata",
        "https://www.data.go.kr/data/15142987/openapi.do",
    ),
    (
        "data_go_pre_strategy_small_api_metadata",
        "https://www.data.go.kr/data/15142990/openapi.do",
    ),
    (
        "data_go_business_area_api_metadata",
        "https://www.data.go.kr/data/15142907/openapi.do",
    ),
)

KOGL_METADATA_REQUESTS = (
    (
        "kogl_type_one_terms",
        "https://www.kogl.or.kr/info/faqList.do?"
        "cPage=1&dataGroup=2&mstIdx=KOGL_005",
    ),
)

EIASS_METADATA_REQUESTS = (
    ("eiass_main_form_metadata", "https://eiasas.eiass.go.kr/main.do"),
    (
        "eiass_project_search_help",
        "https://eiasas.eiass.go.kr/etc/help/view.do?tabgubun=pr",
    ),
    ("eiass_terms", "https://eiasas.eiass.go.kr/etc/service.do"),
    ("eiass_copyright", "https://eiasas.eiass.go.kr/etc/kogl.do"),
    (
        "eiass_openapi_introduction",
        "https://eiasas.eiass.go.kr/openapiguide/kei_html/chapter02.html",
    ),
    (
        "eiass_openapi_service_list",
        "https://eiasas.eiass.go.kr/openapiguide/kei_html/chapter03.html",
    ),
    (
        "eiass_openapi_usage_guide",
        "https://eiasas.eiass.go.kr/openapiguide/kei_html/chapter04.html",
    ),
    (
        "eiass_integrated_user_manual",
        "https://eiasas.eiass.go.kr/contents/"
        "%ED%86%B5%ED%95%A9%EB%A7%A4%EB%89%B4%EC%96%BC"
        "%28%EC%9D%BC%EB%B0%98%EC%82%AC%EC%9A%A9%EC%9E%90%29.pdf",
    ),
)

ALLOWED_HOSTS = {
    "apis.data.go.kr",
    "eiasas.eiass.go.kr",
    "www.data.go.kr",
    "www.eiass.go.kr",
    "www.kogl.or.kr",
}
FORBIDDEN_PATH_PARTS = (
    "/getDscssBsnsListInfoInqire",
    "/getBsnsStrtgySmallScaleDscssListInfoInqire",
)
FORBIDDEN_QUERY_LITERALS = (
    "데이터센터",
    "데이터 센터",
    "data center",
    "data centre",
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _timestamp() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _assert_safe_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError(f"URL is outside the official metadata allowlist: {url}")
    if any(part in parsed.path for part in FORBIDDEN_PATH_PARTS):
        raise ValueError(f"result-bearing API path is forbidden: {url}")
    lowered = url.lower()
    if any(term.lower() in lowered for term in FORBIDDEN_QUERY_LITERALS):
        raise ValueError(f"data-centre query literal is forbidden: {url}")


def _robots_disallows_root(body: bytes) -> bool:
    text = body.decode("utf-8", errors="replace")
    active_wildcard = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        if name.lower() == "user-agent":
            active_wildcard = value == "*"
        elif (
            active_wildcard
            and name.lower() == "disallow"
            and value.strip() == "/"
        ):
            return True
    return False


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "audit_request_start_interval_seconds": (
                AUDIT_REQUEST_START_INTERVAL_SECONDS
            ),
            "controlled_http_requests": [],
            "direct_request_attempt_cap": MAX_DIRECT_REQUEST_ATTEMPTS,
            "format": "datacenter-atlas-south-korea-audit-working-ledger-v1",
            "result_bearing_search_requests": 0,
            "search_export_requests": 0,
            "source_detail_requests": 0,
            "source_document_requests": 0,
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(
        value.get("controlled_http_requests"), list
    ):
        raise ValueError("working ledger is invalid")
    if value.get("direct_request_attempt_cap") != MAX_DIRECT_REQUEST_ATTEMPTS:
        raise ValueError("working ledger cap differs")
    return value


def _last_start_epoch(ledger: dict[str, Any]) -> float | None:
    rows = ledger["controlled_http_requests"]
    if not rows:
        return None
    value = rows[-1]["started_at"]
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _request(
    request_id: str,
    url: str,
    body_directory: Path,
    previous_start_monotonic: float | None,
    previous_start_epoch: float | None,
) -> tuple[dict[str, Any], float, float]:
    _assert_safe_url(url)
    if previous_start_monotonic is not None:
        remaining = (
            AUDIT_REQUEST_START_INTERVAL_SECONDS
            - (time.monotonic() - previous_start_monotonic)
        )
    elif previous_start_epoch is not None:
        remaining = (
            AUDIT_REQUEST_START_INTERVAL_SECONDS
            - (time.time() - previous_start_epoch)
        )
    else:
        remaining = 0.0
    if remaining > 0:
        time.sleep(remaining)

    start_monotonic = time.monotonic()
    start_epoch = time.time()
    started_at = _timestamp()
    request = Request(
        url,
        headers={"Accept": "*/*", "User-Agent": USER_AGENT},
        method="GET",
    )
    opener = build_opener(_NoRedirect)
    try:
        try:
            response = opener.open(request, timeout=20)
        except HTTPError as error:
            response = error
        body = response.read()
        elapsed = round(time.monotonic() - start_monotonic, 3)
        path = body_directory / f"{request_id}.body"
        path.write_bytes(body)
        row = {
            "body_retained_for_analysis": True,
            "bytes": len(body),
            "content_type": response.headers.get("Content-Type"),
            "elapsed_seconds": elapsed,
            "http_status": response.getcode(),
            "location": response.headers.get("Location"),
            "method": "GET",
            "outcome": "response",
            "redirect_followed": False,
            "request_id": request_id,
            "response_body_received": True,
            "sha256": hashlib.sha256(body).hexdigest(),
            "started_at": started_at,
            "url": url,
        }
    except (TimeoutError, socket.timeout, URLError) as error:
        elapsed = round(time.monotonic() - start_monotonic, 3)
        row = {
            "body_retained_for_analysis": False,
            "bytes": 0,
            "content_type": None,
            "elapsed_seconds": elapsed,
            "error_class": error.__class__.__name__,
            "error_detail": str(
                error.reason if isinstance(error, URLError) else error
            )[:240],
            "http_status": None,
            "location": None,
            "method": "GET",
            "outcome": "network_error",
            "redirect_followed": False,
            "request_id": request_id,
            "response_body_received": False,
            "sha256": hashlib.sha256(b"").hexdigest(),
            "started_at": started_at,
            "url": url,
        }
    return row, start_monotonic, start_epoch


def _robots_gate(
    ledger: dict[str, Any],
    body_directory: Path,
    request_ids: tuple[str, ...],
) -> None:
    by_id = {
        row["request_id"]: row for row in ledger["controlled_http_requests"]
    }
    for request_id in request_ids:
        row = by_id.get(request_id)
        if row is None or row.get("outcome") != "response":
            raise ValueError(f"successful robots audit is required: {request_id}")
        path = body_directory / f"{request_id}.body"
        if not path.is_file():
            raise ValueError(f"robots body is missing: {request_id}")
        if _robots_disallows_root(path.read_bytes()):
            raise ValueError(f"robots disallows root; metadata phase stopped: {request_id}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", type=Path, required=True)
    result.add_argument(
        "--phase",
        choices=(
            "robots",
            "data-go-metadata",
            "eiass-metadata",
            "kogl-metadata",
        ),
        required=True,
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    workspace = arguments.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    body_directory = workspace / "temporary-response-bodies"
    body_directory.mkdir(exist_ok=True)
    ledger_path = workspace / "working-ledger.json"
    ledger = _load_ledger(ledger_path)

    if arguments.phase == "data-go-metadata":
        _robots_gate(ledger, body_directory, ("data_go_robots",))
        planned = DATA_GO_METADATA_REQUESTS
    elif arguments.phase == "eiass-metadata":
        _robots_gate(ledger, body_directory, ("eiass_canonical_robots",))
        planned = EIASS_METADATA_REQUESTS
    elif arguments.phase == "kogl-metadata":
        _robots_gate(ledger, body_directory, ("kogl_robots",))
        planned = KOGL_METADATA_REQUESTS
    else:
        planned = ROBOTS_REQUESTS

    existing_ids = {
        row["request_id"] for row in ledger["controlled_http_requests"]
    }
    planned = tuple(row for row in planned if row[0] not in existing_ids)
    if len(ledger["controlled_http_requests"]) + len(planned) > (
        MAX_DIRECT_REQUEST_ATTEMPTS
    ):
        raise ValueError("direct request cap would be exceeded")

    previous_start_monotonic = None
    previous_start_epoch = _last_start_epoch(ledger)
    for request_id, url in planned:
        row, previous_start_monotonic, previous_start_epoch = _request(
            request_id,
            url,
            body_directory,
            previous_start_monotonic,
            previous_start_epoch,
        )
        ledger["controlled_http_requests"].append(row)
        ledger["direct_request_attempts"] = len(
            ledger["controlled_http_requests"]
        )
        ledger_path.write_bytes(_canonical_json(ledger))

    print(_canonical_json(ledger).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
