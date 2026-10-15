"""Deterministic, date-based updates to the Atlas's published tables.

Existing observations retain their dates. New admissions need a recent primary
observation and an explicitly scoped locator. Inputs contain compact factual
projections, not copies of third-party pages. Earlier datasets are never edited.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from .models import LifecycleStatus
from .public_site import validate_dataset


class UpdateError(ValueError):
    """An update cannot be applied without losing its evidence or identity."""


ACTIVE_STATUSES = {
    "site_preparation", "clearing", "civil_works", "foundations", "shell",
    "mep_electrical", "commissioning", "under_construction", "expansion",
}
# Keep this original schema set when reproducing updates that predate lifecycle expansion.
LEGACY_STATUS_VALUES = ACTIVE_STATUSES | {"operational", "paused", "cancelled", "repurposed", "decommissioned", "demolished"}
PLANNED_STATUSES = {LifecycleStatus.ANNOUNCED.value, LifecycleStatus.PERMITTED.value}
STATUS_VALUES = LEGACY_STATUS_VALUES | PLANNED_STATUSES | {LifecycleStatus.COMPLETED.value}
ADMISSION_STATUSES = ACTIVE_STATUSES | PLANNED_STATUSES | {LifecycleStatus.COMPLETED.value, LifecycleStatus.OPERATIONAL.value}
PROJECT_RECORD_POSTURE = "authoritative_project_record_plus_scoped_location"
ROOT = Path(__file__).resolve().parents[1]


def _require(condition, message):
    if not condition:
        raise UpdateError(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _date(value):
    _require(isinstance(value, str), "date must be an ISO date string")
    result = date.fromisoformat(value)
    _require(result.isoformat() == value, "date must be YYYY-MM-DD")
    return result


def _text(value, label):
    _require(isinstance(value, str) and bool(value.strip()), f"missing {label}")
    return value


def _path(root, value):
    path = root / value
    _require(not Path(value).is_absolute() and ".." not in Path(value).parts, "unsafe input path")
    _require(path.resolve().is_relative_to(root.resolve()), "input escapes repository")
    return path


def _csv_bytes(rows, fields):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def _source(row, updated):
    for field in ("id", "kind", "title", "source_url", "publisher", "source_family", "license", "attribution", "summary"):
        _text(row.get(field), f"source {field}")
    url = urlsplit(row["source_url"])
    _require(url.scheme in {"http", "https"} and url.hostname and not url.username, "source URL must be public HTTP(S)")
    published = row.get("published_at")
    if published:
        _require(_date(published) <= updated, "source publication is after update date")
    retrieved = datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
    _require(retrieved.tzinfo is not None and retrieved.date() <= updated, "invalid source retrieval date")
    if published:
        _require(_date(published) <= retrieved.date(), "source capture predates publication")
    digest = row.get("content_hash", "")
    _require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), "source needs a SHA-256 content hash")
    return {
        "evidence_id": str(uuid5(NAMESPACE_URL, f"{row['source_url']}#{digest}")),
        **{key: row.get(key, "") for key in (
            "kind", "title", "source_url", "publisher", "source_family", "license",
            "attribution", "published_at", "retrieved_at", "content_hash",
        )},
        "roles_json": "[]", "project_ids_json": "[]",
    }


def _status(spec, sources, updated, *, admission=False, source_details=None):
    observed = _date(spec["as_of"])
    _require(spec["value"] in STATUS_VALUES, "unrecognized project status")
    _require(observed <= updated, "future status observation")
    if admission:
        _require(spec["value"] in ADMISSION_STATUSES,
                 "new admission needs an announced, permitted, construction, completed or operational project")
        _require((updated - observed).days <= 90, "new admission observation is older than 90 days")
    source = sources[spec["source_id"]]
    if source.get("published_at"):
        _require(observed <= _date(source["published_at"]), "observation postdates its source")
    else:
        # A dated construction photograph can establish its observation day even
        # when the containing web page has no publication date. Keep that date
        # distinct from publication and retrieval rather than fabricating either.
        details = (source_details or {}).get(spec["source_id"], {})
        _require(details.get("source_observation_date") and
                 details.get("source_observation_date_precision") == "day" and
                 spec["value"] in ACTIVE_STATUSES,
                 "status observation needs a dated source")
        _text(details.get("date_semantics"), "source observation date semantics")
        _require(_date(details["source_observation_date"]) == observed,
                 "status must match the explicit source observation date")
        retrieved_day = datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00")).date()
        _require(observed <= retrieved_day, "source capture predates observation")
    if source["kind"] == "news":
        # A named project participant's firsthand statement can be primary
        # evidence inside a report. Ordinary reporting and syndicated summaries
        # do not qualify, and the source remains labelled as news.
        details = (source_details or {}).get(spec["source_id"], {})
        firsthand = details.get("firsthand_status_statement", {})
        _require(firsthand.get("basis") == "attributed_project_participant_statement"
                 and source.get("published_at")
                 and spec["value"] in ACTIVE_STATUSES | {"completed", "operational"},
                 "status observation needs a primary source or reviewed firsthand physical-status statement")
        for field in ("speaker", "speaker_role", "project_identity", "statement", "date_semantics", "review"):
            _text(firsthand.get(field), f"firsthand status {field}")
        _require(firsthand.get("observed_on") == spec["as_of"]
                 and firsthand.get("supported_status") == spec["value"],
                 "firsthand statement must support the selected status and observation date")
    else:
        _require(source["kind"] in {"company_disclosure", "government_record", "regulatory_filing"}, "status observation needs a primary source")
    _text(spec.get("summary"), "project status summary")
    if spec["value"] == LifecycleStatus.PERMITTED.value:
        _require(spec.get("permit_scope") == "data_center_development", "permit must cover data-center development, not ancillary infrastructure")
        _require(spec.get("permit_type") in {"planning_permission", "building_permit", "construction_permit"}, "permit must authorize the planned development or building works")
        _require(spec.get("permit_decision") == "granted", "permitted status needs a granted decision")
        _text(spec.get("permit_reference"), "permit reference")
        _text(spec.get("permit_identity_review"), "permit identity review")
    return source


def _status_metadata(value):
    if value == LifecycleStatus.ANNOUNCED.value:
        return "authoritative_project_announcement", "announcement"
    if value == LifecycleStatus.PERMITTED.value:
        return "authoritative_construction_permit", "permit"
    return "authoritative_physical_status_update", "physical_status"


def _site_from_project(project, name):
    shared = (
        "site_id", "physical_site_stable_key", "country", "country_iso_a2", "latitude", "longitude",
        "geometry_json", "geometry_type", "horizontal_uncertainty_metres", "horizontal_uncertainty_unknown_reason",
        "verification_posture", "independent_imagery_verification",
    )
    site = {key: project[key] for key in shared}
    site.update(name=name, project_count="1", oldest_status_as_of=project["status_as_of"], newest_status_as_of=project["status_as_of"])
    lists = {
        "geometry_source_entity_kinds": "geometry_source_entity_kind", "geometry_derivations": "geometry_derivation",
        "geometry_methods": "geometry_method", "geometry_scope_classes": "geometry_scope_class",
        "geometry_authority_classes": "geometry_authority_class", "geometry_use_scopes": "geometry_use_scope",
        "geometry_precision_scopes": "geometry_precision_scope", "geometry_evidence_ids": "geometry_evidence_id",
        "project_ids": "project_id", "project_stable_keys": "project_stable_key",
        "statuses": "last_observed_physical_status", "imagery_review_outcomes": "imagery_review_outcome",
    }
    site.update({key + "_json": _json([project[field]]) for key, field in lists.items()})
    return site

def _inherited_campus_locator(locator, site, baseline_projects, baseline_evidence):
    """Reuse a pinned baseline locator, without reinterpreting its legacy sources."""
    allowed = {"reuse_from_project_id", "geometry_evidence_id", "geometry_identity_evidence_ids",
               "scope", "identity_review"}
    _require(set(locator) <= allowed, "inherited campus locator does not permit geometry or provenance overrides")
    _require(site is not None, "locator inheritance requires an existing baseline site")
    reference_id = _text(locator.get("reuse_from_project_id"), "baseline locator project reference")
    reference = baseline_projects.get(reference_id)
    _require(reference is not None, "locator reference must name a baseline project")
    _require(reference["site_id"] == site["site_id"]
             and reference["physical_site_stable_key"] == site["physical_site_stable_key"],
             "locator reference must belong to the same baseline site")
    _require(locator.get("scope") == reference["geometry_use_scope"] == "campus_locator",
             "locator inheritance requires campus scope")
    _text(locator.get("identity_review"), "locator identity review")
    _require(reference["geometry_type"] in {"Point", "Polygon"}
             and json.loads(reference["geometry_json"])["type"] == reference["geometry_type"],
             "only baseline Point or Polygon campus locators can be inherited")
    scalar_fields = ("latitude", "longitude", "geometry_json", "geometry_type",
                     "horizontal_uncertainty_metres", "horizontal_uncertainty_unknown_reason")
    _require(all(reference[field] == site[field] for field in scalar_fields),
             "baseline project and site locator geometry, coordinates and uncertainty must agree exactly")
    provenance_fields = {
        "geometry_source_entity_kinds": "geometry_source_entity_kind", "geometry_derivations": "geometry_derivation",
        "geometry_methods": "geometry_method", "geometry_scope_classes": "geometry_scope_class",
        "geometry_authority_classes": "geometry_authority_class", "geometry_use_scopes": "geometry_use_scope",
        "geometry_precision_scopes": "geometry_precision_scope", "geometry_evidence_ids": "geometry_evidence_id",
    }
    _require(all(json.loads(site[field + "_json"]) == [reference[target]]
                 for field, target in provenance_fields.items()),
             "baseline project and site locator provenance and precision must agree exactly")
    geometry_id = _text(locator.get("geometry_evidence_id"), "inherited geometry evidence ID")
    _require(geometry_id == reference["geometry_evidence_id"], "inherited geometry evidence ID must match the baseline project")
    identity_ids = locator.get("geometry_identity_evidence_ids")
    _require(isinstance(identity_ids, list) and all(isinstance(value, str) and value for value in identity_ids)
             and len(identity_ids) == len(set(identity_ids)), "inherited geometry identity evidence IDs must be an explicit unique list")
    for evidence_id, role in [(geometry_id, "geometry")] + [(value, "context:geometry_identity") for value in identity_ids]:
        evidence = baseline_evidence.get(evidence_id)
        _require(evidence is not None, "inherited locator evidence must exist in the baseline")
        _require(reference_id in json.loads(evidence["project_ids_json"])
                 and role in json.loads(evidence["roles_json"]),
                 "inherited locator evidence must have its baseline project association and geometry role")
    _require(baseline_evidence[geometry_id]["source_url"] == reference["geometry_source_url"],
             "inherited geometry source URL must match the baseline evidence")
    expected_identity_ids = {evidence_id for evidence_id, evidence in baseline_evidence.items()
                             if reference_id in json.loads(evidence["project_ids_json"])
                             and "context:geometry_identity" in json.loads(evidence["roles_json"])}
    _require(set(identity_ids) == expected_identity_ids,
             "inherited locator must pin all baseline geometry identity evidence")
    fields = scalar_fields + tuple(provenance_fields.values()) + ("geometry_source_url",)
    return {field: reference[field] for field in fields}, [geometry_id, *identity_ids]



def _feature(site):
    properties = {key: site[key] for key in (
        "site_id", "physical_site_stable_key", "name", "country", "geometry_type",
        "newest_status_as_of", "verification_posture",
    )}
    for key in ("geometry_authority_classes", "geometry_precision_scopes", "geometry_scope_classes", "geometry_use_scopes", "statuses"):
        properties[key] = json.loads(site[key + "_json"])
    properties.update(project_count=int(site["project_count"]), independent_imagery_verification=site["independent_imagery_verification"] == "true",
                      horizontal_uncertainty_metres=float(site["horizontal_uncertainty_metres"]) if site["horizontal_uncertainty_metres"] else None)
    return {"type": "Feature", "id": site["site_id"], "geometry": json.loads(site["geometry_json"]), "properties": properties}


def update_payloads(input_path: Path, *, root: Path = ROOT):
    """Validate the update and return all output bytes, without writing anything."""
    input_bytes = input_path.read_bytes()
    spec = json.loads(input_bytes)
    _require(spec["format"] == "datacenter-atlas-update-input-v1", "unsupported update format")
    actions = [item["project_stable_key"] for group in ("additions", "status_updates", "status_corrections", "context_updates", "withdrawals") for item in spec.get(group, [])]
    _require(len(actions) == len(set(actions)), "a project may occur in only one action per update")
    updated = _date(spec["updated_at"])
    base_path = _path(root, spec["base_dataset"])
    base, base_sha, _ = validate_dataset(base_path)
    _require(base_sha == spec["base_manifest_sha256"], "base manifest hash differs")
    sources, source_details, source_files = {}, {}, []
    for item in spec["source_files"]:
        raw = _path(root, item["path"]).read_bytes()
        _require(_sha(raw) == item["sha256"], f"source file hash differs: {item['path']}")
        source_files.append(item)
        for record in json.loads(raw)["sources"]:
            _require(record["id"] not in sources, "duplicate source ID")
            sources[record["id"]] = _source(record, updated)
            source_details[record["id"]] = record
    schema = json.loads((base_path / "schema.json").read_bytes())
    tables = {name: list(csv.DictReader(io.StringIO((base_path / name).read_text()))) for name in ("sites.csv", "projects.csv", "evidence.csv")}
    sites, projects, evidence = (tables[name] for name in ("sites.csv", "projects.csv", "evidence.csv"))
    has_consolidation = "source-records.json" in base["files"]
    inherited_report = json.loads((base_path / "selection-report.json").read_bytes()) if has_consolidation else {}
    inherited_resolutions = copy.deepcopy(inherited_report.get("source_record_resolutions", []))
    evidence_fields = [field["name"] for field in schema["tables"]["evidence.csv"]["fields"]]
    by_key = {row["project_stable_key"]: row for row in projects}
    sites_by_key = {row["physical_site_stable_key"]: row for row in sites}
    base_site_keys = set(sites_by_key)
    # Later actions and source associations must never become inheritance inputs.
    baseline_projects = {row["project_id"]: copy.deepcopy(row) for row in projects}
    baseline_sites = copy.deepcopy(sites_by_key)
    baseline_evidence = {row["evidence_id"]: copy.deepcopy(row) for row in evidence}
    expanded_site_keys = set()
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    touched = set()
    canonical = {key: value for key, value in evidence_by_id.items()}
    for source in sources.values():
        previous = canonical.get(source["evidence_id"])
        if previous:
            _require(all((previous.get(key) or "") == (value or "") for key, value in source.items()
                         if key not in {"roles_json", "project_ids_json"}), "conflicting metadata for the same evidence capture")
        canonical[source["evidence_id"]] = source

    def associate(source_id, project_id, role):
        source = sources[source_id]
        identifier = source["evidence_id"]
        if identifier not in evidence_by_id:
            row = {name: "" for name in evidence_fields}
            row.update(copy.deepcopy(source))
            if "publication_date_precision" in evidence_fields:
                row["publication_date_precision"] = "day" if source.get("published_at") else "unknown"
            if "content_hash_scope" in evidence_fields:
                row["content_hash_scope"] = source_details[source_id].get("content_hash_scope") or "source_provided_digest"
            evidence_by_id[identifier] = row
            evidence.append(evidence_by_id[identifier])
        row = evidence_by_id[identifier]
        row["roles_json"] = _json(sorted(set(json.loads(row["roles_json"])) | {role}))
        row["project_ids_json"] = _json(sorted(set(json.loads(row["project_ids_json"])) | {project_id}))
        return identifier

    for item in spec.get("additions", []):
        key, site_key = item["project_stable_key"], item["physical_site_stable_key"]
        _require(key not in by_key, "duplicate project; use a status update for an existing project")
        existing_site = sites_by_key.get(site_key)
        if existing_site:
            _require(site_key in base_site_keys and item.get("existing_site_id") == existing_site["site_id"],
                     "existing physical site requires an explicit matching base site ID")
            _text(item.get("site_identity_review"), "existing site identity review")
            _require(all(item.get(field) == existing_site[target] for field, target in (
                ("site_name", "name"), ("country", "country"), ("country_iso_a2", "country_iso_a2"))),
                "existing site name and country must match")
        else:
            _require(not item.get("existing_site_id"), "existing site ID does not resolve to the physical site key")
        _text(item.get("distinctness_review"), "site distinctness review")
        _text(item.get("successor_review"), "later-status review")
        status, locator = item["status"], item["locator"]
        _status(status, sources, updated, admission=True, source_details=source_details)
        status_method, status_role = _status_metadata(status["value"])
        if sources[status["source_id"]]["kind"] == "news":
            status_method = "attributed_firsthand_physical_status_report"
        inherited_evidence_ids = []
        if "reuse_from_project_id" in locator:
            geometry_fields, inherited_evidence_ids = _inherited_campus_locator(
                locator, baseline_sites.get(site_key), baseline_projects, baseline_evidence)
        else:
            _require("geometry" in locator, "locator needs point geometry or an explicit baseline project reference")
            geometry = locator["geometry"]
            _require(geometry["type"] == "Point", "new point admissions only; complex boundary changes require a separate geometry review")
            coords = geometry["coordinates"]
            _require(isinstance(coords, list) and len(coords) == 2 and all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in coords), "invalid point coordinates")
            lon, lat = coords
            _require(-180 <= lon <= 180 and -90 <= lat <= 90, "point outside coordinate range")
            _require(locator["scope"] in {"project_locator", "reviewed_site_locator", "campus_locator"}, "new locator must locate the project or campus")
            for field in ("method", "precision", "identity_review"):
                _text(locator.get(field), f"locator {field}")
            derivation = locator.get("derivation", "direct_geometry")
            _require(derivation in {"direct_geometry", "georeferenced_source_map", "coordinate_transform"}, "unsupported locator derivation")
            if derivation != "direct_geometry":
                _require(locator["authority"] == "compiled_reference", "derived locator must be a compiled reference")
            uncertainty = locator.get("horizontal_uncertainty_metres")
            if uncertainty is None:
                _text(locator.get("uncertainty_reason"), "locator uncertainty reason")
            else:
                _require(isinstance(uncertainty, (int, float)) and not isinstance(uncertainty, bool) and math.isfinite(uncertainty) and uncertainty >= 0, "invalid horizontal uncertainty")
            if existing_site:
                _require(locator["scope"] == "campus_locator" and geometry == json.loads(existing_site["geometry_json"]),
                         "existing site addition must reuse its reviewed campus point")
                _require((str(uncertainty) if uncertainty is not None else "") == existing_site["horizontal_uncertainty_metres"]
                         and locator.get("uncertainty_reason", "") == existing_site["horizontal_uncertainty_unknown_reason"],
                         "existing campus locator uncertainty must be preserved")
            geometry_fields = dict(
                latitude=str(lat), longitude=str(lon), geometry_json=_json(geometry), geometry_type="Point",
                geometry_source_entity_kind="campus", geometry_derivation=derivation, geometry_method=locator["method"],
                geometry_scope_class=locator["scope_class"], geometry_authority_class=locator["authority"], geometry_use_scope=locator["scope"],
                geometry_precision_scope=locator["precision"], horizontal_uncertainty_metres=str(uncertainty) if uncertainty is not None else "",
                horizontal_uncertainty_unknown_reason=locator.get("uncertainty_reason", ""),
                geometry_source_url=sources[locator["source_id"]]["source_url"],
            )
        iso = item["country_iso_a2"]
        _require(len(iso) == 2 and iso.isascii() and iso.isupper(), "invalid ISO country code")
        pid = str(uuid5(NAMESPACE_URL, key))
        sid = existing_site["site_id"] if existing_site else "vcc-site-" + _sha(site_key.encode())[:20]
        if inherited_evidence_ids:
            for evidence_id in inherited_evidence_ids:
                evidence_row = evidence_by_id[evidence_id]
                evidence_row["project_ids_json"] = _json(sorted(set(json.loads(evidence_row["project_ids_json"])) | {pid}))
        else:
            geometry_fields["geometry_evidence_id"] = associate(locator["source_id"], pid, "geometry")
        row = {field["name"]: "[]" if field["logical_type"] == "json_array" else "" for field in schema["tables"]["projects.csv"]["fields"]}
        row.update(
            project_id=pid, project_stable_key=key, site_id=sid, physical_site_stable_key=site_key,
            name=_text(item["name"], "project name"), country=_text(item["country"], "country"), country_iso_a2=iso,
            last_observed_physical_status=status["value"], status_as_of=status["as_of"], status_method=status_method,
            status_evidence_id=associate(status["source_id"], pid, status_role),
            verification_posture=(PROJECT_RECORD_POSTURE if status["value"] in PLANNED_STATUSES else "authoritative_physical_observation_plus_reviewed_site_locator"),
            independent_imagery_verification="false", imagery_review_outcome="not_reviewed",
            development_type="unknown", development_type_unknown_reason="not established by selected evidence",
            operating_model="unknown", operating_model_unknown_reason="not established by selected evidence",
            workloads_json="[]", workload_unknown_reason="not established by selected evidence", role_claims_json="[]",
            power_observations_json="[]", power_unknown_reason="no typed power observation selected; not estimated",
            annual_energy_observations_json="[]", annual_energy_unknown_reason="no scoped annual-energy inputs; not estimated",
            efficiency_observations_json="[]", efficiency_unknown_reason="no scoped PUE or WUE observation",
            status_source_url=sources[status["source_id"]]["source_url"],
        )
        row.update(geometry_fields)
        if existing_site:
            locator_fields = (
                "geometry_source_entity_kind", "geometry_derivation", "geometry_method", "geometry_scope_class",
                "geometry_authority_class", "geometry_use_scope", "geometry_precision_scope",
                "geometry_evidence_id", "geometry_source_url",
            )
            _require(any(project["site_id"] == sid and all(project[field] == row[field] for field in locator_fields)
                         for project in projects),
                     "existing campus locator provenance and precision must be preserved")
        for source_id in item.get("context_source_ids", []):
            associate(source_id, pid, "context:identity")
        roles = []
        for role in item.get("roles", []):
            _require(role["role"] in {"owner", "operator", "user", "tenant", "customer"}, "unknown party role")
            roles.append({"party": _text(role["party"], "party"), "role": role["role"], "relationship_scope": role["relationship_scope"], "evidence_id": associate(role["source_id"], pid, "role:" + role["role"])})
        row["role_claims_json"] = _json(roles)
        for role, column in (("owner", "owner"), ("operator", "operator"), ("user", "users"), ("tenant", "tenants"), ("customer", "customers")):
            row[column] = "; ".join(sorted({entry["party"] for entry in roles if entry["role"] == role}))
        projects.append(row)
        by_key[key] = row
        if existing_site:
            expanded_site_keys.add(site_key)
            projection = _site_from_project(row, item["site_name"])
            for field, value in projection.items():
                if field.endswith("_json") and field != "geometry_json":
                    existing_site[field] = _json(sorted(set(json.loads(existing_site[field])) | set(json.loads(value))))
        else:
            site = _site_from_project(row, item["site_name"])
            sites.append(site)
            sites_by_key[site_key] = site

    changes = [(item, False) for item in spec.get("status_updates", [])]
    changes += [(item, True) for item in spec.get("status_corrections", [])]
    for item, correction in changes:
        key = item["project_stable_key"]
        _require(key in by_key and key not in touched, "unknown or repeated project update")
        touched.add(key)
        row, status = by_key[key], item["status"]
        _status(status, sources, updated, source_details=source_details)
        status_method, status_role = _status_metadata(status["value"])
        if sources[status["source_id"]]["kind"] == "news":
            status_method = "attributed_firsthand_physical_status_report"
        if correction:
            _require(item.get("replaces_status_evidence_id") == row["status_evidence_id"], "correction must name the replaced status evidence")
            _text(item.get("reason"), "status correction reason")
        else:
            _require(_date(status["as_of"]) > _date(row["status_as_of"]), "status refresh must be newer than existing observation")
        _text(item.get("identity_review"), "status identity review")
        _text(item.get("successor_review"), "later-status review")
        row.update(last_observed_physical_status=status["value"], status_as_of=status["as_of"],
                   status_evidence_id=associate(status["source_id"], row["project_id"], status_role),
                   status_source_url=sources[status["source_id"]]["source_url"], status_method=status_method)
        if status["value"] in PLANNED_STATUSES:
            row["verification_posture"] = PROJECT_RECORD_POSTURE

    contextualized = []
    for item in spec.get("context_updates", []):
        key = item["project_stable_key"]
        _require(key in by_key, "unknown context project")
        row = by_key[key]
        _text(item.get("identity_review"), "context identity review")
        _text(item.get("summary"), "context summary")
        _require(item.get("preserve_status_as_of") == row["status_as_of"], "context update must preserve the existing observation date")
        _require(item.get("context_kind") in {"identity", "power_readiness"}, "unsupported context kind")
        source_ids = item.get("source_ids")
        _require(isinstance(source_ids, list) and source_ids and all(sid in sources for sid in source_ids), "context update needs reviewed sources")
        for source_id in source_ids:
            associate(source_id, row["project_id"], "context:" + item["context_kind"])
        contextualized.append(key)

    withdrawn = []
    for item in spec.get("withdrawals", []):
        key = item["project_stable_key"]
        _require(key in by_key and key not in touched, "unknown or repeated withdrawal")
        touched.add(key)
        row = by_key[key]
        _require(item.get("replaces_status_evidence_id") == row["status_evidence_id"], "withdrawal must name the removed status evidence")
        _text(item.get("reason"), "withdrawal reason")
        _require(item.get("source_ids") and all(sid in sources for sid in item["source_ids"]), "withdrawal needs reviewed sources")
        _require(sum(project["site_id"] == row["site_id"] for project in projects) == 1, "multi-project campus withdrawals require a separate review")
        projects.remove(row)
        sites[:] = [site for site in sites if site["site_id"] != row["site_id"]]
        for source in evidence:
            source["project_ids_json"] = _json([pid for pid in json.loads(source["project_ids_json"]) if pid != row["project_id"]])
        # Unmapped program and unresolved inventory sources deliberately have no
        # project association. Keep them, and keep withdrawn imported sources,
        # so their preserved source objects retain complete resolvable provenance.
        evidence[:] = [source for source in evidence if json.loads(source["project_ids_json"]) or source.get("source_record_id")]
        withdrawn.append(key)

    for row in projects:
        row["status_age_days_at_review"] = str((updated - _date(row["status_as_of"])).days)
        _require(int(row["status_age_days_at_review"]) >= 0, "base has observations after update date")
    for site in sites:
        members = [row for row in projects if row["site_id"] == site["site_id"]]
        if site["physical_site_stable_key"] in expanded_site_keys:
            site["project_count"] = str(len(members))
            site["independent_imagery_verification"] = str(all(row["independent_imagery_verification"] == "true" for row in members)).lower()
            postures = {row["verification_posture"] for row in members}
            site["verification_posture"] = next(iter(postures)) if len(postures) == 1 else "mixed_review_postures"
        site["oldest_status_as_of"] = min(row["status_as_of"] for row in members)
        site["newest_status_as_of"] = max(row["status_as_of"] for row in members)
        site["statuses_json"] = _json(sorted({row["last_observed_physical_status"] for row in members}))
        if any(row["verification_posture"] == PROJECT_RECORD_POSTURE for row in members):
            site["verification_posture"] = PROJECT_RECORD_POSTURE
        if has_consolidation:
            postures = {row["verification_posture"] for row in members}
            site["verification_posture"] = next(iter(postures)) if len(postures) == 1 else "mixed_review_postures"
    counts = {
        "physical_sites": len(sites), "projects": len(projects), "evidence": len(evidence),
        "countries": len({row["country_iso_a2"] for row in sites}), "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
        "host_estate_context_projects": sum(row["geometry_use_scope"] == "host_estate_context" for row in projects),
        "official_boundary_projects": sum(row["geometry_use_scope"] == "official_boundary" for row in projects),
    }
    if has_consolidation:
        remaining_projects = {row["project_id"]: row for row in projects}
        for resolution in inherited_resolutions:
            project_id = resolution.get("project_id")
            if project_id and project_id not in remaining_projects:
                resolution.update(previous_project_id=project_id, previous_site_id=resolution.get("site_id"),
                                  project_id=None, site_id=None,
                                  resolution_note="Project withdrawn from the published site inventory; its original source record remains preserved.")
            resolution["related_project_ids"] = [pid for pid in resolution.get("related_project_ids", []) if pid in remaining_projects]
            resolution["related_site_ids"] = sorted({remaining_projects[pid]["site_id"] for pid in resolution["related_project_ids"]})
        counts.update(imported_source_records=len(inherited_resolutions),
                      snapshot_only_records=sum(not item.get("project_id") for item in inherited_resolutions),
                      imported_source_references=sum(bool(row.get("source_record_id")) for row in evidence))
    schema = {key: value for key, value in schema.items() if key not in {"draft_id", "base_preview_id", "v018_draft_contract", "inherited_baseline_annotations"}}
    for name, table in schema["tables"].items():
        for field in table["fields"]:
            if "allowed_values" in field and field["logical_type"] == "string":
                values = {row[field["name"]] for row in tables[name] if row[field["name"]] != ""}
                field["allowed_values"] = sorted(set(field["allowed_values"]) | values)
                field["allowed_values_scope"] = "Published observations and retained historical codes."
            if field["name"] == "last_observed_physical_status":
                field["allowed_values"] = sorted(LEGACY_STATUS_VALUES | set(field["allowed_values"]))
    schema.update(format="datacenter-atlas-tables-v1", observation_policy="Each status has its own observation date. Dataset updates do not renew older observations.")
    report = {
        "updated_at": updated.isoformat(), "lifecycle_reference_date": updated.isoformat(), "counts": counts,
        "added_sites": [item["physical_site_stable_key"] for item in spec.get("additions", []) if item["physical_site_stable_key"] not in base_site_keys],
        "refreshed_projects": sorted(touched - set(withdrawn)), "withdrawn_projects": withdrawn,
        "withdrawal_note": _text(spec.get("withdrawal_note", "Unsupported construction selections are removed; no cancellation or other physical status is inferred."), "withdrawal note"),
        "base_dataset": spec["base_dataset"],
        "observation_policy": "Last documented observations; records are not a claim that all projects are still under construction on the update date.",
    }
    if expanded_site_keys:
        report["expanded_sites"] = sorted(expanded_site_keys)
        report["added_projects"] = [item["project_stable_key"] for item in spec.get("additions", [])]
    if contextualized:
        report["context_enriched_projects"] = sorted(contextualized)
    if has_consolidation:
        report.update(source_record_resolutions=inherited_resolutions,
                      consolidation_policy=inherited_report.get("consolidation_policy", ""),
                      decisions=inherited_report.get("decisions", {}))
    attribution = (base_path / "ATTRIBUTION.txt").read_text()
    attribution += "\nSources added in " + updated.isoformat() + ":\n" + "\n".join(
        f"{row['publisher']}: {row['title']} — {row['source_url']} ({row['license']})" for row in sources.values()
    ) + "\n"
    payloads = {name: _csv_bytes(sorted(rows, key=lambda row: row[next(iter(row))]), [field["name"] for field in schema["tables"][name]["fields"]]) for name, rows in tables.items()}
    payloads.update({
        "schema.json": _bytes(schema), "selection-report.json": _bytes(report),
        "sites.geojson": _bytes({"type": "FeatureCollection", "features": [_feature(row) for row in sorted(sites, key=lambda row: row["site_id"]) ]}),
        "review-provenance.json": _bytes({"input_sha256": _sha(input_bytes), "update": spec, "source_projections": source_details}),
        "ATTRIBUTION.txt": attribution.encode(),
        "README.md": (f"# Data Center Atlas — {updated.isoformat()}\n\n{len(sites)} sites in {counts['countries']} countries.\n\nEach status retains its observation date. This update does not reverify every inherited record.\nEarlier observations and correction history are preserved in the base dataset.\n\nAtlas-authored structure and annotations: CC BY 4.0. Third-party source facts retain their source terms; see ATTRIBUTION.txt.\n").encode(),
    })
    if has_consolidation:
        for name in ("source-records.json", "identity-mapping.json"):
            _require(name in base["files"], f"consolidated base is missing {name}")
            payloads[name] = (base_path / name).read_bytes()
    manifest = {
        "format": "datacenter-atlas-update-v1", "release_status": "published", "updated_at": updated.isoformat(),
        "cohort_lifecycle_reference_date": updated.isoformat(), "observation_window_start": min(row["status_as_of"] for row in projects),
        "observation_window_end": max(row["status_as_of"] for row in projects), "counts": counts,
        "base_dataset": spec["base_dataset"], "base_manifest_sha256": base_sha,
        "input_path": input_path.relative_to(root).as_posix(), "input_sha256": _sha(input_bytes),
        "source_files": source_files,
        "files": {name: {"bytes": len(data), "sha256": _sha(data)} for name, data in sorted(payloads.items())},
    }
    payloads["manifest.json"] = _bytes(manifest)
    payloads["manifest.sha256"] = (_sha(payloads["manifest.json"]) + "  manifest.json\n").encode()
    return payloads, manifest


def build_update(input_path: Path, output: Path, *, root: Path = ROOT):
    payloads, manifest = update_payloads(input_path, root=root)
    _require(not output.exists() or not any(output.iterdir()), "output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    return manifest


def validate_update(input_path: Path, output: Path, *, root: Path = ROOT):
    payloads, manifest = update_payloads(input_path, root=root)
    _require({path.name for path in output.iterdir()} == set(payloads), "dataset file list differs")
    for name, data in payloads.items():
        _require((output / name).read_bytes() == data, f"dataset is not reproducible: {name}")
    validate_dataset(output)
    return manifest
