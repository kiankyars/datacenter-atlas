from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        microsoft_official_current_build_gap_20260721 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import microsoft_official_current_build_gap_20260721 as tranche


def test_exact_source_contract_has_nine_separate_projects_and_no_inference() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 9
    campus_keys = {document["campus"]["stable_key"] for document in documents.values()}
    project_keys = {document["project"]["stable_key"] for document in documents.values()}
    assert len(campus_keys) == len(project_keys) == 9
    assert not campus_keys & project_keys
    assert {
        document["lifecycle"][0]["value"] for document in documents.values()
    } == {"site_preparation", "under_construction"}
    for document in documents.values():
        assert document["campus"]["roles"] == document["project"]["roles"] == {}
        assert document["campus"]["coordinates"] is None
        assert document["project"]["coordinates"] is None
        assert document["campus"]["geometry"] is None
        assert document["project"]["geometry"] is None
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []


def test_collision_witness_reuses_only_exact_master_identities() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["exact_v88_stable_key_collisions"] == []
    assert witness["exact_v88_evidence_key_collisions"] == []
    assert witness["exact_master_identity_keys_reused"] == [
        "osm:way/1383040174",
        "osm:way/1383040174:development-project",
        "osm:way/1383040176",
        "osm:way/1383040176:development-project",
    ]


def test_donnacona_is_review_only_and_other_nine_are_seed_eligible() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T01:00:00Z")
    assert assessment["candidate_count"] == 10
    assert assessment["seed_eligible_source_record_count"] == 9
    assert assessment["review_only_count"] == 1
    donnacona = assessment["candidates"][-1]
    assert donnacona["candidate_id"] == "donnacona"
    assert donnacona["decision"] == "review_only_mixed_stage_schema_boundary"
    assert donnacona["source_paths"] == []


def test_capture_set_is_closed_and_exact() -> None:
    directory = (
        tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    )
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == 20
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 1_907_997


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 9
        return
    recorded_at = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)
    ).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        manifest = tranche.validate_artifact(
            prepared.artifact_stage,
            source_paths=tranche._source_paths(prepared.source_stage),
            require_live=False,
            wall_clock=tranche._instant(recorded_at),
        )
        assert manifest["curated_source_records"] == 9
        assert manifest["review_only_candidates"] == 1
        snapshot = json.loads(
            (prepared.artifact_stage / "source-snapshot.json").read_text()
        )
        assert snapshot["totals"]["new_entities_against_v88"] == 18
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            prepared.artifact_stage.chmod(0o700)
            shutil.rmtree(prepared.artifact_stage)


def test_partial_final_collision_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAMES[0]).write_text("collision")
    with pytest.raises(RuntimeError, match="partial Microsoft source final-path collision"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")
