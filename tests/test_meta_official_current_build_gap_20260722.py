from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        meta_official_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import meta_official_current_build_gap_20260722 as tranche


def test_exact_source_contract_has_three_projects_and_no_normalized_inference() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 3
    assert sum(len(document["evidence"]) for document in documents.values()) == 6
    assert len({row["key"] for document in documents.values() for row in document["evidence"]}) == 5
    assert {document["project"]["stable_key"] for document in documents.values()} == {
        "curated:meta-bowling-green-data-center:2025-current-campus-build",
        "curated:meta-beaver-dam-data-center:2025-current-campus-build",
        "curated:meta-montgomery-data-center:2025-two-building-expansion",
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
        assert document["lifecycle"][0]["value"] == "under_construction"


def test_collision_witness_reuses_campuses_and_forbids_same_name_facilities() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["exact_v90_stable_key_collisions"] == [
        "epoch-ai:data-center:dec73855-d62c-5f35-bd1a-3b1f00b20bec"
    ]
    assert witness["exact_v90_evidence_key_collisions"] == []
    assert witness["exact_global_open_campus_identity_keys_reused"] == [
        "pnnl_im3:2026-02-09:campus/01377162298",
        "pnnl_im3:2026-02-09:campus/01453996659",
    ]
    assert witness["forbidden_global_open_facility_keys"] == [
        "osm:way/1377162298",
        "osm:way/1453996659",
    ]


def test_jamnagar_is_review_only_without_a_physical_start() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T02:00:00Z")
    assert assessment["candidate_count"] == 4
    assert assessment["seed_eligible_source_record_count"] == 3
    assert assessment["review_only_count"] == 1
    jamnagar = assessment["candidates"][-1]
    assert jamnagar["candidate_id"] == "jamnagar-reliance-lease-agreement"
    assert jamnagar["source_paths"] == []
    assert jamnagar["seed_eligible"] is False


def test_context_numbers_stay_metadata_not_normalized_capacity() -> None:
    documents = tranche.expected_source_documents()
    metadata = [
        evidence["metadata"]
        for document in documents.values()
        for evidence in document["evidence"]
    ]
    assert any("energy_infrastructure_spend_not_capacity" in row for row in metadata)
    assert any("renewable_project_context_not_capacity" in row for row in metadata)
    assert all(not document["capacities"] for document in documents.values())


def test_capture_set_is_closed_and_exact() -> None:
    directory = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == 12
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 1_313_782


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 3
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
        assert manifest["curated_source_records"] == 3
        assert manifest["review_only_candidates"] == 1
        snapshot = json.loads((prepared.artifact_stage / "source-snapshot.json").read_text())
        assert snapshot["totals"]["new_entities_against_v90"] == 5
        assert snapshot["totals"]["unique_imported_entity_snapshots"] == 6
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
    with pytest.raises(RuntimeError, match="partial Meta source final-path collision"):
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
