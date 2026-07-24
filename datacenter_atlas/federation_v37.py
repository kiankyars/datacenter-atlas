"""Publish the strict v36-to-v37 federation successor for open seed v92."""

from __future__ import annotations

import argparse
from collections import Counter
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
from . import federated_release_v5 as federation
from . import federation_v36 as base
from . import open_seed_v88 as v88
from . import open_seed_v89 as v89
from . import open_seed_v90 as v90
from . import open_seed_v91 as v91
from . import open_seed_v92 as open_seed


ROOT = base.ROOT
BASE_DEFINITION = base.DEFINITION
BASE_INDEX_DIR = base.INDEX_DIR
V92_DEFINITION = open_seed.DEFINITION
V92_RELEASE = open_seed.RELEASE
DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v37.json"
INDEX_DIR = ROOT / "federated_indexes/2026-07-21-public-open-v37"
PUBLICATION_LOCK = ROOT / ".federation-v37.lock"

GENERATED_AT = "2026-07-22T02:25:00Z"
V92_RECORDED_AT = "2026-07-22T02:00:23Z"
OLD_RELEASE_ID = "epoch-official-open-seed-v87"
NEW_RELEASE_ID = "epoch-official-open-seed-v92"
UNCHANGED_RELEASE_IDS = frozenset({"global-open-v3", "osm-fuzzy-review-v2"})

BASE_DEFINITION_PIN = (
    1_788,
    "84edf2fd5691dbac5740372c63ed87fa1be91f12cf48675c262ebd7c0a9b57d0",
)
BASE_MANIFEST_PIN = (
    986,
    "e9d2d82b06a56090a4a1a9fc3471d0d3ecd08573b42180449d9ff3db6fdd834c",
)
BASE_TREE_SHA256 = "f0532a1ebfeef502948f634a88ca10962eb75f25a84fce7da7026693371fa1cb"
V92_DEFINITION_PIN = (
    109_851,
    "2dab6d4a4bdac34f248268f9f2973ccac88b7fe25deb78b10cf5e44c11990516",
)
V92_MANIFEST_PIN = (
    16_558,
    "3ac9a48eeb121e6ac8a462fb2d99de1a7f2267c6cf9f6b7bd4b74d2b74a25fd7",
)
V92_TREE_SHA256 = "52bdbd5ea299dbd845adfe8e05f739894bff914107ae8fec341551bdb800034b"

DEFINITION_PIN = (
    1_788,
    "2154345738d4cf5560415192680838d89a3a06ac51c445b8806be79a85f0ec79",
)
INDEX_PIN = (
    37_517,
    "dfbd298ee43d7842cead86924ae4056a1500cfb109ca41139b8d7efe7c0d4fd9",
)
MANIFEST_PIN = (
    986,
    "e054aad23253e551e132a47ea0f95e1368a05879fba87ff6f0f6cd2bbe34d938",
)
SIDECAR_PIN = (
    80,
    "bc09a9c73f33f2bdacf1de33ee075fb3cce607549e0493fe38bca580dd1167ac",
)
TREE_SHA256 = "1f72c78760abebdc483adb8d36f1e9b012bba9a17830e69aae58e1435a9bb3e9"

LICENSE_EXPRESSION = base.LICENSE_EXPRESSION
RIGHTS_NOTICE = base.RIGHTS_NOTICE

EXPECTED_OPEN_COUNTS = {
    "capacity_estimates": 558,
    "construction_pipeline_records": 501,
    "entities_by_kind": {"campus": 513, "project": 475},
    "evidence_records": 645,
    "resolution_candidates": 9,
    "source_family_entries": 384,
    "source_scoped_entity_records": 988,
}
EXPECTED_COUNTS = {
    "capacity_estimates": 1344,
    "construction_pipeline_records": 6751,
    "evidence_records": 13658,
    "non_review_construction_pipeline_records": 621,
    "non_review_source_scoped_entity_records": 10283,
    "release_bundles": 3,
    "resolution_candidates": 100414,
    "review_only_construction_pipeline_records": 6130,
    "review_only_release_bundles": 1,
    "review_only_source_scoped_entity_records": 6130,
    "source_family_entries": 391,
    "source_scoped_entity_records": 16413,
    "unique_physical_sites": None,
}
EXPECTED_DELTA = {
    "capacity_estimates": 3,
    "construction_pipeline_records": 29,
    "evidence_records": 28,
    "non_review_construction_pipeline_records": 29,
    "non_review_source_scoped_entity_records": 55,
    "release_bundles": 0,
    "resolution_candidates": 0,
    "review_only_construction_pipeline_records": 0,
    "review_only_release_bundles": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_family_entries": 17,
    "source_scoped_entity_records": 55,
}

