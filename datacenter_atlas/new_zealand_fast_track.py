"""Conservative New Zealand Fast-track data-centre planning lane.

This lane retains only bounded official page text.  Fast-track project pages are
captured as browser-rendered text extracts because the site rejects scripted
HTTP clients; Ministry for the Environment (MfE) pages are fetched directly.
Applicant attachments, images, plans, comments, and third-party PDFs are never
downloaded or redistributed.  Planning descriptions and process milestones do
not establish construction, operation, energy use, or a unique-site count.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import csv
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


SCHEMA_VERSION = 1
RELEASE_ID = "new-zealand-fast-track-2026-07-18-v1"
DEFINITION_FORMAT = "datacenter-atlas-new-zealand-fast-track-definition-v1"
CAPTURE_FORMAT = "datacenter-atlas-new-zealand-fast-track-capture-v1"
RELEASE_FORMAT = "datacenter-atlas-new-zealand-fast-track-release-v1"
ASSESSMENT_FORMAT = "datacenter-atlas-new-zealand-fast-track-assessment-v1"
INVENTORY_FORMAT = "datacenter-atlas-new-zealand-fast-track-inventory-v1"
RELATIONSHIP_FORMAT = "datacenter-atlas-new-zealand-fast-track-advisories-v1"
SCHEMA_FORMAT = "datacenter-atlas-new-zealand-fast-track-schema-v1"
BROWSER_EXTRACT_FORMAT = "datacenter-atlas-official-browser-text-extract-v1"

FASTTRACK_PROJECT_URL = (
    "https://www.fasttrack.govt.nz/projects/"
    "auckland-surf-park-community-stage-2"
)
FASTTRACK_COPYRIGHT_URL = (
    "https://www.fasttrack.govt.nz/secondary-pages/"
    "general-copyright-statement"
)
MFE_AUCKLAND_URL = (
    "https://environment.govt.nz/what-government-is-doing/areas-of-work/"
    "fast-track-consenting/auckland-surf-park-community/"
)
MFE_DATAGRID_URL = (
    "https://environment.govt.nz/acts-and-regulations/acts/"
    "fast-track-approvals/fast-track-projects/"
    "datagrid-sustainable-data-centre-park/"
)
MFE_COPYRIGHT_URL = "https://environment.govt.nz/about-this-site/copyright/"

FASTTRACK_LICENSE_URL = (
    "https://creativecommons.org/licenses/by-sa/4.0/"
)
MFE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

CURRENT_AUCKLAND_ID = "new-zealand-fast-track:auckland-surf-park-stage-2"
DATAGRID_ID = "new-zealand-fast-track:datagrid-fta104"
PRIOR_AUCKLAND_ID = "new-zealand-fast-track:auckland-surf-park-2022-116"

OBSERVATION_ORDER = (
    CURRENT_AUCKLAND_ID,
    DATAGRID_ID,
    PRIOR_AUCKLAND_ID,
)

PROJECT_CANDIDATE = "direct_data_centre_project_candidate"
PRIOR_RELATED = "prior_related_planning_observation"

FASTTRACK_PROJECT_SECTIONS = (
    {
        "heading": "Project identity",
        "text": [
            "Auckland Surf Park Community Stage 2",
            "A multiple-activity project including commercial and residential development in Dairy Flat, Auckland.",
            "Tags: Infrastructure Auckland",
        ],
    },
    {
        "heading": "Project summary",
        "text": [
            "The multiple-activity project will construct and operate:",
            "a hyperscale artificial intelligence data centre",
            "an integrated residential development comprising approximately 400 residential units",
            "a village centre",
            "a work-live precinct and associated activities.",
            "The project will also involve a variation to the decision on Auckland Community Surf Park Stage 1, which was granted resource consents in 2024 under the COVID-19 Recovery (Fast-track Consenting) Act 2020.",
        ],
    },
    {
        "heading": "Project location",
        "text": [
            "Approximately 54 hectares of land between Postmans Road and Dairy Flat Highway, Dairy Flat, Auckland.",
        ],
    },
    {
        "heading": "Project referral",
        "text": [
            "The Minister for Infrastructure referred the project to the Fast-track on 24 June 2025. The application was lodged on 21 March 2025.",
        ],
    },
    {
        "heading": "First substantive application",
        "text": [
            "The first substantive application was made on 11 March 2026. It was withdrawn by the applicant on 1 April 2026. The applicant has subsequently reapplied.",
        ],
    },
    {
        "heading": "Second substantive application",
        "text": [
            "AW Holdings 2021 Limited lodged their second substantive application for the Auckland Surf Park Community Stage 2 project on 7 May 2026.",
            "This second substantive application was returned to the applicant on 28 May 2026. The application was returned after it was assessed as not complying with all the requirements of section 46 (2) of the Fast-track Approvals Act 2024.",
        ],
    },
    {
        "heading": "Third substantive application",
        "text": [
            "The substantive application by AW Holdings 2021 Limited was deemed complete on 9 July 2026. The application complies with the requirements of section 46 (2) of the Fast-track Approvals Act 2024. The application was lodged on 19 June 2026.",
        ],
    },
)

FASTTRACK_COPYRIGHT_SECTIONS = (
    {
        "heading": "General copyright statement",
        "text": [
            "© This website fasttrack.govt.nz is protected by copyright owned by the Environmental Protection Authority.",
            "This work is licensed under the Creative Commons Attribution-ShareAlike 4.0 International licence.",
            "In essence, you are free to copy, distribute and adapt the work, as long as you attribute the work to the Environmental Protection Authority and abide by the other licence terms.",
            "This does not give you permission to use the Fast-track logo, the Environmental Protection Authority’s logo, the New Zealand Government logo, or the coat of arms in any way that breaches the Flags, Emblems and Names Protection Act 1981.",
            "This work may include photographs, images, copies of documents, or other supplied material for which the Environmental Protection Authority does not hold full copyright and is not covered by the Creative Commons licence.",
            "The re-use licence above does not apply to material that is subject to third party copyright. Permission to re-use third party copyright material must be sought form the copyright owner and cannot be given by the Environmental Protection Agency.",
        ],
    },
)

BROWSER_EXTRACT_CONTRACT = {
    "fasttrack_auckland_stage2": {
        "capture_method": "browser_text_extraction_from_official_url",
        "excluded_material": [
            "applicant attachments",
            "comments",
            "images and logos",
            "linked PDFs",
            "plans",
            "third-party documents",
        ],
        "format": BROWSER_EXTRACT_FORMAT,
        "sections": list(FASTTRACK_PROJECT_SECTIONS),
        "source_content_type": "text/html",
        "source_url": FASTTRACK_PROJECT_URL,
        "title": "Auckland Surf Park Community Stage 2",
    },
    "fasttrack_copyright": {
        "capture_method": "browser_text_extraction_from_official_url",
        "excluded_material": [
            "images and logos",
            "linked third-party material",
        ],
        "format": BROWSER_EXTRACT_FORMAT,
        "sections": list(FASTTRACK_COPYRIGHT_SECTIONS),
        "source_content_type": "text/html",
        "source_url": FASTTRACK_COPYRIGHT_URL,
        "title": "General copyright statement",
    },
}

MFE_EXTRACT_CONTRACT = {
    "mfe_auckland_2022_116": {
        "capture_method": "direct_https_get_text_extraction_from_official_html",
        "excluded_material": [
            "linked PDFs",
            "images and logos",
            "page design elements",
            "scripts and styles",
            "supporting documents",
        ],
        "format": BROWSER_EXTRACT_FORMAT,
        "sections": [
            {
                "heading": "Project identity and process",
                "text": [
                    "Auckland Surf Park Community",
                    "This project has been referred to an expert consenting panel for fast-track consenting under the Covid-19 Recovery (Fast-track Consenting Act 2020).",
                    "Last updated:",
                    "4 July 2024",
                    "Project ID",
                    "2022-116",
                    "Applicant",
                    "AW Holdings 2021 Limited",
                ],
            },
            {
                "heading": "Project summary",
                "text": [
                    "To construct and operate a surf park including operational buildings, 40 visitor-accommodation units, a 20-unit wellness retreat, a restaurant, data centre and 7-hectare solar farm to provide power to the development The project will include construction of infrastructure for three-waters services, roading, site access and parking, landscaping and planting, and revegetating a stream corridor.",
                ],
            },
            {
                "heading": "Location",
                "text": [
                    "At 1350 Dairy Flat Highway, Silverdale, Auckland.",
                ],
            },
        ],
        "source_content_type": "text/html",
        "source_url": MFE_AUCKLAND_URL,
        "title": "Auckland Surf Park Community",
    },
    "mfe_datagrid_fta104": {
        "capture_method": "direct_https_get_text_extraction_from_official_html",
        "excluded_material": [
            "application attachments",
            "images and logos",
            "maps and plans",
            "page design elements",
            "scripts and styles",
            "supporting documents",
        ],
        "format": BROWSER_EXTRACT_FORMAT,
        "sections": [
            {
                "heading": "Application metadata",
                "text": [
                    "Datagrid Sustainable Data Centre Park",
                    "Application FTA104 - Datagrid Sustainable Data Centre Park",
                    "Last updated:",
                    "14 January 2025",
                    "Southland",
                    "Infrastructure",
                    "Fast-track approvals",
                ],
            },
        ],
        "source_content_type": "text/html",
        "source_url": MFE_DATAGRID_URL,
        "title": "Datagrid Sustainable Data Centre Park",
    },
    "mfe_copyright": {
        "capture_method": "direct_https_get_text_extraction_from_official_html",
        "excluded_material": [
            "images and logos",
            "page design elements",
            "scripts and styles",
            "third-party material",
        ],
        "format": BROWSER_EXTRACT_FORMAT,
        "sections": [
            {
                "heading": "Copyright statement",
                "text": [
                    "Copyright material on the www.environment.govt.nz website is protected by copyright owned by the Ministry for the Environment on behalf of the Crown.",
                    "Crown copyright ©.",
                    "Unless indicated otherwise for specific items or collections of content (either below or within specific items or collections), this copyright material is licensed for re-use under the Creative Commons Attribution 4.0 International licence.",
                    "In essence, you are free to copy, distribute and adapt the material, as long as you attribute it to the Ministry for the Environment and abide by the other licence terms.",
                    "Please note that this licence does not apply to any logos, emblems and trade marks on the website or to the website’s design elements or to any photography and imagery. Those specific items may not be re-used without express permission.",
                    "The permission to reproduce material on this website does not extend to any material that is identified as being protected by copyright owned by a third party. (This includes material on websites you may access via links from this site).",
                    "The Ministry for the Environment cannot grant permission to reproduce such material: you must obtain permission from the copyright holders themselves.",
                ],
            },
        ],
        "source_content_type": "text/html",
        "source_url": MFE_COPYRIGHT_URL,
        "title": "Copyright statement",
    },
}

RAW_PATHS = {
    "fasttrack_auckland_stage2": (
        "raw/browser-text/fasttrack-auckland-stage2.json"
    ),
    "fasttrack_copyright": "raw/browser-text/fasttrack-copyright.json",
    "mfe_auckland_2022_116": "raw/text-extract/mfe-auckland-2022-116.json",
    "mfe_datagrid_fta104": "raw/text-extract/mfe-datagrid-fta104.json",
    "mfe_copyright": "raw/text-extract/mfe-copyright.json",
}

ARTIFACT_URLS = {
    "fasttrack_auckland_stage2": FASTTRACK_PROJECT_URL,
    "fasttrack_copyright": FASTTRACK_COPYRIGHT_URL,
    "mfe_auckland_2022_116": MFE_AUCKLAND_URL,
    "mfe_datagrid_fta104": MFE_DATAGRID_URL,
    "mfe_copyright": MFE_COPYRIGHT_URL,
}

ARTIFACT_PURPOSES = {
    "fasttrack_auckland_stage2": (
        "current official project summary, location, and process milestones"
    ),
    "fasttrack_copyright": "official Fast-track reuse and exclusion policy",
    "mfe_auckland_2022_116": (
        "official prior Auckland project metadata and relationship context"
    ),
    "mfe_datagrid_fta104": (
        "official Datagrid application metadata without linked attachments"
    ),
    "mfe_copyright": "official MfE reuse and exclusion policy",
}

RIGHTS_SCOPES = {
    "fasttrack_auckland_stage2": (
        "CC-BY-SA-4.0 official page text only; no supplied material"
    ),
    "fasttrack_copyright": "CC-BY-SA-4.0 rights evidence text only",
    "mfe_auckland_2022_116": "CC-BY-4.0 official page text only",
    "mfe_datagrid_fta104": "CC-BY-4.0 official page text only",
    "mfe_copyright": "CC-BY-4.0 rights evidence text only",
}

CAPTURE_METHODS = {
    "fasttrack_auckland_stage2": "browser_text_extraction_from_official_url",
    "fasttrack_copyright": "browser_text_extraction_from_official_url",
    "mfe_auckland_2022_116": (
        "direct_https_get_text_extraction_from_official_html"
    ),
    "mfe_datagrid_fta104": (
        "direct_https_get_text_extraction_from_official_html"
    ),
    "mfe_copyright": "direct_https_get_text_extraction_from_official_html",
}

ARTIFACT_ORDER = tuple(RAW_PATHS)
BROWSER_ARTIFACTS = (
    "fasttrack_auckland_stage2",
    "fasttrack_copyright",
)
DIRECT_ARTIFACTS = (
    "mfe_auckland_2022_116",
    "mfe_datagrid_fta104",
    "mfe_copyright",
)
OFFICIAL_HOSTS = frozenset({"www.fasttrack.govt.nz", "environment.govt.nz"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RIGHTS_POLICY = {
    "applicant_attachments_fetched_or_redistributed": False,
    "comments_fetched_or_redistributed": False,
    "fasttrack_license": "CC-BY-SA-4.0",
    "fasttrack_license_url": FASTTRACK_LICENSE_URL,
    "fasttrack_material_scope": "official page text only",
    "images_logos_or_plans_fetched_or_redistributed": False,
    "mfe_license": "CC-BY-4.0",
    "mfe_license_url": MFE_LICENSE_URL,
    "mfe_material_scope": "official page text only",
    "optional_advisory_report_retained": False,
    "rights_gate_passed_for_retained_scope": True,
    "third_party_documents_fetched_or_redistributed": False,
}

REVIEW_POLICY = {
    "annual_energy_consumption": None,
    "automatic_merge": False,
    "construction_evidence": False,
    "facility_lifecycle_from_process_stage": False,
    "gross_facility_power_mw": None,
    "it_capacity_mw": None,
    "operation_evidence": False,
    "physical_status": "proposed",
    "pue": None,
    "review_only": True,
    "satellite_verification": False,
    "unique_physical_site_count": None,
}

RELATIONSHIP_CONTRACT = (
    {
        "basis": (
            "The current Fast-track page says Stage 2 varies the decision on "
            "Auckland Community Surf Park Stage 1; the older MfE page is kept "
            "as prior planning context, not as a separate unique site."
        ),
        "members": [CURRENT_AUCKLAND_ID, PRIOR_AUCKLAND_ID],
        "relationship_id": "nz-fast-track:auckland-stage1-stage2-advisory",
        "relationship_type": "prior_project_and_stage_2_variation",
    },
)

DERIVED_FILENAMES = {
    "assessment": "assessment.json",
    "attribution": "ATTRIBUTION.txt",
    "definition": "definition.json",
    "inventory": "source-inventory.json",
    "observations_csv": "observations.csv",
    "observations_jsonl": "observations.jsonl",
    "readme": "README.md",
    "relationships": "advisory-relationships.json",
    "request_log": "request-log.jsonl",
    "schema": "schema.json",
}
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"


class NewZealandFastTrackError(ValueError):
    """Raised when capture, derivation, or validation fails closed."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag in {"script", "style", "svg", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        normalized = " ".join(data.split())
        if normalized:
            self.parts.append(normalized)


