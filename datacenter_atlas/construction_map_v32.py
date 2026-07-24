"""Strict private/prepublication construction-map v32 successor.

The wire schema remains construction-map v2, including ``source_record_id``.
Internal identity is deliberately stronger: global row accounting uses
``row_id`` and source-lane classification uses ``(artifact_id, record_id)``.
This preserves the four legitimate v97/global-open-v3 bare-ID overlaps without
collapsing rows or misclassifying inherited observations as v97 additions.
"""

# ruff: noqa: F821, F822 -- the byte-pinned carrier defines these names by exec.

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

_BASE_SOURCE = Path(__file__).with_name("construction_map_v31.py")
_BASE_SOURCE_SHA256 = "846746ae0a290600f1779ab706a90611a3adb05f470e1f656759afed0634bd3d"


def _carrier_replacement(source: str, old: str, new: str, count: int) -> str:
    actual = source.count(old)
    if actual != count:
        raise ImportError(
            "construction_map_v32 accepted-v31 carrier changed: "
            f"expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    return source.replace(old, new)


_raw = _BASE_SOURCE.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _BASE_SOURCE_SHA256:
    raise ImportError("construction_map_v31 changed; refusing v32 carrier load")
_source = _raw.decode("utf-8")
for _old, _new, _count in (
    ("v31", "v32", 19),
    ("V31", "V32", 12),
    ("v86", "v97", 10),
    ("109_381", "109_443", 2),
    ("len(replacement_ids) != 469", "len(replacement_ids) != 531", 1),
    ("len(added) != 270", "len(added) != 332", 1),
    ("109,008", "109,009", 1),
    ("109,381", "109,443", 1),
):
    _source = _carrier_replacement(_source, _old, _new, _count)

exec(compile(_source, __file__, "exec"), globals())  # noqa: S102


MAP_GENERATED_AT = "2026-07-24T23:45:00Z"
MAP_ID = "2026-07-22-public-open-v32-construction-map-v2"
MASTER_ID = "2026-07-22-public-open-v32"
MASTER_DEFINITION = ROOT / "sources/construction-master-2026-07-22-public-open-v32.json"
MASTER = ROOT / "construction_master/2026-07-22-public-open-v32"
DEFINITION = ROOT / "sources/construction-map-2026-07-22-public-open-v32.json"
BUNDLE = ROOT / "construction_maps/2026-07-22-public-open-v32"
PUBLICATION_LOCK = ROOT / ".construction-map-v32.lock"

CANDIDATE_MASTER_TRANSACTION = ROOT / ".construction-master-v32.transaction-8gsvvbir"
CANDIDATE_MASTER_DEFINITION = (
    CANDIDATE_MASTER_TRANSACTION / "construction-master-2026-07-22-public-open-v32.json"
)
CANDIDATE_MASTER = CANDIDATE_MASTER_TRANSACTION / "bundle"
CANDIDATE_MASTER_GENERATED_AT = "2026-07-24T23:30:00Z"
CANDIDATE_MASTER_DEFINITION_SHA256 = (
    "05ed7f1eb48a54efb9e21224356d85108c897e977e2d458d52d10d2c0e14dbdb"
)
CANDIDATE_MASTER_JSONL_SHA256 = (
    "60388e1a111a880ab04ab4ec6aa95bd3cf2a04eaa77b16a1bcd0b85533a32eae"
)
CANDIDATE_MASTER_MANIFEST_SHA256 = (
    "aee4310084012a0adc77b0833df6325c6a2da57d4379fe6b57b49b133876294a"
)
CANDIDATE_MASTER_TREE_SHA256 = (
    "9a651415dbf66c99bcf07bc6aa268a05fc43aa03afaca1eea94cf8b31fed4084"
)
CANDIDATE_DEFINITION_STAGE = (
    DEFINITION.parent
    / ".construction-map-2026-07-22-public-open-v32.json.candidate-jn5inlyj"
)
CANDIDATE_BUNDLE_STAGE = (
    BUNDLE.parent / ".2026-07-22-public-open-v32.candidate-z7hgjpib"
)
CANDIDATE_DEFINITION_SHA256 = (
    "50248a1fafc5ce96693592b990be6fc9352233091e4c4210817db5d6936cef3f"
)
CANDIDATE_MANIFEST_SHA256 = (
    "8b321d67ef80a6af0fbc0d39d60b5a10387777a1ab97d3a1a0f45a5b9bfa952d"
)
CANDIDATE_TREE_SHA256 = (
    "78d444c9b289ccc23acdbc7a7a2ff5fbedf0df16ece8100da328cb7fde05572e"
)

MASTER_DEFINITION_SHA256 = CANDIDATE_MASTER_DEFINITION_SHA256
MASTER_JSONL_SHA256 = CANDIDATE_MASTER_JSONL_SHA256
MASTER_MANIFEST_SHA256 = CANDIDATE_MASTER_MANIFEST_SHA256
MASTER_TREE_SHA256 = CANDIDATE_MASTER_TREE_SHA256

PREDECESSOR_DEFINITION = (
    ROOT / "sources/construction-map-2026-07-21-public-open-v31.json"
)
PREDECESSOR_BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v31"
PREDECESSOR_DEFINITION_SHA256 = (
    "a8c15cc5f78e3b0c2b7a40b46b496b7c3561662aefda237424dc1c4b6d138f97"
)
PREDECESSOR_MANIFEST_SHA256 = (
    "5305dd9c637a74dbd2a3b355e19185e1fd9f49b815b8a9a51786ce8428b33631"
)
PREDECESSOR_TREE_SHA256 = (
    "73e913f53287a2474274b6ff16daf10dcb8cd2ceceadc766e9aedd9ba3852973"
)

EXPECTED_PROJECTION: dict[str, Any] = {
    "added_replacement_rows_unmapped": 305,
    "added_replacement_unmapped_source_record_ids_sha256": (
        "4bbe3bf6cfcbb3bb5dae13b0d0184f1454004225e80ca578f5361c7ae5da6686"
    ),
    "default_visible_rows": 6_515,
    "default_visible_tiers": ["A", "B"],
    "mapped_by_tier": {"A": 235, "B": 6_280, "C": 102_494},
    "mapped_replacement_rows": 116,
    "mapped_rows": 109_009,
    "mapped_rows_with_any_role": 85,
    "master_rows": 109_443,
    "unmapped_rows": 434,
    "unmapped_source_record_ids_sha256": (
        "f0a106f46d9198d196edbb1f5ec4fe65ef1e34de03f422955f8dd7ee014a5605"
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

NEW_MASTER_RECORD_IDS = frozenset(
    {
        "0699881d-568d-5fcc-97d9-92b1fb44f699",
        "06c02a27-bc9b-5966-a050-a528d82d7467",
        "13fa11a5-1569-5049-890a-ab5474c85c8b",
        "146c63a3-61dc-5e94-a4ce-dd4c42e95852",
        "19c36a6e-e16f-53cd-9525-2c7652e23499",
        "1b44ff4b-adee-5bc3-b87b-82f4ad914a85",
        "1f0b6708-7756-5c52-b49b-6dca1268b10e",
        "20f43304-352a-5628-9650-f31863042d19",
        "213cbb8d-9a75-569d-8254-c92397331870",
        "219a90b8-9643-5082-a030-457627eaeddc",
        "22d81e01-2d78-5374-9cb3-0a613d3cbdaf",
        "23c3cb43-c96b-5aeb-b555-a5cb710fd81a",
        "30815507-982d-5e5b-b4fc-2641ae20bdd6",
        "33be3a26-5c79-5426-a1a1-9f5df516611f",
        "342a6eb2-e335-5564-acdc-27943230255b",
        "3518b2c3-e67e-52b5-bb2b-6f01fafed4c6",
        "3da66021-aa56-5186-9eee-e833a84233eb",
        "3e074273-f5f7-5785-ab10-232a5ebd5c6b",
        "453b7cdb-677d-519b-970e-2c4782db4fa0",
        "484cf452-3a8f-5574-8003-a5b3f693c5d2",
        "4a83d17c-2fce-5fd9-aa81-cbc8bbe3aff9",
        "4d0e7831-1169-546d-bbed-1a3374134ab6",
        "56b286a6-7cbe-5f22-bbaf-a598848d5a7e",
        "5ace12f8-658e-5956-9173-d78e625d4df9",
        "5ae9f639-4de6-5ce4-af8d-a40d6f8a3bec",
        "60865d2b-d5aa-57eb-8f92-da564392b07d",
        "62c83bcf-8df7-5c0b-8858-e276f3154bc6",
        "6f8a575c-8f42-59a7-8692-5a57ca92f08f",
        "7643bbe8-ad11-5790-8b7a-3525873bff72",
        "7ac977cb-cbe2-5dfd-b058-f26707f86b6c",
        "7b215704-7584-53a5-b7b9-6cd70a23e53f",
        "80783ff5-7666-5d1a-9d37-927ce7631775",
        "867d91cb-7a17-59db-a92e-4a50a499f54f",
        "890c004f-8f5b-572e-b263-92d30c2ed507",
        "8ad72331-5610-5329-a154-3fdd86219da0",
        "9367137f-f608-5b3b-8d05-adc3c9b14d36",
        "97f12a4b-6526-5c76-94b3-6562420ffe99",
        "ab9bf6d5-73d7-5d84-9b66-b80d2da64866",
        "ac1d16b1-9690-537d-953d-255c37b0cfbf",
        "ac241c9c-55fd-5abf-a473-b1fe521b17f1",
        "ae484949-f575-5553-ad33-bc1f96eab345",
        "b0d80d3b-c3b4-55a9-bafb-3f805583a292",
        "b3656b35-f3ad-5119-8918-ac5237bf2a7f",
        "b75695b9-38e3-58ec-baf2-039179ab353a",
        "b89ee77e-3160-56c2-bd68-e5ace86a7835",
        "c21029d6-f2ae-5645-98dc-29eed9d4b139",
        "c30aeadf-c2f6-58a5-a8b1-227868f477c1",
        "ca1d89df-67f4-5aa7-b78e-e23dc916b92d",
        "cd7cdd87-e2bf-505b-adf3-7e82d9d2847e",
        "d31b7f90-7006-51f5-9b89-4f1dc7ac7e54",
        "d7cf89ce-3263-5e1b-bed6-4dbbd93f668e",
        "d84e71c3-cd2c-5443-912b-aadcec17ee71",
        "df2b8f33-9c46-5f6a-9853-b47474606979",
        "e61b8cc5-8a3e-53f0-a24e-87c6237986f5",
        "eb451867-d1d3-5e41-bce7-d375e861167a",
        "f117fb3b-1fbe-5885-b734-d48cdbba78f3",
        "f20b8a70-2db9-5503-b41a-207876098d62",
        "f50a44c6-9e2c-5339-9066-6de43a1e302c",
        "f86ae4be-9fb2-5d5b-8ea9-47f985a5ebdf",
        "fb03bd6a-5ed1-58cc-87e3-7d0e9b8382fb",
        "fb943def-5b5b-5192-8bb9-599e4cf616cc",
        "fe6f26cf-4be9-51a3-857e-fca7ee21726b",
    }
)
NEW_MASTER_RECORD_IDS_SHA256 = (
    "6b9eef15c9984ffaf3af63c42b1505311d1009d2387f984d01fb7aacb996452b"
)

EXPECTED_BARE_SOURCE_RECORD_COLLISIONS = frozenset(
    {
        "213cbb8d-9a75-569d-8254-c92397331870",
        "867d91cb-7a17-59db-a92e-4a50a499f54f",
        "b3656b35-f3ad-5119-8918-ac5237bf2a7f",
        "d84e71c3-cd2c-5443-912b-aadcec17ee71",
    }
)
NEW_COORDINATE_MAPPING_IDS = frozenset({"ab9bf6d5-73d7-5d84-9b66-b80d2da64866"})
EXPECTED_NEW_COORDINATES = {
    "ab9bf6d5-73d7-5d84-9b66-b80d2da64866": (4.77335841, 52.25979593)
}
REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256 = (
    "546c6424698e722ff2f8b1aed41bc5d199f14cef99cb665a284b94d041fb8e83"
)
REPLACEMENT_MAPPED_PROJECTION_SHA256 = (
    "b155442309b8018b85b85c12eb8a8a3b943a95a28a54ae9be13ac5d8f37e4518"
)

REJECTED_LINEAGE_TOKENS = (
    b"2026-07-21-public-open-v31",
    b"2026-07-21-public-open-v30",
    b"epoch-official-open-seed-v86",
    b"epoch-official-open-seed-v83",
    b"2026-07-21-open-seed-v86",
)


def _row_projection_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda value: str(value["row_id"])):
        digest.update(
            (
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def build_index_v32(
    rows: Iterable[Mapping[str, Any]],
    *,
    master_manifest: Mapping[str, Any],
    master_manifest_sha256: str,
    added_source_record_ids: set[str],
    expected_projection: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project v32 using composite identity for replacement classification."""

    added_identities = {
        ("epoch-official-open-seed-v97", record_id)
        for record_id in added_source_record_ids
    }
    mapped: list[list[Any]] = []
    unmapped_ids: list[str] = []
    added_unmapped_ids: list[str] = []
    tiers: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    mapped_rows_with_any_role = 0
    mapped_replacement_rows = 0
    total = 0
    for line_number, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ConstructionMapV32Error(
                f"master line {line_number} must be an object"
            )
        total += 1
        projected = _project_row(row, line_number)
        source = row.get("source")
        if not isinstance(source, Mapping):
            raise ConstructionMapV32Error(f"master line {line_number} source is absent")
        artifact_id = source.get("artifact_id")
        record_id = source.get("record_id")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or not isinstance(record_id, str)
            or not record_id
        ):
            raise ConstructionMapV32Error(
                f"master line {line_number} source identity is absent"
            )
        source_identity = (artifact_id, record_id)
        if projected is None:
            unmapped_ids.append(record_id)
            if source_identity in added_identities:
                added_unmapped_ids.append(record_id)
            continue
        mapped.append(projected)
        values = dict(zip(FIELDS, projected, strict=True))
        tiers[str(values["tier"])] += 1
        statuses[str(values["normalized_status"] or "unknown")] += 1
        kinds[str(values["observation_kind"] or "unknown")] += 1
        countries[str(values["country"] or values["country_iso_a3"] or "Unknown")] += 1
        sources[str(values["source_artifact_id"] or "unknown")] += 1
        any_role = any(values[key] is not None for key in CORE_ROLE_KEYS) or bool(
            values["source_role_tags"]
        )
        mapped_rows_with_any_role += any_role
        mapped_replacement_rows += source_identity[0] == "epoch-official-open-seed-v97"
    declared = master_manifest.get("row_counts", {}).get("total")
    if total != declared:
        raise ConstructionMapV32Error(
            f"master manifest declares {declared} rows but JSONL has {total}"
        )
    if len(added_source_record_ids) != 332:
        raise ConstructionMapV32Error("v97 additive replacement boundary changed")
    summary = {
        "added_replacement_rows_unmapped": len(added_unmapped_ids),
        "added_replacement_unmapped_source_record_ids_sha256": _id_set_digest(
            added_unmapped_ids
        ),
        "default_visible_rows": sum(tiers[tier] for tier in DEFAULT_VISIBLE_TIERS),
        "default_visible_tiers": list(DEFAULT_VISIBLE_TIERS),
        "mapped_by_tier": {tier: tiers[tier] for tier in ("A", "B", "C")},
        "mapped_replacement_rows": mapped_replacement_rows,
        "mapped_rows": len(mapped),
        "mapped_rows_with_any_role": mapped_rows_with_any_role,
        "master_rows": total,
        "unmapped_rows": len(unmapped_ids),
        "unmapped_source_record_ids_sha256": _id_set_digest(unmapped_ids),
    }
    if expected_projection is not None and summary != dict(expected_projection):
        raise ConstructionMapV32Error(
            f"map projection differs from strict v32 definition: {summary!r}"
        )
    coverage = {
        "counts": {
            "mapped_observation_rows": len(mapped),
            "mapped_replacement_rows": mapped_replacement_rows,
            "mapped_rows_with_any_role": mapped_rows_with_any_role,
            "master_observation_rows": total,
            "unique_physical_site_count": None,
            "unmapped_observation_rows": len(unmapped_ids),
        },
        "freshness": {
            "historical_status_warning": (
                "Statuses are historical source observations; inclusion does not "
                "prove that construction persisted after reported_status_date."
            )
        },
        "mapped_counts": {
            "by_country": dict(sorted(countries.items())),
            "by_normalized_status": dict(sorted(statuses.items())),
            "by_observation_kind": dict(sorted(kinds.items())),
            "by_source_artifact": dict(sorted(sources.items())),
            "by_tier": dict(sorted(tiers.items())),
        },
        "projection": summary,
        "scope": MAP_SCOPE,
        "schema_version": SCHEMA_VERSION,
    }
    index = {
        "attribution": [
            "Source attribution and license are retained per observation",
            "Role fields are exact source strings, not inferred relationships",
            "OpenStreetMap contributors where source rows identify OpenStreetMap",
            "Contains modified Copernicus Sentinel data for linked imagery reviews",
        ],
        "fields": list(FIELDS),
        "format": FORMAT,
        "generated_at": GENERATED_AT,
        "master_id": master_manifest.get("master_id"),
        "master_manifest_sha256": master_manifest_sha256,
        "rows": mapped,
        "schema_version": SCHEMA_VERSION,
        "scope": MAP_SCOPE,
    }
    return index, coverage


_core_build_index = build_index_v32


def _map_rows(path: Path) -> dict[str, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise ConstructionMapV32Error(f"map index must be a regular file: {path}")
    try:
        index = json.loads(gzip.decompress(path.read_bytes()))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConstructionMapV32Error(f"map index is invalid: {path}") from error
    fields = index.get("fields")
    rows = index.get("rows")
    if fields != list(FIELDS) or not isinstance(rows, list):
        raise ConstructionMapV32Error("accepted map v31 row schema changed")
    result: dict[str, dict[str, Any]] = {}
    source_identities: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ConstructionMapV32Error("accepted map v31 row shape changed")
        record = dict(zip(fields, row, strict=True))
        row_id = record.get("row_id")
        artifact_id = record.get("source_artifact_id")
        record_id = record.get("source_record_id")
        source_identity = (artifact_id, record_id)
        if (
            not isinstance(row_id, str)
            or row_id in result
            or not all(isinstance(value, str) and value for value in source_identity)
            or source_identity in source_identities
        ):
            raise ConstructionMapV32Error("accepted map v31 row identity changed")
        result[row_id] = record
        source_identities.add(source_identity)
    return result


def _master_record_ids(path: Path) -> set[str]:
    """Return globally unique row IDs; bare source IDs are not master identity."""

    result: set[str] = set()
    for line_number, row in enumerate(_core_master_rows(path), start=1):
        row_id = row.get("row_id")
        if not isinstance(row_id, str) or row_id in result:
            raise ConstructionMapV32Error(f"master row {line_number} row ID changed")
        result.add(row_id)
    return result


def _projection_from_master(
    master_directory: Path,
    master_definition_path: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    master_generated_at = _master_generated_at(master_definition_path)
    manifest, manifest_raw = _regular_json(
        master_directory / MANIFEST_FILENAME, "master v32 manifest"
    )
    with (
        master_v32._prospective_identity_mode(False),
        _runtime_timestamps("2099-01-01T00:00:01Z", master_generated_at),
    ):
        try:
            master_v32.validate_construction_master_v32(
                master_directory,
                definition_path=master_definition_path,
                reproduce=False,
                allow_prospective_identity=False,
            )
        except master_v32.ConstructionMasterV32Error as error:
            raise ConstructionMapV32Error(str(error)) from error
        added = _core_added_source_record_ids(master_definition_path)
        row_ids: set[str] = set()
        source_identities: set[tuple[str, str]] = set()
        replacement_record_ids: set[str] = set()
        inherited_source_identities: set[tuple[str, str]] = set()
        inherited_row_ids: set[str] = set()
        bare_artifacts: defaultdict[str, set[str]] = defaultdict(set)

        def rows() -> Iterator[Mapping[str, Any]]:
            for line_number, row in enumerate(
                _core_master_rows(master_directory / "construction-master.jsonl"),
                start=1,
            ):
                source = row.get("source")
                row_id = row.get("row_id")
                artifact_id = (
                    source.get("artifact_id") if isinstance(source, Mapping) else None
                )
                record_id = (
                    source.get("record_id") if isinstance(source, Mapping) else None
                )
                if (
                    not isinstance(row_id, str)
                    or row_id in row_ids
                    or not isinstance(artifact_id, str)
                    or not artifact_id
                    or not isinstance(record_id, str)
                    or not record_id
                    or (artifact_id, record_id) in source_identities
                ):
                    raise ConstructionMapV32Error(
                        f"candidate master row {line_number} identity changed"
                    )
                row_ids.add(row_id)
                source_identities.add((artifact_id, record_id))
                bare_artifacts[record_id].add(artifact_id)
                if artifact_id == "epoch-official-open-seed-v97":
                    replacement_record_ids.add(record_id)
                else:
                    inherited_source_identities.add((artifact_id, record_id))
                    inherited_row_ids.add(row_id)
                yield row

        index, coverage = build_index_v32(
            rows(),
            master_manifest=manifest,
            master_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            added_source_record_ids=added,
            expected_projection=None,
        )
    collisions = {
        record_id
        for record_id, artifacts in bare_artifacts.items()
        if len(artifacts) > 1
    }
    if collisions != EXPECTED_BARE_SOURCE_RECORD_COLLISIONS or any(
        bare_artifacts[record_id] != {"epoch-official-open-seed-v97", "global-open-v3"}
        for record_id in collisions
    ):
        raise ConstructionMapV32Error("v32 bare source-record collision set changed")
    if (
        len(row_ids) != 109_443
        or len(source_identities) != 109_443
        or len(bare_artifacts) != 109_439
        or len(replacement_record_ids) != 531
        or len(inherited_source_identities) != 108_912
    ):
        raise ConstructionMapV32Error("v32 structured master identity counts changed")
    projected: dict[str, dict[str, Any]] = {}
    projected_bare_ids: set[str] = set()
    for values in index["rows"]:
        row = dict(zip(FIELDS, values, strict=True))
        row_id = row["row_id"]
        record_id = row["source_record_id"]
        if (
            row_id in projected
            or record_id in projected_bare_ids
            or not isinstance(row_id, str)
            or not isinstance(record_id, str)
        ):
            raise ConstructionMapV32Error("candidate mapped row identity repeats")
        projected[row_id] = row
        projected_bare_ids.add(record_id)
    inventory = {
        "inherited_row_ids": frozenset(inherited_row_ids),
        "inherited_source_identities": frozenset(inherited_source_identities),
        "replacement_record_ids": frozenset(replacement_record_ids),
        "row_ids": frozenset(row_ids),
        "source_identities": frozenset(source_identities),
    }
    return dict(coverage["projection"]), projected, inventory


def _predecessor_master_inventory() -> dict[str, Any]:
    row_ids: set[str] = set()
    source_identities: set[tuple[str, str]] = set()
    replacement_record_ids: set[str] = set()
    inherited_source_identities: set[tuple[str, str]] = set()
    inherited_row_ids: set[str] = set()
    path = (
        ROOT / "construction_master/2026-07-21-public-open-v31/"
        "construction-master.jsonl"
    )
    for line_number, row in enumerate(_core_master_rows(path), start=1):
        source = row.get("source")
        row_id = row.get("row_id")
        artifact_id = source.get("artifact_id") if isinstance(source, Mapping) else None
        record_id = source.get("record_id") if isinstance(source, Mapping) else None
        if (
            not isinstance(row_id, str)
            or row_id in row_ids
            or not isinstance(artifact_id, str)
            or not isinstance(record_id, str)
            or (artifact_id, record_id) in source_identities
        ):
            raise ConstructionMapV32Error(
                f"predecessor master row {line_number} identity changed"
            )
        row_ids.add(row_id)
        source_identities.add((artifact_id, record_id))
        if artifact_id == "epoch-official-open-seed-v86":
            replacement_record_ids.add(record_id)
        else:
            inherited_source_identities.add((artifact_id, record_id))
            inherited_row_ids.add(row_id)
    return {
        "inherited_row_ids": frozenset(inherited_row_ids),
        "inherited_source_identities": frozenset(inherited_source_identities),
        "replacement_record_ids": frozenset(replacement_record_ids),
        "row_ids": frozenset(row_ids),
        "source_identities": frozenset(source_identities),
    }


def _assert_exact_v31_delta(
    projected: Mapping[str, Mapping[str, Any]], inventory: Mapping[str, Any]
) -> None:
    old_projected = _map_rows(PREDECESSOR_BUNDLE / INDEX_FILENAME)
    old_inventory = _predecessor_master_inventory()
    if (
        inventory["inherited_row_ids"] != old_inventory["inherited_row_ids"]
        or inventory["inherited_source_identities"]
        != old_inventory["inherited_source_identities"]
    ):
        raise ConstructionMapV32Error("master v32 changed an inherited core row")
    old_replacement_ids = old_inventory["replacement_record_ids"]
    replacement_ids = inventory["replacement_record_ids"]
    additions = replacement_ids - old_replacement_ids
    if (
        old_replacement_ids - replacement_ids
        or additions != NEW_MASTER_RECORD_IDS
        or _id_set_digest(additions) != NEW_MASTER_RECORD_IDS_SHA256
    ):
        raise ConstructionMapV32Error(
            "master v32 replacement delta is not exactly 62 additive v97 rows"
        )

    old_core = {
        row_id: row
        for row_id, row in old_projected.items()
        if row["source_artifact_id"] != "epoch-official-open-seed-v86"
    }
    new_core = {
        row_id: row
        for row_id, row in projected.items()
        if row["source_artifact_id"] != "epoch-official-open-seed-v97"
    }
    if new_core != old_core or len(new_core) != 108_893:
        raise ConstructionMapV32Error("map v32 changed an inherited mapped row")
    old_replacement = {
        row["source_record_id"]: row
        for row in old_projected.values()
        if row["source_artifact_id"] == "epoch-official-open-seed-v86"
    }
    new_replacement = {
        row["source_record_id"]: row
        for row in projected.values()
        if row["source_artifact_id"] == "epoch-official-open-seed-v97"
    }
    old_ids = set(old_replacement)
    new_ids = set(new_replacement)
    if (
        len(old_ids) != 115
        or _id_set_digest(old_ids) != REWRITTEN_MAPPED_SOURCE_RECORD_IDS_SHA256
        or old_ids - new_ids
        or new_ids - old_ids != NEW_COORDINATE_MAPPING_IDS
    ):
        raise ConstructionMapV32Error("map v32 replacement mapped-row delta changed")
    for record_id, old in old_replacement.items():
        current = dict(new_replacement[record_id])
        current.update(
            {
                "row_id": old["row_id"],
                "source_artifact_id": old["source_artifact_id"],
                "source_release_id": old["source_release_id"],
            }
        )
        if current != old:
            raise ConstructionMapV32Error(
                f"map v32 changed a common replacement row: {record_id}"
            )
    for record_id, coordinates in EXPECTED_NEW_COORDINATES.items():
        current = new_replacement[record_id]
        if (
            current["longitude"],
            current["latitude"],
        ) != coordinates:
            raise ConstructionMapV32Error(
                f"map v32 direct v97 coordinate changed: {record_id}"
            )
    if (
        _row_projection_digest(new_replacement.values())
        != REPLACEMENT_MAPPED_PROJECTION_SHA256
    ):
        raise ConstructionMapV32Error("map v32 replacement projection changed")


_assert_exact_v29_delta = _assert_exact_v31_delta

_carrier_definition_document = globals()["definition_document"]
_carrier_prepare_candidate = globals()["prepare_candidate_construction_map_v32"]
_carrier_validate_candidate = globals()["validate_candidate_construction_map_v32"]
_carrier_validate_public = globals()["validate_construction_map_v32"]
_carrier_write_public = globals()["write_construction_map_v32"]


def definition_document(
    generated_at: str,
    *,
    master_directory: str | Path = MASTER,
    master_definition_path: str | Path = MASTER_DEFINITION,
) -> dict[str, Any]:
    """Bind public definition defaults to the dated v32 master paths."""

    return _carrier_definition_document(
        generated_at,
        master_directory=master_directory,
        master_definition_path=master_definition_path,
    )


def validate_construction_map_v32(
    directory: str | Path = BUNDLE,
    *,
    master_directory: str | Path = MASTER,
    master_definition_path: str | Path = MASTER_DEFINITION,
    map_definition_path: str | Path = DEFINITION,
    replay_count: int = 2,
    require_accepted_master: bool = True,
    require_frozen: bool = True,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    """Validate against the dated v32 public paths unless explicitly overridden."""

    return _carrier_validate_public(
        directory,
        master_directory=master_directory,
        master_definition_path=master_definition_path,
        map_definition_path=map_definition_path,
        replay_count=replay_count,
        require_accepted_master=require_accepted_master,
        require_frozen=require_frozen,
        validation_wall_clock=validation_wall_clock,
    )


def write_construction_map_v32(
    master_directory: str | Path = MASTER,
    output_directory: str | Path = BUNDLE,
    *,
    master_definition_path: str | Path = MASTER_DEFINITION,
    map_definition_path: str | Path = DEFINITION,
    generated_at: str,
    freeze: bool = True,
) -> dict[str, Any]:
    """Publish only the dated v32 public definition and bundle paths."""

    return _carrier_write_public(
        master_directory,
        output_directory,
        master_definition_path=master_definition_path,
        map_definition_path=map_definition_path,
        generated_at=generated_at,
        freeze=freeze,
    )


build_construction_map_v32 = write_construction_map_v32


@contextmanager
def _live_master_mode() -> Iterator[None]:
    """Keep private map work on the same live identity closure as public defaults."""

    with master_v32._prospective_identity_mode(False):
        yield


def prepare_candidate_construction_map_v32(
    generated_at: str = MAP_GENERATED_AT,
) -> tuple[Path, Path]:
    """Build a private map candidate against the pinned private master."""

    with _live_master_mode():
        return _carrier_prepare_candidate(generated_at)


def validate_candidate_construction_map_v32(
    definition_stage: str | Path,
    bundle_stage: str | Path,
    *,
    validation_wall_clock: datetime | None = None,
) -> dict[str, Any]:
    with _live_master_mode():
        return _carrier_validate_candidate(
            definition_stage,
            bundle_stage,
            validation_wall_clock=validation_wall_clock,
        )


__all__ = [
    "BUNDLE",
    "BUNDLE_FILES",
    "CANDIDATE_BUNDLE_STAGE",
    "CANDIDATE_DEFINITION_SHA256",
    "CANDIDATE_DEFINITION_STAGE",
    "CANDIDATE_MANIFEST_SHA256",
    "CANDIDATE_MASTER",
    "CANDIDATE_MASTER_DEFINITION",
    "CANDIDATE_MASTER_GENERATED_AT",
    "CANDIDATE_MASTER_TRANSACTION",
    "CANDIDATE_TREE_SHA256",
    "DEFINITION",
    "EXPECTED_BARE_SOURCE_RECORD_COLLISIONS",
    "EXPECTED_NEW_COORDINATES",
    "EXPECTED_PROJECTION",
    "FIELDS",
    "MAP_GENERATED_AT",
    "MAP_ID",
    "MAP_SCOPE",
    "MASTER",
    "MASTER_DEFINITION",
    "NEW_COORDINATE_MAPPING_IDS",
    "NEW_MASTER_RECORD_IDS",
    "ConstructionMapV32Error",
    "build_construction_map_v32",
    "definition_document",
    "derive_candidate_projection",
    "discard_candidate_construction_map_v32",
    "is_frozen_map_v32",
    "prepare_candidate_construction_map_v32",
    "publish_construction_map_v32",
    "validate_candidate_construction_map_v32",
    "validate_construction_map_v32",
    "validate_map_definition_v32",
    "write_construction_map_v32",
]
