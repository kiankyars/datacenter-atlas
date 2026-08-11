from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil
import stat

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        centra_rno2_official_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        centra_rno2_official_current_build_gap_20260722 as tranche,
    )


def test_exact_source_contract_maps_topout_to_shell_only() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    document = documents[tranche.SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert len(document["evidence"]) == 3
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "shell",
            "evidence_key": tranche.TOPOUT_EVIDENCE_KEY,
            "as_of_date": "2026-04-30",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    for entity in ("campus", "project"):
        assert document[entity]["address"] == "Reno, Nevada, United States"
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None


def test_colocation_is_generic_and_4_4mw_is_not_a_capacity() -> None:
    document = tranche.expected_source_documents()[tranche.SOURCE_FILENAME]
    assert document["operating_models"] == [
        {
            "entity": "project",
            "value": "colocation",
            "evidence_key": tranche.TOPOUT_EVIDENCE_KEY,
            "as_of_date": "2026-04-30",
            "method": "company_disclosure",
            "confidence": 0.99,
        }
    ]
    assert document["workloads"] == []
    assert document["capacities"] == []
    serialized = json.dumps(document, sort_keys=True)
    assert "4.4" in serialized
    assert "untyped_metadata_only" in serialized
    assert "not_critical_it" not in json.dumps(document["capacities"])
    assert "AI-ready" in serialized
    assert "design intent" in serialized


def test_topout_publication_timestamp_is_exact_official_html_value() -> None:
    document = tranche.expected_source_documents()[tranche.SOURCE_FILENAME]
    topout = next(
        row for row in document["evidence"] if row["key"] == tranche.TOPOUT_EVIDENCE_KEY
    )
    assert topout["published_at"] == "2026-04-30T17:47:37.152Z"
    assert topout["metadata"]["linkedin_activity_id"] == "7455674234259030016"
    assert topout["metadata"]["physical_status_as_reported"] == (
        "officially topped out; structural completion"
    )
    assert "current status at retrieval" not in topout["excerpt"]


def test_novva_phases_are_review_only_despite_cms_update() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T05:00:00Z")
    assert assessment["candidate_count"] == 3
    assert assessment["seed_eligible_candidate_count"] == 1
    assert assessment["review_only_count"] == 2
    phase_2, phase_3 = assessment["candidates"][1:]
    assert phase_2["reported_old_start"] == "December 2023"
    assert phase_3["reported_old_start"] == "January 2024"
    for row in (phase_2, phase_3):
        assert row["decision"] == (
            "review_only_no_post_2025_phase_specific_physical_observation"
        )
        assert row["reported_critical_it_mw_not_normalized"] == 72
        assert row["source_paths"] == []
        assert row["stable_key_created"] is False
        assert row["lifecycle_claim_created"] is False
        assert row["capacity_claim_created"] is False
        assert row["later_official_physical_observation_found"] is False
        assert "July 7, 2026 CMS-updated date" in row["cms_update_guardrail"]
        assert "Current phase status remains unknown" in row["status_semantics"]


def test_capture_set_is_closed_exact_and_all_successful() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 7
    assert len(tranche.CAPTURE_FILE_PINS) == 14
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == (
        tranche.CAPTURE_TOTAL_BYTES
    )
    assert tranche.tree_digest(directory) == tranche.CAPTURE_TREE_SHA256
    inventory = tranche._capture_inventory("2026-07-22T05:00:00Z")
    assert inventory["successful_http_200_body_captures"] == 7
    assert inventory["failed_http_body_captures"] == 0
    assert inventory["raw_capture_redistributed"] is False


def test_v94_collision_witness_is_exact_and_nonintegrated() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v94_selected_input_count"] == 498
    assert witness["v94_entity_count"] == 1_011
    assert witness["planned_distinct_stable_keys"] == 2
    assert witness["planned_distinct_evidence_keys"] == 3
    assert witness["exact_v94_stable_key_collisions"] == []
    assert witness["exact_v94_evidence_key_collisions"] == []
    assert witness["exact_v94_rno2_identity_matches"] == []


def test_private_stage_replays_offline_without_final_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 1
        return
    final_paths = [
        tranche.ARTIFACT,
        *(tranche.SOURCES_ROOT / name for name in tranche.SOURCE_FILENAMES),
    ]
    assert not any(path.exists() or path.is_symlink() for path in final_paths)
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        assert not any(path.exists() or path.is_symlink() for path in final_paths)
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_paths=tranche._source_paths(prepared.source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["candidate_assessments"] == 3
        assert manifest["review_only_candidates"] == 2
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["distinct_entities_in_source_records"] == 2
        assert snapshot["totals"]["capacity_estimates"] == 0
        assert snapshot["totals"]["operating_model_observations"] == 1
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            shutil.rmtree(prepared.artifact_stage)


def test_freeze_changes_only_staged_members_and_meets_chronology(
    tmp_path: Path,
) -> None:
    source_stage = tmp_path / "sources"
    artifact_stage = tmp_path / "artifact"
    source_stage.mkdir()
    artifact_stage.mkdir()
    documents = tranche.expected_source_documents()
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(
        artifact_stage, "2000-01-01T00:00:00Z", documents
    )
    prepared = tranche._Prepared(
        source_stage, artifact_stage, "2000-01-01T00:00:00Z"
    )
    tranche._freeze_after_barrier(prepared)
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444 for path in source_stage.iterdir()
    )
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444 for path in artifact_stage.iterdir()
    )
    assert stat.S_IMODE(artifact_stage.stat().st_mode) == 0o555
    tranche._assert_chronology(
        [artifact_stage, *artifact_stage.iterdir(), *source_stage.iterdir()],
        prepared.recorded_at,
    )


def test_partial_final_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAME).write_text("collision")
    with pytest.raises(RuntimeError, match="partial CENTRA final-path collision"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_source_and_artifact_tamper_fail_closed(tmp_path: Path) -> None:
    source_stage = tmp_path / "sources"
    artifact_stage = tmp_path / "artifact"
    source_stage.mkdir()
    artifact_stage.mkdir()
    documents = tranche.expected_source_documents()
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(
        artifact_stage, "2099-01-01T00:00:00Z", documents
    )
    source = source_stage / tranche.SOURCE_FILENAME
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="CENTRA source differs"):
        tranche.validate_artifact(
            artifact_stage,
            source_paths=tranche._source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant("2099-01-01T00:00:00Z"),
        )
    tranche._write_source_stage(source_stage, documents)
    assessment = artifact_stage / "candidate-assessment.json"
    assessment.write_bytes(assessment.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="CENTRA manifest pin differs"):
        tranche.validate_artifact(
            artifact_stage,
            source_paths=tranche._source_paths(source_stage),
            require_live=False,
            require_frozen=False,
            wall_clock=tranche._instant("2099-01-01T00:00:00Z"),
        )


def test_future_time_guard_after_publication() -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("final artifact not published yet")
    manifest = tranche.validate_artifact()
    before = tranche._instant(manifest["recorded_at"]) - timedelta(microseconds=1)
    with pytest.raises(RuntimeError, match="CENTRA recorded_at is not live"):
        tranche.validate_artifact(wall_clock=before)