def canonical_json(value: Any, *, pretty: bool = False) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        sort_keys=True,
    )
    return (text + "\n").encode("utf-8")


def jsonl_bytes(values: Iterable[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json(value) for value in values)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise NewZealandFastTrackError(f"{label} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise NewZealandFastTrackError(f"{label} is not RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NewZealandFastTrackError(f"{label} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _checkpoint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": sha256_bytes(raw)}


def browser_extract_document(artifact_id: str, retrieved_at: str) -> dict[str, Any]:
    """Return the exact canonical browser-extract document after verification."""

    if artifact_id not in BROWSER_ARTIFACTS:
        raise NewZealandFastTrackError("unknown browser extract artifact")
    return {
        **BROWSER_EXTRACT_CONTRACT[artifact_id],
        "retrieved_at": _timestamp(retrieved_at, "browser extract retrieved_at"),
    }


def _mfe_extract_document(artifact_id: str, retrieved_at: str) -> dict[str, Any]:
    if artifact_id not in DIRECT_ARTIFACTS:
        raise NewZealandFastTrackError("unknown MfE text extract artifact")
    return {
        **MFE_EXTRACT_CONTRACT[artifact_id],
        "retrieved_at": _timestamp(retrieved_at, "MfE extract retrieved_at"),
    }


def _visible_text(raw: bytes, label: str) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise NewZealandFastTrackError(f"{label} is not UTF-8 HTML") from error
    parser = _VisibleTextParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:
        raise NewZealandFastTrackError(f"{label} HTML parsing failed") from error
    return "\n".join(parser.parts)


def _capture_specs() -> list[dict[str, str]]:
    return [
        {
            "artifact_id": artifact_id,
            "capture_method": CAPTURE_METHODS[artifact_id],
            "path": RAW_PATHS[artifact_id],
            "request_purpose": ARTIFACT_PURPOSES[artifact_id],
            "rights_scope": RIGHTS_SCOPES[artifact_id],
            "url": ARTIFACT_URLS[artifact_id],
        }
        for artifact_id in ARTIFACT_ORDER
    ]


def _fetch(
    url: str,
    *,
    timeout: float,
    max_attempts: int,
    user_agent: str,
) -> tuple[dict[str, Any], bytes]:
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
                "User-Agent": user_agent,
            },
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                completed = time.monotonic()
                metadata = {
                    "attempt_count": attempt,
                    "content_type": response.headers.get_content_type(),
                    "effective_url": response.geturl(),
                    "elapsed_ms": round((completed - started) * 1000),
                    "http_status": response.status,
                    "response_headers": {
                        name.lower(): response.headers[name]
                        for name in (
                            "Content-Length",
                            "Content-Type",
                            "Date",
                            "ETag",
                            "Last-Modified",
                        )
                        if response.headers.get(name) is not None
                    },
                }
                if response.status != 200 or not body:
                    raise NewZealandFastTrackError(
                        f"unexpected response status/body for {url}"
                    )
                return metadata, body
        except (
            HTTPError,
            URLError,
            TimeoutError,
            NewZealandFastTrackError,
        ) as error:
            last_error = error
            if attempt < max_attempts:
                time.sleep(0.75 * attempt)
    raise NewZealandFastTrackError(f"failed to retrieve {url}") from last_error


def _load_canonical_browser_extract(
    path: Path, artifact_id: str
) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise NewZealandFastTrackError(
            f"browser extract is absent: {artifact_id}"
        )
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NewZealandFastTrackError(
            f"browser extract is invalid JSON: {artifact_id}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json(value, pretty=True):
        raise NewZealandFastTrackError(
            f"browser extract is not canonical: {artifact_id}"
        )
    retrieved_at = _timestamp(
        value.get("retrieved_at"), f"{artifact_id} retrieved_at"
    )
    if value != browser_extract_document(artifact_id, retrieved_at):
        raise NewZealandFastTrackError(
            f"browser extract evidence contract changed: {artifact_id}"
        )
    return value, raw


def capture_live_sources(
    capture_directory: str | Path,
    browser_extract_directory: str | Path,
    *,
    timeout: float = 90.0,
    max_attempts: int = 4,
    pacing_seconds: float = 0.4,
    user_agent: str = "datacenter-atlas-new-zealand-fast-track/1.0",
) -> Path:
    """Assemble two browser extracts and fetch three bounded official pages."""

    destination = Path(capture_directory)
    browser_source = Path(browser_extract_directory)
    if destination.exists() or destination.is_symlink():
        raise NewZealandFastTrackError("capture directory already exists")
    if browser_source.is_symlink() or not browser_source.is_dir():
        raise NewZealandFastTrackError(
            "browser extract directory must be a regular directory"
        )
    if timeout <= 0 or max_attempts <= 0 or pacing_seconds < 0:
        raise NewZealandFastTrackError(
            "capture retry, pacing, or timeout policy is invalid"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    artifacts: dict[str, dict[str, Any]] = {}
    request_log: list[dict[str, Any]] = []
    previous_direct_completion: float | None = None
    try:
        for request_index, spec in enumerate(_capture_specs(), 1):
            artifact_id = spec["artifact_id"]
            if artifact_id in BROWSER_ARTIFACTS:
                source_file = browser_source / Path(spec["path"]).name
                evidence, body = _load_canonical_browser_extract(
                    source_file, artifact_id
                )
                requested_at = evidence["retrieved_at"]
                completed_at = evidence["retrieved_at"]
                response = {
                    "attempt_count": 1,
                    "content_type": "application/json",
                    "effective_url": evidence["source_url"],
                    "elapsed_ms": None,
                    "http_status": None,
                    "response_headers": {},
                    "source_content_type": evidence["source_content_type"],
                }
                method = "BROWSER_RENDERED_TEXT_EXTRACT"
                minimum_pacing: float | None = None
                capture_note = (
                    "Browser-rendered official text was retained because direct "
                    "scripted retrieval encountered the site's managed challenge."
                )
            else:
                if previous_direct_completion is not None:
                    elapsed = time.monotonic() - previous_direct_completion
                    if elapsed < pacing_seconds:
                        time.sleep(pacing_seconds - elapsed)
                requested_at = _now()
                response, source_body = _fetch(
                    spec["url"],
                    timeout=timeout,
                    max_attempts=max_attempts,
                    user_agent=user_agent,
                )
                completed_at = _now()
                previous_direct_completion = time.monotonic()
                source_text = _visible_text(source_body, artifact_id)
                contract_text = [
                    text
                    for section in MFE_EXTRACT_CONTRACT[artifact_id]["sections"]
                    for text in section["text"]
                ]
                _require_markers(source_text, contract_text, artifact_id)
                body = canonical_json(
                    _mfe_extract_document(artifact_id, completed_at),
                    pretty=True,
                )
                response["source_content_type"] = response["content_type"]
                response["source_response_bytes"] = len(source_body)
                response["source_response_sha256"] = sha256_bytes(source_body)
                response["content_type"] = "application/json"
                method = "GET"
                minimum_pacing = pacing_seconds
                capture_note = (
                    "Direct HTTPS HTML was validated and reduced to licensed "
                    "official page text; page design and excluded material were "
                    "not retained."
                )
            raw_path = destination / spec["path"]
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(body)
            checkpoint = {"bytes": len(body), "sha256": sha256_bytes(body)}
            artifacts[artifact_id] = {
                **spec,
                **checkpoint,
                "content_type": response["content_type"],
                "effective_url": response["effective_url"],
                "source_content_type": response["source_content_type"],
                "source_response_bytes": response.get("source_response_bytes"),
                "source_response_sha256": response.get(
                    "source_response_sha256"
                ),
            }
            request_log.append(
                {
                    "artifact_id": artifact_id,
                    "attempt_count": response["attempt_count"],
                    "bytes": len(body),
                    "capture_method": spec["capture_method"],
                    "capture_note": capture_note,
                    "completed_at": completed_at,
                    "content_type": response["content_type"],
                    "effective_url": response["effective_url"],
                    "elapsed_ms": response["elapsed_ms"],
                    "http_status": response["http_status"],
                    "method": method,
                    "minimum_pacing_seconds": minimum_pacing,
                    "network_request_observed": True,
                    "request_index": request_index,
                    "request_purpose": spec["request_purpose"],
                    "requested_at": requested_at,
                    "response_headers": response["response_headers"],
                    "retries_used": response["attempt_count"] - 1,
                    "sha256": checkpoint["sha256"],
                    "source_content_type": response["source_content_type"],
                    "source_response_bytes": response.get(
                        "source_response_bytes"
                    ),
                    "source_response_sha256": response.get(
                        "source_response_sha256"
                    ),
                    "url": spec["url"],
                    "user_agent": (
                        user_agent if artifact_id in DIRECT_ARTIFACTS else None
                    ),
                }
            )
        request_log_raw = jsonl_bytes(request_log)
        (destination / DERIVED_FILENAMES["request_log"]).write_bytes(
            request_log_raw
        )
        retrieved_at = max(
            _timestamp(item["completed_at"], "completed_at")
            for item in request_log
        )
        capture = {
            "artifacts": artifacts,
            "browser_rendered_requests": len(BROWSER_ARTIFACTS),
            "capture_events": len(request_log),
            "direct_http_requests": len(DIRECT_ARTIFACTS),
            "format": CAPTURE_FORMAT,
            "network_requests_observed": len(request_log),
            "release_id": RELEASE_ID,
            "request_log": {
                "bytes": len(request_log_raw),
                "path": DERIVED_FILENAMES["request_log"],
                "sha256": sha256_bytes(request_log_raw),
            },
            "retrieval_policy": {
                "browser_extracts_required": True,
                "direct_http_maximum_attempts_per_request": max_attempts,
                "direct_http_minimum_pacing_seconds": pacing_seconds,
                "direct_http_timeout_seconds": timeout,
                "direct_http_user_agent": user_agent,
                "fasttrack_direct_http_access_note": (
                    "Managed challenge prevented a faithful scripted HTML capture; "
                    "canonical browser-rendered text extracts are required."
                ),
            },
            "retrieved_at": retrieved_at,
            "schema_version": SCHEMA_VERSION,
        }
        (destination / "capture.json").write_bytes(
            canonical_json(capture, pretty=True)
        )
        candidate = definition_from_capture(capture)
        (destination / "definition-candidate.json").write_bytes(
            canonical_json(candidate, pretty=True)
        )
        return destination
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def definition_from_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    """Return the canonical pinned definition for a completed capture."""

    artifacts = capture.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(ARTIFACT_ORDER):
        raise NewZealandFastTrackError("capture artifact inventory changed")
    return {
        "exclusion_contract": {
            "applicant_attachments": "not_fetched",
            "comments": "not_fetched",
            "images_and_logos": "not_fetched",
            "linked_pdfs": "not_fetched",
            "plans": "not_fetched",
            "third_party_material": "not_fetched",
        },
        "format": DEFINITION_FORMAT,
        "observation_ids_in_order": list(OBSERVATION_ORDER),
        "raw_artifacts": {
            artifact_id: dict(artifacts[artifact_id])
            for artifact_id in ARTIFACT_ORDER
        },
        "relationship_contract": list(RELATIONSHIP_CONTRACT),
        "release_id": RELEASE_ID,
        "request_log": dict(capture["request_log"]),
        "retrieval_policy": dict(capture["retrieval_policy"]),
        "retrieved_at": capture["retrieved_at"],
        "review_policy": REVIEW_POLICY,
        "rights_policy": RIGHTS_POLICY,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "country": "New Zealand",
            "coverage_complete": False,
            "description": (
                "Three observations from two named project families on the "
                "bounded official pages; not a nationwide project census."
            ),
            "geography": "incomplete country scope",
            "project_candidates": 2,
            "prior_related_observations": 1,
            "unique_physical_site_count": None,
        },
    }


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NewZealandFastTrackError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise NewZealandFastTrackError(f"{label} must be a JSON object")
    return value


def load_definition(path: str | Path) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NewZealandFastTrackError("source definition is invalid JSON") from error
    if not isinstance(value, dict) or raw != canonical_json(value, pretty=True):
        raise NewZealandFastTrackError("source definition is not canonical")
    _validate_definition(value)
    return value, raw


def _validate_checkpoint(spec: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(spec, Mapping):
        raise NewZealandFastTrackError(f"{label} checkpoint is absent")
    if not isinstance(spec.get("bytes"), int) or spec["bytes"] <= 0:
        raise NewZealandFastTrackError(f"{label} byte count is invalid")
    digest = spec.get("sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise NewZealandFastTrackError(f"{label} SHA-256 is invalid")
    return spec


def _validate_definition(definition: Mapping[str, Any]) -> None:
    required_keys = {
        "exclusion_contract",
        "format",
        "observation_ids_in_order",
        "raw_artifacts",
        "relationship_contract",
        "release_id",
        "request_log",
        "retrieval_policy",
        "retrieved_at",
        "review_policy",
        "rights_policy",
        "schema_version",
        "scope",
    }
    if set(definition) != required_keys:
        raise NewZealandFastTrackError("source definition keys changed")
    if (
        definition.get("format") != DEFINITION_FORMAT
        or definition.get("release_id") != RELEASE_ID
        or definition.get("schema_version") != SCHEMA_VERSION
        or definition.get("observation_ids_in_order") != list(OBSERVATION_ORDER)
        or definition.get("relationship_contract")
        != list(RELATIONSHIP_CONTRACT)
        or definition.get("review_policy") != REVIEW_POLICY
        or definition.get("rights_policy") != RIGHTS_POLICY
    ):
        raise NewZealandFastTrackError(
            "definition identity, rights, or review contract changed"
        )
    expected_exclusions = {
        "applicant_attachments": "not_fetched",
        "comments": "not_fetched",
        "images_and_logos": "not_fetched",
        "linked_pdfs": "not_fetched",
        "plans": "not_fetched",
        "third_party_material": "not_fetched",
    }
    expected_scope = {
        "country": "New Zealand",
        "coverage_complete": False,
        "description": (
            "Three observations from two named project families on the bounded "
            "official pages; not a nationwide project census."
        ),
        "geography": "incomplete country scope",
        "project_candidates": 2,
        "prior_related_observations": 1,
        "unique_physical_site_count": None,
    }
    if (
        definition.get("exclusion_contract") != expected_exclusions
        or definition.get("scope") != expected_scope
    ):
        raise NewZealandFastTrackError("definition scope contract changed")
    _timestamp(definition.get("retrieved_at"), "retrieved_at")
    artifacts = definition.get("raw_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != set(ARTIFACT_ORDER):
        raise NewZealandFastTrackError("raw artifact inventory changed")
    required_artifact_keys = {
        "artifact_id",
        "bytes",
        "capture_method",
        "content_type",
        "effective_url",
        "path",
        "request_purpose",
        "rights_scope",
        "sha256",
        "source_content_type",
        "source_response_bytes",
        "source_response_sha256",
        "url",
    }
    for artifact_id in ARTIFACT_ORDER:
        spec = _validate_checkpoint(artifacts[artifact_id], artifact_id)
        if (
            set(spec) != required_artifact_keys
            or spec.get("artifact_id") != artifact_id
            or spec.get("capture_method") != CAPTURE_METHODS[artifact_id]
            or spec.get("path") != RAW_PATHS[artifact_id]
            or spec.get("request_purpose") != ARTIFACT_PURPOSES[artifact_id]
            or spec.get("rights_scope") != RIGHTS_SCOPES[artifact_id]
            or spec.get("url") != ARTIFACT_URLS[artifact_id]
        ):
            raise NewZealandFastTrackError(
                f"raw artifact contract changed: {artifact_id}"
            )
        parsed = urlsplit(str(spec.get("effective_url")))
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise NewZealandFastTrackError(
                f"raw artifact is not official HTTPS: {artifact_id}"
            )
    request_log = _validate_checkpoint(
        definition.get("request_log"), "request log"
    )
    if set(request_log) != {"bytes", "path", "sha256"} or request_log.get(
        "path"
    ) != DERIVED_FILENAMES["request_log"]:
        raise NewZealandFastTrackError("request-log contract changed")
    retrieval = definition.get("retrieval_policy")
    if (
        not isinstance(retrieval, Mapping)
        or retrieval.get("browser_extracts_required") is not True
        or retrieval.get("direct_http_maximum_attempts_per_request") != 4
        or retrieval.get("direct_http_minimum_pacing_seconds") != 0.4
        or retrieval.get("direct_http_timeout_seconds") != 90.0
        or retrieval.get("direct_http_user_agent")
        != "datacenter-atlas-new-zealand-fast-track/1.0"
        or not isinstance(retrieval.get("fasttrack_direct_http_access_note"), str)
    ):
        raise NewZealandFastTrackError("retrieval policy changed")


def _canonical_jsonl_objects(raw: bytes, label: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NewZealandFastTrackError(
                f"{label} line {line_number} is invalid"
            ) from error
        if not isinstance(value, dict) or line != canonical_json(value):
            raise NewZealandFastTrackError(
                f"{label} line {line_number} is not canonical"
            )
        values.append(value)
    return values


def _validate_capture_inputs(
    definition: Mapping[str, Any], capture: Path
) -> tuple[dict[str, bytes], bytes, list[dict[str, Any]]]:
    raw_bodies: dict[str, bytes] = {}
    artifacts = definition["raw_artifacts"]
    for artifact_id in ARTIFACT_ORDER:
        spec = artifacts[artifact_id]
        path = capture / spec["path"]
        if path.is_symlink() or not path.is_file():
            raise NewZealandFastTrackError(
                f"capture input is absent: {artifact_id}"
            )
        raw = path.read_bytes()
        if {"bytes": len(raw), "sha256": sha256_bytes(raw)} != {
            "bytes": spec["bytes"],
            "sha256": spec["sha256"],
        }:
            raise NewZealandFastTrackError(
                f"captured artifact changed: {artifact_id}"
            )
        raw_bodies[artifact_id] = raw
    log_path = capture / definition["request_log"]["path"]
    request_log_raw = log_path.read_bytes()
    if {"bytes": len(request_log_raw), "sha256": sha256_bytes(request_log_raw)} != {
        "bytes": definition["request_log"]["bytes"],
        "sha256": definition["request_log"]["sha256"],
    }:
        raise NewZealandFastTrackError("request log changed")
    request_log = _canonical_jsonl_objects(request_log_raw, "request log")
    if len(request_log) != len(ARTIFACT_ORDER):
        raise NewZealandFastTrackError("request-log count changed")
    for index, (artifact_id, entry) in enumerate(
        zip(ARTIFACT_ORDER, request_log, strict=True), 1
    ):
        spec = artifacts[artifact_id]
        common_valid = (
            entry.get("artifact_id") == artifact_id
            and entry.get("request_index") == index
            and entry.get("url") == spec["url"]
            and entry.get("effective_url") == spec["effective_url"]
            and entry.get("bytes") == spec["bytes"]
            and entry.get("sha256") == spec["sha256"]
            and entry.get("content_type") == spec["content_type"]
            and entry.get("source_content_type") == spec["source_content_type"]
            and entry.get("source_response_bytes")
            == spec["source_response_bytes"]
            and entry.get("source_response_sha256")
            == spec["source_response_sha256"]
            and entry.get("capture_method") == spec["capture_method"]
            and entry.get("request_purpose") == spec["request_purpose"]
            and entry.get("network_request_observed") is True
        )
        if artifact_id in BROWSER_ARTIFACTS:
            method_valid = (
                entry.get("method") == "BROWSER_RENDERED_TEXT_EXTRACT"
                and entry.get("http_status") is None
                and entry.get("attempt_count") == 1
                and entry.get("retries_used") == 0
                and entry.get("minimum_pacing_seconds") is None
                and entry.get("user_agent") is None
                and entry.get("response_headers") == {}
                and entry.get("source_response_bytes") is None
                and entry.get("source_response_sha256") is None
            )
        else:
            method_valid = (
                entry.get("method") == "GET"
                and entry.get("http_status") == 200
                and isinstance(entry.get("attempt_count"), int)
                and 1 <= entry["attempt_count"] <= 4
                and entry.get("retries_used") == entry["attempt_count"] - 1
                and entry.get("minimum_pacing_seconds") == 0.4
                and entry.get("user_agent")
                == "datacenter-atlas-new-zealand-fast-track/1.0"
                and isinstance(entry.get("source_response_bytes"), int)
                and entry["source_response_bytes"] > entry["bytes"]
                and isinstance(entry.get("source_response_sha256"), str)
                and SHA256_RE.fullmatch(entry["source_response_sha256"])
                is not None
            )
        if not common_valid or not method_valid:
            raise NewZealandFastTrackError(
                f"request lineage changed: {artifact_id}"
            )
        _timestamp(entry.get("requested_at"), "request requested_at")
        _timestamp(entry.get("completed_at"), "request completed_at")
    if max(item["completed_at"] for item in request_log) != definition["retrieved_at"]:
        raise NewZealandFastTrackError(
            "retrieval timestamp and request log differ"
        )
    return raw_bodies, request_log_raw, request_log


def _parse_browser_extract(raw: bytes, artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NewZealandFastTrackError(
            f"browser extract changed: {artifact_id}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json(value, pretty=True):
        raise NewZealandFastTrackError(
            f"browser extract is not canonical: {artifact_id}"
        )
    retrieved_at = _timestamp(
        value.get("retrieved_at"), f"{artifact_id} retrieved_at"
    )
    if value != browser_extract_document(artifact_id, retrieved_at):
        raise NewZealandFastTrackError(
            f"browser extract evidence changed: {artifact_id}"
        )
    return value


def _parse_mfe_extract(raw: bytes, artifact_id: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NewZealandFastTrackError(
            f"MfE text extract changed: {artifact_id}"
        ) from error
    if not isinstance(value, dict) or raw != canonical_json(value, pretty=True):
        raise NewZealandFastTrackError(
            f"MfE text extract is not canonical: {artifact_id}"
        )
    retrieved_at = _timestamp(
        value.get("retrieved_at"), f"{artifact_id} retrieved_at"
    )
    if value != _mfe_extract_document(artifact_id, retrieved_at):
        raise NewZealandFastTrackError(
            f"MfE text extract evidence changed: {artifact_id}"
        )
    return value


def _require_markers(text: str, markers: Sequence[str], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise NewZealandFastTrackError(
            f"{label} evidence markers changed: {missing[0]}"
        )


def _validate_source_evidence(
    raw_bodies: Mapping[str, bytes]
) -> dict[str, Any]:
    current = _parse_browser_extract(
        raw_bodies["fasttrack_auckland_stage2"],
        "fasttrack_auckland_stage2",
    )
    fasttrack_rights = _parse_browser_extract(
        raw_bodies["fasttrack_copyright"], "fasttrack_copyright"
    )
    prior = _parse_mfe_extract(
        raw_bodies["mfe_auckland_2022_116"], "mfe_auckland_2022_116"
    )
    datagrid = _parse_mfe_extract(
        raw_bodies["mfe_datagrid_fta104"], "mfe_datagrid_fta104"
    )
    mfe_rights = _parse_mfe_extract(
        raw_bodies["mfe_copyright"], "mfe_copyright"
    )
    return {
        "current": current,
        "datagrid": datagrid,
        "fasttrack_rights": fasttrack_rights,
        "mfe_rights": mfe_rights,
        "prior": prior,
    }


def _source(
    definition: Mapping[str, Any], artifact_id: str, publisher: str
) -> dict[str, Any]:
    spec = definition["raw_artifacts"][artifact_id]
    return {
        "artifact_id": artifact_id,
        "capture_method": spec["capture_method"],
        "publisher": publisher,
        "raw_bytes": spec["bytes"],
        "raw_sha256": spec["sha256"],
        "url": spec["url"],
    }


def _empty_metrics(
    untyped_context_statements: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "annual_energy_observations": [],
        "capacity_observations": [],
        "power_observations": [],
        "pue_observations": [],
        "untyped_context_statements": [
            dict(item) for item in untyped_context_statements
        ],
    }


def _physical_status() -> dict[str, Any]:
    return {
        "construction_source_supported": False,
        "evidence_scope": "official_planning_or_application_page_only",
        "label": "proposed",
        "operation_source_supported": False,
        "satellite_verified": False,
    }


def _observations(definition: Mapping[str, Any]) -> list[dict[str, Any]]:
    current_source = _source(
        definition,
        "fasttrack_auckland_stage2",
        "Environmental Protection Authority / Fast-track",
    )
    datagrid_source = _source(
        definition,
        "mfe_datagrid_fta104",
        "New Zealand Ministry for the Environment",
    )
    prior_source = _source(
        definition,
        "mfe_auckland_2022_116",
        "New Zealand Ministry for the Environment",
    )
    shared = {
        "accepted_relationship": False,
        "automatic_merge": False,
        "physical_status": _physical_status(),
        "promotion_boundaries": REVIEW_POLICY,
        "review_only": True,
        "unique_site_counted": False,
    }
    current = {
        **shared,
        "advisory_relationship_ids": [
            "nz-fast-track:auckland-stage1-stage2-advisory"
        ],
        "candidate_classification": PROJECT_CANDIDATE,
        "data_centre_characterisation": {
            "declared_facility_type": "hyperscale",
            "declared_workload": "artificial_intelligence",
            "operationally_verified": False,
            "scope": "proposed component of a mixed-use project",
            "source_text": "a hyperscale artificial intelligence data centre",
        },
        "facility_metrics": _empty_metrics(),
        "mixed_project_context": {
            "data_centre_land_area_promoted": False,
            "project_area_hectares": None,
            "project_area_source_text": (
                "Approximately 54 hectares of land between Postmans Road and "
                "Dairy Flat Highway, Dairy Flat, Auckland."
            ),
            "reason": (
                "The 54-hectare statement covers the entire mixed project, not "
                "the data-centre footprint."
            ),
        },
        "observation_id": CURRENT_AUCKLAND_ID,
        "planning_process": {
            "current_state": (
                "third_substantive_application_deemed_complete_under_section_46_2"
            ),
            "events": [
                {
                    "date": "2025-03-21",
                    "event": "referral_application_lodged",
                },
                {
                    "date": "2025-06-24",
                    "event": "referred_to_fast_track",
                },
                {
                    "date": "2026-03-11",
                    "event": "first_substantive_application_made",
                },
                {
                    "date": "2026-04-01",
                    "event": "first_substantive_application_withdrawn",
                },
                {
                    "date": "2026-05-07",
                    "event": "second_substantive_application_lodged",
                },
                {
                    "date": "2026-05-28",
                    "event": (
                        "second_substantive_application_returned_for_"
                        "section_46_2_noncompliance"
                    ),
                },
                {
                    "date": "2026-06-19",
                    "event": "third_substantive_application_lodged",
                },
                {
                    "date": "2026-07-09",
                    "event": (
                        "third_substantive_application_deemed_complete_"
                        "under_section_46_2"
                    ),
                },
            ],
            "facility_lifecycle_status_promoted": False,
            "scope": "Fast-track application process only",
        },
        "project": {
            "applicant": "AW Holdings 2021 Limited",
            "application_id": None,
            "location": (
                "Land between Postmans Road and Dairy Flat Highway, Dairy Flat, "
                "Auckland"
            ),
            "name": "Auckland Surf Park Community Stage 2",
        },
        "record_type": "official_current_project_planning_observation",
        "source": current_source,
    }
    datagrid = {
        **shared,
        "advisory_relationship_ids": [],
        "candidate_classification": PROJECT_CANDIDATE,
        "data_centre_characterisation": {
            "declared_facility_type": None,
            "declared_workload": None,
            "operationally_verified": False,
            "scope": "project title on an official older application page",
            "source_text": "Datagrid Sustainable Data Centre Park",
        },
        "facility_metrics": _empty_metrics(),
        "mixed_project_context": None,
        "observation_id": DATAGRID_ID,
        "planning_process": {
            "current_state": "older_official_application_metadata_only",
            "events": [
                {
                    "date": "2025-01-14",
                    "event": "official_page_last_updated",
                }
            ],
            "facility_lifecycle_status_promoted": False,
            "scope": (
                "Application FTA104 page metadata; linked application and "
                "supporting documents were not fetched"
            ),
        },
        "project": {
            "applicant": None,
            "application_id": "FTA104",
            "location": "Southland, New Zealand",
            "name": "Datagrid Sustainable Data Centre Park",
        },
        "record_type": "official_project_application_metadata_observation",
        "source": datagrid_source,
    }
    prior = {
        **shared,
        "advisory_relationship_ids": [
            "nz-fast-track:auckland-stage1-stage2-advisory"
        ],
        "candidate_classification": PRIOR_RELATED,
        "data_centre_characterisation": {
            "declared_facility_type": None,
            "declared_workload": None,
            "operationally_verified": False,
            "scope": "one component of the prior mixed project summary",
            "source_text": "data centre",
        },
        "facility_metrics": _empty_metrics(
            (
                {
                    "metric_type": None,
                    "promoted_to_data_centre_power_or_energy": False,
                    "reason": (
                        "The page says the solar farm powers the whole development; "
                        "it does not type data-centre load, power, or energy."
                    ),
                    "source_text": (
                        "data centre and 7-hectare solar farm to provide power to "
                        "the development"
                    ),
                    "unit": None,
                    "value": None,
                },
            )
        ),
        "mixed_project_context": {
            "data_centre_land_area_promoted": False,
            "project_area_hectares": None,
            "project_area_source_text": None,
            "reason": "The page describes a multi-component surf-park development.",
        },
        "observation_id": PRIOR_AUCKLAND_ID,
        "planning_process": {
            "current_state": "prior_project_referred_under_2020_act",
            "events": [
                {
                    "date": "2024-07-04",
                    "event": "official_page_last_updated",
                }
            ],
            "facility_lifecycle_status_promoted": False,
            "scope": "prior Fast-track consenting page only",
        },
        "project": {
            "applicant": "AW Holdings 2021 Limited",
            "application_id": "2022-116",
            "location": (
                "1350 Dairy Flat Highway, Silverdale, Auckland, New Zealand"
            ),
            "name": "Auckland Surf Park Community",
        },
        "record_type": "official_prior_related_planning_observation",
        "source": prior_source,
    }
    result = [current, datagrid, prior]
    if [item["observation_id"] for item in result] != list(OBSERVATION_ORDER):
        raise NewZealandFastTrackError("observation order changed")
    return result


def _relationships_document() -> dict[str, Any]:
    return {
        "accepted_relationships": 0,
        "automatic_merges": 0,
        "format": RELATIONSHIP_FORMAT,
        "groups": [
            {
                **relationship,
                "accepted": False,
                "automatic_merge": False,
                "counted_as_separate_unique_site": False,
                "identity_resolution_performed": False,
            }
            for relationship in RELATIONSHIP_CONTRACT
        ],
        "group_count": len(RELATIONSHIP_CONTRACT),
        "unique_physical_site_count": None,
    }


def _inventory(
    definition: Mapping[str, Any], observations: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return {
        "artifact_capture_method_counts": dict(
            sorted(
                Counter(
                    spec["capture_method"]
                    for spec in definition["raw_artifacts"].values()
                ).items()
            )
        ),
        "artifact_count": len(ARTIFACT_ORDER),
        "candidate_classification_counts": dict(
            sorted(Counter(item["candidate_classification"] for item in observations).items())
        ),
        "coverage_complete": False,
        "excluded_material": definition["exclusion_contract"],
        "format": INVENTORY_FORMAT,
        "observation_count": len(observations),
        "observation_ids_in_order": [
            item["observation_id"] for item in observations
        ],
        "physical_status_counts": dict(
            sorted(Counter(item["physical_status"]["label"] for item in observations).items())
        ),
        "raw_bytes": sum(
            spec["bytes"] for spec in definition["raw_artifacts"].values()
        ),
        "raw_sha256_by_artifact": {
            artifact_id: definition["raw_artifacts"][artifact_id]["sha256"]
            for artifact_id in ARTIFACT_ORDER
        },
        "unique_physical_site_count": None,
    }


def _schema_document() -> dict[str, Any]:
    return {
        "format": SCHEMA_FORMAT,
        "observation_contract": {
            "candidate_classification": (
                "direct candidate or prior related planning observation"
            ),
            "data_centre_characterisation": (
                "declared proposed wording; not operational verification"
            ),
            "facility_metrics": (
                "typed metric arrays remain empty unless the retained official "
                "page text supports facility-specific values"
            ),
            "physical_status": (
                "proposed/review-only; application process is not construction"
            ),
            "planning_process": "official process metadata only",
            "unique_site_counted": False,
        },
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def _observations_csv(observations: Sequence[Mapping[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    fields = [
        "observation_id",
        "record_type",
        "candidate_classification",
        "project_name",
        "application_id",
        "applicant",
        "location",
        "physical_status",
        "planning_process_state",
        "declared_facility_type",
        "declared_workload",
        "source_url",
        "review_only",
        "construction_source_supported",
        "operation_source_supported",
        "unique_site_counted",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in observations:
        writer.writerow(
            {
                "observation_id": item["observation_id"],
                "record_type": item["record_type"],
                "candidate_classification": item["candidate_classification"],
                "project_name": item["project"]["name"],
                "application_id": item["project"]["application_id"] or "",
                "applicant": item["project"]["applicant"] or "",
                "location": item["project"]["location"],
                "physical_status": item["physical_status"]["label"],
                "planning_process_state": item["planning_process"][
                    "current_state"
                ],
                "declared_facility_type": item[
                    "data_centre_characterisation"
                ]["declared_facility_type"]
                or "",
                "declared_workload": item[
                    "data_centre_characterisation"
                ]["declared_workload"]
                or "",
                "source_url": item["source"]["url"],
                "review_only": "true",
                "construction_source_supported": "false",
                "operation_source_supported": "false",
                "unique_site_counted": "false",
            }
        )
    return buffer.getvalue().encode("utf-8")


def _attribution(retrieved_at: str) -> bytes:
    return f"""New Zealand Fast-track official-page text assessment
Release: {RELEASE_ID}
Retrieved through: {retrieved_at}

Fast-track source text
Copyright Environmental Protection Authority. The retained official page text is
used under Creative Commons Attribution-ShareAlike 4.0 International:
{FASTTRACK_LICENSE_URL}
Sources:
- {FASTTRACK_PROJECT_URL}
- {FASTTRACK_COPYRIGHT_URL}

Ministry for the Environment source text
Copyright Ministry for the Environment on behalf of the Crown. The retained
official page text is used under Creative Commons Attribution 4.0 International:
{MFE_LICENSE_URL}
Sources:
- {MFE_AUCKLAND_URL}
- {MFE_DATAGRID_URL}
- {MFE_COPYRIGHT_URL}

Only bounded official page text is retained. Logos, photographs, imagery, page
design, applicant attachments, comments, plans, linked PDFs, and third-party
material are excluded. No licence is asserted for excluded material.
""".encode("utf-8")


def _readme(retrieved_at: str) -> bytes:
    return f"""# New Zealand Fast-track data-centre planning observations

Frozen source assessment `{RELEASE_ID}`, retrieved through `{retrieved_at}`.

This bounded lane emits three review-only planning observations: two named
data-centre project candidates and one older Auckland observation retained only
as related prior context. It is **not** a complete New Zealand data-centre list.

The current Auckland Stage 2 page describes a proposed hyperscale artificial-
intelligence data-centre component inside an approximately 54-hectare mixed-use
project. The 54 hectares are not recorded as data-centre site area. Its latest
retained process event is the third substantive application being deemed
complete under section 46(2) on 9 July 2026. This is application-process evidence,
not evidence of construction or operation.

The Datagrid observation retains only Application FTA104 page metadata. Linked
application files, location plans, images, assessment forms, and other supporting
documents were not fetched. The optional advisory-group PDF was not retained:
its project-description material may be supplied by an applicant and the rights
needed to redistribute it were not sufficiently secure. Consequently this lane
does not emit the report's capacity language or any Datagrid power/energy metric.

The older Auckland page says a 7-hectare solar farm would provide power to the
whole development. That sentence remains untyped context and is not data-centre
power, IT capacity, annual energy, or PUE evidence.

Fast-track pages require browser-rendered text capture because direct scripted
access encounters a managed challenge. The two browser extracts are exact,
canonical, official-page text selections. The three MfE pages are fetched over
HTTPS and reduced to exact licensed text selections before retention. This keeps
excluded design, imagery, attachments, and third-party material out of the bundle.

Validate and reproduce every derived byte offline with:

```sh
python3 scripts/fetch_build_new_zealand_fast_track.py --validate-only
```
""".encode("utf-8")


def derive_release_files(
    definition: Mapping[str, Any],
    raw_bodies: Mapping[str, bytes],
    request_log_raw: bytes,
    request_log: Sequence[Mapping[str, Any]],
) -> dict[str, bytes]:
    """Derive every non-manifest file from pinned text extracts offline."""

    _validate_source_evidence(raw_bodies)
    observations = _observations(definition)
    relationships = _relationships_document()
    inventory = _inventory(definition, observations)
    counts = inventory["candidate_classification_counts"]
    if counts != {PRIOR_RELATED: 1, PROJECT_CANDIDATE: 2}:
        raise NewZealandFastTrackError("candidate accounting changed")
    assessment = {
        "advisory_report_boundary": {
            "capacity_statement_retained": False,
            "optional_advisory_report_retained": False,
            "power_or_energy_metric_emitted": False,
            "reason": (
                "The optional report was unnecessary for the bounded application "
                "metadata and its applicant-supplied project description was not "
                "clearly within the official page-text reuse licence."
            ),
        },
        "advisory_relationships": {
            "accepted_relationships": 0,
            "automatic_merges": 0,
            "group_count": relationships["group_count"],
            "unique_physical_site_count": None,
        },
        "assessed_at": definition["retrieved_at"],
        "candidate_classification_counts": counts,
        "coverage": definition["scope"],
        "format": ASSESSMENT_FORMAT,
        "physical_status_counts": inventory["physical_status_counts"],
        "raw_artifacts": definition["raw_artifacts"],
        "release_id": RELEASE_ID,
        "request_lineage": {
            **definition["request_log"],
            "browser_rendered_requests": len(BROWSER_ARTIFACTS),
            "capture_events": len(request_log),
            "direct_http_requests": len(DIRECT_ARTIFACTS),
            "validator_network_requests": 0,
        },
        "review_policy": REVIEW_POLICY,
        "rights_assessment": {
            **RIGHTS_POLICY,
            "assessed_from_fasttrack_copyright_page": FASTTRACK_COPYRIGHT_URL,
            "assessed_from_mfe_copyright_page": MFE_COPYRIGHT_URL,
            "retained_artifacts_are_text_extracts": True,
        },
        "schema_version": SCHEMA_VERSION,
        "typed_metric_counts": {
            "annual_energy": 0,
            "capacity": 0,
            "power": 0,
            "pue": 0,
        },
        "untyped_context_statement_count": 1,
    }
    return {
        DERIVED_FILENAMES["assessment"]: canonical_json(
            assessment, pretty=True
        ),
        DERIVED_FILENAMES["attribution"]: _attribution(
            definition["retrieved_at"]
        ),
        DERIVED_FILENAMES["definition"]: canonical_json(
            definition, pretty=True
        ),
        DERIVED_FILENAMES["inventory"]: canonical_json(inventory, pretty=True),
        DERIVED_FILENAMES["observations_csv"]: _observations_csv(observations),
        DERIVED_FILENAMES["observations_jsonl"]: jsonl_bytes(observations),
        DERIVED_FILENAMES["readme"]: _readme(definition["retrieved_at"]),
        DERIVED_FILENAMES["relationships"]: canonical_json(
            relationships, pretty=True
        ),
        DERIVED_FILENAMES["request_log"]: request_log_raw,
        DERIVED_FILENAMES["schema"]: canonical_json(
            _schema_document(), pretty=True
        ),
    }


def _artifact_role(filename: str) -> str:
    if filename.startswith("raw/"):
        return "bounded_official_page_text_evidence"
    return {
        "assessment.json": "derived_assessment",
        "ATTRIBUTION.txt": "attribution",
        "definition.json": "source_definition",
        "source-inventory.json": "derived_inventory",
        "observations.csv": "review_observations",
        "observations.jsonl": "review_observations",
        "README.md": "documentation",
        "advisory-relationships.json": "advisory_relationships",
        "request-log.jsonl": "request_lineage",
        "schema.json": "schema",
    }[filename]


def _license_scope(filename: str) -> str:
    if filename.startswith("raw/browser-text/"):
        return "CC-BY-SA-4.0_official_page_text_only"
    if filename.startswith("raw/text-extract/"):
        return "CC-BY-4.0_official_page_text_only"
    if filename in {"observations.jsonl", "observations.csv", "README.md"}:
        return "mixed_CC-BY-SA-4.0_and_CC-BY-4.0_source_scope_see_ATTRIBUTION"
    return "derived_by_datacenter_atlas_see_ATTRIBUTION"


def _manifest(path: Path, retrieved_at: str) -> bytes:
    files: dict[str, Any] = {}
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file.relative_to(path).as_posix()
        if relative in {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}:
            continue
        files[relative] = {
            **_checkpoint(file),
            "license_scope": _license_scope(relative),
            "role": _artifact_role(relative),
        }
    return canonical_json(
        {
            "files": files,
            "format": RELEASE_FORMAT,
            "release_id": RELEASE_ID,
            "retrieved_at": retrieved_at,
            "schema_version": SCHEMA_VERSION,
        },
        pretty=True,
    )


def _freeze(path: Path) -> None:
    for entry in sorted(
        path.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    path.chmod(0o555)


def write_release_bundle(
    definition_path: str | Path,
    capture_directory: str | Path,
    output_directory: str | Path,
    *,
    freeze: bool = True,
) -> Path:
    """Build a new immutable release from a pinned completed capture."""

    definition, _ = load_definition(definition_path)
    capture = Path(capture_directory)
    raw_bodies, request_log_raw, request_log = _validate_capture_inputs(
        definition, capture
    )
    destination = Path(os.path.abspath(os.fspath(output_directory)))
    if destination.exists() or destination.is_symlink():
        raise NewZealandFastTrackError("output release already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.stage-", dir=destination.parent
        )
    )
    try:
        for artifact_id in ARTIFACT_ORDER:
            relative = Path(definition["raw_artifacts"][artifact_id]["path"])
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw_bodies[artifact_id])
        for filename, raw in derive_release_files(
            definition, raw_bodies, request_log_raw, request_log
        ).items():
            target = stage / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        manifest_raw = _manifest(stage, definition["retrieved_at"])
        (stage / MANIFEST_FILENAME).write_bytes(manifest_raw)
        (stage / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n",
            encoding="ascii",
        )
        if freeze:
            _freeze(stage)
        stage.replace(destination)
        return destination
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise


def _expected_files(definition: Mapping[str, Any]) -> set[str]:
    return {
        *(spec["path"] for spec in definition["raw_artifacts"].values()),
        *DERIVED_FILENAMES.values(),
        MANIFEST_FILENAME,
        MANIFEST_HASH_FILENAME,
    }


def validate_release_bundle(
    path: str | Path, *, definition_path: str | Path | None = None
) -> dict[str, Any]:
    """Validate and byte-reproduce the release with zero network requests."""

    release = Path(path)
    if release.is_symlink() or not release.is_dir():
        raise NewZealandFastTrackError("release must be a regular directory")
    bundle_definition = release / DERIVED_FILENAMES["definition"]
    definition, definition_raw = load_definition(
        definition_path if definition_path is not None else bundle_definition
    )
    if bundle_definition.read_bytes() != definition_raw:
        raise NewZealandFastTrackError("bundle and source definitions differ")
    actual_files = {
        item.relative_to(release).as_posix()
        for item in release.rglob("*")
        if item.is_file()
    }
    if actual_files != _expected_files(definition):
        raise NewZealandFastTrackError("release file inventory changed")
    manifest_path = release / MANIFEST_FILENAME
    manifest = _load_json(manifest_path, "manifest")
    manifest_raw = manifest_path.read_bytes()
    if manifest_raw != canonical_json(manifest, pretty=True):
        raise NewZealandFastTrackError("manifest is not canonical")
    expected_sidecar = f"{sha256_bytes(manifest_raw)}  {MANIFEST_FILENAME}\n"
    if (release / MANIFEST_HASH_FILENAME).read_text(
        encoding="ascii"
    ) != expected_sidecar:
        raise NewZealandFastTrackError("manifest sidecar changed")
    if (
        manifest.get("format") != RELEASE_FORMAT
        or manifest.get("release_id") != RELEASE_ID
        or manifest.get("retrieved_at") != definition["retrieved_at"]
        or manifest.get("schema_version") != SCHEMA_VERSION
        or set(manifest.get("files", {}))
        != actual_files - {MANIFEST_FILENAME, MANIFEST_HASH_FILENAME}
    ):
        raise NewZealandFastTrackError(
            "manifest identity or file inventory changed"
        )
    for filename, checkpoint in manifest["files"].items():
        if _checkpoint(release / filename) != {
            "bytes": checkpoint.get("bytes"),
            "sha256": checkpoint.get("sha256"),
        }:
            raise NewZealandFastTrackError(f"release file changed: {filename}")
    if manifest_raw != _manifest(release, definition["retrieved_at"]):
        raise NewZealandFastTrackError("manifest metadata changed")
    raw_bodies, request_log_raw, request_log = _validate_capture_inputs(
        definition, release
    )
    reproduced = derive_release_files(
        definition, raw_bodies, request_log_raw, request_log
    )
    for filename, expected in reproduced.items():
        if (release / filename).read_bytes() != expected:
            raise NewZealandFastTrackError(
                f"offline reproduction mismatch: {filename}"
            )
    observations = _canonical_jsonl_objects(
        (release / DERIVED_FILENAMES["observations_jsonl"]).read_bytes(),
        "observations",
    )
    if [item.get("observation_id") for item in observations] != list(
        OBSERVATION_ORDER
    ):
        raise NewZealandFastTrackError("observation count or order changed")
    for item in observations:
        metrics = item.get("facility_metrics", {})
        if (
            item.get("review_only") is not True
            or item.get("automatic_merge") is not False
            or item.get("accepted_relationship") is not False
            or item.get("unique_site_counted") is not False
            or item.get("physical_status") != _physical_status()
            or item.get("promotion_boundaries") != REVIEW_POLICY
            or metrics.get("annual_energy_observations") != []
            or metrics.get("capacity_observations") != []
            or metrics.get("power_observations") != []
            or metrics.get("pue_observations") != []
        ):
            raise NewZealandFastTrackError(
                "observation promotion boundary changed"
            )
    assessment = _load_json(
        release / DERIVED_FILENAMES["assessment"], "assessment"
    )
    if (
        assessment.get("rights_assessment", {}).get(
            "rights_gate_passed_for_retained_scope"
        )
        is not True
        or assessment.get("coverage", {}).get("coverage_complete") is not False
        or assessment.get("coverage", {}).get("unique_physical_site_count")
        is not None
    ):
        raise NewZealandFastTrackError("rights or coverage boundary changed")
    return {
        "assessment": assessment,
        "definition": definition,
        "inventory": _load_json(
            release / DERIVED_FILENAMES["inventory"], "inventory"
        ),
        "manifest": manifest,
        "observations": observations,
        "relationships": _load_json(
            release / DERIVED_FILENAMES["relationships"], "relationships"
        ),
    }


def is_frozen_release(path: str | Path) -> bool:
    release = Path(path)
    return (
        release.stat().st_mode & 0o777 == 0o555
        and all(
            item.stat().st_mode & 0o777
            == (0o555 if item.is_dir() else 0o444)
            for item in release.rglob("*")
        )
    )


def thaw_for_test(path: str | Path) -> None:
    release = Path(path)
    release.chmod(stat.S_IRWXU)
    for item in release.rglob("*"):
        item.chmod(
            stat.S_IRWXU
            if item.is_dir()
            else stat.S_IRUSR | stat.S_IWUSR
        )


__all__ = [
    "ARTIFACT_ORDER",
    "BROWSER_ARTIFACTS",
    "BROWSER_EXTRACT_CONTRACT",
    "CURRENT_AUCKLAND_ID",
    "DATAGRID_ID",
    "DIRECT_ARTIFACTS",
    "MANIFEST_FILENAME",
    "MANIFEST_HASH_FILENAME",
    "OBSERVATION_ORDER",
    "PRIOR_AUCKLAND_ID",
    "PRIOR_RELATED",
    "PROJECT_CANDIDATE",
    "RAW_PATHS",
    "RELEASE_ID",
    "RELATIONSHIP_CONTRACT",
    "REVIEW_POLICY",
    "RIGHTS_POLICY",
    "NewZealandFastTrackError",
    "browser_extract_document",
    "canonical_json",
    "capture_live_sources",
    "definition_from_capture",
    "derive_release_files",
    "is_frozen_release",
    "load_definition",
    "sha256_bytes",
    "thaw_for_test",
    "validate_release_bundle",
    "write_release_bundle",
]
