"""Read reviewed prose for HTML pages without changing frozen dataset records.

The public tables intentionally contain a small common schema. Reviewed source
summaries live in the hash-pinned research provenance and curated source files.
Only prose bound to an exact evidence record and its current project is exposed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence
import uuid


class ProjectNarrativeError(ValueError):
    """A pinned narrative input or its dataset lineage failed verification."""


_CURATED_NAMESPACE = uuid.UUID("aa3d9079-c7f8-4a77-84d9-75ae2097549f")
_MAP_KINDS = frozenset({
    "openstreetmap", "map", "open_map_record", "open_map_geometry", "open_map",
    "government_cadastral_api", "government_cadastral_open_data",
    "government_address_register", "government_coordinate_transformation",
    "government_statistical_boundary", "government_municipal_project_map",
})


def _canonical_sha256(value: Any) -> str:
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ProjectNarrativeError("narrative input path is missing")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProjectNarrativeError(f"unsafe narrative input path: {value}")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ProjectNarrativeError(f"narrative input escapes repository: {value}")
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ProjectNarrativeError(f"symlink in narrative input path: {value}")
    return path


def _pinned_json(root: Path, spec: Mapping[str, Any]) -> Any:
    path = _path(root, spec.get("path"))
    if not path.is_file():
        raise ProjectNarrativeError(f"missing narrative input: {path}")
    raw = path.read_bytes()
    if (hashlib.sha256(raw).hexdigest() != spec.get("sha256")
            or ("bytes" in spec and (type(spec["bytes"]) is not int or len(raw) != spec["bytes"]))):
        raise ProjectNarrativeError(f"narrative input checksum differs: {path}")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise ProjectNarrativeError(f"invalid narrative JSON: {path}") from error


def _pointer(document: Any, pointer: Any) -> Any:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ProjectNarrativeError("invalid narrative JSON pointer")
    current = document
    for token in pointer.split("/")[1:]:
        if re.search(r"~(?![01])", token):
            raise ProjectNarrativeError("invalid narrative JSON pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif (isinstance(current, list) and re.fullmatch(r"0|[1-9][0-9]*", token)
              and int(token) < len(current)):
            current = current[int(token)]
        else:
            raise ProjectNarrativeError(f"unresolved narrative JSON pointer: {pointer}")
    return current


def _lineage(root: Path, versions: Sequence[Any], current: Any) -> list[Any]:
    by_path = {version.path.resolve(): version for version in versions}
    result = []
    seen = set()
    version = current
    while True:
        if version.path.resolve() in seen:
            raise ProjectNarrativeError("cyclic narrative dataset lineage")
        seen.add(version.path.resolve())
        result.append(version)
        manifest = version.manifest
        base = manifest.get("base_dataset") or manifest.get("base_preview_path")
        digest = manifest.get("base_manifest_sha256") or manifest.get("base_preview_manifest_sha256")
        if not base and manifest.get("base_preview_id"):
            base = (version.path.parent.relative_to(root) / manifest["base_preview_id"]).as_posix()
        if not base:
            break
        target = _path(root, base).resolve()
        if target not in by_path or by_path[target].manifest_sha256 != digest:
            raise ProjectNarrativeError(f"narrative base manifest differs: {base}")
        version = by_path[target]
    return result


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _reviewed_source_specs(root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Follow pinned review contracts to the curated sources shipped with the repo."""
    path = manifest.get("definition_paths", {}).get("reviewed_sites")
    digest = manifest.get("review_definition_sha256")
    if not path or not digest:
        return []
    result = []
    seen = set()
    while path:
        if path in seen:
            raise ProjectNarrativeError("cyclic narrative review contract")
        seen.add(path)
        contract = _pinned_json(root, {"path": path, "sha256": digest})
        for acceptance in contract.get("acceptances", []):
            source_path = acceptance.get("source_input_path")
            if (isinstance(source_path, str)
                    and acceptance.get("source_input_sha256")):
                result.append({"path": source_path, "sha256": acceptance["source_input_sha256"]})
        base = contract.get("base_contract") or {}
        path, digest = base.get("path"), base.get("sha256")
    return result


