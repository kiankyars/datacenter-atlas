"""Isolated Scrutica facility discovery fetch and offline import.

Scrutica is a useful compiled discovery surface, but it is licensed under
CC-BY-SA-4.0 and some of its aggregate counts include records that Scrutica
cannot redistribute individually.  This module therefore keeps Scrutica in a
separate SQLite database and never treats a Scrutica row as independent
corroboration of its named upstream source.

The fetcher first proves the public directory inventory, preserving every raw
HTML page and its hash.  It then calls the documented, unauthenticated MCP
facility tool serially, checkpoints the exact SSE response and parsed JSON, and
can resume without repeating completed requests.  The importer is offline and
fails closed on incomplete bundles unless partial import is explicitly enabled.
It also imports only Scrutica's explicit data-centre facility types; mixed
semiconductor and ambiguous records remain unchanged in the raw fetch bundle.
"""

from __future__ import annotations

from collections import Counter
import email.utils
import hashlib
import json
import math
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .adapters import ImportResult
from .models import (
    CapacityEstimate,
    CapacityMetric,
    CapacityStage,
    EstimateMethod,
    Evidence,
    EvidenceKind,
    Facility,
    LifecycleObservation,
    LifecycleStatus,
    OperatingModel,
    Workload,
)
from .repository import (
    add_capacity,
    add_evidence,
    add_facility,
    add_lifecycle,
    add_operating_model,
    add_snapshot,
    add_workload,
    stable_id,
    utc_now,
)


SCRUTICA_DIRECTORY_URL = "https://scrutica.com/facilities"
SCRUTICA_DIRECTORY_SORT = "name"
SCRUTICA_DIRECTORY_DIRECTION = "asc"
SCRUTICA_MCP_URL = "https://scrutica.com/api/mcp"
SCRUTICA_LICENSE = "CC-BY-SA-4.0"
SCRUTICA_ATTRIBUTION = "Scrutica data, licensed under CC BY-SA 4.0"
SCRUTICA_PUBLISHER = "Scrutica"
SCRUTICA_SOURCE_FAMILY = "scrutica"
SCRUTICA_MANIFEST = "manifest.json"
SCRUTICA_MANIFEST_SCHEMA_VERSION = 2
SCRUTICA_EXPECTED_TRACKED = 4_550
SCRUTICA_EXPECTED_BROWSABLE = 4_234
SCRUTICA_EXPECTED_AGGREGATE_ONLY = 316
SCRUTICA_EXPECTED_PAGES = 85
SCRUTICA_PAGE_SIZE = 50
SCRUTICA_DEFAULT_INTERVAL_SECONDS = 1.1
SCRUTICA_DATA_CENTER_SCOPE_POLICY = "scrutica_facility_type_allowlist_v1"
SCRUTICA_OFFICIAL_FACILITY_TYPES = frozenset(
    {
        "ai_training",
        "colocation",
        "edge",
        "hpc_center",
        "hyperscale_dc",
        "logic_fab",
        "memory_fab",
        "other",
        "packaging",
    }
)
SCRUTICA_DATA_CENTER_FACILITY_TYPES = frozenset(
    {"ai_training", "colocation", "edge", "hpc_center", "hyperscale_dc"}
)
SCRUTICA_NON_DATA_CENTER_FACILITY_TYPES = frozenset(
    {"logic_fab", "memory_fab", "packaging"}
)
SCRUTICA_REVIEW_REQUIRED_FACILITY_TYPES = frozenset({"other"})
SCRUTICA_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research; "
    "+https://github.com/kiankyars/semiconductors)"
)
_FACILITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_FACILITY_PATH_RE = re.compile(r"^/facilities/([A-Za-z0-9][A-Za-z0-9-]*)$")
_NORMALIZE_SOURCE_RE = re.compile(r"[^a-z0-9]+")
_TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
_DIRECTORY_BODY_LIMIT = 32 * 1024 * 1024
_MCP_BODY_LIMIT = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DirectorySpec:
    """Pinned public directory inventory used to detect silent coverage drift."""

    tracked: int = SCRUTICA_EXPECTED_TRACKED
    browsable: int = SCRUTICA_EXPECTED_BROWSABLE
    aggregate_only: int = SCRUTICA_EXPECTED_AGGREGATE_ONLY
    pages: int = SCRUTICA_EXPECTED_PAGES
    page_size: int = SCRUTICA_PAGE_SIZE

    def __post_init__(self) -> None:
        if min(
            self.tracked,
            self.browsable,
            self.aggregate_only,
            self.pages,
            self.page_size,
        ) <= 0:
            raise ValueError("Scrutica directory counts must be positive")
        if self.browsable + self.aggregate_only != self.tracked:
            raise ValueError(
                "Scrutica browsable plus aggregate-only counts must equal tracked count"
            )
        expected_pages = (self.browsable + self.page_size - 1) // self.page_size
        if self.pages != expected_pages:
            raise ValueError(
                "Scrutica page count does not match browsable count and page size"
            )

    @property
    def last_page_size(self) -> int:
        return self.browsable - self.page_size * (self.pages - 1)

    def as_dict(self) -> dict[str, int]:
        return {
            "tracked": self.tracked,
            "browsable": self.browsable,
            "aggregate_only": self.aggregate_only,
            "pages": self.pages,
            "page_size": self.page_size,
        }


SCRUTICA_DIRECTORY_SPEC = DirectorySpec()


@dataclass(frozen=True, slots=True)
class DirectoryPage:
    page: int
    total_pages: int
    tracked: int
    browsable: int
    aggregate_only: int
    facility_ids: tuple[str, ...]


class _DirectoryHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.facility_ids: list[str] = []
        self.text: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth or tag != "a":
            return
        href = dict(attrs).get("href")
        if not isinstance(href, str):
            return
        path = urllib.parse.urlsplit(href).path
        match = _FACILITY_PATH_RE.fullmatch(path)
        if match:
            self.facility_ids.append(match.group(1))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.text.append(data.strip())


def _single_integer_match(text: str, patterns: Iterable[str], field: str) -> int:
    values: set[int] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            values.add(int(match.group(1).replace(",", "")))
    if len(values) != 1:
        rendered = ", ".join(str(value) for value in sorted(values)) or "none"
        raise ValueError(f"Scrutica directory {field} count was ambiguous: {rendered}")
    return values.pop()


