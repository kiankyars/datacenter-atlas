"""Publish exact-identity v12 over accepted v11 and federation v36.

Only open-seed v87 replaces v86. Its six admitted source-scoped rows remain
six singleton exact components. Four project-to-campus edges are retained from
explicit curated targets; none is a physical-site merge or inferred claim.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping

from . import exact_identity_decisions as legacy
from . import exact_identity_decisions_carrier_v4 as carrier
from . import exact_identity_decisions_v11 as accepted_v11
from . import federated_release_v4 as federation
from . import federation_v36
from . import open_seed_v87
from .open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = "2026-07-21-public-open-v12"
RECORDED_AT = "2026-07-22T01:00:00Z"
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v12.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v12"
PUBLICATION_LOCK = ROOT / ".exact-identity-v12.lock"

PREDECESSOR_DEFINITION = accepted_v11.DEFINITION
PREDECESSOR_BUNDLE = accepted_v11.BUNDLE
PREDECESSOR_RECORDED_AT = "2026-07-21T23:44:08Z"
PREDECESSOR_DEFINITION_PIN = (
    1_736,
    "658ca591e25045245e2709564cd11a3cdd7d338f5be11913aca4ba54a6656a40",
)
PREDECESSOR_ACCOUNTING_PIN = (
    981,
    "b37514dcc86a52b3254f62ff740507e609c661a0179ee931af13aa4ba9a0f258",
)
PREDECESSOR_MANIFEST_PIN = (
    11_441,
    "cd54ee06c75272974d2ba43859226b61965d04c7ca6c515d19e44447fe48cbb9",
)
PREDECESSOR_TREE_SHA256 = (
    "b25b7b568df098a0405452cf3c0608d9d840ace15af120625f7650423d22f6d9"
)

FEDERATION_DEFINITION = federation_v36.DEFINITION
FEDERATION_BUNDLE = federation_v36.INDEX_DIR
FEDERATION_RECORDED_AT = federation_v36.GENERATED_AT
FEDERATION_DEFINITION_PIN = federation_v36.DEFINITION_PIN
FEDERATION_INDEX_PIN = federation_v36.INDEX_PIN
FEDERATION_MANIFEST_PIN = federation_v36.MANIFEST_PIN
FEDERATION_TREE_SHA256 = federation_v36.TREE_SHA256

V87_DEFINITION = open_seed_v87.DEFINITION
V87_RELEASE = open_seed_v87.RELEASE
V87_RECORDED_AT = "2026-07-22T00:06:19Z"
V87_DEFINITION_PIN = federation_v36.V87_DEFINITION_PIN
V87_MANIFEST_PIN = federation_v36.V87_MANIFEST_PIN
V87_TREE_SHA256 = federation_v36.V87_TREE_SHA256

OLD_RELEASE_ID = federation_v36.OLD_RELEASE_ID
NEW_RELEASE_ID = federation_v36.NEW_RELEASE_ID

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2455,
    "exact_component_reductions": 1732,
    "exact_source_record_components": 8496,
    "non_review_source_scoped_entity_records": 10228,
    "raw_topology_links": 2860,
    "release_candidate_references": 100414,
    "review_only_source_scoped_entity_records": 6130,
    "source_scoped_entity_records": 16358,
    "unresolved_candidate_references": 100541,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 4,
    "exact_component_reductions": 0,
    "exact_source_record_components": 6,
    "non_review_source_scoped_entity_records": 6,
    "raw_topology_links": 4,
    "release_candidate_references": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 6,
    "unresolved_candidate_references": 0,
}

NEW_ENTITY_CONTRACT = {
    "curated:riot-rockdale-site": ("campus", "riot_platforms_company_news"),
    "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit": (
        "project",
        "riot_platforms_company_news",
    ),
    "curated:riot-rockdale-site:amd-lease-first-phase": (
        "project",
        "riot_platforms_company_news",
    ),
    "curated:databank-lithia-springs-campus": (
        "campus",
        "databank_facility_pages",
    ),
    "curated:databank-lithia-springs-campus:atl5-current-build": (
        "project",
        "databank_facility_pages",
    ),
    "curated:databank-lithia-springs-campus:atl6-current-build": (
        "project",
        "databank_facility_pages",
    ),
}
EXPECTED_TARGETS = {
    "curated:riot-rockdale-site:amd-25mw-existing-building-retrofit": (
        "curated:riot-rockdale-site"
    ),
    "curated:riot-rockdale-site:amd-lease-first-phase": (
        "curated:riot-rockdale-site"
    ),
    "curated:databank-lithia-springs-campus:atl5-current-build": (
        "curated:databank-lithia-springs-campus"
    ),
    "curated:databank-lithia-springs-campus:atl6-current-build": (
        "curated:databank-lithia-springs-campus"
    ),
}

DEFINITION_PIN = (
    1_736,
    "18a6717fb01b7db1f1b9424d3cb03d7628dc3b4b8b06979c8e7c0088010ac0c2",
)
ARTIFACT_PINS = {
    "ATTRIBUTION.txt": (
        8_316,
        "47ab5a6794117b0ff7c6156e2652a82cc6f3784d22e2e74c5779f8044ba4acc8",
    ),
    "README.md": (
        629,
        "836a5566da3a89aa726704c86466771fa09377480f798f6012568eb2c310f8b3",
    ),
    "accounting.json": (
        981,
        "576ae85628bbca5a8f43fe4382833a4336ab7d5f802dac38aea0d6f794d86a19",
    ),
    "component-members.csv": (
        3_708_569,
        "9a728937c8667bfb66110ab3235063ac73ec1b8c102ab6d489ff0de4d986a3ca",
    ),
    "manifest.json": (
        11_441,
        "2bb6c2699b53aa3f4e3a1e6cb966985e45419bdfd28fbef866745a3000f431a4",
    ),
    "manifest.sha256": (
        80,
        "1d2e9da23d4ef595a259404cfd975499b1d81280ac47915fe43db34dd0fe8c58",
    ),
    "relationships.csv": (
        948_201,
        "2607f2ca2e7b59ed3c307062b7bb72d874ff76b3202625120c8d685b13cfd633",
    ),
    "source-lineage.csv": (
        44_869,
        "04378128883776c1f2df649dd73b7d7e08f48b3125719b008d55239b82b4ee3b",
    ),
    "unresolved-candidate-references.csv": (
        38_421_688,
        "6b8baf8979b62c13a8766d0f57a8933b348738091b87ba20b0354a126f0c4b39",
    ),
}
BUNDLE_TREE_SHA256 = (
    "c045070811263c471d8b993f6712608412addf17e24cb68b243a83a0d0ba4891"
)

REJECTED_LINEAGE_TOKENS = accepted_v11.REJECTED_LINEAGE_TOKENS
SUPERSEDED_LINEAGE_TOKENS = (
    *accepted_v11.SUPERSEDED_LINEAGE_TOKENS,
    b"2026-07-21-public-open-v35",
    b"epoch-official-open-seed-v86",
    b"2026-07-21-open-seed-v86",
    b"2026-07-21-public-open-v11",
)

ACCOUNTING_FILENAME = carrier.ACCOUNTING_FILENAME
ATTRIBUTION_FILENAME = carrier.ATTRIBUTION_FILENAME
BUNDLE_FILES = carrier.BUNDLE_FILES
BUNDLE_FORMAT = carrier.BUNDLE_FORMAT
COMPONENTS_FILENAME = carrier.COMPONENTS_FILENAME
DEFINITION_FORMAT = carrier.DEFINITION_FORMAT
LINEAGE_FILENAME = carrier.LINEAGE_FILENAME
MANIFEST_FILENAME = carrier.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = carrier.MANIFEST_HASH_FILENAME
POLICY = carrier.POLICY
README_FILENAME = carrier.README_FILENAME
RELATIONSHIPS_FILENAME = carrier.RELATIONSHIPS_FILENAME
UNRESOLVED_FILENAME = carrier.UNRESOLVED_FILENAME
ExactIdentityDecisionError = carrier.ExactIdentityDecisionError

_canonical_json = accepted_v11._canonical_json
_wall_clock = accepted_v11._wall_clock
_parsed_timestamp = accepted_v11._parsed_timestamp
_regular_document = accepted_v11._regular_document
_path_timestamp_bounds = accepted_v11._path_timestamp_bounds
_final_root_ctime = accepted_v11._final_root_ctime


def _sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ExactIdentityDecisionError(f"pinned input must be a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_file(path: Path, pin: tuple[int, str], *, mode: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ExactIdentityDecisionError(f"expected ordinary frozen file: {path}")
    raw = path.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != pin:
        raise ExactIdentityDecisionError(f"frozen identity pin differs: {path}")
    if stat.S_IMODE(path.stat().st_mode) != mode:
        raise ExactIdentityDecisionError(f"frozen identity mode differs: {path}")
    return raw


def _guard_state() -> dict[str, tuple[int, str] | str]:
    return {
        "predecessor_definition": (
            PREDECESSOR_DEFINITION.stat().st_size,
            _sha256(PREDECESSOR_DEFINITION),
        ),
        "predecessor_accounting": (
            (PREDECESSOR_BUNDLE / ACCOUNTING_FILENAME).stat().st_size,
            _sha256(PREDECESSOR_BUNDLE / ACCOUNTING_FILENAME),
        ),
        "predecessor_manifest": (
            (PREDECESSOR_BUNDLE / MANIFEST_FILENAME).stat().st_size,
            _sha256(PREDECESSOR_BUNDLE / MANIFEST_FILENAME),
        ),
        "predecessor_tree": tree_digest(PREDECESSOR_BUNDLE),
        "federation_definition": (
            FEDERATION_DEFINITION.stat().st_size,
            _sha256(FEDERATION_DEFINITION),
        ),
        "federation_index": (
            (FEDERATION_BUNDLE / federation.INDEX_FILENAME).stat().st_size,
            _sha256(FEDERATION_BUNDLE / federation.INDEX_FILENAME),
        ),
        "federation_manifest": (
            (FEDERATION_BUNDLE / MANIFEST_FILENAME).stat().st_size,
            _sha256(FEDERATION_BUNDLE / MANIFEST_FILENAME),
        ),
        "federation_tree": tree_digest(FEDERATION_BUNDLE),
        "v87_definition": (V87_DEFINITION.stat().st_size, _sha256(V87_DEFINITION)),
        "v87_manifest": (
            (V87_RELEASE / MANIFEST_FILENAME).stat().st_size,
            _sha256(V87_RELEASE / MANIFEST_FILENAME),
        ),
        "v87_tree": tree_digest(V87_RELEASE),
    }


def _require_guard_state() -> dict[str, tuple[int, str] | str]:
    try:
        accepted_v11.validate_exact_identity_decision_bundle()
        federation_v36.validate_federation_v36()
    except (
        OSError,
        ExactIdentityDecisionError,
        federation_v36.FederationV36Error,
    ) as error:
        raise ExactIdentityDecisionError(
            f"accepted identity-v12 lineage validation failed: {error}"
        ) from error
    expected: dict[str, tuple[int, str] | str] = {
        "predecessor_definition": PREDECESSOR_DEFINITION_PIN,
        "predecessor_accounting": PREDECESSOR_ACCOUNTING_PIN,
        "predecessor_manifest": PREDECESSOR_MANIFEST_PIN,
        "predecessor_tree": PREDECESSOR_TREE_SHA256,
        "federation_definition": FEDERATION_DEFINITION_PIN,
        "federation_index": FEDERATION_INDEX_PIN,
        "federation_manifest": FEDERATION_MANIFEST_PIN,
        "federation_tree": FEDERATION_TREE_SHA256,
        "v87_definition": V87_DEFINITION_PIN,
        "v87_manifest": V87_MANIFEST_PIN,
        "v87_tree": V87_TREE_SHA256,
    }
    actual = _guard_state()
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise ExactIdentityDecisionError(
            "accepted identity-v12 input pin drift: " + ", ".join(differing)
        )
    return actual


def _v12_document(recorded_at: str = RECORDED_AT) -> dict[str, Any]:
    if recorded_at != RECORDED_AT:
        raise ExactIdentityDecisionError("identity v12 recorded_at is fixed")
    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v11 definition"
    )
    result = deepcopy(predecessor)
    result["bundle_id"] = BUNDLE_ID
    result["recorded_at"] = RECORDED_AT
    result["federation"] = {
        "expected_index_sha256": FEDERATION_INDEX_PIN[1],
        "expected_manifest_sha256": FEDERATION_MANIFEST_PIN[1],
        "index_path": "../federated_indexes/2026-07-21-public-open-v36",
    }
    old_children = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(old_children) != 1:
        raise ExactIdentityDecisionError("accepted identity v11 seed child changed")
    old_children[0].update(
        {
            "expected_manifest_sha256": V87_MANIFEST_PIN[1],
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v87",
        }
    )
    result["expected"] = dict(EXPECTED_COUNTS)
    return result


def _assert_forbidden_lineage_absent(payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        for token in (*REJECTED_LINEAGE_TOKENS, *SUPERSEDED_LINEAGE_TOKENS):
            if token in raw:
                raise ExactIdentityDecisionError(
                    f"forbidden lineage token in identity v12 {name}: "
                    f"{token.decode('ascii')}"
                )


def _definition_object(
    document: Mapping[str, Any], raw: bytes, *, logical_path: Path = DEFINITION
) -> legacy._Definition:
    expected = _v12_document(RECORDED_AT)
    if document != expected or raw != _canonical_json(expected):
        raise ExactIdentityDecisionError(
            "identity v12 definition is not the exact v11 structural successor"
        )
    _assert_forbidden_lineage_absent({logical_path.name: raw})
    children = []
    for child in document["children"]:
        relative = Path(child["release_path"])
        if relative.is_absolute():
            raise ExactIdentityDecisionError("identity v12 child path must be relative")
        children.append(
            {**child, "release_path": (logical_path.parent / relative).resolve()}
        )
    return legacy._Definition(
        path=logical_path.resolve(),
        raw=raw,
        bundle_id=BUNDLE_ID,
        recorded_at=RECORDED_AT,
        federation=dict(document["federation"]),
        children=tuple(sorted(children, key=lambda item: item["release_id"])),
        expected=dict(EXPECTED_COUNTS),
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _replace_occurrence(value: str) -> str:
    prefix = f"{OLD_RELEASE_ID}:"
    if not value.startswith(prefix):
        raise ExactIdentityDecisionError("v11 occurrence replacement scope differs")
    return f"{NEW_RELEASE_ID}:{value.removeprefix(prefix)}"


def _child_feature_inventory() -> dict[str, dict[str, Any]]:
    old_rows = {
        row["entity_id"]: row
        for row in _csv_rows(open_seed_v87.BASE_RELEASE / "entities.csv")
    }
    new_rows = {row["entity_id"]: row for row in _csv_rows(V87_RELEASE / "entities.csv")}
    if (
        len(old_rows) != 927
        or len(new_rows) != 933
        or set(old_rows) - set(new_rows)
        or any(new_rows[key] != row for key, row in old_rows.items())
    ):
        raise ExactIdentityDecisionError("v87 replaced an unchanged v86 source record")
    added_ids = set(new_rows) - set(old_rows)
    if (
        {new_rows[key]["stable_key"] for key in added_ids}
        != set(NEW_ENTITY_CONTRACT)
        or any(
            new_rows[key]["latitude"]
            or new_rows[key]["longitude"]
            or new_rows[key]["geometry_json"] not in {"", "null"}
            for key in added_ids
        )
    ):
        raise ExactIdentityDecisionError("v87 six-record identity inventory differs")

    geojson = json.loads((V87_RELEASE / "atlas.geojson").read_text())
    features = {
        row["properties"]["stable_key"]: row
        for row in geojson["features"]
        if row["properties"]["stable_key"] in NEW_ENTITY_CONTRACT
    }
    if set(features) != set(NEW_ENTITY_CONTRACT):
        raise ExactIdentityDecisionError("v87 added feature inventory differs")
    by_entity = {row["id"]: key for key, row in features.items()}
    actual_targets = {}
    for key, feature in features.items():
        properties = feature["properties"]
        if (
            feature.get("geometry") is not None
            or (properties["entity_kind"], properties["source_family"])
            != NEW_ENTITY_CONTRACT[key]
        ):
            raise ExactIdentityDecisionError("v87 inferred placement or identity class")
        target = properties.get("target_entity_id")
        if target is not None:
            if target not in by_entity:
                raise ExactIdentityDecisionError("v87 project target is outside additions")
            actual_targets[key] = by_entity[target]
    if actual_targets != EXPECTED_TARGETS:
        raise ExactIdentityDecisionError("v87 explicit campus relationship inventory differs")
    if (
        (V87_RELEASE / "resolution_candidates.json").read_bytes()
        != (open_seed_v87.BASE_RELEASE / "resolution_candidates.json").read_bytes()
    ):
        raise ExactIdentityDecisionError("v87 introduced an identity candidate")
    return features


def _validate_component_delta(bundle: Path) -> dict[str, str]:
    features = _child_feature_inventory()
    previous = _csv_rows(PREDECESSOR_BUNDLE / COMPONENTS_FILENAME)
    current = _csv_rows(bundle / COMPONENTS_FILENAME)
    previous_open = [row for row in previous if row["release_id"] == OLD_RELEASE_ID]
    current_open = [row for row in current if row["release_id"] == NEW_RELEASE_ID]
    if len(previous_open) != 927 or len(current_open) != 933:
        raise ExactIdentityDecisionError("identity v12 replaced-record count differs")
    previous_by_entity = {row["entity_id"]: row for row in previous_open}
    current_by_entity = {row["entity_id"]: row for row in current_open}
    new_ids = {
        feature["id"] for feature in features.values()
    }
    if set(current_by_entity) - set(previous_by_entity) != new_ids:
        raise ExactIdentityDecisionError("identity v12 exact new-record inventory differs")
    if set(previous_by_entity) - set(current_by_entity):
        raise ExactIdentityDecisionError("identity v12 dropped a v11 source record")

    dependent = {"component_id", "occurrence_id", "release_id"}
    ordered_old_ids = [
        row["entity_id"] for row in current_open if row["entity_id"] not in new_ids
    ]
    if ordered_old_ids != [row["entity_id"] for row in previous_open]:
        raise ExactIdentityDecisionError("identity v11 replaced-record order changed")
    for entity_id, old in previous_by_entity.items():
        new = current_by_entity[entity_id]
        if (
            {key: value for key, value in new.items() if key not in dependent}
            != {key: value for key, value in old.items() if key not in dependent}
            or new["occurrence_id"] != _replace_occurrence(old["occurrence_id"])
            or new["component_id"]
            != legacy._component_id(new["entity_kind"], [new["occurrence_id"]])
        ):
            raise ExactIdentityDecisionError(
                f"identity v11 source-record decision changed: {entity_id}"
            )

    unaffected_previous = [
        row for row in previous if row["release_id"] != OLD_RELEASE_ID
    ]
    unaffected_current = [row for row in current if row["release_id"] != NEW_RELEASE_ID]
    if unaffected_current != unaffected_previous:
        raise ExactIdentityDecisionError(
            "identity v11 unaffected component bytes or order changed"
        )

    component_for: dict[str, str] = {}
    for key, feature in features.items():
        row = current_by_entity[feature["id"]]
        expected_occurrence = f"{NEW_RELEASE_ID}:{feature['id']}"
        if (
            row["stable_key"] != key
            or row["occurrence_id"] != expected_occurrence
            or row["component_id"]
            != legacy._component_id(row["entity_kind"], [expected_occurrence])
            or row["component_member_count"] != "1"
            or row["identity_proof_parent_occurrence_id"]
            or row["identity_proof_token"]
            or row["typed_identity_tokens_json"] != "[]"
            or row["ambiguous_identity_tokens_json"] != "[]"
        ):
            raise ExactIdentityDecisionError(f"new singleton decision differs: {key}")
        component_for[key] = row["component_id"]
    if len(set(component_for.values())) != 6:
        raise ExactIdentityDecisionError("identity v12 merged a new source record")
    return component_for


def _validate_relationship_delta(bundle: Path, components: Mapping[str, str]) -> None:
    previous = _csv_rows(PREDECESSOR_BUNDLE / RELATIONSHIPS_FILENAME)
    current = _csv_rows(bundle / RELATIONSHIPS_FILENAME)
    new_release_json = json.dumps([NEW_RELEASE_ID], separators=(",", ":"))
    old_release_json = json.dumps([OLD_RELEASE_ID], separators=(",", ":"))

    expected_new = []
    for subject_key, object_key in EXPECTED_TARGETS.items():
        subject = components[subject_key]
        object_ = components[object_key]
        expected_new.append(
            {
                "relationship_id": legacy._relationship_id(
                    "project_targets", subject, object_
                ),
                "relationship_type": "project_targets",
                "subject_component_id": subject,
                "subject_kind": "project",
                "object_component_id": object_,
                "object_kind": "campus",
                "decision_basis": "explicit_parent",
                "typed_identity_tokens_json": "[]",
                "source_release_ids_json": new_release_json,
                "raw_relationship_count": "1",
            }
        )
    expected_new.sort(key=lambda row: row["relationship_id"])
    expected_new_ids = {row["relationship_id"] for row in expected_new}
    actual_new = [row for row in current if row["relationship_id"] in expected_new_ids]
    if actual_new != expected_new:
        raise ExactIdentityDecisionError("identity v12 explicit campus decisions differ")

    previous_components = {
        row["component_id"]: row
        for row in _csv_rows(PREDECESSOR_BUNDLE / COMPONENTS_FILENAME)
        if row["release_id"] == OLD_RELEASE_ID
    }
    current_components = {
        row["entity_id"]: row["component_id"]
        for row in _csv_rows(bundle / COMPONENTS_FILENAME)
        if row["release_id"] == NEW_RELEASE_ID
    }
    component_replacement = {
        component: current_components[row["entity_id"]]
        for component, row in previous_components.items()
    }
    replaced_previous = [
        row for row in previous if row["source_release_ids_json"] == old_release_json
    ]
    transformed = []
    for old in replaced_previous:
        row = dict(old)
        row["subject_component_id"] = component_replacement[
            old["subject_component_id"]
        ]
        row["object_component_id"] = component_replacement[old["object_component_id"]]
        row["source_release_ids_json"] = new_release_json
        row["relationship_id"] = legacy._relationship_id(
            row["relationship_type"],
            row["subject_component_id"],
            row["object_component_id"],
        )
        transformed.append(row)
    transformed.sort(key=lambda row: row["relationship_id"])
    transformed_ids = {row["relationship_id"] for row in transformed}
    actual_replaced = [
        row
        for row in current
        if row["source_release_ids_json"] == new_release_json
        and row["relationship_id"] not in expected_new_ids
    ]
    if actual_replaced != transformed or len(transformed_ids) != 442:
        raise ExactIdentityDecisionError(
            "identity v11 relationship replacement bytes or order changed"
        )

    unaffected_previous = [
        row for row in previous if row["source_release_ids_json"] != old_release_json
    ]
    unaffected_current = [
        row for row in current if row["source_release_ids_json"] != new_release_json
    ]
    if unaffected_current != unaffected_previous or len(current) - len(previous) != 4:
        raise ExactIdentityDecisionError(
            "identity v11 unaffected relationship bytes or order changed"
        )


def _validate_unresolved_and_lineage_delta(bundle: Path) -> None:
    previous_unresolved = _csv_rows(PREDECESSOR_BUNDLE / UNRESOLVED_FILENAME)
    current_unresolved = _csv_rows(bundle / UNRESOLVED_FILENAME)
    previous_unaffected = [
        row for row in previous_unresolved if row["release_id"] != OLD_RELEASE_ID
    ]
    current_unaffected = [
        row for row in current_unresolved if row["release_id"] != NEW_RELEASE_ID
    ]
    if previous_unaffected != current_unaffected:
        raise ExactIdentityDecisionError("identity v11 unresolved bytes or order changed")
    old_rows = [row for row in previous_unresolved if row["release_id"] == OLD_RELEASE_ID]
    new_rows = [row for row in current_unresolved if row["release_id"] == NEW_RELEASE_ID]
    projection = lambda row: tuple(  # noqa: E731
        (key, value.replace(OLD_RELEASE_ID, NEW_RELEASE_ID))
        for key, value in row.items()
        if key != "candidate_reference_id"
    )
    if len(old_rows) != 9 or sorted(map(projection, old_rows)) != sorted(
        projection(row) for row in new_rows
    ):
        raise ExactIdentityDecisionError("identity v12 candidate replacement differs")

    previous_lineage = _csv_rows(PREDECESSOR_BUNDLE / LINEAGE_FILENAME)
    current_lineage = _csv_rows(bundle / LINEAGE_FILENAME)
    if (
        [row for row in previous_lineage if row["release_id"] != OLD_RELEASE_ID]
        != [row for row in current_lineage if row["release_id"] != NEW_RELEASE_ID]
    ):
        raise ExactIdentityDecisionError("identity v11 lineage bytes or order changed")
    old_by_family = {
        row["source_family"]: row
        for row in previous_lineage
        if row["release_id"] == OLD_RELEASE_ID
    }
    new_by_family = {
        row["source_family"]: row
        for row in current_lineage
        if row["release_id"] == NEW_RELEASE_ID
    }
    if set(new_by_family) - set(old_by_family) != {"riot_platforms_company_news"}:
        raise ExactIdentityDecisionError("identity v12 lineage family delta differs")
    for family, old in old_by_family.items():
        if family == "databank_facility_pages":
            continue
        expected = {**old, "release_id": NEW_RELEASE_ID}
        if new_by_family.get(family) != expected:
            raise ExactIdentityDecisionError(f"identity v11 lineage changed: {family}")
    if new_by_family.get("databank_facility_pages") != {
        "release_id": NEW_RELEASE_ID,
        "source_family": "databank_facility_pages",
        "source_root": "databank_facility_pages",
        "publisher_roots_json": '["databank","databank_holdings_ltd"]',
        "occurrence_count": "6",
        "exact_component_count": "6",
        "derivation_status": "direct_or_unclassified",
        "independence_claim_allowed": "False",
    } or new_by_family.get("riot_platforms_company_news") != {
        "release_id": NEW_RELEASE_ID,
        "source_family": "riot_platforms_company_news",
        "source_root": "riot_platforms_company_news",
        "publisher_roots_json": '["riot_platforms_inc"]',
        "occurrence_count": "3",
        "exact_component_count": "3",
        "derivation_status": "direct_or_unclassified",
        "independence_claim_allowed": "False",
    }:
        raise ExactIdentityDecisionError("identity v12 changed-family lineage differs")


def _validate_decision_delta(bundle: Path) -> None:
    components = _validate_component_delta(bundle)
    _validate_relationship_delta(bundle, components)
    _validate_unresolved_and_lineage_delta(bundle)
    accounting = json.loads((bundle / ACCOUNTING_FILENAME).read_text())
    predecessor = json.loads(
        (PREDECESSOR_BUNDLE / ACCOUNTING_FILENAME).read_text()
    )
    if any(
        accounting[key] - predecessor[key] != delta
        for key, delta in EXPECTED_DELTA.items()
    ):
        raise ExactIdentityDecisionError("identity v12 accounting delta differs")
    if (
        accounting["raw_non_review_occurrences_by_kind"]
        != {"building": 2355, "campus": 621, "facility": 6747, "project": 505}
        or accounting["exact_source_record_components_by_kind"]
        != {"building": 1950, "campus": 621, "facility": 5420, "project": 505}
        or accounting["canonical_topology_links_by_type"]
        != {"facility_contains_building": 1950, "project_targets": 505}
        or any(
            accounting[field] is not None
            for field in (
                "unique_physical_sites",
                "physical_site_lower_bound",
                "physical_site_upper_bound",
            )
        )
    ):
        raise ExactIdentityDecisionError("identity v12 conservative accounting differs")


def _validate_temporal_closure(
    definition_path: Path,
    bundle_path: Path,
    *,
    validation_wall_clock: datetime,
) -> None:
    recorded = _parsed_timestamp(RECORDED_AT, "identity v12 recorded_at")
    if recorded > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v12 recorded_at exceeds validation wall clock"
        )
    for path in (definition_path, bundle_path, *bundle_path.rglob("*")):
        _path_timestamp_bounds(path, recorded, f"identity v12 artifact {path.name}")

    lineage = (
        (
            PREDECESSOR_DEFINITION,
            PREDECESSOR_BUNDLE,
            PREDECESSOR_RECORDED_AT,
            "identity v11",
        ),
        (V87_DEFINITION, V87_RELEASE, V87_RECORDED_AT, "open-seed v87"),
        (
            FEDERATION_DEFINITION,
            FEDERATION_BUNDLE,
            FEDERATION_RECORDED_AT,
            "federation v36",
        ),
    )
    previous_time = None
    for definition, directory, timestamp, label in lineage:
        cutoff = _parsed_timestamp(timestamp, f"{label} timestamp")
        if cutoff >= recorded or (previous_time is not None and cutoff <= previous_time):
            raise ExactIdentityDecisionError("identity v12 temporal lineage order differs")
        previous_time = cutoff
        for path in (definition, directory, *directory.rglob("*")):
            _path_timestamp_bounds(path, cutoff, f"{label} artifact {path.name}")
        _final_root_ctime(definition, cutoff, validation_wall_clock, f"{label} definition")
        _final_root_ctime(directory, cutoff, validation_wall_clock, f"{label} bundle")

    if (
        definition_path.absolute() == DEFINITION.absolute()
        and bundle_path.absolute() == BUNDLE.absolute()
    ):
        _final_root_ctime(
            definition_path, recorded, validation_wall_clock, "identity v12 definition"
        )
        _final_root_ctime(
            bundle_path, recorded, validation_wall_clock, "identity v12 bundle"
        )


def validate_exact_identity_decision_bundle(
    path_value: str | Path = BUNDLE,
    *,
    definition_path: str | Path = DEFINITION,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate v12 with exact lineage, inventory, and two offline replays."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v12 requires exactly two offline reconstructions"
        )
    wall_clock = _wall_clock(validation_wall_clock)
    guard = _require_guard_state()
    definition_file = Path(definition_path)
    document, raw = _regular_document(definition_file, "identity v12 definition")
    definition = _definition_object(document, raw, logical_path=definition_file)
    bundle = Path(path_value)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError("identity v12 bundle must be a regular directory")
    _validate_temporal_closure(
        definition_file, bundle, validation_wall_clock=wall_clock
    )

    manifest = carrier.validate_exact_identity_decision_bundle(
        bundle, require_frozen=require_frozen
    )
    first_payloads, first_manifest = carrier._prepare_bundle(definition)
    second_payloads, second_manifest = carrier._prepare_bundle(definition)
    if first_payloads != second_payloads or first_manifest != second_manifest:
        raise ExactIdentityDecisionError(
            "identity v12 inputs changed or two offline reconstructions differ"
        )
    actual_payloads = {entry.name: entry.read_bytes() for entry in bundle.iterdir()}
    if manifest != first_manifest or actual_payloads != first_payloads:
        raise ExactIdentityDecisionError("identity v12 bundle differs from replay")
    if manifest.get("bundle_id") != BUNDLE_ID or manifest.get("counts") is None:
        raise ExactIdentityDecisionError("identity v12 manifest identity differs")
    if any(manifest["counts"].get(key) != value for key, value in EXPECTED_COUNTS.items()):
        raise ExactIdentityDecisionError("identity v12 manifest counts differ")
    if manifest.get("scope") != POLICY:
        raise ExactIdentityDecisionError("identity v12 policy differs")
    _validate_decision_delta(bundle)
    _assert_forbidden_lineage_absent({definition_file.name: raw, **actual_payloads})

    if definition_file.absolute() == DEFINITION.absolute() and bundle.absolute() == BUNDLE.absolute():
        _validate_file(DEFINITION, DEFINITION_PIN, mode=0o444)
        if (
            stat.S_IMODE(BUNDLE.stat().st_mode) != 0o555
            or tree_digest(BUNDLE) != BUNDLE_TREE_SHA256
            or set(ARTIFACT_PINS) != {entry.name for entry in BUNDLE.iterdir()}
        ):
            raise ExactIdentityDecisionError("identity v12 frozen tree differs")
        for name, pin in ARTIFACT_PINS.items():
            _validate_file(BUNDLE / name, pin, mode=0o444)
    if _guard_state() != guard:
        raise ExactIdentityDecisionError("identity v12 validation mutated inputs")
    return manifest


def _wait_until_recorded() -> None:
    target = _parsed_timestamp(RECORDED_AT, "identity v12 recorded_at").timestamp()
    while time.time() < target:
        time.sleep(min(0.25, target - time.time()))


def _max_stage_time(paths: tuple[Path, ...]) -> float:
    values = []
    for root in paths:
        members = (root, *root.rglob("*")) if root.is_dir() else (root,)
        for path in members:
            status = path.stat()
            values.append(status.st_mtime)
            birth = getattr(status, "st_birthtime", None)
            if birth is not None:
                values.append(birth)
    return max(values)


def _discard_private_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    for entry in sorted(stage.rglob("*"), reverse=True):
        if entry.is_symlink():
            raise ExactIdentityDecisionError(
                "refusing contaminated identity-v12 stage cleanup"
            )
        entry.chmod(0o700 if entry.is_dir() else 0o600)
    stage.chmod(0o700)
    shutil.rmtree(stage)


@contextmanager
def publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise ExactIdentityDecisionError(
            f"active identity-v12 publication lock exists: {PUBLICATION_LOCK}"
        ) from error
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


def _require_unpublished() -> None:
    for path in (DEFINITION, BUNDLE):
        if path.exists() or path.is_symlink():
            raise ExactIdentityDecisionError(
                f"identity v12 final path already exists; refusing replacement: {path}"
            )


def _require_output_parents() -> None:
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir() or not os.access(
            parent, os.W_OK | os.X_OK
        ):
            raise ExactIdentityDecisionError(
                f"identity v12 output parent is invalid: {parent}"
            )


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise ExactIdentityDecisionError("identity v12 rollback destination is occupied")
    BUNDLE.chmod(0o755)
    try:
        federation._promote_noreplace(BUNDLE, staged_bundle)
    except federation.FederatedReleaseError as error:
        raise ExactIdentityDecisionError(
            f"identity v12 bundle rollback failed: {error}"
        ) from error
    staged_bundle.chmod(0o555)


def _rollback_definition(staged_definition: Path) -> None:
    if staged_definition.exists() or staged_definition.is_symlink():
        raise ExactIdentityDecisionError(
            "identity v12 definition rollback destination is occupied"
        )
    try:
        federation._promote_noreplace(DEFINITION, staged_definition)
    except federation.FederatedReleaseError as error:
        raise ExactIdentityDecisionError(
            f"identity v12 definition rollback failed: {error}"
        ) from error


def write_exact_identity_decision_bundle() -> dict[str, Any]:
    """Stage, double-replay, freeze, and no-replace publish identity v12."""

    _require_unpublished()
    if _parsed_timestamp(RECORDED_AT, "identity v12 recorded_at") <= datetime.now(
        timezone.utc
    ):
        raise ExactIdentityDecisionError(
            "identity v12 recorded_at must be future before staging"
        )
    with publication_lock():
        guard = _require_guard_state()
        _require_unpublished()
        _require_output_parents()
        stage_root = Path(
            tempfile.mkdtemp(prefix=".identity-v12-private-stage-", dir=ROOT)
        )
        stage_root.chmod(0o700)
        definition_stage = stage_root / DEFINITION.name
        bundle_stage = stage_root / BUNDLE.name
        bundle_stage.mkdir(mode=0o700)
        published_definition = False
        published_bundle = False
        try:
            document = _v12_document()
            raw = _canonical_json(document)
            definition = _definition_object(document, raw)
            first_payloads, first_manifest = carrier._prepare_bundle(definition)
            second_payloads, second_manifest = carrier._prepare_bundle(definition)
            if first_payloads != second_payloads or first_manifest != second_manifest:
                raise ExactIdentityDecisionError(
                    "identity v12 inputs changed or two offline reconstructions differ"
                )
            _assert_forbidden_lineage_absent({DEFINITION.name: raw, **first_payloads})
            if (len(raw), hashlib.sha256(raw).hexdigest()) != DEFINITION_PIN:
                raise ExactIdentityDecisionError("identity v12 definition pin differs")

            with definition_stage.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            for name, payload in first_payloads.items():
                with (bundle_stage / name).open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
            legacy._fsync_directory(bundle_stage)
            definition_stage.chmod(0o444)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o555)
            legacy._fsync_directory(bundle_stage)
            if (
                tree_digest(bundle_stage) != BUNDLE_TREE_SHA256
                or any(
                    (entry.stat().st_size, _sha256(entry))
                    != ARTIFACT_PINS[entry.name]
                    for entry in bundle_stage.iterdir()
                )
            ):
                raise ExactIdentityDecisionError("identity v12 private stage pins differ")
            _validate_decision_delta(bundle_stage)

            target = _parsed_timestamp(
                RECORDED_AT, "identity v12 recorded_at"
            ).timestamp()
            if _max_stage_time((definition_stage, bundle_stage)) > target + 0.000_001:
                raise ExactIdentityDecisionError(
                    "identity v12 staging exceeded publication timestamp"
                )
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = tree_digest(bundle_stage)
            _wait_until_recorded()
            validate_exact_identity_decision_bundle(
                bundle_stage,
                definition_path=definition_stage,
                validation_wall_clock=datetime.now(timezone.utc),
            )
            if (
                definition_stage.read_bytes() != frozen_definition
                or tree_digest(bundle_stage) != frozen_tree
                or _guard_state() != guard
            ):
                raise ExactIdentityDecisionError(
                    "identity v12 stage or inputs changed while waiting"
                )
            _require_unpublished()
            _require_output_parents()

            bundle_stage.chmod(0o755)
            try:
                federation._promote_noreplace(bundle_stage, BUNDLE)
            except federation.FederatedReleaseError as error:
                raise ExactIdentityDecisionError(str(error)) from error
            published_bundle = True
            BUNDLE.chmod(0o555)
            try:
                federation._promote_noreplace(definition_stage, DEFINITION)
                published_definition = True
            except BaseException as error:
                try:
                    _rollback_bundle(bundle_stage)
                    published_bundle = False
                except Exception as rollback_error:
                    error.add_note(
                        f"identity v12 bundle rollback failed: {rollback_error}"
                    )
                raise
            try:
                result = validate_exact_identity_decision_bundle()
            except BaseException as error:
                rollback_errors = []
                if published_definition:
                    try:
                        _rollback_definition(definition_stage)
                        published_definition = False
                    except Exception as rollback_error:
                        rollback_errors.append(
                            f"identity v12 definition rollback failed: {rollback_error}"
                        )
                if published_bundle:
                    try:
                        _rollback_bundle(bundle_stage)
                        published_bundle = False
                    except Exception as rollback_error:
                        rollback_errors.append(
                            f"identity v12 bundle rollback failed: {rollback_error}"
                        )
                for note in rollback_errors:
                    error.add_note(note)
                raise
        finally:
            if not published_definition and definition_stage.exists():
                definition_stage.chmod(0o600)
                definition_stage.unlink()
            if not published_bundle and bundle_stage.exists():
                bundle_stage.chmod(0o700)
                for entry in bundle_stage.iterdir():
                    entry.chmod(0o600)
                shutil.rmtree(bundle_stage)
            if stage_root.exists():
                stage_root.rmdir()
        if _guard_state() != guard:
            raise ExactIdentityDecisionError("identity v12 publication mutated inputs")
        return result


build_exact_identity_decision_bundle = write_exact_identity_decision_bundle


__all__ = [
    "ACCOUNTING_FILENAME",
    "BUNDLE",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT",
    "BUNDLE_ID",
    "COMPONENTS_FILENAME",
    "DEFINITION",
    "DEFINITION_FORMAT",
    "EXPECTED_COUNTS",
    "EXPECTED_DELTA",
    "ExactIdentityDecisionError",
    "FEDERATION_BUNDLE",
    "FEDERATION_DEFINITION",
    "LINEAGE_FILENAME",
    "POLICY",
    "RECORDED_AT",
    "REJECTED_LINEAGE_TOKENS",
    "RELATIONSHIPS_FILENAME",
    "SUPERSEDED_LINEAGE_TOKENS",
    "UNRESOLVED_FILENAME",
    "build_exact_identity_decision_bundle",
    "validate_exact_identity_decision_bundle",
    "write_exact_identity_decision_bundle",
]