def _associated(evidence: Mapping[str, Any], project: Mapping[str, Any]) -> bool:
    return project["project_id"] in evidence.get("project_ids", [])


def _suitable_report(evidence: Mapping[str, Any], project: Mapping[str, Any]) -> bool:
    if (evidence.get("kind") in _MAP_KINDS
            or evidence.get("evidence_id") == project.get("geometry_evidence_id")):
        return False
    roles = set(evidence.get("roles", []))
    if roles and roles <= {"geometry", "imported:geometry", "context:geometry_identity",
                           "context:source_location_identity", "context:site_distinctness"}:
        return False
    # Previous physical observations do not become present-tense project copy.
    if "physical_status" in roles and evidence.get("evidence_id") != project.get("status_evidence_id"):
        return False
    return True


def load_project_narratives(
    root: Path, versions: Sequence[Any], current: Any, atlas: Any,
    read_verified_json: Callable[[Any, str], Any],
) -> dict[str, dict[str, Any]]:
    """Return ``project_id -> {status, context}`` with text/evidence-ID items.

    ``status`` is either ``None`` or ``{text, evidence_id}``; context is a list of
    the same item shape. Inputs are read-only and Atlas records are never mutated.
    The callback must verify manifest file hashes, as public_site._verified_json
    does. The newest matching status summary wins; stale status summaries cannot
    replace the current status. A single-source context update supplies reviewed
    prose for that project and evidence; its newest summary supersedes generic
    document prose. All report wording and its caveats stay intact.
    """
    root = root.resolve()
    projects = {row["project_stable_key"]: row for row in atlas.projects if row.get("project_stable_key")}
    evidence_by_id = atlas.evidence_by_id
    result: dict[str, dict[str, Any]] = {}
    scoped_context: dict[tuple[str, str], str] = {}

    def item(project: Mapping[str, Any]) -> dict[str, Any]:
        return result.setdefault(project["project_id"], {"status": None, "context": []})

    def report(project: Mapping[str, Any], evidence: Mapping[str, Any], text: Any) -> None:
        text = scoped_context.get((project["project_id"], evidence["evidence_id"]), _text(text))
        if not text or not _associated(evidence, project) or not _suitable_report(evidence, project):
            return
        narrative = item(project)
        entry = {"text": text, "evidence_id": evidence["evidence_id"]}
        if (entry != narrative["status"]
                and all(existing["text"] != text for existing in narrative["context"])):
            narrative["context"].append(entry)

    def modern_evidence(source: Any, project: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if not isinstance(source, dict):
            return None
        identifier = str(uuid.uuid5(uuid.NAMESPACE_URL,
                                   f"{source.get('source_url')}#{source.get('content_hash')}"))
        evidence = evidence_by_id.get(identifier)
        if (evidence and _associated(evidence, project)
                and evidence.get("source_url") == source.get("source_url")
                and evidence.get("content_hash") == source.get("content_hash")):
            return evidence
        return None

    lineage = []
    for version in _lineage(root, versions, current):
        files = version.manifest.get("files", {})
        provenance = (read_verified_json(version, "review-provenance.json")
                      if "review-provenance.json" in files else {})
        lineage.append((version, provenance))
        sources = provenance.get("source_projections", {})
        for change in provenance.get("update", {}).get("context_updates", []) or []:
            project = projects.get(change.get("project_stable_key"))
            source_ids = change.get("source_ids", [])
            summary = _text(change.get("summary"))
            if not project or not summary or len(source_ids) != 1:
                continue
            evidence = modern_evidence(sources.get(source_ids[0]), project)
            if evidence and _suitable_report(evidence, project):
                # Lineage is newest first. A shared document may have different
                # reviewed excerpts for each project, so neither source ID nor
                # document hash alone is a sufficient prose key.
                scoped_context.setdefault((project["project_id"], evidence["evidence_id"]), summary)

    pinned_specs: list[Mapping[str, Any]] = []
    for version, provenance in lineage:
        sources = provenance.get("source_projections", {})
        update = provenance.get("update", {})
        for change in [*update.get("additions", []), *update.get("status_updates", []),
                       *update.get("status_corrections", [])]:
            project = projects.get(change.get("project_stable_key"))
            if not project:
                continue
            status = change.get("status", {})
            source = sources.get(status.get("source_id"))
            evidence = modern_evidence(source, project)
            summary = _text(status.get("summary"))
            if (summary and evidence and status.get("value") == project.get("last_observed_physical_status")
                    and status.get("as_of") == project.get("status_as_of")
                    and evidence["evidence_id"] == project.get("status_evidence_id")
                    and item(project)["status"] is None):
                item(project)["status"] = {"text": summary, "evidence_id": evidence["evidence_id"]}
            if project.get("project_details"):
                continue
            for source_id in change.get("context_source_ids", []):
                source = sources.get(source_id)
                evidence = modern_evidence(source, project)
                if evidence:
                    report(project, evidence, source.get("summary"))
        for change in update.get("context_updates", []) or []:
            project = projects.get(change.get("project_stable_key"))
            if not project:
                continue
            for source_id in change.get("source_ids", []):
                source = sources.get(source_id)
                evidence = modern_evidence(source, project)
                if evidence:
                    report(project, evidence, source.get("summary"))
        pinned_specs.extend(provenance.get("source_inputs", []))
        pinned_specs.extend(spec for spec in version.manifest.get("portable_source_inputs", [])
                            if isinstance(spec.get("path"), str)
                            and spec["path"].startswith(("sources/", "source_artifacts/")))
        pinned_specs.extend(_reviewed_source_specs(root, version.manifest))

    # Old curated records use a different evidence-ID scheme. URL/hash matching
    # alone is unsafe: one source page can contain different project excerpts.
    read_cache: dict[tuple[str, str, int | None], Any] = {}
    collected: dict[str, str] = {}
    for spec in pinned_specs:
        cache_key = (spec["path"], spec["sha256"], spec.get("bytes"))
        if cache_key not in read_cache:
            read_cache[cache_key] = _pinned_json(root, spec)
        document = read_cache[cache_key]
        if "evidence_pointer" in spec:
            selected = _pointer(document, spec["evidence_pointer"])
            if _canonical_sha256(selected) != spec.get("evidence_sha256"):
                raise ProjectNarrativeError(f"narrative evidence checksum differs: {spec['path']}")
            candidates = [selected]
        else:
            candidates = document.get("evidence", []) if isinstance(document, dict) else []
        for source in candidates:
            if not isinstance(source, dict) or not source.get("key") or not _text(source.get("excerpt")):
                continue
            identifier = str(uuid.uuid5(_CURATED_NAMESPACE, "|".join([
                "evidence", "curated-official", source["key"], str(source.get("content_hash")),
            ])))
            evidence = evidence_by_id.get(identifier)
            if (not evidence or evidence.get("source_url") != source.get("source_url")
                    or evidence.get("content_hash") != source.get("content_hash")):
                continue
            text = source["excerpt"].strip()
            if identifier in collected and collected[identifier] != text:
                raise ProjectNarrativeError(f"conflicting narrative excerpts for evidence: {identifier}")
            collected[identifier] = text

    for project in atlas.projects:
        if project.get("project_details"):
            continue
        status_id = project.get("status_evidence_id")
        evidence = evidence_by_id.get(status_id)
        if (status_id in collected and evidence and _associated(evidence, project)
                and item(project)["status"] is None):
            item(project)["status"] = {"text": collected[status_id], "evidence_id": status_id}
        for evidence in atlas.evidence_by_project.get(project["project_id"], []):
            identifier = evidence["evidence_id"]
            if identifier in collected and identifier != status_id:
                report(project, evidence, collected[identifier])
    return {key: value for key, value in result.items() if value["status"] or value["context"]}
