#!/usr/bin/env python3
"""Fetch the three allowed Japan MOE casebook sources with exact accounting."""

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


MIN_REQUEST_START_INTERVAL_SECONDS = 3.2
MAX_DIRECT_REQUEST_ATTEMPTS = 12
USER_AGENT = (
    "DataCenterAtlasSourceAssessment/1.0 "
    "(Japan-MOE-casebook; three-source bounded audit)"
)

TERMS_URL = "https://www.env.go.jp/mail.html"
LANDING_URL = (
    "https://www.env.go.jp/earth/earth/ondanka/data-center.html"
)
CASEBOOK_URL = "https://www.env.go.jp/content/000400242.pdf"

REQUESTS = (
    ("moe_terms", TERMS_URL, "terms.html"),
    ("moe_landing", LANDING_URL, "landing.html"),
    ("moe_casebook", CASEBOOK_URL, "casebook.pdf"),
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


def _assert_allowed(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.env.go.jp":
        raise ValueError("only the official www.env.go.jp origin is allowed")
    if url not in {TERMS_URL, LANDING_URL, CASEBOOK_URL}:
        raise ValueError("URL is not one of the three approved starting sources")


def _terms_gate(body: bytes) -> None:
    for marker in ("公共データ利用規約", "PDL1.0", "出典"):
        if marker.encode("utf-8") not in body:
            raise ValueError(f"terms gate marker missing: {marker}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", type=Path, required=True)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    workspace = arguments.workspace.resolve()
    if workspace.exists() or workspace.is_symlink():
        raise ValueError("audit workspace must not already exist")
    workspace.mkdir(parents=True)
    body_directory = workspace / "raw"
    body_directory.mkdir()
    ledger: dict[str, Any] = {
        "browser_proxy_origin_request_count": None,
        "browser_proxy_research_excluded_from_direct_request_arithmetic": True,
        "browser_proxy_research_used": True,
        "controlled_http_requests": [],
        "direct_request_attempt_cap": MAX_DIRECT_REQUEST_ATTEMPTS,
        "format": "datacenter-atlas-japan-moe-working-ledger-v1",
        "minimum_request_start_interval_seconds": (
            MIN_REQUEST_START_INTERVAL_SECONDS
        ),
    }
    opener = build_opener(_NoRedirect)
    previous_start: float | None = None
    for request_id, url, filename in REQUESTS:
        _assert_allowed(url)
        if len(ledger["controlled_http_requests"]) >= (
            MAX_DIRECT_REQUEST_ATTEMPTS
        ):
            raise ValueError("direct request cap reached")
        if previous_start is not None:
            remaining = MIN_REQUEST_START_INTERVAL_SECONDS - (
                time.monotonic() - previous_start
            )
            if remaining > 0:
                time.sleep(remaining)
        previous_start = time.monotonic()
        started_at = _timestamp()
        request = Request(
            url,
            headers={"Accept": "*/*", "User-Agent": USER_AGENT},
            method="GET",
        )
        try:
            try:
                response = opener.open(request, timeout=30)
            except HTTPError as error:
                response = error
            body = response.read()
            elapsed = round(time.monotonic() - previous_start, 3)
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
            (body_directory / filename).write_bytes(body)
            if request_id == "moe_terms":
                if response.getcode() != 200:
                    raise ValueError("terms request did not return HTTP 200")
                _terms_gate(body)
        except (TimeoutError, socket.timeout, URLError) as error:
            elapsed = round(time.monotonic() - previous_start, 3)
            row = {
                "body_retained_for_analysis": False,
                "bytes": 0,
                "content_type": None,
                "elapsed_seconds": elapsed,
                "error_class": error.__class__.__name__,
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
        ledger["controlled_http_requests"].append(row)
        ledger["direct_request_attempts"] = len(
            ledger["controlled_http_requests"]
        )
        (workspace / "working-ledger.json").write_bytes(
            _canonical_json(ledger)
        )
        if row["outcome"] != "response" or row["http_status"] != 200:
            raise ValueError(f"source request failed closed: {request_id}")
    print(_canonical_json(ledger).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
