from __future__ import annotations

import inspect
import json
import shutil
import socket
import stat
from pathlib import Path

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        microsoft_mount_pleasant_phase3_prepublication_20260724 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        microsoft_mount_pleasant_phase3_prepublication_20260724 as tranche,
    )


RECORDED_AT = "2026-07-24T21:42:00Z"


def _document() -> dict[str, object]:
    return tranche.expected_source_document()


def _cleanup(prepared: tranche.PreparedCandidate) -> None:
    if prepared.source_stage.exists():
        shutil.rmtree(prepared.source_stage)
    if prepared.artifact_stage.exists():
        shutil.rmtree(prepared.artifact_stage)


def _configure_private_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    sources = tmp_path / "sources"
    artifacts = tmp_path / "source_artifacts"
    sources.mkdir()
    artifacts.mkdir()
    monkeypatch.setattr(tranche, "SOURCES_ROOT", sources)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifacts)
    monkeypatch.setattr(
        tranche,
        "PROSPECTIVE_ARTIFACT",
        artifacts / tranche.ARTIFACT_ID,
    )
    return sources, artifacts


def test_exact_one_sparse_phase3_source_document() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert documents == {tranche.SOURCE_FILENAME: _document()}
    document = _document()
    assert document["schema_version"] == "1.1"
    assert len(document["evidence"]) == 1
    assert len(document["lifecycle"]) == 1
    assert document["operating_models"] == []
    assert document["workloads"] == []
    assert document["capacities"] == []
    assert set(document) == {
        "schema_version",
        "evidence",
        "campus",
        "project",
        "lifecycle",
        "operating_models",
        "workloads",
        "capacities",
    }


def test_phase3_is_only_march_site_preparation_observation() -> None:
    document = _document()
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PHASE3_KEY
    assert document["project"]["name"] == (
        "Microsoft Mount Pleasant Phase 3—Durand & Hewitt Memorial Drive"
    )
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "site_preparation",
            "evidence_key": tranche.EVIDENCE_KEY,
            "as_of_date": "2026-03-31",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    for entity_name in ("campus", "project"):
        entity = document[entity_name]
        assert entity["address"] == (
            "Mount Pleasant, Wisconsin, United States"
        )
        assert entity["roles"] == {}
        assert entity["coordinates"] is None
        assert entity["geometry"] is None


def test_source_metadata_preserves_all_phase_boundaries() -> None:
    metadata = _document()["evidence"][0]["metadata"]
    assert metadata["phase3_heading"] == (
        "Phase 3—Durand & Hewitt Memorial Drive"
    )
    assert metadata["phase3_reported_status_wording"] == (
        "Preliminary earthwork is underway"
    )
    assert metadata["phase3_reported_purpose"] == (
        "prepare the site for future construction"
    )
    assert metadata["phase1_context"] == {
        "heading": "Phase 1—KR & 90th",
        "reported_status": "nearing completion",
        "reported_work": [
            "final interior work in several buildings",
            "landscaping",
        ],
        "normalized_in_this_source": False,
    }
    assert metadata["phase2_context"] == {
        "heading": "Phase 2—KR & H",
        "reported_status": "ongoing",
        "reported_work": [
            "foundation installation",
            "steel erection",
            "underground utility installation",
        ],
        "reported_completion_schedule": "early 2028",
        "normalized_in_this_source": False,
    }
    july = metadata["july_2026_context"]
    assert july["phase_assignment"] is None
    assert july["normalized_lifecycle_created"] is False
    assert "planned to start" in july["reported_action"]
    assert "future development" in july["reported_action"]


def test_no_building_capacity_operation_or_currentness_is_normalized() -> None:
    document = _document()
    serialized = json.dumps(document, sort_keys=True)
    forbidden = (
        "critical_it_mw",
        "gross_facility_mw",
        "grid_connection_mw",
        "annual_energy_mwh",
        "generation_nameplate_mw",
        '"operational"',
        '"commissioning"',
        '"under_construction"',
        '"latitude"',
        '"longitude"',
    )
    assert not any(value in serialized for value in forbidden)
    metadata = document["evidence"][0]["metadata"]
    assert metadata["status_semantics"] == (
        "dated_last_observed_historical_status_current_status_unknown"
    )
    assert "No building count" in metadata["normalization_guardrail"]


