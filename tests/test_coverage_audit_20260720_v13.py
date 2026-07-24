from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    GAP_REGISTRY_FILENAME,
    CoverageAuditError,
    build_coverage_audit,
    validate_coverage_audit,
)


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v12.json"
)
DEFINITION = ROOT / "sources" / "coverage-audit-2026-07-20-public-open-v13.json"
FEDERATION_DEFINITION = ROOT / "sources" / "federation-2026-07-20-public-open-v13.json"
FEDERATION_RELEASE = ROOT / "federated_indexes" / "2026-07-20-public-open-v13"
OPEN_SEED_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v35.json"
OPEN_SEED_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v35"
PREVIOUS_RELEASE = ROOT / "audits" / "2026-07-19-public-open-coverage-v12"
RELEASE = ROOT / "audits" / "2026-07-20-public-open-coverage-v13"
PREEXISTING_JULY19_TEST = ROOT / "tests" / "test_coverage_audit_v13.py"

PREVIOUS_DEFINITION_SHA256 = (
    "1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f"
)
DEFINITION_SHA256 = (
    "c301b6db50126e795bf68423324dc0a745afcacba3fe6acb4a4a66df51680f9b"
)
PREVIOUS_MANIFEST_SHA256 = (
    "5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77"
)
MANIFEST_SHA256 = (
    "64dc5922dcf68530fafbeec8500e34fdf30fe4b664cdc2ed31093a1c61e53d7a"
)
MANIFEST_HASH_SHA256 = (
    "2203813436d4198cfde2a12274394758b0cb46538c27ce04f3c6fe9b48eac998"
)
FEDERATION_DEFINITION_SHA256 = (
    "0a82b9f772296da40c506c8323b8c3d1e3911d0960d9e5678adb6b7e887cf373"
)
FEDERATION_MANIFEST_SHA256 = (
    "9e2c7f41bf01a2f79b322f91080325ae113b9db02bf8864c2253895c80cc1ee6"
)
FEDERATION_INDEX_SHA256 = (
    "5e30d71535c1700c15ddd49c05d73b6f68c293840745561015bd29e3b7c9a96c"
)
OPEN_SEED_DEFINITION_SHA256 = (
    "ade1722f44a8a97f848d94579a4cfc45bc96f7f706df80f38ad6c46cabc5735d"
)
OPEN_SEED_MANIFEST_SHA256 = (
    "47994a012f4a97ca6dcdafb55c6b98a7121397a843ec1857328acd7953988123"
)
OLD_FEDERATION_MANIFEST_SHA256 = (
    "9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4"
)
OLD_FEDERATION_INDEX_SHA256 = (
    "fa3ea973cc7b210ae4dacb18b4b9b05416d74aa21cfdad686fee6e11b0bf83dd"
)
OLD_OPEN_SEED_MANIFEST_SHA256 = (
    "85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c"
)
PREEXISTING_JULY19_TEST_SHA256 = (
    "6a1f04b845e54fea10f7c0e5398daa068652dddcc94ecc01ba96e37423ea7038"
)

ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_148,
        "sha256": "b3384551e31c29a322875fe9649a24d0f99cfb46bbcf7123b12eff5f8e54d151",
    },
    "coverage-audit.json": {
        "bytes": 1_481_977,
        "sha256": "38eb1f6c56336e934e3dca7dce7ace2f7b623b4004329e5a888d4349a9b41a3c",
    },
    "coverage.csv": {
        "bytes": 203_424,
        "sha256": "238fbe30b66318912c02ec7ff2eec9d5516c66ad647608ea429862d161415a55",
    },
    "gap-registry.json": {
        "bytes": 1_284_521,
        "sha256": "03c59278ca3b735c20f2938d7c0366a3f5a065093347bd71cc833a384de06a30",
    },
}

OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v32"
NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v35"
PERMIT_EVIDENCE_IDS = {
    "435a7953-c5ef-5e7c-bb2d-1ad77b7230c9",
    "7db2bc34-1181-50d4-8cc5-9e943b7b2263",
    "928bbcd8-079d-5b85-a631-2477c6513a79",
    "ace70e8e-68ed-560f-a9e8-241aac11910b",
    "ad206c30-8e4c-569f-9edf-e8ba453378f9",
    "b133a4dc-126f-5e44-8841-f770b6fa9ad0",
    "cd9a0e24-c1f1-59e0-9234-031e6193dc0e",
}
NEW_SOURCE_FAMILIES = {
    "adani_connect_magazine",
    "atnorth_newsroom",
    "csc_news_and_blog",
    "esr_newsroom",
    "green_mountain_project_pages",
    "kouvola_city_news",
    "loviisa_city_news",
    "metsahallitus_press_releases",
    "srv_cision_press_releases",
}

FIELD_TOTALS_SHA256 = (
    "428b02bdfd08b765a5e0df48e7262ac20062cb04f2910a3320dd6aa5174adbe2"
)
ADDED_GROUP_KEYS_SHA256 = (
    "0f7ba8741d590d8148bf9d4aede9c2d25d3e2cfb3fca69087ba2faf029f8f50c"
)
ADDED_GROUPS_SHA256 = (
    "8b85ec8a55d986e9b1fe8803b52223c4fb739f097f0ce71e1836614a6a5a4021"
)
FRESHNESS_GROUP_KEYS_SHA256 = (
    "e72c3b386bc96246af6123dd36cc277626eac660e081471f1759654e11ab5b37"
)
OPEN_RELEASE_GROUP_SHA256 = (
    "9b7467ed72d33c2bba271a6efcfac44b283c0c8f619d601799abf378271aaa19"
)
ADDED_GAP_KEYS_SHA256 = (
    "349d3a578fce677f52ac66a8db535cf2efd0ddfb74c3686377742c6cdde22eda"
)
ADDED_GAPS_SHA256 = (
    "966ffde41c8356a723fd95307e814b4a1e6188766738fbf6f184c7199d9976b2"
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _canonical_hash(value: object) -> str:
    raw = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_open_release_id(value: object) -> object:
    if isinstance(value, dict):
        return {key: _normalize_open_release_id(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_open_release_id(item) for item in value]
    if value == NEW_OPEN_RELEASE_ID:
        return OLD_OPEN_RELEASE_ID
    return value


def _group_key(group: dict[str, object]) -> tuple[object, ...]:
    normalized = _normalize_open_release_id(group)
    assert isinstance(normalized, dict)
    return (
        normalized["child_release"],
        normalized["scope_type"],
        normalized["source_family"],
        normalized["country"],
        normalized["country_iso_a2"],
        normalized["country_iso_a3"],
    )


def _gap_key(gap: dict[str, object]) -> tuple[object, ...]:
    normalized = _normalize_open_release_id(gap)
    assert isinstance(normalized, dict)
    return (
        normalized["scope_type"],
        normalized["child_release"],
        normalized["source_family"],
        normalized["country"],
        normalized["field"],
    )


def _normalized_gap(gap: dict[str, object]) -> dict[str, object]:
    normalized = _normalize_open_release_id(gap)
    assert isinstance(normalized, dict)
    normalized.pop("gap_id")
    return normalized


def _require_frozen_modes(directory: Path) -> None:
    if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o555:
        raise CoverageAuditError("release directory mode must be 0555")
    for path in directory.iterdir():
        if (
            path.is_symlink()
            or not path.is_file()
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise CoverageAuditError("release file mode must be 0444")


class FrozenJuly20PublicCoverageV13Tests(unittest.TestCase):
    def test_frozen_successor_reproduces_twice_offline_with_live_pins(self) -> None:
        pins = {
            PREVIOUS_DEFINITION: PREVIOUS_DEFINITION_SHA256,
            DEFINITION: DEFINITION_SHA256,
            FEDERATION_DEFINITION: FEDERATION_DEFINITION_SHA256,
            FEDERATION_RELEASE / "manifest.json": FEDERATION_MANIFEST_SHA256,
            FEDERATION_RELEASE / "federated-index.json": FEDERATION_INDEX_SHA256,
            OPEN_SEED_DEFINITION: OPEN_SEED_DEFINITION_SHA256,
            OPEN_SEED_RELEASE / "manifest.json": OPEN_SEED_MANIFEST_SHA256,
            PREVIOUS_RELEASE / "manifest.json": PREVIOUS_MANIFEST_SHA256,
            PREEXISTING_JULY19_TEST: PREEXISTING_JULY19_TEST_SHA256,
        }
        for path, expected in pins.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        previous_definition = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        expected_definition = json.loads(PREVIOUS_DEFINITION.read_text(encoding="utf-8"))
        expected_definition["audit_id"] = "public-open-coverage-v13"
        expected_definition["generated_at"] = "2026-07-20T00:50:00Z"
        expected_definition["federated_index"] = {
            "expected_manifest_sha256": FEDERATION_MANIFEST_SHA256,
            "path": "../federated_indexes/2026-07-20-public-open-v13",
        }
        open_child = next(
            child
            for child in expected_definition["children"]
            if child["release_id"] == OLD_OPEN_RELEASE_ID
        )
        open_child.update(
            {
                "expected_manifest_sha256": OPEN_SEED_MANIFEST_SHA256,
                "release_id": NEW_OPEN_RELEASE_ID,
                "release_path": "../releases/2026-07-20-open-seed-v35",
            }
        )
        for reference in expected_definition["methodology_evidence_classification"][
            "permits"
        ]:
            self.assertEqual(reference["release_id"], OLD_OPEN_RELEASE_ID)
            reference["release_id"] = NEW_OPEN_RELEASE_ID
        self.assertEqual(DEFINITION.read_bytes(), _json_bytes(expected_definition))
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        self.assertEqual(definition["public_benchmark"], previous_definition["public_benchmark"])
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(definition["methodology_evidence_classification"][field], [])
        self.assertEqual(
            {
                reference["evidence_id"]
                for reference in definition["methodology_evidence_classification"][
                    "permits"
                ]
            },
            PERMIT_EVIDENCE_IDS,
        )

        stale_references = (
            b"public-open-v11",
            b"open-seed-v32",
            OLD_FEDERATION_MANIFEST_SHA256.encode(),
            OLD_FEDERATION_INDEX_SHA256.encode(),
            OLD_OPEN_SEED_MANIFEST_SHA256.encode(),
        )
        for stale in stale_references:
            self.assertNotIn(stale, DEFINITION.read_bytes())

        frozen = {path.name: path.read_bytes() for path in RELEASE.iterdir()}
        offline = AssertionError("offline build attempted network access")
        with patch.object(socket, "socket", side_effect=offline), patch.object(
            socket, "create_connection", side_effect=offline
        ), patch.object(socket, "getaddrinfo", side_effect=offline), patch.object(
            socket, "gethostbyname", side_effect=offline
        ), patch.object(socket, "gethostbyname_ex", side_effect=offline):
            first = build_coverage_audit(DEFINITION)
            second = build_coverage_audit(DEFINITION)
            first_sealed = validate_coverage_audit(RELEASE, definition_path=DEFINITION)
            second_sealed = validate_coverage_audit(RELEASE, definition_path=DEFINITION)

        self.assertEqual(first, second)
        self.assertEqual(first.audit, first_sealed)
        self.assertEqual(first_sealed, second_sealed)
        self.assertEqual(set(first.payloads), set(frozen))
        for filename, payload in first.payloads.items():
            self.assertEqual(payload, frozen[filename])
            for stale in stale_references:
                self.assertNotIn(stale, payload)
        self.assertEqual(
            {path.name: path.read_bytes() for path in RELEASE.iterdir()}, frozen
        )
        self.assertEqual(first.manifest["artifacts"], ARTIFACTS)
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.json").read_bytes()).hexdigest(),
            MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256((RELEASE / "manifest.sha256").read_bytes()).hexdigest(),
            MANIFEST_HASH_SHA256,
        )

        federation = json.loads(
            (FEDERATION_RELEASE / "federated-index.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            federation["counts"],
            {
                "capacity_estimates": 1_191,
                "construction_pipeline_records": 6_454,
                "evidence_records": 13_249,
                "non_review_construction_pipeline_records": 324,
                "non_review_source_scoped_entity_records": 9_683,
                "release_bundles": 3,
                "resolution_candidates": 100_409,
                "review_only_construction_pipeline_records": 6_130,
                "review_only_release_bundles": 1,
                "review_only_source_scoped_entity_records": 6_130,
                "source_family_entries": 107,
                "source_scoped_entity_records": 15_813,
                "unique_physical_sites": None,
            },
        )

        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        _require_frozen_modes(PREVIOUS_RELEASE)
        _require_frozen_modes(RELEASE)

    def test_groups_gaps_date_rollover_and_methodology_have_exact_v12_delta(self) -> None:
        previous = json.loads((PREVIOUS_RELEASE / AUDIT_FILENAME).read_text(encoding="utf-8"))
        current = json.loads((RELEASE / AUDIT_FILENAME).read_text(encoding="utf-8"))
        previous_gaps = json.loads(
            (PREVIOUS_RELEASE / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )
        current_gaps = json.loads(
            (RELEASE / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                key: current["totals"][key]
                for key in (
                    "advisory_resolution_candidate_records",
                    "non_review_source_scoped_entity_records",
                    "review_only_source_scoped_entity_records",
                    "source_scoped_entity_records",
                    "unique_physical_sites",
                )
            },
            {
                "advisory_resolution_candidate_records": 100_409,
                "non_review_source_scoped_entity_records": 9_683,
                "review_only_source_scoped_entity_records": 6_130,
                "source_scoped_entity_records": 15_813,
                "unique_physical_sites": None,
            },
        )
        self.assertEqual(
            current["totals"]["source_scoped_entity_records"]
            - previous["totals"]["source_scoped_entity_records"],
            18,
        )
        self.assertEqual(
            current["totals"]["non_review_source_scoped_entity_records"]
            - previous["totals"]["non_review_source_scoped_entity_records"],
            18,
        )
        self.assertEqual(
            current["totals"]["review_only_source_scoped_entity_records"],
            previous["totals"]["review_only_source_scoped_entity_records"],
        )

        previous_fields = previous["totals"]["field_totals"]
        current_fields = current["totals"]["field_totals"]
        self.assertEqual(_canonical_hash(current_fields), FIELD_TOTALS_SHA256)
        integer_deltas = {
            field: value - previous_fields[field]
            for field, value in current_fields.items()
            if isinstance(value, int) and value != previous_fields[field]
        }
        self.assertEqual(
            integer_deltas,
            {
                "capacity_entity_rows": 3,
                "capacity_observations": 4,
                "capacity_observations_with_evidence": 4,
                "capacity_observations_with_resolved_evidence": 4,
                "complete_lifecycle_claim_rows": 9,
                "construction_evidence_observations": 8,
                "country_iso_a2_rows": 18,
                "country_iso_a3_rows": 18,
                "country_rows": 18,
                "informative_lifecycle_status_rows": 9,
                "lifecycle_status_rows": 9,
                "non_review_rows": 18,
                "non_review_under_construction_rows": 8,
                "pipeline_rows": 8,
                "pipeline_with_status_evidence_rows": 8,
                "source_scoped_rows": 18,
                "status_as_of_rows": 9,
                "status_evidence_rows": 9,
                "status_method_rows": 9,
                "under_construction_rows": 8,
                "under_construction_with_status_evidence_rows": 8,
                "unresolved_lifecycle_status_rows": 9,
            },
        )
        expected_counter_deltas = {
            "administrative_assignment_status_counts": ({"source_label_only": 18}, {}),
            "capacity_confidence_counts": ({"0.99": 4}, {}),
            "capacity_method_counts": ({"reported": 4}, {}),
            "capacity_metric_counts": ({"critical_it_mw": 1, "gross_facility_mw": 3}, {}),
            "capacity_stage_counts": ({"planned": 4}, {}),
            "non_review_source_declared_entity_kind_counts": ({"campus": 9, "project": 9}, {}),
            "pipeline_status_counts": ({"under_construction": 8}, {}),
            "source_declared_entity_kind_counts": ({"campus": 9, "project": 9}, {}),
            "status_counts": ({"__MISSING__": 9, "site_preparation": 1, "under_construction": 8}, {}),
            "status_freshness_counts": (
                {"366_plus_days": 1, "91_365_days": 107, "missing": 9},
                {"0_90_days": 99},
            ),
        }
        for field, (added, removed) in expected_counter_deltas.items():
            old_counts = Counter(previous_fields[field])
            new_counts = Counter(current_fields[field])
            self.assertEqual(dict(new_counts - old_counts), added)
            self.assertEqual(dict(old_counts - new_counts), removed)
        self.assertEqual(current_fields["capacity_observations"], 1_191)
        self.assertEqual(current_fields["pipeline_rows"], 304)
        self.assertEqual(current_fields["operating_model_rows"], 275)
        self.assertEqual(current_fields["workload_rows"], 105)

        previous_groups = {_group_key(group): group for group in previous["groups"]}
        current_groups = {_group_key(group): group for group in current["groups"]}
        previous_group_keys = set(previous_groups)
        current_group_keys = set(current_groups)
        self.assertEqual((len(previous_groups), len(current_groups)), (441, 459))
        self.assertLessEqual(previous_group_keys, current_group_keys)
        added_group_keys = current_group_keys - previous_group_keys
        ordered_added_group_keys = sorted(added_group_keys, key=repr)
        self.assertEqual(len(added_group_keys), 18)
        self.assertEqual(
            _canonical_hash([list(key) for key in ordered_added_group_keys]),
            ADDED_GROUP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [
                    _normalize_open_release_id(current_groups[key])
                    for key in ordered_added_group_keys
                ]
            ),
            ADDED_GROUPS_SHA256,
        )
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 9, "release_source_country": 9},
        )
        self.assertEqual({key[2] for key in added_group_keys}, NEW_SOURCE_FAMILIES)

        release_group_key = (
            OLD_OPEN_RELEASE_ID,
            "release",
            "__ALL__",
            "__ALL__",
            None,
            None,
        )
        as_of_transitions: Counter[tuple[object, object]] = Counter()
        freshness_changed_keys: set[tuple[object, ...]] = set()
        for key in previous_group_keys:
            old_group = _normalize_open_release_id(previous_groups[key])
            new_group = _normalize_open_release_id(current_groups[key])
            assert isinstance(old_group, dict)
            assert isinstance(new_group, dict)
            if old_group["child_release_as_of"] != new_group["child_release_as_of"]:
                as_of_transitions[
                    (old_group["child_release_as_of"], new_group["child_release_as_of"])
                ] += 1
            if old_group["status_freshness_counts"] != new_group["status_freshness_counts"]:
                freshness_changed_keys.add(key)
            old_comparable = dict(old_group)
            new_comparable = dict(new_group)
            for field in ("child_release_as_of", "status_freshness_counts"):
                old_comparable.pop(field)
                new_comparable.pop(field)
            if key != release_group_key:
                self.assertEqual(new_comparable, old_comparable)
        self.assertEqual(
            as_of_transitions,
            {("2026-07-19", "2026-07-20"): 210},
        )
        self.assertEqual(len(freshness_changed_keys), 10)
        self.assertEqual(
            _canonical_hash(
                [list(key) for key in sorted(freshness_changed_keys, key=repr)]
            ),
            FRESHNESS_GROUP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                _normalize_open_release_id(current_groups[release_group_key])
            ),
            OPEN_RELEASE_GROUP_SHA256,
        )

        previous_gap_rows = {_gap_key(gap): gap for gap in previous_gaps["gaps"]}
        current_gap_rows = {_gap_key(gap): gap for gap in current_gaps["gaps"]}
        previous_gap_keys = set(previous_gap_rows)
        current_gap_keys = set(current_gap_rows)
        self.assertLessEqual(previous_gap_keys, current_gap_keys)
        changed_common_gaps = {
            key
            for key in previous_gap_keys
            if _normalized_gap(current_gap_rows[key])
            != _normalized_gap(previous_gap_rows[key])
        }
        rollover_gap_key = (
            "release_source_country",
            "osm-fuzzy-review-v2",
            "openstreetmap:fuzzy_discovery",
            "United Kingdom",
            "status_stale_366_plus_days",
        )
        self.assertEqual(changed_common_gaps, {rollover_gap_key})
        old_rollover_gap = _normalized_gap(previous_gap_rows[rollover_gap_key])
        new_rollover_gap = _normalized_gap(current_gap_rows[rollover_gap_key])
        self.assertEqual(
            (old_rollover_gap["affected_records"], old_rollover_gap["coverage"]),
            (18, 0.419355),
        )
        self.assertEqual(
            (new_rollover_gap["affected_records"], new_rollover_gap["coverage"]),
            (19, 0.387097),
        )
        for field in old_rollover_gap.keys() - {"affected_records", "coverage"}:
            self.assertEqual(new_rollover_gap[field], old_rollover_gap[field])

        added_gap_keys = current_gap_keys - previous_gap_keys
        ordered_added_gap_keys = sorted(added_gap_keys, key=repr)
        self.assertEqual(len(added_gap_keys), 81)
        self.assertEqual(
            _canonical_hash([list(key) for key in ordered_added_gap_keys]),
            ADDED_GAP_KEYS_SHA256,
        )
        self.assertEqual(
            _canonical_hash(
                [_normalized_gap(current_gap_rows[key]) for key in ordered_added_gap_keys]
            ),
            ADDED_GAPS_SHA256,
        )
        self.assertEqual(
            Counter(key[0] for key in added_gap_keys),
            {"release_source_country": 80, "release_source": 1},
        )
        self.assertEqual(
            Counter(key[4] for key in added_gap_keys),
            {
                "annual_energy": 9,
                "capacity": 8,
                "coordinates": 9,
                "informative_lifecycle_status": 9,
                "lifecycle_status": 9,
                "operating_model": 9,
                "source_scoped_rows": 1,
                "status_as_of": 9,
                "status_evidence": 9,
                "workload": 9,
            },
        )
        self.assertEqual(
            Counter(key[2] for key in added_gap_keys),
            {
                "adani_connect_magazine": 9,
                "atnorth_newsroom": 18,
                "csc_news_and_blog": 9,
                "esr_newsroom": 8,
                "green_mountain_project_pages": 9,
                "kouvola_city_news": 9,
                "loviisa_city_news": 1,
                "metsahallitus_press_releases": 9,
                "srv_cision_press_releases": 9,
            },
        )
        self.assertEqual(
            current_gaps["summary"],
            {
                "open_gaps": 2_492,
                "by_severity": {"high": 130, "info": 18, "low": 1_421, "medium": 923},
                "by_field": {
                    "annual_energy": 341,
                    "capacity": 329,
                    "coordinates": 120,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 330,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 160,
                    "operating_model": 348,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 18,
                    "status_as_of": 160,
                    "status_evidence": 160,
                    "status_stale_366_plus_days": 170,
                    "unique_physical_sites": 1,
                    "workload": 340,
                },
            },
        )

        comparison = current["semianalysis_public_comparison"]
        previous_comparison = previous["semianalysis_public_comparison"]
        self.assertEqual(comparison["benchmark"], previous_comparison["benchmark"])
        self.assertEqual(
            comparison["licensed_row_level_benchmark"],
            previous_comparison["licensed_row_level_benchmark"],
        )
        self.assertEqual(comparison["overall_parity"], previous_comparison["overall_parity"])
        self.assertEqual(comparison["overall_parity"]["status"], "pending")
        self.assertTrue(
            all(item["parity_status"] == "pending" for item in comparison["comparisons"])
        )
        evidence_methodology = next(
            item
            for item in comparison["comparisons"]
            if item["claim_id"] == "evidence_methodology"
        )["atlas_evidence"]
        permits = evidence_methodology["permits"]
        self.assertEqual(permits["evidence_reference_count"], 7)
        self.assertEqual(set(permits["evidence_ids"]), PERMIT_EVIDENCE_IDS)
        self.assertEqual(permits["release_ids"], [NEW_OPEN_RELEASE_ID])
        for field in ("computer_vision", "foia", "property_records", "satellite_imagery"):
            self.assertEqual(evidence_methodology[field]["status"], "absent_from_audited_children")
            self.assertEqual(evidence_methodology[field]["evidence_reference_count"], 0)
        self.assertEqual(evidence_methodology["power_data"]["capacity_observation_count"], 1_191)
        self.assertEqual(
            evidence_methodology["power_data"][
                "capacity_observations_with_resolved_evidence"
            ],
            1_191,
        )

        self.assertEqual(current["scope"], previous["scope"])
        self.assertFalse(current["scope"]["children_merged"])
        self.assertFalse(current["scope"]["cross_source_deduplication"])
        self.assertFalse(current["scope"]["review_candidates_promoted"])
        self.assertIsNone(current["scope"]["confirmed_duplicate_relationships"])
        self.assertIsNone(current["scope"]["unique_physical_sites"])
        self.assertEqual(
            current["inputs"]["federated_index"]["manifest"]["sha256"],
            FEDERATION_MANIFEST_SHA256,
        )
        self.assertEqual(
            current["inputs"]["federated_index"]["index"]["sha256"],
            FEDERATION_INDEX_SHA256,
        )
        report = (RELEASE / "REPORT.md").read_text(encoding="utf-8")
        self.assertIn("not a facility census", report)
        self.assertIn("SemiAnalysis parity determination: **pending**", report)

    def test_successor_fails_closed_on_wrong_pins_mutated_child_and_bundle_shape(self) -> None:
        definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
        definition_root = DEFINITION.parent
        definition["federated_index"]["path"] = str(
            (definition_root / definition["federated_index"]["path"]).resolve()
        )
        for child in definition["children"]:
            child["release_path"] = str(
                (definition_root / child["release_path"]).resolve()
            )

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            for case in ("federation", "child"):
                with self.subTest(case=case):
                    mutated = json.loads(json.dumps(definition))
                    if case == "federation":
                        mutated["federated_index"]["expected_manifest_sha256"] = "0" * 64
                        pattern = "federated index manifest SHA-256"
                    else:
                        open_child = next(
                            child
                            for child in mutated["children"]
                            if child["release_id"] == NEW_OPEN_RELEASE_ID
                        )
                        open_child["expected_manifest_sha256"] = "0" * 64
                        pattern = "manifest SHA-256 does not match audit definition"
                    path = root / f"wrong-{case}.json"
                    path.write_bytes(_json_bytes(mutated))
                    with self.assertRaisesRegex(CoverageAuditError, pattern):
                        build_coverage_audit(path)

            child_copy = root / "mutated-open-seed"
            shutil.copytree(OPEN_SEED_RELEASE, child_copy)
            readme = child_copy / "README.md"
            readme.chmod(0o644)
            readme.write_bytes(readme.read_bytes() + b"mutated\n")
            mutated_child = json.loads(json.dumps(definition))
            open_child = next(
                child
                for child in mutated_child["children"]
                if child["release_id"] == NEW_OPEN_RELEASE_ID
            )
            open_child["release_path"] = str(child_copy)
            mutated_child_definition = root / "mutated-child.json"
            mutated_child_definition.write_bytes(_json_bytes(mutated_child))
            with self.assertRaisesRegex(
                CoverageAuditError, "child release file hash mismatch: README.md"
            ):
                build_coverage_audit(mutated_child_definition)

            extra_copy = root / "extra-copy"
            shutil.copytree(RELEASE, extra_copy)
            extra_copy.chmod(0o755)
            (extra_copy / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
            with self.assertRaisesRegex(CoverageAuditError, "file set is invalid"):
                validate_coverage_audit(extra_copy)

            symlink_copy = root / "symlink-copy"
            shutil.copytree(RELEASE, symlink_copy)
            symlink_copy.chmod(0o755)
            report = symlink_copy / "REPORT.md"
            report.chmod(0o644)
            report.unlink()
            report.symlink_to(RELEASE / "REPORT.md")
            with self.assertRaisesRegex(CoverageAuditError, "regular file"):
                validate_coverage_audit(symlink_copy)

            mode_copy = root / "mode-copy"
            shutil.copytree(RELEASE, mode_copy)
            mode_copy.chmod(0o755)
            with self.assertRaisesRegex(CoverageAuditError, "mode must be 0555"):
                _require_frozen_modes(mode_copy)


if __name__ == "__main__":
    unittest.main()
