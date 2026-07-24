"""Strict construction-map v30 successor over accepted map v29.

The wire schema remains construction-map v2. This carrier binds only the
accepted construction master v30 and deterministically projects its
coordinate-bearing observation rows. It creates no coordinate, identity,
current-status, or unique-physical-site assertion.

Publication remains fail-closed until final master-v30 pins are installed
after independent validation and temporal closure.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping


_BASE_SOURCE = Path(__file__).with_name("construction_map_v12.py")
_BASE_SOURCE_SHA256 = (
    "8f7ab8be0231e989ce0e87b990d92222042a626f6de0dfba1af11082bab7038a"
)


def _carrier_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v30 accepted-v29 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v12 changed; refusing v30 carrier load")
_source = _raw.decode("utf-8")

# Keep the inner v11-to-v30 rewrite distinct from this carrier's v29-to-v30
# predecessor path rewrite.
_version_sentinel = "(__MAP_V30_INNER_OLD__, __MAP_V30_INNER_NEW__, 6),"
_source = _carrier_replacement(
    _source, '("v27", "v28", 6),', _version_sentinel, 1
)
for _old, _new, _count in (
    ("construction_map_v12", "construction_map_v30", 21),
    ("ConstructionMapV12Error", "ConstructionMapV30Error", 58),
    ("build_index_v12", "build_index_v30", 2),
    ("is_frozen_map_v12", "is_frozen_map_v30", 4),
    ("validate_map_definition_v12", "validate_map_definition_v30", 4),
    ("construction_master_v12", "construction_master_v30", 4),
    ("ConstructionMasterV12Error", "ConstructionMasterV30Error", 3),
    ("master_v12", "master_v30", 12),
    ("v28", "v30", 72),
    ("V28", "V30", 1),
    ("v27", "v29", 14),
    ("v71", "v83", 2),
    ("109_328", "109_374", 1),
    ("len(replacement_ids) != 416", "len(replacement_ids) != 462", 1),
    ("len(added) != 217", "len(added) != 263", 1),
    ("108,996", "109,002", 1),
    ("109,328", "109,374", 1),
):
    _source = _carrier_replacement(_source, _old, _new, _count)
_source = _carrier_replacement(
    _source,
    _version_sentinel,
    '("v27", "v30", 6),',
    1,
)

exec(compile(_source, __file__, "exec"), globals())

# Bind dynamically loaded carrier names for static analysis and explicit API
# review. The values are still the exact objects created by the pinned source.
BUNDLE = globals()["BUNDLE"]
BUNDLE_FILES = globals()["BUNDLE_FILES"]
ConstructionMapV30Error = globals()["ConstructionMapV30Error"]
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
build_construction_map_v30 = globals()["build_construction_map_v30"]
definition_document = globals()["definition_document"]
derive_candidate_projection = globals()["derive_candidate_projection"]
is_frozen_map_v30 = globals()["is_frozen_map_v30"]
publish_construction_map_v30 = globals()["publish_construction_map_v30"]
validate_construction_map_v30 = globals()["validate_construction_map_v30"]
validate_map_definition_v30 = globals()["validate_map_definition_v30"]
write_construction_map_v30 = globals()["write_construction_map_v30"]


# Installed only after final construction-master v30 independently reproduces,
# validates, freezes, and closes its no-replace temporal publication gate.
MASTER_DEFINITION_SHA256 = (
    "981bfd4dcf9bcb6f00f6825c4ac74d62b2bfefeb019fbfa945b774c136683a63"
)
MASTER_JSONL_SHA256 = (
    "15f8b61dec37d658f338e83193908c96343893ba6cfc5eabc547cdf71a5f37cb"
)
MASTER_MANIFEST_SHA256 = (
    "8f81ded9c9f351caa0f7a75afce8b4a7abe673c3a078c5bf5fd7bb1f75eabf1f"
)
MASTER_TREE_SHA256 = (
    "32d3370e3604434886d305c2a0b129458bfbe1c4e823760f0ccc3a16a3519e30"
)

PREDECESSOR_DEFINITION_SHA256 = (
    "9668c1ee0eadfb755745407a2b140e414044a9c97dfeecaf95b131afbf8446bc"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "5cfaeba6d854df6aabb4b4c500701d1a3d1d9f7c1e4d1481a986a2602374b889"
)
PREDECESSOR_TREE_SHA256 = (
    "b551f672a6ce6e82815a0633cc5c7cbd45ce358b9d8f1db1bd8257c4c36fe4b8"
)

# Independently derived from accepted v83 and the byte-pinned v29 master/map.
# The final master projection must reproduce these exact values before staging.
EXPECTED_PROJECTION: dict[str, Any] = {
    "added_replacement_rows_unmapped": 243,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "a6894e2bd0d45f3f8884d7f14a153e7cacf1d9ee316b2aba992c6c588c5af0c9"
    ),
    "default_visible_rows": 6508,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 228, "B": 6280, "C": 102494},
    "mapped_replacement_rows": 109,
    "mapped_rows": 109002,
    "mapped_rows_with_any_role": 78,
    "master_rows": 109374,
    "unmapped_rows": 372,
    "unmapped_source_record_ids_sha256": (
        "d5c5b061ad84390ad723c6baaf65798832a64d4ea033c67219535f5cf81a75dc"
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

PRIOR_UNMAPPED_NOW_MAPPED_IDS = frozenset(
    {
        "44130f9f-95af-5f19-9fcf-47aabd3a5c8b",
        "d6270e7f-0c83-5d00-8481-6cb753f4b16c",
        "e997ad94-2a62-5c44-90f9-fa27edf77dc2",
    }
)
NEWLY_ADDED_MAPPED_IDS = frozenset(
    {"5c6e55e6-1029-5edf-9975-8695c3009b9d"}
)
NEW_COORDINATE_MAPPING_IDS = (
    PRIOR_UNMAPPED_NOW_MAPPED_IDS | NEWLY_ADDED_MAPPED_IDS
)
NEW_COORDINATE_MAPPING_IDS_SHA256 = (
    "3eb7aa6289a106b7ea145f71d23862381d3a0aa1e37762402cfd882288392057"
)
EXPECTED_NEW_COORDINATES = {
    "44130f9f-95af-5f19-9fcf-47aabd3a5c8b": (71.4577083333, 51.2067694444),
    "5c6e55e6-1029-5edf-9975-8695c3009b9d": (
        89.22246834914694,
        23.156275210272007,
    ),
    "d6270e7f-0c83-5d00-8481-6cb753f4b16c": (-75.734798, -14.075622),
    "e997ad94-2a62-5c44-90f9-fa27edf77dc2": (22.0132502617, 56.9356302057),
}

NEW_MASTER_RECORD_IDS = frozenset(
    {
        "010c4071-5901-54ea-a312-f59d53358a0a",
        "015d1c6d-52f9-5710-9de7-ea464f900d0a",
        "0fd5e6a4-6421-5a23-b51c-e490e4a79cd9",
        "15e0ef92-6408-5517-b0d4-a6b8707745f4",
        "164033cb-411d-5ffb-ab5d-b04bdecfa1ac",
        "1cae5b48-c630-5f16-9fe2-5d77571cafe9",
        "20a32e9d-3c57-520d-aeb8-ad999d43fee3",
        "2e2b9d40-5024-5e6d-bbb2-56a8b16b9c16",
        "35c427dc-af95-5011-b3ab-3fa7c90fcb30",
        "38033ec9-dbd8-56bb-8a35-0fa91dd284e2",
        "38d0dda4-91f0-5eab-9e8f-f7306ea9f52a",
        "47804028-7f90-5f2c-8b96-3a9aedddec33",
        "48eb54d5-dd3f-51a3-aeed-1ddce1949763",
        "4f39070f-83dd-557a-a1b0-88408f56c1fb",
        "5592f5ef-eed0-52b8-acc6-51f282800721",
        "5ba16966-66eb-5498-85fa-e9a3dbfa7cef",
        "5c366d64-4bb5-5c28-ab62-ec20d60fb31a",
        "5c6e55e6-1029-5edf-9975-8695c3009b9d",
        "61b03f74-0ad9-5d9b-bec5-4b5a7db21849",
        "66f55dcd-e8bb-5c82-abce-cea63c3ee003",
        "6a3cb870-eb89-5d4b-a486-44eb7d10f8b0",
        "6ce55d38-7f1f-5068-b112-035f104def18",
        "6ee08549-01a2-53f9-b1d5-9ddb8826bb7f",
        "71bfdb7b-1ef5-567b-b4c9-4feb7f843e3a",
        "731b8e07-e013-5631-bb26-d0b46101cf33",
        "83efe2e8-3b4b-5260-b4ca-d1dbc653b792",
        "98a3ddfe-7a5b-5fd8-a0c0-a718bf615492",
        "98e47ac5-8576-53f7-ab71-9f3d683b5ec5",
        "9be0ab88-c727-5dbc-8a12-e2443878b69f",
        "9cceddca-71bc-52f2-a417-e9fdf0d7faa3",
        "ad179a16-e0b4-57f3-abc7-01968cbcd63b",
        "adc32529-cea1-5d06-86de-334e63433be6",
        "ae03ca19-d4e7-5739-868c-922fa72a92d5",
        "b6b17653-dede-5457-a8f3-1aeaf23ce393",
        "bb8ba3ad-d563-5f84-a543-079a10264640",
        "cacf6b62-c3a5-5647-833a-7f3d55ae2241",
        "d8bc6500-ec4c-5617-8504-6eea9ed44746",
        "d924512d-a8b5-58db-9a44-cd38bfaabb4a",
        "e2c7c737-5319-551f-9865-0e7eb560e86a",
        "e2c7ea58-17cc-594d-8b98-56ca08988c99",
        "f0a9ec19-2fe0-5da0-949a-3752b08bc846",
        "fcc12381-5738-5526-9cad-092b5cb4e19b",
    }
)
NEW_MASTER_RECORD_IDS_SHA256 = (
    "b597459973ad1d632febbe47d9df0a945d2bffbbc0fcd896208cce69e2c2f035"
)
REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256 = (
    "16437a68fde6ae3bc9da0cb968ac0bcd5eca941c4e2f5cc71e46f8c55ab8caae"
)

# V30 is an accepted target token. V73 map-row lineage must be completely
# replaced by v83; the known rejected v68 lineage remains forbidden.
REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v31",
    b"epoch-official-open-seed-v73",
    b"2026-07-21-open-seed-v68",
    b"epoch-official-open-seed-v68",
)


def _id_set_digest(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _assert_exact_v29_delta(
    projected: Mapping[str, Mapping[str, Any]], all_ids: set[str]
) -> None:
    old_projected = _map_rows(PREDECESSOR_BUNDLE / INDEX_FILENAME)
    old_all_ids = _master_record_ids(
        ROOT
        / "construction_master/2026-07-21-public-open-v29/"
        "construction-master.jsonl"
    )
    if not old_all_ids.issubset(all_ids):
        raise ConstructionMapV30Error("master v30 removed a v29 source record")
    additions = all_ids - old_all_ids
    if (
        additions != NEW_MASTER_RECORD_IDS
        or _id_set_digest(additions) != NEW_MASTER_RECORD_IDS_SHA256
    ):
        raise ConstructionMapV30Error(
            "master v30 additions are not exactly the 42 accepted v83 rows"
        )

    old_ids = set(old_projected)
    new_ids = set(projected)
    if old_ids - new_ids or new_ids - old_ids != NEW_COORDINATE_MAPPING_IDS:
        raise ConstructionMapV30Error(
            "map v30 coordinate delta is not exactly the four accepted v83 rows"
        )
    if (
        _id_set_digest(NEW_COORDINATE_MAPPING_IDS)
        != NEW_COORDINATE_MAPPING_IDS_SHA256
    ):
        raise ConstructionMapV30Error("map v30 coordinate delta digest changed")
    if not PRIOR_UNMAPPED_NOW_MAPPED_IDS.issubset(old_all_ids) or (
        PRIOR_UNMAPPED_NOW_MAPPED_IDS & old_ids
    ):
        raise ConstructionMapV30Error(
            "three v83 coordinate successors were not previously unmapped v29 rows"
        )
    if additions & new_ids != NEWLY_ADDED_MAPPED_IDS:
        raise ConstructionMapV30Error(
            "new v83 rows do not have exactly one direct coordinate mapping"
        )

    for record_id, coordinates in EXPECTED_NEW_COORDINATES.items():
        current = projected[record_id]
        if (
            current["longitude"],
            current["latitude"],
        ) != coordinates or current["source_artifact_id"] != (
            "epoch-official-open-seed-v83"
        ) or current["source_release_id"] != "epoch-official-open-seed-v83":
            raise ConstructionMapV30Error(
                f"map v30 direct v83 coordinate changed: {record_id}"
            )

    rewritten_ids = {
        record_id
        for record_id, row in old_projected.items()
        if row["source_artifact_id"] == "epoch-official-open-seed-v73"
    }
    if (
        len(rewritten_ids) != 105
        or _id_set_digest(rewritten_ids)
        != REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256
    ):
        raise ConstructionMapV30Error(
            "accepted map v29 replacement-lineage boundary changed"
        )
    for record_id, old in old_projected.items():
        current = dict(projected[record_id])
        if record_id in rewritten_ids:
            if (
                current["source_artifact_id"]
                != "epoch-official-open-seed-v83"
                or current["source_release_id"]
                != "epoch-official-open-seed-v83"
            ):
                raise ConstructionMapV30Error(
                    f"map v30 did not rewrite v83 lineage: {record_id}"
                )
            current.update(
                {
                    "row_id": old["row_id"],
                    "source_artifact_id": old["source_artifact_id"],
                    "source_release_id": old["source_release_id"],
                }
            )
        if current != old:
            raise ConstructionMapV30Error(
                f"map v30 changed an inherited mapped row: {record_id}"
            )


__all__ = [
    "BUNDLE",
    "BUNDLE_FILES",
    "ConstructionMapV30Error",
    "DEFINITION",
    "EXPECTED_NEW_COORDINATES",
    "EXPECTED_PROJECTION",
    "FIELDS",
    "MAP_ID",
    "MAP_SCOPE",
    "MASTER",
    "MASTER_DEFINITION",
    "NEW_COORDINATE_MAPPING_IDS",
    "NEW_MASTER_RECORD_IDS",
    "NEWLY_ADDED_MAPPED_IDS",
    "PRIOR_UNMAPPED_NOW_MAPPED_IDS",
    "build_construction_map_v30",
    "definition_document",
    "derive_candidate_projection",
    "is_frozen_map_v30",
    "publish_construction_map_v30",
    "validate_construction_map_v30",
    "validate_map_definition_v30",
    "write_construction_map_v30",
]
