"""Strict public-coverage v31 successor over accepted coverage v30.

V31 replaces the active open-seed, federation, identity, timeline, master, and
map gates with v86, v35, v11, v8, v31, and v31 respectively.  The source-scoped
coverage rows remain confined to the three federated children.  A second
satellite-review carrier is bound only as non-countable methodology support,
and timeline-v8 counts are exposed only as a bounded acceptance-gate summary.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from typing import Any, Iterator, Mapping, Sequence

from . import coverage_audit_v4 as legacy
from . import coverage_audit_v30 as predecessor
from .open_seed_v56 import promote_noreplace, tree_digest


ROOT = Path(__file__).resolve().parents[1]
BASE_DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v30.json"
BASE_BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v30"
DEFINITION = ROOT / "sources/coverage-audit-2026-07-21-public-open-v31.json"
BUNDLE = ROOT / "audits/2026-07-21-public-open-coverage-v31"

V86_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v86.json"
V86_RELEASE = ROOT / "releases/2026-07-21-open-seed-v86"
FEDERATION_DEFINITION = ROOT / "sources/federation-2026-07-21-public-open-v35.json"
FEDERATION_BUNDLE = ROOT / "federated_indexes/2026-07-21-public-open-v35"
IDENTITY_DEFINITION = (
    ROOT / "sources/exact-identity-decisions-2026-07-21-public-open-v11.json"
)
IDENTITY_BUNDLE = ROOT / "exact_identity_decisions/2026-07-21-public-open-v11"
TIMELINE_DEFINITION = (
    ROOT / "sources/construction-timeline-2026-07-21-public-open-v8.json"
)
TIMELINE_BUNDLE = ROOT / "construction_timelines/2026-07-21-public-open-v8"
MASTER_DEFINITION = (
    ROOT / "sources/construction-master-2026-07-21-public-open-v31.json"
)
MASTER_BUNDLE = ROOT / "construction_master/2026-07-21-public-open-v31"
MAP_DEFINITION = ROOT / "sources/construction-map-2026-07-21-public-open-v31.json"
MAP_BUNDLE = ROOT / "construction_maps/2026-07-21-public-open-v31"
V83_REVIEW_BUNDLE = (
    ROOT
    / "satellite_change_reviews/"
    "2026-07-21-open-seed-v83-active-unreviewed-single-68-review-v1"
)
PUBLICATION_LOCK = ROOT / ".coverage-audit-v31.lock"

AUDIT_ID = "public-open-coverage-v31"
OLD_RELEASE_ID = "epoch-official-open-seed-v83"
NEW_RELEASE_ID = "epoch-official-open-seed-v86"
V83_SUPPORT_ID = (
    "2026-07-21-open-seed-v83-active-unreviewed-single-68-review-v1"
)

BASE_DEFINITION_SHA256 = (
    "8d23100aaf465a5464f3945cb4d55d4fe2b370f3ce5a8ebc6e493acdcd141eba"
)
BASE_TREE_SHA256 = (
    "ca7212059190432d407908008e06a684380b04fe46bef75d4201bd7c045b0ed4"
)
BASE_MANIFEST_SHA256 = (
    "5bd7257085f52258c5187f38f811148e8edb9a38d212fc44104f9368bf769b78"
)
V86_DEFINITION_SHA256 = (
    "2a2f0cded9e95efd2ab90cbde1d8ad11306b14f019f42cb14086fb80a63fb25d"
)
V86_MANIFEST_SHA256 = (
    "5bc24a692e2d4fc793192f03bd23fa921e434661a0675e6612370d354cf11488"
)
V86_TREE_SHA256 = (
    "593fe37f16cc81bd6e2011c9b893251be4041dc54376ffec2f743a510fb4d4de"
)
FEDERATION_DEFINITION_SHA256 = (
    "7c6f9c3d7892d86974b20ba694c24695c0a0d9a4fd91d830e9824ad2db49903f"
)
FEDERATION_INDEX_SHA256 = (
    "f7cf31d905bf497a6bc7ba3db7f22fb8e281e7b1452e1f2853ea79af1d9ea802"
)
FEDERATION_MANIFEST_SHA256 = (
    "7396e2854abd73f0209a02f13ab5b31fa79af6250059b92dff484442d61fe388"
)
FEDERATION_TREE_SHA256 = (
    "37bb03f650d2d57823fbc226c471866a4997711ef201440d10dbc4ef6c14f5ba"
)
IDENTITY_DEFINITION_SHA256 = (
    "658ca591e25045245e2709564cd11a3cdd7d338f5be11913aca4ba54a6656a40"
)
IDENTITY_MANIFEST_SHA256 = (
    "cd54ee06c75272974d2ba43859226b61965d04c7ca6c515d19e44447fe48cbb9"
)
IDENTITY_TREE_SHA256 = (
    "b25b7b568df098a0405452cf3c0608d9d840ace15af120625f7650423d22f6d9"
)
TIMELINE_DEFINITION_SHA256 = (
    "9f67b19847aadf326cdd3701c3e4a8aa5309a9b59c58d3d749a6369fdfc3ec97"
)
TIMELINE_MANIFEST_SHA256 = (
    "4a71dd94b0ab97a8b0e9add0b4688bececec285832de991f7c71a23a7dc8a02d"
)
TIMELINE_TREE_SHA256 = (
    "f3231947d338bd201bc416dd7d78cba51e5193d484a8fb84a0f2bab2b4b65f12"
)
MASTER_DEFINITION_SHA256 = (
    "a1b4761820aa6adb3406d5ff3ad6bc52898309fed72fe4f857aca01197597c25"
)
MASTER_MANIFEST_SHA256 = (
    "8d2cb42034ca040c3341582ee0ac125013f208a6712c211fb334943763412c7e"
)
MASTER_TREE_SHA256 = (
    "90790b8d72592bd8c1a9971576cc9bb27a4cbc334b16b0b13246e1ed2639b9da"
)
MAP_DEFINITION_SHA256 = (
    "a8c15cc5f78e3b0c2b7a40b46b496b7c3561662aefda237424dc1c4b6d138f97"
)
MAP_MANIFEST_SHA256 = (
    "5305dd9c637a74dbd2a3b355e19185e1fd9f49b815b8a9a51786ce8428b33631"
)
MAP_INDEX_SHA256 = (
    "a854c2cce01273484277795d4feae80784cce67dde2f8e6c9beeb065dd8af1d7"
)
MAP_TREE_SHA256 = (
    "73e913f53287a2474274b6ff16daf10dcb8cd2ceceadc766e9aedd9ba3852973"
)
V83_REVIEW_MANIFEST_SHA256 = (
    "54229a5fa1fe29eef212ac4263563c776cfd12a5df11b7d0ecd22b6eca034399"
)
V83_REVIEW_TREE_SHA256 = (
    "20d577cf384a37994e7ecc6eb5494d5e3e1e790e505b7b867866292b4297fbec"
)
V83_REVIEW_TREE_BYTES = 360_993
V83_REVIEW_MEMBER_PINS = {
    "ATTRIBUTION.txt": (
        305,
        "ea2508601c684b7814ec6eae3285deb8623d18d06517d1b525d3b208587ef935",
    ),
    "README.md": (
        1_093,
        "74cd732b7f801324f39aecc1e04b1a3a26c47c86cfa95db6888ec1ab99a70f57",
    ),
    "analyst-reviews.jsonl": (
        284_085,
        "66cef2ffa8067fc729dfbc5097049623688cca4e5a6fd46341b0b1feb05e1603",
    ),
    "blind-decisions.json": (
        28_320,
        "dea4ce947fb6d4debbdd4bd71c319b1011ac81397318a61909991e28b62ebec3",
    ),
    "blind-review-part-a.json": (
        14_135,
        "2c752d82b541f2793bb02a4a4a3d916b6131f500f06452ae52721f70279bc396",
    ),
    "blind-review-part-b.json": (
        13_230,
        "ae62a835bef166687bbc81653bf8c57bf55dd58d98801a3ced938512d315a11f",
    ),
    "definition.json": (
        7_659,
        "7ab24635cb6fd3bc8a64740f6318a4b21bcbd03b74e243a3489cc3fbb415a2f6",
    ),
    "manifest.json": (5_622, V83_REVIEW_MANIFEST_SHA256),
    "manifest.sha256": (
        80,
        "7f178b876ad741f5749099cc5b21b2c341d00024d453835765d96232c087f77d",
    ),
    "summary.json": (
        6_464,
        "275ce8feab06f18d6dd3c17e7f645d00631b5759fb5399e2436a671964ab3bc8",
    ),
}
EXPECTED_REVIEW_ACCOUNTING = {
    "decision_rows": 68,
    "unique_exact_visual_evidence_sets": 65,
    "retained_decision_rows": 47,
    "unique_retained_exact_visual_evidence_sets": 44,
    "rejected_decision_rows": 21,
    "exact_duplicate_groups": 3,
    "promotions": 0,
}
EXPECTED_EXACT_DUPLICATE_GROUPS = [
    {
        "blind_ids": ["V83-X008", "V83-X041"],
        "visual_evidence_set_sha256": (
            "116499270c5d52dec49a674211b1f594b1c6a035c984bb1db0f977ef4cfce66c"
        ),
    },
    {
        "blind_ids": ["V83-X021", "V83-X027"],
        "visual_evidence_set_sha256": (
            "c7a84ad205d2a3858dfe2cd61cc135993c44cdf672bb78dca30f16b91a2a03bc"
        ),
    },
    {
        "blind_ids": ["V83-X025", "V83-X053"],
        "visual_evidence_set_sha256": (
            "61e1b3118ccdf8f6d2ebaed215e1ad4c9870d75554a78852ee2241bd8c1bc91f"
        ),
    },
]
EXPECTED_TIMELINE_GATE = {
    "timelines": 517,
    "observations": 537,
    "multi_observation_timelines": 20,
}
EXPECTED_COVERAGE_COUNTS = {
    "confirmed_duplicate_relationships": None,
    "coverage_groups": 979,
    "methodology_support_artifacts": 2,
    "open_gaps": 4_582,
    "source_scoped_entity_records": 16_352,
    "unique_physical_sites": None,
    "v57_review_jobs": 74,
    "v57_review_views": 71,
    "v83_decision_rows": 68,
    "v83_exact_duplicate_groups": 3,
    "v83_promotions": 0,
    "v83_rejected_decision_rows": 21,
    "v83_retained_decision_rows": 47,
    "v83_unique_exact_visual_evidence_sets": 65,
    "v83_unique_retained_exact_visual_evidence_sets": 44,
}
FORBIDDEN_FUTURE_TOKENS = (
    b"open-seed-v87",
    b"open-seed-v88",
    b"public-open-v36",
    b"federation-v36",
)

BUILDER_PATH = Path(__file__).resolve()
ROOT_SHIM_PATH = ROOT / "coverage_audit_v31.py"
CLI_PATH = ROOT / "scripts/build_coverage_audit_v31.py"
CARRIER_PATH = Path(__file__).with_name("coverage_audit_v4.py")


class CoverageAuditV31Error(RuntimeError):
    """Raised when the bounded v31 transition cannot be proved."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: object) -> bytes:
    return predecessor._canonical_json(value)


