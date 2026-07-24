#!/usr/bin/env python3
"""Probe and build the restricted Germany UVP-Verbund assessment."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.germany_uvp_verbund import (
    GermanyUVPVerbundError,
    MAX_NETWORK_REQUESTS,
    MIN_REQUEST_INTERVAL_SECONDS,
    OPENSEARCH_DESCRIPTOR_URL,
    PINNED_RETRIEVAL_INVENTORY,
    RELEASE_ID,
    STATE_ALIAS_DESCRIPTOR_URL,
    canonical_json,
    search_url,
    sha256_bytes,
    source_definition,
    validate_release_bundle,
    validate_retrieval_inventory,
    write_release_bundle,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAGING = PROJECT_ROOT / ".staging" / RELEASE_ID
DEFAULT_OUTPUT = PROJECT_ROOT / "source_assessments" / RELEASE_ID
DEFAULT_DEFINITION = PROJECT_ROOT / "sources" / f"{RELEASE_ID}.json"
USER_AGENT = "datacenter-atlas-germany-uvp-audit/1.0"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    result.add_argument("--capture-only", action="store_true")
    result.add_argument("--resume", action="store_true")
    result.add_argument("--timeout", type=float, default=30.0)
    result.add_argument(
        "--min-request-interval",
        type=float,
        default=MIN_REQUEST_INTERVAL_SECONDS,
    )
    result.add_argument(
        "--max-network-requests", type=int, default=MAX_NETWORK_REQUESTS
    )
    result.add_argument("--max-attempts", type=int, default=3)
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class BoundedProbe:
    def __init__(
        self,
        *,
        timeout: float,
        minimum_interval: float,
        request_cap: int,
        maximum_attempts: int,
    ) -> None:
        if timeout <= 0 or minimum_interval < 1.0:
            raise GermanyUVPVerbundError(
                "timeout must be positive and interval at least one second"
            )
        if not 1 <= request_cap <= MAX_NETWORK_REQUESTS:
            raise GermanyUVPVerbundError("network request cap must be between 1 and 8")
        if maximum_attempts < 1:
            raise GermanyUVPVerbundError("maximum attempts must be positive")
        self.timeout = timeout
        self.minimum_interval = minimum_interval
        self.request_cap = request_cap
        self.maximum_attempts = maximum_attempts
        self.request_count = 0
        self._last_started: float | None = None
        self._opener = build_opener(_NoRedirect())

    def _pace(self) -> None:
        if self._last_started is None:
            return
        wait = self.minimum_interval - (time.monotonic() - self._last_started)
        if wait > 0:
            time.sleep(wait)

    def fetch(self, request_id: str, url: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.maximum_attempts + 1):
            if self.request_count >= self.request_cap:
                raise GermanyUVPVerbundError("network request cap reached")
            if attempt > 1:
                time.sleep(min(2 ** (attempt - 1), 8))
            self._pace()
            self._last_started = time.monotonic()
            self.request_count += 1
            request = Request(
                url,
                headers={
                    "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "identity",
                    "User-Agent": USER_AGENT,
                },
            )
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
                    status = response.status
                    headers = response.headers
            except HTTPError as error:
                body = error.read()
                status = error.code
                headers = error.headers
            except (URLError, TimeoutError) as error:
                last_error = error
                if attempt == self.maximum_attempts:
                    raise GermanyUVPVerbundError(f"request failed: {url}") from error
                continue

            record: dict[str, Any] = {
                "attempt": attempt,
                "body_retained": False,
                "bytes": len(body),
                "content_type": headers.get_content_type(),
                "http_status": status,
                "method": "GET",
                "request_id": request_id,
                "response_date": (
                    parsedate_to_datetime(headers["Date"])
                    .astimezone(UTC)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                    if headers.get("Date")
                    else _now()
                ),
                "sha256": sha256_bytes(body),
                "url": url,
            }
            if headers.get("Location"):
                record["location"] = headers["Location"]
            if status in {429, 401, 403}:
                return record
            if status in {500, 502, 503, 504} and attempt < self.maximum_attempts:
                last_error = GermanyUVPVerbundError(f"HTTP {status}")
                continue
            return record
        raise GermanyUVPVerbundError(f"request failed: {url}") from last_error


def _capture(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.staging_dir.exists():
        raise GermanyUVPVerbundError("staging directory already exists")
    arguments.staging_dir.mkdir(parents=True)
    probe = BoundedProbe(
        timeout=arguments.timeout,
        minimum_interval=arguments.min_request_interval,
        request_cap=arguments.max_network_requests,
        maximum_attempts=arguments.max_attempts,
    )
    requests = [
        probe.fetch(
            "closed_query_probe_rechenzentrum", search_url("Rechenzentrum")
        )
    ]
    if requests[0]["http_status"] == 429:
        requests.append(
            probe.fetch("opensearch_descriptor_probe", OPENSEARCH_DESCRIPTOR_URL)
        )
        requests.append(
            probe.fetch(
                "niedersachsen_alias_descriptor_probe",
                STATE_ALIAS_DESCRIPTOR_URL,
            )
        )

    inventory = dict(PINNED_RETRIEVAL_INVENTORY)
    inventory["capture_completed_at"] = _now()
    inventory["controlled_http_requests"] = requests
    inventory["network_requests"] = probe.request_count
    inventory["maximum_network_requests"] = arguments.max_network_requests
    inventory["minimum_request_interval_seconds"] = arguments.min_request_interval
    destination = arguments.staging_dir / "retrieval-inventory.json"
    destination.write_bytes(canonical_json(inventory))
    return inventory


def _load_capture(staging: Path) -> dict[str, Any]:
    path = staging / "retrieval-inventory.json"
    if path.is_symlink() or not path.is_file():
        raise GermanyUVPVerbundError("staging retrieval inventory is missing")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GermanyUVPVerbundError("staging retrieval inventory is invalid") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise GermanyUVPVerbundError("staging inventory must be canonical JSON")
    return value


def _write_definition(path: Path) -> None:
    expected = canonical_json(source_definition())
    if path.exists():
        if path.is_symlink() or path.read_bytes() != expected:
            raise GermanyUVPVerbundError("existing definition differs")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(expected)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.capture_only and arguments.resume:
        raise GermanyUVPVerbundError("capture-only and resume are mutually exclusive")
    inventory = _load_capture(arguments.staging_dir) if arguments.resume else _capture(arguments)
    print(canonical_json(inventory).decode("utf-8"), end="")
    if arguments.capture_only:
        return 0
    validate_retrieval_inventory(inventory)
    _write_definition(arguments.definition)
    write_release_bundle(inventory, arguments.output)
    validate_release_bundle(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
