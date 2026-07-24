"""Strict construction-map v31 successor over accepted map v30.

The wire schema remains construction-map v2. This carrier binds only the
accepted construction master v31 and deterministically projects its
coordinate-bearing observation rows. It creates no coordinate, identity,
current-status, or unique-physical-site assertion.
"""

# ruff: noqa: F821, F822 -- the byte-pinned carrier defines these names by exec.

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping


_BASE_SOURCE = Path(__file__).with_name("construction_map_v30.py")
_BASE_SOURCE_SHA256 = (
    "1e9dd97f191b9e50e1a287f893e286335fd6ce31861b29c7d09f7f14aa15cf04"
)


def _carrier_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v31 accepted-v30 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v30 changed; refusing v31 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("v30", "v31", 41),
    ("V30", "V31", 19),
    ("v83", "v86", 13),
    ("109_374", "109_381", 1),
    ("len(replacement_ids) != 462", "len(replacement_ids) != 469", 1),
    ("len(added) != 263", "len(added) != 270", 1),
    ("109,002", "109,008", 1),
    ("109,374", "109,381", 1),
):
    _source = _carrier_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())


# Accepted final master-v31 pins. The master is source-observation data; this
# map adds no physical-site or persistence inference.
MASTER_DEFINITION_SHA256 = (
    "a1b4761820aa6adb3406d5ff3ad6bc52898309fed72fe4f857aca01197597c25"
)
MASTER_JSONL_SHA256 = (
    "71fe0a7f054ca2329aa5747cada25cfdc51b52ca02396437cf9e34851552b035"
)
MASTER_MANIFEST_SHA256 = (
    "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e"
)
MASTER_TREE_SHA256 = (
    "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da"
)

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-map-2026-07-21-public-open-v30.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v30"
PREDECESSOR_DEFINITION_SHA256 = (
    "47f2322edd2983bc8ed881edf8e0071d806df304cf773be2e215bcc1806d0847"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "73108a00068912f83233114fc2ab7ae79087e610d54226762512fe3cc8ef4360"
)
PREDECESSOR_TREE_SHA256 = (
    "67bc3870ddc2c34308ab0de5defe19ece9d9cea85f6f1ac5c1d4082b18714149"
)


