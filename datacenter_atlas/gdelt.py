"""Pinned GDELT bulk-news discovery for review-only construction leads.

This lane consumes GDELT's non-consumptive Web NGrams raw snapshot files,
never the rate-limited DOC API.  It preserves exact source bytes and emits
article candidates only when a transparent language-specific lexicon finds
both a data-centre term and a development/construction term.  Candidates are
not facility records and make no identity, lifecycle, operating, or power
claim.
"""

from __future__ import annotations

import email.utils
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


GDELT_DOCUMENTATION_URL = (
    "https://blog.gdeltproject.org/"
    "using-the-new-web-ngrams-dataset-to-find-relevant-coverage/"
)
GDELT_TERMS_URL = "https://www.gdeltproject.org/about.html#termsofuse"
GDELT_PUBLISHER = "The GDELT Project"
GDELT_ATTRIBUTION = "Data from The GDELT Project (https://www.gdeltproject.org/)"
GDELT_USAGE_TERMS = (
    "GDELT datasets permit unlimited and unrestricted use; use or redistribution "
    "must cite and link to The GDELT Project"
)
GDELT_SOURCE_FAMILY = "gdelt:web_news_ngrams"
GDELT_USER_AGENT = (
    "DataCenterAtlas/0.1 (open research GDELT bulk news lane; "
    "+https://github.com/kiankyars/datacenter-atlas)"
)
GDELT_DEFAULT_INTERVAL_SECONDS = 1.1
GDELT_MAX_RETRY_DELAY_SECONDS = 30.0
SOURCE_MANIFEST_FILENAME = "manifest.json"
CANDIDATES_FILENAME = "candidates.jsonl"
CANDIDATE_MANIFEST_FILENAME = "manifest.json"
CANDIDATE_MANIFEST_HASH_FILENAME = "manifest.sha256"
SOURCE_SCHEMA_VERSION = 1
CANDIDATE_SCHEMA_VERSION = 1
QUERY_LEXICON_VERSION = "2026-07-18-v1"
MAX_TOC_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_NGRAM_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_MATCHING_QUADGRAMS = 40
_TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
_SNAPSHOT_RE = re.compile(r"^[0-9]{14}$")


class GDELTValidationError(ValueError):
    """Raised when a GDELT source, fetch, or candidate contract is invalid."""


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    filename: str
    generation: str
    bytes: int
    md5: str

    def __post_init__(self) -> None:
        if Path(self.filename).name != self.filename:
            raise GDELTValidationError("GDELT snapshot filename must be a basename")
        if not isinstance(self.generation, str) or not self.generation.isdigit():
            raise GDELTValidationError("GDELT object generation must be decimal text")
        if isinstance(self.bytes, bool) or not isinstance(self.bytes, int) or self.bytes <= 0:
            raise GDELTValidationError("GDELT expected bytes must be positive")
        if not isinstance(self.md5, str) or not _MD5_RE.fullmatch(self.md5):
            raise GDELTValidationError("GDELT expected MD5 must be lowercase hexadecimal")


@dataclass(frozen=True, slots=True)
class SnapshotSpec:
    snapshot_id: str
    ngrams: SnapshotFile
    toc: SnapshotFile

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not _SNAPSHOT_RE.fullmatch(
            self.snapshot_id
        ):
            raise GDELTValidationError("GDELT snapshot ID must use YYYYMMDDHHMMSS")
        expected = {
            f"{self.snapshot_id}.ngrams.txt.gz",
            f"{self.snapshot_id}.toc.json.gz",
        }
        if {self.ngrams.filename, self.toc.filename} != expected:
            raise GDELTValidationError("GDELT snapshot filenames do not match snapshot ID")

    @property
    def files(self) -> tuple[SnapshotFile, SnapshotFile]:
        return self.ngrams, self.toc


PINNED_SNAPSHOT = SnapshotSpec(
    snapshot_id="20260630201600",
    ngrams=SnapshotFile(
        filename="20260630201600.ngrams.txt.gz",
        generation="1782869063515925",
        bytes=8_192_280,
        md5="773a343d978987fd18d0bfc2e6f057a2",
    ),
    toc=SnapshotFile(
        filename="20260630201600.toc.json.gz",
        generation="1782869063270518",
        bytes=284_249,
        md5="d09abe9b3f031deff5328123a59cdd8d",
    ),
)


REVIEW_CONSTRAINTS = {
    "candidate_basis": "lexical_match_in_gdelt_non_consumptive_ngram_snapshot",
    "article_body_fetched": False,
    "facility_identity_claim": False,
    "lifecycle_or_status_claim": False,
    "operating_status_claim": False,
    "power_or_energy_claim": False,
    "automatic_atlas_import": False,
    "independent_review_required": True,
}


