"""Publish exact-identity v13 over accepted v12 and federation v37.

Open-seed v92 replaces v87.  The 55 source-scoped records admitted by v88
through v92 remain 55 singleton exact components and retain 29 explicit
project-to-campus edges.  No candidate, cross-source merge, review-only row,
physical-site count, coordinate, or inferred claim is admitted here.
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
from . import exact_identity_decisions_carrier_v5 as carrier
from . import exact_identity_decisions_v12 as accepted_v12
from . import federated_release_v5 as federation
from . import federation_v37
from . import open_seed_v88 as v88
from . import open_seed_v89 as v89
from . import open_seed_v90 as v90
from . import open_seed_v91 as v91
from . import open_seed_v92 as v92
from .open_seed_v56 import tree_digest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = "2026-07-21-public-open-v13"
RECORDED_AT = "2026-07-22T03:00:00Z"
DEFINITION = ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v13.json"
BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v13"
PUBLICATION_LOCK = ROOT / ".exact-identity-v13.lock"

PREDECESSOR_DEFINITION = accepted_v12.DEFINITION
PREDECESSOR_BUNDLE = accepted_v12.BUNDLE
PREDECESSOR_RECORDED_AT = accepted_v12.RECORDED_AT
PREDECESSOR_DEFINITION_PIN = (
    1_736,
    "18a6717fb01b7db1f1b9424d3cb03d7628dc3b4b8b06979c8e7c0088010ac0c2",
)
PREDECESSOR_ACCOUNTING_PIN = (
    981,
    "576ae85628bbca5a8f43fe4382833a4336ab7d5f802dac38aea0d6f794d86a19",
)
PREDECESSOR_MANIFEST_PIN = (
    11_441,
    "2bb6c2699b53aa3f4e3a1e6cb966985e45419bdfd28fbef866745a3000f431a4",
)
PREDECESSOR_TREE_SHA256 = (
    "c045070811263c471d8b993f6712608412addf17e24cb68b243a83a0d0ba4891"
)

FEDERATION_DEFINITION = federation_v37.DEFINITION
FEDERATION_BUNDLE = federation_v37.INDEX_DIR
FEDERATION_RECORDED_AT = federation_v37.GENERATED_AT
FEDERATION_DEFINITION_PIN = federation_v37.DEFINITION_PIN
FEDERATION_INDEX_PIN = federation_v37.INDEX_PIN
FEDERATION_MANIFEST_PIN = federation_v37.MANIFEST_PIN
FEDERATION_SIDECAR_PIN = federation_v37.SIDECAR_PIN
FEDERATION_TREE_SHA256 = federation_v37.TREE_SHA256

V92_DEFINITION = v92.DEFINITION
V92_RELEASE = v92.RELEASE
V92_RECORDED_AT = federation_v37.V92_RECORDED_AT
V92_DEFINITION_PIN = federation_v37.V92_DEFINITION_PIN
V92_MANIFEST_PIN = federation_v37.V92_MANIFEST_PIN
V92_TREE_SHA256 = federation_v37.V92_TREE_SHA256

OLD_RELEASE_ID = federation_v37.OLD_RELEASE_ID
NEW_RELEASE_ID = federation_v37.NEW_RELEASE_ID

EXPECTED_COUNTS = {
    "ambiguous_identity_candidate_references": 127,
    "canonical_topology_links": 2484,
    "exact_component_reductions": 1732,
    "exact_source_record_components": 8551,
    "non_review_source_scoped_entity_records": 10283,
    "raw_topology_links": 2889,
    "release_candidate_references": 100414,
    "review_only_source_scoped_entity_records": 6130,
    "source_scoped_entity_records": 16413,
    "unresolved_candidate_references": 100541,
}
EXPECTED_DELTA = {
    "ambiguous_identity_candidate_references": 0,
    "canonical_topology_links": 29,
    "exact_component_reductions": 0,
    "exact_source_record_components": 55,
    "non_review_source_scoped_entity_records": 55,
    "raw_topology_links": 29,
    "release_candidate_references": 0,
    "review_only_source_scoped_entity_records": 0,
    "source_scoped_entity_records": 55,
    "unresolved_candidate_references": 0,
}

RELEASE_DELTAS = {
    "v88": (8, 5),
    "v89": (18, 9),
    "v90": (14, 7),
    "v91": (5, 3),
    "v92": (10, 5),
}
RELEASE_MODULES = {"v88": v88, "v89": v89, "v90": v90, "v91": v91, "v92": v92}
NEW_ENTITY_KEYS = frozenset(
    key for module in RELEASE_MODULES.values() for key in module.ADDED_ENTITY_KEYS
)
NEW_PROJECT_KEYS = frozenset(
    key for module in RELEASE_MODULES.values() for key in module.ADDED_PROJECT_KEYS
)
RELEASE_INPUT_PINS = {
    "v88": {
        "definition": (
            104_159,
            "7267e71dc26581eb8f62bf11525475c3ccc732494c4cca0cea58c0f30b0232da",
        ),
        "manifest": (
            15_706,
            "63bdeac96b5f3cebac092a63cff40de2d928d0643d42fe5b041fd649fc9955e0",
        ),
        "tree": "aae34cbd2b8111a498ef529b08d0be6937c837b70025bdba6c097735b606073e",
    },
    "v89": {
        "definition": (
            105_962,
            "1c9be663976b1b5e93f31868df73f76e66498f14ef9eff157baefb8144b8289b",
        ),
        "manifest": (
            15_707,
            "07f2f521f365b4427c08a7393f72977a68137aa87f9ea015ccf480cac455f9b2",
        ),
        "tree": "83b721b2066c3be6cbf3cf3bfb255abb8ed4427ad5ebd17da8dcc5214551fdad",
    },
    "v90": {
        "definition": (
            107_554,
            "3e224d0560e7f82fc31f7bdf6eb6b723ce50ad8423e2296de8c509b75c0fbdda",
        ),
        "manifest": (
            15_902,
            "40be71c613c74e4e843c5c60ad85ce172c206f72350df5a0996b7e971ca54b66",
        ),
        "tree": "18cda7d054789dde956a393959cde79349f835927b1e757da364e15d974b78f3",
    },
    "v91": {
        "definition": (
            108_188,
            "e1a1c657c88468233dc72e66012ec1f56afd69a599f129c5fcc64f20bdf3038a",
        ),
        "manifest": (
            15_954,
            "8be929e9f24b0bb1d11a318cfd67d8c4e538f2979db9468ecd359cb36afb45f9",
        ),
        "tree": "9c89ab93baf5a13965db764a376affe231186df6a5cbc2758fd9ad95a85a5a5e",
    },
    "v92": {
        "definition": V92_DEFINITION_PIN,
        "manifest": V92_MANIFEST_PIN,
        "tree": V92_TREE_SHA256,
    },
}

DEFINITION_PIN = (
    1_736,
    "a79d341f7f2512eed99f96068e32db1c4c7ebf667e75c35299edf4eea713b221",
)
ARTIFACT_PINS = {
    "ATTRIBUTION.txt": (
        8_696,
        "69368d6ba32da7578c0b7cc4300b14cb8ba6418d8f5bcc05f80998f1a1ebf078",
    ),
    "README.md": (
        629,
        "c36253c2f3afad302ebda15d84b64a5dab983c8a6e1a669a2d93b43ae6c1d404",
    ),
    "accounting.json": (
        981,
        "3e82b6acff2f167a95ec5ad41977d764d3cf7b921809e7ccc64a9c6eeb940c84",
    ),
    "component-members.csv": (
        3_728_850,
        "12e78dbec659100ef6f684e140de58714d6ed76e677f90db9fd42da339e89948",
    ),
    "manifest.json": (
        11_443,
        "0ac852f7898b20089739a6c10fa35dc2e42f096e070477c9aa54adf2038409a4",
    ),
    "manifest.sha256": (
        80,
        "c74bcb307869c6fc4e3aafec479e4dd53a4b4212431c55dc5c7d203399f84d44",
    ),
    "relationships.csv": (
        957_162,
        "ec7d19b34c976389f4b87722bf41fc436f03e23f2b7f641f9433f2ebcc252ce4",
    ),
    "source-lineage.csv": (
        47_234,
        "984f9872b9218d4822952325c8c864708c437b4707f4afce8f17548254371059",
    ),
    "unresolved-candidate-references.csv": (
        38_421_688,
        "8a47549da640ec0a59fd8220a259de6af7631b95af0b6b305f17c09dd63d5b52",
    ),
}
BUNDLE_TREE_SHA256 = (
    "a1f75c07ee0446d4bbdf211798ea1e632c2d9fa3bc2188a0ac54af93119e041f"
)

REJECTED_LINEAGE_TOKENS = accepted_v12.REJECTED_LINEAGE_TOKENS
SUPERSEDED_LINEAGE_TOKENS = (
    *accepted_v12.SUPERSEDED_LINEAGE_TOKENS,
    b"2026-07-21-public-open-v36",
    b"epoch-official-open-seed-v87",
    b"2026-07-21-open-seed-v87",
    b"2026-07-21-public-open-v12",
)
PEERINGDB_FORBIDDEN = b"peeringdb"

CODE_PINS = {
    "exact_identity_decisions.py": (
        76_330,
        "8c5d7fd14575d7f6afdb280144868534c9934753e96658498200a15833ccdfe1",
    ),
    "exact_identity_decisions_carrier_v5.py": (
        21_401,
        "6d99281d256d1fb33b256794c151a52bc9515a1b2398ca4b57b1434537b3698b",
    ),
    "exact_identity_decisions_v12.py": (
        44_190,
        "200ece35ac1c66ae3c29de851ec083fded6b6b65359d36d69567d4d65dc698ed",
    ),
    "federated_release_v3.py": (
        26_524,
        "e8504ca3bba1f201085579df20ec0cde4ebd700284e402f5104b656dd7c24528",
    ),
    "federated_release_v4.py": (
        17_669,
        "af10b118a5941b7d9b021bb7301d58082ac738160afc9a6dc1101213192f516a",
    ),
    "federated_release_v5.py": (
        13_330,
        "b2984555b053d0de64cac0e747fcec02e5ee133983ccf23a44f369e897b1f851",
    ),
    "federation_v37.py": (
        34_145,
        "0d0d12db15603262d90865bf0546c0e772f1e7b1310ca778e4bc34ea2d56c918",
    ),
    "global_snapshot.py": (
        25_282,
        "10eb78e03335b097ad4d43ecda97ef9f109e57217fee3117e6bc6fac630ecef0",
    ),
    "open_seed_v56.py": (
        25_343,
        "3349ba9ef81dfdbaba07e0c8b5b5e83642aed93442ca0aaf0dcdcc0b406a4f1c",
    ),
    "open_seed_v88.py": (
        51_579,
        "9c2494cf18ac4043093e4958086292063dc09169c1d2cc6c56931ac977065d1d",
    ),
    "open_seed_v89.py": (
        48_914,
        "feb320a1345f114a67ca2f083b9ef20bd9a1e7d3af727e60c25671cbecd132e8",
    ),
    "open_seed_v90.py": (
        48_981,
        "e462230948288519524f84b5a278be9c4fdaa52b672ca4949a6b01cc866087e1",
    ),
    "open_seed_v91.py": (
        49_982,
        "b1fc8dcfa3dabefd97ea599a6c9caa2e32dcecbf0970b81031320ee3c8f77884",
    ),
    "open_seed_v92.py": (
        69_392,
        "93a3ba71eac30f455a5d5258096b236e3078c4ec75400e141f6e6b1803c56b7a",
    ),
}

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

_canonical_json = accepted_v12._canonical_json
_wall_clock = accepted_v12._wall_clock
_parsed_timestamp = accepted_v12._parsed_timestamp
_regular_document = accepted_v12._regular_document
_path_timestamp_bounds = accepted_v12._path_timestamp_bounds
_final_root_ctime = accepted_v12._final_root_ctime


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
    result: dict[str, tuple[int, str] | str] = {
        "predecessor_definition": (
            PREDECESSOR_DEFINITION.stat().st_size,
            _sha256(PREDECESSOR_DEFINITION),
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
        "federation_sidecar": (
            (FEDERATION_BUNDLE / MANIFEST_HASH_FILENAME).stat().st_size,
            _sha256(FEDERATION_BUNDLE / MANIFEST_HASH_FILENAME),
        ),
        "federation_tree": tree_digest(FEDERATION_BUNDLE),
        "v92_definition": (V92_DEFINITION.stat().st_size, _sha256(V92_DEFINITION)),
        "v92_manifest": (
            (V92_RELEASE / MANIFEST_FILENAME).stat().st_size,
            _sha256(V92_RELEASE / MANIFEST_FILENAME),
        ),
        "v92_tree": tree_digest(V92_RELEASE),
    }
    for name in accepted_v12.ARTIFACT_PINS:
        path = PREDECESSOR_BUNDLE / name
        result[f"predecessor_artifact:{name}"] = (path.stat().st_size, _sha256(path))
    code_root = ROOT / "datacenter_atlas"
    for name in CODE_PINS:
        path = code_root / name
        result[f"code:{name}"] = (path.stat().st_size, _sha256(path))
    for release, module in RELEASE_MODULES.items():
        result[f"release:{release}:definition"] = (
            module.DEFINITION.stat().st_size,
            _sha256(module.DEFINITION),
        )
        manifest = module.RELEASE / MANIFEST_FILENAME
        result[f"release:{release}:manifest"] = (
            manifest.stat().st_size,
            _sha256(manifest),
        )
        result[f"release:{release}:tree"] = tree_digest(module.RELEASE)
        for relative in module.ADDITION_PINS:
            source = ROOT / relative
            result[f"release:{release}:source:{relative}"] = (
                source.stat().st_size,
                _sha256(source),
            )
    return result


def _require_guard_state() -> dict[str, tuple[int, str] | str]:
    try:
        accepted_v12.validate_exact_identity_decision_bundle()
        federation_v37.validate_federation_v37()
        v92.validate_open_seed_v92()
    except (
        OSError,
        ExactIdentityDecisionError,
        federation_v37.FederationV37Error,
        v92.OpenSeedV92Error,
    ) as error:
        raise ExactIdentityDecisionError(
            f"accepted identity-v13 input validation failed: {error}"
        ) from error
    expected: dict[str, tuple[int, str] | str] = {
        "predecessor_definition": PREDECESSOR_DEFINITION_PIN,
        "predecessor_tree": PREDECESSOR_TREE_SHA256,
        "federation_definition": FEDERATION_DEFINITION_PIN,
        "federation_index": FEDERATION_INDEX_PIN,
        "federation_manifest": FEDERATION_MANIFEST_PIN,
        "federation_sidecar": FEDERATION_SIDECAR_PIN,
        "federation_tree": FEDERATION_TREE_SHA256,
        "v92_definition": V92_DEFINITION_PIN,
        "v92_manifest": V92_MANIFEST_PIN,
        "v92_tree": V92_TREE_SHA256,
    }
    expected.update(
        {
            f"predecessor_artifact:{name}": pin
            for name, pin in accepted_v12.ARTIFACT_PINS.items()
        }
    )
    expected.update({f"code:{name}": pin for name, pin in CODE_PINS.items()})
    for release, module in RELEASE_MODULES.items():
        pins = RELEASE_INPUT_PINS[release]
        expected[f"release:{release}:definition"] = pins["definition"]
        expected[f"release:{release}:manifest"] = pins["manifest"]
        expected[f"release:{release}:tree"] = pins["tree"]
        expected.update(
            {
                f"release:{release}:source:{relative}": pin
                for relative, pin in module.ADDITION_PINS.items()
            }
        )
    actual = _guard_state()
    if actual != expected:
        differing = sorted(key for key in expected if actual.get(key) != expected[key])
        raise ExactIdentityDecisionError(
            "accepted identity-v13 input pin drift: " + ", ".join(differing)
        )
    return actual


def _v13_document(recorded_at: str = RECORDED_AT) -> dict[str, Any]:
    if recorded_at != RECORDED_AT:
        raise ExactIdentityDecisionError("identity v13 recorded_at is fixed")
    predecessor, _ = _regular_document(
        PREDECESSOR_DEFINITION, "accepted identity v12 definition"
    )
    result = deepcopy(predecessor)
    result["bundle_id"] = BUNDLE_ID
    result["recorded_at"] = RECORDED_AT
    result["federation"] = {
        "expected_index_sha256": FEDERATION_INDEX_PIN[1],
        "expected_manifest_sha256": FEDERATION_MANIFEST_PIN[1],
        "index_path": "../federated_indexes/2026-07-21-public-open-v37",
    }
    old_children = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(old_children) != 1:
        raise ExactIdentityDecisionError("accepted identity v12 seed child changed")
    old_children[0].update(
        {
            "expected_manifest_sha256": V92_MANIFEST_PIN[1],
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v92",
        }
    )
    result["expected"] = dict(EXPECTED_COUNTS)
    return result


def _assert_forbidden_lineage_absent(payloads: Mapping[str, bytes]) -> None:
    for name, raw in payloads.items():
        if PEERINGDB_FORBIDDEN in raw.lower():
            raise ExactIdentityDecisionError(
                f"PeeringDB is forbidden from identity v13 {name}"
            )
        for token in (*REJECTED_LINEAGE_TOKENS, *SUPERSEDED_LINEAGE_TOKENS):
            if token in raw:
                raise ExactIdentityDecisionError(
                    f"forbidden lineage token in identity v13 {name}: "
                    f"{token.decode('ascii')}"
                )


def _definition_object(
    document: Mapping[str, Any], raw: bytes, *, logical_path: Path = DEFINITION
) -> legacy._Definition:
    expected = _v13_document(RECORDED_AT)
    if document != expected or raw != _canonical_json(expected):
        raise ExactIdentityDecisionError(
            "identity v13 definition is not the exact v12 structural successor"
        )
    _assert_forbidden_lineage_absent({logical_path.name: raw})
    children = []
    for child in document["children"]:
        relative = Path(child["release_path"])
        if relative.is_absolute():
            raise ExactIdentityDecisionError("identity v13 child path must be relative")
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
        raise ExactIdentityDecisionError("v12 occurrence replacement scope differs")
    return f"{NEW_RELEASE_ID}:{value.removeprefix(prefix)}"


def _child_feature_inventory() -> tuple[
    dict[str, dict[str, Any]], dict[str, str], dict[str, str]
]:
    if (
        len(NEW_ENTITY_KEYS) != 55
        or len(NEW_PROJECT_KEYS) != 29
        or sum(len(module.ADDED_ENTITY_KEYS) for module in RELEASE_MODULES.values())
        != 55
    ):
        raise ExactIdentityDecisionError("v88-v92 admitted-key sets overlap or differ")
    release_for = {
        key: name
        for name, module in RELEASE_MODULES.items()
        for key in module.ADDED_ENTITY_KEYS
    }
    for name, module in RELEASE_MODULES.items():
        expected_entities, expected_projects = RELEASE_DELTAS[name]
        if (
            len(module.ADDED_ENTITY_KEYS) != expected_entities
            or len(module.ADDED_PROJECT_KEYS) != expected_projects
        ):
            raise ExactIdentityDecisionError(f"{name} governed delta differs")

    old_rows = {
        row["entity_id"]: row
        for row in _csv_rows(v88.BASE_RELEASE / "entities.csv")
    }
    new_rows = {
        row["entity_id"]: row for row in _csv_rows(V92_RELEASE / "entities.csv")
    }
    if len(old_rows) != 933 or len(new_rows) != 988 or set(old_rows) - set(new_rows):
        raise ExactIdentityDecisionError("v92 source-record inventory is not append-only")
    changed = {
        entity_id: {
            field
            for field in old_rows[entity_id]
            if old_rows[entity_id][field] != new_rows[entity_id][field]
        }
        for entity_id in old_rows
        if old_rows[entity_id] != new_rows[entity_id]
    }
    if (
        len(changed) != 1
        or next(iter(changed.values())) != {"capacity_estimates_json"}
        or new_rows[next(iter(changed))]["stable_key"]
        not in federation_v37.V87_MUTATED_ENTITY_KEYS
    ):
        raise ExactIdentityDecisionError("v92 changed an inherited identity field")

    added_ids = set(new_rows) - set(old_rows)
    if (
        len(added_ids) != 55
        or {new_rows[key]["stable_key"] for key in added_ids} != NEW_ENTITY_KEYS
        or any(
            new_rows[key]["latitude"]
            or new_rows[key]["longitude"]
            or new_rows[key]["geometry_json"] not in {"", "null"}
            for key in added_ids
        )
    ):
        raise ExactIdentityDecisionError("v88-v92 identity inventory differs")

    geojson = json.loads((V92_RELEASE / "atlas.geojson").read_text())
    all_features = {row["id"]: row for row in geojson["features"]}
    features = {
        row["properties"]["stable_key"]: row
        for row in geojson["features"]
        if row["properties"]["stable_key"] in NEW_ENTITY_KEYS
    }
    if len(all_features) != 988 or set(features) != NEW_ENTITY_KEYS:
        raise ExactIdentityDecisionError("v92 admitted feature inventory differs")

    targets: dict[str, str] = {}
    for key, feature in features.items():
        properties = feature["properties"]
        csv_row = new_rows[feature["id"]]
        source_witnesses = (
            properties.get("source_family"),
            properties.get("source_url"),
            properties.get("source_publisher"),
            properties.get("snapshot_evidence_id"),
        )
        if (
            feature.get("geometry") is not None
            or properties.get("latitude") is not None
            or properties.get("longitude") is not None
            or not all(isinstance(value, str) and value for value in source_witnesses)
            or csv_row["stable_key"] != key
            or csv_row["entity_kind"] != properties["entity_kind"]
            or csv_row["snapshot_evidence_id"] != properties["snapshot_evidence_id"]
            or csv_row["source_url"] != properties["source_url"]
            or csv_row["source_publisher"] != properties["source_publisher"]
        ):
            raise ExactIdentityDecisionError(f"source-key evidence differs: {key}")
        target_id = properties.get("target_entity_id")
        if key in NEW_PROJECT_KEYS:
            if (
                properties["entity_kind"] != "project"
                or not isinstance(target_id, str)
                or target_id not in all_features
                or all_features[target_id]["properties"]["entity_kind"] != "campus"
            ):
                raise ExactIdentityDecisionError(f"explicit target differs: {key}")
            targets[key] = all_features[target_id]["properties"]["stable_key"]
        elif properties["entity_kind"] != "campus" or target_id is not None:
            raise ExactIdentityDecisionError(f"admitted entity kind differs: {key}")
    if len(targets) != 29:
        raise ExactIdentityDecisionError("v88-v92 explicit-target count differs")
    if (
        (V92_RELEASE / "resolution_candidates.json").read_bytes()
        != (v88.BASE_RELEASE / "resolution_candidates.json").read_bytes()
    ):
        raise ExactIdentityDecisionError("v88-v92 introduced an identity candidate")
    return features, targets, release_for


def _validate_component_delta(bundle: Path) -> dict[str, str]:
    features, _, _ = _child_feature_inventory()
    previous = _csv_rows(PREDECESSOR_BUNDLE / COMPONENTS_FILENAME)
    current = _csv_rows(bundle / COMPONENTS_FILENAME)
    previous_open = [row for row in previous if row["release_id"] == OLD_RELEASE_ID]
    current_open = [row for row in current if row["release_id"] == NEW_RELEASE_ID]
    if len(previous_open) != 933 or len(current_open) != 988:
        raise ExactIdentityDecisionError("identity v13 replaced-record count differs")
    previous_by_entity = {row["entity_id"]: row for row in previous_open}
    current_by_entity = {row["entity_id"]: row for row in current_open}
    new_ids = {feature["id"] for feature in features.values()}
    if set(current_by_entity) - set(previous_by_entity) != new_ids:
        raise ExactIdentityDecisionError("identity v13 exact new-record inventory differs")
    if set(previous_by_entity) - set(current_by_entity):
        raise ExactIdentityDecisionError("identity v13 dropped a v12 source record")

    dependent = {"component_id", "occurrence_id", "release_id"}
    ordered_old_ids = [
        row["entity_id"] for row in current_open if row["entity_id"] not in new_ids
    ]
    if ordered_old_ids != [row["entity_id"] for row in previous_open]:
        raise ExactIdentityDecisionError("identity v12 replaced-record order changed")
    for entity_id, old in previous_by_entity.items():
        new = current_by_entity[entity_id]
        if (
            {key: value for key, value in new.items() if key not in dependent}
            != {key: value for key, value in old.items() if key not in dependent}
            or new["occurrence_id"] != _replace_occurrence(old["occurrence_id"])
            or new["component_id"]
            != legacy._component_id(new["entity_kind"], [new["occurrence_id"]])
            or new["component_member_count"] != "1"
        ):
            raise ExactIdentityDecisionError(
                f"identity v12 source-record decision changed: {entity_id}"
            )

    unaffected_previous = [
        row for row in previous if row["release_id"] != OLD_RELEASE_ID
    ]
    unaffected_current = [row for row in current if row["release_id"] != NEW_RELEASE_ID]
    if unaffected_current != unaffected_previous:
        raise ExactIdentityDecisionError(
            "identity v12 unaffected component bytes or order changed"
        )

    component_for: dict[str, str] = {
        row["entity_id"]: row["component_id"] for row in current_open
    }
    for key, feature in features.items():
        row = current_by_entity[feature["id"]]
        expected_occurrence = f"{NEW_RELEASE_ID}:{feature['id']}"
        if (
            row["stable_key"] != key
            or row["source_family"] != feature["properties"]["source_family"]
            or row["snapshot_evidence_id"]
            != feature["properties"]["snapshot_evidence_id"]
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
    if len({component_for[feature["id"]] for feature in features.values()}) != 55:
        raise ExactIdentityDecisionError("identity v13 merged a new source record")
    return component_for


def _validate_relationship_delta(bundle: Path, components: Mapping[str, str]) -> None:
    features, expected_targets, release_for = _child_feature_inventory()
    previous = _csv_rows(PREDECESSOR_BUNDLE / RELATIONSHIPS_FILENAME)
    current = _csv_rows(bundle / RELATIONSHIPS_FILENAME)
    new_release_json = json.dumps([NEW_RELEASE_ID], separators=(",", ":"))
    old_release_json = json.dumps([OLD_RELEASE_ID], separators=(",", ":"))

    expected_new = []
    expected_by_key = {}
    for subject_key, object_key in expected_targets.items():
        subject_feature = features[subject_key]
        subject = components[subject_feature["id"]]
        target_id = subject_feature["properties"]["target_entity_id"]
        object_ = components[target_id]
        if not object_key:
            raise ExactIdentityDecisionError("explicit target stable key is empty")
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
        expected_by_key[subject_key] = expected_new[-1]
    expected_new.sort(key=lambda row: row["relationship_id"])
    expected_new_ids = {row["relationship_id"] for row in expected_new}
    actual_new = [row for row in current if row["relationship_id"] in expected_new_ids]
    if actual_new != expected_new or {
        name: sum(release_for[key] == name for key in expected_by_key)
        for name in RELEASE_DELTAS
    } != {name: delta[1] for name, delta in RELEASE_DELTAS.items()}:
        raise ExactIdentityDecisionError("identity v13 explicit campus decisions differ")

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
    if actual_replaced != transformed or len(transformed_ids) != 446:
        raise ExactIdentityDecisionError(
            "identity v12 relationship replacement bytes or order changed"
        )

    unaffected_previous = [
        row for row in previous if row["source_release_ids_json"] != old_release_json
    ]
    unaffected_current = [
        row for row in current if row["source_release_ids_json"] != new_release_json
    ]
    if unaffected_current != unaffected_previous or len(current) - len(previous) != 29:
        raise ExactIdentityDecisionError(
            "identity v12 unaffected relationship bytes or order changed"
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
        raise ExactIdentityDecisionError("identity v12 unresolved bytes or order changed")
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
        raise ExactIdentityDecisionError("identity v13 candidate replacement differs")
    raw_candidates = json.loads(
        (V92_RELEASE / "resolution_candidates.json").read_text(encoding="utf-8")
    )
    expected_candidate_ids = {
        legacy._candidate_id(
            "release-candidate", NEW_RELEASE_ID, legacy._compact_json(row)
        )
        for row in raw_candidates
    }
    if (
        len(new_rows) != 9
        or {row["candidate_reference_id"] for row in new_rows}
        != expected_candidate_ids
    ):
        raise ExactIdentityDecisionError("identity v13 candidate IDs are not exact")

    previous_lineage = _csv_rows(PREDECESSOR_BUNDLE / LINEAGE_FILENAME)
    current_lineage = _csv_rows(bundle / LINEAGE_FILENAME)
    if (
        [row for row in previous_lineage if row["release_id"] != OLD_RELEASE_ID]
        != [row for row in current_lineage if row["release_id"] != NEW_RELEASE_ID]
    ):
        raise ExactIdentityDecisionError("identity v12 lineage bytes or order changed")
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
    current_components = [
        row
        for row in _csv_rows(bundle / COMPONENTS_FILENAME)
        if row["release_id"] == NEW_RELEASE_ID
        and row["stable_key"] in NEW_ENTITY_KEYS
    ]
    added_by_family: dict[str, list[dict[str, str]]] = {}
    for row in current_components:
        added_by_family.setdefault(row["source_family"], []).append(row)
    expected_new_families = set(added_by_family) - set(old_by_family)
    if (
        set(new_by_family) != set(old_by_family) | expected_new_families
        or len(expected_new_families) != 16
    ):
        raise ExactIdentityDecisionError("identity v13 lineage family delta differs")
    for family, row in new_by_family.items():
        increment = len(added_by_family.get(family, ()))
        old = old_by_family.get(family)
        if old is not None:
            expected = {
                **old,
                "release_id": NEW_RELEASE_ID,
                "occurrence_count": str(int(old["occurrence_count"]) + increment),
                "exact_component_count": str(
                    int(old["exact_component_count"]) + increment
                ),
                "publisher_roots_json": row["publisher_roots_json"],
            }
            old_publishers = set(json.loads(old["publisher_roots_json"]))
            new_publishers = set(json.loads(row["publisher_roots_json"]))
            if (
                row != expected
                or not old_publishers <= new_publishers
                or (increment == 0 and new_publishers != old_publishers)
            ):
                raise ExactIdentityDecisionError(f"identity v12 lineage changed: {family}")
            continue
        members = added_by_family.get(family, [])
        if (
            not members
            or row["occurrence_count"] != str(len(members))
            or row["exact_component_count"] != str(len(members))
            or {member["source_root"] for member in members} != {row["source_root"]}
            or not json.loads(row["publisher_roots_json"])
            or row["independence_claim_allowed"] != "False"
        ):
            raise ExactIdentityDecisionError(f"new lineage witness differs: {family}")


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
        raise ExactIdentityDecisionError("identity v13 accounting delta differs")
    if (
        accounting["raw_non_review_occurrences_by_kind"]
        != {"building": 2355, "campus": 647, "facility": 6747, "project": 534}
        or accounting["exact_source_record_components_by_kind"]
        != {"building": 1950, "campus": 647, "facility": 5420, "project": 534}
        or accounting["canonical_topology_links_by_type"]
        != {"facility_contains_building": 1950, "project_targets": 534}
        or any(
            accounting[field] is not None
            for field in (
                "unique_physical_sites",
                "physical_site_lower_bound",
                "physical_site_upper_bound",
            )
        )
    ):
        raise ExactIdentityDecisionError("identity v13 conservative accounting differs")


def _validate_temporal_closure(
    definition_path: Path,
    bundle_path: Path,
    *,
    validation_wall_clock: datetime,
) -> None:
    recorded = _parsed_timestamp(RECORDED_AT, "identity v13 recorded_at")
    if recorded > validation_wall_clock:
        raise ExactIdentityDecisionError(
            "identity v13 recorded_at exceeds validation wall clock"
        )
    for path in (definition_path, bundle_path, *bundle_path.rglob("*")):
        _path_timestamp_bounds(path, recorded, f"identity v13 artifact {path.name}")
        _final_root_ctime(
            path,
            recorded,
            validation_wall_clock,
            f"identity v13 artifact {path.name}",
        )

    lineage = (
        (
            PREDECESSOR_DEFINITION,
            PREDECESSOR_BUNDLE,
            PREDECESSOR_RECORDED_AT,
            "identity v12",
        ),
        (V92_DEFINITION, V92_RELEASE, V92_RECORDED_AT, "open-seed v92"),
        (
            FEDERATION_DEFINITION,
            FEDERATION_BUNDLE,
            FEDERATION_RECORDED_AT,
            "federation v37",
        ),
    )
    previous_time = None
    for definition, directory, timestamp, label in lineage:
        cutoff = _parsed_timestamp(timestamp, f"{label} timestamp")
        if cutoff >= recorded or (previous_time is not None and cutoff <= previous_time):
            raise ExactIdentityDecisionError("identity v13 temporal lineage order differs")
        previous_time = cutoff
        for path in (definition, directory, *directory.rglob("*")):
            _path_timestamp_bounds(path, cutoff, f"{label} artifact {path.name}")
        _final_root_ctime(definition, cutoff, validation_wall_clock, f"{label} definition")
        _final_root_ctime(directory, cutoff, validation_wall_clock, f"{label} bundle")

def validate_exact_identity_decision_bundle(
    path_value: str | Path = BUNDLE,
    *,
    definition_path: str | Path = DEFINITION,
    require_frozen: bool = True,
    replay_count: int = 2,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate v13 with exact lineage, inventory, and two offline replays."""

    if replay_count != 2:
        raise ExactIdentityDecisionError(
            "identity v13 requires exactly two offline reconstructions"
        )
    wall_clock = _wall_clock(validation_wall_clock)
    guard = _require_guard_state()
    definition_file = Path(definition_path)
    document, raw = _regular_document(definition_file, "identity v13 definition")
    definition = _definition_object(document, raw, logical_path=definition_file)
    bundle = Path(path_value)
    if bundle.is_symlink() or not bundle.is_dir():
        raise ExactIdentityDecisionError("identity v13 bundle must be a regular directory")
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
            "identity v13 inputs changed or two offline reconstructions differ"
        )
    actual_payloads = {entry.name: entry.read_bytes() for entry in bundle.iterdir()}
    if manifest != first_manifest or actual_payloads != first_payloads:
        raise ExactIdentityDecisionError("identity v13 bundle differs from replay")
    if manifest.get("bundle_id") != BUNDLE_ID or manifest.get("counts") is None:
        raise ExactIdentityDecisionError("identity v13 manifest identity differs")
    if any(manifest["counts"].get(key) != value for key, value in EXPECTED_COUNTS.items()):
        raise ExactIdentityDecisionError("identity v13 manifest counts differ")
    if manifest.get("scope") != POLICY:
        raise ExactIdentityDecisionError("identity v13 policy differs")
    _validate_decision_delta(bundle)
    _assert_forbidden_lineage_absent({definition_file.name: raw, **actual_payloads})

    if definition_file.absolute() == DEFINITION.absolute() and bundle.absolute() == BUNDLE.absolute():
        _validate_file(DEFINITION, DEFINITION_PIN, mode=0o444)
        if (
            stat.S_IMODE(BUNDLE.stat().st_mode) != 0o555
            or tree_digest(BUNDLE) != BUNDLE_TREE_SHA256
            or set(ARTIFACT_PINS) != {entry.name for entry in BUNDLE.iterdir()}
        ):
            raise ExactIdentityDecisionError("identity v13 frozen tree differs")
        for name, pin in ARTIFACT_PINS.items():
            _validate_file(BUNDLE / name, pin, mode=0o444)
    if _guard_state() != guard:
        raise ExactIdentityDecisionError("identity v13 validation mutated inputs")
    return manifest