def test_assessment_has_one_source_and_three_review_only_boundaries() -> None:
    assessment = tranche._candidate_assessment(RECORDED_AT)
    assert assessment["candidate_count"] == 4
    assert assessment["governed_source_candidate_count"] == 1
    assert assessment["review_only_count"] == 3
    assert assessment["published"] is False
    by_id = {
        row["candidate_id"]: row for row in assessment["candidates"]
    }
    phase3 = by_id["mount-pleasant-phase3-durand-hewitt"]
    assert phase3["lifecycle"] == "site_preparation"
    assert phase3["current_status_claimed"] is False
    phase1 = by_id["mount-pleasant-phase1-kr-90th"]
    assert phase1["stable_key_created"] is False
    assert phase1["lifecycle_claim_created"] is False
    assert phase1["crosswalk_to_first_facility_or_epoch_fairwater_asserted"] is (
        False
    )
    phase2 = by_id["mount-pleasant-phase2-kr-h"]
    assert phase2["existing_project_stable_key"] == tranche.PHASE2_KEY
    assert phase2["new_entity_created"] is False
    assert phase2["existing_later_observation_preserved"] is True
    july = by_id["mount-pleasant-july-2026-site-wide-soil-hauling"]
    assert july["phase_assignment"] is None
    assert july["currentness_inferred_from_elapsed_calendar_date"] is False


def test_v97_reuses_only_campus_and_adds_distinct_phase3_key() -> None:
    witness = tranche._v97_witness()
    assert witness["release_id"] == "2026-07-22-open-seed-v97"
    assert witness["recorded_at"] == "2026-07-22T06:06:40Z"
    assert witness["curated_input_count"] == 519
    assert witness["entity_count"] == 1_053
    assert witness["evidence_count"] == 693
    assert witness["planned_stable_key_collisions"] == [tranche.CAMPUS_KEY]
    assert witness["planned_new_stable_keys"] == [tranche.PHASE3_KEY]
    assert witness["planned_evidence_key_collisions"] == []
    campus = witness["campus_identity_reuse"]
    assert campus["replace_existing_source"] is False
    assert campus["integration_mode"] == (
        "co_select_new_phase_source_with_existing_v1_campus_reuse"
    )


def test_phase2_exact_existing_project_is_not_duplicated() -> None:
    witness = tranche._v97_witness()
    phase2 = witness["phase2_existing_record"]
    assert phase2 == {
        "stable_key": tranche.PHASE2_KEY,
        "name": "Microsoft Mount Pleasant Second Datacenter Facility",
        "status": "under_construction",
        "status_as_of": "2026-06-23",
        "new_entity_created": False,
        "merge_decision": "reuse_exact_existing_phase2_project",
    }
    assert tranche.PHASE2_KEY != tranche.PHASE3_KEY
    document = _document()
    assert document["project"]["stable_key"] != tranche.PHASE2_KEY


def test_epoch_fairwater_remains_nearby_only_and_unmerged() -> None:
    witness = tranche._v97_witness()
    epoch = witness["epoch_fairwater_record"]
    assert epoch["stable_key"] == tranche.EPOCH_FAIRWATER_KEY
    assert epoch["name"] == "Microsoft Fairwater Wisconsin"
    assert epoch["relationship_suggestion"] == "nearby_only"
    assert epoch["distance_m"] == 4852.93
    assert epoch["merged_with_official_campus_or_any_phase"] is False


def test_capture_bundle_is_exact_frozen_private_and_primary_only() -> None:
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 4
    assert sum(
        size for size, _digest in tranche.CAPTURE_FILE_PINS.values()
    ) == tranche.CAPTURE_TOTAL_BYTES
    assert tranche.tree_digest(tranche.CAPTURE_ORIGIN) == (
        tranche.CAPTURE_TREE_SHA256
    )
    assert stat.S_IMODE(tranche.CAPTURE_ORIGIN.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in tranche.CAPTURE_ORIGIN.iterdir()
    )
    local_body = (
        tranche.CAPTURE_ORIGIN / "mount-pleasant.body"
    ).read_bytes()
    assert (
        b"Preliminary earthwork is underway to prepare the site for future "
        b"construction."
    ) in local_body
    assert b"Starting on or around July 13, 2026" in local_body
    june_body = (
        tranche.CAPTURE_ORIGIN / "mount-pleasant-june-news.body"
    ).read_bytes()
    assert (
        b"foundation installation, steel erection and underground utility "
        b"placement"
    ) in june_body


def test_retrieval_inventory_truthfully_records_failed_trash_move() -> None:
    inventory = tranche._retrieval_inventory(RECORDED_AT)
    assert inventory["successful_http_200_body_captures"] == 2
    assert inventory["raw_capture_redistributed"] is False
    assert inventory["private_capture_directory_frozen"] is True
    assert inventory["private_capture_retained_at_original_path"] is True
    assert inventory["trash_move_attempted"] is True
    assert inventory["trash_move_succeeded"] is False
    assert inventory["trash_move_result"] == (
        "host_permission_denied_retained_frozen_at_original_path"
    )
    by_id = {
        row["capture_id"]: row for row in inventory["controlled_captures"]
    }
    assert by_id["mount-pleasant-local-update"]["claim_use"] == (
        "normalized_phase3_and_review_context"
    )
    assert by_id["mount-pleasant-june-official-news"]["claim_use"] == (
        "dedup_and_chronology_reconciliation_only"
    )