# This deliberately small seed lexicon is an auditable recall aid, not a claim
# of linguistic completeness.  A document must match both groups in its own
# GDELT language before it becomes a review candidate.
QUERY_TERMS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "ar": {
        "subject": ("مركز بيانات", "مراكز البيانات", "مركز للبيانات"),
        "development": ("بناء", "إنشاء", "مشروع", "مقترح", "مخطط", "تصريح", "توسعة", "استثمار", "جديد"),
    },
    "da": {
        "subject": ("datacenter", "datacentre", "serverfarm"),
        "development": ("byggeri", "bygge", "projekt", "planlagt", "forslag", "tilladelse", "udvidelse", "investering", "nyt"),
    },
    "de": {
        "subject": ("rechenzentrum", "rechenzentren", "datenzentrum", "serverfarm"),
        "development": ("bau", "bauen", "projekt", "geplant", "planung", "genehmigung", "erweiterung", "investition", "neu"),
    },
    "el": {
        "subject": ("κέντρο δεδομένων", "κέντρα δεδομένων"),
        "development": ("κατασκευή", "έργο", "σχεδιαζόμενο", "πρόταση", "άδεια", "επέκταση", "επένδυση", "νέο"),
    },
    "en": {
        "subject": ("data center", "data centre", "datacenter", "datacentre", "server farm", "hyperscale campus"),
        "development": ("under construction", "construction", "constructing", "build", "building", "break ground", "groundbreaking", "project", "proposed", "proposal", "planned", "planning", "permit", "approved", "expansion", "expand", "investment", "develop", "development", "new"),
    },
    "es": {
        "subject": ("centro de datos", "centros de datos", "granja de servidores"),
        "development": ("construcción", "construir", "proyecto", "propuesto", "planificado", "permiso", "aprobado", "ampliación", "expansión", "inversión", "nuevo"),
    },
    "fi": {
        "subject": ("datakeskus", "datakeskukset", "palvelinkeskus"),
        "development": ("rakentaminen", "rakentaa", "hanke", "suunniteltu", "ehdotettu", "lupa", "laajennus", "investointi", "uusi"),
    },
    "fr": {
        "subject": ("centre de données", "centres de données", "centre informatique", "ferme de serveurs"),
        "development": ("construction", "construire", "projet", "proposé", "planifié", "permis", "approuvé", "extension", "investissement", "nouveau"),
    },
    "hi": {
        "subject": ("डेटा सेंटर", "डाटा सेंटर"),
        "development": ("निर्माण", "परियोजना", "प्रस्तावित", "योजना", "अनुमति", "विस्तार", "निवेश", "नया"),
    },
    "id": {
        "subject": ("pusat data", "sentra data"),
        "development": ("konstruksi", "membangun", "proyek", "diusulkan", "direncanakan", "izin", "ekspansi", "investasi", "baru"),
    },
    "it": {
        "subject": ("centro dati", "centri dati", "data center", "server farm"),
        "development": ("costruzione", "costruire", "progetto", "proposto", "pianificato", "permesso", "approvato", "espansione", "investimento", "nuovo"),
    },
    "iw": {
        "subject": ("מרכז נתונים", "חוות שרתים"),
        "development": ("בנייה", "הקמה", "פרויקט", "מוצע", "מתוכנן", "היתר", "הרחבה", "השקעה", "חדש"),
    },
    "ja": {
        "subject": ("データセンター", "サーバーファーム"),
        "development": ("建設", "建築", "計画", "提案", "許可", "承認", "拡張", "投資", "新設"),
    },
    "ko": {
        "subject": ("데이터 센터", "데이터센터", "서버 팜"),
        "development": ("건설", "건축", "계획", "제안", "허가", "승인", "확장", "투자", "신설"),
    },
    "nl": {
        "subject": ("datacenter", "datacentrum", "serverpark"),
        "development": ("bouw", "bouwen", "project", "gepland", "voorstel", "vergunning", "goedgekeurd", "uitbreiding", "investering", "nieuw"),
    },
    "no": {
        "subject": ("datasenter", "datasentre", "serverpark"),
        "development": ("bygging", "bygge", "prosjekt", "planlagt", "foreslått", "tillatelse", "utvidelse", "investering", "nytt"),
    },
    "pl": {
        "subject": ("centrum danych", "centra danych", "farma serwerów"),
        "development": ("budowa", "budować", "projekt", "proponowany", "planowany", "pozwolenie", "zatwierdzony", "rozbudowa", "inwestycja", "nowy"),
    },
    "pt": {
        "subject": ("centro de dados", "centros de dados", "fazenda de servidores"),
        "development": ("construção", "construir", "projeto", "proposto", "planejado", "licença", "aprovado", "expansão", "investimento", "novo"),
    },
    "ru": {
        "subject": ("центр обработки данных", "дата центр", "дата-центр", "цод"),
        "development": ("строительство", "строится", "проект", "предлагаемый", "планируется", "разрешение", "одобрен", "расширение", "инвестиции", "новый"),
    },
    "sv": {
        "subject": ("datacenter", "datacentrum", "serverhall"),
        "development": ("byggnation", "bygga", "projekt", "planerad", "föreslagen", "tillstånd", "utbyggnad", "investering", "nytt"),
    },
    "tr": {
        "subject": ("veri merkezi", "veri merkezleri", "sunucu çiftliği"),
        "development": ("inşaat", "inşa", "proje", "önerilen", "planlanan", "izin", "onaylandı", "genişleme", "yatırım", "yeni"),
    },
    "uk": {
        "subject": ("центр обробки даних", "дата центр", "дата-центр", "цод"),
        "development": ("будівництво", "будується", "проєкт", "запропонований", "планується", "дозвіл", "схвалено", "розширення", "інвестиції", "новий"),
    },
    "zh": {
        "subject": ("数据中心", "資料中心", "数据中心园区", "資料中心園區"),
        "development": ("建设", "建設", "建造", "项目", "項目", "拟建", "擬建", "规划", "規劃", "批准", "扩建", "擴建", "投资", "投資", "新建"),
    },
}

