"""Fail-closed assessment of the German states' UVP-Verbund portal.

The portal's own copyright notice requires prior author consent for use of its
data and information.  The first correctly parameterized search probe returned
HTTP 429.  This lane records access and rights metadata but contains no source
result rows.
"""

from __future__ import annotations

from collections.abc import Mapping
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
from urllib.parse import quote, urlsplit


SCHEMA_VERSION = 1
RELEASE_ID = "germany-uvp-verbund-data-centre-search-2026-07-18-v1"
RELEASE_FORMAT = "datacenter-atlas-germany-uvp-verbund-assessment-v1"
DEFINITION_FORMAT = "datacenter-atlas-germany-uvp-verbund-definition-v1"
INVENTORY_FORMAT = "datacenter-atlas-germany-uvp-verbund-retrieval-inventory-v1"
QUERY_PLAN_FORMAT = "datacenter-atlas-germany-uvp-verbund-query-plan-v1"
SCHEMA_FORMAT = "datacenter-atlas-germany-uvp-verbund-schema-v1"

PORTAL_BASE_URL = "https://www.uvp-verbund.de"
SEARCH_PATH = "/freitextsuche"
IMPRINT_URL = f"{PORTAL_BASE_URL}/impressum"
OPENSEARCH_DESCRIPTOR_URL = (
    f"{PORTAL_BASE_URL}/interface-opensearch/descriptor"
)
STATE_ALIAS_DESCRIPTOR_URL = (
    "https://uvp.niedersachsen.de/interface-opensearch/descriptor"
)
SEARCH_TERMS = ("Rechenzentrum", "Rechenzentren", "Datacenter", "Data Center")
MAX_NETWORK_REQUESTS = 8
MIN_REQUEST_INTERVAL_SECONDS = 1.0
MANIFEST_FILENAME = "manifest.json"
MANIFEST_HASH_FILENAME = "manifest.sha256"

PORTAL_REPOSITORY = "https://github.com/informationgrid/ingrid-portal-ng"
PORTAL_COMMIT = "085837f1d91748c90049ce78215842a69772c59b"
PLUGIN_REPOSITORY = "https://github.com/informationgrid/ingrid-grav-plugin"
PLUGIN_COMMIT = "2bf2d7f251c116285121aad1ef69d045745406aa"

