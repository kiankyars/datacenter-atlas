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

from .public_site import validate_dataset


class UpdateError(ValueError):
    """An update cannot be applied without losing its evidence or identity."""


ACTIVE_STATUSES = {
    "site_preparation", "clearing", "civil_works", "foundations", "shell",
    "mep_electrical", "commissioning", "under_construction", "expansion",
}
STATUS_VALUES = ACTIVE_STATUSES | {"operational", "paused", "cancelled", "repurposed", "decommissioned", "demolished"}
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


def _status(spec, sources, updated, *, admission=False):
    observed = _date(spec["as_of"])
    _require(spec["value"] in STATUS_VALUES, "unrecognized physical status")
    _require(observed <= updated, "future physical observation")
    if admission:
        _require(spec["value"] in ACTIVE_STATUSES, "new admission needs physical construction")
        _require((updated - observed).days <= 90, "new admission observation is older than 90 days")
    source = sources[spec["source_id"]]
    _require(source.get("published_at"), "physical observation needs a dated source")
    _require(observed <= _date(source["published_at"]), "observation postdates its source")
    _require(source["kind"] in {"company_disclosure", "government_record", "regulatory_filing"}, "physical observation needs a primary source")
    _text(spec.get("summary"), "physical work summary")
    return source


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
    actions = [item["project_stable_key"] for group in ("additions", "status_updates", "status_corrections", "withdrawals") for item in spec.get(group, [])]
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
    by_key = {row["project_stable_key"]: row for row in projects}
    site_keys = {row["physical_site_stable_key"] for row in sites}
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
            evidence_by_id[identifier] = copy.deepcopy(source)
            evidence.append(evidence_by_id[identifier])
        row = evidence_by_id[identifier]
        row["roles_json"] = _json(sorted(set(json.loads(row["roles_json"])) | {role}))
        row["project_ids_json"] = _json(sorted(set(json.loads(row["project_ids_json"])) | {project_id}))
        return identifier

    for item in spec.get("additions", []):
        key, site_key = item["project_stable_key"], item["physical_site_stable_key"]
        _require(key not in by_key and site_key not in site_keys, "duplicate project or physical site; use a status update for existing sites")
        _text(item.get("distinctness_review"), "site distinctness review")
        _text(item.get("successor_review"), "later-status review")
        status, locator = item["status"], item["locator"]
        _status(status, sources, updated, admission=True)
        geometry = locator["geometry"]
        _require(geometry["type"] == "Point", "new point admissions only; complex boundary changes require a separate geometry review")
        coords = geometry["coordinates"]
        _require(isinstance(coords, list) and len(coords) == 2 and all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in coords), "invalid point coordinates")
        lon, lat = coords
        _require(-180 <= lon <= 180 and -90 <= lat <= 90, "point outside coordinate range")
        _require(locator["scope"] in {"project_locator", "reviewed_site_locator", "campus_locator"}, "new locator must locate the project or campus")
        for field in ("method", "precision", "identity_review"):
            _text(locator.get(field), f"locator {field}")
        uncertainty = locator.get("horizontal_uncertainty_metres")
        if uncertainty is None:
            _text(locator.get("uncertainty_reason"), "locator uncertainty reason")
        else:
            _require(isinstance(uncertainty, (int, float)) and not isinstance(uncertainty, bool) and math.isfinite(uncertainty) and uncertainty >= 0, "invalid horizontal uncertainty")
        iso = item["country_iso_a2"]
        _require(len(iso) == 2 and iso.isascii() and iso.isupper(), "invalid ISO country code")
        pid = str(uuid5(NAMESPACE_URL, key))
        sid = "vcc-site-" + _sha(site_key.encode())[:20]
        row = {field["name"]: "" for field in schema["tables"]["projects.csv"]["fields"]}
        row.update(
            project_id=pid, project_stable_key=key, site_id=sid, physical_site_stable_key=site_key,
            name=_text(item["name"], "project name"), country=_text(item["country"], "country"), country_iso_a2=iso,
            latitude=str(lat), longitude=str(lon), geometry_json=_json(geometry), geometry_type="Point",
            geometry_source_entity_kind="campus", geometry_derivation="direct_geometry", geometry_method=locator["method"],
            geometry_scope_class=locator["scope_class"], geometry_authority_class=locator["authority"], geometry_use_scope=locator["scope"],
            geometry_precision_scope=locator["precision"], horizontal_uncertainty_metres=str(uncertainty) if uncertainty is not None else "",
            horizontal_uncertainty_unknown_reason=locator.get("uncertainty_reason", ""),
            geometry_evidence_id=associate(locator["source_id"], pid, "geometry"),
            last_observed_physical_status=status["value"], status_as_of=status["as_of"], status_method="authoritative_physical_status_update",
            status_evidence_id=associate(status["source_id"], pid, "physical_status"),
            verification_posture="authoritative_physical_observation_plus_reviewed_site_locator",
            independent_imagery_verification="false", imagery_review_outcome="not_reviewed",
            development_type="unknown", development_type_unknown_reason="not established by selected evidence",
            operating_model="unknown", operating_model_unknown_reason="not established by selected evidence",
            workloads_json="[]", workload_unknown_reason="not established by selected evidence", role_claims_json="[]",
            power_observations_json="[]", power_unknown_reason="no typed power observation selected; not estimated",
            annual_energy_observations_json="[]", annual_energy_unknown_reason="no scoped annual-energy inputs; not estimated",
            efficiency_observations_json="[]", efficiency_unknown_reason="no scoped PUE or WUE observation",
            status_source_url=sources[status["source_id"]]["source_url"], geometry_source_url=sources[locator["source_id"]]["source_url"],
        )
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
        sites.append(_site_from_project(row, item["site_name"]))
        site_keys.add(site_key)

    changes = [(item, False) for item in spec.get("status_updates", [])]
    changes += [(item, True) for item in spec.get("status_corrections", [])]
    for item, correction in changes:
        key = item["project_stable_key"]
        _require(key in by_key and key not in touched, "unknown or repeated project update")
        touched.add(key)
        row, status = by_key[key], item["status"]
        _status(status, sources, updated)
        if correction:
            _require(item.get("replaces_status_evidence_id") == row["status_evidence_id"], "correction must name the replaced status evidence")
            _text(item.get("reason"), "status correction reason")
        else:
            _require(_date(status["as_of"]) > _date(row["status_as_of"]), "status refresh must be newer than existing observation")
        _text(item.get("identity_review"), "status identity review")
        _text(item.get("successor_review"), "later-status review")
        row.update(last_observed_physical_status=status["value"], status_as_of=status["as_of"],
                   status_evidence_id=associate(status["source_id"], row["project_id"], "physical_status"),
                   status_source_url=sources[status["source_id"]]["source_url"], status_method="authoritative_physical_status_update")

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
        evidence[:] = [source for source in evidence if json.loads(source["project_ids_json"])]
        withdrawn.append(key)

    for row in projects:
        row["status_age_days_at_review"] = str((updated - _date(row["status_as_of"])).days)
        _require(int(row["status_age_days_at_review"]) >= 0, "base has observations after update date")
    for site in sites:
        members = [row for row in projects if row["site_id"] == site["site_id"]]
        site["oldest_status_as_of"] = min(row["status_as_of"] for row in members)
        site["newest_status_as_of"] = max(row["status_as_of"] for row in members)
        site["statuses_json"] = _json(sorted({row["last_observed_physical_status"] for row in members}))
    counts = {
        "physical_sites": len(sites), "projects": len(projects), "evidence": len(evidence),
        "countries": len({row["country_iso_a2"] for row in sites}), "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
        "host_estate_context_projects": sum(row["geometry_use_scope"] == "host_estate_context" for row in projects),
        "official_boundary_projects": sum(row["geometry_use_scope"] == "official_boundary" for row in projects),
    }
    schema = {key: value for key, value in schema.items() if key not in {"draft_id", "base_preview_id", "v018_draft_contract", "inherited_baseline_annotations"}}
    for name, table in schema["tables"].items():
        for field in table["fields"]:
            if "allowed_values" in field and field["logical_type"] == "string":
                values = {row[field["name"]] for row in tables[name] if row[field["name"]] != ""}
                field["allowed_values"] = sorted(set(field["allowed_values"]) | values)
                field["allowed_values_scope"] = "Published observations and retained historical codes."
            if field["name"] == "last_observed_physical_status":
                field["allowed_values"] = sorted(STATUS_VALUES)
    schema.update(format="datacenter-atlas-tables-v1", observation_policy="Each status has its own observation date. Dataset updates do not renew older observations.")
    report = {
        "updated_at": updated.isoformat(), "lifecycle_reference_date": updated.isoformat(), "counts": counts,
        "added_sites": [item["physical_site_stable_key"] for item in spec.get("additions", [])],
        "refreshed_projects": sorted(touched - set(withdrawn)), "withdrawn_projects": withdrawn,
        "withdrawal_note": "Unsupported construction selections are removed; no cancellation or other physical status is inferred.",
        "base_dataset": spec["base_dataset"],
        "observation_policy": "Last documented observations; records are not a claim that all projects are still under construction on the update date.",
    }
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