EXPECTED_PROJECTION: dict[str, Any] = {
    "added_replacement_rows_unmapped": 244,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "dc7e1f089128258e787199e5ff482c9f3742e58f1f42bac9e9cc37d087d71284"
    ),
    "default_visible_rows": 6_514,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 234, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 115,
    "mapped_rows": 109_008,
    "mapped_rows_with_any_role": 84,
    "master_rows": 109_381,
    "unmapped_rows": 373,
    "unmapped_source_record_ids_sha256": (
        "d4891e0a43dd2df48a55c0cb01521eac35908f81f5e983465ea2422015837620"
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


def _id_set_digest(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


NEW_MASTER_RECORD_IDS = frozenset(
    {
        "0940c2a1-ed83-5dc8-9f89-54732c4c82b2",
        "2b7caba9-326b-5c7d-86eb-86da01d91f1e",
        "9fcb8bf2-26aa-5bfe-a9cc-9a7942033464",
        "a225d046-5d72-5a1f-bf4b-ba454f713a49",
        "a848e771-2e45-55fb-8d43-db0885bb824f",
        "bad745b8-d601-5b71-9ef5-114b6fdad6a3",
        "c160d8d5-7572-53c2-8051-cd7990b1f771",
    }
)
NEW_MASTER_RECORD_IDS_SHA256 = (
    "9f1ee494e8cd0d87fde2d0e81da43bc8aa913772fd9c39e22db71438e4bb7c66"
)

PRIOR_UNMAPPED_NOW_MAPPED_IDS = frozenset(
    {
        "2e2b9d40-5024-5e6d-bbb2-56a8b16b9c16",
        "38033ec9-dbd8-56bb-8a35-0fa91dd284e2",
        "47804028-7f90-5f2c-8b96-3a9aedddec33",
        "5c366d64-4bb5-5c28-ab62-ec20d60fb31a",
        "98e47ac5-8576-53f7-ab71-9f3d683b5ec5",
        "e2c7c737-5319-551f-9865-0e7eb560e86a",
    }
)
NEW_COORDINATE_MAPPING_IDS = PRIOR_UNMAPPED_NOW_MAPPED_IDS
NEW_COORDINATE_MAPPING_IDS_SHA256 = (
    "1254eb2a6fcfd9591999b1f0fd41b9f29138c0582d325df61c0365dd13db21d0"
)
EXPECTED_NEW_COORDINATES = {
    "2e2b9d40-5024-5e6d-bbb2-56a8b16b9c16": (150.837668, -33.818072),
    "38033ec9-dbd8-56bb-8a35-0fa91dd284e2": (
        23.90870178233002,
        37.96626241294147,
    ),
    "47804028-7f90-5f2c-8b96-3a9aedddec33": (
        24.3802635323,
        56.8656322193,
    ),
    "5c366d64-4bb5-5c28-ab62-ec20d60fb31a": (150.837668, -33.818072),
    "98e47ac5-8576-53f7-ab71-9f3d683b5ec5": (
        24.1814716538,
        56.933100002,
    ),
    "e2c7c737-5319-551f-9865-0e7eb560e86a": (150.876, -33.798627),
}
REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256 = (
    "34263ef7d9b2e7e7ac00c57df6fb76f68cfafb2793d8371b8c29760b8c061be5"
)

REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v30",
    b"2026-07-21-public-open-v29",
    b"epoch-official-open-seed-v83",
    b"epoch-official-open-seed-v73",
    b"2026-07-21-open-seed-v68",
    b"epoch-official-open-seed-v68",
)


def _assert_exact_v30_delta(
    projected: Mapping[str, Mapping[str, Any]], all_ids: set[str]
) -> None:
    old_projected = _map_rows(PREDECESSOR_BUNDLE / INDEX_FILENAME)
    old_all_ids = _master_record_ids(
        ROOT
        / "construction_master/2026-07-21-public-open-v30/"
        "construction-master.jsonl"
    )
    if not old_all_ids.issubset(all_ids):
        raise ConstructionMapV31Error("master v31 removed a v30 source record")
    additions = all_ids - old_all_ids
    if (
        additions != NEW_MASTER_RECORD_IDS
        or _id_set_digest(additions) != NEW_MASTER_RECORD_IDS_SHA256
    ):
        raise ConstructionMapV31Error(
            "master v31 additions are not exactly the seven accepted v86 rows"
        )

    old_ids = set(old_projected)
    new_ids = set(projected)
    if old_ids - new_ids or new_ids - old_ids != NEW_COORDINATE_MAPPING_IDS:
        raise ConstructionMapV31Error(
            "map v31 coordinate delta is not exactly the six accepted direct points"
        )
    if (
        _id_set_digest(NEW_COORDINATE_MAPPING_IDS)
        != NEW_COORDINATE_MAPPING_IDS_SHA256
    ):
        raise ConstructionMapV31Error("map v31 coordinate delta digest changed")
    if not PRIOR_UNMAPPED_NOW_MAPPED_IDS.issubset(old_all_ids) or (
        PRIOR_UNMAPPED_NOW_MAPPED_IDS & old_ids
    ):
        raise ConstructionMapV31Error(
            "six v86 coordinate successors were not previously unmapped v30 rows"
        )
    if additions & new_ids:
        raise ConstructionMapV31Error(
            "a newly added v86 master row was promoted without a direct coordinate"
        )

    for record_id, coordinates in EXPECTED_NEW_COORDINATES.items():
        current = projected[record_id]
        if (
            current["longitude"],
            current["latitude"],
        ) != coordinates or current["source_artifact_id"] != (
            "epoch-official-open-seed-v86"
        ) or current["source_release_id"] != "epoch-official-open-seed-v86":
            raise ConstructionMapV31Error(
                f"map v31 direct v86 coordinate changed: {record_id}"
            )

    rewritten_ids = {
        record_id
        for record_id, row in old_projected.items()
        if row["source_artifact_id"] == "epoch-official-open-seed-v83"
    }
    if (
        len(rewritten_ids) != 109
        or _id_set_digest(rewritten_ids)
        != REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256
    ):
        raise ConstructionMapV31Error(
            "accepted map v30 replacement-lineage boundary changed"
        )
    for record_id, old in old_projected.items():
        current = dict(projected[record_id])
        if record_id in rewritten_ids:
            if (
                current["source_artifact_id"]
                != "epoch-official-open-seed-v86"
                or current["source_release_id"]
                != "epoch-official-open-seed-v86"
            ):
                raise ConstructionMapV31Error(
                    f"map v31 did not rewrite v86 lineage: {record_id}"
                )
            current.update(
                {
                    "row_id": old["row_id"],
                    "source_artifact_id": old["source_artifact_id"],
                    "source_release_id": old["source_release_id"],
                }
            )
        if current != old:
            raise ConstructionMapV31Error(
                f"map v31 changed an inherited mapped row: {record_id}"
            )


# The pinned carrier's projection entry point resolves this name dynamically.
_assert_exact_v29_delta = _assert_exact_v30_delta


__all__ = [
    "BUNDLE",
    "BUNDLE_FILES",
    "ConstructionMapV31Error",
    "DEFINITION",
    "EXPECTED_PROJECTION",
    "EXPECTED_NEW_COORDINATES",
    "FIELDS",
    "MAP_ID",
    "MAP_SCOPE",
    "MASTER",
    "MASTER_DEFINITION",
    "NEW_COORDINATE_MAPPING_IDS",
    "NEW_MASTER_RECORD_IDS",
    "PRIOR_UNMAPPED_NOW_MAPPED_IDS",
    "build_construction_map_v31",
    "definition_document",
    "derive_candidate_projection",
    "is_frozen_map_v31",
    "publish_construction_map_v31",
    "validate_construction_map_v31",
    "validate_map_definition_v31",
    "write_construction_map_v31",
]
