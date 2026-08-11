from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        google_official_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import google_official_current_build_gap_20260722 as tranche


def test_exact_source_contract_has_seven_projects_and_no_inference() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 7
    assert sum(len(document["evidence"]) for document in documents.values()) == 12
    assert len({row["key"] for document in documents.values() for row in document["evidence"]}) == 9
    campus_keys = {document["campus"]["stable_key"] for document in documents.values()}
    project_keys = {document["project"]["stable_key"] for document in documents.values()}
    assert len(campus_keys) == len(project_keys) == 7
    assert not campus_keys & project_keys
    assert {document["lifecycle"][0]["value"] for document in documents.values()} == {
        "site_preparation",
        "under_construction",
    }
    for document in documents.values():
        assert document["campus"]["roles"] == document["project"]["roles"] == {}
        assert document["campus"]["coordinates"] is None
        assert document["project"]["coordinates"] is None
        assert document["campus"]["geometry"] is None
        assert document["project"]["geometry"] is None
        assert document["operating_models"] == []
        assert document["workloads"] == []
        assert document["capacities"] == []


def test_collision_witness_reuses_only_five_exact_global_identities() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["exact_v89_stable_key_collisions"] == []
    assert witness["exact_v89_evidence_key_collisions"] == []
    assert witness["exact_master_identity_keys_reused"] == [
        "osm:way/1288894119",
        "osm:way/1288894119:development-project",
        "osm:way/1319701990",
        "osm:way/1319701990:development-project",
        "wikidata:Q136745002",
    ]


def test_four_candidates_remain_review_only() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T02:00:00Z")
    assert assessment["candidate_count"] == 11
    assert assessment["seed_eligible_source_record_count"] == 7
    assert assessment["review_only_count"] == 4
    assert [row["candidate_id"] for row in assessment["candidates"][-4:]] == [
        "skien-second-data-center",
        "project-spade-montgomery-county-missouri",
        "michigan-city-project-maize",
        "morgan-county-indiana",
    ]
    assert all(row["source_paths"] == [] for row in assessment["candidates"][-4:])


def test_capture_set_is_closed_and_exact() -> None:
    directory = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == 30
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 5_889_063


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 7
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
        assert manifest["curated_source_records"] == 7
        assert manifest["review_only_candidates"] == 4
        snapshot = json.loads((prepared.artifact_stage / "source-snapshot.json").read_text())
        assert snapshot["totals"]["new_entities_against_v89"] == 14
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
    with pytest.raises(RuntimeError, match="partial Google source final-path collision"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_collision_rolls_back_promoted_sources(tmp_path, monkeypatch) -> None:
    source_root = tmp_path / "sources"
    artifact_root = tmp_path / "artifacts"
    source_root.mkdir()
    artifact_root.mkdir()
    documents = tranche.expected_source_documents()
    source_stage = Path(tranche.tempfile.mkdtemp(dir=source_root))
    artifact_stage = Path(tranche.tempfile.mkdtemp(dir=artifact_root))
    tranche._write_source_stage(source_stage, documents)
    tranche._write_artifact_stage(artifact_stage, "2099-01-01T00:00:00Z", documents)
    monkeypatch.setattr(tranche, "SOURCES_ROOT", source_root)
    monkeypatch.setattr(tranche, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(tranche, "ARTIFACT", artifact_root / tranche.ARTIFACT_ID)
    prepared = tranche._Prepared(source_stage, artifact_stage, "2099-01-01T00:00:00Z")
    original = tranche._promote_noreplace
    calls = 0

    def collide(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise FileExistsError("injected late collision")
        original(source, destination)

    monkeypatch.setattr(tranche, "_promote_noreplace", collide)
    monkeypatch.setattr(tranche.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(tranche, "_instant", lambda _value: datetime.now(UTC) - timedelta(seconds=1))
    try:
        with pytest.raises(FileExistsError, match="injected late collision"):
            tranche._publish(prepared)
        assert not any(source_root.glob("curated-*.json"))
        assert not tranche.ARTIFACT.exists()
    finally:
        if source_stage.exists():
            source_stage.chmod(0o700)
            shutil.rmtree(source_stage)
        if artifact_stage.exists():
            artifact_stage.chmod(0o700)
            shutil.rmtree(artifact_stage)