def test_builder_has_no_publisher_and_builds_private_stages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    assert not hasattr(tranche, "publish")
    assert not hasattr(tranche, "_publish")
    source = inspect.getsource(tranche.prepare_candidate)
    assert "_promote" not in source
    assert ".rename(" not in source
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()

    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        result = tranche.candidate_result(prepared)
        assert result["status"] == (
            "PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED"
        )
        assert result["curated_source_candidates"] == 1
        assert result["review_only_candidates"] == 3
        assert result["offline_import_counts"] == {
            "entities": 2,
            "entity_snapshots": 2,
            "evidence": 1,
            "lifecycle_observations": 1,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        compatibility = result["v97_compatibility_import"]
        assert compatibility["counts"] == {
            "entities": 3,
            "entity_snapshots": 4,
            "evidence": 2,
            "lifecycle_observations": 2,
            "operating_model_observations": 1,
            "workload_observations": 0,
            "capacity_estimates": 0,
        }
        assert compatibility["campus_entity_rows"] == 1
        assert compatibility["distinct_phase_project_keys"] == sorted(
            {tranche.PHASE2_KEY, tranche.PHASE3_KEY}
        )
        assert result["published"] is False
        assert result["prospective_final_artifact_exists"] is False
        assert not any(result["prospective_final_sources_exist"].values())
        assert result["release_integration"] == "none"
        assert result["federation_integration"] == "none"
        assert result["identity_integration"] == "none"
        assert result["construction_master_integration"] == "none"
        assert result["map_integration"] == "none"
        assert result["ledger_integration"] == "none"
        assert stat.S_IMODE(prepared.source_stage.stat().st_mode) == 0o700
        assert stat.S_IMODE(prepared.artifact_stage.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in prepared.source_stage.iterdir()
        )
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in prepared.artifact_stage.iterdir()
        )
    finally:
        _cleanup(prepared)


def test_two_fixed_prepublication_replays_are_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    first = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    second = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        assert first.source_stage != second.source_stage
        assert first.artifact_stage != second.artifact_stage
        assert tranche.tree_digest(first.source_stage) == tranche.tree_digest(
            second.source_stage
        )
        assert tranche.tree_digest(first.artifact_stage) == tranche.tree_digest(
            second.artifact_stage
        )
        assert (
            first.source_stage / tranche.SOURCE_FILENAME
        ).read_bytes() == (
            second.source_stage / tranche.SOURCE_FILENAME
        ).read_bytes()
        for name in tranche.CLOSED_FILES:
            assert (first.artifact_stage / name).read_bytes() == (
                second.artifact_stage / name
            ).read_bytes()
    finally:
        _cleanup(first)
        _cleanup(second)


def test_candidate_build_is_network_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden during replay")

    monkeypatch.setattr(socket, "create_connection", blocked)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        assert tranche.validate_candidate(
            prepared.artifact_stage,
            prepared.source_stage,
            RECORDED_AT,
        )["published"] is False
    finally:
        _cleanup(prepared)


def test_artifact_is_compact_facts_and_hashes_not_raw_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_private_stages(tmp_path, monkeypatch)
    prepared = tranche.prepare_candidate(recorded_at=RECORDED_AT)
    try:
        entries = {path.name for path in prepared.artifact_stage.iterdir()}
        assert entries == tranche.CLOSED_FILES
        assert not any(
            name.endswith((".body", ".headers", ".html", ".pdf"))
            for name in entries
        )
        rights = json.loads(
            (prepared.artifact_stage / "rights-and-disposition.json").read_text(
                encoding="utf-8"
            )
        )
        assert rights["artifact_is_hash_and_factual_extract_only"] is True
        assert rights["raw_capture_redistributed"] is False
        assert rights["raw_response_bodies_retained_in_artifact"] is False
        assert rights["raw_response_headers_retained_in_artifact"] is False
        assert rights["publisher_media_retained_in_artifact"] is False
    finally:
        _cleanup(prepared)


def test_mutated_capture_copy_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "capture"
    shutil.copytree(tranche.CAPTURE_ORIGIN, copied)
    for path in copied.iterdir():
        path.chmod(0o444)
    copied.chmod(0o555)
    tranche._validate_capture_directory(copied)

    copied.chmod(0o755)
    body = copied / "mount-pleasant.body"
    body.chmod(0o644)
    body.write_bytes(body.read_bytes() + b"\n")
    body.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="pinned file differs"):
        tranche._validate_capture_directory(copied)
    tranche._validate_capture_directory()


def test_v97_tree_and_prospective_final_paths_remain_unchanged() -> None:
    assert tranche.tree_digest(tranche.V97_RELEASE) == (
        tranche.V97_RELEASE_TREE_SHA256
    )
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()
    assert not (tranche.SOURCES_ROOT / tranche.SOURCE_FILENAME).exists()
    witness = tranche._v97_witness()
    assert witness["release_tree_sha256"] == (
        tranche.V97_RELEASE_TREE_SHA256
    )