def _wait_until_recorded() -> None:
    target = _parsed_timestamp(RECORDED_AT, "identity v13 recorded_at").timestamp()
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


def _stamp_publication_ctimes(definition: Path, bundle: Path) -> None:
    target = _parsed_timestamp(RECORDED_AT, "identity v13 recorded_at")
    if datetime.now(timezone.utc) < target:
        raise ExactIdentityDecisionError(
            "identity v13 cannot stamp ctimes before recorded_at"
        )
    definition.chmod(0o400)
    definition.chmod(0o444)
    bundle.chmod(0o755)
    for member in bundle.iterdir():
        member.chmod(0o400)
        member.chmod(0o444)
    bundle.chmod(0o555)
    for path in (definition, bundle, *bundle.rglob("*")):
        if datetime.fromtimestamp(path.stat().st_ctime, timezone.utc) < target:
            raise ExactIdentityDecisionError(
                f"identity v13 staged ctime predates recorded_at: {path}"
            )


def _discard_private_stage(stage: Path) -> None:
    if not stage.exists() or stage.is_symlink() or not stage.is_dir():
        return
    for entry in sorted(stage.rglob("*"), reverse=True):
        if entry.is_symlink():
            raise ExactIdentityDecisionError(
                "refusing contaminated identity-v13 stage cleanup"
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
            f"active identity-v13 publication lock exists: {PUBLICATION_LOCK}"
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
                f"identity v13 final path already exists; refusing replacement: {path}"
            )


