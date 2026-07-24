from __future__ import annotations

import inspect
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        official_nordic_tranche_prepublication_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        official_nordic_tranche_prepublication_20260722 as tranche,
    )


def _documents() -> dict[str, dict[str, object]]:
    return tranche.expected_source_documents()


def _cleanup(prepared: tranche.PreparedCandidate) -> None:
    if prepared.source_stage.exists():
        shutil.rmtree(prepared.source_stage)
    if prepared.artifact_stage.exists():
        shutil.rmtree(prepared.artifact_stage)


def test_exact_source_inventory_and_zero_spatial_or_metric_rows() -> None:
    documents = _documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 3
    assert sum(len(document["evidence"]) for document in documents.values()) == 8
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 3
    for document in documents.values():
        assert document["schema_version"] == "1.1"
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []
        for entity in ("campus", "project"):
            assert document[entity]["coordinates"] is None
            assert document[entity]["geometry"] is None


def test_xtx_second_facility_is_underway_without_first_facility_inheritance() -> None:
    document = _documents()[tranche.XTX_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.XTX_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.XTX_PROJECT_KEY
    assert document["project"]["address"] == "Kajaani, Finland"
    assert document["project"]["roles"] == {
        "developer": ["XTX Markets"],
        "contractor": ["YIT", "Bravida Finland"],
    }
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.XTX_SECOND_EVIDENCE_KEY,
            "as_of_date": "2026-06-25",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    second = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.XTX_SECOND_EVIDENCE_KEY
    )
    assert second["content_hash"] == (
        "a72ca5eb8725b7434d75bb981b9bee986b1ed653d696a12d842af17d239f2a56"
    )
    assert second["metadata"]["physical_status_as_reported"] == (
        "Bravida's work for the second data center is already underway."
    )
    identity = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.XTX_IDENTITY_EVIDENCE_KEY
    )
    first = identity["metadata"]["first_facility_metrics_not_inherited"]
    assert first == {
        "floor_area_sqm": 15_000,
        "data_halls": 3,
        "it_power_mw": 22.5,
        "scope": "first_data_center_only",
        "second_facility_capacity_row_created": False,
    }
    assert document["capacities"] == []
    assert document["workloads"] == []


def test_xtx_third_facility_is_review_only_future_intent() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T04:20:00Z")
    third = next(
        row
        for row in assessment["candidates"]
        if row["candidate_id"] == "xtx-kajaani-third-data-center"
    )
    assert third["decision"] == "review_only_future_intent_no_physical_start"
    assert third["source_paths"] == []
    assert third["stable_key_created"] is False
    assert third["lifecycle_claim_created"] is False
    assert third["capacity_claim_created"] is False


def test_skygard_phase_2_start_does_not_inherit_osl1_power_or_pue() -> None:
    document = _documents()[tranche.SKYGARD_SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.SKYGARD_CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.SKYGARD_PROJECT_KEY
    assert document["project"]["address"] == "Hovinbyen, Oslo, Norway"
    assert document["project"]["roles"] == {
        "operator": ["Skygard"],
        "contractor": ["HENT"],
    }
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.SKYGARD_PHASE2_EVIDENCE_KEY,
            "as_of_date": "2026-06-16",
            "method": "authoritative_construction_start",
            "confidence": 0.99,
        }
    ]
    phase = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.SKYGARD_PHASE2_EVIDENCE_KEY
    )
    assert phase["content_hash"] == (
        "7448563a29b0e39cf807f6409a1efe7d7dfd90a92daef928651dfe9dcbe34228"
    )
    assert phase["metadata"]["physical_status_as_reported"] == (
        "Construction start is immediate."
    )
    assert "MEP is explicitly excluded" in phase["metadata"]["mep_scope_guardrail"]
    identity = next(
        row
        for row in document["evidence"]
        if row["key"] == tranche.SKYGARD_IDENTITY_EVIDENCE_KEY
    )
    metrics = identity["metadata"]["whole_facility_metrics_not_phase_allocated"]
    assert metrics["capacity_mw"] == 20
    assert metrics["pue_as_reported"] == "~1.2 and <1.2 average"
    assert metrics["phase_2_capacity_row_created"] is False
    assert metrics["phase_2_pue_row_created"] is False
    assert document["capacities"] == []


