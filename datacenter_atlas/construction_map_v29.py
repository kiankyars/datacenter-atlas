"""Strict construction-map v29 successor over accepted map v28.

The wire schema remains construction-map v2. This carrier changes only the
bound construction master and the deterministic coordinate projection of its
observation rows. It creates no identity decision, current-status claim, or
unique-physical-site count.

Publication remains fail-closed until the accepted master-v29 pins and the
derived projection below are populated from final artifacts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


_BASE_SOURCE = Path(__file__).with_name("construction_map_v12.py")
_BASE_SOURCE_SHA256 = (
    "8f7ab8be0231e989ce0e87b990d92222042a626f6de0dfba1af11082bab7038a"
)


def _carrier_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v29 accepted-v28 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v12 changed; refusing v29 carrier load")
_source = _raw.decode("utf-8")

# Keep the inner v11-to-v29 version rewrite distinct from this carrier's
# v28-to-v29 and predecessor-v27-to-v28 path rewrites.
_version_sentinel = "(__MAP_V29_INNER_OLD__, __MAP_V29_INNER_NEW__, 6),"
_source = _carrier_replacement(
    _source, '("v27", "v28", 6),', _version_sentinel, 1
)
for _old, _new, _count in (
    ("construction_map_v12", "construction_map_v29", 21),
    ("ConstructionMapV12Error", "ConstructionMapV29Error", 58),
    ("build_index_v12", "build_index_v29", 2),
    ("is_frozen_map_v12", "is_frozen_map_v29", 4),
    ("validate_map_definition_v12", "validate_map_definition_v29", 4),
    ("construction_master_v12", "construction_master_v29", 4),
    ("ConstructionMasterV12Error", "ConstructionMasterV29Error", 3),
    ("master_v12", "master_v29", 12),
    ("v28", "v29", 72),
    ("V28", "V29", 1),
    ("v27", "v28", 14),
    ("v71", "v73", 2),
    ("109_328", "109_332", 1),
    ("len(replacement_ids) != 416", "len(replacement_ids) != 420", 1),
    ("len(added) != 217", "len(added) != 221", 1),
    ("108,996", "108,998", 1),
    ("109,328", "109,332", 1),
):
    _source = _carrier_replacement(_source, _old, _new, _count)
_source = _carrier_replacement(
    _source,
    _version_sentinel,
    '("v27", "v29", 6),',
    1,
)

exec(compile(_source, __file__, "exec"), globals())

# Bind dynamically loaded carrier names for static analysis and explicit API
# review. The values are still the exact objects created by the pinned source.
BUNDLE = globals()["BUNDLE"]
BUNDLE_FILES = globals()["BUNDLE_FILES"]
ConstructionMapV29Error = globals()["ConstructionMapV29Error"]
DEFINITION = globals()["DEFINITION"]
EXPECTED_FIXED = globals()["EXPECTED_FIXED"]
EXPECTED_DIGEST_KEYS = globals()["EXPECTED_DIGEST_KEYS"]
FIELDS = globals()["FIELDS"]
INDEX_FILENAME = globals()["INDEX_FILENAME"]
MAP_ID = globals()["MAP_ID"]
MAP_SCOPE = globals()["MAP_SCOPE"]
MASTER = globals()["MASTER"]
MASTER_DEFINITION = globals()["MASTER_DEFINITION"]
PREDECESSOR_BUNDLE = globals()["PREDECESSOR_BUNDLE"]
ROOT = globals()["ROOT"]
_map_rows = globals()["_map_rows"]
_master_record_ids = globals()["_master_record_ids"]
build_construction_map_v29 = globals()["build_construction_map_v29"]
definition_document = globals()["definition_document"]
derive_candidate_projection = globals()["derive_candidate_projection"]
is_frozen_map_v29 = globals()["is_frozen_map_v29"]
publish_construction_map_v29 = globals()["publish_construction_map_v29"]
validate_construction_map_v29 = globals()["validate_construction_map_v29"]
validate_map_definition_v29 = globals()["validate_map_definition_v29"]
write_construction_map_v29 = globals()["write_construction_map_v29"]


# Installed only after final construction-master v29 independently reproduced,
# passed its validator, and closed its no-replace temporal publication gate.
MASTER_DEFINITION_SHA256 = (
    "cd691202ee07e3a4a541c94c8c619da2120e7fa426a7dd468822b77452bcda3d"
)
MASTER_JSONL_SHA256 = (
    "a36b6de29a74030ff664b3dcf8918c2ad137998fc3c3a9947b2dd6b79441492b"
)
MASTER_MANIFEST_SHA256 = (
    "4d1146c4fe8a3c4d8112e7b33ac825febac42a149df2871863e0ed87300a610c"
)
MASTER_TREE_SHA256 = (
    "09a76700020e35b1daa95e00cbd6c6bdf90aede9d9f794f5a4c70a607541eff8"
)

PREDECESSOR_DEFINITION_SHA256 = (
    "52aa5b4443f60efb6ff2b983566bc194f707345e5eeaca613512c1791b6bbd85"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "199d2c73cd73871ebe183d10531e44c1c8a0f4387973730523d9c78e65f70e6f"
)
PREDECESSOR_TREE_SHA256 = (
    "57b705610c92e7414666ceff0051b973417a587037730a2e687a3809d3bbab9a"
)

# Derived from the byte-pinned final master, then checked against the exact v28
# row delta before any map definition or output bytes were staged.
EXPECTED_PROJECTION: dict[str, Any] = {
    "added_replacement_rows_unmapped": 205,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "d2232b6b3ac02bd1b369d9632702dadbcd6e04db95ab473e1a764d59cf95cfbf"
    ),
    "default_visible_rows": 6504,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 224, "B": 6280, "C": 102494},
    "mapped_replacement_rows": 105,
    "mapped_rows": 108998,
    "mapped_rows_with_any_role": 75,
    "master_rows": 109332,
    "unmapped_rows": 334,
    "unmapped_source_record_ids_sha256": (
        "0324cc076c2fd08a367655154f80f6569236fecb03fe29f4efbcae9febba640d"
    ),
}
EXPECTED_FIXED.clear()
EXPECTED_FIXED.update(
    {
        key: value
        for key, value in EXPECTED_PROJECTION.items()
        if key not in EXPECTED_DIGEST_KEYS and key != "default_visible_tiers"
    }
)

NEW_COORDINATE_MAPPING_IDS = frozenset(
    {
        "19f6a887-c4b1-57a7-9fee-2f11325a5b1d",
        "cafab9a5-428c-5442-98d3-3784f9ecc7bb",
    }
)
NEW_MASTER_RECORD_IDS = frozenset(
    {
        "44130f9f-95af-5f19-9fcf-47aabd3a5c8b",
        "a5284884-bfaa-520e-886b-49ed91354d89",
        "d6270e7f-0c83-5d00-8481-6cb753f4b16c",
        "e997ad94-2a62-5c44-90f9-fa27edf77dc2",
    }
)

# V29 is itself an accepted target token, so only genuinely rejected lineage
# remains forbidden from definition and bundle payloads.
REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v30",
    b"2026-07-21-open-seed-v68",
    b"epoch-official-open-seed-v68",
)


def _assert_exact_v28_delta(
    projected: Mapping[str, Mapping[str, Any]], all_ids: set[str]
) -> None:
    old_projected = _map_rows(PREDECESSOR_BUNDLE / INDEX_FILENAME)
    old_all_ids = _master_record_ids(
        ROOT
        / "construction_master/2026-07-21-public-open-v28/"
        "construction-master.jsonl"
    )
    if not old_all_ids.issubset(all_ids):
        raise ConstructionMapV29Error("master v29 removed a v28 source record")
    additions = all_ids - old_all_ids
    if additions != NEW_MASTER_RECORD_IDS:
        raise ConstructionMapV29Error(
            "master v29 additions are not exactly the four accepted v73 builds"
        )

    old_ids = set(old_projected)
    new_ids = set(projected)
    if old_ids - new_ids or new_ids - old_ids != NEW_COORDINATE_MAPPING_IDS:
        raise ConstructionMapV29Error(
            "map v29 coordinate delta is not exactly the two accepted v72 projects"
        )
    if not NEW_COORDINATE_MAPPING_IDS.issubset(old_all_ids) or (
        NEW_COORDINATE_MAPPING_IDS & old_ids
    ):
        raise ConstructionMapV29Error(
            "map v29 coordinate additions were not previously unmapped v28 rows"
        )
    if additions & new_ids:
        raise ConstructionMapV29Error(
            "the four new master-v29 observations are not coordinate-null"
        )

    for record_id, old in old_projected.items():
        current = dict(projected[record_id])
        if old["source_artifact_id"] == "epoch-official-open-seed-v71":
            current.update(
                {
                    "row_id": old["row_id"],
                    "source_artifact_id": old["source_artifact_id"],
                    "source_release_id": old["source_release_id"],
                }
            )
        if current != old:
            raise ConstructionMapV29Error(
                f"map v29 changed an inherited mapped row: {record_id}"
            )


__all__ = [
    "BUNDLE",
    "BUNDLE_FILES",
    "ConstructionMapV29Error",
    "DEFINITION",
    "EXPECTED_PROJECTION",
    "FIELDS",
    "MAP_ID",
    "MAP_SCOPE",
    "MASTER",
    "MASTER_DEFINITION",
    "NEW_COORDINATE_MAPPING_IDS",
    "NEW_MASTER_RECORD_IDS",
    "build_construction_map_v29",
    "definition_document",
    "derive_candidate_projection",
    "is_frozen_map_v29",
    "publish_construction_map_v29",
    "validate_construction_map_v29",
    "validate_map_definition_v29",
    "write_construction_map_v29",
]