EXPECTED_FILES = {
    "README.md",
    "assessment.json",
    "definition.json",
    MANIFEST_FILENAME,
    MANIFEST_HASH_FILENAME,
    "query-plan.json",
    "retrieval-inventory.json",
    "schema.json",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GermanyUVPVerbundError(ValueError):
    """Raised when the restricted assessment fails its pinned contract."""


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def search_url(term: str, *, page: int | None = None) -> str:
    if term not in SEARCH_TERMS:
        raise GermanyUVPVerbundError("search term is outside the closed query plan")
    url = f"{PORTAL_BASE_URL}{SEARCH_PATH}?q={quote(term, safe='')}"
    if page is not None:
        if page < 1:
            raise GermanyUVPVerbundError("page must be positive")
        url += f"&page={page}"
    return url


def source_definition() -> dict[str, Any]:
    return {
        "access": {
            "automation_probe_blocked": True,
            "block_http_status": 429,
            "closed_query_completed": False,
            "first_blocked_url": search_url("Rechenzentrum"),
            "published_numeric_rate_limit_found": False,
        },
        "coverage": {
            "complete_for_germany": False,
            "geography": "German state and municipal UVP procedures represented by UVP-Verbund",
            "result_count": None,
            "unique_physical_site_count": None,
        },
        "format": DEFINITION_FORMAT,
        "inference_policy": {
            "annual_energy_mwh": None,
            "atlas_facility_identity": None,
            "atlas_lifecycle_status": None,
            "automatic_promotion_permitted": False,
            "construction_evidence_rows": 0,
            "data_centre_type": None,
            "gross_facility_power_mw": None,
            "identity_merge_performed": False,
            "it_capacity_mw": None,
            "operation_evidence_rows": 0,
            "pue": None,
            "regulatory_status_is_physical_lifecycle": False,
            "review_only": True,
            "unique_physical_site_count": None,
        },
        "network_policy": {
            "backoff_seconds_by_retry": [2, 4],
            "maximum_attempts_per_url": 3,
            "maximum_network_requests_per_run": MAX_NETWORK_REQUESTS,
            "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
            "stop_after_access_block": True,
        },
        "publisher": "UVP-Verbund of the German federal states",
        "query": {
            "endpoint": f"{PORTAL_BASE_URL}{SEARCH_PATH}",
            "parameter": "q",
            "planned_terms": list(SEARCH_TERMS),
            "scope": "portal full-text search; the live client does not expose a title-only query",
            "sort": "portal default",
        },
        "release_id": RELEASE_ID,
        "retention": {
            "applicant_attachments_retained": False,
            "maps_or_tiles_retained": False,
            "personal_or_contact_fields_retained": False,
            "public_submissions_retained": False,
            "raw_http_response_bodies_retained": False,
            "source_result_rows_retained": False,
            "third_party_documents_retained": False,
        },
        "rights": {
            "commercial_reuse_permission_clear": False,
            "derivative_record_publication_permitted": False,
            "imprint_url": IMPRINT_URL,
            "legal_conclusion_claimed": False,
            "master_or_ledger_import_permitted": False,
            "prior_author_consent_required_by_portal_notice": True,
            "source_content_publication_permitted": False,
            "verified_local_date": "2026-07-18",
        },
        "schema_version": SCHEMA_VERSION,
        "source_id": "germany-uvp-verbund-data-centre-search",
        "source_urls": {
            "imprint": IMPRINT_URL,
            "opensearch_descriptor": OPENSEARCH_DESCRIPTOR_URL,
            "portal": f"{PORTAL_BASE_URL}/portal/",
            "search": f"{PORTAL_BASE_URL}{SEARCH_PATH}",
        },
        "title": "Restricted UVP-Verbund data-centre search assessment",
    }


PINNED_RETRIEVAL_INVENTORY: dict[str, Any] = {
    "assessment_local_date": "2026-07-18",
    "capture_completed_at": "2026-07-19T01:37:26Z",
    "controlled_http_requests": [
        {
            "body_retained": False,
            "bytes": 162,
            "content_type": "text/html",
            "http_status": 429,
            "method": "GET",
            "request_id": "closed_query_probe_rechenzentrum",
            "response_date": "2026-07-19T01:35:02Z",
            "sha256": "413d294fad14524bf94e764b33ff0f327682549408545171fcf9240189c154ae",
            "url": search_url("Rechenzentrum"),
        },
        {
            "body_retained": False,
            "bytes": 162,
            "content_type": "text/html",
            "http_status": 429,
            "method": "GET",
            "request_id": "opensearch_descriptor_probe",
            "response_date": "2026-07-19T01:37:11Z",
            "sha256": "413d294fad14524bf94e764b33ff0f327682549408545171fcf9240189c154ae",
            "url": OPENSEARCH_DESCRIPTOR_URL,
        },
        {
            "body_retained": False,
            "bytes": 138,
            "content_type": "text/html",
            "http_status": 302,
            "location": OPENSEARCH_DESCRIPTOR_URL,
            "method": "GET",
            "request_id": "niedersachsen_alias_descriptor_probe",
            "response_date": "2026-07-19T01:37:26Z",
            "sha256": "753e0dd54f28c4f7009b9c0b18a68aed175416bd8b7d134858264586eaac56f0",
            "url": STATE_ALIAS_DESCRIPTOR_URL,
        },
    ],
    "format": INVENTORY_FORMAT,
    "live_contract_evidence": {
        "body_retained": False,
        "bytes": 220679,
        "content_type": "text/html;charset=UTF-8",
        "http_status": 200,
        "purpose": "transient inspection of the rendered live search form",
        "response_date": "2026-07-19T01:34:34Z",
        "sha256": "13c7ae21000f25b014ff383a530188415a8c04d96d7ea2ecab9425a4e343884e",
        "url": f"{PORTAL_BASE_URL}{SEARCH_PATH}?query=Rechenzentrum",
    },
    "maximum_network_requests": MAX_NETWORK_REQUESTS,
    "minimum_request_interval_seconds": MIN_REQUEST_INTERVAL_SECONDS,
    "network_requests": 3,
    "pre_capture_note": {
        "count": 1,
        "description": (
            "One exploratory q=Rechenzentrum request returned 429 before the "
            "controlled inventory began; its response metadata was not retained."
        ),
        "included_in_network_requests": False,
    },
    "raw_response_bodies_retained": False,
    "release_id": RELEASE_ID,
    "software_contract_files": [
        {
            "bytes": 2722,
            "commit": PORTAL_COMMIT,
            "path": "user/themes/uvp/pages/init/imprint/cms.md",
            "repository": PORTAL_REPOSITORY,
            "role": "copyright and prior-consent notice",
            "sha256": "c42d29ca93866d75b134645246a3ecd55edacf410a5bc5d12a7e751ff2d349f0",
        },
        {
            "bytes": 12174,
            "commit": PORTAL_COMMIT,
            "path": "user/themes/uvp/uvp.yaml",
            "repository": PORTAL_REPOSITORY,
            "role": "UVP search fields, page size, and copyright footer config",
            "sha256": "840044525b20ef1cd58c9162e253753d6a42943e8729320b87c48c7358574943",
        },
        {
            "bytes": 2674,
            "commit": PLUGIN_COMMIT,
            "path": "templates/modular/home-search.html.twig",
            "repository": PLUGIN_REPOSITORY,
            "role": "GET form and q parameter contract",
            "sha256": "cf7f12592cb24d3f7d2edb5ca197c5d7917292bfbf950da2403eccbeba35447d",
        },
        {
            "bytes": 26609,
            "commit": PLUGIN_COMMIT,
            "path": "classes/controller/SearchController.php",
            "repository": PLUGIN_REPOSITORY,
            "role": "server-side q and page parameter handling",
            "sha256": "f4e0f1193093858a42ca4a5d78cf02671016a70dab345afbd8ab285e95101f10",
        },
        {
            "bytes": 380,
            "commit": PLUGIN_COMMIT,
            "path": "pages/search/modular.md",
            "repository": PLUGIN_REPOSITORY,
            "role": "freitextsuche route contract",
            "sha256": "d4102ff63a45560b7a81b5e45a5b8fb432fecff6d29600a9ae35073bc88af1c9",
        },
    ],
}


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GermanyUVPVerbundError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GermanyUVPVerbundError(f"{field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GermanyUVPVerbundError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _validate_https_url(value: Any, hosts: set[str], field: str) -> str:
    if not isinstance(value, str):
        raise GermanyUVPVerbundError(f"{field} must be a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in hosts:
        raise GermanyUVPVerbundError(f"{field} must use an allowed official host")
    return value


def validate_retrieval_inventory(inventory: Mapping[str, Any]) -> None:
    if dict(inventory) != PINNED_RETRIEVAL_INVENTORY:
        raise GermanyUVPVerbundError("retrieval inventory differs from the pinned capture")
    _timestamp(inventory.get("capture_completed_at"), "capture_completed_at")
    requests = inventory.get("controlled_http_requests")
    if not isinstance(requests, list) or len(requests) != 3:
        raise GermanyUVPVerbundError("controlled request inventory must contain three rows")
    if inventory.get("network_requests") != len(requests):
        raise GermanyUVPVerbundError("network request arithmetic differs")
    if inventory.get("maximum_network_requests") != MAX_NETWORK_REQUESTS:
        raise GermanyUVPVerbundError("network request cap differs")
    if inventory.get("minimum_request_interval_seconds") != 1.0:
        raise GermanyUVPVerbundError("minimum request interval differs")
    if inventory.get("raw_response_bodies_retained") is not False:
        raise GermanyUVPVerbundError("raw HTTP bodies must remain unretained")
    expected_statuses = [429, 429, 302]
    if [row.get("http_status") for row in requests] != expected_statuses:
        raise GermanyUVPVerbundError("controlled request statuses differ")
    allowed_hosts = {"www.uvp-verbund.de", "uvp.niedersachsen.de"}
    for index, row in enumerate(requests):
        _validate_https_url(row.get("url"), allowed_hosts, f"request[{index}].url")
        _timestamp(row.get("response_date"), f"request[{index}].response_date")
        if (
            row.get("method") != "GET"
            or row.get("body_retained") is not False
            or isinstance(row.get("bytes"), bool)
            or not isinstance(row.get("bytes"), int)
            or row["bytes"] <= 0
            or not isinstance(row.get("sha256"), str)
            or not _SHA256_RE.fullmatch(row["sha256"])
        ):
            raise GermanyUVPVerbundError("controlled response metadata is invalid")
    contract = inventory.get("live_contract_evidence")
    if not isinstance(contract, Mapping):
        raise GermanyUVPVerbundError("live contract evidence must be an object")
    _validate_https_url(
        contract.get("url"), {"www.uvp-verbund.de"}, "live_contract_evidence.url"
    )
    if (
        contract.get("http_status") != 200
        or contract.get("body_retained") is not False
        or contract.get("sha256")
        != "13c7ae21000f25b014ff383a530188415a8c04d96d7ea2ecab9425a4e343884e"
    ):
        raise GermanyUVPVerbundError("live form contract evidence differs")
    files = inventory.get("software_contract_files")
    if not isinstance(files, list) or len(files) != 5:
        raise GermanyUVPVerbundError("software contract inventory differs")
    for index, record in enumerate(files):
        if (
            record.get("repository")
            not in {PORTAL_REPOSITORY, PLUGIN_REPOSITORY}
            or record.get("commit") not in {PORTAL_COMMIT, PLUGIN_COMMIT}
            or not isinstance(record.get("path"), str)
            or not record["path"]
            or isinstance(record.get("bytes"), bool)
            or not isinstance(record.get("bytes"), int)
            or record["bytes"] <= 0
            or not isinstance(record.get("sha256"), str)
            or not _SHA256_RE.fullmatch(record["sha256"])
        ):
            raise GermanyUVPVerbundError(
                f"software contract record {index} is invalid"
            )


def query_plan() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for index, term in enumerate(SEARCH_TERMS):
        attempted = index == 0
        rows.append(
            {
                "classification_counts": {
                    "context": None,
                    "direct": None,
                    "excluded": None,
                },
                "closed_set_completed": False,
                "exact_url": search_url(term),
                "first_page_http_status": 429 if attempted else None,
                "pages_retrieved": 0,
                "result_count": None,
                "search_term": term,
                "status": (
                    "blocked_http_429"
                    if attempted
                    else "not_attempted_after_fail_closed_stop"
                ),
            }
        )
    return {
        "classification_contract": {
            "context": "the record refers to a data centre but the regulated project is ancillary or related infrastructure, including emergency generation",
            "direct": "the regulated project itself is a data-centre build or expansion",
            "excluded": "the full-text match has no data-centre project relevance",
        },
        "deduplication": "exact source record ID only",
        "format": QUERY_PLAN_FORMAT,
        "query_parameter": "q",
        "release_id": RELEASE_ID,
        "rows": rows,
        "scope": (
            "full-text portal search across title, summary, and content fields; "
            "the client contract exposes no title-only endpoint"
        ),
        "unique_physical_site_count": None,
    }


def assessment_document(inventory: Mapping[str, Any]) -> dict[str, Any]:
    validate_retrieval_inventory(inventory)
    return {
        "access_assessment": {
            "automation_block_observed": True,
            "bypass_attempted": False,
            "closed_query_completed": False,
            "descriptor_available_during_probe": False,
            "first_correct_search_probe_http_status": 429,
            "legacy_state_alias_behavior": "HTTP 302 redirect to UVP-Verbund descriptor",
            "portal_search_parameter": "q",
            "published_numeric_rate_limit_found": False,
            "result_pagination_contract_executed": False,
        },
        "assessment_id": RELEASE_ID,
        "assessed_at": inventory["capture_completed_at"],
        "atlas_decision": {
            "assessment_artifact_indexing_permitted": True,
            "automatic_promotion_permitted": False,
            "construction_master_import_permitted": False,
            "current_coverage_ledger_import_permitted": False,
            "publication_observation_rows": 0,
            "source_content_publication_permitted": False,
            "status": "rights_and_access_blocked_metadata_only",
        },
        "coverage_assessment": {
            "all_german_data_centres_claim_supported": False,
            "all_search_results_classified": False,
            "classification_counts": {
                "context": None,
                "direct": None,
                "excluded": None,
            },
            "closed_query_completed": False,
            "closed_set_sha256": None,
            "complete_for_germany": False,
            "query_variants_completed": 0,
            "query_variants_planned": 4,
            "result_count": None,
            "source_record_ids_deduplicated": False,
            "unique_physical_site_count": None,
        },
        "format": RELEASE_FORMAT,
        "inference_policy": source_definition()["inference_policy"],
        "query_assessment": query_plan(),
        "release_id": RELEASE_ID,
        "retention_assessment": source_definition()["retention"],
        "retrieval_batch": {
            "controlled_network_requests": inventory["network_requests"],
            "maximum_network_requests": inventory["maximum_network_requests"],
            "minimum_request_interval_seconds": inventory[
                "minimum_request_interval_seconds"
            ],
            "raw_inventory_sha256": sha256_bytes(canonical_json(inventory)),
            "raw_response_bodies_retained": False,
        },
        "rights_assessment": source_definition()["rights"]
        | {
            "portal_notice_scope": "individual portal data and information",
            "reuse_decision": "prior author consent required",
        },
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": "UVP-Verbund",
            "operator": "Landesbetrieb Geoinformation und Vermessung",
            "portal_url": f"{PORTAL_BASE_URL}/portal/",
            "represented_jurisdictions": 16,
            "search_url": f"{PORTAL_BASE_URL}{SEARCH_PATH}",
        },
    }


def schema_document() -> dict[str, Any]:
    return {
        "classification_rows": [],
        "facility_lead_count": 0,
        "format": SCHEMA_FORMAT,
        "lifecycle_contract": {
            "construction_evidence_rows": 0,
            "operation_evidence_rows": 0,
            "regulatory_status_is_physical_lifecycle": False,
        },
        "metric_contract": {
            "annual_energy_mwh": None,
            "gross_facility_power_mw": None,
            "it_capacity_mw": None,
            "numeric_statements_retained": 0,
            "pue": None,
        },
        "publication_contract": {
            "automatic_promotion_permitted": False,
            "master_or_ledger_import_permitted": False,
            "source_rows_publication_permitted": False,
        },
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
        "unique_physical_site_count": None,
    }


def readme_bytes() -> bytes:
    return f"""# Germany UVP-Verbund restricted source assessment

UVP-Verbund's live client uses `GET {SEARCH_PATH}` with the search text in the `q` parameter. The client searches title, summary, and content fields. It does not expose a title-only contract.

The planned closed query contains four terms: `Rechenzentrum`, `Rechenzentren`, `Datacenter`, and `Data Center`. The first correctly parameterized request, `{search_url("Rechenzentrum")}`, returned HTTP 429. The controlled probe stopped before pagination or the remaining terms. The result count and direct, context, and excluded counts remain null.

The portal imprint says that the individual data and information require prior author consent before use. This release contains access and rights metadata. It contains no result rows, applicant material, attachments, submissions, personal fields, images, maps, or HTTP response bodies. It cannot feed the construction master, map, or current-coverage ledger.

UVP process states do not establish physical construction or operation. This assessment publishes no facility identity, lifecycle status, data-centre type, power metric, PUE, or annual-energy value. The unique physical site count remains null.

The frozen bundle uses directory mode `0555` and file mode `0444`. Validate it without network access:

```bash
python3 scripts/validate_germany_uvp_verbund.py
```

The fetch/build command uses an eight-request cap, one-second minimum pacing, bounded retries, and a fail-closed stop on HTTP 429:

```bash
python3 scripts/fetch_build_germany_uvp_verbund.py --capture-only
```
""".encode("utf-8")


def derive_release_files(inventory: Mapping[str, Any]) -> dict[str, bytes]:
    validate_retrieval_inventory(inventory)
    return {
        "README.md": readme_bytes(),
        "assessment.json": canonical_json(assessment_document(inventory)),
        "definition.json": canonical_json(source_definition()),
        "query-plan.json": canonical_json(query_plan()),
        "retrieval-inventory.json": canonical_json(inventory),
        "schema.json": canonical_json(schema_document()),
    }


def _manifest(files: Mapping[str, bytes]) -> dict[str, Any]:
    return {
        "file_count": len(files),
        "files": {
            name: {"bytes": len(body), "sha256": sha256_bytes(body)}
            for name, body in sorted(files.items())
        },
        "format": "datacenter-atlas-manifest-v1",
        "release_id": RELEASE_ID,
        "schema_version": SCHEMA_VERSION,
    }


def _freeze_tree(root: Path) -> None:
    for entry in sorted(root.rglob("*"), reverse=True):
        entry.chmod(0o555 if entry.is_dir() else 0o444)
    root.chmod(0o555)


def thaw_for_test(root: Path) -> None:
    root.chmod(0o755)
    for entry in root.rglob("*"):
        entry.chmod(0o755 if entry.is_dir() else 0o644)


def write_release_bundle(inventory: Mapping[str, Any], output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise GermanyUVPVerbundError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", dir=str(output.parent))
    )
    try:
        files = derive_release_files(inventory)
        for name, body in files.items():
            (temporary / name).write_bytes(body)
        manifest_body = canonical_json(_manifest(files))
        (temporary / MANIFEST_FILENAME).write_bytes(manifest_body)
        (temporary / MANIFEST_HASH_FILENAME).write_text(
            f"{sha256_bytes(manifest_body)}  {MANIFEST_FILENAME}\n",
            encoding="utf-8",
        )
        _freeze_tree(temporary)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            thaw_for_test(temporary)
            shutil.rmtree(temporary)
        raise


def _load_canonical_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GermanyUVPVerbundError(f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GermanyUVPVerbundError(f"invalid {label}") from error
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise GermanyUVPVerbundError(f"{label} must contain canonical JSON")
    return value


def is_frozen_release(root: Path) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        return False
    return all(
        stat.S_IMODE(entry.stat().st_mode) == (0o555 if entry.is_dir() else 0o444)
        for entry in root.rglob("*")
    )


def validate_release_bundle(root: Path) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise GermanyUVPVerbundError("release must be a regular directory")
    entries = {str(entry.relative_to(root)) for entry in root.rglob("*")}
    if entries != EXPECTED_FILES:
        raise GermanyUVPVerbundError("release file set differs")
    if any(entry.is_symlink() for entry in root.rglob("*")):
        raise GermanyUVPVerbundError("release cannot contain symlinks")
    if not is_frozen_release(root):
        raise GermanyUVPVerbundError("release modes are not frozen")

    inventory = _load_canonical_json(
        root / "retrieval-inventory.json", "retrieval inventory"
    )
    validate_retrieval_inventory(inventory)
    derived = derive_release_files(inventory)
    for name, expected in derived.items():
        if (root / name).read_bytes() != expected:
            raise GermanyUVPVerbundError(f"derived file differs: {name}")

    manifest = _load_canonical_json(root / MANIFEST_FILENAME, "manifest")
    if manifest != _manifest(derived):
        raise GermanyUVPVerbundError("manifest inventory differs")
    expected_sidecar = (
        f"{sha256_bytes((root / MANIFEST_FILENAME).read_bytes())}  "
        f"{MANIFEST_FILENAME}\n"
    )
    if (root / MANIFEST_HASH_FILENAME).read_text(encoding="utf-8") != expected_sidecar:
        raise GermanyUVPVerbundError("manifest sidecar differs")

    assessment = _load_canonical_json(root / "assessment.json", "assessment")
    schema = _load_canonical_json(root / "schema.json", "schema")
    if assessment["atlas_decision"]["status"] != "rights_and_access_blocked_metadata_only":
        raise GermanyUVPVerbundError("assessment decision differs")
    if assessment["coverage_assessment"]["result_count"] is not None:
        raise GermanyUVPVerbundError("blocked assessment cannot publish a result count")
    if assessment["coverage_assessment"]["unique_physical_site_count"] is not None:
        raise GermanyUVPVerbundError("unique site count must remain null")
    if schema["facility_lead_count"] != 0 or schema["classification_rows"] != []:
        raise GermanyUVPVerbundError("restricted assessment cannot emit source rows")
    return {
        "assessment": assessment,
        "definition": _load_canonical_json(root / "definition.json", "definition"),
        "inventory": inventory,
        "manifest": manifest,
        "query_plan": _load_canonical_json(root / "query-plan.json", "query plan"),
        "schema": schema,
    }