EXPECTED_CAPACITY_EXPORT = {
    "curated:vantage-nv1-reno-storey-county-campus:nv12-current-build": (
        "critical_it_mw",
        "planned",
        "MW",
        64.0,
    ),
}
V87_MUTATED_ENTITY_KEYS = frozenset(
    {"epoch-ai:data-center:9b244849-c931-5ed2-b694-3f43509cf198"}
)
BANNED_CLAIMS = (
    "semianalysis",
    "semi-analysis",
    "global completeness",
    "regional completeness",
    "comprehensive",
    "parity",
)

CHILDREN = {
    NEW_RELEASE_ID: V92_RELEASE,
    "global-open-v3": ROOT / "releases/2026-07-18-global-open-v3",
    "osm-fuzzy-review-v2": ROOT / "releases/2026-07-18-osm-fuzzy-review-v2",
}


class FederationV37Error(RuntimeError):
    """Raised when v37 lineage, claims, or publication differs."""


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
            raise FederationV37Error(f"bundle contains symlink: {relative}")
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
            raise FederationV37Error(f"unsupported bundle entry: {relative}")
    return digest.hexdigest()


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FederationV37Error(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise FederationV37Error(f"frozen file pin differs: {path}")
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise FederationV37Error(f"frozen file mode differs: {path}")
    return raw


def _validate_tree(path: Path, expected: str) -> None:
    if (
        path.is_symlink()
        or not path.is_dir()
        or stat.S_IMODE(path.stat().st_mode) != 0o555
        or tree_digest(path) != expected
    ):
        raise FederationV37Error(f"frozen tree pin differs: {path}")
    for member in path.rglob("*"):
        expected_mode = 0o555 if member.is_dir() else 0o444
        if member.is_symlink() or stat.S_IMODE(member.stat().st_mode) != expected_mode:
            raise FederationV37Error(f"frozen tree member differs: {member}")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _validate_v92_provenance() -> None:
    chain = (v88, v89, v90, v91, open_seed)
    try:
        for module in chain:
            module._validate_guard(module._guard_state())
            definition = json.loads(module.DEFINITION.read_text())
            recorded_at = definition["build"]["recorded_at"]
            module._validate_release_facts(module.RELEASE, recorded_at=recorded_at)
    except RuntimeError as error:
        raise FederationV37Error(
            f"accepted v87-to-v92 source chain differs: {error}"
        ) from error

    for module in chain:
        base_definition = json.loads(module.BASE_DEFINITION.read_text())
        definition = json.loads(module.DEFINITION.read_text())
        additions = [
            {"path": path, "sha256": module.ADDITION_PINS[path][1]}
            for path in module.ADDITION_ORDER
        ]
        base_inputs = base_definition.get("curated_inputs", ())
        inputs = definition.get("curated_inputs", ())
        if (
            definition.get("release_id") != module.RELEASE_ID
            or inputs[: len(base_inputs)] != base_inputs
            or inputs[len(base_inputs) :] != additions
            or len(inputs) != len(base_inputs) + len(additions)
        ):
            raise FederationV37Error(
                f"{module.RELEASE_ID} is not an exact curated-input append"
            )

    v92_base_definition = json.loads(open_seed.BASE_DEFINITION.read_text())
    v92_definition = json.loads(V92_DEFINITION.read_text())
    selected, _paths = open_seed.selected_inputs(
        v92_base_definition,
        recorded_at=V92_RECORDED_AT,
        validation_wall_clock=datetime.now(UTC),
    )
    if selected != v92_definition["curated_inputs"]:
        raise FederationV37Error("v92 collision-checked selected inputs differ")

    v87_release = v88.BASE_RELEASE
    v87_entities = {
        row["stable_key"]: row for row in _csv_rows(v87_release / "entities.csv")
    }
    v91_entities = {
        row["stable_key"]: row for row in _csv_rows(v91.RELEASE / "entities.csv")
    }
    v92_entities = {
        row["stable_key"]: row for row in _csv_rows(V92_RELEASE / "entities.csv")
    }
    prior_additions = set().union(
        v88.ADDED_ENTITY_KEYS,
        v89.ADDED_ENTITY_KEYS,
        v90.ADDED_ENTITY_KEYS,
        v91.ADDED_ENTITY_KEYS,
    )
    if (
        len(prior_additions) != 45
        or set(v91_entities) - set(v87_entities) != prior_additions
        or set(v92_entities) - set(v91_entities) != open_seed.ADDED_ENTITY_KEYS
        or len(open_seed.ADDED_ENTITY_KEYS) != 10
    ):
        raise FederationV37Error("v87-to-v91 or v92-only entity append differs")

    for filename in (
        "evidence.csv",
        "capacity_estimates.csv",
        "construction_pipeline.csv",
        "construction_source_signals.csv",
        "lifecycle_freshness.csv",
        "resolution_candidates.csv",
    ):
        before = Counter(
            json.dumps(row, sort_keys=True, ensure_ascii=False)
            for row in _csv_rows(v87_release / filename)
        )
        after = Counter(
            json.dumps(row, sort_keys=True, ensure_ascii=False)
            for row in _csv_rows(V92_RELEASE / filename)
        )
        if before - after:
            raise FederationV37Error(f"v92 changed an inherited v87 row: {filename}")

    changed_entities = {
        key
        for key, row in v87_entities.items()
        if v92_entities.get(key) != row
    }
    if changed_entities != V87_MUTATED_ENTITY_KEYS:
        raise FederationV37Error("v92 inherited entity mutation set differs")
    denton_key = next(iter(V87_MUTATED_ENTITY_KEYS))
    before_denton = dict(v87_entities[denton_key])
    after_denton = dict(v92_entities[denton_key])
    before_capacity = json.loads(before_denton.pop("capacity_estimates_json"))
    after_capacity = json.loads(after_denton.pop("capacity_estimates_json"))
    added_capacity = [row for row in after_capacity if row not in before_capacity]
    if (
        before_denton != after_denton
        or any(row not in after_capacity for row in before_capacity)
        or len(added_capacity) != 1
        or (
            added_capacity[0].get("metric"),
            added_capacity[0].get("stage"),
            added_capacity[0].get("unit"),
            added_capacity[0].get("base"),
            added_capacity[0].get("as_of_date"),
            added_capacity[0].get("evidence_id"),
            added_capacity[0].get("method"),
        )
        != (
            "grid_connection_mw",
            "contracted",
            "MW",
            394.0,
            "2026-04-21",
            "53e9af07-ef47-5a55-94c7-29b112ddafd8",
            "reported",
        )
        or "not precision, current draw, critical IT, generation, annual energy"
        not in added_capacity[0].get("notes", "")
    ):
        raise FederationV37Error("v88 Denton contracted grid claim differs")
    evidence_by_id = {
        row["evidence_id"]: row for row in _csv_rows(V92_RELEASE / "evidence.csv")
    }
    denton_evidence = evidence_by_id.get(added_capacity[0]["evidence_id"], {})
    if (
        denton_evidence.get("source_family") != "sec_edgar_core_scientific_exhibit"
        or denton_evidence.get("content_hash")
        != "5f4f71a85f2e2c7ec56fdfefd1c78c9fcb96f1887468a1dc71a4b5efdec86068"
    ):
        raise FederationV37Error("v88 Denton evidence provenance differs")

    documents = open_seed._validate_official_artifact()
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
                raise FederationV37Error("v92 duplicate evidence semantics differ")
    if entity_keys != open_seed.ADDED_ENTITY_KEYS or set(evidence) != (
        open_seed.ADDED_EVIDENCE_KEYS
    ):
        raise FederationV37Error("v92 source entity or evidence closure differs")

    source_document = json.loads((V92_RELEASE / "source_inputs.json").read_text())
    source_rows = {
        row.get("provenance", {}).get("curated_record_key"): row
        for row in source_document.get("sources", ())
        if row.get("provenance", {}).get("curated_record_key")
        in open_seed.ADDED_EXPORTED_EVIDENCE_KEYS
    }
    if set(source_rows) != open_seed.ADDED_EXPORTED_EVIDENCE_KEYS:
        raise FederationV37Error("v92 exported provenance closure differs")
    for key, row in source_rows.items():
        if (
            row.get("license") != "all-rights-reserved"
            or row.get("source_family") != evidence[key][0]
            or row.get("provenance", {}).get("content_hash") != evidence[key][1]
        ):
            raise FederationV37Error(f"v92 exported provenance differs: {key}")

    entities = {
        key: v92_entities[key] for key in open_seed.ADDED_ENTITY_KEYS
    }
    if any(
        not key.startswith("curated:")
        or row["latitude"]
        or row["longitude"]
        or row["geometry_json"] not in {"", "null"}
        or row["workloads_json"] != "[]"
        or row["operating_model"]
        for key, row in entities.items()
    ):
        raise FederationV37Error(
            "v92 inferred placement, OSM geometry, workload, or operating model"
        )
    for key, expected in EXPECTED_CAPACITY_EXPORT.items():
        rows = json.loads(entities[key]["capacity_estimates_json"])
        if len(rows) != 1 or (
            rows[0]["metric"],
            rows[0]["stage"],
            rows[0]["unit"],
            rows[0]["base"],
        ) != expected:
            raise FederationV37Error(f"v92 capacity semantics differ: {key}")
    for key in open_seed.ADDED_ENTITY_KEYS - set(EXPECTED_CAPACITY_EXPORT):
        if entities[key]["capacity_estimates_json"] != "[]":
            raise FederationV37Error(f"v92 inferred capacity aggregation: {key}")

    freshness = {
        row["stable_key"]: row
        for row in _csv_rows(V92_RELEASE / "lifecycle_freshness.csv")
        if row["stable_key"] in open_seed.ADDED_PROJECT_KEYS
    }
    if set(freshness) != open_seed.ADDED_PROJECT_KEYS or any(
        row["status_semantics"] != "last_observed"
        or row["current_status_classification"] != "unknown"
        or row["current_construction_claim"] != "false"
        for row in freshness.values()
    ):
        raise FederationV37Error("v92 inferred current construction status")

    manifest = json.loads((V92_RELEASE / "manifest.json").read_text())
    if (
        manifest.get("append_only_base_release") != v91.RELEASE_ID
        or manifest.get("base_rows_frozen") is not True
        or manifest.get("internal_database_delta")
        != {
            "capacity_estimates": 1,
            "entities": 10,
            "evidence": 19,
            "lifecycle_observations": 6,
        }
        or manifest.get("public_release_delta")
        != {
            "capacity_estimates": 1,
            "construction_pipeline": 5,
            "construction_source_signals": 5,
            "entities": 10,
            "evidence": 6,
            "lifecycle_freshness": 5,
        }
    ):
        raise FederationV37Error("v92 append-only manifest contract differs")

    for filename in ("resolution_candidates.csv", "resolution_candidates.json"):
        if (V92_RELEASE / filename).read_bytes() != (
            open_seed.BASE_RELEASE / filename
        ).read_bytes():
            raise FederationV37Error("v92 introduced an identity-resolution inference")


def _validate_inputs() -> tuple[dict[str, Any], Mapping[str, Any]]:
    base_raw = _validate_file(BASE_DEFINITION, BASE_DEFINITION_PIN, mode=0o444)
    base_definition = json.loads(base_raw)
    if base_raw != _canonical_json(base_definition):
        raise FederationV37Error("accepted v36 definition is not canonical")
    _validate_file(
        BASE_INDEX_DIR / federation.MANIFEST_FILENAME,
        BASE_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(BASE_INDEX_DIR, BASE_TREE_SHA256)
    try:
        base_index = federation.validate_federated_release_index(BASE_INDEX_DIR)
    except federation.FederatedReleaseError as error:
        raise FederationV37Error(f"accepted v36 is invalid: {error}") from error
    if base_index.get("counts") != base.EXPECTED_COUNTS:
        raise FederationV37Error("accepted v36 counts differ")

    v92_raw = _validate_file(V92_DEFINITION, V92_DEFINITION_PIN, mode=0o444)
    v92 = json.loads(v92_raw)
    if (
        v92_raw != _canonical_json(v92)
        or v92.get("release_id") != open_seed.RELEASE_ID
        or v92.get("build", {}).get("recorded_at") != V92_RECORDED_AT
        or len(v92.get("curated_inputs", ())) != 485
    ):
        raise FederationV37Error("accepted v92 definition contract differs")
    _validate_file(
        V92_RELEASE / federation.MANIFEST_FILENAME,
        V92_MANIFEST_PIN,
        mode=0o444,
    )
    _validate_tree(V92_RELEASE, V92_TREE_SHA256)
    _validate_v92_provenance()
    child = legacy._ChildDefinition(
        release_id=NEW_RELEASE_ID,
        release_path=V92_RELEASE,
        reference="../../releases/2026-07-21-open-seed-v92/",
        expected_manifest_sha256=V92_MANIFEST_PIN[1],
        license_expression=LICENSE_EXPRESSION,
        rights_notice=RIGHTS_NOTICE,
    )
    descriptor = federation._inspect_child(child)
    if descriptor["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV37Error("accepted v92 child counts differ")
    manifest = descriptor["manifest"]
    if (
        manifest.get("recorded_at") != V92_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 550
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV37Error("accepted v92 status or geometry guardrail differs")
    return base_definition, base_index


def build_definition() -> bytes:
    accepted, _ = _validate_inputs()
    definition = deepcopy(accepted)
    definition["generated_at"] = GENERATED_AT
    matches = [
        row for row in definition["children"] if row["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise FederationV37Error("accepted v36 open child differs")
    matches[0].update(
        {
            "expected_manifest_sha256": V92_MANIFEST_PIN[1],
            "reference": "../../releases/2026-07-21-open-seed-v92/",
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v92",
        }
    )
    if {row["release_id"] for row in definition["children"]} != (
        UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}
    ):
        raise FederationV37Error("v37 child set differs")
    _validate_no_completeness_claims(definition)
    return _canonical_json(definition)


def _validate_no_completeness_claims(*documents: Mapping[str, Any]) -> None:
    text = "\n".join(_canonical_json(document).decode().casefold() for document in documents)
    marker = next((claim for claim in BANNED_CLAIMS if claim in text), None)
    if marker is not None:
        raise FederationV37Error(f"v37 asserted a prohibited completeness claim: {marker}")


def _validate_counts(index: Mapping[str, Any], accepted: Mapping[str, Any]) -> None:
    if index.get("counts") != EXPECTED_COUNTS:
        raise FederationV37Error("v37 aggregate counts differ")
    delta = {
        key: index["counts"][key] - accepted["counts"][key]
        for key in EXPECTED_DELTA
    }
    if delta != EXPECTED_DELTA:
        raise FederationV37Error("v37 aggregate delta differs")
    by_id = {row["release_id"]: row for row in index["releases"]}
    accepted_by_id = {row["release_id"]: row for row in accepted["releases"]}
    if set(by_id) != UNCHANGED_RELEASE_IDS | {NEW_RELEASE_ID}:
        raise FederationV37Error("v37 release set differs")
    if any(
        by_id[release_id] != accepted_by_id[release_id]
        for release_id in UNCHANGED_RELEASE_IDS
    ):
        raise FederationV37Error("v37 changed an inherited child descriptor")
    child = by_id[NEW_RELEASE_ID]
    if child["counts"] != EXPECTED_OPEN_COUNTS:
        raise FederationV37Error("v37 v92 descriptor counts differ")
    manifest = child["manifest"]
    if (
        manifest.get("recorded_at") != V92_RECORDED_AT
        or manifest.get("current_status_inferred") is not False
        or manifest.get("lifecycle_status_semantics") != "last_observed"
        or manifest.get("lifecycle_freshness_records") != 550
        or manifest.get(federation.GEOMETRY_NON_INFERENCE_FIELD) is not False
    ):
        raise FederationV37Error("v37 inferred current status or geometry")
    if index["counts"]["unique_physical_sites"] is not None:
        raise FederationV37Error("v37 asserted a unique-site count")
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
            raise FederationV37Error(f"v37 staged bytes post-date generated_at: {path}")


def _wait_until_generated() -> None:
    target = _generated_at()
    while True:
        remaining = (target - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def _stamp_publication_ctimes(definition: Path, bundle: Path) -> None:
    """Advance every staged inode ctime after the declared publication time."""

    target = _generated_at()
    if datetime.now(UTC) < target:
        raise FederationV37Error("v37 cannot stamp publication ctimes before generated_at")
    definition.chmod(0o400)
    definition.chmod(0o444)
    bundle.chmod(0o755)
    for member in bundle.iterdir():
        member.chmod(0o400)
        member.chmod(0o444)
    bundle.chmod(0o555)
    for path in (definition, bundle, *bundle.rglob("*")):
        if datetime.fromtimestamp(path.stat().st_ctime, UTC) < target:
            raise FederationV37Error(f"v37 staged ctime predates generated_at: {path}")


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise FederationV37Error("active v37 publication lock exists") from error
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
        raise FederationV37Error("v37 definition differs")
    return raw


def _validate_offline_replays(definition: Path, bundle: Path) -> None:
    frozen = {path.name: path.read_bytes() for path in bundle.iterdir()}
    replay_payloads: list[dict[str, bytes]] = []
    for _ in range(2):
        replay = federation._bundle_payloads(
            federation.build_federated_release_index(definition)
        )
        if replay != frozen:
            raise FederationV37Error("v37 offline replay differs from private stage")
        replay_payloads.append(replay)
    if replay_payloads[0] != replay_payloads[1]:
        raise FederationV37Error("v37 offline replays differ")


def _validate_prepublication_boundary(
    staged_definition: Path, staged_bundle: Path
) -> None:
    raw = legacy._regular_bytes(staged_definition, "staged federation definition")
    document = legacy._json_object(raw, "staged federation definition")
    if raw != legacy._canonical_json(document):
        raise FederationV37Error("staged federation definition is not canonical")
    if set(document) != {"children", "generated_at", "schema_version"}:
        raise FederationV37Error("staged federation definition schema differs")
    generated_at = datetime.fromisoformat(
        legacy._timestamp(
            document["generated_at"],
            "federation generated_at",
            require_canonical_utc=True,
        ).replace("Z", "+00:00")
    )
    if datetime.now(UTC) < generated_at:
        raise FederationV37Error("v37 generated_at is not yet live")
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV37Error("v37 final path collision; refusing publication")
    federation.validate_federated_release_index(staged_bundle)
    for path in (staged_definition, staged_bundle):
        details = path.stat()
        born = datetime.fromtimestamp(
            getattr(details, "st_birthtime", details.st_ctime), UTC
        )
        modified = datetime.fromtimestamp(details.st_mtime, UTC)
        if max(born, modified) > generated_at:
            raise FederationV37Error("v37 stage post-dates generated_at")


def validate_federation_v37() -> Mapping[str, Any]:
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
        raise FederationV37Error("v37 bundle is not exactly reproducible")
    _validate_counts(index, accepted)
    target = _generated_at()
    for path in (DEFINITION, INDEX_DIR, *INDEX_DIR.rglob("*")):
        if datetime.fromtimestamp(path.stat().st_ctime, UTC) < target:
            raise FederationV37Error(f"v37 final inode predates generated_at: {path}")
    return index


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise FederationV37Error("v37 rollback destination is occupied")
    INDEX_DIR.chmod(0o755)
    federation._promote_noreplace(INDEX_DIR, staged_bundle)
    staged_bundle.chmod(0o555)


def _rollback_definition(staged_definition: Path) -> None:
    if staged_definition.exists() or staged_definition.is_symlink():
        raise FederationV37Error("v37 definition rollback destination is occupied")
    federation._promote_noreplace(DEFINITION, staged_definition)


def build_and_publish_federation_v37() -> Mapping[str, Any]:
    if (
        DEFINITION.exists()
        or DEFINITION.is_symlink()
        or INDEX_DIR.exists()
        or INDEX_DIR.is_symlink()
    ):
        raise FederationV37Error("v37 final path collision; refusing publication")
    if _generated_at() <= datetime.now(UTC):
        raise FederationV37Error("v37 generated_at must be future before staging")
    definition_raw = build_definition()
    with _publication_lock():
        stage_root = Path(
            tempfile.mkdtemp(prefix=".federation-v37-private-stage-", dir=ROOT)
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
                raise FederationV37Error("v37 private stage pins differ")
            bundle_members = {
                path.name: path.read_bytes() for path in staged_bundle.iterdir()
            }
            _wait_until_generated()
            _stamp_publication_ctimes(staged_definition, staged_bundle)
            if (
                staged_definition.read_bytes() != frozen_definition
                or tree_digest(staged_bundle) != frozen_tree
                or any(
                    (staged_bundle / name).read_bytes() != raw
                    for name, raw in bundle_members.items()
                )
                or build_definition() != frozen_definition
            ):
                raise FederationV37Error("v37 private stage or inputs changed while waiting")
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
                return validate_federation_v37()
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
        validate_federation_v37()
        if arguments.verify
        else build_and_publish_federation_v37()
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
    "FederationV37Error",
    "GENERATED_AT",
    "INDEX_DIR",
    "build_and_publish_federation_v37",
    "build_definition",
    "main",
    "tree_digest",
    "validate_federation_v37",
]
