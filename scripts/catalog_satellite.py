#!/usr/bin/env python3
"""Query two bounded Sentinel-2 windows and save an exact pair manifest."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Sequence
import urllib.error
import urllib.request


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.satellite_catalog import (
    CatalogQuery,
    Provider,
    build_pair_manifest,
    build_stac_request,
    manifest_json,
)
from datacenter_atlas.satellite_batch import DEFAULT_MAX_RESPONSE_BYTES
from datacenter_atlas.satellite_change import parse_bbox


USER_AGENT = "DataCenterAtlas/0.1 (open research Sentinel catalog pilot)"
RESPONSE_READ_CHUNK_BYTES = 64 * 1024


class CatalogResponseError(ValueError):
    """Raised when an HTTP response cannot be consumed under the byte contract."""


class CatalogResponseTooLarge(CatalogResponseError):
    """Raised before a catalog response can exceed its configured byte cap."""


class _RequestPacer:
    def __init__(self, minimum_interval_seconds: float) -> None:
        self.minimum_interval_seconds = minimum_interval_seconds
        self.last_started: float | None = None

    def wait(self) -> None:
        if self.last_started is not None:
            remaining = self.minimum_interval_seconds - (
                time.monotonic() - self.last_started
            )
            if remaining > 0:
                time.sleep(remaining)
        self.last_started = time.monotonic()


def _declared_content_length(response: Any) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = get_all("Content-Length") or []
    else:
        value = headers.get("Content-Length")
        values = [] if value is None else [value]
    if not values:
        return None
    if any(not isinstance(value, str) for value in values):
        raise CatalogResponseError("catalog response Content-Length is invalid")
    tokens = [token.strip() for value in values for token in value.split(",")]
    if not tokens or any(
        not token.isascii() or not token.isdecimal() for token in tokens
    ):
        raise CatalogResponseError("catalog response Content-Length is invalid")
    lengths = {int(token) for token in tokens}
    if len(lengths) != 1:
        raise CatalogResponseError("catalog response Content-Length values conflict")
    return lengths.pop()


def _read_bounded_response(response: Any, max_response_bytes: int) -> bytes:
    if (
        isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or max_response_bytes <= 0
    ):
        raise CatalogResponseError("max_response_bytes must be a positive integer")
    declared = _declared_content_length(response)
    if declared is not None and declared > max_response_bytes:
        raise CatalogResponseTooLarge(
            "catalog response declared "
            f"{declared} bytes, exceeding the {max_response_bytes}-byte cap"
        )

    body = bytearray()
    while True:
        remaining_with_sentinel = max_response_bytes + 1 - len(body)
        chunk = response.read(min(RESPONSE_READ_CHUNK_BYTES, remaining_with_sentinel))
        if not chunk:
            if declared is not None and len(body) != declared:
                raise CatalogResponseError(
                    "catalog response Content-Length declared "
                    f"{declared} bytes but streamed {len(body)} bytes"
                )
            return bytes(body)
        if not isinstance(chunk, bytes):
            raise CatalogResponseError("catalog response read returned non-byte data")
        body.extend(chunk)
        if len(body) > max_response_bytes:
            raise CatalogResponseTooLarge(
                "catalog response body exceeded the "
                f"{max_response_bytes}-byte cap while streaming"
            )


def _post(
    request_plan: dict,
    *,
    timeout: float,
    retries: int,
    user_agent: str,
    pacer: _RequestPacer,
    max_response_bytes: int,
) -> bytes:
    body = json.dumps(request_plan["payload"], sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        request_plan["url"],
        data=body,
        headers={**request_plan["headers"], "User-Agent": user_agent},
        method="POST",
    )
    for attempt in range(retries + 1):
        pacer.wait()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return _read_bounded_response(response, max_response_bytes)
        except urllib.error.HTTPError as error:
            error.close()
            if attempt == retries:
                raise
            time.sleep(min(2**attempt, 8))
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
            time.sleep(min(2**attempt, 8))
    raise AssertionError("retry loop exhausted")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--provider", choices=[item.value for item in Provider], default=Provider.EARTH_SEARCH.value)
    result.add_argument("--bbox", required=True, type=parse_bbox)
    result.add_argument("--baseline-start", required=True)
    result.add_argument("--baseline-end", required=True)
    result.add_argument("--baseline-target", required=True)
    result.add_argument("--current-start", required=True)
    result.add_argument("--current-end", required=True)
    result.add_argument("--current-target", required=True)
    result.add_argument("--max-cloud-cover", type=float, default=20.0)
    result.add_argument("--limit", type=int, default=100)
    result.add_argument("--temporal-window-days", type=int, default=45)
    result.add_argument("--timeout", type=float, default=60.0)
    result.add_argument("--retries", type=int, default=2)
    result.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        help=(
            "Maximum bytes accepted for each STAC response "
            f"(default: {DEFAULT_MAX_RESPONSE_BYTES})"
        ),
    )
    result.add_argument("--user-agent", default=USER_AGENT)
    result.add_argument(
        "--minimum-interval-seconds",
        type=float,
        default=0.0,
        help="Minimum spacing between HTTP request starts (default: 0)",
    )
    result.add_argument("--output-dir", required=True, type=Path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if (
        not math.isfinite(arguments.timeout)
        or arguments.timeout <= 0
        or arguments.retries < 0
        or arguments.max_response_bytes <= 0
        or not math.isfinite(arguments.minimum_interval_seconds)
        or arguments.minimum_interval_seconds < 0
    ):
        raise SystemExit(
            "timeout and max response bytes must be positive; retries and minimum "
            "interval must be non-negative"
        )
    if not arguments.user_agent.strip() or any(
        character in arguments.user_agent for character in "\r\n"
    ):
        raise SystemExit("user-agent must be non-empty and contain no line breaks")
    arguments.user_agent = arguments.user_agent.strip()
    pacer = _RequestPacer(arguments.minimum_interval_seconds)
    provider = Provider(arguments.provider)
    baseline_query = CatalogQuery(
        arguments.bbox,
        arguments.baseline_start,
        arguments.baseline_end,
        arguments.max_cloud_cover,
        arguments.limit,
    )
    current_query = CatalogQuery(
        arguments.bbox,
        arguments.current_start,
        arguments.current_end,
        arguments.max_cloud_cover,
        arguments.limit,
    )
    baseline_raw = _post(
        build_stac_request(provider, baseline_query),
        timeout=arguments.timeout,
        retries=arguments.retries,
        user_agent=arguments.user_agent,
        pacer=pacer,
        max_response_bytes=arguments.max_response_bytes,
    )
    current_raw = _post(
        build_stac_request(provider, current_query),
        timeout=arguments.timeout,
        retries=arguments.retries,
        user_agent=arguments.user_agent,
        pacer=pacer,
        max_response_bytes=arguments.max_response_bytes,
    )
    retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    manifest = build_pair_manifest(
        provider,
        baseline_query,
        baseline_raw,
        current_query,
        current_raw,
        baseline_date=arguments.baseline_target,
        current_date=arguments.current_target,
        retrieved_at=retrieved_at,
        temporal_window_days=arguments.temporal_window_days,
    )
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "baseline-response.json").write_bytes(baseline_raw)
    (arguments.output_dir / "current-response.json").write_bytes(current_raw)
    manifest_path = arguments.output_dir / "manifest.json"
    manifest_path.write_text(manifest_json(manifest), encoding="utf-8")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path.resolve()),
                "selected_ids": manifest["selected_ids"],
                "retrieved_at": manifest["retrieved_at"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
