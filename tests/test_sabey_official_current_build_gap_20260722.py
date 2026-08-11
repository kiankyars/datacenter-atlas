from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        sabey_official_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import sabey_official_current_build_gap_20260722 as tranche


def test_exact_source_contract_has_two_pairs_and_no_normalized_inference() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    assert len(documents) == 2
    assert sum(len(document["evidence"]) for document in documents.values()) == 6
    assert len({row["key"] for document in documents.values() for row in document["evidence"]}) == 6
    assert sum(len(document["lifecycle"]) for document in documents.values()) == 3
    assert {document["campus"]["stable_key"] for document in documents.values()} == {
        "curated:sabey-sdc-ashburn-campus",
        "curated:sabey-sdc-austin-round-rock-campus",
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


def test_austin_preserves_start_and_adds_exact_shell_update() -> None:
    documents = tranche.expected_source_documents()
    austin = documents[tranche.SOURCE_FILENAMES[1]]
    assert [
        (row["value"], row["as_of_date"], row["method"])
        for row in austin["lifecycle"]
    ] == [
        ("under_construction", "2025-07-29", "authoritative_construction_start"),
        ("shell", "2026-06-16", "authoritative_physical_status_update"),
    ]


def test_power_pue_design_and_roles_remain_metadata_only() -> None:
    documents = tranche.expected_source_documents()
    metadata = [
        evidence["metadata"]
        for document in documents.values()
        for evidence in document["evidence"]
    ]
    assert any("pue_context_not_normalized" in row for row in metadata)
    assert any("roles_and_joint_venture_context_not_normalized" in row for row in metadata)
    assert all(not document["capacities"] for document in documents.values())
    assert all(not document["workloads"] for document in documents.values())
    assert all(not document["operating_models"] for document in documents.values())


def test_collision_witness_keeps_structural_buildings_distinct() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["exact_v91_stable_key_collisions"] == []
    assert witness["exact_v91_evidence_key_collisions"] == []
    assert witness["related_global_open_structural_keys_not_reused"] == [
        "osm:way/793888427",
        "pnnl_im3:2026-02-09:building/00793888427",
    ]


def test_capture_set_is_closed_and_exact() -> None:
    directory = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURE_FILE_PINS) == 12
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 587_054


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 2
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
        assert manifest["curated_source_records"] == 2
        assert manifest["review_only_candidates"] == 0
        snapshot = json.loads((prepared.artifact_stage / "source-snapshot.json").read_text())
        assert snapshot["totals"]["new_entities_against_v91"] == 4
        assert snapshot["totals"]["capacity_estimates"] == 0
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
    with pytest.raises(RuntimeError, match="partial Sabey source final-path collision"):
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
        if calls == 2:
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
