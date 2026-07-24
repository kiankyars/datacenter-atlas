"""Publish the strict v35-to-v36 federation successor for open seed v87."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import csv
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import federated_release as legacy
from . import federated_release_v4 as federation
from . import federation_v35 as base
from . import global_official_builds_us_operator_gap_20260721 as us_gap
from . import open_seed_v87 as open_seed


ROOT = base.ROOT
BASE_DEFINITION = base.DEFINITION
BASE_INDEX_DIR = base.INDEX_DIR
V87_DEFINITION = open_seed.DEFINITION
V87_RELEASE = open_seed.RELEASE
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v36.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v36"
PUBLICATION_LOCK = ROOT / ".federation-v36.lock"

GENERATED_AT = "2026-07-22T00:30:00Z"
V87_RECORDED_AT = "2026-07-22T00:06:19Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v86"
NEW_RELEASE_ID = "epoch-official-open-seed-v87"
UNCHANGED_RELEASE_IDS = frozenset({"global-open-v3", "osm-fuzzy-review-v2"})

BASE_DEFINITION_PIN = (
    1_788,
    "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f",
)
BASE_MANIFEST_PIN = (
    986,
    "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388",
)
BASE_TREE_SHA256 = "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba"
V87_DEFINITION_PIN = (
    103_031,
    "bf0ef1b6bbe9f4f7edb4525de89d487de1e03ed5eaaccc1a0e122e24d5c9bf08",
)
V87_MANIFEST_PIN = (
    15_566,
    "6b2787e982049f1bcab139fce874880499c8610e2e71bb6bde091bcc101abf35",
)
V87_TREE_SHA256 = "02be747070df5f998080ca7c54a94146649a54b84078850c4c31522ae05c6185"

DEFINITION_PIN = (
    1_788,
    "84edf2fd5691dbac5740372c63ed87fa1be91f12cf48675c262ebd7c0a9b57d0",
)
INDEX_PIN = (
    36_486,
    "b5cc9f77f5b7eaef50631320ef748b4f246b79d19aa8b45a915911e54b122217",
)
MANIFEST_PIN = (
    986,
    "e9d2d82b06a56090a4a1a9fc3471d0d3ecd08573b42180449d9ff3db6fdd834c",
)
SIDECAR_PIN = (
    80,
    "370f72aa1380988573471ee4013efaea08b23a68eb7f4acdaf5424a7d2824ab2",
)
TREE_SHA256 = "f0532a1ebfeef502948f634a88ca10962eb75f25a84fce7da7026693371fa1cb"

LICENSE_EXPRESSION = base.LICENSE_EXPRESSION
RIGHTS_NOTICE = base.RIGHTS_NOTICE

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 555,
    "construction_pipeline_records": 472,
    "entities_by_kind": {"campus": 487, "project": 446},
    "evidence_records": 617,
    "resolution_candidates": 9,
    "source_family_entries": 367,
    "source_scoped_entity_records": 933,
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1341,
    "construction_pipeline_records": 6722,
    "evidence_records": 13630,
    "non_review_construction_pipeline_records": 592,
    "non_review_source_scoped_entity_records": 10228,
    "release_bundles": 3,
    "resolution_candidates": 100414,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 374,
    "source_scoped_entity_records": 16358,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 3,
    "construction_pipeline_records": 3,
    "evidence_records": 6,
    "non_review_construction_pipeline_records": 3,
    "non_review_source_scoped_entity_records": 6,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 1,
    "source_scoped_entity_records": 6,
}

EXPECTED_SOURCE_FAMILIES = {
    us_gap.RIOT_LEASE_EVIDENCE: "riot_platforms_company_news",
    us_gap.RIOT_FY_EVIDENCE: "riot_platforms_company_news",
    us_gap.DATABANK_CAMPUS_EVIDENCE: "databank_facility_pages",
    us_gap.DATABANK_SOCIAL_EVIDENCE: "databank_official_linkedin",
    us_gap.DATABANK_ATL5_EVIDENCE: "databank_facility_pages",
    us_gap.DATABANK_ATL6_EVIDENCE: "databank_facility_pages",
}
EXPECTED_CAPACITY_EXPORT = {
    "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit": (
        "critical_it_mw",
        "planned",
        "MW",
        25.0,
    ),
    "curated:databank-lithia-springs-campus:atl5-current-build": (
        "critical_it_mw",
        "design",
        "MW",
        48.0,
    ),
    "curated:databank-lithia-springs-campus:atl6-current-build": (
        "critical_it_mw",
        "design",
        "MW",
        72.0,
    ),
}
BANNED_CLAIMS = (
    "semianalysis",
    "semi-analysis",
    "global completeness",
    "regional completeness",
    "comprehensive",
    "parity",
)

CHILDREN = {
    NEW_RELEASE_ID: V87_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


class FederationV36Error(RuntimeError):
    """Raised when v36 lineage, claims, or publication differs."""


def _canonical_json(value: Any, *, sort_keys: bool = True) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise FederationV36Error(f"bundle contains symlink: {relative}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode()
            )
        else:
            raise FederationV36Error(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederationV36Error(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise FederationV36Error(f"frozen file pin differs: {path}")
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise FederationV36Error(f"frozen file mode differs: {path}")
    return raw


def _validate_tree(path: Path, expected: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
        or tree_digest(path) != expected
    ):
        raise FederationV36Error(f"frozen tree pin differs: {path}")
    for member in path.rglob("*"):
        expected_mode = 0o555 if member.is_dir() else 0o444
        if member.is_symlink() or stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise FederationV36Error(f"frozen tree member differs: {member}")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _validate_v87_provenance() -> None:
    try:
        documents = open_seed._validate_official_artifact()
        open_seed._validate_release_facts(V87_RELEASE, recorded_at=V87_RECORDED_AT)
    except open_seed.OpenSeedV87Error as error:
        raise FederationV36Error(f"accepted v87 source closure differs: {error}") from error

    base_definition = json.loads(open_seed.BASE_DEFINITION.read_text())
    definition = json.loads(V87_DEFINITION.read_text())
    additions = [
        {"path": path, "sha256": open_seed.ADDITION_PINS[path][1]}
        for path in open_seed.ADDITION_ORDER
    ]
    if (
        definition.get("release_id") != open_seed.RELEASE_ID
        or definition.get("build")
        != {"as_of": open_seed.AS_OF, "recorded_at": V87_RECORDED_AT}
        or definition.get("curated_inputs", ())[:452]
        != base_definition.get("curated_inputs")
        or definition.get("curated_inputs", ())[452:] != additions
        or len(definition.get("curated_inputs", ())) != 456
    ):
        raise FederationV36Error("accepted v87 is not the exact four-input append")

    entity_keys = {
        document[name]["stable_key"]
        for document in documents.values()
        for name in ("campus", "project")
    }
    evidence: dict[str, tuple[str, str]] = {}
    for document in documents.values():
        for row in document["evidence"]:
            observed = row["source_family"], row["content_hash"]
            previous = evidence.setdefault(row["key"], observed)
            if previous != observed:
                raise FederationV36Error("v87 duplicate evidence semantics differ")
    if (
        entity_keys != open_seed.ADDED_ENTITY_KEYS
        or set(evidence) != open_seed.ADDED_EVIDENCE_KEYS
        or {key: value[0] for key, value in evidence.items()}
        != EXPECTED_SOURCE_FAMILIES
    ):
        raise FederationV36Error("v87 source entity or evidence closure differs")

    source_document = json.loads((V87_RELEASE / "source_inputs.json").read_text())
    source_rows = {
        row.get("provenance", {}).get("curated_record_key"): row
        for row in source_document.get("sources", ())
        if row.get("provenance", {}).get("curated_record_key")
        in open_seed.ADDED_EVIDENCE_KEYS
    }
    if set(source_rows) != open_seed.ADDED_EVIDENCE_KEYS:
        raise FederationV36Error("v87 exported provenance closure differs")
    for key, row in source_rows.items():
        if (
            row.get("license") != "all-rights-reserved"
            or row.get("source_family") != EXPECTED_SOURCE_FAMILIES[key]
            or row.get("provenance", {}).get("content_hash") != evidence[key][1]
        ):
            raise FederationV36Error(f"v87 exported provenance differs: {key}")

    base_manifest = json.loads((open_seed.BASE_RELEASE / "manifest.json").read_text())
    manifest = json.loads((V87_RELEASE / "manifest.json").read_text())
    if set(manifest["source_families"]) - set(base_manifest["source_families"]) != {
        "riot_platforms_company_news"
    } or set(base_manifest["source_families"]) - set(manifest["source_families"]):
        raise FederationV36Error("v87 source-family delta differs")

    entities = {
        row["stable_key"]: row
        for row in _csv_rows(V87_RELEASE / "entities.csv")
        if row["stable_key"] in open_seed.ADDED_ENTITY_KEYS
    }
    if set(entities) != open_seed.ADDED_ENTITY_KEYS or any(
        row["latitude"]
        or row["longitude"]
        or row["geometry_json"] not in {"", "null"}
        or row["workloads_json"] != "[]"
        for row in entities.values()
    ):
        raise FederationV36Error("v87 inferred placement, geometry, or workload")
    first_phase = entities["curated:riot-rockdale-site:amd-lease-first-phase"]
    if (
        first_phase["status"] != "operational"
        or first_phase["status_as_of"] != "2026-01-31"
        or first_phase["capacity_estimates_json"] != "[]"
    ):
        raise FederationV36Error("v87 first operational phase capacity differs")
    for key, expected in EXPECTED_CAPACITY_EXPORT.items():
        rows = json.loads(entities[key]["capacity_estimates_json"])
        if len(rows) != 1 or (
            rows[0]["metric"],
            rows[0]["stage"],
            rows[0]["unit"],
            rows[0]["base"],
        ) != expected:
            raise FederationV36Error(f"v87 capacity semantics differ: {key}")
    for key in open_seed.ADDED_ENTITY_KEYS - set(EXPECTED_CAPACITY_EXPORT):
        if entities[key]["capacity_estimates_json"] != "[]":
            raise FederationV36Error(f"v87 inferred capacity aggregation: {key}")
    for key in (
        "curated:databank-lithia-springs-campus:atl5-current-build",
        "curated:databank-lithia-springs-campus:atl6-current-build",
    ):
        if (
            entities[key]["status"] != "under_construction"
            or entities[key]["operating_model"] != "colocation"
        ):
            raise FederationV36Error(f"v87 DataBank semantics differ: {key}")

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (V87_RELEASE / filename).read_bytes() != (
            open_seed.BASE_RELEASE / filename
        ).read_bytes():
            raise FederationV36Error("v87 introduced an identity-resolution inference")


def _validate_inputs() -> tuple[dict[str, Any], Mapping[str, Any]]:
    base_raw = _validate_file(BASE_DEFINITION, BASE_DEFINITION_PIN, mode=0o444)
    base_definition = json.loads(base_raw)
    if base_raw != _canonical_json(base_definition):
        raise FederationV36Error("accepted v35 definition is not canonical")
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_FILENAME,
        BASE_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(BASE_INDEX_DIR, BASE_TREE_SHA256)
    try:
        base_index = base.validate_federation_v35()
    except base.FederationV35Error as error:
        raise FederationV36Error(f"accepted v35 is invalid: {error}") from error
    if base_index.get("counts") != base.EXPECTED_COUNTS:
        raise FederationV36Error("accepted v35 counts differ")

    v87_raw = _validate_file(V87_DEFINITION, V87_DEFINITION_PIN, mode=0o444)
    v87 = json.loads(v87_raw)
    if (
        v87_raw != _canonical_json(v87)
        or v87.get("release_id") != open_seed.RELEASE_ID
        or v87.get("build", {}).get("recorded_at") != V87_RECORDED_AT
        or len(v87.get("curated_inputs", ())) != 456
    ):
        raise FederationV36Error("accepted v87 definition contract differs")
    _validate_file(
        V87_RELEASE / federation.MANIFEST_FILENAME,
        V87_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(V87_RELEASE, V87_TREE_SHA256)
    _validate_v87_provenance()
    child = legacy._ChildDefinition(
        release_id=NEW_RELEASE_ID,
        release_path=V87_RELEASE,
        reference="../../releases/2026-07-21-open-seed-v87/",
        expected_manifest_sha256=V87_MANIFEST_PIN[1],
        license_expression=LICENSE_EXPRESSION,
        rights_notice=RIGHTS_NOTICE,
    )
    descriptor = federation._inspect_child(child)
    if descriptor["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV36Error("accepted v87 child counts differ")
    manifest = descriptor["manifest"]
    if (
        manifest.get("recorded_at") != V87_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 521
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV36Error("accepted v87 status or geometry guardrail differs")
    return base_definition, base_index


def build_definition() -> bytes:
    accepted, _ = _validate_inputs()
    definition = deepcopy(accepted)
    definition["generated_at"] = GENERATED_AT
    matches = [
        row for row in definition["children"] if row["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise FederationV36Error("accepted v35 open child differs")
    matches[0].update(
        {
            "expected_manifest_sha256": V87_MANIFEST_PIN[1],
            "reference": "../../releases/2026-07-21-open-seed-v87/",
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v87",
        }
    )
    if {row["release_id"] for row in definition["children"]} != (
        UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
    ):
        raise FederationV36Error("v36 child set differs")
    _validate_no_completeness_claims(definition)
    return _canonical_json(definition)


def _validate_no_completeness_claims(*documents: Mapping[str, Any]) -> None:
    text = "\n".join(_canonical_json(document).decode().casefold() for document in documents)
    marker = next((claim for claim in BANNED_CLAIMS if claim in text), None)
    if marker is not None:
        raise FederationV36Error(f"v36 asserted a prohibited completeness claim: {marker}")


def _validate_counts(index: Mapping[str, Any], accepted: Mapping[str, Any]) -> None:
    if index.get("counts") != EXPECTED_COUNTS:
        raise FederationV36Error("v36 aggregate counts differ")
    delta = {
        key: index["counts"][key] - accepted["counts"][key]
        for key in EXPECTED_DELTA
    }
    if delta != EXPECTED_DELTA:
        raise FederationV36Error("v36 aggregate delta differs")
    by_id = {row["release_id"]: row for row in index["releases"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
    if set(by_id) != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}:
        raise FederationV36Error("v36 release set differs")
    if any(
        by_id[release_id] != accepted_by_id[release_id]
        for release_id in UNCHANGED_RELEASE_IDS
    ):
        raise FederationV36Error("v36 changed an inherited child descriptor")
    child = by_id[NEW_RELEASE_ID]
    if child["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV36Error("v36 v87 descriptor counts differ")
    manifest = child["manifest"]
    if (
        manifest.get("recorded_at") != V87_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 521
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV36Error("v36 inferred current status or geometry")
    if index["counts"]["unique_physical_sites"] is not None:
        raise FederationV36Error("v36 asserted a unique-site count")
    _validate_no_completeness_claims(index)


def _generated_at() -> datetime:
    return datetime.fromisoformat(GENERATED_AT.replace("Z", "+00:00"))


def _validate_stage_times(definition: Path, bundle: Path) -> None:
    target = _generated_at()
    for path in (definition, bundle, *bundle.rglob("*")):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > target:
            raise FederationV36Error(f"v36 staged bytes post-date generated_at: {path}")


def _wait_until_generated() -> None:
    target = _generated_at()
    while True:
        remaining = (target - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise FederationV36Error("active v36 publication lock exists") from error
    lock_stat = os.fstat(descriptor)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            current = PUBLICATION_LOCK.lstat()
        except FileNotFoundError:
            pass
        else:
            if (
                stat.S_ISREG(current.st_mode)
                and current.st_dev == lock_stat.st_dev
                and current.st_ino == lock_stat.st_ino
            ):
                PUBLICATION_LOCK.unlink()


def _validate_exact_definition(path: Path) -> bytes:
    expected = build_definition()
    raw = _validate_file(path, DEFINITION_PIN, mode=0o444)
    if (
        raw != expected
        or (len(expected), hashlib.sha256(expected).hexdigest()) != DEFINITION_PIN
    ):
        raise FederationV36Error("v36 definition differs")
    return raw


def _validate_offline_replays(definition: Path, bundle: Path) -> None:
    frozen = {path.name: path.read_bytes() for path in bundle.iterdir()}
    replay_payloads: list[dict[str, bytes]] = []
    for _ in range(2):
        replay = federation._bundle_payloads(
            federation.build_federated_release_index(definition)
        )
        if replay != frozen:
            raise FederationV36Error("v36 offline replay differs from private stage")
        replay_payloads.append(replay)
    if replay_payloads[0] != replay_payloads[1]:
        raise FederationV36Error("v36 offline replays differ")


def _validate_prepublication_boundary(
    staged_definition: Path, staged_bundle: Path
) -> None:
    raw = legacy._regular_bytes(staged_definition, "staged federation definition")
    document = legacy._json_object(raw, "staged federation definition")
    if raw != legacy._canonical_json(document):
        raise FederationV36Error("staged federation definition is not canonical")
    if set(document) != {"children", "generated_at", "schema_version"}:
        raise FederationV36Error("staged federation definition schema differs")
    generated_at = datetime.fromisoformat(
        legacy._timestamp(
            document["generated_at"],
            "federation generated_at",
            require_canonical_utc=True,
        ).replace("Z", "+00:00")
    )
    if datetime.now(UTC) < generated_at:
        raise FederationV36Error("v36 generated_at is not yet live")
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV36Error("v36 final path collision; refusing publication")
    federation.validate_federated_release_index(staged_bundle)
    for path in (staged_definition, staged_bundle):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > generated_at:
            raise FederationV36Error("v36 stage post-dates generated_at")


def validate_federation_v36() -> Mapping[str, Any]:
    _validate_exact_definition(DEFINITION)
    _, accepted = _validate_inputs()
    for filename, pin in (
        (federation.INDEX_FILENAME, INDEX_PIN),
        (federation.MANIFEST_FILENAME, MANIFEST_PIN),
        (federation.MANIFEST_HASH_FILENAME, SIDECAR_PIN),
    ):
        _validate_file(INDEX_DIR / filename, pin, mode=0o444)
    _validate_tree(INDEX_DIR, TREE_SHA256)
    index = federation.validate_federated_release_index(
        INDEX_DIR, child_release_paths=CHILDREN
    )
    rebuilt = federation.build_federated_release_index(DEFINITION)
    expected_files = federation._bundle_payloads(rebuilt)
    if any(
        (INDEX_DIR / name).read_bytes() != raw for name, raw in expected_files.items()
    ):
        raise FederationV36Error("v36 bundle is not exactly reproducible")
    _validate_counts(index, accepted)
    target = _generated_at()
    for path in (DEFINITION, INDEX_DIR):
        if datetime.fromtimestamp(path.stat().st_ctime, UTC) < target:
            raise FederationV36Error(f"v36 final root predates generated_at: {path}")
    return index


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise FederationV36Error("v36 rollback destination is occupied")
    INDEX_DIR.chmod(0o755)
    federation._promote_noreplace(INDEX_DIR, staged_bundle)
    staged_bundle.chmod(0o555)


def _rollback_definition(staged_definition: Path) -> None:
    if staged_definition.exists() or staged_definition.is_symlink():
        raise FederationV36Error("v36 definition rollback destination is occupied")
    federation._promote_noreplace(DEFINITION, staged_definition)


def build_and_publish_federation_v36() -> Mapping[str, Any]:
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV36Error("v36 final path collision; refusing publication")
    if _generated_at() <= datetime.now(UTC):
        raise FederationV36Error("v36 generated_at must be future before staging")
    definition_raw = build_definition()
    with _publication_lock():
        stage_root = Path(
            tempfile.mkdtemp(prefix=".federation-v36-private-stage-", dir=ROOT)
        )
        stage_root.chmod(0o700)
        staged_definition = stage_root / DEFINITION.name
        staged_bundle = stage_root / INDEX_DIR.name
        published_bundle = False
        published_definition = False
        bundle_members: dict[str, bytes] = {}
        try:
            legacy._write_bytes(staged_definition, definition_raw)
            staged_definition.chmod(0o444)
            federation.write_federated_release_index(staged_definition, staged_bundle)
            _validate_offline_replays(staged_definition, staged_bundle)
            _validate_stage_times(staged_definition, staged_bundle)
            frozen_definition = staged_definition.read_bytes()
            frozen_tree = tree_digest(staged_bundle)
            if (
                (len(frozen_definition), hashlib.sha256(frozen_definition).hexdigest())
                != DEFINITION_PIN
                or frozen_tree != TREE_SHA256
            ):
                raise FederationV36Error("v36 private stage pins differ")
            bundle_members = {
                path.name: path.read_bytes() for path in staged_bundle.iterdir()
            }
            _wait_until_generated()
            if (
                staged_definition.read_bytes() != frozen_definition
                or tree_digest(staged_bundle) != frozen_tree
                or any(
                    (staged_bundle / name).read_bytes() != raw
                    for name, raw in bundle_members.items()
                )
                or build_definition() != frozen_definition
            ):
                raise FederationV36Error("v36 private stage or inputs changed while waiting")
            _validate_stage_times(staged_definition, staged_bundle)
            _validate_prepublication_boundary(staged_definition, staged_bundle)

            staged_bundle.chmod(0o755)
            federation._promote_noreplace(staged_bundle, INDEX_DIR)
            published_bundle = True
            INDEX_DIR.chmod(0o555)
            try:
                federation._promote_noreplace(staged_definition, DEFINITION)
                published_definition = True
            except Exception:
                _rollback_bundle(staged_bundle)
                published_bundle = False
                raise

            try:
                _, accepted = _validate_inputs()
                index = federation.validate_federated_release_index(
                    INDEX_DIR, child_release_paths=CHILDREN
                )
                _validate_counts(index, accepted)
                return validate_federation_v36()
            except Exception:
                if published_definition:
                    _rollback_definition(staged_definition)
                    published_definition = False
                if published_bundle:
                    _rollback_bundle(staged_bundle)
                    published_bundle = False
                raise
        finally:
            if not published_definition and staged_definition.exists():
                staged_definition.chmod(0o600)
                staged_definition.unlink()
            if not published_bundle and staged_bundle.exists():
                staged_bundle.chmod(0o700)
                for path in staged_bundle.iterdir():
                    path.chmod(0o600)
                shutil.rmtree(staged_bundle)
            if stage_root.exists():
                stage_root.rmdir()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--verify", action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    index = (
        validate_federation_v36()
        if arguments.verify
        else build_and_publish_federation_v36()
    )
    print(
        json.dumps(
            {
                "counts": index["counts"],
                "definition": str(DEFINITION.resolve()),
                "federated_index": str(INDEX_DIR.resolve()),
                "generated_at": GENERATED_AT,
                "release_ids": [row["release_id"] for row in index["releases"]],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFINITION",
    "EXPECTED_COUNTS",
    "EXPECTED_DELTA",
    "EXPECTED_OPEN_COUNTS",
    "FederationV36Error",
    "GENERATED_AT",
    "INDEX_DIR",
    "build_and_publish_federation_v36",
    "build_definition",
    "main",
    "tree_digest",
    "validate_federation_v36",
]
