"""Lossless, reproducible consolidation of a separately curated project inventory.

This import is not a fresh primary-source verification. Identity decisions are an
explicit input; coarse locations, original dates and claim scopes stay intact.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date, datetime
import io
import json
import math
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from .dataset_update import ROOT, _bytes, _csv_bytes, _feature, _json, _path, _sha, _site_from_project
from .public_site import validate_dataset


class ConsolidationError(ValueError):
    """A consolidation would lose source content, evidence or identity."""


DECISIONS = {"exact_project", "same_site_distinct_scope", "unique_site", "multi_site_program", "unresolved"}
SNAPSHOT_ONLY = {"multi_site_program", "unresolved"}
LOCATION_SCOPES = {
    "site": "project_locator", "approximate_site": "approximate_site_locator",
    "locality": "locality_context", "admin2": "admin2_context", "admin1": "admin1_context",
}
SOURCE_KINDS = {
    "company": "company_disclosure", "government": "government_record",
    "regulatory_filing": "regulatory_filing", "court": "court_record",
    "news": "news", "trade_press": "trade_press", "analyst": "analyst_report",
    "utility": "utility_disclosure", "other": "other",
}
SITE_LISTS = {
    "geometry_source_entity_kinds": "geometry_source_entity_kind", "geometry_derivations": "geometry_derivation",
    "geometry_methods": "geometry_method", "geometry_scope_classes": "geometry_scope_class",
    "geometry_authority_classes": "geometry_authority_class", "geometry_use_scopes": "geometry_use_scope",
    "geometry_precision_scopes": "geometry_precision_scope", "geometry_evidence_ids": "geometry_evidence_id",
    "project_ids": "project_id", "project_stable_keys": "project_stable_key",
    "statuses": "last_observed_physical_status", "imagery_review_outcomes": "imagery_review_outcome",
}


def _require(condition, message):
    if not condition:
        raise ConsolidationError(message)


def _date(value):
    _require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "expected full ISO date")
    return date.fromisoformat(value)


def _precision(value):
    if not value:
        return "unknown"
    if re.fullmatch(r"\d{4}-\d{2}", value):
        _date(value + "-01")
        return "month"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        _date(value)
        return "day"
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return "datetime"


def _public_url(value):
    url = urlsplit(value)
    _require(url.scheme in {"http", "https"} and url.hostname and not url.username, "source URL must be public HTTP(S)")
    return value


def capture_snapshot(repository: Path, output: Path, *, captured_at: str):
    """Freeze every source object with the original file digest and repository commit."""
    _date(captured_at)
    _require(not output.exists(), "snapshot output already exists")

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repository), *args], text=True).strip()

    paths = sorted((repository / "datacenters/projects").glob("*.json"))
    _require(paths, "source repository contains no project records")
    records = []
    for path in paths:
        raw = path.read_bytes()
        record = json.loads(raw)
        records.append({
            "source_file": path.relative_to(repository).as_posix(),
            "source_bytes": len(raw), "source_sha256": _sha(raw),
            "source_record_sha256": _sha(_json(record).encode()), "record": record,
        })
    snapshot = {
        "format": "semiconductor-atlas-project-snapshot-v1", "captured_at": captured_at,
        "source_repository": "https://github.com/kiankyars/semiconductor-atlas",
        "source_repository_commit": git("rev-parse", "HEAD"),
        "source_worktree_changes": git("status", "--porcelain", "--", "datacenters/projects").splitlines(),
        "record_count": len(records), "records": records,
        "hash_policy": "source_sha256 hashes the original file bytes; source_record_sha256 hashes canonical JSON of the complete source object.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_bytes(snapshot))
    return snapshot


def _field(schema, table, name, logical="string", *, empty=False, description=""):
    fields = schema["tables"][table]["fields"]
    _require(name not in {item["name"] for item in fields}, f"base already has consolidation field {name}")
    fields.append({"name": name, "logical_type": logical, "allows_empty_string": empty, "description": description})


def _validate_record(entry, updated):
    record = entry["record"]
    _require(entry["source_record_sha256"] == _sha(_json(record).encode()), f"source record hash differs: {record.get('id')}")
    _require(re.fullmatch(r"[0-9a-f]{64}", entry["source_sha256"]), "invalid original source file hash")
    _require(isinstance(record["id"], str) and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", record["id"]), "source record ID must be a safe stable slug")
    _require(_date(record["status_as_of"]) <= updated, "future imported status date")
    source_ids = [source["id"] for source in record["sources"]]
    _require(source_ids and len(source_ids) == len(set(source_ids)), "missing or repeated record-local source IDs")

    def check_refs(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("source_ids"):
                    _require(isinstance(item, list) and all(ref in source_ids for ref in item), f"unresolved source reference in {record['id']}: {key}")
                else:
                    check_refs(item)
        elif isinstance(value, list):
            for item in value:
                check_refs(item)

    check_refs(record)
    _require(record["status_source_ids"] and record["location"]["source_ids"], "status and geometry need source references")
    location = record["location"]
    _require(location["precision"] in LOCATION_SCOPES, "unrecognized imported location precision")
    lat, lon = location["lat"], location["lon"]
    _require(all(isinstance(n, (float, int)) and not isinstance(n, bool) and math.isfinite(n) for n in (lat, lon)), "invalid imported coordinate")
    _require(-90 <= lat <= 90 and -180 <= lon <= 180, "imported coordinate outside range")
    for source in record["sources"]:
        _public_url(source["url"])
        _require(source["type"] in SOURCE_KINDS, "unknown imported source type")
        _require(_date(source["accessed"]) <= updated, "source access after consolidation date")
        precision = _precision(source.get("published"))
        if precision == "day":
            _require(_date(source["published"]) <= _date(source["accessed"]), "source accessed before publication")
        elif precision == "month":
            _require(source["published"] <= source["accessed"][:7], "source accessed before publication month")
    return record


def _source_roles(record):
    roles = {source["id"]: {"imported:record"} for source in record["sources"]}
    for source_id in record["status_source_ids"]:
        roles[source_id].add("imported:status")
    for source_id in record["location"]["source_ids"]:
        roles[source_id].add("imported:geometry")
    for field, key, prefix in (("parties", "role", "role"), ("metrics", "metric", "metric"),
                               ("milestones", "event", "milestone"), ("power_sources", "type", "power_source")):
        for item in record.get(field, []):
            for source_id in item.get("source_ids", []):
                roles[source_id].add(prefix + ":" + item[key])
    return roles


def consolidation_payloads(input_path: Path, *, root: Path = ROOT):
    """Return the complete release without writing or contacting source publishers."""
    input_bytes = input_path.read_bytes()
    spec = json.loads(input_bytes)
    _require(spec["format"] == "datacenter-atlas-consolidation-input-v1", "unsupported consolidation format")
    updated = _date(spec["updated_at"])
    base_path = _path(root, spec["base_dataset"])
    _, base_sha, _ = validate_dataset(base_path)
    _require(base_sha == spec["base_manifest_sha256"], "base manifest hash differs")
    frozen = {}
    for key in ("source_snapshot", "identity_mapping"):
        descriptor = spec[key]
        raw = _path(root, descriptor["path"]).read_bytes()
        _require(_sha(raw) == descriptor["sha256"], f"{key} hash differs")
        frozen[key] = (raw, json.loads(raw))
    snapshot, mapping = (frozen[key][1] for key in ("source_snapshot", "identity_mapping"))
    _require(snapshot["format"] == "semiconductor-atlas-project-snapshot-v1", "unsupported source snapshot")
    _require(mapping["format"] == "datacenter-atlas-consolidation-mapping-v1", "unsupported identity mapping")
    if "canonical_dataset" in mapping:
        _require(mapping["canonical_dataset"] == spec["base_dataset"], "identity mapping targets a different base dataset")
    for name, digest in mapping.get("canonical_inputs_sha256", {}).items():
        _require(name in {"projects.csv", "sites.csv", "evidence.csv"}, "unknown canonical mapping input")
        _require(_sha((base_path / name).read_bytes()) == digest, "identity mapping base table hash differs")
    _require(snapshot["record_count"] == len(snapshot["records"]) == spec["expected_source_records"], "source record count differs")
    _require(re.fullmatch(r"[0-9a-f]{40,64}", snapshot["source_repository_commit"]), "invalid source repository commit")
    records = {}
    for entry in snapshot["records"]:
        record = _validate_record(entry, updated)
        _require(record["id"] not in records, "duplicate source record ID")
        records[record["id"]] = entry
    decisions = {}
    for decision in mapping["decisions"]:
        identifier = decision["source_record_id"]
        _require(identifier not in decisions, "duplicate identity decision")
        _require(decision["decision"] in DECISIONS, "unknown identity decision")
        _require(isinstance(decision.get("rationale"), str) and decision["rationale"].strip(), "identity decision needs rationale")
        decisions[identifier] = decision
    _require(set(records) == set(decisions), "identity mapping must cover every source record exactly once")

    schema = json.loads((base_path / "schema.json").read_bytes())
    tables = {name: list(csv.DictReader(io.StringIO((base_path / name).read_text()))) for name in ("sites.csv", "projects.csv", "evidence.csv")}
    sites, projects, evidence = (tables[name] for name in ("sites.csv", "projects.csv", "evidence.csv"))
    inherited_site_ids = {site["site_id"] for site in sites}
    _field(schema, "projects.csv", "project_details_json", "json_array", description="Complete imported source objects, identity decisions, record provenance and local-source-to-evidence-ID maps. Dates, units, qualifiers and scopes are preserved without reinterpretation.")
    for name, description in (
        ("publication_date_precision", "Precision of published_at: day, month, datetime or unknown. Unknown dates remain empty; month dates are not padded."),
        ("content_hash_scope", "What content_hash covers; imported source_record_projection hashes a canonical factual record projection, never the publisher page."),
        ("source_record_id", "Original source inventory record ID, when imported."),
        ("source_local_id", "Original record-local source ID, when imported."),
        ("source_record_sha256", "SHA-256 of the full canonical source inventory object, when imported."),
    ):
        _field(schema, "evidence.csv", name, empty=name.startswith("source_"), description=description)
    for row in projects:
        row["project_details_json"] = "[]"
    for row in evidence:
        row.update(publication_date_precision=_precision(row.get("published_at")), content_hash_scope="inherited_unspecified",
                   source_record_id="", source_local_id="", source_record_sha256="")
    by_project = {row["project_stable_key"]: row for row in projects}
    by_site = {row["physical_site_stable_key"]: row for row in sites}
    evidence_ids = {row["evidence_id"] for row in evidence}
    country_names = {row["country_iso_a2"]: row["country"] for row in sites}
    country_names.update(spec["country_names"])
    imported_projects = {}
    resolved = []

    def resolve_project(identifier, pending=None):
        if identifier in imported_projects:
            return imported_projects[identifier]
        pending = set() if pending is None else pending
        _require(identifier not in pending, "cyclic source identity decisions")
        pending.add(identifier)
        decision, record = decisions[identifier], records[identifier]["record"]
        kind = decision["decision"]
        if kind in SNAPSHOT_ONLY:
            imported_projects[identifier] = None
            return None
        target_source = decision.get("target_source_record_id")
        if target_source:
            _require(target_source in records, "unknown source identity target")
            target = resolve_project(target_source, pending)
            _require(target is not None, "identity target is not a physical project")
        else:
            target = None
        if kind == "exact_project":
            if target is None:
                key = decision.get("target_project_stable_key")
                _require(key in by_project, "unknown exact-project target")
                target = by_project[key]
            _require(record["location"]["country"] == target["country_iso_a2"], "exact-project target is in a different country")
            imported_projects[identifier] = target
            return target
        key = f"imported:semiconductor-atlas:{identifier}"
        _require(key not in by_project, "duplicate imported project stable key")
        if kind == "same_site_distinct_scope":
            site_key = target["physical_site_stable_key"] if target else decision.get("target_physical_site_stable_key")
            _require(site_key in by_site, "unknown same-site target")
            _require(record["location"]["country"] == by_site[site_key]["country_iso_a2"], "same-site target is in a different country")
            sid = by_site[site_key]["site_id"]
        else:
            _require(not target_source, "unique site cannot have a source identity target")
            site_key = f"imported:semiconductor-atlas:{identifier}"
            _require(site_key not in by_site, "duplicate imported site stable key")
            sid = "vcc-site-" + _sha(site_key.encode())[:20]
        loc = record["location"]
        iso = loc["country"]
        _require(iso in country_names, f"missing country display name: {iso}")
        row = {field["name"]: "" for field in schema["tables"]["projects.csv"]["fields"]}
        row.update(
            project_id=str(uuid5(NAMESPACE_URL, key)), project_stable_key=key,
            site_id=sid, physical_site_stable_key=site_key, name=record["name"], country=country_names[iso], country_iso_a2=iso,
            latitude=str(loc["lat"]), longitude=str(loc["lon"]), geometry_json=_json({"type": "Point", "coordinates": [loc["lon"], loc["lat"]]}),
            geometry_type="Point", geometry_source_entity_kind="project", geometry_derivation="imported_reference_point",
            geometry_method="imported_reference_point", geometry_scope_class=loc["precision"], geometry_authority_class="compiled_reference",
            geometry_use_scope=LOCATION_SCOPES[loc["precision"]],
            geometry_precision_scope=loc.get("note") or f"Imported {loc['precision']} reference point; no surveyed boundary or positional accuracy is claimed.",
            horizontal_uncertainty_unknown_reason="The source record provides no measured horizontal uncertainty; original coordinate precision and note are preserved.",
            last_observed_physical_status=record["status"], status_as_of=record["status_as_of"],
            status_age_days_at_review=str((updated - _date(record["status_as_of"])).days),
            status_method="imported_documented_status", verification_posture="imported_source_record",
            independent_imagery_verification="false", imagery_review_outcome="not_reviewed",
            development_type="unknown", development_type_unknown_reason="Not normalized from imported source record.",
            operating_model="unknown", operating_model_unknown_reason="Not normalized from imported source record.",
            workloads_json="[]", workload_unknown_reason="Original workload labels are retained in project_details without inventing deployment scope or per-label source support.",
            role_claims_json="[]", power_observations_json="[]",
            power_unknown_reason="Original power metrics are retained in project_details with their units, qualifiers, phases and scopes; no unscoped or additive capacity is inferred.",
            annual_energy_observations_json="[]", annual_energy_unknown_reason="No scoped annual-energy observation selected; not estimated.",
            efficiency_observations_json="[]", efficiency_unknown_reason="No scoped efficiency observation selected; not estimated.",
            project_details_json="[]",
        )
        projects.append(row)
        by_project[key] = row
        imported_projects[identifier] = row
        if kind == "unique_site":
            site = _site_from_project(row, record["name"])
            sites.append(site)
            by_site[site_key] = site
        return row

    for identifier in sorted(records):
        resolve_project(identifier)

    for identifier, entry in sorted(records.items()):
        record, decision, project = entry["record"], decisions[identifier], imported_projects[identifier]
        related = []
        for key in decision.get("related_project_stable_keys", []):
            _require(decision["decision"] == "multi_site_program" and key in by_project, "unknown program-context target")
            related.append(by_project[key])
        linked_projects = [project] if project else related
        local_ids = {}
        roles = _source_roles(record)
        for source in record["sources"]:
            projection = {"source_record_id": identifier, "source_record_sha256": entry["source_record_sha256"], "source": source}
            digest = _sha(_json(projection).encode())
            eid = str(uuid5(NAMESPACE_URL, f"semiconductor-atlas:{identifier}:{source['id']}:{digest}"))
            _require(eid not in evidence_ids, "duplicate imported evidence ID")
            evidence_ids.add(eid)
            local_ids[source["id"]] = eid
            evidence.append({
                "evidence_id": eid, "roles_json": _json(sorted(roles[source["id"]] | ({"context:multi_site_program"} if related else set()))),
                "project_ids_json": _json(sorted(row["project_id"] for row in linked_projects)),
                "kind": SOURCE_KINDS[source["type"]], "title": source["title"], "source_url": source["url"],
                "publisher": source["publisher"], "source_family": urlsplit(source["url"]).hostname,
                "license": source.get("license") or "source-terms-not-recorded", "attribution": source["publisher"],
                "published_at": source.get("published") or "", "retrieved_at": source["accessed"], "content_hash": digest,
                "publication_date_precision": _precision(source.get("published")), "content_hash_scope": "source_record_projection",
                "source_record_id": identifier, "source_local_id": source["id"], "source_record_sha256": entry["source_record_sha256"],
            })
        detail = {
            "source_dataset": "semiconductor_atlas", "source_record_id": identifier,
            "source_file": entry["source_file"], "source_sha256": entry["source_sha256"],
            "source_record_sha256": entry["source_record_sha256"], "source_repository_commit": snapshot["source_repository_commit"],
            "identity_decision": decision, "source_evidence_ids": local_ids, "record": record,
        }
        resolved.append({
            "source_record_id": identifier, "decision": decision["decision"],
            "project_id": project["project_id"] if project else None,
            "site_id": project["site_id"] if project else None, "source_evidence_ids": local_ids,
            "related_project_ids": [row["project_id"] for row in related],
            "related_site_ids": sorted({row["site_id"] for row in related}),
        })
        for linked in linked_projects:
            linked["project_details_json"] = _json([*json.loads(linked["project_details_json"]), detail])
        if project is None:
            continue
        if project["project_stable_key"] == f"imported:semiconductor-atlas:{identifier}":
            source_by_id = {source["id"]: source for source in record["sources"]}
            for field, local in (("status", record["status_source_ids"][0]), ("geometry", record["location"]["source_ids"][0])):
                project[field + "_evidence_id"] = local_ids[local]
                project[field + "_source_url"] = source_by_id[local]["url"]
        role_claims = json.loads(project["role_claims_json"])
        for party in record["parties"]:
            for local in party.get("source_ids", []):
                role_claims.append({"party": party["name"], "role": party["role"], "relationship_scope": "unknown",
                                    "evidence_id": local_ids[local], "source_record_id": identifier, "notes": party.get("note")})
        project["role_claims_json"] = _json(role_claims)
        for role, column in (("owner", "owner"), ("operator", "operator"), ("user", "users"), ("tenant", "tenants"), ("customer", "customers")):
            values = {value.strip() for value in project[column].split(";") if value.strip()}
            values.update(claim["party"] for claim in role_claims if claim["role"] == role)
            project[column] = "; ".join(sorted(values))

    for site in sites:
        members = [row for row in projects if row["site_id"] == site["site_id"]]
        site["project_count"] = str(len(members))
        site["oldest_status_as_of"] = min(row["status_as_of"] for row in members)
        site["newest_status_as_of"] = max(row["status_as_of"] for row in members)
        for plural, singular in SITE_LISTS.items():
            # Existing site geometry has its own reviewed evidence set, often more
            # than the primary reference on a project. Imported campus context
            # does not replace that geometry or reduce its provenance.
            if site["site_id"] in inherited_site_ids and plural.startswith("geometry_"):
                continue
            site[plural + "_json"] = _json(sorted({row[singular] for row in members}))
        postures = {row["verification_posture"] for row in members}
        site["verification_posture"] = next(iter(postures)) if len(postures) == 1 else "mixed_review_postures"
    schema["observation_policy"] = "Source status dates and existing canonical selections are retained. Consolidation is not new verification; imported source records may contain primary or secondary evidence."
    schema["embedded_array_items"]["projects.csv:project_details_json"] = {"item_type": "imported_project_record"}
    schema["embedded_types"]["imported_project_record"] = {
        "required_fields": ["source_dataset", "source_record_id", "source_file", "source_sha256", "source_record_sha256", "source_repository_commit", "identity_decision", "source_evidence_ids", "record"],
        "record_policy": "The record object equals the source snapshot object, including every field, unknown value, qualifier, source and original date precision.",
    }
    schema["embedded_types"]["role_claim"]["allowed_roles"] = sorted(set(schema["embedded_types"]["role_claim"]["allowed_roles"]) | {party["role"] for entry in records.values() for party in entry["record"]["parties"]})
    schema["embedded_types"]["role_claim"]["optional_fields"] = ["notes", "source_record_id"]
    for name, table in schema["tables"].items():
        for field in table["fields"]:
            if "allowed_values" in field and field["logical_type"] == "string":
                field["allowed_values"] = sorted(set(field["allowed_values"]) | {row[field["name"]] for row in tables[name] if row[field["name"]]})
                field["allowed_values_scope"] = "Published observations and retained historical codes."
    counts = {
        "physical_sites": len(sites), "projects": len(projects), "evidence": len(evidence),
        "countries": len({row["country_iso_a2"] for row in sites}), "non_us_sites": sum(row["country_iso_a2"] != "US" for row in sites),
        "host_estate_context_projects": sum(row["geometry_use_scope"] == "host_estate_context" for row in projects),
        "official_boundary_projects": sum(row["geometry_use_scope"] == "official_boundary" for row in projects),
        "imported_source_records": len(records), "snapshot_only_records": sum(item["decision"] in SNAPSHOT_ONLY for item in resolved),
        "imported_source_references": sum(len(entry["record"]["sources"]) for entry in records.values()),
    }
    policy = "All imported source objects and references are retained. Exact projects share an existing project; phases remain separate projects at shared sites. Multi-site programs and unresolved identities stay in downloadable source records without being counted as physical sites."
    report = {
        "updated_at": spec["updated_at"], "lifecycle_reference_date": spec["updated_at"], "counts": counts,
        "base_dataset": spec["base_dataset"], "observation_policy": schema["observation_policy"],
        "consolidation_policy": policy, "decisions": dict(sorted(Counter(item["decision"] for item in resolved).items())),
        "source_record_resolutions": resolved,
    }
    attribution = (base_path / "ATTRIBUTION.txt").read_text()
    attribution += "\nConsolidated source inventory: " + snapshot["source_repository"] + " at " + snapshot["source_repository_commit"] + ".\n"
    attribution += "Imported references retain their recorded publishers and original publication/access dates. Source terms were not recorded in this inventory; no open license is inferred. Full source objects, including archived URLs, are in source-records.json.\n"
    attribution += ("\nImported coordinate provenance:\n"
                    "Each original location.note is retained verbatim. A location citation can support the named place while the coordinate was obtained separately; the first listed geometry reference is not necessarily the coordinate provider. Original geocoder responses and lookup hashes were not included in this inventory.\n"
                    "Where a location note identifies OpenStreetMap or its Nominatim geocoder as the coordinate provider: © OpenStreetMap contributors; ODbL 1.0, https://www.openstreetmap.org/copyright . This attribution concerns the derived reference point, not the separately cited company or news page.\n"
                    "Where a location note identifies Wikipedia: coordinate provenance is credited to Wikipedia contributors; article URLs are retained when the original record supplied them. Coordinate-specific source terms and underlying coordinate provenance were not recorded, and no license is inferred for the separately cited sources.\n"
                    "Imported evidence content_hash values hash the canonical factual source-record projection specified in consolidation.py, not a downloaded publisher page or geocoder response.\n")
    attribution += "\n".join(f"{row['publisher']}: {row['title']} — {row['source_url']}" for row in evidence if row["source_record_id"]) + "\n"
    payloads = {name: _csv_bytes(sorted(rows, key=lambda row: row[next(iter(row))]), [field["name"] for field in schema["tables"][name]["fields"]]) for name, rows in tables.items()}
    payloads.update({
        "schema.json": _bytes(schema), "selection-report.json": _bytes(report),
        "sites.geojson": _bytes({"type": "FeatureCollection", "features": [_feature(row) for row in sorted(sites, key=lambda row: row["site_id"]) ]}),
        "source-records.json": frozen["source_snapshot"][0], "identity-mapping.json": frozen["identity_mapping"][0],
        "review-provenance.json": _bytes({"input_sha256": _sha(input_bytes), "consolidation": spec,
                                         "source_repository_commit": snapshot["source_repository_commit"], "source_record_resolutions": resolved}),
        "ATTRIBUTION.txt": attribution.encode(),
        "README.md": (f"# Data Center Atlas — {spec['updated_at']} consolidated\n\n{len(sites)} physical sites, {len(projects)} projects and {len(records)} imported source records.\n\n{policy}\n\n{schema['observation_policy']}\n\nOriginal source objects, complete metrics and their qualifiers, milestones, parties, workload labels, power sources, related IDs, notes and references are preserved in source-records.json and project_details_json for linked projects. Source publication precision is explicit; a missing date is unknown. Coarse coordinates describe localities or administrative areas, not site footprints.\n\nAtlas-authored structure and annotations: CC BY 4.0. Third-party source facts retain their source terms; see ATTRIBUTION.txt.\n").encode(),
    })
    manifest = {
        "format": "datacenter-atlas-update-v1", "release_status": "published", "updated_at": spec["updated_at"],
        "cohort_lifecycle_reference_date": spec["updated_at"], "observation_window_start": min(row["status_as_of"] for row in projects),
        "observation_window_end": max(row["status_as_of"] for row in projects), "counts": counts,
        "base_dataset": spec["base_dataset"], "base_manifest_sha256": base_sha,
        "input_path": input_path.relative_to(root).as_posix(), "input_sha256": _sha(input_bytes),
        "source_files": [spec["source_snapshot"], spec["identity_mapping"]],
        "files": {name: {"bytes": len(data), "sha256": _sha(data)} for name, data in sorted(payloads.items())},
    }
    payloads["manifest.json"] = _bytes(manifest)
    payloads["manifest.sha256"] = (_sha(payloads["manifest.json"]) + "  manifest.json\n").encode()
    return payloads, manifest


def build_consolidation(input_path: Path, output: Path, *, root: Path = ROOT):
    payloads, manifest = consolidation_payloads(input_path, root=root)
    _require(not output.exists() or not any(output.iterdir()), "output must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        (output / name).write_bytes(data)
    return manifest



def validate_consolidation(input_path: Path, output: Path, *, root: Path = ROOT):
    payloads, manifest = consolidation_payloads(input_path, root=root)
    _require({path.name for path in output.iterdir()} == set(payloads), "dataset file list differs")
    for name, data in payloads.items():
        _require((output / name).read_bytes() == data, f"dataset is not reproducible: {name}")
    validate_dataset(output)
    return manifest
