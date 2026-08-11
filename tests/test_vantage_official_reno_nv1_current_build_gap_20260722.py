from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shutil

import pytest

try:
    from datacenter_atlas.datacenter_atlas import (
        vantage_official_reno_nv1_current_build_gap_20260722 as tranche,
    )
except ModuleNotFoundError:  # pragma: no cover
    from datacenter_atlas import (  # type: ignore[no-redef]
        vantage_official_reno_nv1_current_build_gap_20260722 as tranche,
    )


def test_exact_source_contract_has_one_nv12_project_and_one_capacity() -> None:
    documents = tranche.expected_source_documents()
    assert tuple(documents) == tranche.SOURCE_FILENAMES
    document = documents[tranche.SOURCE_FILENAME]
    assert document["campus"]["stable_key"] == tranche.CAMPUS_KEY
    assert document["project"]["stable_key"] == tranche.PROJECT_KEY
    assert len(document["evidence"]) == 4
    assert document["lifecycle"] == [
        {
            "entity": "project",
            "value": "shell",
            "evidence_key": tranche.PRIMARY_EVIDENCE_KEY,
            "as_of_date": "2026-01-22",
            "method": "authoritative_physical_status_update",
            "confidence": 0.99,
        }
    ]
    assert len(document["capacities"]) == 1
    capacity = document["capacities"][0]
    assert capacity["entity"] == "project"
    assert capacity["metric"] == "critical_it_mw"
    assert capacity["stage"] == "planned"
    assert [capacity[key] for key in ("low", "base", "high")] == [64, 64, 64]
    for entity in ("campus", "project"):
        assert document[entity]["roles"] == {}
        assert document[entity]["coordinates"] is None
        assert document[entity]["geometry"] is None
    assert document["operating_models"] == []
    assert document["workloads"] == []


def test_aggregates_are_metadata_and_nv11_is_review_only() -> None:
    assessment = tranche._candidate_assessment("2026-07-22T02:00:00Z")
    nv12, nv11 = assessment["candidates"]
    assert nv12["lifecycle"]["status"] == "shell"
    assert nv12["lifecycle"]["current_status_persisted"] is False
    assert nv12["normalized_capacity"]["base"] == 64
    assert [row["value"] for row in nv12["reported_context_not_normalized"]] == [128, 224, 500]
    assert nv11["decision"] == "review_only_context_no_current_status_claim"
    assert nv11["source_paths"] == []
    assert nv11["operation_claim_created"] is False
    assert nv11["capacity_claim_created"] is False


def test_collision_witness_creates_no_existing_identity_link() -> None:
    witness = tranche._collision_witness(tranche.expected_source_documents())
    assert witness["v90_selected_input_count"] == 477
    assert witness["v90_entity_count"] == 973
    assert witness["exact_v90_stable_key_collisions"] == []
    assert witness["exact_v90_evidence_key_collisions"] == []
    assert witness["exact_v90_address_matches"] == []
    assert witness["exact_existing_identity_keys_reused"] == []


def test_capture_set_is_closed_and_exact() -> None:
    directory = tranche.resolve_external_capture(tranche.CAPTURE_ORIGIN, tranche.CAPTURE_TRASH)
    tranche._validate_capture_directory(directory)
    assert len(tranche.CAPTURES) == 4
    assert len(tranche.CAPTURE_FILE_PINS) == 8
    assert sum(size for size, _digest in tranche.CAPTURE_FILE_PINS.values()) == 9_532_448


def test_private_stage_replays_offline_and_has_no_final_path_side_effect() -> None:
    if tranche.ARTIFACT.exists():
        manifest = tranche.validate_artifact()
        assert manifest["curated_source_records"] == 1
        return
    recorded_at = (datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    prepared = tranche._prepare(recorded_at)
    try:
        manifest = tranche.validate_artifact(prepared.artifact_stage, source_paths=tranche._source_paths(prepared.source_stage), require_live=False, wall_clock=tranche._instant(recorded_at))
        assert manifest["curated_source_records"] == 1
        snapshot = json.loads((prepared.artifact_stage / "source-snapshot.json").read_text())
        assert snapshot["totals"]["normalized_critical_it_mw_sum"] == 64
        assert snapshot["totals"]["capacity_estimates"] == 1
        assert snapshot["totals"]["energy_estimates"] == 0
        assert snapshot["totals"]["unique_physical_sites_claimed"] == 0
    finally:
        if prepared.source_stage.exists():
            shutil.rmtree(prepared.source_stage)
        if prepared.artifact_stage.exists():
            prepared.artifact_stage.chmod(0o700)
            shutil.rmtree(prepared.artifact_stage)


def test_partial_final_collision_fails_closed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(tranche, "SOURCES_ROOT", tmp_path)
    monkeypatch.setattr(tranche, "ARTIFACT", tmp_path / "artifact")
    (tmp_path / tranche.SOURCE_FILENAME).write_text("collision")
    with pytest.raises(RuntimeError, match="partial Vantage source final-path collision"):
        tranche.build(recorded_at="2099-01-01T00:00:00Z")


def test_late_collision_rolls_back_promoted_source(tmp_path, monkeypatch) -> None:
    source_root, artifact_root = tmp_path / "sources", tmp_path / "artifacts"
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


def test_future_time_and_tamper_guards_after_publication(tmp_path) -> None:
    if not tranche.ARTIFACT.exists():
        pytest.skip("final artifact not published yet")
    manifest = tranche.validate_artifact()
    before = tranche._instant(manifest["recorded_at"]) - timedelta(microseconds=1)
    with pytest.raises(RuntimeError, match="recorded_at is not live"):
        tranche.validate_artifact(wall_clock=before)
    copied = tmp_path / "artifact"
    shutil.copytree(tranche.ARTIFACT, copied)
    copied.chmod(0o755)
    target = copied / "candidate-assessment.json"
    target.chmod(0o644)
    target.write_bytes(target.read_bytes() + b" ")
    target.chmod(0o444)
    copied.chmod(0o555)
    with pytest.raises(RuntimeError, match="manifest file pin differs"):
        tranche.validate_artifact(copied)