def _require_output_parents() -> None:
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir() or not os.access(
            parent, os.W_OK | os.X_OK
        ):
            raise ExactIdentityDecisionError(
                f"identity v13 output parent is invalid: {parent}"
            )


def _rollback_bundle(staged_bundle: Path) -> None:
    if staged_bundle.exists() or staged_bundle.is_symlink():
        raise ExactIdentityDecisionError("identity v13 rollback destination is occupied")
    BUNDLE.chmod(0o755)
    try:
        federation._promote_noreplace(BUNDLE, staged_bundle)
    except federation.FederatedReleaseError as error:
        raise ExactIdentityDecisionError(
            f"identity v13 bundle rollback failed: {error}"
        ) from error
    staged_bundle.chmod(0o555)


def _rollback_definition(staged_definition: Path) -> None:
    if staged_definition.exists() or staged_definition.is_symlink():
        raise ExactIdentityDecisionError(
            "identity v13 definition rollback destination is occupied"
        )
    try:
        federation._promote_noreplace(DEFINITION, staged_definition)
    except federation.FederatedReleaseError as error:
        raise ExactIdentityDecisionError(
            f"identity v13 definition rollback failed: {error}"
        ) from error


def write_exact_identity_decision_bundle() -> dict[str, Any]:
    """Stage, double-replay, freeze, and no-replace publish identity v13."""

    _require_unpublished()
    if _parsed_timestamp(RECORDED_AT, "identity v13 recorded_at") <= datetime.now(
        timezone.utc
    ):
        raise ExactIdentityDecisionError(
            "identity v13 recorded_at must be future before staging"
        )
    with publication_lock():
        guard = _require_guard_state()
        _require_unpublished()
        _require_output_parents()
        stage_root = Path(
            tempfile.mkdtemp(prefix=".identity-v13-private-stage-", dir=ROOT)
        )
        stage_root.chmod(0o700)
        definition_stage = stage_root / DEFINITION.name
        bundle_stage = stage_root / BUNDLE.name
        bundle_stage.mkdir(mode=0o700)
        published_definition = False
        published_bundle = False
        try:
            document = _v13_document()
            raw = _canonical_json(document)
            definition = _definition_object(document, raw)
            first_payloads, first_manifest = carrier._prepare_bundle(definition)
            second_payloads, second_manifest = carrier._prepare_bundle(definition)
            if first_payloads != second_payloads or first_manifest != second_manifest:
                raise ExactIdentityDecisionError(
                    "identity v13 inputs changed or two offline reconstructions differ"
                )
            _assert_forbidden_lineage_absent({DEFINITION.name: raw, **first_payloads})
            if (len(raw), hashlib.sha256(raw).hexdigest()) != DEFINITION_PIN:
                raise ExactIdentityDecisionError("identity v13 definition pin differs")

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
                raise ExactIdentityDecisionError("identity v13 private stage pins differ")
            _validate_decision_delta(bundle_stage)

            target = _parsed_timestamp(
                RECORDED_AT, "identity v13 recorded_at"
            ).timestamp()
            if _max_stage_time((definition_stage, bundle_stage)) > target + 0.000_001:
                raise ExactIdentityDecisionError(
                    "identity v13 staging exceeded publication timestamp"
                )
            frozen_definition = definition_stage.read_bytes()
            frozen_tree = tree_digest(bundle_stage)
            _wait_until_recorded()
            _stamp_publication_ctimes(definition_stage, bundle_stage)
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
                    "identity v13 stage or inputs changed while waiting"
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
                        f"identity v13 bundle rollback failed: {rollback_error}"
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
                            f"identity v13 definition rollback failed: {rollback_error}"
                        )
                if published_bundle:
                    try:
                        _rollback_bundle(bundle_stage)
                        published_bundle = False
                    except Exception as rollback_error:
                        rollback_errors.append(
                            f"identity v13 bundle rollback failed: {rollback_error}"
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
            raise ExactIdentityDecisionError("identity v13 publication mutated inputs")
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