def parse_directory_page(raw: bytes, *, expected_page: int) -> DirectoryPage:
    """Parse one server-rendered directory page without executing JavaScript."""
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("Scrutica directory response must contain raw bytes")
    if expected_page <= 0:
        raise ValueError("Scrutica expected page must be positive")
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Scrutica directory response is not UTF-8") from error
    parser = _DirectoryHTMLParser()
    parser.feed(html)
    parser.close()
    visible = " ".join(parser.text)

    page_matches = {
        (int(match.group(1)), int(match.group(2)))
        for match in re.finditer(
            r"\bPage\s+([0-9][0-9,]*)\s+of\s+([0-9][0-9,]*)\b",
            visible,
            flags=re.IGNORECASE,
        )
    }
    if len(page_matches) != 1:
        raise ValueError("Scrutica directory page marker was missing or ambiguous")
    page, total_pages = page_matches.pop()
    if page != expected_page:
        raise ValueError(
            f"Scrutica directory returned page {page}, expected {expected_page}"
        )

    browsable = _single_integer_match(
        visible,
        (
            r"\bof\s+([0-9][0-9,]*)\s*\(\s*[0-9][0-9,]*\s+tracked",
            r"\b([0-9][0-9,]*)\s+individually\s+browsable\b",
        ),
        "browsable",
    )
    tracked = _single_integer_match(
        visible,
        (
            r"\b([0-9][0-9,]*)\s+tracked\b",
            r"\b([0-9][0-9,]*)\s+facilities\s+tracked\b",
        ),
        "tracked",
    )
    aggregate_only = _single_integer_match(
        visible,
        (
            r"\b([0-9][0-9,]*)\s+licensed-source\s+rows\s+in\s+aggregates\s+only\b",
            r"\b([0-9][0-9,]*)\s+sourced\s+from\s+licensed\s+databases",
        ),
        "aggregate-only",
    )
    facility_ids = tuple(dict.fromkeys(parser.facility_ids))
    if len(facility_ids) != len(parser.facility_ids):
        raise ValueError("Scrutica directory page repeats a facility link")
    if not facility_ids:
        raise ValueError("Scrutica directory page contains no facility links")
    return DirectoryPage(
        page=page,
        total_pages=total_pages,
        tracked=tracked,
        browsable=browsable,
        aggregate_only=aggregate_only,
        facility_ids=facility_ids,
    )


def _require_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _bundle_file(root: Path, relative: str, label: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"{label} has an unsafe bundle path")
    candidate = root
    for part in relative_path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"{label} may not be a symlink")
    if not candidate.is_file():
        raise ValueError(f"{label} is missing")
    if root.resolve() not in candidate.resolve().parents:
        raise ValueError(f"{label} escapes the Scrutica bundle")
    return candidate