def _parse_utc(value: str, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CoverageAuditV31Error(f"{label} must use canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError as error:
        raise CoverageAuditV31Error(f"{label} must use canonical UTC") from error
    canonical = {
        parsed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    if value not in canonical:
        raise CoverageAuditV31Error(f"{label} must use canonical UTC")
    return parsed


def _require_checkpoint(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise CoverageAuditV31Error(f"{label} is not a regular file: {path}")
    actual = _sha256(path)
    if actual != expected:
        raise CoverageAuditV31Error(
            f"{label} checkpoint changed: expected {expected}, got {actual}"
        )


def _require_tree(path: Path, expected: str, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise CoverageAuditV31Error(f"{label} is not a directory: {path}")
    actual = tree_digest(path)
    if actual != expected:
        raise CoverageAuditV31Error(
            f"{label} tree changed: expected {expected}, got {actual}"
        )


def _definition_timestamp(path: Path, keys: Sequence[str], label: str) -> datetime:
    value: Any = json.loads(path.read_bytes())
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise CoverageAuditV31Error(f"{label} timestamp field is absent")
        value = value[key]
    if not isinstance(value, str):
        raise CoverageAuditV31Error(f"{label} timestamp is not a string")
    return _parse_utc(value, label=f"{label} timestamp")


def _require_frozen_dependency(
    definition: Path,
    bundle: Path,
    timestamp_keys: Sequence[str],
    label: str,
    *,
    definition_is_member: bool = False,
) -> datetime:
    timestamp = _definition_timestamp(definition, timestamp_keys, label)
    for path in (definition, bundle, *bundle.rglob("*")):
        if path.is_symlink():
            raise CoverageAuditV31Error(f"{label} contains a symlink: {path}")
        expected_mode = 0o555 if path.is_dir() else 0o444
        metadata = path.stat()
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise CoverageAuditV31Error(f"{label} is not frozen: {path}")
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > timestamp.timestamp() + 0.000_001:
            raise CoverageAuditV31Error(f"{label} post-dates its timestamp: {path}")
    final_roots = (bundle,) if definition_is_member else (definition, bundle)
    for root in final_roots:
        if root.stat().st_ctime + 0.000_001 < timestamp.timestamp():
            raise CoverageAuditV31Error(f"{label} final rename predates its timestamp")
    return timestamp


def _dependency_times() -> tuple[tuple[str, datetime], ...]:
    return (
        (
            "accepted coverage v30",
            _require_frozen_dependency(
                BASE_DEFINITION, BASE_BUNDLE, ("generated_at",), "coverage v30"
            ),
        ),
        (
            "accepted open-seed v86",
            _require_frozen_dependency(
                V86_DEFINITION, V86_RELEASE, ("build", "recorded_at"), "open-seed v86"
            ),
        ),
        (
            "accepted federation v35",
            _require_frozen_dependency(
                FEDERATION_DEFINITION,
                FEDERATION_BUNDLE,
                ("generated_at",),
                "federation v35",
            ),
        ),
        (
            "accepted identity v11",
            _require_frozen_dependency(
                IDENTITY_DEFINITION,
                IDENTITY_BUNDLE,
                ("recorded_at",),
                "identity v11",
            ),
        ),
        (
            "accepted timeline v8",
            _require_frozen_dependency(
                TIMELINE_DEFINITION,
                TIMELINE_BUNDLE,
                ("generated_at",),
                "timeline v8",
            ),
        ),
        (
            "accepted master v31",
            _require_frozen_dependency(
                MASTER_DEFINITION,
                MASTER_BUNDLE,
                ("generated_at",),
                "master v31",
            ),
        ),
        (
            "accepted map v31",
            _require_frozen_dependency(
                MAP_DEFINITION, MAP_BUNDLE, ("generated_at",), "map v31"
            ),
        ),
        (
            "accepted v83 review support",
            _require_frozen_dependency(
                V83_REVIEW_BUNDLE / "definition.json",
                V83_REVIEW_BUNDLE,
                ("generated_at",),
                "v83 review support",
                definition_is_member=True,
            ),
        ),
    )


def _require_inputs() -> None:
    checks = (
        (BASE_DEFINITION, BASE_DEFINITION_SHA256, "coverage v30 definition"),
        (BASE_BUNDLE / "manifest.json", BASE_MANIFEST_SHA256, "coverage v30 manifest"),
        (V86_DEFINITION, V86_DEFINITION_SHA256, "open-seed v86 definition"),
        (V86_RELEASE / "manifest.json", V86_MANIFEST_SHA256, "open-seed v86 manifest"),
        (FEDERATION_DEFINITION, FEDERATION_DEFINITION_SHA256, "federation v35 definition"),
        (FEDERATION_BUNDLE / "federated-index.json", FEDERATION_INDEX_SHA256, "federation v35 index"),
        (FEDERATION_BUNDLE / "manifest.json", FEDERATION_MANIFEST_SHA256, "federation v35 manifest"),
        (IDENTITY_DEFINITION, IDENTITY_DEFINITION_SHA256, "identity v11 definition"),
        (IDENTITY_BUNDLE / "manifest.json", IDENTITY_MANIFEST_SHA256, "identity v11 manifest"),
        (TIMELINE_DEFINITION, TIMELINE_DEFINITION_SHA256, "timeline v8 definition"),
        (TIMELINE_BUNDLE / "manifest.json", TIMELINE_MANIFEST_SHA256, "timeline v8 manifest"),
        (MASTER_DEFINITION, MASTER_DEFINITION_SHA256, "master v31 definition"),
        (MASTER_BUNDLE / "manifest.json", MASTER_MANIFEST_SHA256, "master v31 manifest"),
        (MAP_DEFINITION, MAP_DEFINITION_SHA256, "map v31 definition"),
        (MAP_BUNDLE / "manifest.json", MAP_MANIFEST_SHA256, "map v31 manifest"),
        (MAP_BUNDLE / "construction-map-index.json.gz", MAP_INDEX_SHA256, "map v31 index"),
        (V83_REVIEW_BUNDLE / "manifest.json", V83_REVIEW_MANIFEST_SHA256, "v83 review manifest"),
    )
    for path, digest, label in checks:
        _require_checkpoint(path, digest, label)
    for path, digest, label in (
        (BASE_BUNDLE, BASE_TREE_SHA256, "accepted coverage v30"),
        (V86_RELEASE, V86_TREE_SHA256, "accepted open-seed v86"),
        (FEDERATION_BUNDLE, FEDERATION_TREE_SHA256, "accepted federation v35"),
        (IDENTITY_BUNDLE, IDENTITY_TREE_SHA256, "accepted identity v11"),
        (TIMELINE_BUNDLE, TIMELINE_TREE_SHA256, "accepted timeline v8"),
        (MASTER_BUNDLE, MASTER_TREE_SHA256, "accepted master v31"),
        (MAP_BUNDLE, MAP_TREE_SHA256, "accepted map v31"),
        (V83_REVIEW_BUNDLE, V83_REVIEW_TREE_SHA256, "accepted v83 review support"),
    ):
        _require_tree(path, digest, label)
    _dependency_times()


def _require_dependencies_before(target: datetime) -> None:
    for label, timestamp in _dependency_times():
        if timestamp >= target:
            raise CoverageAuditV31Error(
                f"{label} is not temporally prior to coverage v31 generated_at"
            )


def _v83_support_definition() -> dict[str, Any]:
    return {
        "accounting": {
            **EXPECTED_REVIEW_ACCOUNTING,
            "exact_duplicate_group_members": EXPECTED_EXACT_DUPLICATE_GROUPS,
            "x052_x041_similarity": "reviewer_approximate_only_no_exact_deduplication",
        },
        "categories": ["computer_vision", "satellite_imagery"],
        "classification": "review_only_methodology_support",
        "closed_tree": {
            "directories": 1,
            "directory_mode": "0555",
            "file_bytes": V83_REVIEW_TREE_BYTES,
            "file_mode": "0444",
            "files": 10,
            "inventory_sha256": V83_REVIEW_TREE_SHA256,
            "schema_version": 1,
        },
        "directory": f"../satellite_change_reviews/{V83_SUPPORT_ID}",
        "members": {
            name: {"bytes": size, "sha256": digest}
            for name, (size, digest) in sorted(V83_REVIEW_MEMBER_PINS.items())
        },
        "scope": {
            "atlas_mutation": False,
            "child_evidence": False,
            "countable": False,
            "current_status_claim": False,
            "lifecycle_observations": False,
            "promoted": False,
            "row_provenance": False,
        },
        "support_id": V83_SUPPORT_ID,
    }


def definition_document(generated_at: str) -> dict[str, Any]:
    """Return the exact accepted-v30 to v31 definition transform."""

    parsed = _parse_utc(generated_at, label="coverage v31 generated_at")
    if generated_at != parsed.strftime("%Y-%m-%dT%H:%M:%SZ"):
        raise CoverageAuditV31Error(
            "coverage v31 generated_at must use canonical UTC seconds"
        )
    raw = BASE_DEFINITION.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_DEFINITION_SHA256:
        raise CoverageAuditV31Error("accepted coverage v30 definition changed")
    result = deepcopy(json.loads(raw))
    result["audit_id"] = AUDIT_ID
    result["generated_at"] = generated_at
    matches = [
        child for child in result["children"] if child["release_id"] == OLD_RELEASE_ID
    ]
    if len(matches) != 1:
        raise CoverageAuditV31Error("v30 open-seed child boundary changed")
    matches[0].update(
        {
            "expected_manifest_sha256": V86_MANIFEST_SHA256,
            "release_id": NEW_RELEASE_ID,
            "release_path": "../releases/2026-07-21-open-seed-v86",
        }
    )
    result["federated_index"] = {
        "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
        "path": "../federated_indexes/2026-07-21-public-open-v35",
    }
    replacements = 0
    for references in result["methodology_evidence_classification"].values():
        for reference in references:
            if reference["release_id"] == OLD_RELEASE_ID:
                reference["release_id"] = NEW_RELEASE_ID
                replacements += 1
    if replacements != 12:
        raise CoverageAuditV31Error(
            "v30 methodology-reference boundary changed: "
            f"expected 12, got {replacements}"
        )
    supports = result.get("methodology_support_artifacts")
    if (
        not isinstance(supports, list)
        or len(supports) != 1
        or supports[0].get("support_id")
        != "2026-07-20-open-seed-v57-active-review-v1"
    ):
        raise CoverageAuditV31Error("v30 methodology support boundary changed")
    supports.append(_v83_support_definition())
    claims = result.get("public_benchmark", {}).get("claims", [])
    base_claims = json.loads(BASE_DEFINITION.read_bytes())["public_benchmark"]["claims"]
    if claims != base_claims:
        raise CoverageAuditV31Error("v30 public benchmark text changed")
    encoded = _canonical_json(result)
    for token in FORBIDDEN_FUTURE_TOKENS:
        if token in encoded:
            raise CoverageAuditV31Error(
                f"future lineage token present: {token.decode('ascii')}"
            )
    return result


def _legacy_definition(document: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(document)
    supports = result["methodology_support_artifacts"]
    if len(supports) != 2 or supports[1]["support_id"] != V83_SUPPORT_ID:
        raise CoverageAuditV31Error("v31 support stripping boundary changed")
    result["methodology_support_artifacts"] = supports[:1]
    return result


def _exact_member(path: Path, size: int, digest: str, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CoverageAuditV31Error(f"{label} is not a regular file")
    raw = path.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise CoverageAuditV31Error(f"{label} changed")
    return raw


def _validate_v83_support() -> dict[str, Any]:
    if tree_digest(V83_REVIEW_BUNDLE) != V83_REVIEW_TREE_SHA256:
        raise CoverageAuditV31Error("v83 review support tree changed")
    members = {
        name: _exact_member(
            V83_REVIEW_BUNDLE / name, size, digest, f"v83 review member {name}"
        )
        for name, (size, digest) in V83_REVIEW_MEMBER_PINS.items()
    }
    if set(members) != {path.name for path in V83_REVIEW_BUNDLE.iterdir()}:
        raise CoverageAuditV31Error("v83 review support member inventory changed")
    manifest = json.loads(members["manifest.json"])
    summary = json.loads(members["summary.json"])
    combined = json.loads(members["blind-decisions.json"])
    rows = [json.loads(line) for line in members["analyst-reviews.jsonl"].splitlines()]
    if (
        manifest.get("review_id") != V83_SUPPORT_ID
        or manifest.get("format")
        != "datacenter-atlas-explicit-v83-combined-analyst-review"
        or summary.get("review_id") != V83_SUPPORT_ID
        or len(rows) != 68
        or len(combined.get("decisions", [])) != 68
        or any(value is not False for value in manifest.get("guardrails", {}).values())
    ):
        raise CoverageAuditV31Error("v83 review support identity changed")
    accounting = summary.get("accounting")
    decision_rows = accounting.get("decision_rows") if isinstance(accounting, dict) else None
    unique_sets = (
        accounting.get("unique_exact_visual_evidence_sets")
        if isinstance(accounting, dict)
        else None
    )
    flags = accounting.get("reviewer_similarity_flags") if isinstance(accounting, dict) else None
    approximate = next(
        (
            item
            for item in flags or []
            if item.get("reported_by") == "V83-X052"
            and item.get("reported_target") == "V83-X041"
        ),
        None,
    )
    exact_groups = accounting.get("exact_duplicate_groups") if isinstance(accounting, dict) else None
    if (
        decision_rows.get("total") != 68
        or decision_rows.get("promotion_dispositions")
        != {
            "rejected_for_site_promotion": 21,
            "retained_for_manual_followup": 47,
        }
        or unique_sets.get("total") != 65
        or unique_sets.get("promotion_dispositions")
        != {
            "rejected_for_site_promotion": 21,
            "retained_for_manual_followup": 44,
        }
        or exact_groups != EXPECTED_EXACT_DUPLICATE_GROUPS
        or not isinstance(approximate, dict)
        or approximate.get("exact_four_image_hash_match") is not False
        or approximate.get("counted_as_exact_duplicate") is not False
    ):
        raise CoverageAuditV31Error("v83 review exact-evidence accounting changed")
    return {
        "accounting": {
            **EXPECTED_REVIEW_ACCOUNTING,
            "exact_duplicate_group_members": EXPECTED_EXACT_DUPLICATE_GROUPS,
            "x052_x041_similarity": "reviewer_approximate_only_no_exact_deduplication",
        },
        "categories": ["computer_vision", "satellite_imagery"],
        "classification": "review_only_methodology_support",
        "closed_tree": _v83_support_definition()["closed_tree"],
        "directory": f"../satellite_change_reviews/{V83_SUPPORT_ID}",
        "format": manifest["format"],
        "guardrails": manifest["guardrails"],
        "members": _v83_support_definition()["members"],
        "reviewed_at": manifest["generated_at"],
        "schema_version": manifest["schema_version"],
        "scope": _v83_support_definition()["scope"],
        "status_semantics": "not_a_status_observation_current_status_unknown",
        "support_id": V83_SUPPORT_ID,
    }


def _timeline_gate() -> dict[str, Any]:
    definition = json.loads(TIMELINE_DEFINITION.read_bytes())
    expected = definition.get("expected")
    if not isinstance(expected, dict) or {
        "timelines": expected.get("entities_with_lifecycle_observations"),
        "observations": expected.get("raw_lifecycle_observations"),
        "multi_observation_timelines": expected.get("multi_observation_entities"),
    } != EXPECTED_TIMELINE_GATE:
        raise CoverageAuditV31Error("timeline-v8 bounded counts changed")
    return {
        **EXPECTED_TIMELINE_GATE,
        "definition_sha256": TIMELINE_DEFINITION_SHA256,
        "manifest_sha256": TIMELINE_MANIFEST_SHA256,
        "scope": {
            "current_status_inferred": False,
            "every_facility_coverage_claimed": False,
            "quarterly_2017_2032_parity_claimed": False,
            "row_provenance": False,
            "unique_physical_sites": None,
        },
        "tree_sha256": TIMELINE_TREE_SHA256,
    }


def _numeric_leaf_deltas(previous: Any, current: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(previous, dict) and isinstance(current, dict):
        for key in sorted(set(previous) | set(current)):
            path = f"{prefix}.{key}" if prefix else key
            result.update(
                _numeric_leaf_deltas(previous.get(key), current.get(key), path)
            )
    elif (
        isinstance(previous, (int, float))
        and not isinstance(previous, bool)
        and isinstance(current, (int, float))
        and not isinstance(current, bool)
        and previous != current
    ):
        result[prefix] = {
            "current": current,
            "delta": round(current - previous, 12),
            "previous": previous,
        }
    elif previous != current:
        result[prefix] = {"current": current, "previous": previous}
    return result


def _group_key(group: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        group.get("scope_type"),
        group.get("source_family"),
        group.get("country"),
        group.get("country_iso_a2"),
        group.get("country_iso_a3"),
    )


def _successor_delta(
    audit: Mapping[str, Any], gaps: Mapping[str, Any]
) -> dict[str, Any]:
    previous_audit = json.loads((BASE_BUNDLE / legacy.AUDIT_FILENAME).read_bytes())
    previous_gaps = json.loads((BASE_BUNDLE / legacy.GAP_REGISTRY_FILENAME).read_bytes())
    previous_unrelated = [
        row for row in previous_audit["groups"] if row["child_release"] != OLD_RELEASE_ID
    ]
    current_unrelated = [
        row for row in audit["groups"] if row["child_release"] != NEW_RELEASE_ID
    ]
    if previous_unrelated != current_unrelated:
        raise CoverageAuditV31Error("unrelated child coverage groups changed")
    previous_groups = {
        _group_key(row): row
        for row in previous_audit["groups"]
        if row["child_release"] == OLD_RELEASE_ID
    }
    current_groups = {
        _group_key(row): row
        for row in audit["groups"]
        if row["child_release"] == NEW_RELEASE_ID
    }
    group_deltas = []
    for key in sorted(set(previous_groups) | set(current_groups), key=str):
        old = previous_groups.get(key)
        new = current_groups.get(key)
        normalized_old = (
            {**old, "child_release": NEW_RELEASE_ID} if old is not None else None
        )
        changes = _numeric_leaf_deltas(normalized_old, new)
        if changes:
            group_deltas.append(
                {
                    "group_key": list(key),
                    "numeric_and_value_deltas": changes,
                }
            )
    previous_ids = {row["gap_id"] for row in previous_gaps["gaps"]}
    current_ids = {row["gap_id"] for row in gaps["gaps"]}
    return {
        "coverage_groups": {
            "current": len(audit["groups"]),
            "delta": len(audit["groups"]) - len(previous_audit["groups"]),
            "previous": len(previous_audit["groups"]),
        },
        "gap_id_changes": {
            "added": len(current_ids - previous_ids),
            "added_ids_sha256": hashlib.sha256(
                _canonical_json(sorted(current_ids - previous_ids))
            ).hexdigest(),
            "removed": len(previous_ids - current_ids),
            "removed_ids_sha256": hashlib.sha256(
                _canonical_json(sorted(previous_ids - current_ids))
            ).hexdigest(),
        },
        "gap_summary_deltas": _numeric_leaf_deltas(
            previous_gaps["summary"], gaps["summary"]
        ),
        "open_seed_group_deltas": group_deltas,
        "open_seed_groups": {
            "current": len(current_groups),
            "delta": len(current_groups) - len(previous_groups),
            "previous": len(previous_groups),
        },
        "totals_deltas": _numeric_leaf_deltas(
            previous_audit["totals"], audit["totals"]
        ),
        "unrelated_child_groups_byte_equivalent": True,
        "unrelated_child_groups_compared": len(previous_unrelated),
    }


@contextmanager
def _temporary_legacy_definition(document: Mapping[str, Any]) -> Iterator[Path]:
    descriptor, name = tempfile.mkstemp(
        prefix=".coverage-v31-legacy-", suffix=".json", dir=DEFINITION.parent
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_json(_legacy_definition(document)))
            stream.flush()
            os.fsync(stream.fileno())
        yield path
    finally:
        path.unlink(missing_ok=True)


def _implementation_pins() -> dict[str, Any]:
    result = {}
    for label, path in (
        ("coverage_audit_v4_carrier", CARRIER_PATH),
        ("cli", CLI_PATH),
        ("module", BUILDER_PATH),
        ("root_shim", ROOT_SHIM_PATH),
    ):
        raw = path.read_bytes()
        result[label] = {
            "bytes": len(raw),
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if label == "coverage_audit_v4_carrier":
            result[label].update(
                {
                    "adds_identity_claims": False,
                    "adds_lifecycle_claims": False,
                    "classification": "non_release_validator_dependency",
                    "contract": (
                        "federation_v35_geometry_non_inference_validation_only"
                    ),
                    "release_artifact": False,
                }
            )
    return result


def _acceptance_gates() -> dict[str, Any]:
    def frozen(
        definition: Path,
        timestamp_keys: Sequence[str],
        timestamp_field: str,
        pins: Mapping[str, str],
    ) -> dict[str, Any]:
        value: Any = json.loads(definition.read_bytes())
        for key in timestamp_keys:
            value = value[key]
        return {
            **pins,
            "frozen_modes": {
                "bundle_directory": "0555",
                "bundle_files": "0444",
                "definition": "0444",
            },
            "timestamp": {"field": timestamp_field, "value": value},
        }

    return {
        "construction_map_v31": frozen(
            MAP_DEFINITION,
            ("generated_at",),
            "generated_at",
            {
                "definition_sha256": MAP_DEFINITION_SHA256,
                "index_sha256": MAP_INDEX_SHA256,
                "manifest_sha256": MAP_MANIFEST_SHA256,
                "tree_sha256": MAP_TREE_SHA256,
            },
        ),
        "construction_master_v31": frozen(
            MASTER_DEFINITION,
            ("generated_at",),
            "generated_at",
            {
                "definition_sha256": MASTER_DEFINITION_SHA256,
                "manifest_sha256": MASTER_MANIFEST_SHA256,
                "tree_sha256": MASTER_TREE_SHA256,
            },
        ),
        "construction_timeline_v8": frozen(
            TIMELINE_DEFINITION,
            ("generated_at",),
            "generated_at",
            {
                "definition_sha256": TIMELINE_DEFINITION_SHA256,
                "manifest_sha256": TIMELINE_MANIFEST_SHA256,
                "tree_sha256": TIMELINE_TREE_SHA256,
            },
        ),
        "exact_identity_v11": frozen(
            IDENTITY_DEFINITION,
            ("recorded_at",),
            "recorded_at",
            {
                "definition_sha256": IDENTITY_DEFINITION_SHA256,
                "manifest_sha256": IDENTITY_MANIFEST_SHA256,
                "tree_sha256": IDENTITY_TREE_SHA256,
            },
        ),
        "federation_v35": frozen(
            FEDERATION_DEFINITION,
            ("generated_at",),
            "generated_at",
            {
                "definition_sha256": FEDERATION_DEFINITION_SHA256,
                "index_sha256": FEDERATION_INDEX_SHA256,
                "manifest_sha256": FEDERATION_MANIFEST_SHA256,
                "tree_sha256": FEDERATION_TREE_SHA256,
            },
        ),
        "open_seed_v86": frozen(
            V86_DEFINITION,
            ("build", "recorded_at"),
            "build.recorded_at",
            {
                "definition_sha256": V86_DEFINITION_SHA256,
                "manifest_sha256": V86_MANIFEST_SHA256,
                "tree_sha256": V86_TREE_SHA256,
            },
        ),
    }


def _report_v31(audit: Mapping[str, Any], gaps: Mapping[str, Any]) -> bytes:
    report_input = deepcopy(audit)
    supports = report_input["inputs"]["methodology_support_artifacts"]
    v83 = next(row for row in supports if row["support_id"] == V83_SUPPORT_ID)
    v83["counts"] = {"jobs": 68, "views": 65}
    text = legacy._report(report_input, gaps).decode("utf-8")
    old = (
        f"- `{V83_SUPPORT_ID}`: **68 jobs / 65 views**, schema v4, last-observed "
        "status semantics; every claim-creation and promotion guardrail remains false."
    )
    new = (
        f"- `{V83_SUPPORT_ID}`: **68 decisions / 65 unique exact four-image sets**; "
        "47 decisions are retained for manual follow-up, representing 44 unique "
        "retained sets, while 21 are rejected. Three exact duplicate groups are "
        "counted once; X052/X041 is approximate-only and is not deduplicated. This "
        "artifact is non-countable and non-promoted."
    )
    if old not in text:
        raise CoverageAuditV31Error("v31 support report anchor changed")
    text = text.replace(old, new, 1)
    anchor = "## SemiAnalysis public benchmark\n"
    carrier = (
        "## Validator carrier boundary\n\n"
        "The byte-pinned `coverage_audit_v4` carrier is a non-release validator "
        "dependency. Its only compatibility extension accepts federation v35's "
        "explicit geometry non-inference field; it creates no lifecycle claim, "
        "identity claim, or release artifact.\n\n"
    )
    timeline = (
        "## Bounded timeline gate evidence\n\n"
        "Accepted timeline v8 contains 517 source-scoped timelines, 537 dated "
        "observations, and 20 multi-observation timelines. These counts are a "
        "bounded acceptance-gate summary, not row provenance, current status, "
        "unique physical sites, or every-facility coverage.\n\n"
    )
    if anchor not in text:
        raise CoverageAuditV31Error("v31 timeline report anchor changed")
    return text.replace(anchor, carrier + timeline + anchor, 1).encode("utf-8")


def _patched_payloads(document: Mapping[str, Any]) -> Mapping[str, bytes]:
    definition_raw = _canonical_json(document)
    with _temporary_legacy_definition(document) as legacy_path:
        built = legacy.build_coverage_audit(legacy_path)
    payloads = dict(built.payloads)
    audit = json.loads(payloads[legacy.AUDIT_FILENAME])
    v83_support = _validate_v83_support()
    supports = audit["inputs"]["methodology_support_artifacts"]
    supports.append(v83_support)
    supports.sort(key=lambda row: row["support_id"])
    for category in ("computer_vision", "satellite_imagery"):
        record = audit["methodology_evidence_classification"][category]
        support_rows = record["methodology_support_artifacts"]
        support_rows.append(v83_support)
        support_rows.sort(key=lambda row: row["support_id"])
        record["methodology_support_artifact_count"] = 2
        record["methodology_support_ids"] = [row["support_id"] for row in support_rows]
        record["methodology_support_promotions"] = 0
    comparison = audit["semianalysis_public_comparison"]
    for row in comparison["comparisons"]:
        if row["claim_id"] == "evidence_methodology":
            for category in ("computer_vision", "satellite_imagery"):
                row["atlas_evidence"][category] = deepcopy(
                    audit["methodology_evidence_classification"][category]
                )
            row["atlas_evidence"]["methodology_scope"] = (
                "hash_bound_source_evidence_plus_non_countable_review_support"
            )
        elif row["claim_id"] == "construction_timeline_pjm":
            row["atlas_evidence"]["bounded_partial_timeline_gate"] = _timeline_gate()
            row["atlas_evidence"]["multi_milestone_construction_timelines"] = (
                "not_claimed_by_bounded_gate"
            )
            row["atlas_status"] = "partial_bounded_timeline_gate"
            row["parity_status"] = "pending"
        elif row["claim_id"] == "temporal_granularity":
            row["atlas_evidence"]["bounded_partial_timeline_gate"] = _timeline_gate()
            row["atlas_status"] = "partial_current_view_plus_bounded_timeline_gate"
            row["parity_status"] = "pending"
    comparison["overall_parity"] = {
        "reason": (
            "Public claims are not a row-level benchmark; Atlas unique physical "
            "sites remain unknown; bounded timeline-v8 gate evidence is not "
            "every-facility coverage; and reviewed methodology support does not "
            "close the material facility, FOIA, timeline, or capacity gaps."
        ),
        "status": "pending",
    }
    audit["bounded_partial_timeline_gate"] = _timeline_gate()
    gaps = legacy.legacy._gap_registry(
        audit["audit_id"], audit["generated_at"], audit["groups"], comparison
    )
    gaps["schema_version"] = legacy.SCHEMA_VERSION
    gaps["format"] = legacy.GAP_FORMAT
    audit["successor_delta_from_v30"] = _successor_delta(audit, gaps)
    audit_raw = _canonical_json(audit)
    gaps_raw = _canonical_json(gaps)
    csv_raw = legacy.legacy._coverage_csv(audit["groups"])
    report_raw = _report_v31(audit, gaps)
    artifacts = {
        legacy.AUDIT_FILENAME: audit_raw,
        legacy.COVERAGE_CSV_FILENAME: csv_raw,
        legacy.GAP_REGISTRY_FILENAME: gaps_raw,
        legacy.REPORT_FILENAME: report_raw,
    }
    base_manifest = json.loads(payloads[legacy.MANIFEST_FILENAME])
    manifest = {
        **base_manifest,
        "acceptance_gates": _acceptance_gates(),
        "artifacts": {
            name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(artifacts.items())
        },
        "definition": {
            "bytes": len(definition_raw),
            "file": DEFINITION.name,
            "sha256": hashlib.sha256(definition_raw).hexdigest(),
        },
        "implementation": _implementation_pins(),
        "inputs": {
            **base_manifest["inputs"],
            "methodology_support_artifacts": {
                **base_manifest["inputs"]["methodology_support_artifacts"],
                V83_SUPPORT_ID: {
                    "closed_tree_inventory_sha256": V83_REVIEW_TREE_SHA256,
                    "manifest_sha256": V83_REVIEW_MANIFEST_SHA256,
                    "member_sha256": {
                        name: digest
                        for name, (_size, digest) in sorted(
                            V83_REVIEW_MEMBER_PINS.items()
                        )
                    },
                    "summary_sha256": V83_REVIEW_MEMBER_PINS["summary.json"][1],
                },
            },
        },
        "successor_delta_from_v30": audit["successor_delta_from_v30"],
    }
    manifest["counts"] = dict(EXPECTED_COVERAGE_COUNTS)
    if (
        len(audit["groups"]) != EXPECTED_COVERAGE_COUNTS["coverage_groups"]
        or len(gaps["gaps"]) != EXPECTED_COVERAGE_COUNTS["open_gaps"]
        or audit["totals"]["source_scoped_entity_records"]
        != EXPECTED_COVERAGE_COUNTS["source_scoped_entity_records"]
    ):
        raise CoverageAuditV31Error("coverage v31 accepted count boundary changed")
    manifest_raw = _canonical_json(manifest)
    result = {
        **artifacts,
        legacy.MANIFEST_FILENAME: manifest_raw,
        legacy.MANIFEST_HASH_FILENAME: (
            f"{hashlib.sha256(manifest_raw).hexdigest()}  {legacy.MANIFEST_FILENAME}\n"
        ).encode("ascii"),
    }
    for name, raw in result.items():
        for token in FORBIDDEN_FUTURE_TOKENS:
            if token in raw:
                raise CoverageAuditV31Error(
                    f"future lineage token present in {name}: {token.decode('ascii')}"
                )
    return result


def _validate_payloads(
    directory: Path, *, definition_path: Path, rebuild: bool
) -> Mapping[str, Any]:
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != legacy.AUDIT_BUNDLE_FILES:
        raise CoverageAuditV31Error("coverage v31 bundle file set changed")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise CoverageAuditV31Error("coverage v31 bundle contains a non-file")
    payloads = {entry.name: entry.read_bytes() for entry in entries}
    manifest_raw = payloads[legacy.MANIFEST_FILENAME]
    if payloads[legacy.MANIFEST_HASH_FILENAME] != (
        f"{hashlib.sha256(manifest_raw).hexdigest()}  {legacy.MANIFEST_FILENAME}\n"
    ).encode("ascii"):
        raise CoverageAuditV31Error("coverage v31 manifest sidecar changed")
    manifest = json.loads(manifest_raw)
    audit = json.loads(payloads[legacy.AUDIT_FILENAME])
    gaps = json.loads(payloads[legacy.GAP_REGISTRY_FILENAME])
    if definition_path.is_symlink() or not definition_path.is_file():
        raise CoverageAuditV31Error("coverage v31 definition is not a regular file")
    definition_raw = definition_path.read_bytes()
    definition = json.loads(definition_raw)
    if definition_raw != _canonical_json(definition):
        raise CoverageAuditV31Error("coverage v31 definition is not canonical")
    for value, raw, label in (
        (manifest, manifest_raw, "manifest"),
        (audit, payloads[legacy.AUDIT_FILENAME], "audit"),
        (gaps, payloads[legacy.GAP_REGISTRY_FILENAME], "gaps"),
    ):
        if raw != _canonical_json(value):
            raise CoverageAuditV31Error(f"coverage v31 {label} is not canonical")
    if not (
        manifest.get("audit_id") == audit.get("audit_id") == gaps.get("audit_id") == AUDIT_ID
        and manifest.get("generated_at")
        == audit.get("generated_at")
        == gaps.get("generated_at")
    ):
        raise CoverageAuditV31Error("coverage v31 identities do not reconcile")
    if manifest.get("definition") != {
        "bytes": len(definition_raw),
        "file": DEFINITION.name,
        "sha256": hashlib.sha256(definition_raw).hexdigest(),
    }:
        raise CoverageAuditV31Error("coverage v31 definition pin changed")
    if manifest.get("acceptance_gates") != _acceptance_gates():
        raise CoverageAuditV31Error("coverage v31 acceptance gates changed")
    if manifest.get("implementation") != _implementation_pins():
        raise CoverageAuditV31Error("coverage v31 implementation pins changed")
    if manifest.get("counts") != EXPECTED_COVERAGE_COUNTS:
        raise CoverageAuditV31Error("coverage v31 counts changed")
    for name, checkpoint in manifest["artifacts"].items():
        raw = payloads[name]
        if checkpoint != {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }:
            raise CoverageAuditV31Error(f"coverage v31 artifact drift: {name}")
    if audit["scope"]["children_merged"] is not False:
        raise CoverageAuditV31Error("coverage v31 merged child rows")
    if audit["scope"]["current_status_inferred"] is not False:
        raise CoverageAuditV31Error("coverage v31 inferred current status")
    if audit["totals"]["unique_physical_sites"] is not None:
        raise CoverageAuditV31Error("coverage v31 claimed unique physical sites")
    if (
        audit["totals"]["source_scoped_entity_records"] != 16_352
        or audit["totals"]["non_review_source_scoped_entity_records"] != 10_222
        or audit["totals"]["review_only_source_scoped_entity_records"] != 6_130
        or len(audit["groups"]) != 979
        or len(audit["entity_source_families"]) != 300
        or len(gaps["gaps"]) != 4_582
    ):
        raise CoverageAuditV31Error("coverage v31 source-scoped accounting changed")
    if audit["semianalysis_public_comparison"]["overall_parity"]["status"] != "pending":
        raise CoverageAuditV31Error("coverage v31 claimed SemiAnalysis parity")
    supports = audit["inputs"]["methodology_support_artifacts"]
    if [row["support_id"] for row in supports] != [
        "2026-07-20-open-seed-v57-active-review-v1",
        V83_SUPPORT_ID,
    ]:
        raise CoverageAuditV31Error("coverage v31 support inventory changed")
    support = supports[1]
    if support["accounting"] != {
        **EXPECTED_REVIEW_ACCOUNTING,
        "exact_duplicate_group_members": EXPECTED_EXACT_DUPLICATE_GROUPS,
        "x052_x041_similarity": "reviewer_approximate_only_no_exact_deduplication",
    } or any(
        support["scope"][field] is not False
        for field in (
            "atlas_mutation",
            "child_evidence",
            "countable",
            "current_status_claim",
            "lifecycle_observations",
            "promoted",
            "row_provenance",
        )
    ):
        raise CoverageAuditV31Error("coverage v31 v83 support scope changed")
    if audit["bounded_partial_timeline_gate"] != _timeline_gate():
        raise CoverageAuditV31Error("coverage v31 timeline gate changed")
    evidence = audit["methodology_evidence_classification"]
    for category in ("computer_vision", "satellite_imagery"):
        record = evidence[category]
        if (
            record["evidence_reference_count"] != 0
            or record["methodology_support_artifact_count"] != 2
            or record["methodology_support_promotions"] != 0
            or record["methodology_support_is_countable"] is not False
            or record["methodology_support_is_promoted"] is not False
        ):
            raise CoverageAuditV31Error(
                f"coverage v31 {category} support scope changed"
            )
    if (
        evidence["foia"]["evidence_reference_count"] != 0
        or evidence["foia"]["status"] != "absent_from_audited_children"
    ):
        raise CoverageAuditV31Error("coverage v31 claimed FOIA evidence")
    if audit["successor_delta_from_v30"] != _successor_delta(audit, gaps):
        raise CoverageAuditV31Error("coverage v31 successor deltas changed")
    if manifest.get("successor_delta_from_v30") != audit[
        "successor_delta_from_v30"
    ]:
        raise CoverageAuditV31Error("coverage v31 manifest deltas changed")
    if payloads[legacy.COVERAGE_CSV_FILENAME] != legacy.legacy._coverage_csv(
        audit["groups"]
    ):
        raise CoverageAuditV31Error("coverage v31 CSV does not reconcile")
    if payloads[legacy.REPORT_FILENAME] != _report_v31(audit, gaps):
        raise CoverageAuditV31Error("coverage v31 report does not reconcile")
    if rebuild:
        document = json.loads(definition_path.read_bytes())
        if payloads != _patched_payloads(document):
            raise CoverageAuditV31Error("coverage v31 offline reconstruction drifted")
    return audit


def _write_definition_stage(path: Path, raw: bytes) -> None:
    with path.open("r+b") as stream:
        stream.truncate(0)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _write_bundle_stage(path: Path, payloads: Mapping[str, bytes]) -> None:
    for name, raw in sorted(payloads.items()):
        with (path / name).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())


def _latest_stage_time(definition_stage: Path, bundle_stage: Path) -> float:
    timestamps = []
    for path in (definition_stage, bundle_stage, *bundle_stage.iterdir()):
        metadata = path.stat()
        if not hasattr(metadata, "st_birthtime"):
            raise CoverageAuditV31Error("filesystem birth time is unavailable")
        timestamps.extend((metadata.st_birthtime, metadata.st_mtime))
    return max(timestamps)


def _wait_until(target: datetime) -> None:
    remaining = target.timestamp() - time.time()
    if remaining > 900:
        raise CoverageAuditV31Error("coverage v31 publication is over 15 minutes ahead")
    while time.time() < target.timestamp():
        time.sleep(min(0.05, target.timestamp() - time.time()))


def _discard_bundle_stage(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o700)
    for entry in path.iterdir():
        if entry.is_symlink() or not entry.is_file():
            raise CoverageAuditV31Error("refusing contaminated stage cleanup")
        entry.chmod(0o600)
    shutil.rmtree(path)


def _discard_definition_stage(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not path.is_file():
        return
    path.chmod(0o600)
    path.unlink()


def _rollback_publication(*, definition_published: bool, bundle_published: bool) -> None:
    if definition_published and DEFINITION.exists():
        rollback_definition = (
            DEFINITION.parent / f".{DEFINITION.name}.rollback-{os.getpid()}"
        )
        promote_noreplace(DEFINITION, rollback_definition)
        _discard_definition_stage(rollback_definition)
    if bundle_published and BUNDLE.exists():
        rollback_bundle = BUNDLE.parent / f".{BUNDLE.name}.rollback-{os.getpid()}"
        BUNDLE.chmod(0o755)
        promote_noreplace(BUNDLE, rollback_bundle)
        _discard_bundle_stage(rollback_bundle)


@contextmanager
def _publication_lock() -> Iterator[None]:
    try:
        descriptor = os.open(
            PUBLICATION_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
    except FileExistsError as error:
        raise CoverageAuditV31Error(
            f"active coverage-v31 publication lock exists: {PUBLICATION_LOCK}"
        ) from error
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        PUBLICATION_LOCK.unlink(missing_ok=True)


def _require_unpublished() -> None:
    for path in (DEFINITION, BUNDLE):
        if path.exists() or path.is_symlink():
            raise CoverageAuditV31Error(f"refusing replacement of coverage v31: {path}")


def publish_coverage_audit_v31(generated_at: str) -> Mapping[str, Any]:
    """Double-build, time-gate, and no-replace publish coverage v31."""

    target = _parse_utc(generated_at, label="coverage v31 generated_at")
    if target <= datetime.now(timezone.utc):
        raise CoverageAuditV31Error("coverage v31 generated_at must be in the future")
    _require_inputs()
    _require_dependencies_before(target)
    for parent in (DEFINITION.parent, BUNDLE.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise CoverageAuditV31Error(f"invalid output parent: {parent}")
    with _publication_lock():
        _require_unpublished()
        descriptor, definition_name = tempfile.mkstemp(
            prefix=f".{DEFINITION.name}.stage-", dir=DEFINITION.parent
        )
        os.close(descriptor)
        definition_stage = Path(definition_name)
        bundle_stage = Path(
            tempfile.mkdtemp(prefix=f".{BUNDLE.name}.stage-", dir=BUNDLE.parent)
        )
        definition_published = False
        bundle_published = False
        try:
            document = definition_document(generated_at)
            definition_raw = _canonical_json(document)
            _write_definition_stage(definition_stage, definition_raw)
            first = _patched_payloads(document)
            second = _patched_payloads(document)
            if first != second:
                raise CoverageAuditV31Error("two offline v31 reconstructions differ")
            _write_bundle_stage(bundle_stage, first)
            for entry in bundle_stage.iterdir():
                entry.chmod(0o444)
            bundle_stage.chmod(0o555)
            definition_stage.chmod(0o444)
            _validate_payloads(
                bundle_stage, definition_path=definition_stage, rebuild=False
            )
            if _latest_stage_time(definition_stage, bundle_stage) > (
                target.timestamp() + 0.000_001
            ):
                raise CoverageAuditV31Error(
                    "coverage v31 staging exceeded generated_at"
                )
            _wait_until(target)
            _require_unpublished()
            bundle_stage.chmod(0o755)
            promote_noreplace(bundle_stage, BUNDLE)
            bundle_published = True
            BUNDLE.chmod(0o555)
            promote_noreplace(definition_stage, DEFINITION)
            definition_published = True
            for final in (BUNDLE, DEFINITION):
                if final.stat().st_ctime + 0.000_001 < target.timestamp():
                    raise CoverageAuditV31Error(
                        f"coverage v31 final rename predates generated_at: {final.name}"
                    )
            return validate_coverage_audit_v31()
        except BaseException as error:
            try:
                _rollback_publication(
                    definition_published=definition_published,
                    bundle_published=bundle_published,
                )
            except BaseException as rollback_error:
                error.add_note(f"coverage v31 rollback failed: {rollback_error}")
            raise
        finally:
            if not bundle_published:
                _discard_bundle_stage(bundle_stage)
            if not definition_published and definition_stage.exists():
                _discard_definition_stage(definition_stage)


def validate_coverage_audit_v31() -> Mapping[str, Any]:
    """Validate frozen v31 and reproduce it byte-for-byte offline."""

    _require_inputs()
    document = json.loads(DEFINITION.read_bytes())
    generated = _parse_utc(document["generated_at"], label="coverage v31 generated_at")
    if generated > datetime.now(timezone.utc):
        raise CoverageAuditV31Error("coverage v31 generated_at exceeds wall clock")
    _require_dependencies_before(generated)
    if document != definition_document(document["generated_at"]):
        raise CoverageAuditV31Error("coverage v31 definition is not the bounded successor")
    for path in (DEFINITION, BUNDLE, *BUNDLE.iterdir()):
        metadata = path.stat()
        expected_mode = 0o555 if path.is_dir() else 0o444
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise CoverageAuditV31Error(f"coverage v31 artifact is not frozen: {path}")
        birth = getattr(metadata, "st_birthtime", metadata.st_ctime)
        if max(birth, metadata.st_mtime) > generated.timestamp() + 0.000_001:
            raise CoverageAuditV31Error(f"coverage v31 artifact post-dates generated_at: {path}")
    for root in (DEFINITION, BUNDLE):
        if root.stat().st_ctime + 0.000_001 < generated.timestamp():
            raise CoverageAuditV31Error(f"coverage v31 rename predates generated_at: {root}")
    return _validate_payloads(BUNDLE, definition_path=DEFINITION, rebuild=True)


__all__ = [
    "AUDIT_ID",
    "BUNDLE",
    "CoverageAuditV31Error",
    "DEFINITION",
    "EXPECTED_REVIEW_ACCOUNTING",
    "EXPECTED_TIMELINE_GATE",
    "V83_SUPPORT_ID",
    "definition_document",
    "publish_coverage_audit_v31",
    "validate_coverage_audit_v31",
]