LANGUAGE_ALIASES = {
    "zh-tw": "zh",
    "he": "iw",
}


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GDELTValidationError(f"{field} must be a non-empty RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GDELTValidationError(f"{field} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GDELTValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _snapshot_url(filename: str, generation: str | None = None) -> str:
    base = (
        "https://storage.googleapis.com/data.gdeltproject.org/"
        f"gdeltv5/weblegacy/ngrams/{filename}"
    )
    return base if generation is None else f"{base}?generation={generation}"


def _hash_file(path: Path) -> tuple[int, str, str]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            sha256.update(chunk)
            md5.update(chunk)
    return size, sha256.hexdigest(), md5.hexdigest()


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    raw = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise GDELTValidationError(f"stale GDELT checkpoint exists: {temporary}")
    with temporary.open("wb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


def _retry_after(headers: Any, wall_time: Callable[[], float]) -> float | None:
    value = headers.get("Retry-After") if headers is not None else None
    if value is None:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, parsed.timestamp() - wall_time())


def _manifest_template(spec: SnapshotSpec, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "pipeline": "gdelt_v5_web_ngram_snapshot_fetch",
        "state": "incomplete",
        "created_at": created_at,
        "updated_at": created_at,
        "finished_at": None,
        "source": {
            "snapshot_id": spec.snapshot_id,
            "publisher": GDELT_PUBLISHER,
            "source_family": GDELT_SOURCE_FAMILY,
            "documentation_url": GDELT_DOCUMENTATION_URL,
            "terms_url": GDELT_TERMS_URL,
            "attribution": GDELT_ATTRIBUTION,
            "usage_terms": GDELT_USAGE_TERMS,
            "access_method": "pinned_bulk_raw_files_not_doc_api",
            "article_fulltext_included": False,
        },
        "files": {
            item.filename: {
                "state": "pending",
                "attempts": 0,
                "failures": [],
                "source_url": _snapshot_url(item.filename),
                "request_url": _snapshot_url(item.filename, item.generation),
                "generation": item.generation,
                "expected_bytes": item.bytes,
                "expected_md5": item.md5,
                "bytes": None,
                "md5": None,
                "sha256": None,
                "fetched_at": None,
            }
            for item in spec.files
        },
        "summary": {"files_expected": 2, "files_completed": 0, "bytes_completed": 0},
        "last_run": None,
    }


def _validate_manifest_header(
    value: Any, spec: SnapshotSpec
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GDELTValidationError("GDELT source manifest must be an object")
    expected = _manifest_template(spec, str(value.get("created_at")))
    if set(value) != set(expected):
        raise GDELTValidationError("GDELT source manifest has unexpected fields")
    for key in ("schema_version", "pipeline", "source"):
        if value.get(key) != expected[key]:
            raise GDELTValidationError(f"GDELT source manifest changed {key}")
    _timestamp(value.get("created_at"), "GDELT manifest created_at")
    _timestamp(value.get("updated_at"), "GDELT manifest updated_at")
    files = value.get("files")
    if not isinstance(files, dict) or set(files) != set(expected["files"]):
        raise GDELTValidationError("GDELT source manifest file inventory changed")
    immutable = {
        "source_url",
        "request_url",
        "generation",
        "expected_bytes",
        "expected_md5",
    }
    for filename, task in files.items():
        expected_task = expected["files"][filename]
        if not isinstance(task, dict) or set(task) != set(expected_task):
            raise GDELTValidationError(f"GDELT source task is invalid: {filename}")
        for field in immutable:
            if task.get(field) != expected_task[field]:
                raise GDELTValidationError(
                    f"GDELT source task {filename} changed {field}"
                )
        if task.get("state") not in {"pending", "failed", "completed"}:
            raise GDELTValidationError(f"GDELT source task {filename} state is invalid")
        attempts = task.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            raise GDELTValidationError(f"GDELT source task {filename} attempts are invalid")
        failures = task.get("failures")
        if not isinstance(failures, list) or len(failures) > attempts:
            raise GDELTValidationError(f"GDELT source task {filename} failures are invalid")
        failure_attempts: list[int] = []
        for failure in failures:
            if not isinstance(failure, dict) or set(failure) != {"attempt", "at", "error"}:
                raise GDELTValidationError(f"GDELT source task {filename} failure is invalid")
            failure_attempt = failure.get("attempt")
            if (
                isinstance(failure_attempt, bool)
                or not isinstance(failure_attempt, int)
                or not 1 <= failure_attempt <= attempts
            ):
                raise GDELTValidationError(
                    f"GDELT source task {filename} failure attempt is invalid"
                )
            failure_attempts.append(failure_attempt)
            _timestamp(failure.get("at"), f"GDELT {filename} failure at")
            if not isinstance(failure.get("error"), str) or not failure["error"]:
                raise GDELTValidationError(
                    f"GDELT source task {filename} failure error is invalid"
                )
        if failure_attempts != sorted(set(failure_attempts)):
            raise GDELTValidationError(
                f"GDELT source task {filename} failures are not unique and ordered"
            )
        output_fields = ("bytes", "md5", "sha256", "fetched_at")
        if task["state"] == "completed":
            if attempts == 0:
                raise GDELTValidationError(
                    f"completed GDELT source task {filename} has no attempt"
                )
            if task.get("bytes") != expected_task["expected_bytes"]:
                raise GDELTValidationError(
                    f"completed GDELT source task {filename} byte count changed"
                )
            if task.get("md5") != expected_task["expected_md5"]:
                raise GDELTValidationError(
                    f"completed GDELT source task {filename} MD5 changed"
                )
            if not isinstance(task.get("sha256"), str) or not _SHA256_RE.fullmatch(
                task["sha256"]
            ):
                raise GDELTValidationError(
                    f"completed GDELT source task {filename} SHA-256 is invalid"
                )
            _timestamp(task.get("fetched_at"), f"GDELT {filename} fetched_at")
        elif any(task.get(field) is not None for field in output_fields):
            raise GDELTValidationError(
                f"incomplete GDELT source task {filename} claims output"
            )
        if task["state"] == "failed" and (
            not failure_attempts or failure_attempts[-1] != attempts
        ):
            raise GDELTValidationError(
                f"failed GDELT source task {filename} lacks its final failure"
            )
    completed_tasks = [task for task in files.values() if task["state"] == "completed"]
    expected_summary = {
        "files_expected": len(files),
        "files_completed": len(completed_tasks),
        "bytes_completed": sum(int(task["bytes"]) for task in completed_tasks),
    }
    if value.get("summary") != expected_summary:
        raise GDELTValidationError("GDELT source manifest summary does not reconcile")
    expected_state = "completed" if len(completed_tasks) == len(files) else "incomplete"
    if value.get("state") != expected_state:
        raise GDELTValidationError("GDELT source manifest state does not reconcile")
    if expected_state == "completed":
        _timestamp(value.get("finished_at"), "GDELT manifest finished_at")
    elif value.get("finished_at") is not None:
        raise GDELTValidationError("incomplete GDELT source manifest has finished_at")
    last_run = value.get("last_run")
    if last_run is not None:
        if not isinstance(last_run, dict) or set(last_run) != {
            "started_at",
            "finished_at",
            "max_requests",
            "requests_made",
        }:
            raise GDELTValidationError("GDELT source manifest last_run is invalid")
        _timestamp(last_run.get("started_at"), "GDELT last_run started_at")
        _timestamp(last_run.get("finished_at"), "GDELT last_run finished_at")
        maximum = last_run.get("max_requests")
        made = last_run.get("requests_made")
        if (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum <= 0
            or isinstance(made, bool)
            or not isinstance(made, int)
            or not 0 <= made <= maximum
        ):
            raise GDELTValidationError("GDELT source manifest request counts are invalid")
    return value


def _update_source_summary(document: dict[str, Any], updated_at: str) -> None:
    completed = [task for task in document["files"].values() if task["state"] == "completed"]
    document["updated_at"] = updated_at
    document["summary"] = {
        "files_expected": len(document["files"]),
        "files_completed": len(completed),
        "bytes_completed": sum(int(task["bytes"]) for task in completed),
    }
    if len(completed) == len(document["files"]):
        document["state"] = "completed"
        document["finished_at"] = updated_at
    else:
        document["state"] = "incomplete"
        document["finished_at"] = None


class GDELTSnapshotFetcher:
    """Low-rate, resumable fetcher for the one pinned raw snapshot pair."""

    def __init__(
        self,
        *,
        spec: SnapshotSpec = PINNED_SNAPSHOT,
        user_agent: str = GDELT_USER_AGENT,
        minimum_interval_seconds: float = GDELT_DEFAULT_INTERVAL_SECONDS,
        timeout: float = 60.0,
        max_attempts: int = 3,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
        timestamp: Callable[[], str] = _utc_now,
    ) -> None:
        if not isinstance(spec, SnapshotSpec):
            raise GDELTValidationError("spec must be a SnapshotSpec")
        if not isinstance(user_agent, str) or not user_agent.strip() or any(
            character in user_agent for character in "\r\n"
        ):
            raise GDELTValidationError("a transparent single-line User-Agent is required")
        if (
            isinstance(minimum_interval_seconds, bool)
            or not isinstance(minimum_interval_seconds, (int, float))
            or not math.isfinite(float(minimum_interval_seconds))
            or float(minimum_interval_seconds) <= 0
        ):
            raise GDELTValidationError("minimum interval must be finite and positive")
        if not math.isfinite(timeout) or timeout <= 0:
            raise GDELTValidationError("timeout must be finite and positive")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts <= 0:
            raise GDELTValidationError("max_attempts must be positive")
        self.spec = spec
        self.user_agent = user_agent.strip()
        self.minimum_interval_seconds = float(minimum_interval_seconds)
        self.timeout = float(timeout)
        self.max_attempts = max_attempts
        self.opener = opener
        self.sleep = sleep
        self.monotonic = monotonic
        self.wall_time = wall_time
        self.timestamp = timestamp
        self._last_request_started: float | None = None

    def _wait(self) -> None:
        if self._last_request_started is not None:
            remaining = self.minimum_interval_seconds - (
                self.monotonic() - self._last_request_started
            )
            if remaining > 0:
                self.sleep(remaining)
        self._last_request_started = self.monotonic()

    def _checkpoint(self, output: Path, document: dict[str, Any]) -> None:
        updated_at = _timestamp(self.timestamp(), "GDELT checkpoint timestamp")
        _update_source_summary(document, updated_at)
        _write_json_atomic(output / SOURCE_MANIFEST_FILENAME, document)

    def _verify_completed(
        self, output: Path, item: SnapshotFile, task: Mapping[str, Any]
    ) -> None:
        path = output / item.filename
        if not path.is_file() or path.is_symlink():
            raise GDELTValidationError(f"completed GDELT source file is missing: {path}")
        size, sha256, md5 = _hash_file(path)
        if (
            size != item.bytes
            or md5 != item.md5
            or size != task.get("bytes")
            or md5 != task.get("md5")
            or sha256 != task.get("sha256")
        ):
            raise GDELTValidationError(f"completed GDELT source file changed: {item.filename}")

    def _download_once(self, output: Path, item: SnapshotFile) -> tuple[int, str, str]:
        final = output / item.filename
        partial = output / f".{item.filename}.partial"
        if final.exists() or final.is_symlink():
            raise GDELTValidationError(f"refusing unexpected GDELT source file: {final}")
        if partial.is_symlink() or (partial.exists() and not partial.is_file()):
            raise GDELTValidationError(f"GDELT partial is not a regular file: {partial}")
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > item.bytes:
            raise GDELTValidationError(f"GDELT partial exceeds expected size: {item.filename}")
        headers = {
            "Accept": "application/gzip,application/octet-stream",
            "Accept-Encoding": "identity",
            "User-Agent": self.user_agent,
        }
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(
            _snapshot_url(item.filename, item.generation),
            headers=headers,
            method="GET",
        )
        self._wait()
        with self.opener(request, timeout=self.timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else request.full_url
            if str(final_url) != request.full_url:
                raise GDELTValidationError("GDELT raw request redirected unexpectedly")
            status = getattr(response, "status", None) or (
                response.getcode() if hasattr(response, "getcode") else 200
            )
            response_headers = getattr(response, "headers", {})
            if response_headers.get("x-goog-generation") != item.generation:
                raise GDELTValidationError("GDELT object generation changed")
            etag = response_headers.get("ETag") or response_headers.get("etag")
            if not isinstance(etag, str) or etag.strip('"') != item.md5:
                raise GDELTValidationError("GDELT object ETag does not match pinned MD5")
            if offset:
                if status != 206:
                    raise GDELTValidationError("GDELT range resume did not return HTTP 206")
                content_range = response_headers.get("Content-Range") or response_headers.get(
                    "content-range"
                )
                if content_range != f"bytes {offset}-{item.bytes - 1}/{item.bytes}":
                    raise GDELTValidationError("GDELT range response does not match partial")
            elif status != 200:
                raise GDELTValidationError(f"GDELT raw request returned HTTP {status}")
            mode = "ab" if offset else "wb"
            with partial.open(mode) as destination:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if destination.tell() + len(chunk) > item.bytes:
                        raise GDELTValidationError("GDELT response exceeded expected bytes")
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
        size, sha256, md5 = _hash_file(partial)
        if size != item.bytes:
            raise urllib.error.URLError(
                f"GDELT response ended at {size} bytes, expected {item.bytes}"
            )
        if md5 != item.md5:
            raise GDELTValidationError("GDELT source MD5 does not match its pin")
        partial.replace(final)
        return size, sha256, md5

    def fetch(
        self,
        output_directory: str | Path,
        *,
        max_requests: int = 2,
        retry_failed: bool = False,
    ) -> dict[str, Any]:
        if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests <= 0:
            raise GDELTValidationError("max_requests must be positive")
        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)
        if not output.is_dir() or output.is_symlink():
            raise GDELTValidationError("GDELT source output must be a regular directory")
        manifest_path = output / SOURCE_MANIFEST_FILENAME
        manifest_temporary = output / f".{SOURCE_MANIFEST_FILENAME}.tmp"
        if manifest_temporary.is_symlink():
            raise GDELTValidationError("GDELT manifest temporary may not be a symlink")
        if manifest_temporary.exists():
            if not manifest_temporary.is_file():
                raise GDELTValidationError("GDELT manifest temporary is not a regular file")
            manifest_temporary.unlink()
        if manifest_path.exists():
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise GDELTValidationError("GDELT source manifest must be a regular file")
            manifest_raw = manifest_path.read_bytes()
            try:
                document = json.loads(manifest_raw)
            except json.JSONDecodeError as error:
                raise GDELTValidationError("GDELT source manifest is not valid JSON") from error
            canonical = (
                json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            if manifest_raw != canonical:
                raise GDELTValidationError("GDELT source manifest is not canonical JSON")
            document = _validate_manifest_header(document, self.spec)
        else:
            if any(output.iterdir()):
                raise GDELTValidationError(
                    "GDELT source files exist without a manifest; refusing ambiguous resume"
                )
            created_at = _timestamp(self.timestamp(), "GDELT fetch created_at")
            document = _manifest_template(self.spec, created_at)
            _write_json_atomic(manifest_path, document)

        if document["state"] == "completed":
            for item in self.spec.files:
                self._verify_completed(output, item, document["files"][item.filename])
            return document

        requests_made = 0
        run_started = _timestamp(self.timestamp(), "GDELT run started_at")
        for item in self.spec.files:
            task = document["files"][item.filename]
            if task.get("state") == "completed":
                self._verify_completed(output, item, task)
                continue
            if task.get("state") == "failed" and not retry_failed:
                continue
            if task.get("state") == "failed":
                task["state"] = "pending"
            for _ in range(self.max_attempts):
                if requests_made >= max_requests:
                    break
                task["attempts"] = int(task.get("attempts", 0)) + 1
                requests_made += 1
                try:
                    size, sha256, md5 = self._download_once(output, item)
                    fetched_at = _timestamp(self.timestamp(), "GDELT file fetched_at")
                    task.update(
                        {
                            "state": "completed",
                            "bytes": size,
                            "md5": md5,
                            "sha256": sha256,
                            "fetched_at": fetched_at,
                        }
                    )
                    self._checkpoint(output, document)
                    break
                except Exception as error:
                    failure_at = _timestamp(self.timestamp(), "GDELT failure timestamp")
                    task.setdefault("failures", []).append(
                        {
                            "attempt": task["attempts"],
                            "at": failure_at,
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
                    transient = (
                        isinstance(error, urllib.error.HTTPError)
                        and error.code in _TRANSIENT_HTTP_CODES
                    ) or (
                        isinstance(error, (urllib.error.URLError, TimeoutError))
                        and not isinstance(error, urllib.error.HTTPError)
                    )
                    retry_after = None
                    if isinstance(error, urllib.error.HTTPError):
                        if error.code == 429:
                            retry_after = _retry_after(error.headers, self.wall_time)
                        error.close()
                    if not transient:
                        task["state"] = "failed"
                        self._checkpoint(output, document)
                        break
                    if requests_made >= max_requests:
                        task["state"] = "pending"
                        self._checkpoint(output, document)
                        break
                    delay = min(
                        GDELT_MAX_RETRY_DELAY_SECONDS,
                        float(2 ** (task["attempts"] - 1)),
                    )
                    if retry_after is not None:
                        delay = min(GDELT_MAX_RETRY_DELAY_SECONDS, retry_after)
                    self._checkpoint(output, document)
                    self.sleep(delay)
            if requests_made >= max_requests:
                break

        finished_at = _timestamp(self.timestamp(), "GDELT run finished_at")
        document["last_run"] = {
            "started_at": run_started,
            "finished_at": finished_at,
            "max_requests": max_requests,
            "requests_made": requests_made,
        }
        _update_source_summary(document, finished_at)
        _write_json_atomic(manifest_path, document)
        return document


def validate_source_bundle(
    directory: str | Path, spec: SnapshotSpec = PINNED_SNAPSHOT
) -> dict[str, Any]:
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise GDELTValidationError("GDELT source bundle must be a regular directory")
    entries = list(root.iterdir())
    expected_names = {SOURCE_MANIFEST_FILENAME, *(item.filename for item in spec.files)}
    if {entry.name for entry in entries} != expected_names or len(entries) != len(
        expected_names
    ):
        raise GDELTValidationError("GDELT completed source bundle file set is invalid")
    manifest_path = root / SOURCE_MANIFEST_FILENAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise GDELTValidationError("GDELT source manifest must be a regular file")
    raw_manifest = manifest_path.read_bytes()
    try:
        document = json.loads(raw_manifest)
    except json.JSONDecodeError as error:
        raise GDELTValidationError("GDELT source manifest is not valid JSON") from error
    canonical = (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if raw_manifest != canonical:
        raise GDELTValidationError("GDELT source manifest is not canonical JSON")
    _validate_manifest_header(document, spec)
    if document.get("state") != "completed" or document.get("finished_at") is None:
        raise GDELTValidationError("GDELT source bundle is incomplete")
    _timestamp(document["finished_at"], "GDELT source finished_at")
    completed_bytes = 0
    for item in spec.files:
        task = document["files"][item.filename]
        if task.get("state") != "completed":
            raise GDELTValidationError(f"GDELT source task is incomplete: {item.filename}")
        path = root / item.filename
        if path.is_symlink() or not path.is_file():
            raise GDELTValidationError(f"GDELT source artifact is invalid: {item.filename}")
        size, sha256, md5 = _hash_file(path)
        if (
            size != item.bytes
            or md5 != item.md5
            or task.get("bytes") != size
            or task.get("md5") != md5
            or task.get("sha256") != sha256
        ):
            raise GDELTValidationError(f"GDELT source artifact hash changed: {item.filename}")
        _timestamp(task.get("fetched_at"), f"GDELT {item.filename} fetched_at")
        completed_bytes += size
    if document.get("summary") != {
        "files_expected": 2,
        "files_completed": 2,
        "bytes_completed": completed_bytes,
    }:
        raise GDELTValidationError("GDELT source summary does not reconcile")
    return document


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in normalized).split()
    )


def _matches(text: str, term: str) -> bool:
    normalized_term = _normalized_text(term)
    if not normalized_term:
        return False
    if " " not in normalized_term and any(
        "\u2e80" <= character <= "\u9fff"
        or "\u3040" <= character <= "\u30ff"
        or "\uac00" <= character <= "\ud7af"
        for character in normalized_term
    ):
        return normalized_term in text
    return f" {normalized_term} " in f" {text} "


def _language(value: str) -> str:
    lowered = value.strip().casefold()
    return LANGUAGE_ALIASES.get(lowered, lowered)


def _terms_for(language: str, group: str) -> tuple[str, ...]:
    return QUERY_TERMS.get(_language(language), {}).get(group, ())


def _matching_terms(text: str, terms: Iterable[str]) -> set[str]:
    return {term for term in terms if _matches(text, term)}


def _gzip_lines(path: Path, *, maximum_bytes: int) -> Iterable[str]:
    total = 0
    try:
        with gzip.open(path, "rb") as source:
            for raw_line in source:
                total += len(raw_line)
                if total > maximum_bytes:
                    raise GDELTValidationError(
                        f"GDELT decompressed data exceeds {maximum_bytes} bytes"
                    )
                try:
                    yield raw_line.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise GDELTValidationError("GDELT decompressed data is not UTF-8") from error
    except (OSError, EOFError) as error:
        raise GDELTValidationError(f"GDELT artifact is not valid gzip: {path.name}") from error


def _toc_records(path: Path, snapshot_id: str) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    expected_date_prefix = datetime.strptime(snapshot_id, "%Y%m%d%H%M%S").strftime(
        "%Y-%m-%dT%H:%M:"
    )
    for line_number, line in enumerate(
        _gzip_lines(path, maximum_bytes=MAX_TOC_UNCOMPRESSED_BYTES), start=1
    ):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise GDELTValidationError(f"GDELT TOC line {line_number} is invalid JSON") from error
        if not isinstance(value, dict) or set(value) != {"ID", "date", "img", "lang", "title", "url"}:
            raise GDELTValidationError(f"GDELT TOC line {line_number} schema changed")
        doc_id = value["ID"]
        if isinstance(doc_id, bool) or not isinstance(doc_id, int) or doc_id <= 0:
            raise GDELTValidationError(f"GDELT TOC line {line_number} has invalid ID")
        if doc_id in records:
            raise GDELTValidationError(f"GDELT TOC repeats document ID {doc_id}")
        article_date = _timestamp(value["date"], f"GDELT TOC document {doc_id} date")
        if not article_date.startswith(expected_date_prefix):
            raise GDELTValidationError(f"GDELT TOC document {doc_id} date differs from snapshot")
        for field in ("img", "lang", "title", "url"):
            if not isinstance(value[field], str):
                raise GDELTValidationError(f"GDELT TOC document {doc_id} {field} is not text")
        if not value["lang"].strip() or not value["title"].strip():
            raise GDELTValidationError(f"GDELT TOC document {doc_id} lacks language or title")
        parsed_url = urllib.parse.urlsplit(value["url"])
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise GDELTValidationError(f"GDELT TOC document {doc_id} URL is invalid")
        records[doc_id] = {
            "ID": doc_id,
            "date": article_date,
            "img": value["img"],
            "lang": value["lang"],
            "title": value["title"],
            "url": value["url"],
        }
    if not records:
        raise GDELTValidationError("GDELT TOC contains no records")
    return records


def _retain_snippet(snippets: set[str], phrase: str) -> None:
    snippets.add(phrase)
    if len(snippets) > MAX_MATCHING_QUADGRAMS:
        snippets.remove(max(snippets))


def _publisher_location_hints(url: str) -> list[dict[str, str]]:
    hostname = urllib.parse.urlsplit(url).hostname or ""
    final_label = hostname.rstrip(".").split(".")[-1].casefold()
    if len(final_label) == 2 and final_label.isalpha():
        return [
            {
                "kind": "publisher_domain_cctld",
                "value": final_label.upper(),
                "scope": "publisher_domain_only_not_article_or_facility_location",
            }
        ]
    return []


def _candidate_id(snapshot_id: str, doc_id: int, url: str) -> str:
    raw = json.dumps(
        {"snapshot_id": snapshot_id, "doc_id": doc_id, "url": url},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"gdelt-news-{hashlib.sha256(raw).hexdigest()[:24]}"


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GDELTValidationError(f"{field} must be a non-negative integer")
    return value


def _query_manifest() -> dict[str, Any]:
    return {
        "lexicon_version": QUERY_LEXICON_VERSION,
        "algorithm": "same_document_language_specific_subject_and_development_term_match",
        "fulltext_used": False,
        "terms": {
            language: {group: list(values) for group, values in groups.items()}
            for language, groups in sorted(QUERY_TERMS.items())
        },
        "matching_quadgram_limit_per_candidate": MAX_MATCHING_QUADGRAMS,
        "location_hint_policy": (
            "two-letter publisher-domain ccTLD only; not article or facility geography"
        ),
    }


def build_candidate_bundle(
    source_directory: str | Path,
    *,
    generated_at: str,
    spec: SnapshotSpec = PINNED_SNAPSHOT,
) -> tuple[bytes, bytes, bytes, dict[str, Any]]:
    source = Path(source_directory)
    source_manifest = validate_source_bundle(source, spec)
    generated = _timestamp(generated_at, "GDELT candidate generated_at")
    toc = _toc_records(source / spec.toc.filename, spec.snapshot_id)
    states: dict[int, dict[str, Any]] = {}
    unsupported_languages: dict[str, int] = {}
    for doc_id, article in toc.items():
        language = _language(article["lang"])
        if language not in QUERY_TERMS:
            unsupported_languages[article["lang"]] = (
                unsupported_languages.get(article["lang"], 0) + 1
            )
        title = _normalized_text(article["title"])
        states[doc_id] = {
            "subject": _matching_terms(title, _terms_for(language, "subject")),
            "development": _matching_terms(
                title, _terms_for(language, "development")
            ),
            "title_subject": _matching_terms(
                title, _terms_for(language, "subject")
            ),
            "title_development": _matching_terms(
                title, _terms_for(language, "development")
            ),
            "quadgrams": set(),
            "ngram_match_count": 0,
        }

    ngram_rows = 0
    seen_documents: set[int] = set()
    current_doc_id = 0
    current_phrases: set[str] = set()
    for line_number, line in enumerate(
        _gzip_lines(source / spec.ngrams.filename, maximum_bytes=MAX_NGRAM_UNCOMPRESSED_BYTES),
        start=1,
    ):
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            raise GDELTValidationError(f"GDELT ngram line {line_number} is not three columns")
        try:
            doc_id = int(parts[0])
            count = int(parts[2])
        except ValueError as error:
            raise GDELTValidationError(f"GDELT ngram line {line_number} has invalid integers") from error
        phrase = parts[1]
        if doc_id <= 0 or count <= 0 or not phrase.strip():
            raise GDELTValidationError(f"GDELT ngram line {line_number} has invalid values")
        if doc_id not in toc:
            raise GDELTValidationError(f"GDELT ngram line {line_number} references unknown document")
        if doc_id < current_doc_id:
            raise GDELTValidationError(
                f"GDELT ngram line {line_number} document order moved backwards"
            )
        if doc_id != current_doc_id:
            current_doc_id = doc_id
            current_phrases = set()
        if phrase in current_phrases:
            raise GDELTValidationError(f"GDELT ngram line {line_number} repeats a document phrase")
        current_phrases.add(phrase)
        seen_documents.add(doc_id)
        ngram_rows += 1
        language = _language(toc[doc_id]["lang"])
        normalized = _normalized_text(phrase)
        subject = _matching_terms(normalized, _terms_for(language, "subject"))
        development = _matching_terms(
            normalized, _terms_for(language, "development")
        )
        if subject or development:
            state = states[doc_id]
            state["subject"].update(subject)
            state["development"].update(development)
            state["ngram_match_count"] += count
            _retain_snippet(state["quadgrams"], phrase)
    if seen_documents != set(toc):
        raise GDELTValidationError("GDELT ngram document inventory differs from TOC")

    candidates: list[dict[str, Any]] = []
    subject_documents = 0
    development_documents = 0
    for doc_id in sorted(toc):
        article = toc[doc_id]
        state = states[doc_id]
        if state["subject"]:
            subject_documents += 1
        if state["development"]:
            development_documents += 1
        if not state["subject"] or not state["development"]:
            continue
        parsed_url = urllib.parse.urlsplit(article["url"])
        candidates.append(
            {
                "schema_version": CANDIDATE_SCHEMA_VERSION,
                "candidate_id": _candidate_id(spec.snapshot_id, doc_id, article["url"]),
                "snapshot_id": spec.snapshot_id,
                "gdelt_document_id": doc_id,
                "article": {
                    "url": article["url"],
                    "date": article["date"],
                    "language": article["lang"],
                    "title": article["title"],
                    "image_url": article["img"] or None,
                    "publisher_domain": parsed_url.hostname,
                },
                "location_hints": _publisher_location_hints(article["url"]),
                "lexical_match": {
                    "lexicon_version": QUERY_LEXICON_VERSION,
                    "subject_terms": sorted(state["subject"]),
                    "development_terms": sorted(state["development"]),
                    "title_subject_terms": sorted(state["title_subject"]),
                    "title_development_terms": sorted(state["title_development"]),
                    "matching_quadgrams": sorted(state["quadgrams"]),
                    "ngram_match_count": state["ngram_match_count"],
                },
                "source": {
                    "publisher": GDELT_PUBLISHER,
                    "source_family": GDELT_SOURCE_FAMILY,
                    "toc_url": _snapshot_url(spec.toc.filename),
                    "ngrams_url": _snapshot_url(spec.ngrams.filename),
                    "documentation_url": GDELT_DOCUMENTATION_URL,
                    "terms_url": GDELT_TERMS_URL,
                    "attribution": GDELT_ATTRIBUTION,
                },
                "review_constraints": dict(REVIEW_CONSTRAINTS),
            }
        )
    candidates.sort(key=lambda item: (item["article"]["date"], item["gdelt_document_id"]))
    candidate_bytes = b"".join(
        (
            json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        for item in candidates
    )
    source_manifest_raw = (source / SOURCE_MANIFEST_FILENAME).read_bytes()
    manifest = {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "pipeline": "gdelt_data_centre_news_candidate_extraction",
        "generated_at": generated,
        "scope": {
            "purpose": "review_only_news_article_discovery",
            "confirmed_release_eligible": False,
            **REVIEW_CONSTRAINTS,
        },
        "source": {
            "snapshot_id": spec.snapshot_id,
            "source_manifest_bytes": len(source_manifest_raw),
            "source_manifest_sha256": hashlib.sha256(source_manifest_raw).hexdigest(),
            "source_finished_at": source_manifest["finished_at"],
            "publisher": GDELT_PUBLISHER,
            "source_family": GDELT_SOURCE_FAMILY,
            "documentation_url": GDELT_DOCUMENTATION_URL,
            "terms_url": GDELT_TERMS_URL,
            "attribution": GDELT_ATTRIBUTION,
            "usage_terms": GDELT_USAGE_TERMS,
            "files": {
                filename: {
                    "bytes": task["bytes"],
                    "md5": task["md5"],
                    "sha256": task["sha256"],
                    "generation": task["generation"],
                }
                for filename, task in sorted(source_manifest["files"].items())
            },
        },
        "query": _query_manifest(),
        "counts": {
            "toc_documents": len(toc),
            "ngram_rows": ngram_rows,
            "documents_with_subject_terms": subject_documents,
            "documents_with_development_terms": development_documents,
            "candidate_articles": len(candidates),
            "distinct_candidate_urls": len(
                {candidate["article"]["url"] for candidate in candidates}
            ),
            "unsupported_languages": dict(sorted(unsupported_languages.items())),
        },
        "artifacts": {
            CANDIDATES_FILENAME: {
                "format": "application/x-ndjson",
                "records": len(candidates),
                "bytes": len(candidate_bytes),
                "sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            }
        },
    }
    manifest_bytes = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    sidecar_bytes = (
        f"{hashlib.sha256(manifest_bytes).hexdigest()}  {CANDIDATE_MANIFEST_FILENAME}\n"
    ).encode("ascii")
    return candidate_bytes, manifest_bytes, sidecar_bytes, manifest


def validate_candidate_bundle(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise GDELTValidationError("GDELT candidate bundle must be a regular directory")
    expected = {
        CANDIDATES_FILENAME,
        CANDIDATE_MANIFEST_FILENAME,
        CANDIDATE_MANIFEST_HASH_FILENAME,
    }
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != expected or len(entries) != len(expected):
        raise GDELTValidationError("GDELT candidate bundle file set is invalid")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise GDELTValidationError("GDELT candidate bundle contains a non-regular file")
    candidate_raw = (root / CANDIDATES_FILENAME).read_bytes()
    manifest_raw = (root / CANDIDATE_MANIFEST_FILENAME).read_bytes()
    sidecar_raw = (root / CANDIDATE_MANIFEST_HASH_FILENAME).read_bytes()
    expected_sidecar = (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {CANDIDATE_MANIFEST_FILENAME}\n"
    ).encode("ascii")
    if sidecar_raw != expected_sidecar:
        raise GDELTValidationError("GDELT candidate manifest sidecar does not match")
    try:
        manifest = json.loads(manifest_raw)
    except json.JSONDecodeError as error:
        raise GDELTValidationError("GDELT candidate manifest is not valid JSON") from error
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "pipeline",
        "generated_at",
        "scope",
        "source",
        "query",
        "counts",
        "artifacts",
    }:
        raise GDELTValidationError("GDELT candidate manifest schema changed")
    canonical_manifest = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    if manifest_raw != canonical_manifest:
        raise GDELTValidationError("GDELT candidate manifest is not canonical JSON")
    if (
        manifest.get("schema_version") != CANDIDATE_SCHEMA_VERSION
        or manifest.get("pipeline") != "gdelt_data_centre_news_candidate_extraction"
    ):
        raise GDELTValidationError("GDELT candidate manifest identity changed")
    if manifest.get("scope") != {
        "purpose": "review_only_news_article_discovery",
        "confirmed_release_eligible": False,
        **REVIEW_CONSTRAINTS,
    }:
        raise GDELTValidationError("GDELT candidate review constraints changed")
    if _timestamp(
        manifest.get("generated_at"), "GDELT candidate generated_at"
    ) != manifest.get("generated_at"):
        raise GDELTValidationError("GDELT candidate generated_at is not canonical UTC")
    if manifest.get("query") != _query_manifest():
        raise GDELTValidationError("GDELT candidate query contract changed")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "snapshot_id",
        "source_manifest_bytes",
        "source_manifest_sha256",
        "source_finished_at",
        "publisher",
        "source_family",
        "documentation_url",
        "terms_url",
        "attribution",
        "usage_terms",
        "files",
    } or any(
        source.get(field) != expected
        for field, expected in {
            "publisher": GDELT_PUBLISHER,
            "source_family": GDELT_SOURCE_FAMILY,
            "documentation_url": GDELT_DOCUMENTATION_URL,
            "terms_url": GDELT_TERMS_URL,
            "attribution": GDELT_ATTRIBUTION,
            "usage_terms": GDELT_USAGE_TERMS,
        }.items()
    ):
        raise GDELTValidationError("GDELT candidate source lineage changed")
    if not isinstance(source.get("snapshot_id"), str) or not _SNAPSHOT_RE.fullmatch(
        source["snapshot_id"]
    ):
        raise GDELTValidationError("GDELT candidate source snapshot ID is invalid")
    if not isinstance(source.get("source_manifest_sha256"), str) or not _SHA256_RE.fullmatch(
        source["source_manifest_sha256"]
    ):
        raise GDELTValidationError("GDELT candidate source manifest hash is invalid")
    if _nonnegative_integer(
        source.get("source_manifest_bytes"),
        "GDELT candidate source manifest bytes",
    ) <= 0:
        raise GDELTValidationError("GDELT candidate source manifest is empty")
    if _timestamp(
        source.get("source_finished_at"), "GDELT candidate source finished_at"
    ) != source.get("source_finished_at"):
        raise GDELTValidationError("GDELT candidate source finished_at is not canonical UTC")
    source_files = source.get("files")
    expected_source_files = {
        f"{source['snapshot_id']}.ngrams.txt.gz",
        f"{source['snapshot_id']}.toc.json.gz",
    }
    if not isinstance(source_files, dict) or set(source_files) != expected_source_files:
        raise GDELTValidationError("GDELT candidate source file inventory changed")
    for filename, record in source_files.items():
        if not isinstance(record, dict) or set(record) != {
            "bytes",
            "md5",
            "sha256",
            "generation",
        }:
            raise GDELTValidationError(
                f"GDELT candidate source file record changed: {filename}"
            )
        if _nonnegative_integer(
            record.get("bytes"), f"GDELT candidate source {filename} bytes"
        ) <= 0:
            raise GDELTValidationError(f"GDELT candidate source file is empty: {filename}")
        if not isinstance(record.get("md5"), str) or not _MD5_RE.fullmatch(
            record["md5"]
        ):
            raise GDELTValidationError(f"GDELT candidate source MD5 is invalid: {filename}")
        if not isinstance(record.get("sha256"), str) or not _SHA256_RE.fullmatch(
            record["sha256"]
        ):
            raise GDELTValidationError(
                f"GDELT candidate source SHA-256 is invalid: {filename}"
            )
        if not isinstance(record.get("generation"), str) or not record[
            "generation"
        ].isdigit():
            raise GDELTValidationError(
                f"GDELT candidate source generation is invalid: {filename}"
            )

    counts = manifest.get("counts")
    count_fields = {
        "toc_documents",
        "ngram_rows",
        "documents_with_subject_terms",
        "documents_with_development_terms",
        "candidate_articles",
        "distinct_candidate_urls",
        "unsupported_languages",
    }
    if not isinstance(counts, dict) or set(counts) != count_fields:
        raise GDELTValidationError("GDELT candidate counts schema changed")
    for field in count_fields - {"unsupported_languages"}:
        _nonnegative_integer(counts.get(field), f"GDELT candidate counts.{field}")
    unsupported = counts.get("unsupported_languages")
    if not isinstance(unsupported, dict) or any(
        not isinstance(language, str)
        or not language.strip()
        or _nonnegative_integer(
            count, f"GDELT candidate unsupported language {language!r}"
        ) <= 0
        for language, count in unsupported.items()
    ):
        raise GDELTValidationError("GDELT candidate unsupported-language counts are invalid")
    toc_documents = counts["toc_documents"]
    if (
        counts["ngram_rows"] < toc_documents
        or counts["documents_with_subject_terms"] > toc_documents
        or counts["documents_with_development_terms"] > toc_documents
        or counts["candidate_articles"] > counts["documents_with_subject_terms"]
        or counts["candidate_articles"] > counts["documents_with_development_terms"]
        or counts["distinct_candidate_urls"] > counts["candidate_articles"]
        or sum(unsupported.values()) > toc_documents
    ):
        raise GDELTValidationError("GDELT candidate counts do not reconcile")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {CANDIDATES_FILENAME}:
        raise GDELTValidationError("GDELT candidate artifact inventory changed")
    artifact = artifacts[CANDIDATES_FILENAME]
    if not isinstance(artifact, dict) or set(artifact) != {
        "format",
        "records",
        "bytes",
        "sha256",
    }:
        raise GDELTValidationError("GDELT candidate artifact record changed")
    _nonnegative_integer(artifact.get("records"), "GDELT candidate artifact records")
    _nonnegative_integer(artifact.get("bytes"), "GDELT candidate artifact bytes")
    if (
        artifact.get("format") != "application/x-ndjson"
        or artifact.get("bytes") != len(candidate_raw)
        or artifact.get("sha256") != hashlib.sha256(candidate_raw).hexdigest()
    ):
        raise GDELTValidationError("GDELT candidate artifact hash does not match")
    lines = candidate_raw.splitlines(keepends=True)
    if len(lines) != artifact.get("records"):
        raise GDELTValidationError("GDELT candidate record count does not match")
    candidate_ids: set[str] = set()
    document_ids: set[int] = set()
    candidate_urls: set[str] = set()
    previous_ordering_key: tuple[str, int] | None = None
    expected_date_prefix = datetime.strptime(
        source["snapshot_id"], "%Y%m%d%H%M%S"
    ).strftime("%Y-%m-%dT%H:%M:")
    for index, line in enumerate(lines, start=1):
        if not line.endswith(b"\n"):
            raise GDELTValidationError(f"GDELT candidate line {index} lacks newline")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise GDELTValidationError(f"GDELT candidate line {index} is invalid JSON") from error
        canonical = (
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        if canonical != line:
            raise GDELTValidationError(f"GDELT candidate line {index} is not canonical")
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "candidate_id",
            "snapshot_id",
            "gdelt_document_id",
            "article",
            "location_hints",
            "lexical_match",
            "source",
            "review_constraints",
        }:
            raise GDELTValidationError(f"GDELT candidate line {index} schema changed")
        if value.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
            raise GDELTValidationError(f"GDELT candidate line {index} version changed")
        if value.get("snapshot_id") != source["snapshot_id"]:
            raise GDELTValidationError(f"GDELT candidate line {index} snapshot changed")
        if value.get("review_constraints") != REVIEW_CONSTRAINTS:
            raise GDELTValidationError(f"GDELT candidate line {index} changed safeguards")
        candidate_source = value.get("source")
        if not isinstance(candidate_source, dict) or candidate_source != {
            "publisher": GDELT_PUBLISHER,
            "source_family": GDELT_SOURCE_FAMILY,
            "toc_url": _snapshot_url(f"{source['snapshot_id']}.toc.json.gz"),
            "ngrams_url": _snapshot_url(f"{source['snapshot_id']}.ngrams.txt.gz"),
            "documentation_url": GDELT_DOCUMENTATION_URL,
            "terms_url": GDELT_TERMS_URL,
            "attribution": GDELT_ATTRIBUTION,
        }:
            raise GDELTValidationError(
                f"GDELT candidate line {index} source lineage changed"
            )
        article = value.get("article")
        if not isinstance(article, dict) or set(article) != {
            "url",
            "date",
            "language",
            "title",
            "image_url",
            "publisher_domain",
        }:
            raise GDELTValidationError(f"GDELT candidate line {index} article is invalid")
        if not isinstance(article.get("url"), str):
            raise GDELTValidationError(f"GDELT candidate line {index} URL is invalid")
        parsed_url = urllib.parse.urlsplit(article["url"])
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise GDELTValidationError(f"GDELT candidate line {index} URL is invalid")
        if article.get("publisher_domain") != parsed_url.hostname:
            raise GDELTValidationError(f"GDELT candidate line {index} domain changed")
        if _timestamp(
            article.get("date"), f"GDELT candidate line {index} date"
        ) != article.get("date") or not article["date"].startswith(expected_date_prefix):
            raise GDELTValidationError(f"GDELT candidate line {index} date changed")
        if not isinstance(article.get("language"), str) or not article["language"].strip():
            raise GDELTValidationError(f"GDELT candidate line {index} language is invalid")
        if not isinstance(article.get("title"), str) or not article["title"].strip():
            raise GDELTValidationError(f"GDELT candidate line {index} title is invalid")
        image_url = article.get("image_url")
        if image_url is not None and not isinstance(image_url, str):
            raise GDELTValidationError(f"GDELT candidate line {index} image URL is invalid")
        lexical = value.get("lexical_match")
        if not isinstance(lexical, dict) or set(lexical) != {
            "lexicon_version",
            "subject_terms",
            "development_terms",
            "title_subject_terms",
            "title_development_terms",
            "matching_quadgrams",
            "ngram_match_count",
        }:
            raise GDELTValidationError(f"GDELT candidate line {index} match is invalid")
        language = _language(article["language"])
        allowed_subject = set(_terms_for(language, "subject"))
        allowed_development = set(_terms_for(language, "development"))
        if (
            lexical.get("lexicon_version") != QUERY_LEXICON_VERSION
            or not isinstance(lexical.get("subject_terms"), list)
            or not lexical["subject_terms"]
            or not set(lexical["subject_terms"]).issubset(allowed_subject)
            or not isinstance(lexical.get("development_terms"), list)
            or not lexical["development_terms"]
            or not set(lexical["development_terms"]).issubset(allowed_development)
        ):
            raise GDELTValidationError(f"GDELT candidate line {index} terms are invalid")
        for field, allowed in (
            ("subject_terms", allowed_subject),
            ("development_terms", allowed_development),
            ("title_subject_terms", allowed_subject),
            ("title_development_terms", allowed_development),
        ):
            terms = lexical.get(field)
            if (
                not isinstance(terms, list)
                or terms != sorted(set(terms))
                or not set(terms).issubset(allowed)
            ):
                raise GDELTValidationError(
                    f"GDELT candidate line {index} {field} is invalid"
                )
        normalized_title = _normalized_text(article["title"])
        if lexical["title_subject_terms"] != sorted(
            _matching_terms(normalized_title, allowed_subject)
        ) or lexical["title_development_terms"] != sorted(
            _matching_terms(normalized_title, allowed_development)
        ):
            raise GDELTValidationError(
                f"GDELT candidate line {index} title terms do not match its title"
            )
        snippets = lexical.get("matching_quadgrams")
        match_count = lexical.get("ngram_match_count")
        if (
            not isinstance(snippets, list)
            or snippets != sorted(set(snippets))
            or len(snippets) > MAX_MATCHING_QUADGRAMS
            or any(not isinstance(snippet, str) or not snippet for snippet in snippets)
            or isinstance(match_count, bool)
            or not isinstance(match_count, int)
            or match_count < 0
        ):
            raise GDELTValidationError(
                f"GDELT candidate line {index} quadgram evidence is invalid"
            )
        if any(
            not _matching_terms(_normalized_text(snippet), allowed_subject)
            and not _matching_terms(_normalized_text(snippet), allowed_development)
            for snippet in snippets
        ):
            raise GDELTValidationError(
                f"GDELT candidate line {index} includes an unrelated quadgram"
            )
        hints = value.get("location_hints")
        if not isinstance(hints, list) or any(
            not isinstance(hint, dict)
            or set(hint) != {"kind", "value", "scope"}
            or hint.get("kind") != "publisher_domain_cctld"
            or hint.get("scope")
            != "publisher_domain_only_not_article_or_facility_location"
            or not isinstance(hint.get("value"), str)
            or not re.fullmatch(r"[A-Z]{2}", hint["value"])
            for hint in hints
        ):
            raise GDELTValidationError(f"GDELT candidate line {index} hints are invalid")
        if hints != _publisher_location_hints(article["url"]):
            raise GDELTValidationError(
                f"GDELT candidate line {index} location hints changed"
            )
        candidate_id = value.get("candidate_id")
        if (
            not isinstance(candidate_id, str)
            or not re.fullmatch(r"gdelt-news-[0-9a-f]{24}", candidate_id)
            or candidate_id in candidate_ids
        ):
            raise GDELTValidationError(f"GDELT candidate line {index} ID is invalid")
        document_id = value.get("gdelt_document_id")
        if (
            isinstance(document_id, bool)
            or not isinstance(document_id, int)
            or document_id <= 0
            or document_id in document_ids
        ):
            raise GDELTValidationError(
                f"GDELT candidate line {index} document ID is invalid"
            )
        if candidate_id != _candidate_id(
            str(value.get("snapshot_id")), document_id, article["url"]
        ):
            raise GDELTValidationError(f"GDELT candidate line {index} ID changed")
        ordering_key = (article["date"], document_id)
        if previous_ordering_key is not None and ordering_key <= previous_ordering_key:
            raise GDELTValidationError("GDELT candidate records are not deterministically ordered")
        previous_ordering_key = ordering_key
        candidate_ids.add(candidate_id)
        document_ids.add(document_id)
        candidate_urls.add(article["url"])
    if (
        counts["candidate_articles"] != len(lines)
        or counts["distinct_candidate_urls"] != len(candidate_urls)
        or artifact["records"] != len(lines)
    ):
        raise GDELTValidationError("GDELT candidate count does not reconcile")
    return manifest


def write_candidate_bundle(
    source_directory: str | Path,
    output_directory: str | Path,
    *,
    generated_at: str,
    spec: SnapshotSpec = PINNED_SNAPSHOT,
) -> dict[str, Any]:
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise GDELTValidationError(f"refusing existing GDELT candidate output: {destination}")
    candidate_raw, manifest_raw, sidecar_raw, manifest = build_candidate_bundle(
        source_directory, generated_at=generated_at, spec=spec
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent)
    )
    try:
        for filename, raw in (
            (CANDIDATES_FILENAME, candidate_raw),
            (CANDIDATE_MANIFEST_FILENAME, manifest_raw),
            (CANDIDATE_MANIFEST_HASH_FILENAME, sidecar_raw),
        ):
            path = stage / filename
            with path.open("wb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
        validate_candidate_bundle(stage)
        stage.replace(destination)
    except Exception:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return manifest