def _write_bytes_atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)
    directory_descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _json_bytes(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_json_atomic(path: Path, document: Any) -> None:
    _write_bytes_atomic(path, _json_bytes(document))


def _read_limited(response: Any, limit: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise ValueError(f"{label} response did not return raw bytes")
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ValueError(f"{label} response exceeded {limit} bytes")
    return b"".join(chunks)


def _retry_after_seconds(headers: Any, now: Callable[[], float]) -> float | None:
    value = headers.get("Retry-After") if headers is not None else None
    if value is None:
        return None
    value = str(value).strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, parsed.timestamp() - now())


def _parse_sse_events(raw: bytes) -> list[tuple[str, str]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Scrutica MCP response is not UTF-8 SSE") from error
    events: list[tuple[str, str]] = []
    event_name = "message"
    data_lines: list[str] = []

    def finish() -> None:
        nonlocal event_name, data_lines
        if data_lines:
            events.append((event_name, "\n".join(data_lines)))
        event_name = "message"
        data_lines = []

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line:
            finish()
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    finish()
    return events


def parse_mcp_facility_response(
    raw: bytes,
    *,
    request_id: str,
    facility_id: str,
) -> dict[str, Any]:
    """Validate one JSON-RPC SSE response and return its facility document."""
    if not _FACILITY_ID_RE.fullmatch(facility_id):
        raise ValueError("invalid Scrutica facility ID")
    events = _parse_sse_events(raw)
    messages = [data for event, data in events if event == "message"]
    if len(messages) != 1:
        raise ValueError("Scrutica MCP response must contain exactly one message event")
    try:
        envelope = json.loads(messages[0])
    except json.JSONDecodeError as error:
        raise ValueError("Scrutica MCP message is not valid JSON") from error
    if not isinstance(envelope, dict) or envelope.get("jsonrpc") != "2.0":
        raise ValueError("Scrutica MCP response has an invalid JSON-RPC envelope")
    if envelope.get("id") != request_id:
        raise ValueError("Scrutica MCP response ID does not match its request")
    if "error" in envelope:
        raise ValueError(f"Scrutica MCP returned an error: {envelope['error']!r}")
    result = envelope.get("result")
    if not isinstance(result, dict):
        raise ValueError("Scrutica MCP response is missing result")
    content = result.get("content")
    if not isinstance(content, list):
        raise ValueError("Scrutica MCP result content must be a list")
    text_blocks = [
        item.get("text")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    if len(text_blocks) != 1 or not isinstance(text_blocks[0], str):
        raise ValueError("Scrutica MCP result must contain exactly one text block")
    try:
        document = json.loads(text_blocks[0])
    except json.JSONDecodeError as error:
        raise ValueError("Scrutica MCP text block is not valid JSON") from error
    if not isinstance(document, dict):
        raise ValueError("Scrutica facility document must be a JSON object")
    facility = document.get("facility")
    if not isinstance(facility, dict) or facility.get("id") != facility_id:
        raise ValueError("Scrutica facility document ID does not match its request")
    expected_url = f"{SCRUTICA_DIRECTORY_URL}/{facility_id}"
    if document.get("url") != expected_url:
        raise ValueError("Scrutica facility document has a non-canonical facility URL")
    return document


def _request_id(facility_id: str) -> str:
    return f"scrutica-facility:{facility_id}"


def _directory_ordering_contract() -> dict[str, str]:
    return {
        "sort": SCRUTICA_DIRECTORY_SORT,
        "dir": SCRUTICA_DIRECTORY_DIRECTION,
    }


def _directory_page_url(directory_url: str, page: int) -> str:
    if page <= 0:
        raise ValueError("Scrutica directory page must be positive")
    query = urllib.parse.urlencode(
        (
            ("sort", SCRUTICA_DIRECTORY_SORT),
            ("dir", SCRUTICA_DIRECTORY_DIRECTION),
            ("page", page),
        )
    )
    return f"{directory_url.rstrip('/')}?{query}"


def _manifest_template(spec: DirectorySpec, created_at: str) -> dict[str, Any]:
    pages = {
        str(page): {"state": "pending", "attempts": 0, "failures": []}
        for page in range(1, spec.pages + 1)
    }
    return {
        "schema_version": SCRUTICA_MANIFEST_SCHEMA_VERSION,
        "pipeline": "scrutica_facility_discovery_fetch",
        "state": "directory_pending",
        "created_at": created_at,
        "updated_at": created_at,
        "source": {
            "directory_url": SCRUTICA_DIRECTORY_URL,
            "mcp_url": SCRUTICA_MCP_URL,
            "publisher": SCRUTICA_PUBLISHER,
            "license": SCRUTICA_LICENSE,
            "attribution": SCRUTICA_ATTRIBUTION,
            "source_family": SCRUTICA_SOURCE_FAMILY,
            "independent_corroboration": False,
            "redistribution_scope": "isolated_cc_by_sa_discovery_database",
        },
        "directory": {
            "expected": spec.as_dict(),
            "ordering": _directory_ordering_contract(),
            "state": "pending",
            "pages": pages,
            "facility_ids": [],
            "facility_ids_sha256": None,
        },
        "records": {},
        "summary": {
            "tracked": spec.tracked,
            "browsable": spec.browsable,
            "aggregate_only": spec.aggregate_only,
            "directory_pages_completed": 0,
            "records_completed": 0,
            "records_failed": 0,
            "records_pending": spec.browsable,
        },
    }


def _validate_manifest_header(document: Any, spec: DirectorySpec) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("Scrutica manifest must be a JSON object")
    expected = {
        "schema_version": SCRUTICA_MANIFEST_SCHEMA_VERSION,
        "pipeline": "scrutica_facility_discovery_fetch",
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise ValueError(f"Scrutica manifest has unexpected {key}")
    source = document.get("source")
    expected_source = {
        "directory_url": SCRUTICA_DIRECTORY_URL,
        "mcp_url": SCRUTICA_MCP_URL,
        "publisher": SCRUTICA_PUBLISHER,
        "license": SCRUTICA_LICENSE,
        "attribution": SCRUTICA_ATTRIBUTION,
        "source_family": SCRUTICA_SOURCE_FAMILY,
        "independent_corroboration": False,
        "redistribution_scope": "isolated_cc_by_sa_discovery_database",
    }
    if source != expected_source:
        raise ValueError("Scrutica manifest source/rights boundary does not match")
    directory = document.get("directory")
    if not isinstance(directory, dict) or directory.get("expected") != spec.as_dict():
        raise ValueError("Scrutica manifest directory pin does not match")
    if directory.get("ordering") != _directory_ordering_contract():
        raise ValueError("Scrutica manifest directory ordering contract does not match")
    _require_timestamp(document.get("created_at"), "Scrutica manifest created_at")
    _require_timestamp(document.get("updated_at"), "Scrutica manifest updated_at")
    return document


def _update_summary(document: dict[str, Any], spec: DirectorySpec) -> None:
    pages = document["directory"]["pages"]
    records = document["records"]
    completed = sum(task.get("state") == "completed" for task in records.values())
    failed = sum(task.get("state") == "failed" for task in records.values())
    pending = spec.browsable - completed - failed
    document["summary"] = {
        "tracked": spec.tracked,
        "browsable": spec.browsable,
        "aggregate_only": spec.aggregate_only,
        "directory_pages_completed": sum(
            task.get("state") == "completed" for task in pages.values()
        ),
        "records_completed": completed,
        "records_failed": failed,
        "records_pending": pending,
    }
    directory_complete = (
        document["directory"].get("state") == "completed"
        and len(document["directory"].get("facility_ids", [])) == spec.browsable
    )
    if directory_complete and completed == spec.browsable and not failed:
        document["state"] = "completed"
    elif directory_complete:
        document["state"] = "incomplete"
    else:
        document["state"] = "directory_pending"


class ScruticaFetcher:
    """Resumable, rate-limited Scrutica directory and MCP facility fetcher."""

    def __init__(
        self,
        *,
        spec: DirectorySpec = SCRUTICA_DIRECTORY_SPEC,
        directory_url: str = SCRUTICA_DIRECTORY_URL,
        mcp_url: str = SCRUTICA_MCP_URL,
        user_agent: str = SCRUTICA_USER_AGENT,
        timeout: float = 60.0,
        interval_seconds: float = SCRUTICA_DEFAULT_INTERVAL_SECONDS,
        max_attempts: int = 3,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
        timestamp: Callable[[], str] = utc_now,
    ) -> None:
        for url, label in ((directory_url, "directory"), (mcp_url, "MCP")):
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname != "scrutica.com":
                raise ValueError(f"Scrutica {label} URL must use https://scrutica.com")
        if not user_agent.strip():
            raise ValueError("a transparent User-Agent is required")
        if timeout <= 0:
            raise ValueError("Scrutica timeout must be positive")
        if interval_seconds < SCRUTICA_DEFAULT_INTERVAL_SECONDS:
            raise ValueError(
                f"Scrutica MCP interval must be at least {SCRUTICA_DEFAULT_INTERVAL_SECONDS}s"
            )
        if max_attempts <= 0:
            raise ValueError("Scrutica max_attempts must be positive")
        self.spec = spec
        self.directory_url = directory_url.rstrip("/")
        self.mcp_url = mcp_url
        self.user_agent = user_agent
        self.timeout = timeout
        self.interval_seconds = interval_seconds
        self.max_attempts = max_attempts
        self.opener = opener
        self.sleep = sleep
        self.monotonic = monotonic
        self.wall_time = wall_time
        self.timestamp = timestamp
        self._last_mcp_started: float | None = None

    def _checkpoint(
        self, output: Path, document: dict[str, Any], *, timestamp: str | None = None
    ) -> None:
        document["updated_at"] = _require_timestamp(
            timestamp or self.timestamp(), "Scrutica checkpoint timestamp"
        )
        _update_summary(document, self.spec)
        _write_json_atomic(output / SCRUTICA_MANIFEST, document)

    def _new_or_existing_manifest(
        self, output: Path, *, created_at: str | None
    ) -> dict[str, Any]:
        manifest_path = output / SCRUTICA_MANIFEST
        if manifest_path.exists():
            if manifest_path.is_symlink():
                raise ValueError("Scrutica manifest may not be a symlink")
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            return _validate_manifest_header(document, self.spec)
        unexpected = list((output / "directory").glob("*.html")) + list(
            (output / "records").glob("*")
        )
        if unexpected:
            raise ValueError(
                "Scrutica raw files exist without a manifest; refusing ambiguous resume"
            )
        checkpoint_time = _require_timestamp(
            created_at or self.timestamp(), "Scrutica created_at"
        )
        document = _manifest_template(self.spec, checkpoint_time)
        self._checkpoint(output, document, timestamp=checkpoint_time)
        return document

    def _open(self, request: urllib.request.Request, label: str, limit: int) -> bytes:
        with self.opener(request, timeout=self.timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else request.full_url
            parsed = urllib.parse.urlsplit(str(final_url))
            if parsed.scheme != "https" or parsed.hostname != "scrutica.com":
                raise ValueError(f"{label} redirected outside https://scrutica.com")
            return _read_limited(response, limit, label)

    def _backoff(self, attempt: int, error: BaseException) -> float:
        if isinstance(error, urllib.error.HTTPError) and error.code == 429:
            retry_after = _retry_after_seconds(error.headers, self.wall_time)
            if retry_after is not None:
                return retry_after
        return min(30.0, float(2 ** (attempt - 1)))

    @staticmethod
    def _transient(error: BaseException) -> bool:
        if isinstance(error, urllib.error.HTTPError):
            return error.code in _TRANSIENT_HTTP_CODES
        return isinstance(error, (urllib.error.URLError, TimeoutError))

    def _directory_request(self, page: int) -> urllib.request.Request:
        return urllib.request.Request(
            _directory_page_url(self.directory_url, page),
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )

    def _mcp_request(self, facility_id: str, request_id: str) -> urllib.request.Request:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": "scrutica_get_facility",
                    "arguments": {"facility_id": facility_id},
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return urllib.request.Request(
            self.mcp_url,
            data=body,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": "2025-11-25",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )

    def _verify_completed_page(
        self, output: Path, page: int, task: Mapping[str, Any]
    ) -> DirectoryPage:
        if task.get("url") != self._directory_request(page).full_url:
            raise ValueError(f"Scrutica page {page} checkpoint has unexpected URL")
        relative = task.get("file")
        if relative != f"directory/page-{page:03d}.html":
            raise ValueError(f"Scrutica page {page} checkpoint has unexpected path")
        path = _bundle_file(output, relative, f"Scrutica page {page} raw HTML")
        size, digest = _hash_file(path)
        if size != task.get("bytes") or digest != task.get("sha256"):
            raise ValueError(f"Scrutica page {page} raw HTML hash does not match")
        parsed = parse_directory_page(path.read_bytes(), expected_page=page)
        if list(parsed.facility_ids) != task.get("facility_ids"):
            raise ValueError(f"Scrutica page {page} parsed IDs changed")
        return parsed

    def _fetch_directory(
        self, output: Path, document: dict[str, Any]
    ) -> None:
        directory = document["directory"]
        all_ids: list[str] = []
        seen: set[str] = set()
        for page in range(1, self.spec.pages + 1):
            task = directory["pages"][str(page)]
            parsed_page: DirectoryPage | None = None
            if task.get("state") == "completed":
                parsed_page = self._verify_completed_page(output, page, task)
            else:
                for attempt in range(1, self.max_attempts + 1):
                    task["attempts"] = int(task.get("attempts", 0)) + 1
                    try:
                        raw = self._open(
                            self._directory_request(page),
                            f"Scrutica directory page {page}",
                            _DIRECTORY_BODY_LIMIT,
                        )
                        parsed_page = parse_directory_page(raw, expected_page=page)
                        if parsed_page.total_pages != self.spec.pages:
                            raise ValueError("Scrutica directory total page count drifted")
                        if (
                            parsed_page.tracked != self.spec.tracked
                            or parsed_page.browsable != self.spec.browsable
                            or parsed_page.aggregate_only != self.spec.aggregate_only
                        ):
                            raise ValueError("Scrutica directory inventory counts drifted")
                        expected_size = (
                            self.spec.last_page_size
                            if page == self.spec.pages
                            else self.spec.page_size
                        )
                        if len(parsed_page.facility_ids) != expected_size:
                            raise ValueError(
                                f"Scrutica page {page} has "
                                f"{len(parsed_page.facility_ids)} IDs, expected {expected_size}"
                            )
                        relative = f"directory/page-{page:03d}.html"
                        _write_bytes_atomic(output / relative, raw)
                        task.update(
                            {
                                "state": "completed",
                                "url": self._directory_request(page).full_url,
                                "file": relative,
                                "bytes": len(raw),
                                "sha256": _sha256(raw),
                                "facility_ids": list(parsed_page.facility_ids),
                                "fetched_at": _require_timestamp(
                                    self.timestamp(), "Scrutica page fetched_at"
                                ),
                            }
                        )
                        self._checkpoint(output, document)
                        break
                    except Exception as error:
                        task.setdefault("failures", []).append(
                            {
                                "attempt": task["attempts"],
                                "at": _require_timestamp(
                                    self.timestamp(), "Scrutica failure timestamp"
                                ),
                                "error": f"{type(error).__name__}: {error}",
                            }
                        )
                        self._checkpoint(output, document)
                        if attempt == self.max_attempts or not self._transient(error):
                            if isinstance(error, urllib.error.HTTPError):
                                error.close()
                            raise
                        delay = self._backoff(attempt, error)
                        if isinstance(error, urllib.error.HTTPError):
                            error.close()
                        self.sleep(delay)
            assert parsed_page is not None
            if parsed_page.total_pages != self.spec.pages:
                raise ValueError("Scrutica directory total page count drifted")
            if (
                parsed_page.tracked != self.spec.tracked
                or parsed_page.browsable != self.spec.browsable
                or parsed_page.aggregate_only != self.spec.aggregate_only
            ):
                raise ValueError("Scrutica directory inventory counts drifted")
            expected_size = (
                self.spec.last_page_size
                if page == self.spec.pages
                else self.spec.page_size
            )
            if len(parsed_page.facility_ids) != expected_size:
                raise ValueError(f"Scrutica page {page} facility count drifted")
            duplicates = seen.intersection(parsed_page.facility_ids)
            if duplicates:
                raise ValueError(
                    "Scrutica directory repeats facility IDs across pages: "
                    + ", ".join(sorted(duplicates)[:5])
                )
            seen.update(parsed_page.facility_ids)
            all_ids.extend(parsed_page.facility_ids)

        if len(all_ids) != self.spec.browsable:
            raise ValueError("Scrutica directory did not yield the pinned browsable count")
        encoded_ids = ("\n".join(all_ids) + "\n").encode("utf-8")
        existing_ids = directory.get("facility_ids")
        if existing_ids and existing_ids != all_ids:
            raise ValueError("Scrutica directory facility ordering changed during resume")
        directory.update(
            {
                "state": "completed",
                "facility_ids": all_ids,
                "facility_ids_sha256": _sha256(encoded_ids),
            }
        )
        existing_records = document.get("records")
        if existing_records and set(existing_records) != set(all_ids):
            raise ValueError("Scrutica record task inventory does not match directory")
        if not existing_records:
            document["records"] = {
                facility_id: {
                    "state": "pending",
                    "attempts": 0,
                    "failures": [],
                    "request_id": _request_id(facility_id),
                }
                for facility_id in all_ids
            }
        self._checkpoint(output, document)

    def _verify_completed_record(
        self, output: Path, facility_id: str, task: Mapping[str, Any]
    ) -> None:
        expected_raw = f"records/{facility_id}.sse"
        expected_json = f"records/{facility_id}.json"
        if task.get("raw_sse_file") != expected_raw:
            raise ValueError(f"Scrutica record {facility_id} has unexpected SSE path")
        if task.get("parsed_json_file") != expected_json:
            raise ValueError(f"Scrutica record {facility_id} has unexpected JSON path")
        raw_path = _bundle_file(
            output, expected_raw, f"Scrutica record {facility_id} raw SSE"
        )
        json_path = _bundle_file(
            output, expected_json, f"Scrutica record {facility_id} parsed JSON"
        )
        raw_size, raw_hash = _hash_file(raw_path)
        json_size, json_hash = _hash_file(json_path)
        if (
            raw_size != task.get("raw_sse_bytes")
            or raw_hash != task.get("raw_sse_sha256")
            or json_size != task.get("parsed_json_bytes")
            or json_hash != task.get("parsed_json_sha256")
        ):
            raise ValueError(f"Scrutica record {facility_id} checkpoint hash does not match")
        document = parse_mcp_facility_response(
            raw_path.read_bytes(),
            request_id=str(task.get("request_id")),
            facility_id=facility_id,
        )
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        if saved != document:
            raise ValueError(f"Scrutica record {facility_id} parsed JSON changed")

    def _wait_for_mcp_slot(self) -> None:
        if self._last_mcp_started is not None:
            wait = self.interval_seconds - (self.monotonic() - self._last_mcp_started)
            if wait > 0:
                self.sleep(wait)
        self._last_mcp_started = self.monotonic()

    def fetch(
        self,
        output_directory: str | Path,
        *,
        created_at: str | None = None,
        max_requests: int | None = None,
        max_failures: int | None = 10,
        retry_failed: bool = False,
    ) -> dict[str, Any]:
        """Fetch directory pages then at most ``max_requests`` MCP HTTP attempts.

        Directory GETs are deliberately excluded from ``max_requests``: all
        directory pages are required to prove the exact task inventory before
        any facility MCP call can be made.
        """
        if max_requests is not None and max_requests < 0:
            raise ValueError("Scrutica max_requests cannot be negative")
        if max_failures is not None and max_failures <= 0:
            raise ValueError("Scrutica max_failures must be positive")
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        if not output.is_dir():
            raise ValueError(f"Scrutica output is not a directory: {output}")
        for subdirectory in ("directory", "records"):
            candidate = output / subdirectory
            if candidate.is_symlink():
                raise ValueError(
                    f"Scrutica output subdirectory may not be a symlink: {candidate}"
                )
        document = self._new_or_existing_manifest(output, created_at=created_at)
        self._fetch_directory(output, document)
        facility_ids = document["directory"]["facility_ids"]
        records = document["records"]

        if retry_failed:
            for task in records.values():
                if task.get("state") == "failed":
                    task["state"] = "pending"
            self._checkpoint(output, document)

        for facility_id in facility_ids:
            task = records[facility_id]
            if task.get("state") == "completed":
                self._verify_completed_record(output, facility_id, task)

        requests_made = 0
        failures = 0
        stop = False
        for facility_id in facility_ids:
            if stop:
                break
            task = records[facility_id]
            if task.get("state") in {"completed", "failed"}:
                continue
            request_id = _request_id(facility_id)
            if task.get("request_id") != request_id:
                raise ValueError(f"Scrutica record {facility_id} request ID drifted")
            succeeded = False
            for attempt in range(1, self.max_attempts + 1):
                if max_requests is not None and requests_made >= max_requests:
                    stop = True
                    break
                self._wait_for_mcp_slot()
                task["attempts"] = int(task.get("attempts", 0)) + 1
                requests_made += 1
                try:
                    raw = self._open(
                        self._mcp_request(facility_id, request_id),
                        f"Scrutica MCP facility {facility_id}",
                        _MCP_BODY_LIMIT,
                    )
                    parsed = parse_mcp_facility_response(
                        raw,
                        request_id=request_id,
                        facility_id=facility_id,
                    )
                    parsed_raw = _json_bytes(parsed)
                    raw_relative = f"records/{facility_id}.sse"
                    json_relative = f"records/{facility_id}.json"
                    _write_bytes_atomic(output / raw_relative, raw)
                    _write_bytes_atomic(output / json_relative, parsed_raw)
                    task.update(
                        {
                            "state": "completed",
                            "raw_sse_file": raw_relative,
                            "raw_sse_bytes": len(raw),
                            "raw_sse_sha256": _sha256(raw),
                            "parsed_json_file": json_relative,
                            "parsed_json_bytes": len(parsed_raw),
                            "parsed_json_sha256": _sha256(parsed_raw),
                            "fetched_at": _require_timestamp(
                                self.timestamp(), "Scrutica record fetched_at"
                            ),
                        }
                    )
                    self._checkpoint(output, document)
                    succeeded = True
                    break
                except Exception as error:
                    task.setdefault("failures", []).append(
                        {
                            "attempt": task["attempts"],
                            "at": _require_timestamp(
                                self.timestamp(), "Scrutica failure timestamp"
                            ),
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
                    transient = self._transient(error)
                    delay = self._backoff(attempt, error) if transient else 0.0
                    if attempt == self.max_attempts or not transient:
                        task["state"] = "failed"
                        failures += 1
                    self._checkpoint(output, document)
                    if isinstance(error, urllib.error.HTTPError):
                        error.close()
                    if task.get("state") == "failed":
                        break
                    self.sleep(delay)
            if not succeeded and task.get("state") == "failed":
                if max_failures is not None and failures >= max_failures:
                    stop = True
        document["last_run"] = {
            "finished_at": _require_timestamp(
                self.timestamp(), "Scrutica run finished_at"
            ),
            "mcp_requests_made": requests_made,
            "facilities_failed": failures,
            "max_requests": max_requests,
            "max_failures": max_failures,
            "retry_failed": retry_failed,
        }
        self._checkpoint(output, document)
        return document


_STATUS_MAP: dict[str, LifecycleStatus] = {
    "announced": LifecycleStatus.ANNOUNCED,
    "permitted": LifecycleStatus.PERMITTED,
    "under_construction": LifecycleStatus.UNDER_CONSTRUCTION,
    "operational": LifecycleStatus.OPERATIONAL,
    "expanding": LifecycleStatus.EXPANSION,
    "decommissioned": LifecycleStatus.DECOMMISSIONED,
}


def upstream_source_family(data_source: Any) -> str:
    """Map Scrutica's provenance label to a conservative dependency root."""
    normalized = _NORMALIZE_SOURCE_RE.sub("_", str(data_source or "").casefold()).strip(
        "_"
    )
    tokens = set(normalized.split("_"))
    if "epoch" in tokens or normalized.startswith("epoch"):
        return "epoch_ai"
    if (
        "im3" in tokens
        or "osm" in tokens
        or "openstreetmap" in tokens
        or "open_street_map" in normalized
    ):
        return "openstreetmap"
    if "pdb" in tokens or "peeringdb" in tokens or "peering_db" in normalized:
        return "peeringdb"
    if "gridstatus" in tokens or "grid_status" in normalized:
        return "gridstatus"
    return normalized or "unknown"


def scrutica_data_center_scope(facility_type: str | None) -> str:
    """Classify an exact Scrutica type without inferring from names or descriptions."""
    if facility_type in SCRUTICA_DATA_CENTER_FACILITY_TYPES:
        return "in_scope"
    if facility_type in SCRUTICA_NON_DATA_CENTER_FACILITY_TYPES:
        return "out_of_scope"
    if facility_type in SCRUTICA_REVIEW_REQUIRED_FACILITY_TYPES:
        return "review_required"
    return "unknown_type"


def assert_scrutica_database_is_isolated(connection: sqlite3.Connection) -> None:
    """Refuse to add Scrutica evidence to a database containing another family."""
    rows = connection.execute(
        """
        SELECT DISTINCT COALESCE(source_family, '') AS source_family
        FROM evidence
        WHERE COALESCE(source_family, '') != ?
        ORDER BY source_family
        """,
        (SCRUTICA_SOURCE_FAMILY,),
    ).fetchall()
    if rows:
        families = ", ".join(repr(row["source_family"]) for row in rows[:5])
        raise ValueError(
            "Scrutica must use a separate CC-BY-SA database; this database already "
            f"contains other evidence families: {families}"
        )


def _validate_bundle(
    bundle: Path,
    *,
    spec: DirectorySpec,
    allow_partial: bool,
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any], dict[str, Any]]]]:
    manifest_path = _bundle_file(bundle, SCRUTICA_MANIFEST, "Scrutica manifest.json")
    manifest_raw = manifest_path.read_bytes()
    try:
        document = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise ValueError("Scrutica manifest is not valid JSON") from error
    _validate_manifest_header(document, spec)
    if document.get("state") not in {"completed", "incomplete"}:
        raise ValueError("Scrutica bundle state must be completed or incomplete")
    directory = document["directory"]
    facility_ids = directory.get("facility_ids")
    if directory.get("state") != "completed" or not isinstance(facility_ids, list):
        raise ValueError("Scrutica directory inventory is incomplete")
    if len(facility_ids) != spec.browsable or len(set(facility_ids)) != spec.browsable:
        raise ValueError("Scrutica directory facility inventory does not match its pin")
    for facility_id in facility_ids:
        if not isinstance(facility_id, str) or not _FACILITY_ID_RE.fullmatch(facility_id):
            raise ValueError("Scrutica directory contains an invalid facility ID")
    ids_raw = ("\n".join(facility_ids) + "\n").encode("utf-8")
    if _sha256(ids_raw) != directory.get("facility_ids_sha256"):
        raise ValueError("Scrutica directory facility inventory hash does not match")
    page_tasks = directory.get("pages")
    if not isinstance(page_tasks, dict) or set(page_tasks) != {
        str(page) for page in range(1, spec.pages + 1)
    }:
        raise ValueError("Scrutica directory page task inventory does not match its pin")
    verified_ids: list[str] = []
    for page in range(1, spec.pages + 1):
        task = page_tasks[str(page)]
        if not isinstance(task, dict) or task.get("state") != "completed":
            raise ValueError(f"Scrutica directory page {page} is incomplete")
        _require_timestamp(task.get("fetched_at"), f"Scrutica directory page {page} fetched_at")
        expected_url = _directory_page_url(SCRUTICA_DIRECTORY_URL, page)
        if task.get("url") != expected_url:
            raise ValueError(f"Scrutica directory page {page} has unexpected URL")
        relative = f"directory/page-{page:03d}.html"
        if task.get("file") != relative:
            raise ValueError(f"Scrutica directory page {page} has unexpected path")
        page_path = _bundle_file(
            bundle, relative, f"Scrutica directory page {page} raw HTML"
        )
        page_size, page_hash = _hash_file(page_path)
        if page_size != task.get("bytes") or page_hash != task.get("sha256"):
            raise ValueError(f"Scrutica directory page {page} hash does not match")
        parsed_page = parse_directory_page(page_path.read_bytes(), expected_page=page)
        expected_size = spec.last_page_size if page == spec.pages else spec.page_size
        if (
            parsed_page.total_pages != spec.pages
            or parsed_page.tracked != spec.tracked
            or parsed_page.browsable != spec.browsable
            or parsed_page.aggregate_only != spec.aggregate_only
            or len(parsed_page.facility_ids) != expected_size
            or list(parsed_page.facility_ids) != task.get("facility_ids")
        ):
            raise ValueError(f"Scrutica directory page {page} no longer matches its pin")
        verified_ids.extend(parsed_page.facility_ids)
    if verified_ids != facility_ids:
        raise ValueError("Scrutica directory page order does not match facility inventory")

    records = document.get("records")
    if not isinstance(records, dict) or set(records) != set(facility_ids):
        raise ValueError("Scrutica record task inventory does not match its directory")
    state_counts = {
        state: sum(
            isinstance(task, dict) and task.get("state") == state
            for task in records.values()
        )
        for state in ("completed", "failed", "pending")
    }
    if sum(state_counts.values()) != spec.browsable:
        raise ValueError("Scrutica record task state is invalid")
    expected_summary = {
        "tracked": spec.tracked,
        "browsable": spec.browsable,
        "aggregate_only": spec.aggregate_only,
        "directory_pages_completed": spec.pages,
        "records_completed": state_counts["completed"],
        "records_failed": state_counts["failed"],
        "records_pending": state_counts["pending"],
    }
    if document.get("summary") != expected_summary:
        raise ValueError("Scrutica manifest summary does not match task states")
    if document.get("state") != "completed" and not allow_partial:
        raise ValueError(
            "Scrutica bundle is incomplete; pass allow_partial=True only for a "
            "clearly labeled discovery snapshot"
        )
    completed: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for facility_id in facility_ids:
        task = records[facility_id]
        if not isinstance(task, dict):
            raise ValueError(f"Scrutica task {facility_id} is not an object")
        if task.get("state") != "completed":
            continue
        _require_timestamp(task.get("fetched_at"), f"Scrutica task {facility_id} fetched_at")
        request_id = _request_id(facility_id)
        if task.get("request_id") != request_id:
            raise ValueError(f"Scrutica task {facility_id} request ID does not match")
        raw_relative = task.get("raw_sse_file")
        json_relative = task.get("parsed_json_file")
        if raw_relative != f"records/{facility_id}.sse":
            raise ValueError(f"Scrutica task {facility_id} has unexpected SSE path")
        if json_relative != f"records/{facility_id}.json":
            raise ValueError(f"Scrutica task {facility_id} has unexpected JSON path")
        raw_path = _bundle_file(
            bundle, raw_relative, f"Scrutica task {facility_id} raw SSE"
        )
        json_path = _bundle_file(
            bundle, json_relative, f"Scrutica task {facility_id} parsed JSON"
        )
        raw_size, raw_hash = _hash_file(raw_path)
        json_size, json_hash = _hash_file(json_path)
        if (
            raw_size != task.get("raw_sse_bytes")
            or raw_hash != task.get("raw_sse_sha256")
            or json_size != task.get("parsed_json_bytes")
            or json_hash != task.get("parsed_json_sha256")
        ):
            raise ValueError(f"Scrutica task {facility_id} file hash does not match")
        parsed = parse_mcp_facility_response(
            raw_path.read_bytes(), request_id=request_id, facility_id=facility_id
        )
        try:
            saved = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Scrutica task {facility_id} parsed JSON is invalid"
            ) from error
        if saved != parsed:
            raise ValueError(
                f"Scrutica task {facility_id} parsed JSON does not match raw SSE"
            )
        completed.append((facility_id, task, parsed))
    if not completed:
        raise ValueError("Scrutica bundle contains no completed facility records")
    if document.get("state") == "completed" and len(completed) != spec.browsable:
        raise ValueError("Scrutica completed manifest is missing completed records")
    return document, completed


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Scrutica {field} must be text or null")
    stripped = value.strip()
    return stripped or None


def _coordinate_pair(facility: Mapping[str, Any]) -> tuple[float | None, float | None]:
    latitude = facility.get("lat")
    longitude = facility.get("lng")
    if latitude is None and longitude is None:
        return None, None
    if (
        isinstance(latitude, bool)
        or isinstance(longitude, bool)
        or not isinstance(latitude, (int, float))
        or not isinstance(longitude, (int, float))
    ):
        raise ValueError("Scrutica lat/lng must both be finite numbers or null")
    latitude = float(latitude)
    longitude = float(longitude)
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Scrutica latitude is outside WGS84 bounds")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Scrutica longitude is outside WGS84 bounds")
    return latitude, longitude


def _capacity_value(value: Any, field: str, *, positive: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Scrutica {field} must be numeric or null")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        comparator = "positive" if positive else "non-negative"
        raise ValueError(f"Scrutica {field} must be finite and {comparator}")
    return result


def _as_of_date(facility: Mapping[str, Any], retrieved_at: str) -> str:
    vintage = facility.get("data_vintage")
    if isinstance(vintage, str) and vintage.strip():
        candidate = vintage.strip()
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            try:
                datetime.strptime(candidate, "%Y-%m-%d")
            except ValueError:
                pass
            else:
                return candidate
        else:
            return parsed.date().isoformat()
    return datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")).date().isoformat()


def _snapshot_tags(facility: Mapping[str, Any]) -> dict[str, str]:
    tags: dict[str, str] = {
        "scrutica:id": str(facility["id"]),
        "datacenter_atlas:scope": "data_center",
        "datacenter_atlas:scope_policy": SCRUTICA_DATA_CENTER_SCOPE_POLICY,
    }
    simple = {
        "country": "country",
        "region": "scrutica:region",
        "state": "scrutica:state",
        "county": "scrutica:county",
        "city": "scrutica:city",
        "facility_type": "scrutica:facility_type",
        "status": "scrutica:status",
        "data_source": "scrutica:data_source",
        "source_url": "scrutica:upstream_source_url",
        "authority_tier": "scrutica:authority_tier",
        "data_vintage": "scrutica:data_vintage",
        "announced_date": "scrutica:announced_date",
        "construction_start_date": "scrutica:construction_start_date",
        "expected_operational_date": "scrutica:expected_operational_date",
        "actual_operational_date": "scrutica:actual_operational_date",
        "water_source": "scrutica:water_source",
    }
    for source_key, tag_key in simple.items():
        value = facility.get(source_key)
        if value is not None and str(value).strip():
            tags[tag_key] = str(value)
    if isinstance(facility.get("is_estimated"), bool):
        tags["scrutica:is_estimated"] = str(facility["is_estimated"]).lower()
    owner = facility.get("owner_name")
    operator = facility.get("operator_name")
    if isinstance(owner, str) and owner.strip():
        tags["owner"] = owner.strip()
    if isinstance(operator, str) and operator.strip():
        tags["operator"] = operator.strip()
    for source_key in ("energy_profile", "water_usage_mgd"):
        value = facility.get(source_key)
        if value is not None:
            tags[f"scrutica:{source_key}"] = json.dumps(
                value, sort_keys=True, separators=(",", ":")
            )
    return tags


class ScruticaAdapter:
    """Import verified Scrutica records into an isolated source-scoped database."""

    source_name = SCRUTICA_SOURCE_FAMILY

    def __init__(self, *, spec: DirectorySpec = SCRUTICA_DIRECTORY_SPEC) -> None:
        self.spec = spec

    def import_file(
        self,
        connection: sqlite3.Connection,
        path: str | Path,
        *,
        retrieved_at: str,
        allow_partial: bool = False,
    ) -> ImportResult:
        retrieved_at = _require_timestamp(retrieved_at, "retrieved_at")
        assert_scrutica_database_is_isolated(connection)
        bundle = Path(path)
        if not bundle.is_dir():
            raise ValueError("Scrutica input must be a fetch bundle directory")
        manifest, records = _validate_bundle(
            bundle, spec=self.spec, allow_partial=allow_partial
        )
        manifest_hash = _sha256((bundle / SCRUTICA_MANIFEST).read_bytes())
        entities_created = 0
        evidence_created = 0
        warnings: list[str] = []
        if manifest.get("state") != "completed":
            warnings.append(
                "PARTIAL SCRUTICA DISCOVERY IMPORT: bundle is incomplete; missing "
                "records are unknown coverage, not negative evidence"
            )

        scoped_records: list[tuple[str, dict[str, Any], dict[str, Any], str]] = []
        excluded_by_type: Counter[str] = Counter()
        excluded_by_scope: Counter[str] = Counter()
        for facility_id, task, document in records:
            facility = document["facility"]
            facility_type = _optional_text(
                facility.get("facility_type"), f"{facility_id}.facility_type"
            )
            scope = scrutica_data_center_scope(facility_type)
            if scope == "in_scope":
                scoped_records.append((facility_id, task, document, facility_type or ""))
                continue
            excluded_by_type[facility_type or "<missing>"] += 1
            excluded_by_scope[scope] += 1

        scope_summary = {
            "policy": SCRUTICA_DATA_CENTER_SCOPE_POLICY,
            "official_facility_types": sorted(SCRUTICA_OFFICIAL_FACILITY_TYPES),
            "in_scope_facility_types": sorted(SCRUTICA_DATA_CENTER_FACILITY_TYPES),
            "out_of_scope_facility_types": sorted(
                SCRUTICA_NON_DATA_CENTER_FACILITY_TYPES
            ),
            "review_required_facility_types": sorted(
                SCRUTICA_REVIEW_REQUIRED_FACILITY_TYPES
            ),
            "completed_records_examined": len(records),
            "records_imported": len(scoped_records),
            "records_excluded": len(records) - len(scoped_records),
            "excluded_by_scope": dict(sorted(excluded_by_scope.items())),
            "excluded_by_facility_type": dict(sorted(excluded_by_type.items())),
            "raw_fetch_bundle_unchanged": True,
            "name_or_description_inference": False,
        }
        excluded_text = ", ".join(
            f"{facility_type}={count}"
            for facility_type, count in sorted(excluded_by_type.items())
        ) or "none"
        warnings.append(
            "SCRUTICA DATA-CENTER SCOPE: "
            f"examined {len(records)} completed records; imported {len(scoped_records)}; "
            f"excluded {len(records) - len(scoped_records)} by exact facility_type "
            f"({excluded_text}). Raw fetched records remain unchanged in the bundle."
        )

        with connection:
            for facility_id, task, document, facility_type in scoped_records:
                facility = document["facility"]
                if facility.get("id") != facility_id:
                    raise ValueError("Scrutica facility ID changed after bundle validation")
                name = _optional_text(facility.get("name"), f"{facility_id}.name")
                if name is None:
                    raise ValueError(f"Scrutica {facility_id}.name is required")
                latitude, longitude = _coordinate_pair(facility)
                raw_status = _optional_text(
                    facility.get("status"), f"{facility_id}.status"
                )
                status = _STATUS_MAP.get(raw_status or "", LifecycleStatus.UNKNOWN)
                is_estimated = facility.get("is_estimated")
                if is_estimated is not None and not isinstance(is_estimated, bool):
                    raise ValueError(f"Scrutica {facility_id}.is_estimated must be boolean or null")
                modeled = is_estimated is not False
                method = EstimateMethod.MODELED if modeled else EstimateMethod.REPORTED
                as_of = _as_of_date(facility, retrieved_at)
                canonical_url = f"{SCRUTICA_DIRECTORY_URL}/{facility_id}"
                if document.get("url") != canonical_url:
                    raise ValueError("Scrutica canonical URL changed after bundle validation")
                upstream = upstream_source_family(facility.get("data_source"))
                data_vintage = facility.get("data_vintage")
                published_at = (
                    data_vintage.strip()
                    if isinstance(data_vintage, str) and data_vintage.strip()
                    else None
                )
                content_hash = str(task["parsed_json_sha256"])
                evidence_id = stable_id(
                    "evidence",
                    SCRUTICA_SOURCE_FAMILY,
                    facility_id,
                    retrieved_at,
                    content_hash,
                )
                evidence_created += int(
                    add_evidence(
                        connection,
                        Evidence(
                            id=evidence_id,
                            kind=EvidenceKind.THIRD_PARTY_DATASET,
                            title=f"Scrutica facility {facility_id}: {name}",
                            source_url=canonical_url,
                            publisher=SCRUTICA_PUBLISHER,
                            source_family=SCRUTICA_SOURCE_FAMILY,
                            license=SCRUTICA_LICENSE,
                            attribution=SCRUTICA_ATTRIBUTION,
                            published_at=published_at,
                            retrieved_at=retrieved_at,
                            excerpt=(
                                "Source-scoped Scrutica discovery record; not merged and "
                                "not independent of its named upstream source."
                            ),
                        ),
                        content_hash=content_hash,
                        metadata={
                            "canonical_scrutica_url": canonical_url,
                            "data_source": facility.get("data_source"),
                            "source_url": facility.get("source_url"),
                            "upstream_source_url": facility.get("source_url"),
                            "upstream_source_family": upstream,
                            "is_estimated": is_estimated,
                            "authority_tier": facility.get("authority_tier"),
                            "data_vintage": facility.get("data_vintage"),
                            "facility_type": facility_type,
                            "datacenter_atlas_scope": {
                                "classification": "in_scope",
                                "facility_type": facility_type,
                                **scope_summary,
                            },
                            "independent_corroboration": False,
                            "resolution_policy": "candidate_links_only_no_automatic_merge",
                            "redistribution_scope": "isolated_cc_by_sa_discovery_database",
                            "aggregate_only_records_not_in_bundle": self.spec.aggregate_only,
                            "directory_facility_ids_sha256": manifest["directory"][
                                "facility_ids_sha256"
                            ],
                            "manifest_sha256": manifest_hash,
                            "raw_sse_sha256": task["raw_sse_sha256"],
                            "parsed_json_sha256": content_hash,
                            "mcp_request_id": task["request_id"],
                            "mcp_fetched_at": task.get("fetched_at"),
                            "provenance": {
                                "manifest_sha256": manifest_hash,
                                "raw_sse_sha256": task["raw_sse_sha256"],
                                "parsed_json_sha256": content_hash,
                                "mcp_request_id": task["request_id"],
                                "mcp_fetched_at": task.get("fetched_at"),
                                "datacenter_atlas_scope": {
                                    "classification": "in_scope",
                                    "facility_type": facility_type,
                                    **scope_summary,
                                },
                            },
                            "scrutica_record": document,
                            "scrutica_facility": facility,
                        },
                    )
                )
                stable_key = f"scrutica:{facility_id}"
                entity_id = stable_id("entity", stable_key, "facility")
                entities_created += int(
                    add_facility(
                        connection,
                        Facility(entity_id, stable_key, evidence_id),
                        created_at=retrieved_at,
                    )
                )
                snapshot_confidence = 0.50 if modeled else 0.70
                add_snapshot(
                    connection,
                    snapshot_id=stable_id("snapshot", entity_id, evidence_id),
                    entity_id=entity_id,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    geometry=(
                        {"type": "Point", "coordinates": [longitude, latitude]}
                        if latitude is not None and longitude is not None
                        else None
                    ),
                    tags=_snapshot_tags(facility),
                    evidence_id=evidence_id,
                    as_of_date=as_of,
                    recorded_at=retrieved_at,
                    method="scrutica_source_scoped_facility",
                    confidence=snapshot_confidence,
                )
                add_lifecycle(
                    connection,
                    LifecycleObservation(
                        id=stable_id("lifecycle", entity_id, evidence_id, status.value),
                        entity_id=entity_id,
                        status=status,
                        evidence_id=evidence_id,
                        as_of_date=as_of,
                        recorded_at=retrieved_at,
                        method=(
                            "scrutica_explicit_status"
                            if raw_status in _STATUS_MAP
                            else "scrutica_unmapped_status"
                        ),
                        confidence=(
                            0.42 if modeled else 0.62
                        )
                        if status is not LifecycleStatus.UNKNOWN
                        else 0.20,
                    ),
                )
                if raw_status and status is LifecycleStatus.UNKNOWN:
                    warnings.append(
                        f"Scrutica {facility_id} status {raw_status!r} was retained but mapped to unknown"
                    )

                classification_confidence = 0.40 if modeled else 0.55
                if facility_type == "colocation":
                    add_operating_model(
                        connection,
                        observation_id=stable_id(
                            "operating-model", entity_id, evidence_id, "colocation"
                        ),
                        entity_id=entity_id,
                        operating_model=OperatingModel.COLOCATION,
                        evidence_id=evidence_id,
                        as_of_date=as_of,
                        recorded_at=retrieved_at,
                        method="scrutica_explicit_facility_type",
                        confidence=classification_confidence,
                    )
                if facility_type == "ai_training":
                    add_workload(
                        connection,
                        observation_id=stable_id(
                            "workload", entity_id, evidence_id, "ai_training"
                        ),
                        entity_id=entity_id,
                        workload=Workload.AI_TRAINING,
                        evidence_id=evidence_id,
                        as_of_date=as_of,
                        recorded_at=retrieved_at,
                        method="scrutica_explicit_facility_type",
                        confidence=classification_confidence,
                    )

                capacity_fields = (
                    ("power_capacity_mw", CapacityMetric.GROSS_FACILITY_MW, False),
                    ("it_load_mw", CapacityMetric.CRITICAL_IT_MW, False),
                    ("pue", CapacityMetric.PUE, True),
                )
                for field, metric, positive in capacity_fields:
                    value = _capacity_value(
                        facility.get(field), f"{facility_id}.{field}", positive=positive
                    )
                    if value is None:
                        continue
                    add_capacity(
                        connection,
                        CapacityEstimate(
                            id=stable_id("capacity", entity_id, evidence_id, metric.value),
                            entity_id=entity_id,
                            metric=metric,
                            low=value,
                            base=value,
                            high=value,
                            method=method,
                            confidence=0.45 if modeled else 0.68,
                            evidence_id=evidence_id,
                            as_of_date=as_of,
                            recorded_at=retrieved_at,
                            stage=CapacityStage.UNKNOWN,
                            notes=(
                                f"Scrutica {field}; is_estimated="
                                f"{json.dumps(is_estimated)}; no stage inferred"
                            ),
                        ),
                    )

        return ImportResult(
            source=self.source_name,
            examined_elements=len(records),
            imported_elements=len(scoped_records),
            skipped_elements=len(records) - len(scoped_records),
            entities_created=entities_created,
            evidence_created=evidence_created,
            warnings=tuple(warnings),
        )


ScruticaFacilityAdapter = ScruticaAdapter