def test_fin04_is_exact_existing_phase_successor_with_430mw_untyped() -> None:
    predecessor = json.loads(tranche.FIN04_PREDECESSOR.read_text(encoding="utf-8"))
    successor = _documents()[tranche.FIN04_SOURCE_FILENAME]
    assert successor["schema_version"] == "1.1"
    assert successor["campus"]["stable_key"] == tranche.FIN04_CAMPUS_KEY
    assert successor["project"]["stable_key"] == tranche.FIN04_PROJECT_KEY
    assert successor["project"]["roles"] == {
        "developer": ["atNorth"],
        "contractor": ["YIT"],
    }
    assert successor["evidence"][:-1] == predecessor["evidence"]
    assert len(successor["evidence"]) == len(predecessor["evidence"]) + 1
    assert successor["lifecycle"] == [
        {
            "entity": "project",
            "value": "under_construction",
            "evidence_key": tranche.FIN04_YIT_EVIDENCE_KEY,
            "as_of_date": "2026-07-21",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    yit = successor["evidence"][-1]
    assert yit["key"] == tranche.FIN04_YIT_EVIDENCE_KEY
    assert yit["content_hash"] == (
        "678a6298ce048e09e42c2e8aa416217f0ec05124e0ec4d25002ec4063df4f1b6"
    )
    capacity = yit["metadata"]["entire_campus_capacity_not_normalized"]
    assert capacity["value"] == 430
    assert capacity["typing"] == "untyped_entire_campus_planning_metadata_only"
    assert capacity["project_capacity_row_created"] is False
    assert capacity["campus_capacity_row_created"] is False
    assert successor["capacities"] == []
    assert successor["workloads"] == []
    serialized = json.dumps(successor, sort_keys=True)
    assert "no additional phase is inferred" in serialized


def test_capture_bundle_is_exact_frozen_and_private() -> None:
    tranche._validate_capture_directory()
    assert len(tranche.CAPTURES) == 6
    assert len(tranche.CAPTURE_FILE_PINS) == tranche.CAPTURE_FILE_COUNT == 12
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(tranche.CAPTURE_ORIGIN) == tranche.CAPTURE_TREE_SHA256
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in tranche.CAPTURE_ORIGIN.iterdir()
    )
    inventory = tranche._retrieval_inventory("2026-07-22T04:20:00Z")
    assert inventory["successful_http_200_body_captures"] == 6
    assert inventory["normalized_claim_capture_count"] == 5
    assert inventory["same_publisher_duplicate_verification_capture_count"] == 1
    assert inventory["raw_capture_redistributed"] is False


def test_v94_witness_reuses_only_fin04_and_pins_predecessor() -> None:
    witness = tranche._v94_witness()
    assert witness["v94_selected_input_count"] == 498
    assert witness["v94_entity_count"] == 1_011
    assert witness["fin04_predecessor_selected_once"] is True
    assert witness["fin04_predecessor_pin"] == {
        "path": f"sources/{tranche.FIN04_PREDECESSOR_FILENAME}",
        "bytes": 15_068,
        "sha256": ("28773caea4d839386074e6bd3003953c75c9f1bbd3441442a83cfc2d9ca22fe4"),
    }
    assert witness["existing_stable_keys_reused"] == [
        tranche.FIN04_CAMPUS_KEY,
        tranche.FIN04_PROJECT_KEY,
    ]
    assert witness["new_phase_created_for_fin04"] is False


def test_builder_has_no_publisher_and_builds_private_replayable_stages() -> None:
    assert not hasattr(tranche, "publish")
    assert not hasattr(tranche, "_publish")
    source = inspect.getsource(tranche.prepare_candidate)
    assert "_promote" not in source
    assert "rename" not in source
    assert not tranche.PROSPECTIVE_ARTIFACT.exists()
    assert not any(
        (tranche.SOURCES_ROOT / name).exists() for name in tranche.SOURCE_FILENAMES
    )
    prepared = tranche.prepare_candidate(recorded_at="2026-07-22T04:20:00Z")
    try:
        manifest = tranche.validate_candidate(
            prepared.artifact_stage, prepared.source_stage
        )
        assert manifest["published"] is False
        assert manifest["publisher_function_present"] is False
        assert manifest["curated_source_candidates"] == 3
        assert manifest["review_only_candidates"] == 1
        result = tranche.candidate_result(prepared)
        assert result["status"] == ("PREPUBLICATION_CANDIDATE_BUILT_NOT_PUBLISHED")
        assert result["published"] is False
        assert result["prospective_final_artifact_exists"] is False
        assert result["prospective_final_source_exists"] is False
        assert stat.S_IMODE(prepared.source_stage.stat().st_mode) == 0o700
        assert stat.S_IMODE(prepared.artifact_stage.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600
            for path in prepared.source_stage.iterdir()
        )
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"] == {
            "candidate_assessments": 4,
            "source_records": 3,
            "governed_prepublication_candidates": 3,
            "review_only_candidates": 1,
            "distinct_campuses_in_source_records": 3,
            "projects": 3,
            "distinct_entity_snapshots": 6,
            "new_entities_against_v94": 4,
            "reused_existing_entities": 2,
            "evidence_records": 8,
            "lifecycle_observations": 3,
            "operating_model_observations": 0,
            "workload_observations": 0,
            "capacity_estimates": 0,
            "coordinate_observations": 0,
            "geometry_observations": 0,
            "satellite_observations": 0,
        }
        assert snapshot["integration"]["v95_files_touched"] == []
    finally:
        _cleanup(prepared)


def test_source_and_artifact_tamper_fail_closed() -> None:
    prepared = tranche.prepare_candidate(recorded_at="2026-07-22T04:20:00Z")
    try:
        source = prepared.source_stage / tranche.XTX_SOURCE_FILENAME
        source.write_bytes(source.read_bytes() + b"\n")
        with pytest.raises(RuntimeError, match="staged source differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
        source.write_bytes(
            tranche._canonical(
                tranche.expected_source_documents()[tranche.XTX_SOURCE_FILENAME]
            )
        )
        assessment = prepared.artifact_stage / "candidate-assessment.json"
        assessment.write_bytes(assessment.read_bytes() + b" ")
        with pytest.raises(RuntimeError, match="candidate manifest pin differs"):
            tranche.validate_candidate(prepared.artifact_stage, prepared.source_stage)
    finally:
        _cleanup(prepared)


def test_prospective_final_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "PROSPECTIVE_ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.XTX_SOURCE_FILENAME).write_text("collision")
    with pytest.raises(RuntimeError, match="prospective final-path collision"):
        tranche.prepare_candidate(recorded_at="2026-07-22T04:20:00Z")
